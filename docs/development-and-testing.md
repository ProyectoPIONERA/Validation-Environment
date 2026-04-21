# Desarrollo y Testing

## Flujo Seguro de Desarrollo

Trabaja con cambios pequeños y valídalos con pruebas focalizadas antes de ejecutar suites amplias.

Loop recomendado:

```bash
python3 -m unittest tests.test_main_cli
python3 -m unittest tests.test_deployer_shared_contracts
python3 -m unittest tests.test_deployer_shared_hosts_manager
```

Para cambios UI, ejecuta la suite Playwright relevante desde `validation/ui/`.

## Extender Deployers

La lógica compartida de deployers pertenece a:

```text
deployers/infrastructure/lib/
```

El comportamiento específico de un adapter pertenece a:

```text
deployers/<adapter>/
adapters/<adapter>/
```

Evita añadir comportamiento específico de un adapter en helpers compartidos si no está parametrizado explícitamente.

## Extender Topologías

La resolución de topología está centralizada en:

```text
deployers/infrastructure/lib/topology.py
deployers/shared/lib/topology.py
```

El contexto del deployer debe describir:

- nombre de topología;
- dirección por defecto;
- direcciones por rol;
- IP externa de ingress;
- modo de routing.

La ejecución real de una topología solo debe habilitarse después de implementar y probar sus preflights.

## Extender Validaciones

Las nuevas validaciones deben seguir este orden:

1. Añadir checks API cuando sea posible.
2. Añadir checks UI solo para comportamiento visible.
3. Añadir limpieza de datos generados.
4. Guardar artefactos en `experiments/`.
5. Añadir pruebas focalizadas de orquestación y configuración.

## Ficheros Generados y Sensibles

No subas:

- `deployer.config` locales;
- despliegues generados;
- salidas de experimentos;
- reportes Playwright;
- repositorios fuente locales bajo carpetas ignoradas;
- contexto interno de desarrollo.

Usa `.gitignore` como fuente de verdad antes de preparar commits.

## Suites Amplias

Algunas suites legacy amplias pueden requerir servicios externos o suposiciones antiguas. Para desarrollo diario, prioriza pruebas focalizadas del área modificada y amplía cobertura cuando el entorno esté preparado.
