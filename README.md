# Validation-Environment

Validation-Environment es un framework para crear entornos reproducibles de
validación de espacios de datos PIONERA. Se utiliza para desplegar dataspaces,
validar conectores, ejecutar pruebas funcionales, recoger métricas y generar
evidencias experimentales de forma trazable.

El punto de entrada principal es `main.py`. El framework está organizado para
trabajar con distintos adapters y topologías sin duplicar la lógica común de
validación.

## Funcionalidades Principales

- desplegar un dataspace por niveles;
- seleccionar el adapter de conectores: `inesdata` o `edc`;
- preparar servicios comunes como Keycloak, MinIO, PostgreSQL y Vault;
- desplegar conectores provider/consumer;
- desplegar componentes opcionales como `ontology-hub` y `ai-model-hub` cuando el adapter lo soporte;
- sincronizar entradas de `hosts` de forma planificada e idempotente;
- ejecutar validaciones API con Newman;
- ejecutar validaciones UI con Playwright;
- comprobar transferencias y almacenamiento en MinIO;
- recoger métricas de control plane y benchmarks Kafka opcionales;
- persistir resultados en `experiments/`;
- producir reportes y artefactos de validación.

## Adapters

| Adapter | Uso |
| --- | --- |
| `inesdata` | Despliegue y validación con conectores INESData y su portal. |
| `edc` | Despliegue y validación con conectores EDC genéricos y dashboard EDC. |

Cada adapter tiene su propio deployer:

```text
deployers/inesdata/
deployers/edc/
```

Los artefactos compartidos viven en:

```text
deployers/shared/
deployers/infrastructure/
```

## Topologías

El framework reconoce tres topologías canónicas:

```text
local
vm-single
vm-distributed
```

`local` es la ruta de despliegue normal y usa Minikube. Las topologías
`vm-single` y `vm-distributed` ya forman parte del contexto del deployer y de la
planificación de hosts. La ejecución real no-local queda protegida por guardas
hasta que la ruta Kubernetes correspondiente esté implementada para cada nivel.

## Inicio Rápido

1. Clona el repositorio:

```bash
git clone --branch feature/new-pionera-automation --single-branch https://github.com/ProyectoPIONERA/Validation-Environment.git
cd Validation-Environment
```

2. Prepara dependencias del framework:

```bash
bash scripts/bootstrap_framework.sh
source .venv/bin/activate
```

En Linux/WSL, este comando instala también las dependencias del sistema que
Playwright necesita para arrancar los navegadores. Si el entorno no permite
instalar paquetes del sistema, usa `--without-system-deps`.

3. Configura el entorno:

```bash
cp deployers/infrastructure/deployer.config.example deployers/infrastructure/deployer.config
```

Edita `deployers/infrastructure/deployer.config` y ajusta al menos:

```text
KC_PASSWORD=change-me
PG_PASSWORD=change-me
MINIO_PASSWORD=change-me
VT_TOKEN=<vault-token>
PUBLIC_HOSTNAME=org1.pionera.oeg.fi.upm.es   # hostname público para acceso externo
VM_COMMON_IP=192.168.122.64                   # IP de la VM host
```

4. Ejecuta los niveles en orden desde el menú guiado:

```bash
python3 main.py menu
```

Ejecuta **1 → 2 → 3 → 4 → 5 → 6** en orden. El menú guiado es la entrada
recomendada para usuarios que quieran ejecutar los niveles sin memorizar comandos.

5. Después de Level 4 — proxy nginx (acceso externo):

Si Level 4 imprime `sudo requires a password — run manually:`, ejecuta el
comando que aparece en pantalla una sola vez (requiere contraseña sudo de la VM).
Si `sudo` es passwordless, el proxy se configura automáticamente.

6. Accede a los conectores desde cualquier PC en red UPM o VPN:

| URL | Usuario | Contraseña |
|-----|---------|------------|
| `https://org1.pionera.oeg.fi.upm.es/c/citycouncil/inesdata-connector-interface/` | `user-conn-citycouncil-demo` | ver `credentials-connector-conn-citycouncil-demo.json` |
| `https://org1.pionera.oeg.fi.upm.es/c/company/inesdata-connector-interface/` | `user-conn-company-demo` | ver `credentials-connector-conn-company-demo.json` |
| `https://org1.pionera.oeg.fi.upm.es/auth/admin/demo/console/` | `admin` | `change-me` |
| `https://org1.pionera.oeg.fi.upm.es/s3-console/` | `admin` | `change-me` |

