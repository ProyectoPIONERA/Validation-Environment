# 00. Visión General

## Qué hace este repositorio

Este repositorio sirve para levantar un entorno local del dataspace PIONERA y validar que los conectores funcionan correctamente.

Hoy cubre principalmente:

- despliegue local del cluster y servicios base
- despliegue del dataspace y de los conectores
- despliegue opcional de componentes adicionales
- validación API de interoperabilidad con Newman

## Qué problema resuelve

PIONERA necesita un entorno reproducible donde se pueda comprobar que:

- los conectores arrancan correctamente
- el dataspace queda operativo
- los flujos básicos de interoperabilidad funcionan
- los componentes adicionales pueden integrarse sin romper el resto del entorno

Sin este framework, cada integración tendría que resolverse de forma manual y sería difícil comparar resultados entre ejecuciones.

## Idea general de la arquitectura

La estructura actual del repositorio se entiende bien si la miramos en cuatro bloques:

1. `inesdata.py` orquesta los niveles de trabajo.
2. `adapters/inesdata/` encapsula la lógica específica de INESData.
3. `framework/` contiene la lógica genérica de validación y resultados.
4. `validation/` contiene las pruebas API actuales y la estructura preparada para pruebas de componentes y UI.

## Qué está implementado hoy

- La validación activa es la validación API del núcleo del dataspace.
- Las colecciones activas están en `validation/core/collections/`.
- Los scripts JS activos están en `validation/core/tests/` y `validation/shared/api/`.
- `validation/components/` ya existe como estructura modular, pero todavía no entra en la ejecución automática.
- `validation/ui/` existe solo como scaffolding inicial.

## Qué debe leer un desarrollador nuevo

Si tu propósito es integrar o mantener un componente:

1. Lee [01_framework_architecture.md](./01_framework_architecture.md).
2. Mira [05_repository_structure.md](./05_repository_structure.md).
3. Sigue [03_integration_guide.md](./03_integration_guide.md).

Si tu propósito es entender la validación:

1. Lee [02_validation_architecture.md](./02_validation_architecture.md).
2. Luego revisa [04_execution_flow.md](./04_execution_flow.md).
