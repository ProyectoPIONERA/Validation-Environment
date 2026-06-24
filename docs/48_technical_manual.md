# Manual técnico

Este manual resume el uso del Validation Environment desde CLI y describe la
estructura principal del repositorio. Esta orientado a operacion tecnica,
reproduccion de experimentos, diagnostico y mantenimiento basico.

## Entrada CLI

La entrada canonica es `main.py`:

```bash
python3 main.py menu
python3 main.py list
python3 main.py <adapter> <command> --topology <topology>
```

Adapters soportados:

```text
inesdata
edc
```

Topologias soportadas:

```text
local
vm-single
vm-distributed
```

## Comandos principales

| Comando | Uso |
| --- | --- |
| `python3 main.py menu` | Abre el menu interactivo. |
| `python3 main.py list` | Lista adapters disponibles. |
| `python3 main.py <adapter> deploy --topology <topology>` | Ejecuta niveles de despliegue. |
| `python3 main.py <adapter> level <N> --topology <topology>` | Ejecuta un nivel concreto, de `1` a `6`. |
| `python3 main.py <adapter> validate --topology <topology>` | Ejecuta Nivel 6. |
| `python3 main.py <adapter> metrics --topology <topology>` | Ejecuta metricas o benchmarks. |
| `python3 main.py <adapter> run --topology <topology>` | Ejecuta despliegue y validacion como experimento. |
| `python3 main.py <adapter> hosts --topology <topology>` | Planifica o aplica entradas de `hosts`. |
| `python3 main.py <adapter> public-access --topology <topology>` | Revisa o reconcilia acceso publico. |
| `python3 main.py <adapter> ssh-access --topology vm-distributed` | Revisa acceso SSH de topologia distribuida. |
| `python3 main.py <adapter> local-repair --topology local` | Repara acceso local gestionado por el framework. |
| `python3 main.py <adapter> recreate-dataspace --topology <topology>` | Recrea el dataspace con confirmacion explicita. |
| `python3 main.py report <experiment_id>` | Genera o abre reporte de un experimento. |
| `python3 main.py compare <experiment_a> <experiment_b>` | Compara dos experimentos. |

## Opciones frecuentes

| Opcion | Uso |
| --- | --- |
| `--topology` | Selecciona `local`, `vm-single` o `vm-distributed`. |
| `--dry-run` | Previsualiza sin ejecutar despliegues o validaciones reales. |
| `--validation-mode` | Ajusta el modo de Nivel 6: `auto`, `stable` o `fast`. |
| `--kafka` | Activa benchmark Kafka en la fase de metricas. |
| `--baseline` | Marca el experimento como baseline. |
| `--confirm-dataspace` | Confirma operaciones destructivas sobre un dataspace. |
| `--with-connectors` | Recrea conectores tras recrear el dataspace. |
| `--recover-connectors` | Reinicia conectores durante `local-repair`. |
| `--json` | Imprime salida estructurada cuando el comando lo soporta. |

El modo `batch` usa `--plan`, `--secrets`, `--levels` y `--run` para ejecutar
planes locales. Los ficheros de secretos deben permanecer ignorados por Git.

## Ejemplos

```bash
python3 main.py inesdata level 6 --topology local
python3 main.py edc validate --topology vm-single
python3 main.py inesdata hosts --topology vm-distributed --dry-run
python3 main.py report experiment_YYYY-MM-DD_HH-MM-SS
```

## Escenario técnico de referencia de esta rama

Esta rama se mantiene como referencia operativa para `vm-distributed` con el
adapter `inesdata`. El manual técnico conserva la descripción general del
framework, pero las comprobaciones de cierre de esta rama deben interpretarse
en ese alcance: conectores INESData distribuidos, servicios comunes,
componentes y validación asociada.

Para EDC en `vm-distributed`, la referencia correspondiente es
`refactoring-vm-distributed-edc-ai`.

## Estructura del repositorio

| Ruta | Responsabilidad |
| --- | --- |
| `main.py` | CLI y menu interactivo. |
| `framework/` | Logica comun de validacion, metricas, Kafka, reportes y experimentos. |
| `adapters/` | Comportamiento especifico de INESData y EDC. |
| `deployers/` | Despliegue por niveles, charts, configuracion y servicios compartidos. |
| `validation/` | Colecciones Newman, Playwright, orquestacion de Nivel 6 y validacion de componentes. |
| `tests/` | Pruebas automatizadas del propio framework. |
| `docs/` | Documentacion publica y operativa. |
| `experiments/` | Salidas generadas por validaciones y metricas. No debe versionarse. |

## Mapa técnico de despliegue

