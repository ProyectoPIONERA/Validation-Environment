# Manual de usuario

Este manual resume el uso operativo del Validation Environment desde el menu
interactivo. Esta pensado para personas que necesitan desplegar, validar o
revisar evidencias sin conocer la estructura interna del codigo.

## Alcance

El menu expone rutas de despliegue, preparacion, validacion y consulta de
resultados. Para cierre documental, una ruta solo debe considerarse validada si
existe un experimento asociado con reporte, metricas, logs y artefactos
reproducibles. La existencia de una opcion en el menu no equivale por si sola a
evidencia formal de validacion.

La evidencia de cierre disponible se interpreta asi:

| Adapter | `local` | `vm-single` | `vm-distributed` |
| --- | --- | --- | --- |
| `inesdata` | Evidencia disponible | Evidencia disponible | Evidencia disponible en su rama específica |
| `edc` | Evidencia disponible | Evidencia disponible | Evidencia disponible en esta rama |

## Acceso al menu

Desde la raiz del repositorio:

```bash
python3 main.py menu
```

El menu permite seleccionar topologia y adapter antes de ejecutar niveles u
operaciones. Las topologias canonicas son `local`, `vm-single` y
`vm-distributed`; los adapters disponibles son `inesdata` y `edc`.

## Flujo habitual

Para una ejecucion completa desde cero:

1. Seleccionar topologia con `T - Select topology`.
2. Seleccionar adapter con `S - Select adapter`.
3. Ejecutar `0 - Run All Levels (1-6) sequentially`, o ejecutar los niveles de
   forma separada si se quiere revisar cada fase.
4. Consultar las URLs de acceso con `U - Show available access URLs`.
5. Revisar los resultados con `E - View experiment reports`.

En topologia `local`, el operador debe mantener `minikube tunnel` abierto cuando
las rutas publicas dependan de Ingress. Si se modifican recursos de Minikube,
conviene recrear el cluster desde el Nivel 1.

## Configurar un entorno propio

Para usar el framework en un contexto nuevo, primero se debe decidir la
topologia, el adapter y la forma de acceso a las maquinas. En `local` suelen
bastar los `.config` locales y `minikube tunnel`. En `vm-single` y
`vm-distributed` hay que revisar direcciones publicas, kubeconfig, SSH,
certificados, estrategia de imagenes y conectores.

La regla practica es sencilla:

| Elemento | Uso |
| --- | --- |
| `.config` | Configuracion efectiva que leen los deployers. |
| `.config.example` | Plantilla versionada. |
| `.profiles/*.env` | Perfil local opcional para rellenar `.config`; no guarda secretos. |
| `.secrets/*.env` | Secretos locales ignorados por Git. |
| `PIONERA_*` | Overrides temporales durante una ejecucion. |

La lista organizada de variables modificables esta en
[Referencia de variables de configuracion](./51_configuration_variables_reference.md).

En `vm-distributed`, la ruta recomendada desde el menu es:

1. `T` para seleccionar `vm-distributed`.
2. `W -> P` para elegir el perfil local, si se usa uno.
3. `W -> 1` para crear o actualizar los `.config`.
4. `W -> C` para revisar valores efectivos y su origen.
5. `W -> 2` para revisar el preflight estatico.
6. `W -> 3` para previsualizar despliegue y hosts.
7. `W -> 4` para ejecutar preflight SSH/HTTP solo si la politica de red lo
   permite.

Si las politicas de red de las organizaciones implicadas no autorizan tuneles
hacia una VM externa, el despliegue no debe basarse en port-forwarding SSH hacia
esa VM. Las alternativas son ejecutar el framework desde una maquina con acceso
aprobado a todas las VMs, usar un registry accesible por el cluster externo o
pedir a la organizacion externa que despliegue su conector y exponga endpoints
publicos acordados. La guia completa esta en
[Mapa de configuracion y despliegue](./49_configuration_map.md).

## Niveles

