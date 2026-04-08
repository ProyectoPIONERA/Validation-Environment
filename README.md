# Validation-Environment

Validation-Environment es un framework para crear entornos reproducibles de validación de espacios de datos. Se utiliza como infraestructura de validación para evaluar componentes del ecosistema PIONERA mediante pruebas funcionales, de interoperabilidad y de rendimiento.

Permite desplegar automáticamente una infraestructura basada en INESData, ejecutar escenarios de intercambio de datos entre conectores y recopilar métricas experimentales sobre el comportamiento del sistema.

Actualmente el adapter disponible es `inesdata`.

El framework ofrece la opción de guardar en `hosts` los dominios necesarios de forma dinámica. En wsl este fichero se encuentra en `C:\Windows\System32\drivers\etc` y en Linux en `/etc/hosts`. Para el demo local, se utilizan los siguientes dominios:

## Demo

Para arrancar el demo, se recomienda agregar el siguiente bloque de dominios en el fichero `hosts`. En wsl se encuentra en `C:\Windows\System32\drivers\etc` y en Linux en `/etc/hosts`:

```text
127.0.0.1 keycloak.dev.ed.dataspaceunit.upm
127.0.0.1 keycloak-admin.dev.ed.dataspaceunit.upm
127.0.0.1 minio.dev.ed.dataspaceunit.upm
127.0.0.1 console.minio-s3.dev.ed.dataspaceunit.upm

127.0.0.1 registration-service-demo.dev.ds.dataspaceunit.upm
127.0.0.1 conn-citycouncil-demo.dev.ds.dataspaceunit.upm
127.0.0.1 conn-company-demo.dev.ds.dataspaceunit.upm
```

## Funcionalidades principales

- desplegar un entorno de dataspace mediante un adapter
- validar funcionalmente el entorno con colecciones Newman/Postman
- recoger métricas de control plane
- ejecutar benchmarks Kafka opcionales
- generar artefactos experimentales reproducibles en `experiments/`
- producir resúmenes y gráficas automáticamente

## Cuándo usar `inesdata.py` y cuándo usar `main.py`

Hay dos puntos de entrada principales:

- `inesdata.py`: flujo recomendado para onboarding, bootstrap desde cero, troubleshooting y despliegue guiado por niveles de INESData.
- `main.py`: CLI moderna del framework para validación, métricas y experimentos cuando el entorno ya está operativo, o para la ejecución modular del adapter.

En la práctica:

- Usa `python inesdata.py` para levantar o reconstruir el entorno.
- Usa `python main.py ...` para validar, medir y ejecutar experimentos desde el framework.

## Inicio rápido

Para el despliegue inicial de INESData desde cero, el flujo recomendado es `inesdata.py` ejecutado por niveles.

1. Clona el repositorio:

```bash
git clone --branch refactor/new-framework --single-branch https://github.com/ProyectoPIONERA/Validation-Environment.git
cd Validation-Environment
```

2. Prepara el framework localmente con el bootstrap reproducible:

```bash
bash scripts/bootstrap_framework.sh
```

3. Revisa o ajusta la configuración local:

```bash
cp deployer.config.example deployer.config
```

El bootstrap ya crea `deployer.config` automáticamente si no existe, así que el `cp` anterior solo es necesario si quieres recrearlo manualmente.

4. Abre el menú interactivo y usa el doctor local para revisar si la máquina está lista:

```bash
python3 inesdata.py
```

Dentro del menú:

- `B` ejecuta el bootstrap local del framework
- `D` ejecuta el doctor/preflight del entorno local

5. Usa preferentemente la opción `0` o ejecuta los niveles manualmente.

### Definición de niveles de despliegue de `inesdata.py`

- **Nivel 1 – Setup Cluster**: prepara el clúster base con Minikube, Helm e ingress.
- **Nivel 2 – Deploy Common Services**: sincroniza configuración, prepara `hosts`, despliega servicios comunes y configura Vault.
- **Nivel 3 – Deploy Dataspace**: despliega el dataspace y sus componentes principales sobre el clúster ya preparado, y valida que `registration-service` deja listo su esquema antes de pasar a conectores.
- **Nivel 4 – Deploy Connectors**: crea y despliega los conectores definidos en la configuración del entorno, comprueba su disponibilidad y muestra el resumen operativo de credenciales y endpoints.
- **Nivel 5 – Deploy Components (opcional)**: despliega servicios adicionales vía Helm charts en `inesdata-deployment/components/*`. La selección por defecto puede definirse en `deployer.config` con `COMPONENTS`.
- **Nivel 6 – Run Validation Tests**: ejecuta las validaciones funcionales sobre los conectores desplegados, con un flujo Newman que distingue entre CRUD aislado y escenario end-to-end del dataspace.

