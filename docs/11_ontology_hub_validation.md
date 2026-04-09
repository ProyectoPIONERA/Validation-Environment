# 11. Validación de Ontology Hub

## Objetivo

Este documento centraliza la referencia documental de `Ontology Hub` dentro del
framework y, además, recoge la trazabilidad funcional actualmente útil para PT5.

No sustituye a los README operativos junto al código, pero sí concentra:

- la organización de las suites
- la correlación con las hojas relevantes del Excel
- el estado real de cobertura actual

## Documentación principal

- Componente completo:
  - `validation/components/ontology_hub/README.md`
- Suite de integración técnica:
  - `validation/components/ontology_hub/integration/README.md`
- Suite funcional:
  - `validation/components/ontology_hub/functional/README.md`
- Criterio general de correlación PT5:
  - `docs/13_test_cases.md`

## Estructura actual

- `validation/components/ontology_hub/integration/`
  - validación PT5 de integración técnica del componente en el framework
  - runners, catálogo de casos y specs PT5
- `validation/components/ontology_hub/functional/`
  - flujos funcionales Playwright alineados con la hoja `Ontology Hub` del Excel
  - fixtures, estado interno y artefactos generados por la app
  - suite usada por defecto para `ontology-hub` en `Level 6`
  - se ejecuta con `hard reset` por defecto para mantener reproducibilidad
- `validation/components/ontology_hub/ui/`
  - infraestructura Playwright compartida
  - `fixtures`, `pages`, `support` y runtime común

## Inventario operativo actual de Ontology Hub

| Elemento | Estado actual en el framework local | Referencia real |
| --- | --- | --- |
| Tipo de despliegue | componente opcional de `Level 5` | `inesdata-deployment/deployer.config` |
| Namespace | `demo` | `inesdata-deployment/deployer.config` |
| Release Helm | `demo-ontology-hub` | `adapters/inesdata/components.py` |
| Chart | `inesdata-deployment/components/ontology-hub/` | árbol del repo |
| Host público | `ontology-hub-demo.dev.ds.dataspaceunit.upm` | `inesdata-deployment/components/ontology-hub/values-demo.yaml` |
| Servicio interno | `ClusterIP` puerto `3333` | `inesdata-deployment/components/ontology-hub/values-demo.yaml` |
| Dependencias internas | MongoDB y Elasticsearch | `inesdata-deployment/components/ontology-hub/values-demo.yaml` |
| Imagen | `ontology-hub:local` preparada por `Level 5` | `adapters/inesdata/components.py` |
| Suite automática en `Level 6` | `functional/` | `validation/components/runner.py` |
| Suite complementaria | `integration/` | `validation/components/ontology_hub/integration/README.md` |
| Estrategia de preparación por defecto | `hard reset` | `validation/components/ontology_hub/functional/README.md` |

## Puntos de entrada reales de Ontology Hub

| Punto de entrada | Uso real | Papel en validación |
| --- | --- | --- |
| `http://ontology-hub-demo.dev.ds.dataspaceunit.upm/` | home pública | disponibilidad inicial |
| `http://ontology-hub-demo.dev.ds.dataspaceunit.upm/dataset` | catálogo y navegación pública principal | base de la suite `functional/` |
| `http://ontology-hub-demo.dev.ds.dataspaceunit.upm/edition` | área autenticada de edición | login, CRUD y administración |
| `http://ontology-hub-demo.dev.ds.dataspaceunit.upm/edition/login` | acceso autenticado | caso funcional de sesión |
| `http://ontology-hub-demo.dev.ds.dataspaceunit.upm/dataset/lov/api` | documentación API histórica del componente | parte de la validación `integration/` |

## Artefactos y estado interno

| Tipo | Ruta actual | Uso |
| --- | --- | --- |
| Evidencias oficiales | `experiments/.../components/ontology-hub/` | artefactos persistidos de `Level 6` |
| Estado de `integration` | `validation/components/ontology_hub/integration/state/` | bootstrap y coordinación técnica |
| Estado de `functional` | `validation/components/ontology_hub/functional/state/` | coordinación entre tests al lanzar por CLI |
| Artefactos generados por la app | `validation/components/ontology_hub/functional/generated/` | `.n3`, resultados Themis, ZIPs de Patterns |