Las contraseñas de los usuarios de conector se encuentran en:

```text
deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-citycouncil-demo.json  → connector_user.passwd
deployers/inesdata/deployments/DEV/demo/credentials-connector-conn-company-demo.json       → connector_user.passwd
```

## Configuración

La configuración común de infraestructura vive en:

```text
deployers/infrastructure/deployer.config
```

La configuración específica de cada adapter vive en:

```text
deployers/inesdata/deployer.config
deployers/edc/deployer.config
```

Usa los ficheros `.example` como plantilla cuando existan:

```text
deployers/infrastructure/deployer.config.example
deployers/inesdata/deployer.config.example
```

Las variables `PUBLIC_HOSTNAME` y `VM_COMMON_IP` en `deployers/infrastructure/deployer.config`
habilitan el acceso externo vía HTTPS desde un navegador:

```text
PUBLIC_HOSTNAME=org1.pionera.oeg.fi.upm.es   # hostname público del entorno
VM_COMMON_IP=192.168.122.64                   # IP de la VM host (red interna)
```

Cuando `PUBLIC_HOSTNAME` está configurado:

- `bootstrap.py` (Level 2) establece automáticamente el `frontendUrl` de Keycloak,
  garantizando que los tokens JWT contengan el issuer correcto para HTTPS externo.
- Al finalizar Level 4, el framework intenta ejecutar `setup-nginx-proxy.sh`
  automáticamente si `sudo` no requiere contraseña. Si requiere contraseña,
  imprime el comando manual a ejecutar una vez:

```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  <minikube_ip> <vm_ip> <public_hostname> <internal_domain>
```

También puedes sobreescribir valores con variables `PIONERA_*`, por ejemplo:

```bash
PIONERA_DS_1_NAME=demo \
PIONERA_DS_1_NAMESPACE=demo \
PIONERA_DS_1_CONNECTORS=citycouncil,company \
python3 main.py inesdata hosts --topology local --dry-run
```

## Hosts Locales

El framework puede planificar o aplicar entradas en el fichero `hosts` del
sistema. Por defecto, la operación solo planifica.

Planificación:

```bash
python3 main.py inesdata hosts --topology local --dry-run
python3 main.py edc hosts --topology local --dry-run
```

Aplicación explícita:

```bash
PIONERA_SYNC_HOSTS=true \
PIONERA_HOSTS_FILE=/etc/hosts \
python3 main.py edc hosts --topology local
```

En WSL, el fichero `hosts` de Windows suele estar en:

```text
/mnt/c/Windows/System32/drivers/etc/hosts
```

La sincronización es idempotente: si una entrada ya existe, el framework la
omite en lugar de duplicarla.

## Menú y Niveles

El menú se abre con:

```bash
python3 main.py menu
```

Niveles disponibles:

| Nivel | Acción |
| --- | --- |
| `1` | Setup Cluster |
| `2` | Deploy Common Services |
| `3` | Deploy Dataspace |
| `4` | Deploy Connectors |
| `5` | Deploy Components |
| `6` | Run Validation Tests |

La opción `0` ejecuta los niveles `1` a `6` de forma secuencial.

Opciones operativas del menú:

| Opción | Uso |
| --- | --- |
| `S` | Seleccionar adapter activo. |
| `P` | Previsualizar el plan de despliegue. |
| `H` | Planificar o aplicar entradas de hosts. |
| `M` | Ejecutar métricas, con Kafka opcional. |
| `T` | Abrir herramientas locales. |
| `U` | Ejecutar validaciones UI. |
| `?` | Mostrar ayuda. |
| `Q` | Salir. |

La referencia completa está en [docs/menu-reference.md](./docs/menu-reference.md).

## Prerrequisitos

Para ejecución local, el framework espera:

| Bloque | Herramientas principales |
| --- | --- |
| Base local | Python 3.10+, Git, Docker |
| Kubernetes local | **k3s** (topología VM) o Minikube (topología local), Helm, `kubectl` |
| Validación | Node.js, `npm`, Newman, Playwright |
| Operación | cliente PostgreSQL `psql`, permisos para `hosts` cuando aplique |

Verificación rápida:

```bash
python3 --version
git --version
docker --version
# k3s (entorno VM):
k3s --version
# Minikube (entorno local):
minikube version
helm version
kubectl version --client=true
psql --version
node --version
npm --version
npx newman -v
```