### Notas operativas importantes

- Antes del nivel 3 es necesario abrir un nuevo terminal y ejecutar:

```bash
minikube tunnel
```

- Cuando `minikube tunnel` empiece a mostrar logs, puede solicitar la contraseña del sistema aunque la consola no siempre muestre un indicador visible. Si parece que no se escribe nada, introduce la contraseña igualmente y pulsa **Enter**.
- El flujo por niveles sigue siendo el más seguro para bootstrap y troubleshooting porque guía al usuario cuando hace falta intervención manual.
- El archivo real `deployer.config` debe mantenerse en formato `KEY=VALUE` puro, sin comentarios ni líneas informativas.
- El nivel 3 reinicia `registration-service` tras recrear la base de datos del dataspace para asegurar que vuelva a cargar sus credenciales y aplique Liquibase antes de dar el nivel por completado.

## Prerrequisitos

Conviene distinguir tres grupos de prerrequisitos:

| Bloque | Cuándo aplica | Herramientas / requisitos principales | ¿Lo instala el framework? |
| --- | --- | --- | --- |
| Bootstrap base de INESData | Levantar el entorno con `python inesdata.py` | Python 3.10, Git, Docker, Minikube, Helm, `kubectl`, permisos para `hosts`, `minikube tunnel` | No |
| Validación automatizada y experimentación | Ejecutar validación funcional, UI y parte del workflow experimental | Node.js, `npm`, `newman`, Playwright | Parcialmente |
| Implementación actual del adapter | Ejecutar el adapter `inesdata` tal y como está implementado hoy | `psql` local | No |

### Verificación rápida de herramientas

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

### Instalación recomendada en Ubuntu/WSL

#### Python 3.10

```bash
sudo apt update
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev -y
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
python3.10 -m pip --version
```

#### Git

```bash
sudo apt update
sudo apt install git -y
```

#### Docker

Verificar:

```bash
docker --version
docker info
```

- En WSL, la opción recomendada es instalar Docker Desktop en Windows y habilitar la integración con WSL.
- En Ubuntu nativo, puedes instalar Docker Engine con:

```bash
sudo apt update
sudo apt install docker.io -y
sudo usermod -aG docker $USER
```

#### Minikube

```bash
curl -LO https://github.com/kubernetes/minikube/releases/latest/download/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
rm -f minikube-linux-amd64
minikube version
```

#### Helm

```bash
sudo snap install helm --classic
helm version
```

#### kubectl

```bash
sudo snap install kubectl --classic
kubectl version --client=true
```

#### PostgreSQL client (`psql`)

```bash
sudo apt update
sudo apt install postgresql-client -y
psql --version
```

#### Node.js y npm

```bash
sudo apt update
sudo apt install nodejs npm -y
node --version
npm --version
```

#### Newman

```bash
npm install
npx newman -v
```

El framework prioriza `node_modules/.bin/newman` y, si no existe, intenta `npm install` automáticamente cuando una validación necesita Newman y el repositorio incluye `package.json`.

Alternativa global:

```bash
npm install -g newman
newman -v
```

### Entorno virtual del framework en la raíz

El entorno Python operativo del despliegue de INESData es `inesdata-deployment/.venv`. Para una ejecución reproducible del framework desde la raíz en una máquina nueva, el entorno virtual de la raíz debe considerarse el camino recomendado, porque evita instalar dependencias Python en el intérprete global.

```bash
cd ~/Validation-Environment
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Preparación reproducible en una máquina nueva

Si el objetivo es ejecutar el framework con una preparación mínima pero reproducible desde cero, el bloque recomendado hoy es:

```bash
bash scripts/bootstrap_framework.sh
```

Qué cubre este bloque:

- crea `.venv` en la raíz si no existe
- instala `requirements.txt` en ese entorno
- ejecuta `npm install` en la raíz para `newman`
- ejecuta `npm install` en `validation/ui`
- ejecuta `npx playwright install`
- crea `deployer.config` desde `deployer.config.example` si falta

Notas:

- si prefieres ver los pasos manuales, el bootstrap equivale aproximadamente a:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm install
cd validation/ui
npm install
npx playwright install
cd ../..
```