El framework separa orquestacion, configuracion, despliegue y validacion:

| Capa | Ruta principal | Papel |
| --- | --- | --- |
| Entrada | `main.py` | Resuelve adapter/topologia, menu, batch, niveles, preflights y reportes. |
| Infraestructura | `deployers/infrastructure/` | Cluster, topologias, dominios, kubeconfig, SSH e Ingress. |
| Servicios compartidos | `deployers/shared/` | Servicios comunes, dataspace base y componentes reutilizables. |
| Adapter | `deployers/<adapter>/` y `adapters/<adapter>/` | Inventario, charts, fuentes y comportamiento especifico. |
| Validacion | `validation/` | Newman, Playwright, componentes, datasets, Kafka y Nivel 6. |
| Evidencia | `experiments/` | Salidas generadas por experimento. |

Para una vista mas detallada de fuentes de verdad, perfiles locales, batch y
VMs externas, usa [Mapa de configuracion y despliegue](./49_configuration_map.md).
Para consultar las familias de variables modificables, usa
[Referencia de variables de configuracion](./51_configuration_variables_reference.md).

## Configuracion

La configuracion comun vive en:

```text
deployers/infrastructure/deployer.config
deployers/infrastructure/topologies/<topology>.config
```

La configuracion especifica de adapter vive en:

```text
deployers/inesdata/deployer.config
deployers/edc/deployer.config
```

Los ficheros `.config` locales contienen rutas, dominios y datos propios del
entorno. No deben subirse a Git. Si un valor es secreto, debe preferirse
`.secrets/*.env` o una variable de entorno gestionada fuera del repositorio. Las
plantillas versionables son los ficheros `.example`.

La referencia practica de variables, ubicacion recomendada y proposito esta en
[Referencia de variables de configuracion](./51_configuration_variables_reference.md).

La precedencia operativa es:

1. `.config.example` aporta valores base cuando no existe `.config`.
2. `deployers/infrastructure/deployer.config` define la base comun.
3. `deployers/infrastructure/topologies/<topology>.config` define overrides de
   topologia.
4. `deployers/<adapter>/deployer.config` define el dataspace, conectores y
   componentes del adapter.
5. Las variables `PIONERA_*` sobrescriben valores durante la ejecucion.

Los perfiles `.profiles/*.env` no se leen como configuracion efectiva hasta que
se aplican. Al aplicarse desde `W -> 1` o desde `batch` con `profile:`, escriben
valores en los `.config` correspondientes. Los planes batch pueden vivir en
`.profiles/runs/*.yaml`; si se versionan, deben estar sanitizados y no contener
secretos.

En `vm-distributed`, revisa siempre los valores efectivos con:

```text
W - vm-distributed assistant
C - Show effective configuration values and sources
```

Ese visor ayuda a detectar contradicciones entre `.config`, `.profiles` y
variables `PIONERA_*` antes de ejecutar niveles.

## VM externa y redes restringidas

Si las politicas de red de las organizaciones implicadas no autorizan tuneles
hacia una VM externa, no se deben configurar kubeconfigs que dependan de
port-forwarding SSH hacia esa VM. Las rutas tecnicas viables son:

| Opcion | Condicion |
| --- | --- |
| Ejecutar el framework desde un host con acceso aprobado a todas las VMs | El host alcanza SSH o Kubernetes API de cada rol. |
| Usar un registry compartido | El cluster externo puede descargar las imagenes sin importacion remota por SSH. |
| Delegar el despliegue externo | La organizacion externa despliega su conector y expone endpoints publicos acordados. |
| Usar kubeconfigs directos o VPN aprobada | La politica permite acceso Kubernetes sin tunel local. |

El framework puede validar la interoperabilidad por endpoints publicos aunque
un conector externo no haya sido desplegado directamente por la misma ejecucion,
siempre que los contratos de URL, catalogo, negociacion y transferencia sean
coherentes.

## Niveles técnicos

| Nivel | Responsabilidad |
| --- | --- |
| `1` | Preparacion de cluster. |
| `2` | Servicios comunes. |
| `3` | Dataspace y control plane. |
| `4` | Conectores. |
| `5` | Componentes y fuentes auxiliares. |
| `6` | Validacion, metricas y evidencias. |

## Evidencia y alcance

El Nivel 6 puede ejecutar limpieza segura, Newman/Postman, Playwright,
validaciones de componentes, Kafka cuando se habilita, metricas y reportes. Los
resultados se guardan bajo `experiments/`.

Para cierre documental, no basta con que exista un comando o una opcion de
menu. Una combinacion de adapter y topologia debe tener un experimento
reproducible con reporte, metricas, logs y artefactos asociados.
