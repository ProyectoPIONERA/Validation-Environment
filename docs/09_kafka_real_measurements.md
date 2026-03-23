# Medidas Reales de Kafka

En la secuencia de evolución descrita desde [07_experiment_system.md](./07_experiment_system.md), la Fase 3 distingue dos capas complementarias:

- benchmark de broker Kafka en `kafka_metrics.json`
- validacion funcional opcional `EDC+Kafka` en `kafka_edc_results.json`

## Alcance

Esta fase mantiene las metricas de Kafka como opcionales, pero hace que su resultado sea explicito y repetible desde los caminos de ejecucion activos:

- `python main.py inesdata metrics --kafka`
- `python main.py inesdata run --kafka`
- `python inesdata.py` -> `Level 6 - Validation Tests`

Cuando se activa `LEVEL6_RUN_KAFKA_EDC=true`, `Level 6` ejecuta ademas una suite funcional inspirada en el sample oficial `Transfer06KafkaBrokerTest` de EDC.

## Salida

Toda ejecucion con Kafka habilitado debe dejar:

- `kafka_metrics.json`

Cuando la suite `EDC+Kafka` se activa en `Level 6`, la ejecucion deja además:

- `kafka_edc_results.json`
- `kafka_edc/<provider>__<consumer>.json`

El fichero debe contener siempre un estado de ejecucion:

- `completed`
- `skipped`

## Payload Completado

Cuando un broker es alcanzable, el payload incluye:

- `status`
- `topic`
- `messages_produced`
- `messages_consumed`
- `average_latency_ms`
- `p50_latency_ms`
- `p95_latency_ms`
- `p99_latency_ms`
- `throughput_messages_per_second`
- `broker_source`
- `bootstrap_servers`

## Payload Omitido

Cuando Kafka no puede alcanzarse o arrancarse, el payload sigue existiendo e incluye:

- `status=skipped`
- `reason`
- `broker_source` cuando se conozca
- `bootstrap_servers` cuando se conozcan

## Resolucion del Broker

La resolucion del broker sigue este orden:

1. variables de entorno
2. configuracion Kafka del adapter
3. overrides de ejecucion
4. arranque de contenedor Kafka gestionado por el framework

## Configuracion del Contenedor

El arranque del contenedor Kafka puede configurarse con:

- `container_env_file`
- `container_env`
- `KAFKA_EDC_STARTUP_GRACE_SECONDS` cuando la transferencia Kafka necesita unos segundos extra para estabilizar el dataplane antes de empezar a producir mensajes de medida. El valor por defecto actual es `60` segundos y la suite usa mensajes sonda antes de empezar a medir latencias reales.
- `KAFKA_EDC_PRE_RUN_SETTLE_SECONDS` cuando interesa dejar una pequeña ventana de asentamiento tras limpiar transferencias y recursos Kafka EDC anteriores. El valor por defecto actual es `10` segundos y ayuda a reducir flakes cuando el dataplane todavía está cerrando consumidores o productores viejos.

Estas opciones se gestionan desde `framework/kafka_container_factory.py` y estan pensadas para entornos reproducibles con broker securizado, como pruebas locales basadas en SASL.

La fuente de verdad de esta configuracion puede vivir en `deployer.config` mediante:

- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_CLUSTER_BOOTSTRAP_SERVERS`
- `KAFKA_CLUSTER_ADVERTISED_HOST`
- `KAFKA_TOPIC_NAME`
- `KAFKA_TOPIC_STRATEGY`
- `KAFKA_SECURITY_PROTOCOL`
- `KAFKA_CONTAINER_NAME`
- `KAFKA_CONTAINER_IMAGE`
- `KAFKA_CONTAINER_ENV_FILE`

El adapter `inesdata` reutiliza esos valores tanto para `main.py --kafka` como para `inesdata.py` en `Level 6`.

## Runtime del Conector

El framework ya deja activada en el codigo fuente local del conector la dependencia `data-plane-kafka`, que es la pieza EDC necesaria para un escenario de transferencia Kafka real.

Eso significa:

- el benchmark persistido sigue siendo de broker
- la imagen local del conector ya queda preparada para construir un runtime con soporte Kafka
- el validador `EDC+Kafka` puede ya ejercer un flujo completo `asset -> catalogo -> negociacion -> transfer Kafka-PUSH -> consumo del topic destino`
- ese flujo se ejecuta como suite opcional independiente del benchmark, para no mezclar latencia del broker con latencia del intercambio mediado por EDC

## Broker Autoaprovisionado

Cuando la suite `EDC+Kafka` no recibe un broker accesible y el framework lo autoaprovisiona, el broker se levanta con dos listeners anunciados:

- listener de host para el productor, consumidor y admin client locales
- listener de cluster para el dataplane del conector dentro de Kubernetes

Eso evita que el dataplane reciba `localhost:<puerto>` como metadato del broker, que era la causa principal de los fallos cuando la transferencia entraba en `STARTED` pero no movia mensajes reales.

## Notas

- `kafka_metrics.json` y `kafka_edc_results.json` responden a preguntas distintas y no deben compararse directamente.
- `kafka_metrics.json` mide el broker.
- `kafka_edc_results.json` mide el flujo EDC+Kafka mediado por el conector sobre un topic fuente y un topic destino.
- Si la suite `EDC+Kafka` falla mientras el benchmark pasa, el problema suele estar en el flujo de transferencia o en el runtime del conector, no en el broker base.