- Si solo vas a usar despliegue y validación API, el bloque de `validation/ui` puede omitirse, pero entonces las suites UI quedarán en `skipped`.
- En Linux o WSL, si Playwright necesita dependencias del sistema, puede ser necesario usar `npx playwright install --with-deps`.
- `inesdata.py` y `main.py` pueden intentar instalar dependencias Python que falten en el intérprete actual, pero para una máquina nueva no conviene depender de ese comportamiento sobre el Python del sistema.

### Doctor / preflight local

El menú interactivo de `inesdata.py` ahora incluye un doctor local que revisa:

- comandos del sistema (`docker`, `minikube`, `helm`, `kubectl`, `psql`, `node`, `npm`)
- entorno `.venv` de la raíz
- disponibilidad de `newman`
- disponibilidad de Playwright y sus navegadores
- existencia de `deployer.config`
- estado básico del fichero `hosts`
- presencia de `minikube tunnel`

Uso:

```bash
python3 inesdata.py
```

Y dentro del menú:

- `B` para bootstrap local del framework
- `D` para ejecutar el doctor/preflight

Antes de usar `main.py` o helpers del framework desde la raíz, conviene asegurar explícitamente que ese entorno tiene las dependencias instaladas:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

El helper `scripts/run_kafka_benchmark.sh` ejecuta esta instalación automáticamente sobre el intérprete que vaya a usar antes de lanzar el benchmark.

### Automatización de tareas

En el flujo de `inesdata.py` y del adapter `inesdata`, el framework automatiza tareas como:

- clonado de `inesdata-deployment/` cuando no existe
- copia de `deployer.config` al repositorio operativo
- creación de `inesdata-deployment/.venv`
- instalación de dependencias Python de `inesdata-deployment/requirements.txt`
- alta de repositorios Helm y `helm dependency build`
- arranque de Minikube y habilitación de ingress
- despliegue de servicios comunes, dataspace y conectores
- configuración de Vault y preparación de artefactos del entorno

No debe asumirse que el framework sea un instalador completo del sistema. Antes del primer uso, el usuario debe preparar por su cuenta:

- Python 3.10 del sistema
- Git
- Docker
- Minikube
- Helm
- `kubectl`
- `psql`
- Node.js / `npm`
- `newman`
- Playwright si se quiere ejecutar `Level 6` con cobertura UI completa

Tampoco automatiza la intervención manual requerida para mantener `minikube tunnel` abierto ni la edición inicial del fichero `hosts` cuando el entorno lo requiere.

> Algunas utilidades se ejecutan dentro de contenedores o pods mediante `docker exec` o `kubectl exec`. Por ello, herramientas como `vault`, `mc`, `kafka-topics` o determinados clientes internos del servicio no requieren instalación local independiente.

### Dependencias en `requirements.txt`

El framework separa sus dependencias por tipo de la siguiente manera:

- `requirements.txt` de la raíz: librerías Python usadas por `main.py`, `inesdata.py`, adapters, tests core y helpers Python del framework. Aquí sí deben vivir dependencias como `requests`, `PyYAML`, `tabulate`, `ruamel.yaml`, `matplotlib`, `docker`, `testcontainers` o `kafka-python`.
- `inesdata-deployment/requirements.txt`: dependencias Python del repositorio operativo INESData que se ejecuta mediante `inesdata-deployment/.venv`.
- herramientas Node.js: `newman` no pertenece a `requirements.txt` porque no es un paquete Python. Se gestiona con `npm` y `package.json`, no con `pip`.
- herramientas del sistema: `docker`, `minikube`, `helm`, `kubectl`, `psql` o `snap`/`apt` tampoco pertenecen a `requirements.txt`. Son prerrequisitos del sistema operativo o del entorno de contenedores.

Estado actual del framework:

