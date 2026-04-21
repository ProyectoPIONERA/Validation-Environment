# Validation Environment

Framework de validación para desplegar y probar entornos de dataspace PIONERA de forma reproducible.

El framework soporta adapters para:

- `inesdata`;
- `edc`.

La entrada principal es `main.py`.

## Inicio Rápido

```bash
bash scripts/bootstrap_framework.sh
python3 main.py menu
```

Comandos útiles:

```bash
python3 main.py inesdata deploy --topology local
python3 main.py edc validate --topology local
python3 main.py edc hosts --topology local --dry-run
python3 main.py inesdata metrics --topology local
```

## Documentación

La documentación pública y estable está en [docs/](./docs/README.md).

Orden recomendado:

- [Inicio rápido](./docs/getting-started.md)
- [Referencia del menú](./docs/menu-reference.md)
- [Arquitectura](./docs/architecture.md)
- [Deployers y topologías](./docs/deployers-and-topologies.md)
- [Adapters](./docs/adapters.md)
- [Validación](./docs/validation.md)
- [Desarrollo y testing](./docs/development-and-testing.md)
- [Troubleshooting](./docs/troubleshooting.md)

## Topologías

Topologías canónicas:

```text
local
vm-single
vm-distributed
```

`local` es la ruta de despliegue normal y usa Minikube. Las topologías VM se modelan en el contexto del deployer y en la planificación de hosts; la ejecución real no-local queda protegida por guardas hasta que la ruta Kubernetes correspondiente esté implementada para cada nivel.

## Estructura Principal

```text
main.py                         CLI y menú guiado
framework/                      lógica reutilizable de validación, métricas y reportes
adapters/                       comportamiento específico por adapter
deployers/                      deployers, configuración y artefactos de despliegue
validation/                     suites Newman, Playwright y validaciones de componentes
tests/                          pruebas unitarias
docs/                           documentación pública estable
```

## Artefactos Generados

No deben subirse al repositorio:

- `deployer.config` locales;
- `experiments/`;
- `deployers/*/deployments/`;
- reportes Playwright;
- repositorios fuente locales bajo carpetas ignoradas;
- `context/`.
