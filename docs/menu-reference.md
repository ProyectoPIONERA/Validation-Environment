# Referencia del Menú

El menú guiado se abre con:

```bash
python3 main.py menu
```

El menú está en inglés para alinearse con nombres de comandos, código y artefactos técnicos. Esta guía explica cuándo usar cada opción.

## Encabezado

El encabezado muestra:

- `Active adapter`: adapter seleccionado para las acciones del menú.
- `Available adapters`: adapters disponibles, normalmente `edc` e `inesdata`.

Si una acción depende del adapter, se ejecutará sobre el adapter activo.

## Full Deployment

`0 - Run All Levels (1-6) sequentially`

Usa esta opción para un despliegue completo desde cero o para reconstruir todo el entorno en orden. Ejecuta preparación de cluster, servicios comunes, dataspace, conectores, componentes y validación.

## Individual Levels

`1 - Level 1: Setup Cluster`

Prepara el cluster base. En `local`, esta ruta usa Minikube.

`2 - Level 2: Deploy Common Services`

Despliega o actualiza servicios comunes como Keycloak, MinIO, PostgreSQL y Vault.

`3 - Level 3: Deploy Dataspace`

Despliega el runtime base del dataspace y el registration service.

`4 - Level 4: Deploy Connectors`

Despliega los conectores del adapter activo. En `inesdata`, despliega conectores INESData. En `edc`, despliega conectores EDC.

`5 - Level 5: Deploy Components`

Despliega componentes opcionales configurados, como Ontology Hub o AI Model Hub cuando correspondan al adapter y configuración activos.

`6 - Level 6: Run Validation Tests`

Ejecuta la validación integral del adapter activo. Puede incluir limpieza previa, Newman, checks de almacenamiento, Playwright, componentes y métricas según el perfil de validación.

## Operations

`S - Select adapter`

Cambia el adapter activo. Úsalo para alternar entre `inesdata` y `edc` antes de desplegar, validar o planificar hosts.

`P - Preview deployment plan`

Muestra un plan de despliegue sin modificar el entorno. Úsalo antes de ejecutar cambios destructivos o cuando quieras revisar dataspace, conectores, componentes, namespaces y hosts esperados.

`H - Plan/apply hosts entries`

Planifica o aplica entradas del fichero `hosts`. Por defecto solo planifica. Para aplicar cambios debes habilitar sincronización explícita con `PIONERA_SYNC_HOSTS=true` y `PIONERA_HOSTS_FILE`.

`M - Run metrics (Kafka optional)`

Ejecuta métricas sobre el adapter activo. El benchmark Kafka es opcional y los resultados se guardan en `experiments/`.

## More

`T - Tools`

Abre herramientas locales de soporte.

`U - UI Validation`

Abre suites UI específicas para portales y componentes.

## Tools

`1 - Bootstrap Framework Dependencies`

Instala o repara dependencias del framework. Úsalo en una máquina limpia o tras problemas de dependencias; en Linux/WSL también prepara las dependencias de sistema necesarias para Playwright.

`2 - Run Framework Doctor`

Ejecuta checks de preparación local. Úsalo antes de desplegar o para diagnosticar fallos de entorno.

`3 - Recover Connectors After WSL Restart`

Recupera acceso local tras reiniciar WSL cuando los recursos del cluster siguen desplegados pero el acceso local queda roto.

`4 - Cleanup Workspace`

Limpia artefactos generados, caches o salidas previas que dificultan razonar sobre el estado actual.

`5 - Build and Deploy Local Images`

Construye y carga imágenes locales. Úsalo durante desarrollo cuando hayas modificado código fuente de conectores, dashboards o componentes que deban probarse en el cluster.

`6/X - Recreate Dataspace`

Destruye y recrea el dataspace seleccionado preservando servicios comunes. Requiere escribir el nombre exacto del dataspace. Invalida conectores de nivel 4 y permite recrearlos inmediatamente si se confirma.

`B - Back`

Vuelve al menú principal.

## UI Validation

`1 - INESData Tests (Normal/Live/Debug)`

Ejecuta validaciones UI del portal INESData de forma independiente del nivel 6 completo.

`2 - Ontology Hub Tests (Normal/Live/Debug)`

Ejecuta validaciones UI de Ontology Hub.

`3 - AI Model Hub Tests (Normal/Live/Debug)`

Ejecuta validaciones UI de AI Model Hub.

`B - Back`

Vuelve al menú principal.

## Control

`? - Help`

Muestra ayuda resumida dentro del propio menú.

`Q - Exit`

Sale del menú.

## Atajos Legacy

Los atajos legacy siguen funcionando aunque no se muestren como opciones principales:

```text
B  Bootstrap Framework Dependencies
D  Run Framework Doctor
R  Recover Connectors After WSL Restart
C  Cleanup Workspace
L  Build and Deploy Local Images
I  INESData UI tests
O  Ontology Hub UI tests
A  AI Model Hub UI tests
```

Estos atajos existen para compatibilidad durante la transición hacia `main.py`.

## Topología

La topología se selecciona por CLI con `--topology`:

```bash
python3 main.py inesdata deploy --topology local
python3 main.py edc hosts --topology vm-single --dry-run
```

Topologías canónicas:

```text
local
vm-single
vm-distributed
```

La opción visual `Topology` puede añadirse al menú cuando la selección interactiva de topología esté implementada. Mientras tanto, el menú usa la topología recibida por argumento o `local` por defecto.
