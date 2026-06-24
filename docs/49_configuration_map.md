# Mapa de configuración y despliegue

Este documento explica cómo está construido el framework desde el punto de
vista de configuración operativa. Su objetivo es reducir ambigüedades al adaptar
el Validation Environment a otro contexto, por ejemplo a un entorno con varias
VMs, redes separadas, restricciones de túneles o conectores gestionados por
organizaciones distintas.

## Lectura rápida

La regla principal es:

1. Los deployers leen los ficheros `.config` locales.
2. Los ficheros `.profiles/*.env` son entradas locales que pueden escribir
   valores en esos `.config`.
3. Las variables `PIONERA_*` sirven para sobrescribir valores durante una
   ejecución concreta.
4. Los secretos viven en `.secrets/*.env` o en el entorno de ejecución, nunca en
   Git ni en `docs/`.

Por tanto, antes de desplegar hay que comprobar siempre los valores efectivos
con el asistente `W -> C` o con una previsualización `--dry-run`.

La lista organizada de variables modificables, su propósito y el fichero donde
conviene ajustarlas está en
[Referencia de variables de configuración](./51_configuration_variables_reference.md).

## Piezas principales del framework

| Ruta | Papel en despliegue y validación |
| --- | --- |
| `main.py` | Entrada CLI, menú interactivo, ejecución por niveles, batch, asistentes y preflights. |
| `framework/` | Lógica común de experimentos, métricas, evidencias, reportes, Kafka y utilidades compartidas. |
| `deployers/infrastructure/` | Configuración base de infraestructura, topologías y preparación de clúster. |
| `deployers/shared/` | Servicios comunes, dataspace base, charts compartidos y componentes reutilizables. |
| `deployers/inesdata/` | Configuración, charts y despliegue del adapter INESData. |
| `deployers/edc/` | Configuración, charts y despliegue del adapter EDC. |
| `adapters/inesdata/` | Integración del adapter INESData con el framework y fuentes externas necesarias. |
| `adapters/edc/` | Integración del adapter EDC, dashboard, conector y fuentes importadas. |
| `validation/` | Suites Newman, Playwright, validación de componentes, datasets y orquestación de Nivel 6. |
| `tests/` | Pruebas automatizadas del propio framework. |
| `docs/` | Documentación estable, manuales, runbooks y trazabilidad pública. |
| `experiments/` | Evidencias generadas por ejecuciones. No se versiona. |

## Fuentes de verdad

### `.config`

Los `.config` locales son la fuente efectiva para el despliegue. Son los
ficheros que leen los deployers cuando se ejecutan niveles.

| Fichero | Qué controla |
| --- | --- |
| `deployers/infrastructure/deployer.config` | Base común: dominio, servicios compartidos y claves de infraestructura aplicables a más de una topología. |
| `deployers/infrastructure/topologies/local.config` | Overrides de topología local. |
| `deployers/infrastructure/topologies/vm-single.config` | Overrides de una VM. |
| `deployers/infrastructure/topologies/vm-distributed.config` | Roles distribuidos, URLs públicas, kubeconfigs, SSH, estrategia de imágenes y routing. |
| `deployers/inesdata/deployer.config` | Dataspace, conectores, componentes y opciones propias de INESData. |
| `deployers/edc/deployer.config` | Dataspace, conectores, componentes y opciones propias de EDC. |

Los `.config.example` son plantillas versionadas. Los `.config` reales se
generan o editan localmente y están ignorados por Git.

### `.profiles`

Los perfiles locales están en `.profiles/*.env`. No son la configuración que
lee directamente el despliegue. Son una forma de preparar o transportar valores
entre entornos de trabajo.

Un perfil se puede aplicar de dos formas:

- desde el asistente `W -> P` y `W -> 1`;
- desde un plan batch con `profile:` o `profile_path:`.

Al aplicarse, el framework separa las claves por destino y actualiza:

```text
deployers/infrastructure/deployer.config
deployers/infrastructure/topologies/<topology>.config
deployers/<adapter>/deployer.config
```

El perfil rechaza claves sensibles por nombre, por ejemplo claves que incluyan
`PASSWORD`, `TOKEN`, `SECRET`, `PRIVATE_KEY`, `UNSEAL` o `ROOT_KEY`. Si un valor
es secreto, debe ir en `.secrets/*.env` o en el entorno de ejecución.

### Planes batch

Los planes batch suelen vivir en `.profiles/runs/*.yaml`. Definen qué adapter,
topología, niveles y variables temporales se ejecutan. También pueden aplicar un
perfil antes de lanzar los niveles.

Un plan batch no debe contener contraseñas, tokens, cookies, claves privadas ni
kubeconfigs reales. Si se decide versionar un plan, debe revisarse como
documentación operativa pública.

### Variables `PIONERA_*`

