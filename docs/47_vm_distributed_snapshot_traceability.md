# Registro de Versión Validada `vm-distributed`

## Propósito

Este documento registra una referencia versionada de la topología
`vm-distributed` del framework. Su objetivo es ofrecer trazabilidad técnica
sobre una versión identificada a partir de un entorno distribuido operativo, sin
confundir ese alcance con la estabilidad global de todas las topologías del
repositorio.

## Referencia Versionada

| Campo | Valor |
| --- | --- |
| Rama | `snapshot/pionera40-vm-distributed` |
| Tag | `vm-distributed-pionera40-demo-2026-06-05` |
| Commit base de la referencia funcional | `0255bff` |
| Topología cubierta | `vm-distributed` |
| Topologías no cubiertas por esta referencia | `local`, `vm-single` |

El tag apunta a un commit concreto y debe usarse como referencia fija cuando se
necesite revisar la versión validada. La rama snapshot puede contener
documentación o ajustes posteriores relacionados con la trazabilidad, sin mover
el tag.

## Alcance

La referencia cubre la topología `vm-distributed` del framework. No constituye
una declaración de estabilidad para `main`, ni certifica automáticamente el
estado de `local` o `vm-single`.

Antes de promover cambios desde esta rama hacia una rama principal de desarrollo,
se recomienda ejecutar una matriz de revalidación por topología.

## Criterios de Trazabilidad

La referencia se conserva separada porque cumple estos criterios:

- procede de una versión reconstruida desde un entorno distribuido operativo;
- está identificada mediante rama, tag y commit;
- separa el alcance validado de las topologías pendientes de revalidación;
- conserva la trazabilidad sin publicar artefactos auxiliares de diagnóstico;
- evita versionar contraseñas, tokens, claves privadas, cookies o kubeconfigs
  reales;
- documenta explícitamente que la estabilidad de una topología no implica la
  estabilidad automática de las demás.

## Uso de la Referencia

Para revisar el commit etiquetado:

```bash
git fetch --all --tags
git checkout tags/vm-distributed-pionera40-demo-2026-06-05 -b review/vm-distributed
```

Para revisar la rama snapshot:

```bash
git fetch origin
git checkout snapshot/pionera40-vm-distributed
git pull
```

## Matriz Mínima Antes de Fusionar

Antes de fusionar cambios hacia una rama principal, se recomienda registrar una
matriz de validación como la siguiente:

| Topología | Estado esperado antes de fusionar |
| --- | --- |
| `local` | Revalidación de niveles críticos y validación funcional |
| `vm-single` | Revalidación con el runtime configurado para esa topología |
| `vm-distributed` | Evidencia de despliegue distribuido y validación asociada |

La fusión debe realizarse por bloques pequeños y revisables para mantener
separadas las decisiones de infraestructura, despliegue, validación y
documentación.
