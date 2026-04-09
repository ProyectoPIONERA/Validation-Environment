# 13. Casos de Prueba y Correlación PT5

## Objetivo

Este documento define el criterio general para correlacionar:

- funcionalidades atómicas
- casos PT5 normalizados
- casos operativos detallados por componente
- automatización real del framework

La idea es usar el mismo patrón para todos los componentes, no solo para
`Ontology Hub`.

## Las tres capas del Excel

Dentro de `docs/A5.2_Casos_Prueba_.xlsx` hay tres niveles distintos de
representación:

### 1. `A5.1_Funcionlidades_Ex.1`

Contiene funcionalidades atómicas por componente, por ejemplo:

- `OntHub-1`
- `OntHub-33`
- `MH-04`

Esta hoja responde a:

- qué capacidad concreta del componente se quiere validar

### 2. `A5.1_Casos_Prueba_Ex.1`

Contiene casos PT5 normalizados, por ejemplo:

- `PT5-OH-01`
- `PT5-MH-04`

Esta hoja responde a:

- qué caso de prueba PT5 agrupa una o varias funcionalidades

Además, ya incluye una columna de trazabilidad funcional que enlaza con la hoja
de funcionalidades.

### 3. Hoja específica del componente

Ejemplos:

- `Ontology Hub`

Esta hoja responde a:

- cómo se ejecuta operativamente el flujo del componente
- qué pasos manuales o funcionales concretos se esperan

## Regla de correlación recomendada

La correlación correcta en el framework debe seguir este orden:

1. funcionalidad atómica
2. caso PT5 normalizado
3. caso operativo del componente
4. automatización real

En forma resumida:

```text
A5.1_Funcionlidades_Ex.1
    -> A5.1_Casos_Prueba_Ex.1
        -> hoja específica del componente
            -> test automatizado real
```

## Inventario mínimo de trazabilidad por componente

Para mantener una correlación útil y comparable entre componentes, cada
componente debería documentar al menos estas piezas:

| Pieza | Ejemplo | Propósito |
| --- | --- | --- |
| Funcionalidades atómicas | `OntHub-33` | granularidad fina de cobertura |
| Casos PT5 normalizados | `PT5-OH-08` | normalización oficial PT5 |
| Casos operativos del componente | caso `23` de la hoja `Ontology Hub` | flujo detallado real |
| Automatización ejecutable | `OH-APP-23` | evidencia automatizada actual |
| Estado de cobertura | `sí`, `parcial`, `no` | lectura honesta del estado del framework |

## Uso recomendado por tipo de suite

### Suite funcional

Debe mapearse primero contra la hoja específica del componente, porque ahí está
el flujo operativo detallado.

Después debe declararse su relación con:

- los casos PT5 normalizados
- las funcionalidades atómicas

### Suite de integración

Debe mapearse primero contra `A5.1_Casos_Prueba_Ex.1`, porque ahí está la
normalización PT5 más estable.

Después puede bajar a funcionalidades atómicas cuando haga falta justificar
cobertura parcial o gaps.

## Plantilla recomendada de correlación

La tabla mínima recomendada para cualquier componente es:

| Funcionalidad atómica | Caso PT5 | Caso operativo | Automatización | Cobertura | Observaciones |
| --- | --- | --- | --- | --- | --- |
| `OntHub-33` | `PT5-OH-08` | `23` | `OH-APP-23` | `parcial` | ejemplo ilustrativo |

Esto permite reutilizar el mismo patrón en:

- `Ontology Hub`
- `AI Model Hub`
- cualquier componente futuro que se incorpore al framework

## Ejemplo aplicado a Ontology Hub

Para `Ontology Hub`, la correlación correcta es:

- `A5.1_Funcionlidades_Ex.1`:
  - `OntHub-1` a `OntHub-56`
- `A5.1_Casos_Prueba_Ex.1`:
  - `PT5-OH-01` a `PT5-OH-16`
- hoja `Ontology Hub`:
  - 27 casos operativos detallados
- automatización real:
  - `OH-APP-00`, `OH-APP-01`, `OH-APP-03` ... `OH-APP-27`

## Qué aporta este criterio

- evita mezclar niveles de abstracción
- permite decir con precisión si una cobertura es:
  - funcional-operativa
  - PT5 normalizada
  - funcional atómica
- facilita comparar componentes con distinto grado de madurez
- permite extender la misma lógica a `AI Model Hub` y futuros componentes

## Recomendación práctica

- La documentación específica de cada componente debe mantener su propia
  correlación concreta dentro de `docs/`.
- Este documento debe mantenerse como regla general común del framework.
- Los documentos de inventario del entorno, como `docs/12_local_validation_environment.md`,
  no deben duplicar esta matriz; deben enlazarla y consumir su criterio.
