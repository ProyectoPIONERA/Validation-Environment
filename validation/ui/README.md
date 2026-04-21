# Validacion UI con Playwright

Esta carpeta contiene la capa UI de validacion con Playwright.

Actualmente existen dos modos:

- `inesdata`: suite estable heredada del portal INESData
- `edc`: suite inicial del portal EDC con autenticacion `oidc-bff`

La suite `inesdata` sigue siendo la referencia principal y actualmente cubre:

- `01 login readiness`
- `03 provider setup` con creacion de asset y subida de fichero
- `03b provider policy creation`
- `03c provider contract definition creation`
- `04 consumer catalog` con listado y detalle
- `05 consumer negotiation`
- `06 consumer transfer`

## Estructura

- `core/`: specs principales que definen los flujos estables.
- `components/`: page objects reutilizables.
- `shared/fixtures/`: resolucion de runtime, autenticacion y evidencias.
- `tests/`: referencias legacy; la ejecucion activa se hace desde `core/`.
- `test_cases.yaml`: catalogo estable para los checks `support`, los casos de evidencia del dataspace y la suite ops.
- `reporting.py`: agregador que transforma el `results.json` de Playwright en un reporte enriquecido para `Level 6`.
- `playwright.config.ts`: configuracion de ejecucion y reporters.
- `playwright.edc.config.ts`: configuracion separada para la suite inicial del portal EDC.
- `playwright.ops.config.ts`: configuracion separada para suites opcionales de operaciones.

## Preparacion

1. Copia `.env.example` a `.env`.
2. Elige uno de estos modos de runtime:
   - `single-portal`: ajusta `PORTAL_BASE_URL`, `PORTAL_USER` y `PORTAL_PASSWORD`
   - `connector-aware`: ajusta `UI_PORTAL_CONNECTOR` o `UI_PORTAL_ROLE`, y para flujos de dataspace `UI_PROVIDER_CONNECTOR` y `UI_CONSUMER_CONNECTOR`
3. Si vas a ejecutar la suite `edc`, define al menos:
   - `UI_ADAPTER=edc`
   - `UI_DATASPACE=<dataspace edc>`
   - opcionalmente `UI_PROVIDER_CONNECTOR` y `UI_CONSUMER_CONNECTOR`
4. Opcional: cambia `PORTAL_TEST_FILE_MB` o `PORTAL_TEST_OBJECT_PREFIX`.

## Instalacion

```bash
cd validation/ui
npm install
npx playwright install
```

## Ejecucion

Suite core completa:

```bash
cd validation/ui
npm run test:e2e
```

Suite estable de `inesdata`:

```bash
cd validation/ui
npm run test:inesdata
```

Smoke suite inicial de `edc`:

```bash
cd validation/ui
UI_ADAPTER=edc \
UI_DATASPACE=demoedc \
UI_PROVIDER_CONNECTOR=conn-citycounciledc-demoedc \
UI_CONSUMER_CONNECTOR=conn-companyedc-demoedc \
npm run test:edc
```

La suite actual de `edc` cubre:

- `01 login readiness`
- `02 navigation smoke`
- `03 consumer negotiation`
- `04 consumer transfer`
- `05 consumer transfer storage` con validacion del objeto transferido en MinIO

Smoke usado por `main.py menu` Level 6:

```bash
cd validation/ui
npx playwright test core/01-login-readiness.spec.ts core/04-consumer-catalog.spec.ts
```

Suite dataspace usada por `main.py menu` Level 6 por defecto:

```bash
cd validation/ui
npx playwright test \
  core/03-provider-setup.spec.ts \
  core/03b-provider-policy-create.spec.ts \
  core/03c-provider-contract-definition-create.spec.ts \
  core/05-consumer-negotiation.spec.ts \
  core/06-consumer-transfer.spec.ts
```

Suite ops opcional para visibilidad de buckets en MinIO Console:

```bash
cd validation/ui
npm run test:ops
```

`Level 6` la ejecuta automáticamente cuando la suite existe en `validation/ui/ops`.

Para desactivarla explícitamente desde `main.py menu` Level 6, exporta:

```bash
export LEVEL6_RUN_UI_OPS=false
```

La opción interactiva `I > Core` también la ejecuta automáticamente al final del bloque smoke + dataspace, usando el mismo modo (`Normal`, `Live` o `Debug`).

En `Live` y `Debug`, el framework activa marcadores visuales sobre los elementos antes de `click`, `fill` y otras interacciones principales para que el recorrido sea más fácil de seguir.