## Fuentes funcionales del Excel

Dentro de `docs/A5.2_Casos_Prueba_.xlsx`, para `Ontology Hub` hay tres niveles
distintos de referencia:

1. `Ontology Hub`
2. `A5.1_Casos_Prueba_Ex.1`
3. `A5.1_Funcionlidades_Ex.1`

La lectura correcta es esta:

- `Ontology Hub`:
  - define 27 escenarios operativos detallados del componente
  - es la base más directa de la suite `functional/`
- `A5.1_Casos_Prueba_Ex.1`:
  - normaliza `Ontology Hub` en 16 casos PT5 (`PT5-OH-*`)
  - es la referencia natural para la suite `integration/`
- `A5.1_Funcionlidades_Ex.1`:
  - descompone el componente en funcionalidades atómicas (`OntHub-*`)
  - sirve como capa de trazabilidad más fina

## Correlación aplicable a Ontology Hub

Sí: para `Ontology Hub` tiene sentido asociar conjuntamente:

- los 27 casos de la hoja `Ontology Hub`
- los 16 casos `PT5-OH-*` de `A5.1_Casos_Prueba_Ex.1`
- las 56 funcionalidades `OntHub-*` de `A5.1_Funcionlidades_Ex.1`

Esa triple asociación es útil porque:

- la hoja `Ontology Hub` describe el flujo operativo detallado
- `A5.1_Casos_Prueba_Ex.1` expresa la normalización PT5
- `A5.1_Funcionlidades_Ex.1` permite justificar granularmente qué capacidad del
  componente está cubierta o no

## Cobertura funcional actual de los 27 casos

La suite `functional/` sí modela los 27 casos de la hoja `Ontology Hub`, con
una nota de numeración:

- `OH-APP-00` cubre el caso `1`
- `OH-APP-01` cubre el caso `2`
- no existe `OH-APP-02`, pero no falta cobertura del Excel por ello

### Matriz hoja `Ontology Hub` -> automatización

| Caso hoja `Ontology Hub` | Automatización |
| --- | --- |
| `1` | `OH-APP-00` |
| `2` | `OH-APP-01` |
| `3` | `OH-APP-03` |
| `4` | `OH-APP-04` |
| `5` | `OH-APP-05` |
| `6` | `OH-APP-06` |
| `7` | `OH-APP-07` |
| `8` | `OH-APP-08` |
| `9` | `OH-APP-09` |
| `10` | `OH-APP-10` |
| `11` | `OH-APP-11` |
| `12` | `OH-APP-12` |
| `13` | `OH-APP-13` |
| `14` | `OH-APP-14` |
| `15` | `OH-APP-15` |
| `16` | `OH-APP-16` |
| `17` | `OH-APP-17` |
| `18` | `OH-APP-18` |
| `19` | `OH-APP-19` |
| `20` | `OH-APP-20` |
| `21` | `OH-APP-21` |
| `22` | `OH-APP-22` |
| `23` | `OH-APP-23` |
| `24` | `OH-APP-24` |
| `25` | `OH-APP-25` |
| `26` | `OH-APP-26` |
| `27` | `OH-APP-27` |

## Cobertura PT5 normalizada

La respuesta corta es:

- sí, los 27 casos funcionales cubren la hoja `Ontology Hub`
- no, eso no equivale automáticamente a cubrir de forma completa los 16 casos
  `PT5-OH-*`

La cobertura real frente a `A5.1_Casos_Prueba_Ex.1` hoy es:

