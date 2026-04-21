# 11. Validacion de Ontology Hub

Este documento resume como queda integrado `Ontology Hub` en el framework de
validacion. La referencia operativa detallada vive junto al codigo del
componente, pero este documento centraliza las rutas, el despliegue, las suites
y la trazabilidad PT5.

## Rutas Principales

| Elemento | Ruta |
| --- | --- |
| Suite funcional | `validation/components/ontology_hub/functional/` |
| Suite de integracion | `validation/components/ontology_hub/integration/` |
| Infraestructura Playwright compartida | `validation/components/ontology_hub/ui/` |
| Runner comun de componentes | `validation/components/runner.py` |
| Chart Helm | `deployers/shared/components/ontology-hub/` |
| Artefactos de experimentos | `experiments/.../components/ontology-hub/` |

## Despliegue

`Ontology Hub` se despliega como componente opcional de `Level 5`. En el modo
local actual, el chart fuente se mantiene en `deployers/shared/components` y
los valores runtime se resuelven desde el deployer activo.

| Propiedad | Valor habitual local |
| --- | --- |
| Namespace | `demo` o el namespace del dataspace activo |
| Release Helm | `<dataspace>-ontology-hub` |
| Host publico | `ontology-hub-<dataspace>.dev.ds.dataspaceunit.upm` |
| Servicio interno | `ClusterIP` en puerto `3333` |
| Dependencias | MongoDB y Elasticsearch |
| Imagen local | `ontology-hub:local` cuando se usa build local |

El chart puede inyectar `hostAliases` para que el hostname publico del
componente sea resoluble tambien desde dentro del pod. Esto evita fallos de
autoacceso del backend en operaciones como analisis de versiones.

## Puntos de Entrada

| URL | Uso |
| --- | --- |
| `http://ontology-hub-<dataspace>.dev.ds.dataspaceunit.upm/` | Home publica |
| `http://ontology-hub-<dataspace>.dev.ds.dataspaceunit.upm/dataset` | Catalogo publico |
| `http://ontology-hub-<dataspace>.dev.ds.dataspaceunit.upm/edition` | Area autenticada |
| `http://ontology-hub-<dataspace>.dev.ds.dataspaceunit.upm/edition/login` | Login |
| `http://ontology-hub-<dataspace>.dev.ds.dataspaceunit.upm/dataset/lov/api` | API historica del componente |

## Suites

La suite `functional/` valida el comportamiento observable del componente. Se
usa por defecto cuando `Level 6` ejecuta validacion de componentes.

La suite `integration/` conserva pruebas tecnicas y casos PT5 normalizados. Es
util para comprobar endpoints, estado interno y compatibilidad tecnica del
componente.

## Trazabilidad PT5

La trazabilidad se lee en tres capas:

| Capa | Papel |
| --- | --- |
| `A5.1_Funcionlidades_Ex.1` | Funcionalidades atomicas `OntHub-*` |
| `A5.1_Casos_Prueba_Ex.1` | Casos PT5 normalizados `PT5-OH-*` |
| Hoja `Ontology Hub` | Casos operativos detallados del componente |

La suite funcional modela los 27 casos operativos de la hoja `Ontology Hub`.
La numeracion tiene una excepcion historica: `OH-APP-00` cubre el caso `1`,
`OH-APP-01` cubre el caso `2` y no existe `OH-APP-02`.

| Caso hoja `Ontology Hub` | Automatizacion |
| --- | --- |
| `1` | `OH-APP-00` |
| `2` | `OH-APP-01` |
| `3` a `27` | `OH-APP-03` a `OH-APP-27` |

La cobertura PT5 se reparte entre `functional/` e `integration/`.

| Caso PT5 | Cobertura actual |
| --- | --- |
| `PT5-OH-01` | si |
| `PT5-OH-02` | si |
| `PT5-OH-03` | si |
| `PT5-OH-04` | si |
| `PT5-OH-05` | parcial |
| `PT5-OH-06` | no automatizada de forma funcional |
| `PT5-OH-07` | no explicita como asercion semantica RDF/OWL |
| `PT5-OH-08` | parcial |
| `PT5-OH-09` | si |
| `PT5-OH-10` | si |
| `PT5-OH-11` | parcial |
| `PT5-OH-12` | no explicita |
| `PT5-OH-13` | cubierta desde integracion, no desde funcional |
| `PT5-OH-14` | si, sustancial |
| `PT5-OH-15` | parcial |
| `PT5-OH-16` | no automatizada de forma funcional directa |

## Integracion Semantica con INESData

El framework integra la extension semantica del conector INESData de forma
selectiva:

- la interfaz del conector permite seleccionar vocabularios de `Ontology Hub`;
- el flujo detecta archivos RDF y lanza validacion semantica antes de crear el
  asset;
- el conector incluye la extension `ontology-validator`;
- `ONTOLOGY_URL` se genera desde el dataspace activo y se inyecta en
  `app.config.json`;
- las URLs `ontology-hub-<dataspace>.<dominio>` se traducen internamente a
  `http://<dataspace>-ontology-hub:3333`.

Las credenciales administrativas de `Ontology Hub` no se hardcodean en el
frontend. Cualquier flujo que necesite secretos debe resolverse mediante
configuracion segura o backend intermedio.