| Opcion | Uso |
| --- | --- |
| `0 - Run All Levels (1-6) sequentially` | Ejecuta despliegue y validacion en orden. |
| `1 - Level 1: Setup Cluster` | Prepara el cluster base. |
| `2 - Level 2: Deploy Common Services` | Despliega servicios comunes como Keycloak, MinIO, PostgreSQL y Vault. |
| `3 - Level 3: Deploy Dataspace` | Despliega el dataspace y servicios de control. |
| `4 - Level 4: Deploy Connectors` | Despliega conectores del adapter activo. |
| `5 - Level 5: Deploy Components` | Despliega componentes como Ontology Hub, AI Model Hub y Semantic Virtualization cuando estan configurados. |
| `6 - Level 6: Run Validation Tests` | Ejecuta las validaciones y genera evidencias. |

## Operaciones principales

| Opcion | Uso |
| --- | --- |
| `S - Select adapter` | Selecciona `inesdata` o `edc` para la sesion. |
| `T - Select topology` | Cambia entre `local`, `vm-single` y `vm-distributed`. |
| `K - Select cluster runtime` | Revisa o fija el runtime de cluster; actualmente solo es configurable en `vm-single`. |
| `W - vm-distributed assistant` | Ayuda a preparar configuracion distribuida, preflights y planes. |
| `P - Preview deployment plan` | Muestra el plan sin modificar el entorno. |
| `H - Plan/apply hosts entries` | Planifica o aplica entradas de `hosts`. |
| `U - Show available access URLs` | Muestra URLs de portales, conectores y componentes. |
| `J - Add connector to existing dataspace` | Añade un conector a un dataspace existente y ofrece ejecutar Nivel 4 en modo aditivo. |
| `G - Validate target` | Valida targets externos en modo seguro de solo lectura. |
| `E - View experiment reports` | Abre el visor local de experimentos. |
| `M - Run metrics / benchmarks` | Ejecuta metricas o benchmarks independientes. |
| `X - Recreate dataspace` | Recrea el dataspace con confirmacion explicita. |

## Componentes y validacion

Las opciones UI abren submenus de ejecucion normal, live o debug segun la
suite. Para una descripcion completa de los submenus, consulta
[Referencia del menu](./33_menu_reference.md).

| Opcion | Uso |
| --- | --- |
| `CM - Deploy selected components` | Ejecuta Nivel 5 para un subconjunto de componentes. |
| `AMH - Run official AI Model Hub Steps 7-10` | Ejecuta el flujo oficial de AI Model Hub soportado por esta rama para preparar componentes, servidor de modelos y sembrados de casos de uso. |
| `I - INESData UI Tests` | Ejecuta pruebas UI de INESData. |
| `N - EDC UI Tests` | Ejecuta pruebas UI del dashboard EDC e integraciones de componentes. |
| `O - Ontology Hub UI Tests` | Ejecuta pruebas UI de Ontology Hub. |
| `A - AI Model Hub UI Tests` | Ejecuta pruebas UI de AI Model Hub. |
| `V - Semantic Virtualization UI Tests` | Ejecuta pruebas UI o read-only de Semantic Virtualization. |
| `F - Dataspace Interoperability Tests` | Ejecuta Newman o Kafka sin lanzar todo el Nivel 6. |
| `Y - Run Test by ID` | Ejecuta un caso concreto por identificador Playwright/API. |

## Operacion y diagnostico

| Opcion | Uso |
| --- | --- |
| `B - Bootstrap Framework Dependencies` | Instala o repara dependencias del framework. |
| `D - Run Framework Doctor` | Ejecuta comprobaciones de preparacion local. |
| `R - Repair Local Access / Connectors` | Repara acceso local y, si se confirma, reinicia conectores. |
| `C - Cleanup Workspace` | Limpia artefactos generados o caches locales. |
| `L - Build and Deploy Local Images` | Construye y carga imagenes locales para desarrollo. |
| `? - Help` | Muestra ayuda breve del menu. |
| `Q - Exit` | Sale del menu. |

## Evidencias

Las ejecuciones de validacion generan resultados bajo `experiments/`. El punto
de entrada recomendado para revisar un experimento es el reporte HTML del
framework o la opcion `E - View experiment reports`. Las evidencias pueden
incluir reportes Newman, reportes Playwright, metricas JSON, logs de consola,
graficas y artefactos de componentes.
