# Adapters

## Propósito

Los adapters aíslan el comportamiento específico de cada implementación de dataspace.

Los adapters actuales son:

```text
adapters/inesdata/
adapters/edc/
```

Cada adapter puede aportar:

- operaciones de despliegue;
- descubrimiento de conectores;
- generación de URLs;
- carga de credenciales;
- limpieza de datos;
- configuración específica de validación;
- soporte para construir imágenes locales.

## Adapter INESData

El adapter INESData soporta el despliegue basado en INESData.

Configuración relevante:

```text
deployers/infrastructure/deployer.config
deployers/inesdata/deployer.config
```

Deployer relevante:

```text
deployers/inesdata/deployer.py
```

Los componentes opcionales se configuran en el `deployer.config` del adapter y se despliegan en el nivel 5 cuando están habilitados.

## Adapter EDC

El adapter EDC soporta un despliegue EDC genérico.

Configuración relevante:

```text
deployers/infrastructure/deployer.config
deployers/edc/deployer.config
```

Deployer relevante:

```text
deployers/edc/deployer.py
```

El adapter EDC puede construir o usar una imagen de conector configurada. El despliegue real rechaza valores por defecto inseguros salvo que se indiquen overrides explícitos.

Variables comunes de override:

```text
PIONERA_EDC_CONNECTOR_IMAGE_NAME
PIONERA_EDC_CONNECTOR_IMAGE_TAG
```

El dashboard EDC es opcional y sirve como apoyo visual para validación UI. Las validaciones API con Newman siguen siendo el mecanismo principal de validación end-to-end.

## Añadir un Adapter

Para añadir otro adapter:

1. Crear `adapters/<name>/`.
2. Crear `deployers/<name>/`.
3. Implementar un deployer con el contrato compartido.
4. Registrar adapter y deployer en `main.py`.
5. Definir el perfil de validación por defecto.
6. Añadir pruebas unitarias focalizadas.
7. Añadir documentación pública solo cuando el comportamiento sea estable.
