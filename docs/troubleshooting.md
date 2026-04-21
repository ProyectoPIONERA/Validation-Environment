# Troubleshooting

## Las Entradas de Hosts No Resuelven

Previsualiza las entradas esperadas:

```bash
python3 main.py edc hosts --topology local --dry-run
```

Aplica entradas solo con sincronización explícita:

```bash
PIONERA_SYNC_HOSTS=true \
PIONERA_HOSTS_FILE=/etc/hosts \
python3 main.py edc hosts --topology local
```

Si una entrada ya existe, el gestor de hosts la omite en lugar de duplicarla.

## Los Servicios Minikube No Son Accesibles

En despliegues locales, mantén esto abierto en otra terminal:

```bash
minikube tunnel
```

Verifica también:

```bash
kubectl get pods -A
kubectl get ingress -A
helm list -A
```

## Falla la Autenticación Admin de Keycloak

Comprueba que:

- los servicios comunes están en ejecución;
- la URL admin de Keycloak resuelve;
- las credenciales en `deployers/infrastructure/deployer.config` son correctas;
- el fichero `hosts` contiene las entradas de Keycloak;
- el túnel local o ingress está disponible.

## EDC Rechaza la Imagen por Defecto

El despliegue real de conectores EDC requiere overrides explícitos de imagen:

```bash
PIONERA_EDC_CONNECTOR_IMAGE_NAME=validation-environment/edc-connector \
PIONERA_EDC_CONNECTOR_IMAGE_TAG=<tag> \
python3 main.py edc deploy --topology local
```

Esta protección evita desplegar una imagen por defecto no verificada.

## Una Topología VM Requiere Dirección

`vm-single` necesita una dirección de VM:

```bash
PIONERA_VM_EXTERNAL_IP=192.0.2.10 \
python3 main.py edc hosts --topology vm-single --dry-run
```

Si no hay dirección configurada, el CLI falla con un error claro de topología.

## Playwright Falla de Forma Intermitente

Comprueba:

- que la URL objetivo resuelve desde el entorno del navegador;
- que las entradas de `hosts` existen;
- que el dashboard o portal está desplegado;
- que el modo de autenticación coincide con la suite esperada;
- que el reporte en `experiments/` contiene screenshots, trazas o detalles de error.

## Se Acumulan Datos de Validación

Habilita o ejecuta limpieza previa cuando las pruebas repetidas creen demasiados datos.

La limpieza debe ser adapter-aware y escribir reporte bajo la carpeta del experimento actual.
