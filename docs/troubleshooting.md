# Troubleshooting

## Las Entradas de Hosts No Resuelven

Previsualiza las entradas esperadas:

```bash
python3 main.py edc hosts --topology local --dry-run
```

Aplica entradas solo con sincronización explícita:

```bash
PIONERA_SYNC_HOSTS=true \
PIONERA_HOSTS_FILE=/etc/hosts \
python3 main.py edc hosts --topology local
```

Si una entrada ya existe, el gestor de hosts la omite en lugar de duplicarla.

## Los Servicios Minikube No Son Accesibles

En despliegues locales, mantén esto abierto en otra terminal:

```bash
minikube tunnel
```

Verifica también:

```bash
kubectl get pods -A
kubectl get ingress -A
helm list -A
```

## Los Conectores Solo Funcionan con Port-forward

En local, el resultado correcto es que los conectores sean accesibles por su
hostname público de Ingress, por ejemplo:

```text
http://conn-<connector>-<dataspace>.dev.ds.dataspaceunit.upm/inesdata-connector-interface
http://conn-<connector>-<dataspace>.dev.ds.dataspaceunit.upm/edc-dashboard/
```

Si solo funcionan con `kubectl port-forward`, revisa primero:

- que `minikube tunnel` esté abierto;
- que las entradas de `hosts` existan para el dataspace y sus conectores;
- que el Ingress del namespace exista y tenga dirección;
- que los pods y endpoints del conector estén listos.

Comandos útiles:

```bash
python3 main.py inesdata hosts --topology local --dry-run
python3 main.py edc hosts --topology local --dry-run
kubectl get ingress -A
kubectl get endpoints -A
```

El fallback de `port-forward` para conectores está desactivado por defecto para
no ocultar problemas reales de routing. Úsalo solo como diagnóstico temporal:

```bash
PIONERA_ALLOW_CONNECTOR_PORT_FORWARD_FALLBACK=true
```

## Falla la Autenticación Admin de Keycloak

Comprueba que:

- los servicios comunes están en ejecución;
- la URL admin de Keycloak resuelve;
- las credenciales en `deployers/infrastructure/deployer.config` son correctas;
- el fichero `hosts` contiene las entradas de Keycloak;
- el túnel local o ingress está disponible.

## Vault Indica Token Obsoleto

Si nivel 2 o nivel 4 informa que el token de Vault no es válido para el Vault en
ejecución, significa que el estado persistente de Vault y el artefacto local
`deployers/shared/common/init-keys-vault.json` no corresponden entre sí.

No reintentes nivel 4 en bucle. Primero recupera el root token actual de Vault,
si existe, o recrea los servicios comunes de nivel 2 en entorno local para que
el framework vuelva a generar claves consistentes. Después ejecuta de nuevo
nivel 3 y nivel 4.

En un entorno sano no debería ser necesario recrear `common-srvs` en cada
despliegue. Si vuelve a pasar, revisa si se ejecutó el mismo cluster desde dos
copias distintas del framework, si se conservaron PVCs antiguos o si se copió
`init-keys-vault.json` desde otro entorno.

## Level 4 Falla con Keycloak 415

Si `Level 4` falla al crear conectores con un error `415` de Keycloak durante
el mapeo de roles del service account, revisa que estás usando una versión del
framework que restaura `Content-Type: application/json` después de subir el
certificado público del conector.

El síntoma típico aparece justo después de:

```text
Client certificate for <connector> synchronized
```

La corrección forma parte del bootstrap de INESData y permite recrear conectores
con certificados, scopes y roles de service account de forma reproducible.

## Kafka Transfer Queda Omitido por Imagen INESData Antigua

Si `Level 6` muestra `SKIP Kafka transfer` con razón
`kafka_dataaddress_not_supported`, Kafka no necesariamente ha fallado. Ese
resultado indica que el broker y los logins funcionaron, pero el runtime del
conector rechazó assets con `DataAddress.type=Kafka`.

Comprueba la imagen desplegada:

```bash
kubectl get deploy -n demo -o wide
```

En local, `Level 4` debe preparar y desplegar una imagen local de
`inesdata-connector` compatible con Kafka. Si ves una imagen remota antigua,
vuelve a ejecutar `Level 4` o fuerza el comportamiento estricto:

```bash
INESDATA_LOCAL_IMAGES_MODE=required python3 main.py inesdata deploy --topology local
```

## Level 4 Falla Preparando Imágenes INESData

En topología `local`, `Level 4` recompila `inesdata-connector` e
`inesdata-connector-interface` antes de crear los conectores. Si el log falla
en `Preparing artifacts for connector` con un error de `Gradle Worker Daemon`,
el problema está en el build local previo al despliegue, no en Helm ni en
Kubernetes.

El framework ejecuta Gradle de forma conservadora por defecto:

```text
--no-daemon --no-parallel -Dorg.gradle.workers.max=1
```

Si una máquina de desarrollo tiene más recursos y se quiere acelerar el build,
puede sobreescribirse con:

```bash
GRADLE_MAX_WORKERS=2 python3 main.py menu
```

## EDC Rechaza la Imagen por Defecto

En topología `local`, Level 4 prepara automáticamente la imagen local del
conector EDC cuando no hay overrides explícitos. Para ello usa:

