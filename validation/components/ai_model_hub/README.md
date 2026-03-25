# AI Model Hub Validation

Esta carpeta inicia la adecuacion de `AI Model Hub` al patron de validacion por componente del framework, pero todavia **no activa** su ejecucion en `Level 6`.

El objetivo de esta fase es dejar preparada la base metodologica para `E5.2`:

- catalogo PT5 normalizado
- trazabilidad con `E4.1`
- criterio de madurez por caso
- identificacion de la primera ola de automatizacion

## Estado Actual

En esta fase ya existen:

- `validation/components/ai_model_hub/test_cases.yaml`
- `validation/components/ai_model_hub/__init__.py`
- `validation/components/ai_model_hub/runner.py`
- `validation/components/ai_model_hub/component_runner.py`
- `validation/components/ai_model_hub/ui_runner.py`
- `validation/components/ai_model_hub/ui/`

Todavia **no** existen:

- registro en `validation/components/runner.py`

Por tanto:

- no afecta a la ejecucion actual de `Level 6`
- no introduce nuevos componentes por defecto
- no modifica el baseline estable de `Ontology Hub`
- permite ejecutar comprobaciones bootstrap de forma opt-in y con el mismo contrato de salida general del framework
- permite activar una primera capa Playwright de forma opt-in mediante `AI_MODEL_HUB_ENABLE_UI_VALIDATION=1`

## Fuentes

La base normativa y tecnica usada para esta fase es:

- `docs_/logs/components/ai-model-catalog/PIONERA E4.1 - final.docx`
- `docs_/logs/validation/casos_prueba_extraidos.tsv`
- `docs_/fase-4-analisis-componentes.md`
- `docs_/fase-7-diseno-tests-componentes.md`
- el repositorio local `AIModelHub/`

## Criterio de Trabajo

El catalogo local distingue:

- `test_cases`: casos oficiales PT5 del componente
- `support_checks`: comprobaciones auxiliares

Cada caso puede declarar:

- `validation_type`
- `dataspace_dimension`
- `execution_mode`
- `coverage_status`
- `mapping_status`

Esto permite representar honestamente si un caso esta:

- listo para automatizar
- cubierto solo de forma manual
- bloqueado por dependencias de integracion

## Primera Ola Recomendada

Los mejores candidatos para la primera automatizacion del framework son:

- `PT5-MH-01` acceso al catalogo
- `PT5-MH-02` registro local de modelo
- `PT5-MH-03` publicacion federada
- `PT5-MH-04` listado de modelos
- `PT5-MH-05` busqueda global
- `PT5-MH-06` filtros avanzados
- `PT5-MH-07` ficha del modelo
- `PT5-MH-08` creacion de contrato

Motivo:

- estan bien sustentados por `E4.1`
- tienen flujo UI comprensible
- son los casos que mejor encajan con una automatizacion temprana sin exigir comparacion, benchmarking o identidad avanzada

## Uso de AIModelHub Standalone

El repositorio local `AIModelHub/` puede utilizarse como entorno de **preintegracion** para:

- descubrir flujos reales
- identificar selectores estables
- preparar datasets y modelos demo
- entender el ciclo contractual y de catalogo

Pero no debe confundirse con la evidencia final del framework porque:

- es un prototipo de investigacion
- sus pruebas Cypress actuales dependen mucho de mocks
- su topologia local no equivale todavia al despliegue final del framework PT5

La validacion final de `E5.2` debe ejecutarse dentro de `Validation-Environment`.

## Siguiente Paso Tecnico

La primera capa UI ya esta preparada en modo opt-in para:

- `PT5-MH-01`
- `PT5-MH-04`
- `PT5-MH-05`
- `PT5-MH-06`

Los siguientes pasos recomendados son:

1. ampliar la suite UI hacia `PT5-MH-02`, `PT5-MH-03`, `PT5-MH-07` y `PT5-MH-08`
2. estabilizar datos demo y contratos para que la automatizacion deje de ser `partial`
3. registrar el componente de forma opt-in en `validation/components/runner.py`, no por defecto
