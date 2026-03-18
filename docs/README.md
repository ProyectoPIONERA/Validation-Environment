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

## Por dónde empezar

Lee estos documentos en este orden:

1. [00_overview.md](./00_overview.md)
2. [01_framework_architecture.md](./01_framework_architecture.md)
3. [05_repository_structure.md](./05_repository_structure.md)
4. [03_integration_guide.md](./03_integration_guide.md)
5. [02_validation_architecture.md](./02_validation_architecture.md)
6. [04_execution_flow.md](./04_execution_flow.md)

## Documentación principal

- [00_overview.md](./00_overview.md): visión general del framework y del problema que resuelve.
- [01_framework_architecture.md](./01_framework_architecture.md): arquitectura actual explicada de forma simple.
- [02_validation_architecture.md](./02_validation_architecture.md): qué valida hoy el sistema y cómo evolucionará.
- [03_integration_guide.md](./03_integration_guide.md): guía práctica para integrar componentes.
- [04_execution_flow.md](./04_execution_flow.md): flujo secuencial desde `inesdata.py`.
- [05_repository_structure.md](./05_repository_structure.md): mapa del repositorio para nuevos desarrolladores.