El bootstrap del framework prepara `.venv`, dependencias Python, dependencias
Node.js, navegadores Playwright y, en Linux/WSL, las dependencias del sistema
necesarias para ejecutar esos navegadores:

```bash
bash scripts/bootstrap_framework.sh
```

Si un entorno no permite instalar paquetes del sistema desde el bootstrap, se
puede usar `bash scripts/bootstrap_framework.sh --without-system-deps`.

## Minikube Tunnel

En despliegues **locales** (topología `local`) puede ser necesario mantener
`minikube tunnel` abierto en otra terminal:

```bash
minikube tunnel
```

Cuando `minikube tunnel` solicite contraseña, puede que la consola no muestre un
indicador visible. Introduce la contraseña y pulsa `Enter`.

En despliegues **VM con k3s** (topología `vm-single`) no se necesita `minikube tunnel`.
El servicio `ingress-nginx-controller` se configura como `NodePort` y el proxy nginx
de la VM escucha directamente en los puertos 80 y 443.

Los accesos funcionales locales deben ejercitar los hostnames publicados por
Ingress. El framework puede usar `port-forward` como apoyo interno para
diagnósticos o clientes host-side, pero no debe sustituir los endpoints de
navegador o API. El fallback de `port-forward` para conectores está desactivado
por defecto y solo debe habilitarse temporalmente con
`PIONERA_ALLOW_CONNECTOR_PORT_FORWARD_FALLBACK=true`.

## Acceso Externo (entorno VM/PIONERA con k3s)

En entornos desplegados en VM (topología `vm-single`), los servicios corren dentro
de k3s. El acceso externo se realiza a través de un nginx reverse proxy en la VM
que escucha en los puertos 80 y 443 y reenvía al ingress-nginx de k3s vía NodePort.

### Arquitectura de red

```
[Browser] → HTTPS 443 → [Hypervisor 138.100.15.165]
                              │ proxy
                              ▼
                    [VM nginx 192.168.122.64:443]
                              │ proxy_pass NodePort 31667
                              ▼
                    [k3s ingress-nginx :31667]
                              │
                              ▼
                    [Pods: Keycloak, MinIO, Conectores]
```

### Configuración automática (recomendada)

Configura en `deployers/infrastructure/deployer.config`:

```text
PUBLIC_HOSTNAME=org1.pionera.oeg.fi.upm.es
VM_COMMON_IP=192.168.122.64
```

Al ejecutar Level 4, el framework detecta `PUBLIC_HOSTNAME` y ejecuta
`setup-nginx-proxy.sh` automáticamente si `sudo` es passwordless.
Si `sudo` requiere contraseña, imprime el comando a ejecutar manualmente:

```bash
bash deployers/inesdata/scripts/setup-nginx-proxy.sh \
  192.168.49.2 192.168.122.64 org1.pionera.oeg.fi.upm.es pionera.oeg.fi.upm.es
```

### Qué hace el script

1. Instala nginx e iptables-persistent en la VM.
2. Detecta k3s y configura `INGRESS_BACKEND` como `VM_IP:31667` (NodePort).
3. Configura reglas iptables DNAT para puertos 80 y 443 hacia el nginx de la VM.
4. Genera certificado TLS autofirmado para el hostname público.
5. Parchea `app.config.json` en los pods con URLs HTTPS correctas.
6. Escribe configuración nginx con rutas por prefijo, routing por cookie,
   y `proxy_cookie_path` para que los cookies de sesión Keycloak funcionen
   correctamente al acceder vía el prefijo `/auth/`.
7. Establece el `frontendUrl` de Keycloak vía Admin API.

El script es idempotente: se puede re-ejecutar sin problemas.

### Consideración k3s: tipo de servicio NodePort

En k3s, el ingress-nginx-controller se configura automáticamente como tipo
`LoadBalancer` con la IP de la VM. Esto hace que kube-proxy intercepte el tráfico
a los puertos 80/443 antes de que llegue al nginx de la VM. El framework corrige
esto en Level 1 cambiando el servicio a `NodePort`.

La arquitectura y URLs de acceso están documentadas en
[docs/acceso_externo_conectores_pionera.md](./docs/acceso_externo_conectores_pionera.md)
y el tutorial completo en
[docs/tutorial-k3s-vm-setup.md](./docs/tutorial-k3s-vm-setup.md).

## CLI Principal

Listar adapters:

