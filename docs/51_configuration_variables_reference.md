# Referencia de variables de configuración

Este documento resume las variables que el operador puede ajustar para adaptar
el framework a un entorno propio. La referencia se basa en las plantillas
versionadas:

```text
deployers/infrastructure/deployer.config.example
deployers/infrastructure/topologies/local.config.example
deployers/infrastructure/topologies/vm-single.config.example
deployers/infrastructure/topologies/vm-distributed.config.example
deployers/inesdata/deployer.config.example
deployers/edc/deployer.config.example
```

Las plantillas contienen el inventario bruto completo. Este documento organiza
esas variables por uso para que sea más fácil saber qué modificar y dónde.

La intención no es duplicar línea por línea todas las plantillas, porque eso
puede quedar obsoleto cuando cambie un `.config.example`. La fuente nominal
completa sigue siendo cada plantilla versionada; esta referencia documenta las
familias, el propósito operativo y el criterio de uso. Cuando haga falta auditar
el inventario exacto, usa el comando de la sección
[Mantenimiento de esta Referencia](#mantenimiento-de-esta-referencia).

## Reglas de uso

| Regla | Implicación |
| --- | --- |
| Los `.config` locales son la configuración efectiva. | Si un valor debe quedar persistido para un entorno, ajústalo en el `.config` correspondiente. |
| Los `.profiles/*.env` son entrada local. | Sirven para aplicar valores sobre `.config`, pero no reemplazan a los `.config`. |
| Las variables `PIONERA_*` son overrides de ejecución. | Úsalas para pruebas puntuales, CI/CD o comandos no interactivos. |
| Los secretos no deben versionarse. | Contraseñas, tokens, claves privadas y kubeconfigs reales deben vivir en `.secrets/`, variables de entorno o ficheros locales ignorados. |
| `W -> C` muestra la verdad efectiva. | Antes de desplegar en un entorno nuevo, revisa los valores y su origen con el asistente. |

## Precedencia

De menor a mayor prioridad:

1. Valores por defecto del código y plantillas `.config.example`.
2. `deployers/infrastructure/deployer.config`.
3. `deployers/infrastructure/topologies/<topology>.config`.
4. `deployers/<adapter>/deployer.config`.
5. Variables de entorno `PIONERA_*`.

Ejemplo:

```bash
PIONERA_DS_1_NAME=demo \
PIONERA_VM_EXTERNAL_IP=192.0.2.10 \
python3 main.py inesdata hosts --topology vm-single --dry-run
```

`PIONERA_DS_1_NAME` sobrescribe temporalmente `DS_1_NAME` y
`PIONERA_VM_EXTERNAL_IP` sobrescribe temporalmente `VM_EXTERNAL_IP`.

## Qué fichero modificar

| Necesidad | Fichero recomendado |
| --- | --- |
| Valores comunes a varias topologías | `deployers/infrastructure/deployer.config` |
| Valores propios de `local` | `deployers/infrastructure/topologies/local.config` |
| Valores propios de `vm-single` | `deployers/infrastructure/topologies/vm-single.config` |
| Valores propios de `vm-distributed` | `deployers/infrastructure/topologies/vm-distributed.config` |
| Dataspace, conectores y componentes INESData | `deployers/inesdata/deployer.config` |
| Dataspace, conectores y componentes EDC | `deployers/edc/deployer.config` |
| Ejecuciones puntuales o CI | Variables `PIONERA_*` o plan batch |
| Secretos locales | `.secrets/*.env` o variables del entorno de ejecución |

## Tipos de valor y formatos

No todas las variables tienen un conjunto cerrado de valores. Muchas son rutas,
URLs, nombres de imagen o listas propias del entorno. Esta tabla resume los
formatos más frecuentes.

| Tipo | Formato | Ejemplo |
| --- | --- | --- |
| Booleano | `true`/`false`. El framework también suele aceptar `1`, `0`, `yes`, `no`, `on`, `off`, `enabled`, `disabled`. | `LEVEL5_AUTO_BUILD_LOCAL_IMAGES=true` |
| Modo automático | `auto`, cuando el framework puede decidir según topología y contexto. | `VM_DISTRIBUTED_KUBECONFIG_SYNC=auto` |
| Lista simple | Valores separados por coma, sin espacios necesarios. | `DS_1_CONNECTORS=org2,org3` |
| Mapa simple | Pares `clave:valor` separados por coma. | `DS_1_CONNECTOR_NAMESPACES=org2:provider,org3:consumer` |
| Par de validación | Formato `origen>destino`, con varios pares separados por coma. | `DS_1_VALIDATION_PAIRS=org2>org3,org3>org2` |
| URL pública | URL completa con esquema. | `VM_PROVIDER_PUBLIC_URL=https://provider.example.org` |
| Host o IP | DNS o IP alcanzable desde quien ejecuta la operación. | `VM_COMMON_IP=192.0.2.10` |
| Imagen | Referencia `registry/imagen:tag` o `imagen:tag` si el runtime la resuelve localmente. | `AI_MODEL_HUB_IMAGE_REF=registry.example.org/pionera/ai-model-hub:1.0.0` |
| Ref de fuente | Rama, etiqueta o commit. Para reproducibilidad, preferir commit o tag. | `AI_MODEL_HUB_SOURCE_REF=91ef338c4203` |
| Ruta local | Ruta absoluta o relativa al checkout, según la variable. | `K3S_KUBECONFIG_COMMON=.profiles/kubeconfigs/common.yaml` |

En ejemplos documentales se usan direcciones reservadas como `192.0.2.10` y
dominios `example.org`. Sustitúyelos por direcciones reales del entorno.

## Valores controlados más usados

Estas variables sí tienen modos o valores recomendados. Si una variable no
aparece aquí, normalmente es un texto libre con el formato indicado en la
sección anterior o en su plantilla `.config.example`.

| Variable o familia | Valores habituales | Cuándo usar cada valor |
| --- | --- | --- |
| `TOPOLOGY` | `local`, `vm-single`, `vm-distributed` | Selecciona la topología del fichero. No mezclar valores entre overlays. |
| `NAMESPACE_PROFILE` | `compact`, `role-aligned` | `compact` conserva el layout histórico; `role-aligned` separa roles como `core-control`, `provider`, `consumer` y `components`. |
| `CLUSTER_TYPE` | `minikube`, `k3s` | `local` usa normalmente `minikube`; `vm-single` y `vm-distributed` usan `k3s`. |
| `LOCAL_RESOURCE_PROFILE` | `single-adapter`, `coexistence` | `single-adapter` para validar un adapter; `coexistence` cuando INESData y EDC conviven en local con más memoria. |
| `LEVEL4_CONNECTOR_RECONCILIATION_MODE` | `full`, `additive` | `full` para instalación limpia; `additive` para añadir conectores sin recrear conectores sanos. |
| `LEVEL4_LOCAL_IMAGES_MODE`, `INESDATA_LOCAL_IMAGES_MODE`, `EDC_LOCAL_IMAGES_MODE` | `auto`, `required`, `disabled` | `auto` prepara imágenes cuando procede; `required` falla si no puede prepararlas; `disabled` obliga a usar imágenes ya disponibles. |
| `PIONERA_VALIDATION_MODE`, `LEVEL6_VALIDATION_MODE` | `auto`, `stable`, `fast` | `auto` usa `stable` en `local` y `fast` en VM; `stable` reduce solapamiento; `fast` prioriza tiempo. |
| `SSH_ACCESS_MODE`, `VM_*_SSH_ACCESS_MODE` | `direct`, `bastion` | `direct` cuando la VM es alcanzable; `bastion` cuando se entra mediante salto SSH. |
| `FRAMEWORK_EXECUTION_MODE` | `auto`, `orchestrator`, `target-vm` | `orchestrator` cuando el framework corre desde estación operadora; `target-vm` cuando corre dentro de la VM objetivo. |
| `VM_DISTRIBUTED_EXECUTION_HOST` | `auto`, `external`, `common-services` | `external` si se ejecuta desde fuera; `common-services` si se ejecuta desde la VM de servicios comunes. |
| `VM_SINGLE_LEVEL_EXECUTION_MODE` | `local`, `tunnel`, `remote`, `auto` | `local` si se opera dentro de la VM; `tunnel` si el operador usa túnel a k3s; `remote` para ejecutar niveles por SSH; `auto` deja decidir al framework. |
| `VM_SINGLE_K3S_TUNNEL_MODE`, `VM_DISTRIBUTED_K3S_TUNNEL_MODE`, `SEMANTIC_VIRTUALIZATION_MAPPING_EDITOR_TUNNEL_MODE` | `auto`, `disabled`, `manual`, `false` | `auto` intenta preparar túneles cuando procede; `disabled`/`manual` evita que el framework los cree. |
| `VM_DISTRIBUTED_KUBECONFIG_SYNC` | `auto`, `enabled`, `disabled` | `auto` sincroniza cuando la ejecución lo requiere; `enabled` fuerza preparación; `disabled` exige kubeconfigs ya preparados. |
| `VM_SINGLE_WORKSPACE_SYNC` | `auto`, `always`, `disabled`, `manual` | `auto` sincroniza cuando hace falta; `always` fuerza sync; `disabled`/`manual` lo evita. |
| `VM_DISTRIBUTED_SSH_BOOTSTRAP_MODE`, `VM_SINGLE_SSH_BOOTSTRAP_MODE` | `manual`, `plan`, `auto` | `manual` no escribe llaves; `plan` muestra acciones; `auto` intenta prepararlas cuando hay identidad dedicada. |
| `VM_DISTRIBUTED_HTTP_PREFLIGHT_TLS_VERIFY` | `auto`, `true`, `false` | `auto` verifica TLS en HTTPS; `false` solo para entornos controlados con certificados no confiables. |
| `VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT` | `true`, `false` | `true` importa imágenes por SSH/k3s; `false` para registry compartido o despliegue delegado. |
| `VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT_INTERACTIVE` | `auto`, `always`, `never` | `auto` permite interacción cuando la importación lo requiere; `never` para CI/no interactivo. |
| `VM_DISTRIBUTED_POSTGRES_ACCESS_MODE` | `direct`, `nodeport` | `direct` si los workloads alcanzan PostgreSQL internamente; `nodeport` si conectores remotos necesitan endpoint expuesto. |
| `K3S_INGRESS_SERVICE_TYPE`, `KAFKA_K8S_EXTERNAL_SERVICE_TYPE` | `LoadBalancer`, `NodePort`, `ClusterIP` | `LoadBalancer`/`NodePort` para exposición fuera del clúster; `ClusterIP` solo dentro del clúster. |
| `*_IMAGE_PULL_POLICY` | `Always`, `IfNotPresent`, `Never` | `Always` descarga siempre; `IfNotPresent` reutiliza si existe; `Never` exige imagen local ya cargada. |
| `COMPONENTS_RELEASE_SCOPE` | `auto`, `dataspace`, `shared` | `auto` usa la lógica del adapter; `dataspace` separa por dataspace; `shared` reutiliza release común. |
| `COMPONENTS_SHARED_RELEASE_COMPONENTS` | Lista, `*`, `all`, `none`, `false`, `0` | Lista componentes compartidos; `*`/`all` comparte todos; `none`/`false`/`0` no comparte. |
| `AI_MODEL_HUB_MODEL_SERVER_ENABLED` | `true`, `false` | Activa o desactiva el model-server gestionado por Nivel 5. |
| `AI_MODEL_HUB_MODEL_SERVER_MODE` | `mock`, `use-cases`, `combined`, `external`, valores tipo `false` para desactivar | `mock` para endpoint determinista; `use-cases` para casos oficiales; `combined` para servidor combinado; `external` si el endpoint ya existe fuera. |
| `KAFKA_PROVISIONER` | `kubernetes`, `kubernetes-split-kraft`, `docker` | `kubernetes` es el modo habitual; `kubernetes-split-kraft` ayuda en `vm-distributed`; `docker` queda para desarrollo avanzado. |
| `KAFKA_EDC_VALIDATION_BACKEND` | `kubernetes-exec`, `python-client` | `kubernetes-exec` valida desde el clúster; `python-client` usa cliente Python desde el host. |
| `SEMANTIC_VIRTUALIZATION_MAPPING_EDITOR_EXPOSURE_MODE` | `ingress`, `host-port` | `ingress` publica por Ingress; `host-port` usa puerto directo cuando se configura `*_HOST_PORT`. |
| `EDC_DASHBOARD_PROXY_AUTH_MODE` | `service-account`, `oidc-bff` | `service-account` usa credenciales técnicas; `oidc-bff` habilita flujo OIDC para el dashboard. |

## Variables base

| Variable | Para qué sirve | Uso habitual |
| --- | --- | --- |
| `ENVIRONMENT` | Nombre lógico del entorno de despliegue. | Mantener `DEV` salvo que se separen despliegues por entorno. |
| `NAMESPACE_PROFILE` | Perfil de namespaces. | `role-aligned` para separar `core-control`, `provider`, `consumer` y `components`; `compact` para rutas históricas. |
| `COMMON_SERVICES_NAMESPACE` | Namespace de servicios comunes. | Normalmente `common-srvs`. |
| `COMPONENTS_NAMESPACE` | Namespace de componentes compartidos. | Normalmente `components`. |
| `DOMAIN_BASE` | Dominio base de servicios comunes y componentes. | Configurar por topología si hay DNS/Ingress propio. |
| `DS_DOMAIN_BASE` | Dominio base de conectores y dataspace. | Configurar por topología si los conectores se publican con otro dominio. |
| `TOPOLOGY` | Topología activa representada por el fichero. | `local`, `vm-single` o `vm-distributed`; no mezclar valores entre ficheros. |

## Secretos y credenciales

Estas variables aparecen en plantillas para bootstrap local, pero sus valores
reales no deben publicarse:

| Variable | Para qué sirve | Recomendación |
| --- | --- | --- |
| `KC_USER`, `KC_PASSWORD` | Usuario administrador inicial de Keycloak. | Mantener en `.config` local ignorado o secreto externo. |
| `PG_USER`, `PG_PASSWORD` | Usuario de PostgreSQL. | No versionar valores reales. |
| `MINIO_USER`, `MINIO_PASSWORD` | Credenciales de MinIO. | No versionar valores reales. |
| `MINIO_ADMIN_USER`, `MINIO_ADMIN_PASS` | Credenciales administrativas de MinIO. | No versionar valores reales. |
| `VT_TOKEN` | Token de Vault, si se usa. | Preferir `.secrets/` o entorno seguro. |
| `ONTOLOGY_HUB_ADMIN_EMAIL`, `ONTOLOGY_HUB_ADMIN_PASSWORD` | Credenciales administrativas para Ontology Hub cuando aplican. | Dejar vacío si no se requiere o mover a secreto local. |
| `SSH_IDENTITY_FILE`, `*_SSH_IDENTITY_FILE` | Ruta a llave privada SSH local. | Usar rutas locales ignoradas; nunca copiar claves al repositorio. |

Los perfiles `.profiles/*.env` rechazan claves sensibles por nombre. Si una
clave incluye `PASSWORD`, `TOKEN`, `SECRET`, `PRIVATE_KEY`, `UNSEAL` o
`ROOT_KEY`, debe tratarse como secreto y no como perfil público.

## Dataspace, namespaces y conectores

| Variable | Para qué sirve | Uso habitual |
| --- | --- | --- |
| `DS_1_NAME` | Nombre del dataspace. | `pionera` para INESData, `pionera-edc` para EDC, o nombre propio del entorno. |
| `DS_1_NAMESPACE` | Namespace del control plane del dataspace. | `core-control` o equivalente del adapter. |
| `DS_1_REGISTRATION_NAMESPACE` | Namespace del registration service. | Normalmente igual a `DS_1_NAMESPACE`. |
| `DS_1_PROVIDER_NAMESPACE` | Namespace para conectores del grupo provider. | `provider` o namespace adapter-specific. |
| `DS_1_CONSUMER_NAMESPACE` | Namespace para conectores del grupo consumer. | `consumer` o namespace adapter-specific. |
| `DS_1_CONNECTORS` | Inventario lógico de conectores. | Lista separada por comas, por ejemplo `org2,org3`. |
| `DS_1_CONNECTOR_NAMESPACES` | Ubicación de conectores por rol/namespace. | Formato `org2:provider,org3:consumer`. |
| `DS_1_VALIDATION_PAIRS` | Pares origen-destino de validación. | Formato `org2>org3`; admite varios pares separados por comas. |
| `LEVEL4_CONNECTOR_RECONCILIATION_MODE` | Modo de reconciliación de conectores. | `full` para instalación limpia; `additive` para añadir sin recrear conectores sanos. |
| `LEVEL4_SYNC_EXISTING_CONNECTOR_KEYCLOAK_CLIENTS` | Sincroniza clientes técnicos existentes en modo aditivo. | Mantener `true` salvo diagnóstico. |

Ejemplo de dataspace con dos conectores:

```ini
DS_1_NAME=pionera
DS_1_NAMESPACE=core-control
DS_1_REGISTRATION_NAMESPACE=core-control
DS_1_PROVIDER_NAMESPACE=provider
DS_1_CONSUMER_NAMESPACE=consumer
DS_1_CONNECTORS=org2,org3
DS_1_CONNECTOR_NAMESPACES=org2:provider,org3:consumer
DS_1_VALIDATION_PAIRS=org2>org3,org3>org2
LEVEL4_CONNECTOR_RECONCILIATION_MODE=full
```

Para añadir un conector a un entorno ya estable, cambia el inventario y usa modo
aditivo:

```ini
DS_1_CONNECTORS=org2,org3,org4
DS_1_CONNECTOR_NAMESPACES=org2:provider,org3:consumer,org4:provider
DS_1_VALIDATION_PAIRS=org2>org3,org4>org3
LEVEL4_CONNECTOR_RECONCILIATION_MODE=additive
```

## Topología `local`

| Variable | Para qué sirve |
| --- | --- |
| `LOCAL_HOSTS_ADDRESS` | Dirección usada para entradas locales de `hosts`; suele quedar vacía para usar `127.0.0.1`. |
| `LOCAL_INGRESS_EXTERNAL_IP` | IP local de Ingress si no se usa el valor canónico. |
| `LOCAL_RESOURCE_PROFILE` | Perfil de recursos local: por ejemplo `single-adapter` o `coexistence`. |
| `MINIKUBE_DRIVER` | Driver de Minikube, normalmente `docker`. |
| `MINIKUBE_CPUS` | vCPU asignadas a Minikube. |
| `MINIKUBE_MEMORY` | Memoria asignada a Minikube en MB. |
| `MINIKUBE_PROFILE` | Perfil de Minikube que usa el framework. |

Si se modifican CPU o memoria de Minikube, hay que recrear el clúster desde
Nivel 1.

Ejemplo para validar un adapter local:

```ini
TOPOLOGY=local
CLUSTER_TYPE=minikube
DOMAIN_BASE=pionera.local
DS_DOMAIN_BASE=pionera.local
LOCAL_RESOURCE_PROFILE=single-adapter
MINIKUBE_DRIVER=docker
MINIKUBE_CPUS=10
MINIKUBE_MEMORY=14336
MINIKUBE_PROFILE=minikube
```

Ejemplo para coexistencia local de adapters, solo si Docker Desktop tiene
memoria suficiente:

```ini
LOCAL_RESOURCE_PROFILE=coexistence
MINIKUBE_CPUS=10
MINIKUBE_MEMORY=18432
```

## Topología `vm-single`

| Variable | Para qué sirve |
| --- | --- |
| `VM_EXTERNAL_IP` | Dirección principal de la VM o del Ingress publicado. |
| `INGRESS_EXTERNAL_IP` | IP que usará Ingress para publicar servicios. |
| `VM_SINGLE_PUBLIC_URL` | URL pública explícita para la VM cuando no basta con inferirla desde dominios. |
| `VM_SINGLE_HTTP_URL` | URL HTTP interna o semipública para flujos que la requieran. |
| `VM_SINGLE_CONNECTOR_PUBLIC_PATH_PREFIX` | Prefijo público de conectores INESData en `vm-single`. |
| `EDC_VM_SINGLE_CONNECTOR_PUBLIC_PATH_PREFIX` | Prefijo público de conectores EDC en `vm-single`. |
| `VM_SINGLE_LOCAL_KUBECONFIG` | Kubeconfig local generado o usado para operar k3s. |
| `VM_SINGLE_REMOTE_KUBECONFIG` | Ruta remota del kubeconfig dentro de la VM. |
| `VM_SINGLE_K3S_TUNNEL_MODE` | Controla si el framework prepara túnel para la API k3s cuando la red lo permite. |
| `VM_SINGLE_REMOTE_IMAGE_IMPORT` | Controla si se importan imágenes locales al runtime remoto. |
| `VM_SINGLE_WORKSPACE_SYNC` | Sincronización de workspace hacia la VM, si se usa ejecución remota. |

Ejemplo mínimo para operar una VM con k3s:

```ini
TOPOLOGY=vm-single
CLUSTER_TYPE=k3s
VM_EXTERNAL_IP=192.0.2.10
INGRESS_EXTERNAL_IP=192.0.2.10
VM_SINGLE_PUBLIC_URL=https://vm-single.example.org
VM_SINGLE_K3S_TUNNEL_MODE=auto
VM_SINGLE_LOCAL_KUBECONFIG=.profiles/kubeconfigs/vm-single.yaml
```

Si el framework se ejecuta dentro de la propia VM, evita depender de túnel:

```ini
FRAMEWORK_EXECUTION_MODE=target-vm
VM_SINGLE_LEVEL_EXECUTION_MODE=local
VM_SINGLE_K3S_TUNNEL_MODE=disabled
```

## Topología `vm-distributed`

| Variable o familia | Para qué sirve |
| --- | --- |
| `VM_COMMON_IP`, `VM_PROVIDER_IP`, `VM_CONSUMER_IP`, `VM_COMPONENTS_IP` | Direcciones de VMs o roles lógicos. |
| `VM_PROVIDER_K8S_NODE`, `VM_CONSUMER_K8S_NODE` | Nodos Kubernetes donde deben programarse conectores en un clúster compartido. |
| `VM_COMMON_PUBLIC_URL`, `VM_PROVIDER_PUBLIC_URL`, `VM_CONSUMER_PUBLIC_URL` | URLs públicas explícitas por rol. |
| `K3S_KUBECONFIG_COMMON`, `K3S_KUBECONFIG_PROVIDER`, `K3S_KUBECONFIG_CONSUMER`, `K3S_KUBECONFIG_COMPONENTS` | Kubeconfigs por rol cuando hay varios clústeres o contextos. |
| `VM_DISTRIBUTED_EXECUTION_HOST` | Dónde se ejecuta el framework: `auto`, `external` o `common-services`. |
| `VM_DISTRIBUTED_DEPLOYMENT_MODE` | Modo operativo de despliegue distribuido. |
| `VM_DISTRIBUTED_KUBECONFIG_SYNC` | Preparación/localización de kubeconfigs. |
| `VM_DISTRIBUTED_K3S_TUNNEL_MODE` | Uso de túnel para API k3s, solo si la política de red lo permite. |
| `VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT` | Importación remota de imágenes por SSH/k3s. Desactivar si se usa registry o despliegue delegado. |
| `VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT_COMMAND` | Comando remoto para importar imágenes, por ejemplo `k3s ctr`. |
| `VM_DISTRIBUTED_REMOTE_NGINX_INTERACTIVE` | Control de sincronización NGINX remota interactiva. |
| `VM_DISTRIBUTED_POSTGRES_ACCESS_MODE` | Cómo acceden conectores remotos a PostgreSQL: `direct` o `nodeport`. |
| `VM_PROVIDER_CONNECTORS`, `VM_CONSUMER_CONNECTORS` | Distribución explícita de conectores por rol. |
| `CONNECTOR_PROTOCOL_ADDRESS_MODE` | Modo de dirección usada para protocolo de conector, por ejemplo interna o pública. |

Para VMs externas, no configures túneles si las políticas de red no los
autorizan. Usa acceso aprobado directo, registry compartido o despliegue
delegado.

Ejemplo con tres roles accesibles por la estación operadora:

```ini
TOPOLOGY=vm-distributed
CLUSTER_TYPE=k3s
VM_DISTRIBUTED_EXECUTION_HOST=external
VM_COMMON_IP=192.0.2.10
VM_PROVIDER_IP=192.0.2.11
VM_CONSUMER_IP=192.0.2.12
VM_COMPONENTS_IP=192.0.2.10
VM_COMMON_PUBLIC_URL=https://common.example.org
VM_PROVIDER_PUBLIC_URL=https://provider.example.org
VM_CONSUMER_PUBLIC_URL=https://consumer.example.org
K3S_KUBECONFIG_COMMON=.profiles/kubeconfigs/common.yaml
K3S_KUBECONFIG_PROVIDER=.profiles/kubeconfigs/provider.yaml
K3S_KUBECONFIG_CONSUMER=.profiles/kubeconfigs/consumer.yaml
K3S_KUBECONFIG_COMPONENTS=.profiles/kubeconfigs/common.yaml
```

Ejemplo para una VM externa donde no se autorizan túneles ni importación por
SSH. En este caso el conector externo debe desplegarse por una ruta aprobada y
el framework valida contra endpoints publicados:

```ini
VM_DISTRIBUTED_K3S_TUNNEL_MODE=disabled
VM_DISTRIBUTED_KUBECONFIG_SYNC=disabled
VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT=false
VM_PROVIDER_PUBLIC_URL=https://provider.example.org
VM_CONSUMER_PUBLIC_URL=https://consumer.external.example.org
CONNECTOR_PROTOCOL_ADDRESS_MODE=public
```

## Kubernetes, k3s e ingress

| Variable | Para qué sirve |
| --- | --- |
| `CLUSTER_TYPE` | Runtime Kubernetes esperado: `minikube`, `k3s` u otro soportado. |
| `K3S_KUBECONFIG` | Kubeconfig principal para k3s. |
| `K3S_INSTALL_EXEC` | Parámetros de instalación de k3s, por ejemplo desactivar Traefik. |
| `K3S_SERVICE_NAME` | Nombre del servicio systemd de k3s. |
| `K3S_INGRESS_CONTROLLER` | Controlador Ingress esperado. |
| `K3S_INGRESS_SERVICE_TYPE` | Tipo de servicio de Ingress, por ejemplo `LoadBalancer`. |
| `K3S_INGRESS_HTTP_NODEPORT` | NodePort HTTP si se usa exposición por NodePort. |
| `K3S_REPAIR_ON_LEVEL1` | Comportamiento de reparación en Nivel 1. |
| `K3S_WRITE_KUBECONFIG_MODE` | Permisos del kubeconfig generado por k3s. |

Ejemplo k3s con Ingress por `LoadBalancer`:

```ini
CLUSTER_TYPE=k3s
K3S_INSTALL_EXEC=--disable=traefik
K3S_SERVICE_NAME=k3s
K3S_INGRESS_CONTROLLER=ingress-nginx
K3S_INGRESS_SERVICE_TYPE=LoadBalancer
K3S_WRITE_KUBECONFIG_MODE=0644
```

Ejemplo k3s con Ingress por `NodePort`:

```ini
K3S_INGRESS_SERVICE_TYPE=NodePort
K3S_INGRESS_HTTP_NODEPORT=32080
```

## SSH y acceso remoto

| Variable o familia | Para qué sirve |
| --- | --- |
| `SSH_ACCESS_MODE` | Modo global: `direct` o `bastion`. |
| `SSH_BASTION_HOST`, `SSH_BASTION_PORT`, `SSH_BASTION_USER`, `SSH_BASTION_IDENTITY_FILE` | Bastión global si aplica. |
| `SSH_IDENTITY_FILE` | Llave SSH global por defecto. |
| `SSH_CONNECT_TIMEOUT_SECONDS` | Timeout de conexión SSH. |
| `VM_SINGLE_SSH_*` | Acceso SSH específico de `vm-single`. |
| `VM_COMMON_SSH_*`, `VM_PROVIDER_SSH_*`, `VM_CONSUMER_SSH_*`, `VM_COMPONENTS_SSH_*` | Acceso SSH por rol en `vm-distributed`. |
| `VM_*_SSH_ACCESS_MODE` | Permite mezclar roles directos y roles por bastión. |
| `VM_*_SSH_BASTION_*` | Bastión específico por rol. |

El asistente `W -> 6` ayuda a preparar acceso SSH dedicado cuando la política de
red lo permite.

Ejemplo de acceso directo:

```ini
SSH_ACCESS_MODE=direct
SSH_IDENTITY_FILE=~/.ssh/pionera_validation
VM_COMMON_SSH_HOST=192.0.2.10
VM_COMMON_SSH_USER=ubuntu
VM_COMMON_SSH_PORT=22
```

Ejemplo con bastión:

```ini
SSH_ACCESS_MODE=bastion
SSH_IDENTITY_FILE=~/.ssh/pionera_validation
SSH_BASTION_HOST=bastion.example.org
SSH_BASTION_USER=operator
SSH_BASTION_PORT=2222
VM_PROVIDER_SSH_HOST=10.10.0.21
VM_PROVIDER_SSH_USER=ubuntu
VM_PROVIDER_SSH_PORT=22
```

## URLs públicas y servicios compartidos

| Variable o familia | Para qué sirve |
| --- | --- |
| `KC_URL`, `KC_INTERNAL_URL` | URLs de Keycloak para operación externa e interna. |
| `KEYCLOAK_HOSTNAME`, `KEYCLOAK_ADMIN_HOSTNAME`, `KEYCLOAK_FRONTEND_URL`, `KEYCLOAK_PUBLIC_URL` | Hostnames y URLs públicas de Keycloak. |
| `MINIO_ENDPOINT`, `MINIO_HOSTNAME`, `MINIO_CONSOLE_HOSTNAME` | Endpoint y hostnames de MinIO. |
| `MINIO_API_PUBLIC_URL`, `MINIO_CONSOLE_PUBLIC_URL`, `MINIO_PUBLIC_URL` | URLs públicas de MinIO. |
| `MINIO_CONSOLE_PUBLIC_ROOT_ALIASES*` | Alias de rutas públicas para consola MinIO cuando se publica por proxy. |
| `DATABASE_HOSTNAME` | Host interno de PostgreSQL para workloads desplegados. |
| `VAULT_URL`, `VT_URL` | URLs de Vault. |
| `COMPONENTS_PUBLIC_BASE_URL` | Base pública de componentes compartidos. |
| `COMPONENTS_PUBLIC_PATH_REWRITE` | Controla reescritura por path para componentes. |

Ejemplo de URLs públicas explícitas:

```ini
KEYCLOAK_FRONTEND_URL=https://common.example.org/auth
KEYCLOAK_PUBLIC_URL=https://common.example.org/auth
MINIO_API_PUBLIC_URL=https://common.example.org/s3
MINIO_CONSOLE_PUBLIC_URL=https://common.example.org/s3-console
COMPONENTS_PUBLIC_BASE_URL=https://components.example.org
```

## Imágenes, fuentes y build

| Variable o familia | Para qué sirve |
| --- | --- |
| `LEVEL4_LOCAL_IMAGES_MODE` | Control de imágenes locales en conectores. |
| `LEVEL5_AUTO_BUILD_LOCAL_IMAGES`, `LEVEL6_AUTO_BUILD_LOCAL_IMAGES` | Build automático de imágenes antes de componentes o validación. |
| `LEVEL5_ASSUME_LOCAL_IMAGES_AVAILABLE`, `LEVEL6_ASSUME_LOCAL_IMAGES_AVAILABLE` | Evita build cuando las imágenes ya están disponibles. |
| `COMPONENTS_IMAGE_PULL_POLICY` | Política de descarga de imágenes de componentes. |
| `*_IMAGE_REF` | Referencia completa de imagen con tag para componentes. |
| `*_IMAGE_NAME`, `*_IMAGE_TAG` | Nombre y tag separados para imágenes de conectores o dashboards. |
| `*_SOURCE_REPOSITORY` | Repositorio fuente para construir componente o servidor auxiliar. |
| `*_SOURCE_REF` | Rama, tag o commit fuente. |
| `*_SOURCE_REFRESH` | Controla si se refresca la fuente antes de construir. |

Para despliegues compartidos o con VMs externas, es preferible usar imágenes
publicadas en un registry accesible por los clústeres implicados.

Ejemplo con imágenes publicadas en registry:

```ini
LEVEL4_LOCAL_IMAGES_MODE=disabled
COMPONENTS_IMAGE_PULL_POLICY=IfNotPresent
AI_MODEL_HUB_IMAGE_REF=registry.example.org/pionera/ai-model-hub:1.0.0
ONTOLOGY_HUB_IMAGE_REF=registry.example.org/pionera/ontology-hub:1.0.0
SEMANTIC_VIRTUALIZATION_IMAGE_REF=registry.example.org/pionera/semantic-virtualization:1.0.0
```

Ejemplo de desarrollo local estricto:

```ini
LEVEL4_LOCAL_IMAGES_MODE=required
LEVEL5_AUTO_BUILD_LOCAL_IMAGES=true
LEVEL6_AUTO_BUILD_LOCAL_IMAGES=true
COMPONENTS_IMAGE_PULL_POLICY=Never
```

## Componentes

| Variable o familia | Para qué sirve |
| --- | --- |
| `COMPONENTS` | Lista de componentes a desplegar. |
| `COMPONENTS_RELEASE_SCOPE` | Ámbito del release de componentes. |
| `COMPONENTS_RELEASE_DATASPACE_NAME` | Dataspace asociado a releases de componentes si se necesita fijarlo. |
| `COMPONENTS_SHARED_RELEASE_COMPONENTS` | Componentes compartidos entre adapters. |
| `ONTOLOGY_HUB_*` | Imagen, fuentes, URL pública, persistencia de versiones y URLs internas de Ontology Hub. |
| `AI_MODEL_HUB_*` | Imagen, fuentes, URL pública y opciones de AI Model Hub. |
| `SEMANTIC_VIRTUALIZATION_*` | Imagen, fuentes y URL pública de Semantic Virtualization. |
| `SEMANTIC_VIRTUALIZATION_MAPPING_EDITOR_*` | Exposición del editor Streamlit: URL, host port, service type, NodePort o túnel. |
| `AUTOMAP_*` | Repositorio, ref y refresh de Automap para validaciones de virtualización semántica. |

Ejemplo para desplegar componentes compartidos:

```ini
COMPONENTS=ontology-hub,ai-model-hub,semantic-virtualization
COMPONENTS_NAMESPACE=components
COMPONENTS_RELEASE_SCOPE=auto
COMPONENTS_SHARED_RELEASE_COMPONENTS=ontology-hub,ai-model-hub,semantic-virtualization
```

Ejemplo para exponer el mapping editor por host/puerto:

```ini
SEMANTIC_VIRTUALIZATION_MAPPING_EDITOR_ENABLED=true
SEMANTIC_VIRTUALIZATION_MAPPING_EDITOR_EXPOSURE_MODE=host-port
SEMANTIC_VIRTUALIZATION_MAPPING_EDITOR_PUBLIC_HOST=components.example.org
SEMANTIC_VIRTUALIZATION_MAPPING_EDITOR_HOST_PORT=8501
```

## AI Model Hub y model server

| Variable | Para qué sirve |
| --- | --- |
| `AI_MODEL_HUB_MODEL_SERVER_ENABLED` | Indica si Nivel 5 despliega o gestiona model-server. |
| `AI_MODEL_HUB_MODEL_SERVER_MODE` | Modo del servidor: vacío/mock, `use-cases`, `combined` o `external`. |
| `AI_MODEL_HUB_MODEL_SERVER_IMAGE` | Imagen del model-server. |
| `AI_MODEL_HUB_MODEL_SERVER_SOURCE_*` | Fuente para construir servidor de casos de uso. |
| `AI_MODEL_HUB_MODEL_SERVER_CONNECTOR_BASE_URL` | URL que usan los conectores para ejecutar modelos. |
| `AI_MODEL_HUB_MODEL_SERVER_PUBLIC_URL` | URL pública del model-server. |
| `AI_MODEL_HUB_MODEL_SERVER_VALIDATION_*` | Rutas y payloads usados por validación. |
| `AI_MODEL_HUB_REAL_MODELS_ARTIFACT_DIR` | Directorio de artefactos de modelos reales. |
| `AI_MODEL_HUB_REAL_MODELS_TRAIN_COMMAND` | Comando de entrenamiento cuando se habilitan modelos reales. |
| `AI_MODEL_OBSERVER_JOURNAL_BASE_URL` | URL del journal/observer accesible para conectores. |

Ejemplo para usar el servidor de casos de uso oficiales:

```ini
AI_MODEL_HUB_MODEL_SERVER_ENABLED=true
AI_MODEL_HUB_MODEL_SERVER_MODE=use-cases
AI_MODEL_HUB_MODEL_SERVER_SOURCE_REPOSITORY=https://github.com/ProyectoPIONERA/AIModelHub-Use-Cases.git
AI_MODEL_HUB_MODEL_SERVER_SOURCE_REF=main
AI_MODEL_HUB_MODEL_SERVER_IMAGE=model-server:latest
AI_MODEL_HUB_MODEL_SERVER_CONNECTOR_BASE_URL=http://model-server.components.svc.cluster.local:8080
AI_MODEL_HUB_MODEL_SERVER_PUBLIC_URL=https://components.example.org/model-server
```

Ejemplo para validar contra un servidor externo ya desplegado:

```ini
AI_MODEL_HUB_MODEL_SERVER_ENABLED=true
AI_MODEL_HUB_MODEL_SERVER_MODE=external
AI_MODEL_HUB_MODEL_SERVER_CONNECTOR_BASE_URL=https://models.external.example.org
AI_MODEL_HUB_MODEL_SERVER_PUBLIC_URL=https://models.external.example.org
```

## Kafka

| Variable o familia | Para qué sirve |
| --- | --- |
| `KAFKA_PROVISIONER` | Quién prepara Kafka, por ejemplo `kubernetes`. |
| `KAFKA_K8S_NAMESPACE`, `KAFKA_K8S_SERVICE_NAME` | Namespace y servicio Kafka. |
| `KAFKA_K8S_EXTERNAL_SERVICE_TYPE`, `KAFKA_K8S_NODEPORT`, `KAFKA_K8S_LOCAL_PORT` | Exposición de Kafka para pruebas y conectores. |
| `KAFKA_BOOTSTRAP_SERVERS` | Bootstrap usado por el proceso del framework. |
| `KAFKA_CLUSTER_BOOTSTRAP_SERVERS` | Bootstrap que reciben los conectores; debe ser alcanzable desde sus VMs/clústeres. |
| `KAFKA_CLUSTER_ADVERTISED_HOST` | Host anunciado para Kafka si se expone fuera del clúster. |
| `KAFKA_EDC_*` | Timeouts, reintentos y parámetros de validación Kafka EDC. |

En `vm-distributed`, `KAFKA_CLUSTER_BOOTSTRAP_SERVERS` no debe apuntar a
`localhost`, `host.minikube.internal` ni a DNS `*.svc` si los conectores están
en otros clústeres o VMs.

Ejemplo local con Kafka gestionado por Kubernetes:

```ini
KAFKA_PROVISIONER=kubernetes
KAFKA_K8S_NAMESPACE=core-control
KAFKA_K8S_SERVICE_NAME=framework-kafka
KAFKA_K8S_EXTERNAL_SERVICE_TYPE=ClusterIP
KAFKA_BOOTSTRAP_SERVERS=
```

Ejemplo `vm-distributed` con Kafka expuesto por `NodePort`:

```ini
KAFKA_PROVISIONER=kubernetes-split-kraft
KAFKA_K8S_NAMESPACE=core-control
KAFKA_K8S_SERVICE_NAME=framework-kafka
KAFKA_K8S_EXTERNAL_SERVICE_TYPE=NodePort
KAFKA_K8S_NODEPORT=32093
KAFKA_CLUSTER_ADVERTISED_HOST=192.0.2.10
KAFKA_CLUSTER_BOOTSTRAP_SERVERS=192.0.2.10:32093
KAFKA_EDC_VALIDATION_BACKEND=kubernetes-exec
```

## Variables específicas de INESData

| Variable o familia | Para qué sirve |
| --- | --- |
| `INESDATA_CONNECTOR_IMAGE_NAME`, `INESDATA_CONNECTOR_IMAGE_TAG` | Imagen del conector INESData. |
| `INESDATA_CONNECTOR_INTERFACE_IMAGE_NAME`, `INESDATA_CONNECTOR_INTERFACE_IMAGE_TAG` | Imagen del portal/interfaz del conector. |
| `DS_1_CONNECTORS`, `DS_1_CONNECTOR_NAMESPACES`, `DS_1_VALIDATION_PAIRS` | Inventario y pares de validación INESData. |
| `KAFKA_K8S_PROBE_NAMESPACES` | Namespaces donde se comprueba Kafka para flujos INESData. |

## Variables específicas de EDC

| Variable o familia | Para qué sirve |
| --- | --- |
| `EDC_CONNECTOR_IMAGE_NAME`, `EDC_CONNECTOR_IMAGE_TAG` | Imagen del conector EDC. |
| `EDC_DASHBOARD_ENABLED` | Habilita dashboard EDC. |
| `EDC_DASHBOARD_REPO_URL`, `EDC_DASHBOARD_REPO_REF` | Fuente del dashboard EDC. |
| `EDC_DASHBOARD_IMAGE_NAME`, `EDC_DASHBOARD_IMAGE_TAG` | Imagen del dashboard. |
| `EDC_DASHBOARD_PROXY_IMAGE_NAME`, `EDC_DASHBOARD_PROXY_IMAGE_TAG` | Imagen del proxy/BFF del dashboard. |
| `EDC_DASHBOARD_PROXY_AUTH_MODE` | Modo de autenticación del proxy. |
| `EDC_DASHBOARD_PROXY_CLIENT_ID`, `EDC_DASHBOARD_PROXY_SCOPE` | Cliente y scopes OIDC. |
| `EDC_DASHBOARD_BASE_HREF` | Base path público del dashboard. |
| `EDC_SQL_SCHEMA_AUTOCREATE` | Autocreación de esquemas SQL EDC. |
| `EDC_VM_SINGLE_CONNECTOR_PUBLIC_PATH_PREFIX` | Prefijo público EDC en `vm-single`. |
| `EDC_VM_DISTRIBUTED_CONNECTOR_PUBLIC_PATH_PREFIX` | Prefijo público EDC en `vm-distributed`. |

## Variables runtime `PIONERA_*`

Estas variables se usan para ejecución puntual, CI o diagnóstico. No sustituyen
la documentación de `.config`, pero ayudan a no editar ficheros locales para una
prueba aislada.

| Variable | Para qué sirve |
| --- | --- |
| `PIONERA_ENVIRONMENT_PROFILE` | Selecciona perfil local `.profiles/<nombre>.env`. |
| `PIONERA_SECRETS_FILE` | Ruta alternativa de secretos locales. |
| `PIONERA_AUTO_LOAD_SECRETS` | Activa o desactiva carga automática de secretos locales. |
| `PIONERA_ADAPTER`, `PIONERA_TOPOLOGY` | Adapter y topología efectivos para procesos hijos o validaciones. |
| `PIONERA_VALIDATION_MODE` o `LEVEL6_VALIDATION_MODE` | Modo de validación: `auto`, `stable` o `fast`. |
| `PIONERA_LEVEL6_RUN_KAFKA` | Activa Kafka en Nivel 6 no interactivo. |
| `PIONERA_LEVEL6_SKIP_KAFKA` | Omite Kafka en Nivel 6. |
| `PIONERA_SYNC_HOSTS` | Permite aplicar entradas de `hosts`. |
| `PIONERA_HOSTS_FILE` | Fichero `hosts` que se puede actualizar. |
| `PIONERA_HOSTS_ADDRESS` | Dirección para entradas de hosts en una ejecución. |
| `PIONERA_SUDO_PASSWORD`, `PIONERA_SSH_PASSWORD` | Contraseñas locales para prompts automatizados; deben ir en `.secrets/`, no en Git. |
| `PIONERA_LOCAL_ADAPTER_SWITCH_CONFIRM` | Confirmación explícita para cambio local de adapter. |
| `PIONERA_VM_SINGLE_CLUSTER_SWITCH_CONFIRM` | Confirmación explícita para cambio de runtime en `vm-single`. |
| `PIONERA_RECREATE_DATASPACE_CONFIRM` | Confirmación explícita para recrear dataspace. |
| `PIONERA_VERBOSE_COMMANDS` | Muestra comandos completos en logs cuando se necesita diagnóstico. |
| `PIONERA_USE_DEPLOYER_VALIDATE`, `PIONERA_DISABLE_DEPLOYER_VALIDATE` | Fuerza o desactiva la ruta de validación del deployer. |
| `PIONERA_USE_DEPLOYER_METRICS`, `PIONERA_DISABLE_DEPLOYER_METRICS` | Fuerza o desactiva métricas del deployer. |
| `PIONERA_USE_DEPLOYER_DEPLOY`, `PIONERA_DISABLE_DEPLOYER_DEPLOY` | Fuerza o desactiva despliegue por deployer. |
| `PIONERA_LOCAL_STABILITY_*` | Ajusta comprobaciones de estabilidad local antes/después de Nivel 6. |
| `PIONERA_EDC_*` | Overrides runtime de imágenes, dashboard, build y readiness EDC. |
| `PIONERA_INESDATA_*` | Overrides runtime de imágenes y readiness INESData. |

En general, cualquier clave de `.config` puede probarse como override temporal
con prefijo `PIONERA_`. Ejemplo: `VM_EXTERNAL_IP` puede sobrescribirse con
`PIONERA_VM_EXTERNAL_IP`.

Ejemplo de ejecución puntual sin editar `.config`:

```bash
PIONERA_TOPOLOGY=vm-single \
PIONERA_VM_EXTERNAL_IP=192.0.2.10 \
PIONERA_INGRESS_EXTERNAL_IP=192.0.2.10 \
python3 main.py inesdata hosts --topology vm-single --dry-run
```

Ejemplo de Nivel 6 estable con Kafka:

```bash
PIONERA_VALIDATION_MODE=stable \
PIONERA_LEVEL6_RUN_KAFKA=true \
python3 main.py inesdata validate --topology local
```

## Variables en perfiles `.profiles/*.env`

Los perfiles son útiles para transportar configuración entre entornos, pero no
aceptan cualquier clave. El framework separa claves conocidas en:

| Grupo | Destino |
| --- | --- |
| Infraestructura | `deployers/infrastructure/deployer.config` |
| Topología | `deployers/infrastructure/topologies/<topology>.config` |
| Adapter | `deployers/<adapter>/deployer.config` |
| Metadatos | `PROFILE_NAME`, `PROFILE_TOPOLOGY`, `PROFILE_ADAPTER`, `ENVIRONMENT_NAME`, `ENVIRONMENT_LABEL` |

Si el perfil contiene una clave desconocida o sensible, el asistente falla antes
de escribir los `.config`. Para comprobar qué quedó activo, usa `W -> C`.

Ejemplo de perfil local sanitizado:

```ini
PROFILE_NAME=vm-distributed-demo
PROFILE_TOPOLOGY=vm-distributed
PROFILE_ADAPTER=inesdata
VM_COMMON_IP=192.0.2.10
VM_PROVIDER_IP=192.0.2.11
VM_CONSUMER_IP=192.0.2.12
VM_COMMON_PUBLIC_URL=https://common.example.org
VM_PROVIDER_PUBLIC_URL=https://provider.example.org
VM_CONSUMER_PUBLIC_URL=https://consumer.example.org
DS_1_NAME=pionera
DS_1_CONNECTORS=org2,org3
DS_1_CONNECTOR_NAMESPACES=org2:provider,org3:consumer
DS_1_VALIDATION_PAIRS=org2>org3
```

## Decisiones frecuentes

| Quiero... | Variables que normalmente reviso |
| --- | --- |
| Cambiar dominios públicos | `DOMAIN_BASE`, `DS_DOMAIN_BASE`, `VM_*_PUBLIC_URL`, `KEYCLOAK_FRONTEND_URL`, `COMPONENTS_PUBLIC_BASE_URL` |
| Añadir un conector | `DS_1_CONNECTORS`, `DS_1_CONNECTOR_NAMESPACES`, `DS_1_VALIDATION_PAIRS`, `LEVEL4_CONNECTOR_RECONCILIATION_MODE` |
| Usar una VM externa sin túneles | `VM_*_PUBLIC_URL`, `K3S_KUBECONFIG_*` si hay acceso aprobado, `VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT=false`, imágenes de registry |
| Congelar repositorios fuente | `*_SOURCE_REF`, preferiblemente con tag o commit |
| Usar imágenes publicadas | `*_IMAGE_REF` o `*_IMAGE_NAME` + `*_IMAGE_TAG`, `*_IMAGE_PULL_POLICY` |
| Activar Kafka en validación | `PIONERA_LEVEL6_RUN_KAFKA=true`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_CLUSTER_BOOTSTRAP_SERVERS` |
| Diagnosticar valores contradictorios | `W -> C`, `--dry-run`, `PIONERA_VERBOSE_COMMANDS=true` |

## Mantenimiento de esta referencia

Si se añade una variable nueva a una plantilla `.config.example`, debe añadirse
a este documento dentro de su familia. Para obtener el inventario bruto:

```bash
rg -n '^[A-Z][A-Z0-9_]*=' \
  deployers/infrastructure/deployer.config.example \
  deployers/infrastructure/topologies/*.config.example \
  deployers/inesdata/deployer.config.example \
  deployers/edc/deployer.config.example
```
