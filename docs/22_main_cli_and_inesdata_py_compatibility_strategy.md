# 22. `main.py` e `inesdata.py`

`main.py` es la entrada canonica del framework. `inesdata.py` queda como entrada
legacy de compatibilidad cuando exista en una copia local del proyecto.

## Entrada Recomendada

```bash
python3 main.py menu
python3 main.py inesdata deploy --topology local
python3 main.py edc deploy --topology local
python3 main.py inesdata validate --topology local
python3 main.py edc validate --topology local
```

## Por Que `main.py`

`main.py` es neutral respecto al adapter:

- selecciona `inesdata` o `edc`;
- selecciona topologia;
- orquesta niveles;
- ejecuta hosts, metricas, validacion y run completo;
- expone menu guiado para usuarios no tecnicos;
- mantiene una interfaz reproducible para automatizacion.

## Menu Guiado

El menu de `main.py` conserva las acciones importantes del flujo historico:

- niveles `1` a `6`;
- `Run All Levels`;
- seleccion de adapter;
- plan de despliegue;
- hosts;
- metricas;
- herramientas de desarrollo;
- validaciones UI.

Las opciones legacy como bootstrap, doctor, recovery, cleanup, build de imagenes
y suites UI siguen disponibles desde submenus para no romper el flujo de trabajo
existente.

## Compatibilidad

La logica nueva no debe nacer en `inesdata.py`. Las operaciones compartidas
viven en:

| Modulo | Uso |
| --- | --- |
| `framework/local_menu_tools.py` | bootstrap, doctor, recovery, cleanup, imagenes locales |
| `validation/ui/interactive_menu.py` | submenus de validacion UI |
| `validation/orchestration/` | orquestacion de `Level 6` |
| `deployers/infrastructure/lib` | contratos y utilidades compartidas |

El objetivo es que la ergonomia historica se mantenga, pero la arquitectura
evolucione desde `main.py`.
