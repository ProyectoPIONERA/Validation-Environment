# 02. Arquitectura de Validación

## Qué valida hoy el sistema

La validación actual comprueba la interoperabilidad básica entre conectores del dataspace.

El foco hoy está en el núcleo compartido del sistema:

- estado del entorno
- API de gestión del conector
- preparación del proveedor
- descubrimiento por catálogo
- negociación
- transferencia o acceso

Estas pruebas viven en `validation/core/collections/`.

## Qué significa `core`

`core` es la validación común que cualquier despliegue funcional del dataspace debe superar.

No está pensada para un componente concreto. Está pensada para responder a una pregunta muy práctica:

“¿Los conectores desplegados pueden interoperar entre sí en el flujo base esperado?”

## Qué significa `components`

La carpeta `validation/components/` ya existe para separar validaciones específicas por componente.

Ahora mismo esta estructura está preparada, pero todavía no se ejecuta automáticamente desde `inesdata.py`.

Su objetivo es alojar, próximamente, pruebas como estas:

- validación API específica de Ontology Hub
- validación API específica de AI Model Hub
- validación API específica de Semantic Virtualization

## Qué significa `shared`

`validation/shared/api/` contiene utilidades comunes que pueden reutilizar varias colecciones.

Hoy se usa sobre todo para centralizar el script compartido `common_tests.js`.

## Diferencia entre pruebas API y pruebas UI

### Pruebas API

Son las pruebas que ya están activas.

Se ejecutan con Newman y verifican contratos, respuestas y flujos backend.

Sirven para comprobar interoperabilidad y consistencia de las APIs implicadas en el dataspace.

### Pruebas UI

La carpeta `validation/ui/` existe hoy solo como preparación inicial.

Su objetivo futuro es cubrir validaciones funcionales sobre interfaces de usuario, por ejemplo:

- comportamiento del portal
- flujos de usuario
- coherencia entre UI y API

Hoy no forman parte de la ejecución normal del framework.

## Qué debe saber un desarrollador de componentes

Los desarrolladores de componentes no deben implementar ni modificar la lógica de validación del framework.

La responsabilidad práctica está separada así:

- el desarrollador integra el componente en despliegue o en código fuente
- el framework mantiene las pruebas en `validation/`

En otras palabras:

- sí debes conocer qué valida el sistema
- no debes editar `validation/` ni `framework/` para integrar tu componente