- `main.py` e `inesdata.py` aseguran automáticamente las dependencias Python de la raíz antes de continuar si el intérprete actual permite instalar paquetes.
- el flujo legacy asegura también `inesdata-deployment/requirements.txt` antes de invocar `deployer.py` dentro de `inesdata-deployment/.venv`.
- `newman` se puede instalar localmente con `npm install` en la raíz del repo; el framework prioriza `node_modules/.bin/newman` y, si no existe, usa un `newman` global en `PATH`.
- cuando una validación necesita `newman` y no está disponible, el framework intenta `npm install` automáticamente si existe `package.json` en la raíz.
- las suites UI del dataspace y de componentes dependen de Playwright instalado en `validation/ui`.

## Uso del framework

### CLI principal

Listar adapters disponibles:

```bash
python main.py list
```

Desplegar con el adapter INESData:

```bash
python main.py inesdata deploy
```

Validar el dataspace:

```bash
python main.py inesdata validate
```

Recoger métricas:

```bash
python main.py inesdata metrics
```

Ejecutar el ciclo completo:

```bash
python main.py inesdata run
```

Ejecutar varias iteraciones:

```bash
python main.py inesdata run --iterations 5
```

Previsualizar wiring sin ejecutar cambios reales:

```bash
python main.py inesdata run --dry-run
```

## Benchmark Kafka

El repositorio incluye un helper reproducible que levanta un broker externo, comprueba su estabilidad y ejecuta el benchmark vía CLI.

> Este helper puede ejecutarse con un entorno virtual de la raíz si existe, pero también puede reutilizar `inesdata-deployment/.venv` cuando ese es el entorno activo o el único disponible.

Smoke test corto:

```bash
cd ~/Validation-Environment
npm install
source .venv/bin/activate
bash scripts/run_kafka_benchmark.sh --messages 10
```

Con política explícita de reintentos:

```bash
bash scripts/run_kafka_benchmark.sh --messages 10 --max-retries 3 --retry-backoff 15
```

Modo más estable para entornos sensibles a cold starts o a timeouts de metadata:

```bash
bash scripts/run_kafka_benchmark.sh \
  --messages 10 \
  --topic-strategy STATIC_TOPIC \
  --topic-name framework-kafka-benchmark \
  --keep-broker
```

### Resumen operativo del helper Kafka

Script: `scripts/run_kafka_benchmark.sh`

Qué hace:
- levanta un broker Kafka externo reproducible con `docker compose`
- espera salud del broker y ventana de estabilización
- reintenta fallos transitorios con reinicio limpio y backoff lineal
- asegura dependencias Python de la raíz y `newman` local si el repositorio tiene `package.json`
- ejecuta `python main.py inesdata metrics --kafka` o `run --kafka`
- valida `kafka_metrics.json` y muestra artefactos recientes

El `docker-compose.kafka.yml` está afinado para un broker KRaft de un solo nodo con márgenes de heartbeat y sesión menos agresivos que los valores por defecto, porque en entornos como WSL o Docker Desktop los timeouts cortos pueden provocar ciclos de `fencing/unfencing` durante la fase de estabilización.

Fuente de verdad de Kafka:
- `deployer.config` puede definir `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_CLUSTER_BOOTSTRAP_SERVERS`, `KAFKA_CLUSTER_ADVERTISED_HOST`, `KAFKA_TOPIC_NAME`, `KAFKA_TOPIC_STRATEGY`, `KAFKA_SECURITY_PROTOCOL`, `KAFKA_CONTAINER_NAME`, `KAFKA_CONTAINER_IMAGE` y `KAFKA_CONTAINER_ENV_FILE`.
- el adapter `inesdata` reutiliza esos valores tanto para `main.py --kafka` como para `Level 6`.
- si `KAFKA_CONTAINER_ENV_FILE` apunta a un fichero SASL, el framework lo usa al autoaprovisionar el broker.
- si el framework autoaprovisiona Kafka para la suite `EDC+Kafka`, arranca un broker con dos listeners anunciados: uno para el host y otro para los pods, para que la medicion y el dataplane puedan usar el mismo broker sin depender de `localhost` dentro del cluster.

