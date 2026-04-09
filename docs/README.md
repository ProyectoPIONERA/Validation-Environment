# Framework de Validación PIONERA

Esta carpeta contiene la documentación vigente del framework usado para desplegar y validar el entorno local de PIONERA con el adapter `inesdata`.

## Qué es este framework

Este repositorio resuelve tres problemas prácticos:

1. Desplegar un entorno local del dataspace PIONERA.
2. Integrar conectores y componentes opcionales.
3. Ejecutar validaciones funcionales de interoperabilidad sobre los conectores desplegados.

La idea principal es simple:

- `inesdata.py` orquesta los niveles de despliegue y validación.
- `adapters/inesdata/` contiene la lógica específica de INESData.
- `framework/` contiene la lógica reutilizable de validación, métricas y persistencia de resultados.
- `validation/` contiene las colecciones y scripts de prueba.
- `inesdata-deployment/` contiene los charts y values Helm del entorno.

## Cómo leer esta carpeta

La documentación está pensada para leerse en dos bloques secuenciales:

1. `00` a `06`: describen la base del framework, su arquitectura y el flujo operativo.
2. `07` a `10`: describen la evolución por fases del sistema de validación y artefactos.

En esa división por fases:

- `Fase 1`: sistema de experimentos
- `Fase 2`: pipeline de métricas
- `Fase 3`: medidas reales de Kafka
- `Fase 4`: validación UI con Playwright

## Orden recomendado de lectura

- [00_overview.md](./00_overview.md): visión general del framework y del problema que resuelve.
- [01_framework_architecture.md](./01_framework_architecture.md): arquitectura actual.
- [02_validation_architecture.md](./02_validation_architecture.md): qué valida hoy el sistema y cómo evolucionará.
- [03_integration_guide.md](./03_integration_guide.md): guía práctica para integrar componentes.
- [04_execution_flow.md](./04_execution_flow.md): flujo secuencial desde `inesdata.py`.
- [05_repository_structure.md](./05_repository_structure.md): mapa del repositorio para nuevos desarrolladores.
- [06_information_exchange_flow.md](./06_information_exchange_flow.md): flujo manual de intercambio de información para reproducirlo en Postman.
- [07_experiment_system.md](./07_experiment_system.md): contrato de artefactos del experimento.
- [08_metrics_pipeline.md](./08_metrics_pipeline.md): extracción y agregación de métricas.
- [09_kafka_real_measurements.md](./09_kafka_real_measurements.md): benchmarking Kafka persistido.
- [10_ui_validation_core.md](./10_ui_validation_core.md): validación UI alineada con los flujos API.
- [11_ontology_hub_validation.md](./11_ontology_hub_validation.md): validación, cobertura y trazabilidad actual de Ontology Hub.
- [12_local_validation_environment.md](./12_local_validation_environment.md): inventario del entorno local actual de validación.
- [13_test_cases.md](./13_test_cases.md): criterio común para correlacionar funcionalidades, PT5, casos operativos y automatización.
- [14_production_environment_plan.md](./14_production_environment_plan.md): plan de transición desde el entorno local actual hacia el entorno productivo.
