# NIVEL 6 – Despliegue del Dataspace (infraestructura)

### Propósito
Materializar en infraestructura Kubernetes el dataspace definido de forma lógica en el NIVEL 5, desplegando los componentes necesarios para su funcionamiento operativo. Este nivel aplica cambios controlados sobre la infraestructura (base de datos y servicios) de forma reproducible y QA-safe, en el contexto de la validación definida en A5.2.

### Ruta
```
pionera-env/
```

### Ejecutar `dataspace-deploy.py` (automatización)
> **Precondiciones técnicas:**
> - El dataspace debe haber sido creado lógicamente en el NIVEL 5.
> - Debe existir el fichero values-demo.yaml en `runtime/workdir/inesdata-deployment/dataspace/step-1/`.
> - Los servicios comunes (PostgreSQL) deben encontrarse operativos conforme al NIVEL 2.

Este script se ejecuta de forma no interactiva, idempotente y QA-safe y:
- verifica la disponibilidad real de PostgreSQL,
- ejecuta un reset controlado de la base de datos del dataspace,
- despliega el `registration-service` mediante Helm (`Step-1`),
- garantiza la existencia y alineación de `ConfigMap` y `Secret` usados por el Deployment,
- fuerza un reinicio controlado del servicio para asegurar la correcta aplicación de la configuración,
- garantiza la inicialización del esquema EDC requerido (`edc_participant`).
```bash
kubectl create namespace demo
python adapters/inesdata/dataspace/dataspace-deploy.py
```

### Verificación
```bash
kubectl get ns demo

kubectl get pods -n demo
```
**Ejemplo de salida esperada**
```text

$ kubectl create namespace demo
namespace/demo created

$ kubectl get ns demo
NAME   STATUS   AGE
demo   Active   10s

NAME                                         READY   STATUS    RESTARTS   AGE
demo-registration-service-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
```
### Criterios de aceptación
- El namespace del dataspace (`demo`) existe y es accesible.
- El pod `demo-registration-service` se encuentra en estado `Running`.
- La base de datos del dataspace ha sido creada y asociada correctamente.
- El Deployment utiliza `ConfigMap` y `Secret` reales del clúster.
- El servicio queda listo para su uso en los niveles posteriores (NIVEL 7 – conectores).

---

⬅️ [Nivel anterior: Nivel 5 – Creación lógica del Dataspace](../nivel-5/README.md)  
➡️ [Siguiente nivel: Nivel 7 – Creación lógica del Conector](../nivel-7/README.md)
🏠 [Volver al README principal](/README.md)