Activacion del runtime Kafka del conector:
- el codigo fuente del conector ya empaqueta `data-plane-kafka` en el launcher local.
- eso deja preparada la imagen local del conector para flujos EDC+Kafka cuando se construye con el workflow de imagenes locales.
- el `kafka_metrics.json` persistido sigue siendo el benchmark del broker.
- `Level 6` puede ejecutar ademas una suite opcional `EDC+Kafka` con `LEVEL6_RUN_KAFKA_EDC=true`, que genera `kafka_edc_results.json` y artefactos por pareja en `kafka_edc/`.
- esa suite reproduce el flujo funcional `asset Kafka -> catalogo -> negociacion -> transfer Kafka-PUSH -> consumo del topic destino`, mas cerca del sample oficial `Transfer06KafkaBrokerTest`.

Parámetros útiles:
- `--messages <n>`
- `--max-retries <n>` (por defecto `3`)
- `--retry-backoff <s>` (por defecto `15`)
- `--topic-strategy <EXPERIMENT_TOPIC|STATIC_TOPIC>`
- `--topic-name <name>` (obligatorio con `STATIC_TOPIC`)
- `--no-reuse-broker-on-retry`
- `--keep-broker`
- `--prepare-only`
- `--teardown-only`

Ejemplos:

```bash
bash scripts/run_kafka_benchmark.sh --messages 10
bash scripts/run_kafka_benchmark.sh --messages 10 --max-retries 3 --retry-backoff 15
bash scripts/run_kafka_benchmark.sh --messages 10 --topic-strategy STATIC_TOPIC --topic-name framework-kafka-benchmark --keep-broker
bash scripts/run_kafka_benchmark.sh --prepare-only
bash scripts/run_kafka_benchmark.sh --teardown-only
```

## Orquestación de imágenes INESData

Scripts disponibles en `adapters/inesdata/scripts/`:

- `build_images.sh`: construye imágenes, ejecuta pre-build por componente cuando está configurado (por ejemplo `connector`) y genera un manifest `images-*.tsv` en `/tmp/inesdata-manifests` (por defecto).
- `local_build_load_deploy.sh`: flujo local sin GHCR (build + `minikube image load` + `helm upgrade` con overrides).

Tras tener el entorno ya levantado (niveles 1-4, y `minikube tunnel` activo si aplica), para probar cambios hechos en `adapters/inesdata/sources`:

Flujo completo (todos los componentes):

```bash
bash adapters/inesdata/scripts/local_build_load_deploy.sh --apply --platform-dir inesdata-deployment
```

Flujo parcial para iterar rápido en un componente (build + load, sin deploy Helm):

```bash
bash adapters/inesdata/scripts/local_build_load_deploy.sh --apply --component connector-interface --skip-deploy --platform-dir inesdata-deployment
```

Por defecto, `local_build_load_deploy.sh` despliega en todos los namespaces `DS_*_NAMESPACE` definidos en `deployer.config`.
Si quieres forzar un único namespace, usa `--namespace <name>`.

En el menú legacy (`python inesdata.py`), la opción `L` ejecuta este flujo en modo Full (sin selección por componente), con confirmación directa.

En la automatización de niveles, este paso ya se aplica por defecto: `Level 4` ejecuta automáticamente el workflow local justo después de desplegar conectores (antes de su validación final), usando `connector-interface` y `skip-prebuild=0`.

No necesitas añadir variables en `deployer.config`. Solo úsalo como override opcional si quieres cambiar o desactivar el comportamiento por defecto:

```bash
LOCAL_IMAGE_OVERRIDE_AFTER_LEVEL4=0
LOCAL_IMAGE_OVERRIDE_COMPONENT=public-portal-frontend
LOCAL_IMAGE_OVERRIDE_SKIP_PREBUILD=1
```

`LOCAL_IMAGE_OVERRIDE_COMPONENT` es opcional: si se omite, se usa `connector-interface`. Valores permitidos: `connector`, `connector-interface`, `registration-service`, `public-portal-backend`, `public-portal-frontend`.

Caso especial `ontology-hub`:

- cuando `COMPONENTS=ontology-hub`, `Level 5` asegura un checkout local en `adapters/inesdata/sources/Ontology-Hub`
- si ese checkout no existe o está vacío, el framework lo clona automáticamente desde GitHub
- antes de desplegar el chart, el framework reconstruye siempre en el host la imagen local referenciada por el chart y después la carga en minikube
- `Level 6` valida después exactamente ese despliegue, por lo que la iteración de integración queda acoplada al repo clonado y no a una imagen remota previa
- este flujo no usa overrides de `source dir` ni de imagen para `ontology-hub`; el checkout canónico y la imagen local del chart son parte del contrato del framework
- para troubleshooting de Playwright UI en WSL, ver `docs/10_ui_validation_core.md`, especialmente la sección `Troubleshooting WSL`

