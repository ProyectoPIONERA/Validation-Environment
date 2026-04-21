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

## Se Acumulan Datos de Validación

Habilita o ejecuta limpieza previa cuando las pruebas repetidas creen demasiados datos.

La limpieza debe ser adapter-aware y escribir reporte bajo la carpeta del experimento actual.