```bash
python3 main.py list
```

Desplegar:

```bash
python3 main.py inesdata deploy --topology local
python3 main.py edc deploy --topology local
```

Validar:

```bash
python3 main.py inesdata validate --topology local
python3 main.py edc validate --topology local
```

Ejecutar despliegue y validación:

```bash
python3 main.py inesdata run --topology local
python3 main.py edc run --topology local
```

Previsualizar sin modificar el entorno:

```bash
python3 main.py inesdata deploy --topology local --dry-run
python3 main.py edc run --topology local --dry-run
```

Recrear un dataspace de forma controlada:

```bash
python3 main.py edc recreate-dataspace --topology local --confirm-dataspace demoedc
python3 main.py edc recreate-dataspace --topology local --confirm-dataspace demoedc --with-connectors
```

## Validación

`Level 6` ejecuta la validación integral del adapter activo. Puede incluir:

- Newman;
- validación funcional EDC+Kafka después de Newman cuando el adapter la soporta;
- Playwright;
- comprobaciones de storage/MinIO;
- validaciones de componentes;
- métricas;
- reportes en `experiments/`.

Colecciones Newman principales:

| Colección | Uso |
| --- | --- |
| `01_environment_health.json` | Salud básica, reachability y autenticación. |
| `02_connector_management_api.json` | CRUD aislado del Management API. |
| `03_provider_setup.json` | Preparación del escenario E2E del provider. |
| `04_consumer_catalog.json` | Descubrimiento de catálogo. |
| `05_consumer_negotiation.json` | Negociación contractual. |
| `06_consumer_transfer.json` | Transferencia y recuperación de datos. |

Playwright se resuelve por adapter:

```text
validation/ui/playwright.config.ts
validation/ui/playwright.edc.config.ts
```

La documentación de validación está en [docs/validation.md](./docs/validation.md).

## Métricas y Kafka

Ejecutar métricas:

```bash
python3 main.py inesdata metrics --topology local
python3 main.py edc metrics --topology local
```

Ejecutar métricas con Kafka:

```bash
python3 main.py inesdata metrics --topology local --kafka
```

Helper reproducible de Kafka:

```bash
bash scripts/run_kafka_benchmark.sh --messages 10
bash scripts/run_kafka_benchmark.sh --messages 10 --max-retries 3 --retry-backoff 15
bash scripts/run_kafka_benchmark.sh --prepare-only
bash scripts/run_kafka_benchmark.sh --teardown-only
```

El benchmark puede generar `kafka_metrics.json`. Además, `Level 6` ejecuta la
validación funcional EDC+Kafka después de Newman para adapters compatibles y
puede generar `kafka_transfer_results.json`.

En local, esa validación usa por defecto un broker Kafka temporal dentro de
Kubernetes. Los conectores acceden al broker por DNS de cluster y el proceso
Python del framework puede usar un `port-forward` temporal solo para crear
topics y verificar mensajes desde el host.

## Imágenes Locales

Durante desarrollo, usa la opción `T -> 5 - Build and Deploy Local Images` del
menú para construir y cargar imágenes locales del adapter activo.

En topología `local`, `Level 4` de INESData prepara automáticamente
`inesdata-connector` e `inesdata-connector-interface` desde las fuentes locales
antes de crear los conectores. Esto evita validar con imágenes remotas antiguas
cuando `Level 6` ejecuta flujos como Kafka o Playwright.

Si la receta corresponde a un componente de `Level 5` ya desplegado, como
`Ontology Hub` o `AI Model Hub`, el framework reinicia su deployment para que
Kubernetes use la imagen recién cargada. Si el componente aún no existe, carga
la imagen y deja el despliegue para `Level 5`.

Scripts relevantes:

```text
adapters/inesdata/scripts/sync_sources.sh
adapters/inesdata/scripts/build_images.sh
adapters/inesdata/scripts/local_build_load_deploy.sh
adapters/edc/scripts/sync_sources.sh
adapters/edc/scripts/build_image.sh
adapters/edc/scripts/sync_dashboard_sources.sh
adapters/edc/scripts/build_dashboard_image.sh
adapters/edc/scripts/build_dashboard_proxy_image.sh
```

Para EDC, las fuentes locales se gestionan bajo:

```text
adapters/edc/sources/
```

El runtime del conector EDC se sincroniza desde:

```text
https://github.com/luciamartinnunez/Connector
```

El dashboard EDC se sincroniza desde:

```text
https://github.com/ProyectoPIONERA/EDC-asset-filter-dashboard
```

## Limpieza y Doctor

El menú incluye herramientas locales:

| Herramienta | Uso |
| --- | --- |
| `Bootstrap Framework Dependencies` | Prepara o repara dependencias. |
| `Run Framework Doctor` | Ejecuta checks del entorno local. |
| `Recover Connectors After WSL Restart` | Recupera acceso local tras reiniciar WSL. |
| `Cleanup Workspace` | Limpia caches y artefactos temporales. |
| `Build and Deploy Local Images` | Construye imágenes locales y reinicia componentes desplegados cuando aplica. |

El script de limpieza también puede ejecutarse manualmente:

```bash
bash scripts/clean_workspace.sh
bash scripts/clean_workspace.sh --apply
bash scripts/clean_workspace.sh --apply --include-results
```

## Experimentos y Reportes

Un experimento es una ejecución reproducible del flujo de validación y medición.
Puede incluir despliegue, validación API, validación UI, métricas, Kafka y
artefactos de componentes.

Estructura habitual:

```text
experiments/
  experiment_<timestamp>/
    metadata.json
    experiment_results.json
    aggregated_metrics.json
    kafka_metrics.json
    kafka_transfer_results.json
    summary.json
    summary.md
    graphs/
```

Los reportes Playwright quedan dentro del experimento correspondiente cuando se
ejecutan desde `Level 6`.

## Arquitectura y Estructura

| Ruta | Descripción |
| --- | --- |
| `main.py` | CLI principal y menú guiado. |
| `framework/` | Núcleo reutilizable de validación, métricas y reportes. |
| `adapters/` | Integraciones específicas por adapter. |
| `deployers/` | Deployers, configuración y artefactos de despliegue. |
| `deployers/infrastructure/` | Contratos, topologías, hosts y utilidades transversales. |
| `deployers/shared/` | Charts y artefactos reutilizables. |
| `validation/` | Suites Newman, Playwright y validaciones de componentes. |
| `tests/` | Pruebas unitarias del framework. |
| `docs/` | Documentación pública estable. |

## Tests

Pruebas focalizadas de topologías, contratos, hosts y CLI:

```bash
python3 -m unittest \
  tests.test_deployer_shared_contracts \
  tests.test_deployer_shared_topology \
  tests.test_deployer_shared_hosts_manager \
  tests.test_main_cli
```

Descubrimiento general:

```bash
python3 -m unittest discover tests
```

El descubrimiento general puede incluir suites amplias de Vault, Kafka,
Ontology, métricas o componentes que dependan del entorno local disponible.

## Documentación

La documentación pública está en [docs/](./docs/README.md).

Orden recomendado:

- [Inicio rápido](./docs/getting-started.md)
- [Referencia del menú](./docs/menu-reference.md)
- [Arquitectura](./docs/architecture.md)
- [Deployers y topologías](./docs/deployers-and-topologies.md)
- [Adapters](./docs/adapters.md)
- [Validación](./docs/validation.md)
- [Desarrollo y testing](./docs/development-and-testing.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Acceso externo a conectores (VM/PIONERA)](./docs/acceso_externo_conectores_pionera.md)

## Referencias Técnicas

- [INESData local environment](https://github.com/INESData/inesdata-local-env)
- [INESData connector management API collection](https://github.com/INESData/inesdata-local-env/blob/master/resources/operations/InesData_Connector_Management_API.postman_collection.json)
- [Eclipse EDC Management API](https://eclipse-edc.github.io/Connector/openapi/management-api/#/)
- [Eclipse EDC Kafka sample](https://github.com/eclipse-edc/Samples/tree/main/transfer/transfer-06-kafka-broker)
- [DataSpaceUnit local deployment](https://github.com/DataSpaceUnit/ds-local-deployment)

## Financiación

This work has received funding from the **PIONERA project** (Enhancing interoperability in data spaces through artificial intelligence), a project funded in the context of the call for Technological Products and Services for Data Spaces of the Ministry for Digital Transformation and Public Administration within the framework of the PRTR funded by the European Union (NextGenerationEU).

<div align="center">
  <img src="funding_label.png" alt="Logos financiación" width="900" />
</div>

---

## Licencia

Validation-Environment is available under the **[Apache License 2.0](https://github.com/ProyectoPIONERA/pionera_env/blob/main/LICENSE)**.