Si solo quieres construir imágenes desde el script de build:

```bash
bash adapters/inesdata/scripts/build_images.sh --apply --component connector-interface
```

Para omitir pre-build en componentes que lo tengan configurado:

```bash
bash adapters/inesdata/scripts/build_images.sh --apply --component connector --skip-prebuild
```

## Limpieza del workspace

Script: `scripts/clean_workspace.sh`

También está disponible desde el menú legacy (`python inesdata.py`):
- `C - Cleanup Workspace`
- `1 - Apply cleanup` (equivale a `bash scripts/clean_workspace.sh --apply`)
- `2 - Apply cleanup + include results` (equivale a `bash scripts/clean_workspace.sh --apply --include-results`)

Si el workspace acumula demasiados artefactos locales generados por el framework, este script es la forma recomendada de recuperar espacio y dejar el workspace limpio sin tocar el código fuente.

Objetivo:
- eliminar artefactos temporales locales para mantener el repositorio limpio
- evitar que cachés de ejecución se mezclen con cambios reales del framework

Qué limpia por defecto:
- directorios `__pycache__`
- archivos `*.pyc`
- cachés `.pytest_cache`, `.mypy_cache`, `.ruff_cache`

Qué no limpia por defecto:
- directorios `experiments/`
- directorio `newman/`
- entornos virtuales como `.venv` o `inesdata-deployment/.venv`
- `node_modules/`

Para borrar también los resultados generados por experimentos y ejecuciones Newman, hay que añadir `--include-results`.

Modo de uso:

```bash
# simulación (no borra)
bash scripts/clean_workspace.sh

# aplicar limpieza segura
bash scripts/clean_workspace.sh --apply

# incluir además resultados locales (experiments/newman)
bash scripts/clean_workspace.sh --apply --include-results
```

Recomendación práctica:
- si solo quieres limpiar cachés y basura temporal, usa `--apply`
- si además quieres vaciar resultados experimentales acumulados porque el workspace ya está demasiado cargado, usa `--apply --include-results`

Qué se espera de este script:
- uso manual antes de commits, empaquetado o entregas
- no sustituye backups ni control de versiones
- no modifica código fuente ni configuraciones funcionales

## Experimentos, métricas y artefactos

### Experimentos

En este framework, un experimento es una ejecución reproducible del flujo de validación y medición del entorno de dataspace.

Un experimento puede incluir:

- despliegue del dataspace mediante un adapter
- validación funcional usando colecciones Newman/Postman
- recogida de métricas de control plane
- benchmark Kafka opcional
- generación automática de artefactos del experimento

En el flujo actual de validación funcional del adapter `inesdata`, las colecciones Newman se ejecutan en este orden:

- `01_environment_health.json`: salud básica, reachability y autenticación
- `02_connector_management_api.json`: CRUD aislado del Management API con IDs únicos por ejecución
- `03_provider_setup.json`: preparación del escenario E2E del provider con recursos `e2e_*`
- `04_consumer_catalog.json`: descubrimiento de catálogo sobre el escenario E2E
- `05_consumer_negotiation.json`: negociación contractual usando el contexto E2E
- `06_consumer_transfer.json`: transferencia y recuperación de datos usando el contexto E2E

Las variables de entorno de Newman se preservan entre colecciones durante una misma validación para mantener el contexto compartido del escenario E2E.

### Métricas recogidas

#### Control plane metrics

- request latency
- latency percentiles (`p50`, `p95`, `p99`)
- error rate
- per-endpoint request metrics

#### Data plane metrics (Kafka benchmark)

- end-to-end message latency
- latency percentiles
- throughput (`messages per second`)

### Artefactos generados por experimento

Cada experimento se guarda en `experiments/experiment_<timestamp>/` y puede incluir:

- `metadata.json`
- `experiment_results.json`
- `raw_requests.jsonl`
- `aggregated_metrics.json`
- `kafka_metrics.json` (opcional)
- `kafka_edc_results.json` (opcional)
- `summary.json`
- `summary.md`
- `graphs/`