| Caso PT5 | Cobertura desde `functional/` | Referencia principal |
| --- | --- | --- |
| `PT5-OH-01` | `sí` | `OH-APP-03`, `OH-APP-04` |
| `PT5-OH-02` | `sí` | `OH-APP-10` |
| `PT5-OH-03` | `sí` | `OH-APP-14` |
| `PT5-OH-04` | `sí` | `OH-APP-19`, `OH-APP-20`, `OH-APP-21` |
| `PT5-OH-05` | `parcial` | `OH-APP-15` a `OH-APP-18` |
| `PT5-OH-06` | `no` | sin automatización funcional específica |
| `PT5-OH-07` | `no explícita` | no hay aserción semántica RDF/OWL dedicada |
| `PT5-OH-08` | `parcial` | búsqueda indirecta en catálogo, no caso dedicado de vocabularios por texto libre |
| `PT5-OH-09` | `sí` | `OH-APP-06` a `OH-APP-09` |
| `PT5-OH-10` | `sí` | `OH-APP-11` a `OH-APP-13` |
| `PT5-OH-11` | `parcial` | `OH-APP-05` cubre ficha y descarga, pero no toda la visualización PT5 normalizada |
| `PT5-OH-12` | `no explícita` | no hay caso funcional dedicado a estadísticas y popularidad |
| `PT5-OH-13` | `no` | SPARQL vive en la suite `integration/` |
| `PT5-OH-14` | `sí sustancial` | `OH-APP-22`, `OH-APP-23`, `OH-APP-24` |
| `PT5-OH-15` | `parcial` | acceso UI sí; paridad UI/API no queda completa en `functional/` |
| `PT5-OH-16` | `no` | no hay validación funcional directa de conexión con conector |

## Lectura correcta de la cobertura

Para `Ontology Hub`, la lectura correcta hoy es:

- la hoja `Ontology Hub` está cubierta operativamente por la suite
  `functional/`
- los casos `PT5-OH-*` quedan cubiertos de forma desigual entre
  `functional/` e `integration/`
- las funcionalidades `OntHub-*` sirven para justificar cobertura fina y gaps

Por tanto:

- `functional/` describe mejor el comportamiento observable del componente
- `integration/` describe mejor la cobertura PT5 más normalizada
- ambos niveles siguen siendo necesarios si se quiere hablar con precisión de
  PT5

## Relación con `A5.1_Funcionlidades_Ex.1`

Sí, esta hoja debe usarse como referencia adicional para `Ontology Hub`.

Es especialmente útil para:

- justificar cobertura fina
- detectar funcionalidades aún no automatizadas
- homogeneizar el criterio con otros componentes

Ejemplos directos:

- `PT5-OH-01` se apoya en `OntHub-1` y `OntHub-4`
- `PT5-OH-04` se apoya en `OntHub-8`, `OntHub-9`, `OntHub-10`
- `PT5-OH-14` se apoya en `OntHub-52`, `OntHub-53`
- `PT5-OH-15` se apoya en `OntHub-54`, `OntHub-55`
- `PT5-OH-16` se apoya en `OntHub-56`

## Artefactos

- Artefactos oficiales del framework:
  - `experiments/`
- Estado interno de `integration`:
  - `validation/components/ontology_hub/integration/state/`
- Estado interno de `functional`:
  - `validation/components/ontology_hub/functional/state/`
- Artefactos generados por la app en `functional`:
  - `validation/components/ontology_hub/functional/generated/`

## Nota de despliegue

- El framework prepara el despliegue de `ontology-hub` para que su hostname
  público también sea resoluble desde dentro del pod.
- Esto se hace inyectando `hostAliases` en el chart cuando existe un host
  público configurado para el componente.
- El objetivo es evitar fallos de autoacceso del backend en operaciones como el
  análisis de versiones, sin modificar el código de la aplicación.

## Criterio de mantenimiento

- La documentación operativa debe mantenerse junto al código de cada suite.
- La trazabilidad documental de `Ontology Hub` debe mantenerse aquí, en `docs/`.
- Si se extiende el mismo criterio al resto de componentes, la referencia común
  debe vivir en `docs/13_test_cases.md`.
- El inventario operativo del componente debe mantenerse alineado con
  `docs/12_local_validation_environment.md` cuando cambien hostnames, releases,
  dependencias o estrategia de ejecución.
