# 05. Estructura del Repositorio

## Mapa rápido

```text
integration_pionera/
  adapters/
  docs/
  framework/
  inesdata-deployment/
  tests/
  validation/
  inesdata.py
  main.py
```

## `validation/`

Aquí viven los artefactos de prueba.

### `validation/core/`

Contiene la validación activa del núcleo del dataspace.

- `collections/`: colecciones Postman ejecutadas con Newman
- `tests/`: scripts JS específicos por colección

### `validation/components/`

Contiene validaciones específicas por componente.

Hoy existen estas carpetas:

- `ontology_hub/`
- `ai_model_hub/`
- `semantic_virtualization/`

Estado actual:

- `ontology_hub/` es una implementación activa de referencia con validación API y UI.
- `ai_model_hub/` ya existe como base de Fase 3 con `README.md`, `test_cases.yaml` y trazabilidad PT5, pero aún no tiene runners activos.
- `semantic_virtualization/` sigue siendo estructura reservada.
- `Level 6` puede ejecutar automáticamente validaciones de componente cuando el componente está configurado y existe runner registrado.

### `validation/shared/`

Contiene utilidades compartidas por las pruebas en:

- `validation/shared/api/common_tests.js`

### `validation/ui/`

Contiene la validación UI del dataspace core con Playwright:

- `package.json`
- `playwright.config.ts`
- `README.md`
- `core/`
- `ops/`
- `components/`
- `shared/`

Sí forma parte del framework actual:

- `Level 6` ejecuta un smoke UI estable por conector
- ejecuta la suite `ops` de MinIO Console cuando existe, salvo opt-out explicito
- guarda sus artefactos dentro del experimento activo

## `framework/`

Aquí vive la lógica reutilizable del sistema.

Archivos importantes para nuevos desarrolladores de validación:

- `validation_engine.py`: coordina la validación entre pares de conectores
- `newman_executor.py`: ejecuta las colecciones con Newman
- `experiment_storage.py`: guarda resultados y artefactos

## `adapters/`

Aquí vive la lógica específica del ecosistema soportado.

En este proyecto, el adapter activo es:

- `adapters/inesdata/`

### `adapters/inesdata/sources/`

Aquí viven las fuentes locales del conector, de la interfaz y del portal.

Es la zona importante cuando un componente se integra como extensión.

Subdirectorios destacados:

- `inesdata-connector/`
- `inesdata-connector/extensions/`
- `inesdata-connector-interface/`
- `inesdata-public-portal-frontend/`
- `inesdata-public-portal-backend/`

## `inesdata-deployment/`

Aquí están los charts y values Helm usados por el entorno local:

- `common/`: servicios base
- `dataspace/`: despliegue base del dataspace
- `connector/`: chart del conector
- `components/`: componentes opcionales desplegados como servicios

Actualmente el ejemplo real de componente API-based es:

- `inesdata-deployment/components/ontology-hub/`

## `tests/`

Contiene tests automatizados del propio framework.

No es la carpeta de validación funcional del dataspace. Esa responsabilidad está en `validation/`.

## `docs/`

Contiene la documentación vigente compartida con los desarrolladores.

Empieza por:

- `README.md`
- `00_overview.md`
- `01_framework_architecture.md`
- `03_integration_guide.md`
- `04_execution_flow.md`
- `06_information_exchange_flow.md`

Y continúa con la serie de evolución del sistema:

- `07_experiment_system.md`
- `08_metrics_pipeline.md`
- `09_kafka_real_measurements.md`
- `10_ui_validation_core.md`
