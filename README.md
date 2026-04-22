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
git clone --branch refactor/new-framework --single-branch https://github.com/ProyectoPIONERA/Validation-Environment.git
cd Validation-Environment
```

2. Prepara dependencias del framework:

```bash
bash scripts/bootstrap_framework.sh
```

En Linux/WSL, este comando instala también las dependencias del sistema que
Playwright necesita para arrancar los navegadores. Si el entorno no permite
instalar paquetes del sistema, usa `--without-system-deps`.

3. Activa el entorno Python raíz:

```bash
source .venv/bin/activate
```

4. Revisa la configuración generada si necesitas ajustar credenciales, dominios
o dataspaces:

```text
deployers/infrastructure/deployer.config
deployers/inesdata/deployer.config
deployers/edc/deployer.config
```

5. Abre el menú guiado:

```bash
python3 main.py menu
```

El menú guiado es la entrada recomendada para usuarios que quieran ejecutar los
niveles de despliegue sin memorizar comandos.

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
| `X` | Recrear el dataspace seleccionado. |
| `B/D/R/C/L` | Accesos de desarrollo: bootstrap, doctor, recovery, cleanup e imágenes locales. |
| `I/O/A` | Validaciones UI de INESData, Ontology Hub y AI Model Hub. |
| `?` | Mostrar ayuda. |
| `Q` | Salir. |

La referencia completa está en [docs/menu-reference.md](./docs/menu-reference.md).

## Prerrequisitos

Para ejecución local, el framework espera:

| Bloque | Herramientas principales |
| --- | --- |
| Base local | Python 3.10+, Git, Docker |
| Kubernetes local | Minikube, Helm, `kubectl` |
| Validación | Node.js, `npm`, Newman, Playwright |
| Operación | cliente PostgreSQL `psql`, permisos para `hosts` cuando aplique |

Verificación rápida:

```bash
python3 --version
git --version
docker --version
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

En despliegues locales puede ser necesario mantener `minikube tunnel` abierto en
otra terminal:

```bash
minikube tunnel
```

Cuando `minikube tunnel` solicite contraseña, puede que la consola no muestre un
indicador visible. Introduce la contraseña y pulsa `Enter`.

Los accesos funcionales locales deben ejercitar los hostnames publicados por
Ingress. El framework puede usar `port-forward` como apoyo interno para
diagnósticos o clientes host-side, pero no debe sustituir los endpoints de
navegador o API. El fallback de `port-forward` para conectores está desactivado
por defecto y solo debe habilitarse temporalmente con
`PIONERA_ALLOW_CONNECTOR_PORT_FORWARD_FALLBACK=true`.

`Level 6` comprueba esos hostnames antes de ejecutar la limpieza y las suites de
validación. Si vas a validar conectores ya desplegados, ejecuta `Level 6` desde
el mismo checkout que ejecutó `Level 4`, porque las credenciales locales
generadas para Keycloak, MinIO y conectores viven bajo
`deployers/<adapter>/deployments/`.

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

Ejecutar métricas con benchmark standalone de broker Kafka:

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

El benchmark standalone puede generar `kafka_metrics.json` y mide el broker
Kafka, no el flujo E2E del dataspace. Además, `Level 6` ejecuta la validación
funcional EDC+Kafka después de Newman para adapters compatibles y puede generar
`kafka_transfer_results.json`.

En local, esa validación usa por defecto un broker Kafka temporal dentro de
Kubernetes. Los conectores acceden al broker por DNS de cluster y el proceso
Python del framework puede usar un `port-forward` temporal solo para crear
topics y verificar mensajes desde el host.

## Imágenes Locales

Durante desarrollo, usa la opción `L - Build and Deploy Local Images` del menú
para construir, cargar y redesplegar imágenes locales del adapter activo.

En topología `local`, `Level 4` de INESData prepara automáticamente
`inesdata-connector` e `inesdata-connector-interface` desde las fuentes locales
antes de crear los conectores. Esto evita validar con imágenes remotas antiguas
cuando `Level 6` ejecuta flujos como Kafka o Playwright.

La opción `L` está pensada para iteración de desarrollo y preserva datos en
redeploys INESData: reutiliza los valores existentes de Helm y no recrea
credenciales, dataspace ni servicios comunes. Si un release todavía no existe,
ejecuta primero el nivel correspondiente.

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

El menú incluye accesos directos de desarrollo:

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