```text
adapters/edc/scripts/build_image.sh --apply
```

Si quieres forzar una imagen concreta, o si estás preparando una topología VM,
define overrides explícitos:

```bash
PIONERA_EDC_CONNECTOR_IMAGE_NAME=validation-environment/edc-connector \
PIONERA_EDC_CONNECTOR_IMAGE_TAG=<tag> \
python3 main.py edc deploy --topology local
```

Esta protección evita desplegar una imagen por defecto no verificada. Si la
preparación automática falla, revisa que Docker, Minikube y el repositorio bajo
`adapters/edc/sources/connector` estén disponibles.

## Playwright EDC Recibe 503 de NGINX

Si todas las pruebas UI de EDC fallan con un error de login y la captura muestra:

```text
503 Service Temporarily Unavailable
nginx
```

significa que el navegador no llegó a Keycloak ni al dashboard. Normalmente el
ingress existe, pero los servicios `*-dashboard` o `*-dashboard-proxy` no tienen
endpoints listos.

Comprueba:

```bash
kubectl get pods -n <dataspace>
kubectl get endpoints -n <dataspace>
```

En local, Level 4 prepara automáticamente las imágenes:

```text
validation-environment/edc-dashboard:latest
validation-environment/edc-dashboard-proxy:latest
```

Level 6 comprueba la disponibilidad de esos endpoints antes de lanzar
Playwright. Si no están listos, guarda el diagnóstico en
`experiments/<experiment>/ui/edc/dashboard_readiness.json`.

## Una Topología VM Requiere Dirección

`vm-single` necesita una dirección de VM:

```bash
PIONERA_VM_EXTERNAL_IP=192.0.2.10 \
python3 main.py edc hosts --topology vm-single --dry-run
```

Si no hay dirección configurada, el CLI falla con un error claro de topología.

## Playwright Falla de Forma Intermitente

Comprueba:

- que la URL objetivo resuelve desde el entorno del navegador;
- que las entradas de `hosts` existen;
- que el dashboard o portal está desplegado;
- que el modo de autenticación coincide con la suite esperada;
- que el reporte en `experiments/` contiene screenshots, trazas o detalles de error.

## Playwright INESData y Transferencias en STARTED

Si el test E2E de transferencia crea el asset, completa la negociación e inicia
la transferencia, `STARTED` es un estado aceptado para la validación UI de
INESData. La UI valida que el transfer fue aceptado e iniciado; la evidencia
fuerte de movimiento de datos debe venir de Newman, MinIO o verificaciones de
storage separadas.

Si la suite falla aunque el historial muestre `STARTED`, o si las validaciones
de almacenamiento fallan, revisa:

- el reporte `e2e-transfer-report.json` o `consumer-transfer-report.json` dentro del experimento;
- la colección Newman `06_consumer_transfer`;
- los logs del conector consumer y provider;
- la disponibilidad de MinIO y del dataplane;
- si `minikube tunnel` pidió contraseña y no quedó realmente activo.

No conviene resolver este caso sustituyendo el hostname por `port-forward`,
porque eso puede validar una ruta distinta a la que usaría el entorno local
publicado por Ingress.

## Transferencia Falla con Assets Subidos en Folder

Si un asset creado desde la UI aparece en catálogo pero la transferencia no
encuentra el objeto en MinIO/S3, comprueba si fue subido con un valor en el
campo `Folder`.

El objeto físico y el `DataAddress` del asset deben usar la misma key. Para
uploads con folder, la key esperada es:

```text
<folder>/<file>
```

El flujo E2E `core/05-e2e-transfer-flow.spec.ts` cubre este caso porque crea un
asset con folder, lo publica, lo descubre desde el consumidor y ejecuta
negociación y transferencia.

## EDC+Kafka Queda en STARTED o No Consume Mensajes

`Level 6` ejecuta la validación funcional EDC+Kafka después de Newman cuando el
adapter tiene soporte Kafka. En local, el broker gestionado por defecto se crea
dentro de Kubernetes para que el dataplane de los conectores lo alcance por DNS
de cluster:

```text
framework-kafka.<namespace>.svc.cluster.local:9092
```

El proceso Python del framework puede abrir un `port-forward` temporal a
`127.0.0.1:<puerto>` para crear topics y verificar mensajes desde el host. Ese
`port-forward` es interno a la validación y no debe usarse como endpoint del
conector.

Si ves errores contra `host.minikube.internal:<puerto>` o transferencias que
quedan en `STARTED`, comprueba que no existan overrides antiguos como:

```text
KAFKA_BOOTSTRAP_SERVERS
KAFKA_CLUSTER_BOOTSTRAP_SERVERS
```

Para la ruta local normal, usa el modo por defecto:

```text
KAFKA_PROVISIONER=kubernetes
```

Durante una ejecución puedes inspeccionar el broker temporal con:

```bash
kubectl get pods,svc -n <dataspace> -l app=framework-kafka
```

## Se Acumulan Datos de Validación

Habilita o ejecuta limpieza previa cuando las pruebas repetidas creen demasiados datos.

La limpieza debe ser adapter-aware y escribir reporte bajo la carpeta del experimento actual.
