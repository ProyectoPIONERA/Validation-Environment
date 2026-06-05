# Trazabilidad del Snapshot `vm-distributed`

## Objetivo

Este documento fija la referencia técnica que debe usarse para explicar y
reproducir la versión funcional de la topología `vm-distributed` durante demos,
revisión interna y auditoría.

La finalidad es evitar mezclar una rama general de desarrollo con la versión que
sí fue identificada a partir de un entorno distribuido real y operativo.

## Referencia Versionada

| Campo | Valor |
| --- | --- |
| Rama de referencia | `snapshot/pionera40-vm-distributed` |
| Tag de demo/auditoría | `vm-distributed-pionera40-demo-2026-06-05` |
| Commit | `0255bff` |
| Alcance confirmado | Topología `vm-distributed` |
| Estado de `local` | Pendiente de revalidación en esta línea |
| Estado de `vm-single` | Pendiente de revalidación en esta línea |

El tag es la referencia más estable para demos y auditoría porque apunta a un
commit concreto. La rama snapshot permite revisar la evolución documental o
correcciones posteriores sin perder esa referencia fija.

## Criterio de Auditoría

La versión de `vm-distributed` se considera defendible porque:

- se identificó a partir de un entorno distribuido real que estaba operativo;
- se reconstruyó en una rama separada para preservar trazabilidad;
- se revisó antes de subirla al repositorio remoto;
- no se versionaron artefactos auxiliares de diagnóstico;
- no se versionaron contraseñas, tokens, claves privadas, cookies ni
  kubeconfigs reales;
- los valores sensibles encontrados durante la revisión se sustituyeron por
  marcadores seguros;
- no se fusionó con `main` sin una revalidación previa de todas las topologías.

Este criterio no afirma que todas las topologías del framework estén validadas
en el mismo commit. Afirma que la topología `vm-distributed` tiene una
referencia trazable y separada.

## Uso Recomendado Para Demo

Para revisar exactamente la versión etiquetada:

```bash
git fetch --all --tags
git checkout tags/vm-distributed-pionera40-demo-2026-06-05 -b demo/vm-distributed-pionera40
```

Para trabajar sobre la rama snapshot:

```bash
git fetch origin
git checkout snapshot/pionera40-vm-distributed
git pull
```

Usa esta referencia para demos de `vm-distributed`. No uses `main` como prueba de
estabilidad de esta topología mientras no exista una matriz de revalidación
actualizada.

## Redacción Recomendada Para Entregable

Texto breve defendible:

```text
La topología distribuida se validó sobre una versión snapshot reconstruida desde
un entorno real funcional. La versión fue preservada en una rama separada y en
un tag fijo para asegurar trazabilidad, reproducibilidad de demo y revisión de
auditoría. Antes de versionarla se realizó una revisión de seguridad para evitar
subir secretos o artefactos auxiliares. Las topologías local y vm-single no se
declaran estables en esa misma línea hasta completar su revalidación específica.
```

## Qué No Debe Interpretarse

Esta referencia no debe interpretarse como:

- una declaración de estabilidad global de `main`;
- una certificación automática de `local` o `vm-single`;
- una autorización para publicar secretos, kubeconfigs o logs privados;
- una obligación de fusionar la rama snapshot a `main`.

## Siguiente Paso Antes de Fusionar

Antes de mover cambios hacia `main`, debe existir una matriz mínima de
validación:

| Topología | Evidencia mínima esperada |
| --- | --- |
| `local` | Niveles críticos ejecutados y validación funcional sin contaminación de hosts ni recursos |
| `vm-single` | Despliegue con su runtime esperado y validación funcional de conectores/componentes |
| `vm-distributed` | Referencia snapshot, evidencia de despliegue distribuido y resultados de validación asociados |

La fusión a `main` debe hacerse por bloques pequeños y revisables, evitando
mezclar cambios de infraestructura, componentes, tests y documentación en una
única operación grande.
