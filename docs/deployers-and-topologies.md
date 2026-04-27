# Deployers y Topologías

## Topologías Soportadas

El framework usa estos nombres canónicos:

```text
local
vm-single
vm-distributed
```

El menú puede mostrar alias más amigables:

```text
local  máquina local
vm1    una máquina virtual
vm3    tres máquinas virtuales
```

## Comportamiento Actual

`local` es la topología por defecto y la ruta soportada para despliegue normal.

`vm-single` y `vm-distributed` ya forman parte del contexto del deployer y de la planificación de `hosts`. `vm-single` ya dispone de ejecución real para la ruta base del dataspace en `inesdata` y `edc`; `vm-distributed` sigue protegido por guardas hasta que exista una ruta Kubernetes cerrada para ese perfil.

Esta protección evita ejecutar suposiciones locales contra un entorno VM allí donde la topología todavía no está cerrada.

## Local

`local` usa Minikube.

Flujo típico:

```bash
python3 main.py menu
python3 main.py inesdata hosts --topology local --dry-run
python3 main.py edc hosts --topology local --dry-run
```

Las entradas de `hosts` normalmente resuelven a `127.0.0.1`.

El diagrama local de referencia está disponible en [Inicio rápido](./getting-started.md#vista-local).

## VM Single

`vm-single` representa una máquina virtual respaldada por Kubernetes.

Estado actual del framework:

- `inesdata`: `Level 1` a `Level 6` operativos, con `Level 5` compartido para componentes configurados
- `edc`: `Level 1` a `Level 4` y `Level 6` operativos
- `edc Level 5`: pendiente de soporte real de componentes

La topología necesita una dirección externa, suministrada mediante una de estas variables:

```text
PIONERA_VM_EXTERNAL_IP
PIONERA_VM_SINGLE_IP
PIONERA_VM_SINGLE_ADDRESS
PIONERA_HOSTS_ADDRESS
PIONERA_INGRESS_EXTERNAL_IP
```

Ejemplo:

```bash
PIONERA_VM_EXTERNAL_IP=192.0.2.10 \
python3 main.py edc hosts --topology vm-single --dry-run
```

## VM Distributed

`vm-distributed` representa una topología distribuida de validación. La primera interpretación recomendada es un único cluster Kubernetes lógico respaldado por tres nodos/VM:

```text
common    servicios comunes
provider  conector proveedor
consumer  conector consumidor
```

Los labels esperados para los nodos son:

```text
pionera.role=common
pionera.role=provider
pionera.role=consumer
```

Esto valida placement físico por rol y comunicación entre nodos manteniendo un único plano de control Kubernetes. Un modo multi-cluster puede añadirse en el futuro si se convierte en requisito explícito.

## Interpretación del Diagrama VM3

El diagrama `vm3` debe leerse como una vista conceptual.

![PIONERA production validation environment](<./pionera production validation environment.png>)

En la primera implementación, `vm3` significa un único cluster Kubernetes o k3s con tres nodos respaldados por VM. Los namespaces pertenecen al cluster. Los workloads se programan sobre la VM/nodo esperado usando labels, `nodeSelector` o affinity.

La EDC Management API se considera interna u orientada a operación. Las interacciones públicas entre participantes deben ocurrir mediante los endpoints de protocolo de conector, catálogo, negociación y transferencia.

## Routing

El modelo de routing por defecto es host-based:

```text
keycloak.<domain>
minio.<domain>
registration-service-<dataspace>.<ds-domain>
conn-<connector>-<dataspace>.<ds-domain>
```

El routing path-based puede añadirse más adelante si un único dominio público se convierte en requisito estricto.
