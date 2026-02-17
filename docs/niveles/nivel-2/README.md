# NIVEL 2 – Instalación base de INESData (servicios comunes)

### Propósito
Proporcionar a INESData un conjunto mínimo de servicios comunes operativos, necesarios para habilitar la creación y gestión de dataspaces y conectores. Este nivel establece el estado base requerido del sistema para poder ejecutar de forma controlada los escenarios de validación definidos en la actividad A5.2.


> **Precondiciones técnicas:**  
> El entorno debe disponer de kubectl y helm operativos, así como de los artefactos de configuración requeridos para los servicios comunes. Estas precondiciones son verificadas automáticamente por el script.
> Clonar este repositorio e ingresar a la carpeta `pionera-env/` (`clon-pionera-env`)

Este comando despliega los servicios comunes de INESData de forma no interactiva, idempotente y QA-safe, aplicando validaciones previas y mecanismos de limpieza controlada en caso de fallo.
---

### Ruta
```text
pionera-env/
```

### Eliminar credsStore
Desvincular WSL de Docker desktop


```bash
nano ~/.docker/config.json
# Dejar vacía la configuración
# Antes
{
  "credsStore": "desktop"
}
# Después
{}

```



### Instalar los siguientes repositorios es necesario en INESData
```bash
helm repo add minio https://charts.min.io/
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update
```

### Ejecutar `install.py` (automatización)

```bash
pip install PyYAML
python3 adapters/inesdata/bootstrap.py
python3 adapters/inesdata/normalize/normalize-base.py
python3 adapters/inesdata/install.py # Esperar algunos minutos
```

### Verificación
```bash
kubectl get pods -n common-srvs
```
**Ejemplo de salida esperada**
```text
NAME                                   READY   STATUS    RESTARTS   AGE
common-srvs-postgresql-0               1/1     Running   0          2m
common-srvs-keycloak-0                 1/1     Running   0          2m
common-srvs-vault-0                    0/1     Running   0          2m
common-srvs-minio-0                    1/1     Running   0          2m
```
**Criterio de aceptación**
Todos los pods del namespace common-srvs se encuentran en estado Running.

---

⬅️ [Nivel anterior: Nivel 1 – Creación del clúster Kubernetes local](../nivel-1/README.md)  
➡️ [Siguiente nivel: Nivel 3 – Post-configuración de Vault y Deployer](../nivel-3/README.md)
🏠 [Volver al README principal](/README.md)