Para omitir la suite dataspace desde `main.py menu` Level 6, exporta:

```bash
export LEVEL6_RUN_UI_DATASPACE=false
```

Solo provider setup:

```bash
cd validation/ui
npx playwright test core/03-provider-setup.spec.ts
```

Negociacion y transferencia:

```bash
cd validation/ui
npx playwright test core/05-consumer-negotiation.spec.ts core/06-consumer-transfer.spec.ts
```

Modo visible:

```bash
cd validation/ui
npm run test:e2e:headed
```

Modo visible `edc`:

```bash
cd validation/ui
UI_ADAPTER=edc \
UI_DATASPACE=demoedc \
UI_PROVIDER_CONNECTOR=conn-citycounciledc-demoedc \
UI_CONSUMER_CONNECTOR=conn-companyedc-demoedc \
npm run test:edc:headed
```

Modo debug:

```bash
cd validation/ui
npm run test:e2e:debug
```

## Evidencias

Cada flujo deja:

- video
- trace
- screenshots en hitos de negocio
- adjuntos JSON con datos del flujo cuando aplica

Los tests lanzados desde `main.py validate`, Level 6 o el menú interactivo activan por defecto marcadores visuales sobre los elementos antes de las interacciones principales (`click`, `fill`, `check`, `selectOption`, subida de ficheros). Esto facilita seguir el recorrido en modo `Live` y también en los vídeos generados en modo headless.

Las ejecuciones integradas usan una pausa corta de `150` ms por marcador para optimizar el tiempo total. Los modos `Live` y `Debug` usan `350` ms para que el recorrido sea más fácil de seguir visualmente.

Si ejecutas Playwright manualmente con `npx`, puedes activarlos así:

```bash
PLAYWRIGHT_INTERACTION_MARKERS=1 npx playwright test
```

Para desactivarlos explícitamente:

```bash
PLAYWRIGHT_INTERACTION_MARKERS=0 npx playwright test
```

Para ajustar la pausa del resaltado:

```bash
PLAYWRIGHT_INTERACTION_MARKER_DELAY_MS=500 npx playwright test
```

Por defecto los artefactos se guardan en:

- `validation/ui/test-results`
- `validation/ui/playwright-report`
- `validation/ui/blob-report`

Cuando la ejecucion llega desde `main.py menu` o desde la orquestación de Level 6, esos directorios se redirigen automaticamente a `experiments/<experiment_id>/ui/<connector>/`.
Ademas, tanto `Level 6` como la opcion interactiva `I > Core` guardan un JSON enriquecido por suite:

- `ui_core_validation.json`
- `ui_ops_validation.json`
- `ui_validation_summary.json` en la raiz del experimento
- `experiment_results.json` en la raiz del experimento

Estos artefactos separan `support_checks`, `dataspace_cases`, `ops_checks`, `evidence_index` y `catalog_alignment` sin cambiar la ejecucion nativa de Playwright.

## Variables de entorno

- `PORTAL_BASE_URL`
- `PORTAL_USER`
- `PORTAL_PASSWORD`
- `PORTAL_MANAGEMENT_BASE_URL`
- `PORTAL_SKIP_LOGIN`
- `PORTAL_TEST_FILE_MB`
- `PORTAL_TEST_OBJECT_PREFIX`
- `UI_PORTAL_CONNECTOR`
- `UI_PORTAL_ROLE`
- `UI_ADAPTER`
- `UI_DATASPACE`
- `UI_ENVIRONMENT`
- `UI_DS_DOMAIN`
- `UI_KEYCLOAK_URL`
- `UI_KEYCLOAK_CLIENT_ID`
- `UI_PROVIDER_CONNECTOR`
- `UI_CONSUMER_CONNECTOR`
- `PLAYWRIGHT_OUTPUT_DIR`
- `PLAYWRIGHT_HTML_REPORT_DIR`
- `PLAYWRIGHT_BLOB_REPORT_DIR`
- `PLAYWRIGHT_JSON_REPORT_FILE`
- `LEVEL6_RUN_UI_OPS`
- `LEVEL6_RUN_UI_DATASPACE`
- `UI_MINIO_CONSOLE_URL`
- `UI_MINIO_PROVIDER_BUCKET`
- `UI_MINIO_CONSUMER_BUCKET`
- `UI_MINIO_PROVIDER_EXPECT_OBJECT`
- `UI_MINIO_CONSUMER_EXPECT_OBJECT`