Las variables `PIONERA_*` tienen prioridad durante la ejecución. Sirven para
CI/CD, pruebas puntuales o ejecución no interactiva.

Ejemplo conceptual:

```bash
PIONERA_VM_EXTERNAL_IP=192.0.2.10 python3 main.py inesdata hosts --topology vm-single --dry-run
```

Las variables sin prefijo que aparecen en `.config`, por ejemplo
`VM_EXTERNAL_IP`, son claves internas de configuración. Para sobrescribirlas
desde el shell se prefiere la forma pública `PIONERA_VM_EXTERNAL_IP`.

### Secretos

Los secretos locales pueden cargarse desde `.secrets/pionera.env` o desde el
entorno de ejecución. Estos ficheros están ignorados por Git.

Ejemplos de valores que no deben estar en `.profiles`, `.config.example` ni
`docs/`:

- contraseñas de `sudo` o SSH;
- tokens de API;
- cookies de sesión;
- claves privadas;
- kubeconfigs reales;
- certificados privados.

## Qué modificar según la necesidad

| Necesidad | Fichero o mecanismo recomendado |
| --- | --- |
| Cambiar adapter activo | Menú `S` o argumento CLI `<adapter>`. |
| Cambiar topología | Menú `T` o `--topology`. |
| Configurar dominios base | `.config` de infraestructura/topología: `DOMAIN_BASE`, `DS_DOMAIN_BASE`. |
| Definir URLs públicas explícitas | `VM_COMMON_PUBLIC_URL`, `VM_PROVIDER_PUBLIC_URL`, `VM_CONSUMER_PUBLIC_URL`, `KEYCLOAK_FRONTEND_URL`, `COMPONENTS_PUBLIC_BASE_URL`. |
| Definir VMs y roles | `deployers/infrastructure/topologies/vm-distributed.config`. |
| Definir kubeconfigs por rol | `K3S_KUBECONFIG_COMMON`, `K3S_KUBECONFIG_PROVIDER`, `K3S_KUBECONFIG_CONSUMER`, `K3S_KUBECONFIG_COMPONENTS`. |
| Configurar SSH | `SSH_ACCESS_MODE`, `SSH_IDENTITY_FILE`, `VM_<ROLE>_SSH_HOST`, `VM_<ROLE>_SSH_USER` y variantes de bastión. |
| Publicar imágenes por registry | Variables de imagen del componente o adapter, más `*_IMAGE_PULL_POLICY`. |
| Usar importación remota de imágenes | `VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT=true` y variables asociadas, solo si SSH y permisos lo permiten. |
| Cambiar inventario de conectores | `DS_1_CONNECTORS`, `DS_1_CONNECTOR_NAMESPACES`, `DS_1_VALIDATION_PAIRS`. |
| Añadir conectores sin recrear los sanos | `LEVEL4_CONNECTOR_RECONCILIATION_MODE=additive`. |
| Validar AI Model Hub con modelos reales | Variables `AI_MODEL_HUB_*` y asistente `W -> 10` cuando aplique. |
| Ejecutar sin interacción | Plan batch con `--plan` y secretos locales con `--secrets`. |

## Uso recomendado de `W`

El asistente `W - vm-distributed assistant` es la ruta recomendada para entornos
distribuidos o con dudas de configuración.

| Opción | Cuándo usarla |
| --- | --- |
| `P` | Seleccionar el perfil local que servirá como entrada de configuración. |
| `1` | Crear o actualizar los `.config` locales a partir del perfil y del asistente. |
| `C` | Ver valores efectivos y la fuente de cada valor antes de desplegar. |
| `2` | Revisar topología configurada y preflight estático. |
| `3` | Previsualizar despliegue y entradas de `hosts`. |
| `4` | Ejecutar comprobaciones SSH/HTTP no destructivas. |
| `5` | Obtener comandos manuales para revisión externa. |
| `6` | Preparar acceso SSH dedicado cuando la política lo permita. |
| `8` | Preparar kubeconfigs locales para k3s cuando proceda. |
| `10` | Preparar demo de casos de uso de AI Model Hub cuando el adapter lo soporte. |

La opción `C` debe usarse antes de cualquier despliegue en un contexto nuevo,
porque muestra si un valor viene de `.config`, de una plantilla, de un override
`PIONERA_*` o de un valor por defecto.

## Topologías

### `local`

Usa Minikube en la estación operadora. Requiere Docker Desktop en Windows/WSL y
normalmente `minikube tunnel` para exponer Ingress.

Fichero principal:

```text
deployers/infrastructure/topologies/local.config
```

### `vm-single`

Usa una VM con Kubernetes/k3s. El framework puede operar desde la propia VM o
desde una estación con acceso aprobado a la VM.

Fichero principal:

```text
deployers/infrastructure/topologies/vm-single.config
```

