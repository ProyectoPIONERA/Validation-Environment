# 04. Flujo de Ejecución

## Flujo general desde `inesdata.py`

El repositorio está organizado en niveles secuenciales.

El flujo habitual es este:

1. `Level 1`: prepara el cluster local.
2. `Level 2`: despliega servicios comunes.
3. `Level 3`: despliega el dataspace base.
4. `Level 4`: despliega los conectores.
5. `Level 5`: despliega componentes opcionales.
6. `Level 6`: ejecuta la validación.

## Qué hace hoy `Level 6`

`Level 6` ejecuta la validación API del núcleo del dataspace.

El flujo actual es:

1. Comprueba que Newman está disponible.
2. Detecta los conectores desplegados en el cluster.
3. Verifica que hay al menos dos conectores.
4. Comprueba que el despliegue de conectores es válido.
5. Llama a `ValidationEngine.run_all_dataspace_tests(connectors)`.

## Qué hace `ValidationEngine`

`ValidationEngine` toma la lista de conectores y genera todas las parejas proveedor-consumidor.

Para cada pareja:

1. limpia entidades de prueba antiguas si hace falta
2. prepara variables de entorno para Newman
3. delega la ejecución real a `NewmanExecutor`

## Qué hace `NewmanExecutor`

`NewmanExecutor` ejecuta secuencialmente las seis colecciones core:

1. `01_environment_health.json`
2. `02_connector_management_api.json`
3. `03_provider_setup.json`
4. `04_consumer_catalog.json`
5. `05_consumer_negotiation.json`
6. `06_consumer_transfer.json`

Además:

- carga `validation/shared/api/common_tests.js`
- añade el script específico de cada colección desde `validation/core/tests/`

## Qué pasa con los componentes

Actualmente `Level 5` y `Level 6` están separados:

- `Level 5` despliega componentes opcionales
- `Level 6` sigue ejecutando solo la validación core

Es decir:

- hoy los componentes pueden desplegarse
- pero sus carpetas en `validation/components/` todavía no se ejecutan automáticamente

## Cómo se añadirán más pruebas más adelante

La evolución prevista, sin cambiar la estructura actual, es simple:

1. mantener `core` como validación obligatoria
2. añadir llamadas explícitas para validaciones de componentes
3. dejar `validation/ui/` para pruebas de interfaz cuando se activen

A día de hoy esa parte futura todavía no está conectada en el flujo normal.
