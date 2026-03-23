# Validacion UI con Playwright

Esta carpeta contiene la capa UI de validacion para INESData. Los tests se derivan de los flujos reales ya cubiertos por Newman y actualmente cubren:

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
- `playwright.config.ts`: configuracion de ejecucion y reporters.
- `playwright.ops.config.ts`: configuracion separada para suites opcionales de operaciones.

## Preparacion

1. Copia `.env.example` a `.env`.
2. Elige uno de estos modos de runtime:
   - `single-portal`: ajusta `PORTAL_BASE_URL`, `PORTAL_USER` y `PORTAL_PASSWORD`
   - `connector-aware`: ajusta `UI_PORTAL_CONNECTOR` o `UI_PORTAL_ROLE`, y para flujos de dataspace `UI_PROVIDER_CONNECTOR` y `UI_CONSUMER_CONNECTOR`
3. Opcional: cambia `PORTAL_TEST_FILE_MB` o `PORTAL_TEST_OBJECT_PREFIX`.

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

Smoke usado por `inesdata.py` Level 6:

```bash
cd validation/ui
npx playwright test core/01-login-readiness.spec.ts core/04-consumer-catalog.spec.ts
```

Suite ops opcional para visibilidad de buckets en MinIO Console:

```bash
cd validation/ui
npm run test:ops
```

Para ejecutarla también desde `inesdata.py` Level 6, exporta:

```bash
export LEVEL6_RUN_UI_OPS=true
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

Por defecto los artefactos se guardan en:

- `validation/ui/test-results`
- `validation/ui/playwright-report`
- `validation/ui/blob-report`

Cuando la ejecucion llega desde `inesdata.py` Level 6, esos directorios se redirigen automaticamente a `experiments/<experiment_id>/ui/<connector>/`.

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
- `UI_MINIO_CONSOLE_URL`
- `UI_MINIO_PROVIDER_BUCKET`
- `UI_MINIO_CONSUMER_BUCKET`
- `UI_MINIO_PROVIDER_EXPECT_OBJECT`
- `UI_MINIO_CONSUMER_EXPECT_OBJECT`