### `vm-distributed`

Separa roles de infraestructura. Puede representar:

- un clúster Kubernetes lógico con varios nodos;
- varios clústeres k3s accesibles con kubeconfigs por rol;
- una combinación donde algunos conectores se despliegan fuera del entorno
  principal, si existe una ruta de operación aprobada.

Fichero principal:

```text
deployers/infrastructure/topologies/vm-distributed.config
```

Roles habituales:

| Rol | Uso |
| --- | --- |
| `common` | Servicios comunes y control del dataspace. |
| `provider` | Conectores del lado proveedor o primer grupo de validación. |
| `consumer` | Conectores del lado consumidor o segundo grupo de validación. |
| `components` | Componentes compartidos, si usan contexto propio. |

## VM externa sin túneles

Si las políticas de red de las organizaciones implicadas no autorizan túneles
hacia una VM externa, el framework no debe depender de port-forwarding SSH para
operar esa VM. Esto no impide necesariamente el despliegue, pero cambia la
estrategia.

Para desplegar un conector en una VM externa se necesita al menos una de estas
rutas de operación:

1. La estación que ejecuta el framework tiene acceso aprobado al Kubernetes API
   o al SSH de la VM externa.
2. El framework se ejecuta desde una máquina que sí puede llegar a todas las VMs
   implicadas.
3. La organización externa despliega su propio conector con una configuración
   acordada y se integra por endpoints públicos.
4. Las imágenes se publican en un registry accesible por el clúster externo, sin
   importación remota por SSH.

En un escenario con varias VMs dentro de una red controlada y una VM externa, las
opciones defendibles son:

| Opción | Viabilidad | Requisitos |
| --- | --- | --- |
| Ejecutar el framework desde un host con acceso aprobado a las tres VMs | Alta si la red lo permite | SSH o Kubernetes API directo, DNS/HTTPS público y kubeconfigs válidos. |
| Despliegue dividido por organización | Alta cuando no hay túneles | La organización que opera el entorno principal despliega su parte y la organización externa despliega su conector; la validación usa endpoints públicos. |
| Registry compartido | Alta para imágenes | Las imágenes se publican en un registry que pueda leer el clúster externo. |
| Túnel SSH a la VM externa | No viable si la política no lo autoriza | Solo debe usarse cuando esté permitido formalmente. |

En estos casos conviene fijar explícitamente:

```ini
VM_PROVIDER_PUBLIC_URL=https://<url-publica-provider>
VM_CONSUMER_PUBLIC_URL=https://<url-publica-consumer>
VM_DISTRIBUTED_REMOTE_IMAGE_IMPORT=false
```

Y usar referencias de imagen accesibles por registry, por ejemplo las variables
`AI_MODEL_HUB_IMAGE_REF`, `AI_MODEL_HUB_MODEL_SERVER_IMAGE` o las variables de
imagen del adapter correspondiente.

El despliegue no es viable desde el framework si se cumplen todas estas
condiciones a la vez:

- nadie con permiso puede ejecutar `kubectl` o `helm` contra el clúster externo;
- no existe registry accesible para entregar imágenes;
- la VM externa no expone endpoints públicos o privados alcanzables por los
  demás participantes;
- la política impide túneles y tampoco existe una alternativa de operación
  autorizada.

## Flujo para adaptar el framework a un contexto propio

1. Elegir topología y adapter: `local`, `vm-single` o `vm-distributed`; `inesdata`
   o `edc`.
2. Copiar o generar los `.config` locales desde sus `.config.example`.
3. Si se quiere reutilizar una plantilla local, crear `.profiles/<nombre>.env`
   sin secretos.
4. Aplicar el perfil con `W -> P` y `W -> 1`, o mediante un plan batch.
5. Revisar `W -> C` para confirmar valores efectivos y fuentes.
6. Ejecutar `W -> 2` y corregir valores faltantes.
7. Ejecutar `W -> 3` para revisar plan de despliegue y hosts.
8. Ejecutar `W -> 4` solo si la política permite las comprobaciones SSH/HTTP.
9. Ejecutar el nivel necesario con `--dry-run` cuando exista duda.
10. Ejecutar niveles en orden y conservar evidencias bajo `experiments/`.

## Evitar ambigüedades

- No edites artefactos generados bajo `deployers/*/deployments/`.
- No mezcles valores de `local`, `vm-single` y `vm-distributed` en el mismo
  `.config` si el valor depende de topología.
- No uses `.profiles/*.env` como almacén de secretos.
- No cites una combinación adapter/topología como validada si no existe un
  experimento reproducible asociado.
- No uses túneles hacia VMs externas si la política de red no los permite.
- Antes de depurar un fallo de despliegue, comprueba `W -> C`: muchas
  incidencias vienen de un valor efectivo distinto al que se esperaba.
