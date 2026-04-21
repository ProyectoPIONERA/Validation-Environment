# 12. Entorno Local de Validacion

El entorno local concentra el dataspace en un unico cluster `Minikube`. Sirve
como baseline reproducible para desarrollo, validacion API, validacion UI,
componentes y experimentos.

![PIONERA local validation environment](<./pionera local validation environment.png>)

## Capas

| Capa | Elementos |
| --- | --- |
| Infraestructura | `Minikube`, `ingress`, `minikube tunnel` |
| Servicios comunes | PostgreSQL, Keycloak, MinIO, Vault |
| Dataspace | `registration-service`, public portal INESData cuando aplica |
| Conectores | Provider y consumer del adapter activo |
| Componentes | `ontology-hub`, `ai-model-hub` cuando estan habilitados |
| Validacion | Newman, Playwright, validaciones de componentes, metricas |

## Namespaces Locales

| Rol | Namespace habitual |
| --- | --- |
| Servicios comunes | `common-srvs` |
| Dataspace INESData | `demo` por defecto |
| Dataspace EDC | namespace configurado, por ejemplo `demoedc` |
| Componentes | namespace del dataspace o namespace de componentes configurado |

Los nombres reales se resuelven desde `deployers/<adapter>/deployer.config`,
variables `PIONERA_*` y los defaults del deployer.

## Servicios Comunes

Los servicios comunes son compartidos por los adapters:

- PostgreSQL para persistencia;
- Keycloak para identidad y clientes tecnicos;
- MinIO para almacenamiento S3;
- Vault para secretos y material criptografico.

Los charts fuente viven en `deployers/shared/common/`. Los ficheros runtime con
secretos o valores generados no se versionan.

## Dataspace y Conectores

`Level 3` despliega el dataspace base. `Level 4` despliega los conectores del
adapter activo:

| Adapter | Runtime de conectores |
| --- | --- |
| `inesdata` | Conectores INESData con interfaz propia |
| `edc` | Runtime EDC generico con dashboard EDC |

La convencion local de host para conectores es:

```text
conn-<connector>-<dataspace>.dev.ds.dataspaceunit.upm
```

La interfaz INESData no vive en la raiz del host. Se accede normalmente con:

```text
http://conn-<connector>-<dataspace>.dev.ds.dataspaceunit.upm/inesdata-connector-interface
```

El dashboard EDC usa:

```text
http://conn-<connector>-<dataspace>.dev.ds.dataspaceunit.upm/edc-dashboard/
```

## Hosts Locales

El framework puede planificar y aplicar entradas en `/etc/hosts` o en el fichero
indicado por `PIONERA_HOSTS_FILE`. La sincronizacion es idempotente: las entradas
existentes se omiten y solo se agregan las faltantes.

Comando de planificacion:

```bash
python3 main.py edc hosts --topology local --dry-run
```

Comando de aplicacion:

```bash
PIONERA_SYNC_HOSTS=true python3 main.py edc hosts --topology local
```

## Artefactos Runtime

Cada deployer escribe sus artefactos generados bajo:

```text
deployers/<adapter>/deployments/<ENV>/<dataspace>/
```

Estas carpetas pueden contener credenciales, certificados, policies, values de
Helm y configuraciones generadas. Por eso permanecen ignoradas por Git.

## Validacion

`Level 6` ejecuta la validacion integral:

- Newman para flujos API;
- Playwright del adapter activo;
- comprobaciones MinIO/storage;
- validaciones de componentes cuando el perfil las habilita;
- persistencia del resultado en `experiments/`.