Ejemplo de estructura:

```text
experiments/
  experiment_<timestamp>/
    metadata.json
    aggregated_metrics.json
    kafka_metrics.json
    kafka_edc_results.json
    summary.json
    summary.md
    graphs/
```

## Arquitectura y estructura

Validation-Environment desacopla el núcleo experimental de la infraestructura específica de cada plataforma mediante adapters.

| Componente | Descripción                                                                                      |
| --- |--------------------------------------------------------------------------------------------------|
| `main.py` | CLI principal del framework                                                                      |
| `framework/` | Núcleo de ejecución experimental                                                                 |
| `adapters/` | Integraciones específicas con plataformas                                                        |
| `adapters/inesdata/` | Integración específica con INESData                                                              |
| `validation/` | Colecciones Newman/Postman y scripts de test                                                     |
| `experiments/` | Artefactos generados por los experimentos                                                        |
| `inesdata-deployment/` | Repositorio operativo utilizado por el adapter `inesdata` (clonado automáticamente si no existe) |

## Relación con `inesdata-deployment`

El adapter `inesdata` utiliza `inesdata-deployment/` para despliegue y configuración de la plataforma. Sus dependencias y scripts propios siguen viviendo ahí, pero su presencia viene de la propia automatización del entorno además de existir ya en un el repositorio oficial de PIONERA con fines de desarrollo y pruebas.

> En la automatización de INESData, `inesdata-deployment/deployer.config` actúa como fuente de configuración para instanciar el entorno. Incluye parámetros del dataspace y definiciones de conectores como `DS_1_CONNECTORS`.
>
> La plantilla recomendada para usuarios del repositorio es `deployer.config.example` en la raíz. Debe copiarse a `deployer.config` y editarse localmente.
>
> Significado de las claves principales del bloque `DS_1_*`:
> - `DS_1_NAME`: nombre lógico del dataspace que se va a crear.
> - `DS_1_NAMESPACE`: namespace de Kubernetes donde se despliega ese dataspace.
> - `DS_1_CONNECTORS`: lista separada por comas con los conectores que deben instanciarse dentro del dataspace.

## Tests

Ejecutar las suites principales del framework:

```bash
cd ~/Validation-Environment
source .venv/bin/activate
python -m unittest -v \
  tests.test_kafka_metrics \
  tests.test_newman_metrics \
  tests.test_experiment_summary \
  tests.test_main_cli \
  tests.test_inesdata_menu_cli \
  tests.test_kafka_manager
```

## Referencias técnicas

El flujo de validación y parte de las colecciones de este framework se han definido tomando como referencia materiales públicos del ecosistema INESData y Eclipse EDC.

Referencias principales:

- [InesData_Local_Environment.postman_collection.json](https://github.com/INESData/inesdata-local-env/blob/master/resources/operations/InesData_Local_Environment.postman_collection.json)
- [InesData_Connector_Management_API.postman_collection.json](https://github.com/INESData/inesdata-local-env/blob/master/resources/operations/InesData_Connector_Management_API.postman_collection.json)
- [Documentación pública de la Management API de Eclipse EDC](https://eclipse-edc.github.io/Connector/openapi/management-api/#/)
- [Sample de referencia para streaming Kafka en Eclipse EDC](https://github.com/eclipse-edc/Samples/tree/main/transfer/transfer-06-kafka-broker)
- [Guía de despliegue de INESData](https://github.com/DataSpaceUnit/ds-local-deployment)
- [Demo operativa de referencia](https://github.com/DataSpaceUnit/ds-local-deployment/blob/master/DEMO.md)

## Financiación

This work has received funding from the **PIONERA project** (Enhancing interoperability in data spaces through artificial intelligence), a project funded in the context of the call for Technological Products and Services for Data Spaces of the Ministry for Digital Transformation and Public Administration within the framework of the PRTR funded by the European Union (NextGenerationEU).

<div align="center">
  <img src="funding_label.png" alt="Logos financiación" width="900" />
</div>

---

## Autores y contacto

- **Mantenedor:** Adrian Vargas
- **Contacto:** adrian.vargas@upm.es

## Licencia

Validation-Environment is available under the **[Apache License 2.0](https://github.com/ProyectoPIONERA/pionera_env/blob/main/LICENSE)**.


