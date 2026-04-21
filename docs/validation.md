# Validación

## Nivel 6

El nivel 6 es el nivel de validación. Debe validar el dataspace desplegado y los componentes habilitados sin requerir un nivel adicional de validación de servicios.

Según el adapter y el perfil del deployer, el nivel 6 puede ejecutar:

- limpieza de datos de prueba;
- colecciones Newman/Postman;
- suites UI con Playwright;
- validaciones de componentes;
- recolección de métricas;
- generación de reportes de experimento.

## Newman

Newman valida comportamiento API y flujos end-to-end del dataspace.

La cobertura típica incluye:

- autenticación en conectores;
- publicación de assets;
- descubrimiento de catálogo;
- negociación de contrato;
- inicio de transferencia;
- verificación de almacenamiento de transferencia cuando aplica.

## Playwright

Playwright valida flujos visibles en navegador.

Las suites UI son adapter-aware. Deben validar dashboards y portales de usuario sin sustituir las validaciones API.

Comandos típicos:

```bash
python3 main.py inesdata validate --topology local
python3 main.py edc validate --topology local
```

## Limpieza de Datos de Prueba

La validación puede empezar con limpieza para facilitar trazabilidad y evitar saturación por datos de ejecuciones previas.

La limpieza debe ser segura por defecto y reportar qué eliminó o qué omitió.

## Métricas

Las métricas pueden ejecutarse desde menú o CLI:

```bash
python3 main.py inesdata metrics --topology local
python3 main.py inesdata metrics --topology local --kafka
```

Los artefactos de métricas y validación se almacenan en:

```text
experiments/
```

Esta carpeta es salida generada y no debe subirse al repositorio.

## Reportes

Después de una validación o experimento:

```bash
python3 main.py report <experiment_id>
python3 main.py compare <experiment_a> <experiment_b>
```

Los reportes deben indicar adapter, topología, conectores y suites ejecutadas.
