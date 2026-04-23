# Inicio Rápido

## Requisitos

Para ejecución local, el framework espera:

- Python 3.10 o superior;
- Git;
- Docker;
- Minikube;
- Helm;
- `kubectl`;
- Node.js y `npm`;
- cliente PostgreSQL;
- permisos para actualizar el fichero `hosts` del sistema cuando la sincronización de hosts esté habilitada.

La topología local usa Minikube. Las topologías VM usan Kubernetes directamente y actualmente se exponen de forma segura mediante contexto de topología, planificación de hosts y guardas de ejecución cuando la operación VM real aún no está implementada.

## Vista Local

El siguiente diagrama resume el entorno local de validación:

![PIONERA local validation environment](<./pionera local validation environment.png>)

## Bootstrap

Desde la raíz del repositorio:

```bash
bash scripts/bootstrap_framework.sh
```

En Linux/WSL, el bootstrap instala Playwright con sus dependencias del sistema
para evitar que las validaciones UI fallen al arrancar el navegador. En
entornos donde no se puedan instalar paquetes del sistema, usa
`bash scripts/bootstrap_framework.sh --without-system-deps`.

Después activa el entorno Python raíz:

```bash
source .venv/bin/activate
```

Revisa la configuración generada si necesitas ajustar credenciales, dominios o
dataspaces:

```text
deployers/infrastructure/deployer.config
deployers/inesdata/deployer.config
deployers/edc/deployer.config
```

Finalmente abre el menú guiado:

```bash
python3 main.py menu
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

Usa los ficheros `.example` como plantilla cuando existan. Los ficheros locales `deployer.config` pueden contener credenciales y no deben subirse al repositorio.

## Coexistencia de Adapters

`inesdata` y `edc` pueden reutilizar los servicios comunes de `common-srvs`.
Esa es la ruta esperada cuando se prueban ambos adapters sobre el mismo cluster
local.

La restricción importante es que cada adapter debe usar un dataspace aislado:

```text
inesdata -> DS_1_NAME=demo, DS_1_NAMESPACE=demo
edc      -> DS_1_NAME=demoedc, DS_1_NAMESPACE=demoedc
```

No reutilices el mismo `DS_1_NAME` o `DS_1_NAMESPACE` para dos adapters
distintos en el mismo cluster. El problema no sería compartir PostgreSQL,
Keycloak, MinIO o Vault, sino colisionar en namespaces, registration-service,
bases de datos, usuarios y artefactos generados por `Level 3`.

## Hosts

El framework puede planificar o aplicar entradas de `hosts` para el adapter y la topología seleccionados:

```bash
python3 main.py inesdata hosts --topology local --dry-run
python3 main.py edc hosts --topology local --dry-run
```

Para aplicar entradas, indica explícitamente el fichero destino:

```bash
PIONERA_SYNC_HOSTS=true \
PIONERA_HOSTS_FILE=/etc/hosts \
python3 main.py edc hosts --topology local
```

Desde WSL, el fichero `hosts` de Windows suele estar en:

```text
/mnt/c/Windows/System32/drivers/etc/hosts
```

La sincronización es idempotente: si una entrada ya existe fuera de los bloques gestionados, se omite en lugar de duplicarse.

## Niveles del Menú

El menú expone seis niveles:

- `Level 1`: prepara el cluster.
- `Level 2`: despliega servicios comunes.
- `Level 3`: despliega el dataspace.
- `Level 4`: despliega conectores.
- `Level 5`: despliega componentes opcionales.
- `Level 6`: ejecuta validaciones.

Para un despliegue local desde cero, ejecuta los niveles secuencialmente del `1` al `6`, o usa la opción `0` del menú.

La referencia completa del menú está en [Referencia del menú](./menu-reference.md).

## Minikube Tunnel

En despliegues locales puede ser necesario mantener `minikube tunnel` abierto para que los servicios sean accesibles por ingress:

```bash
minikube tunnel
```

Déjalo ejecutándose en otra terminal durante despliegue y validación.

Las validaciones funcionales deben usar los hostnames locales publicados por
Ingress. Los `port-forward` quedan reservados para comprobaciones internas o
diagnóstico de desarrollo; no deben sustituir la ruta normal de navegador o API.

Para PostgreSQL, el servicio del cluster sigue usando el puerto `5432`. El
framework intenta usar `PG_PORT=5432` como puerto local preferente. Si ese puerto
está ocupado por un `kubectl port-forward` antiguo del framework, lo libera y lo
recrea. Si pertenece a Windows, WSL u otro entorno local, el framework falla con
un diagnóstico y no termina procesos externos automáticamente.
