# Ontology Hub Validation Index

Este documento actua como indice de la validacion de `Ontology Hub` dentro del framework.

## Objetivo

Centralizar los puntos de entrada documentales sin duplicar la documentacion operativa que vive junto al codigo.

## Documentacion Principal

- Componente completo:
  - `validation/components/ontology_hub/README.md`
- Suite de integracion tecnica del componente:
  - `validation/components/ontology_hub/integration/README.md`
- Suite funcional basada en el Excel A5.2 y usada por defecto en `Level 6`:
  - `validation/components/ontology_hub/functional/README.md`
- Trazabilidad funcional de la suite basada en Excel:
  - `validation/components/ontology_hub/functional/TRACEABILITY.md`

## Estructura

- `validation/components/ontology_hub/integration/`
  - validacion PT5 de integracion del componente en el framework
  - runners, catalogo de casos y specs PT5
- `validation/components/ontology_hub/functional/`
  - flujos funcionales Playwright trazados contra el Excel `docs/A5.2_Casos_Prueba_.xlsx`
  - fixtures, estado interno y artefactos generados por la app
  - suite usada por defecto para `ontology-hub` en `Level 6`
  - se ejecuta con `hard reset` por defecto para mantener reproducibilidad
- `validation/components/ontology_hub/ui/`
  - infraestructura compartida de Playwright
  - `fixtures`, `pages`, `support` y runtime comun

## Artefactos

- Artefactos oficiales del framework:
  - `experiments/`
- Estado interno de integration:
  - `validation/components/ontology_hub/integration/state/`
- Estado interno de functional:
  - `validation/components/ontology_hub/functional/state/`
- Artefactos generados por la app en functional:
  - `validation/components/ontology_hub/functional/generated/`

## Nota De Despliegue

- El framework prepara el despliegue de `ontology-hub` para que su hostname publico tambien sea resoluble desde dentro del pod.
- Esto se hace inyectando `hostAliases` en el chart cuando existe un host publico configurado para el componente.
- El objetivo es evitar fallos de autoacceso del backend en operaciones como el analisis de versiones, sin modificar el codigo de la aplicación.

## Fuentes Funcionales

- Excel de casos funcionales:
  - `docs/A5.2_Casos_Prueba_.xlsx`
- Contexto metodologico:
  - `docs_/logs/validation/PIONERA E5.1 - final.docx`
- Contexto del componente:
  - `docs_/logs/components/ontology-hub/README.md`
  - `docs_/logs/components/ontology-hub/PIONERA E2.1 - final.docx`

## Criterio De Mantenimiento

- La documentacion operativa debe mantenerse junto al codigo de cada suite.
- Este archivo solo debe resumir, enlazar y explicar la organizacion general.
- Si cambian rutas o suites, este indice debe actualizarse junto con los README locales.
