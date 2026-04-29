# Validación

## Nivel 6

El nivel 6 es el nivel de validación. Debe validar el dataspace desplegado y los componentes habilitados sin requerir un nivel adicional de validación de servicios.

Según el adapter y el perfil del deployer, el nivel 6 puede ejecutar:

- limpieza de datos de prueba;
- colecciones Newman/Postman;
- validación funcional EDC+Kafka después de Newman cuando el adapter la soporta;
- suites UI con Playwright;
- validaciones de componentes;
- recolección de métricas;
- generación de reportes de experimento.

Cuando hay componentes configurados con runner registrado, `Level 6` ejecuta su
validacion despues de las suites del dataspace. En el estado actual:

- `ontology-hub` corre por defecto como validacion de componente;
- `ai-model-hub` corre su bootstrap por defecto;
- la UI PT5 de `ai-model-hub` sigue siendo opt-in con
  `AI_MODEL_HUB_ENABLE_UI_VALIDATION=1`.

En topología `local`, antes de limpiar datos o ejecutar suites, `Level 6`
comprueba que los hostnames públicos del entorno sean accesibles desde la
máquina que lanza el framework. Si esta comprobación falla, revisa que
`minikube tunnel` siga abierto en otra terminal. Si esa terminal muestra
`[sudo] password for <user>:`, introduce la contraseña Linux/WSL en esa misma
terminal y vuelve a lanzar el nivel.

Ese preflight público forma parte del comportamiento esperado del framework en
`local`. `Level 6` completo debe ejecutarse contra la ruta pública del entorno,
no contra `port-forward` como camino principal.

En modo estable local, `Level 6` ejecuta además una guarda de estabilidad de
Kubernetes antes de arrancar las suites. La guarda espera a que el nodo y los
pods relevantes estén listos, registra reinicios y eventos `NodeNotReady`, y
deja evidencia en:

```text
local_stability_preflight.json
local_stability_postflight.json
```

Si el runtime local no queda listo tras la ventana de espera, el framework falla
pronto con un mensaje accionable en lugar de ejecutar suites sobre un clúster
claramente inestable. Para diagnóstico excepcional puede desactivarse con
`PIONERA_LOCAL_STABILITY_CHECKS=false`. La ventana puede ajustarse con
`PIONERA_LOCAL_STABILITY_TIMEOUT_SECONDS` y
`PIONERA_LOCAL_STABILITY_POLL_SECONDS`.

Después de ese check general, `Level 6` hace preflights específicos del adapter
antes de abrir Playwright:

- `inesdata`: valida Keycloak, los servicios `*-interface` y la ruta pública
  `http://<connector>.../inesdata-connector-interface/`. Si falla, deja
  `ui/inesdata/portal_readiness.json` dentro del experimento.
- `edc`: valida Keycloak, dashboard, proxy y rutas públicas del dashboard y
  management API. Si falla, deja `ui/edc/dashboard_readiness.json`.

Para validaciones sobre conectores ya desplegados, ejecuta `Level 6` desde el
mismo checkout que ejecutó `Level 4`. Los artefactos locales bajo
`deployers/<adapter>/deployments/<environment>/<dataspace>/` contienen
credenciales generadas para Keycloak, MinIO y conectores. Si se valida desde
otro checkout con artefactos distintos, pueden aparecer errores como
`invalid_grant`, `Invalid user credentials` o `InvalidAccessKeyId`.

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

El framework no arranca Playwright solo porque Kubernetes reporte pods o
endpoints listos. Primero espera a que las rutas HTTP públicas necesarias del
adapter respondan realmente. Esto reduce flakes por `503`, proxys aún no
sincronizados o portales todavía no accesibles a través de Ingress.

Comandos típicos:

```bash
python3 main.py inesdata validate --topology local
python3 main.py edc validate --topology local
```

## Limpieza de Datos de Prueba

La validación puede empezar con limpieza para facilitar trazabilidad y evitar saturación por datos de ejecuciones previas.

La limpieza debe ser segura por defecto y reportar qué eliminó o qué omitió.

## Kafka en Nivel 6

La validación funcional EDC+Kafka no es el mismo flujo que el benchmark opcional
de broker. En `Level 6`, se ejecuta automáticamente después de Newman para los
adapters compatibles y valida el recorrido `asset -> catalogo -> negociacion ->
transferencia Kafka -> consumo del topic destino`.

En modo `fast`, la preparación del broker Kafka puede empezar al inicio de
`Level 6` mientras Newman sigue ejecutándose en primer plano. En modo `stable`
local, que es el predeterminado para `local`, esa preparación se difiere hasta
la fase Kafka para reducir solapamiento operativo y mejorar reproducibilidad.

El flujo completo de `Level 6` sigue requiriendo que Keycloak, MinIO,
`registration-service` y los conectores sean accesibles por hostname público. La
parte Kafka puede usar mecanismos locales de soporte para el propio proceso del
framework, pero eso no convierte `Level 6` completo en una validación correcta
si la capa pública local no está disponible.

En topología `local`, el broker gestionado por defecto se despliega dentro de
Kubernetes. Los conectores usan el endpoint interno de cluster:

```text
framework-kafka.<namespace>.svc.cluster.local:9092
```

El framework puede usar un `port-forward` temporal para que el proceso Python
del host cree topics, produzca mensajes de prueba y verifique el topic destino.
Ese `port-forward` es un mecanismo de soporte interno de la validación, no un
endpoint público del dataspace.

Cuando interesa una variante más estable del broker Kafka local sin salir de
Kubernetes, puede usarse de forma explícita:

```bash
PIONERA_KAFKA_PROVISIONER=kubernetes-split-kraft python3 main.py edc validate --topology local
```

Esa variante sigue siendo opt-in. El modo por defecto no cambia automáticamente.

Para diagnósticos Kafka muy concretos en `local`, también existe un fallback
HTTP opt-in del framework:

```bash
PIONERA_LEVEL6_LOCAL_HTTP_PORT_FORWARD_FALLBACK=true
```

Ese fallback solo actúa como ayuda técnica de la suite Kafka cuando el flujo ya
ha llegado a esa fase. No sustituye el preflight público de `Level 6`, ni debe
usarse para declarar válida una ejecución completa que no puede acceder a los
hostnames públicos del entorno.

La consola usa mensajes neutrales bajo el nombre `Kafka transfer validation`.
Por defecto imprime resultado por par de conectores a medida que cada prueba
termina, con iconos y resumen final. El detalle incluye pasos ejecutados,
topics, mensajes producidos/consumidos, latencias y throughput. Para mostrar
muestras de IDs de mensajes en consola durante diagnóstico:

```bash
PIONERA_KAFKA_TRANSFER_LOG_MESSAGES=true python3 main.py inesdata validate --topology local
```

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
