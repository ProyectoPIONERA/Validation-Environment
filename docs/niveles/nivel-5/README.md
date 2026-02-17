# NIVEL 5 – Creación lógica del Dataspace

### Propósito
Crear de forma lógica un dataspace de INESData y generar los artefactos de configuración necesarios para su despliegue posterior. Este nivel ejecuta operaciones declarativas a través del Deployer, sin aplicar cambios directos sobre la infraestructura Kubernetes ni sobre los servicios comunes, en el contexto de la validación definida en A5.2.

### Ruta
```
pionera-env/
```

### Ejecutar `dataspace-create.py` (automatización)
> **Precondiciones técnicas:**
> El entorno Deployer debe encontrarse preparado conforme a lo establecido en el NIVEL 4, incluyendo entorno virtual activo, túneles a los servicios comunes y disponibilidad del fichero `deployer.config`.

Este script se ejecuta de forma no interactiva, idempotente y QA-safe y:
- invoca al Deployer para crear el dataspace a nivel lógico,
- normaliza los ficheros values.yaml generados,
- prepara artefactos consistentes para su uso en el despliegue Helm del NIVEL 6.

```bash
export VAULT_ADDR=http://127.0.0.1:8200
python adapters/inesdata/dataspace/dataspace-create.py
```
### Verificación
```bash
ls runtime/workdir/inesdata-deployment/dataspace/step-1/values-demo.yaml
ls runtime/workdir/inesdata-deployment/dataspace/step-2/values-demo.yaml
```
**Ejemplo de salida esperada**
```text
runtime/workdir/inesdata-deployment/dataspace/step-1/values-demo.yaml
runtime/workdir/inesdata-deployment/dataspace/step-2/values-demo.yaml
```

### Artefactos generados
```text
runtime/workdir/inesdata-deployment/dataspace/step-1/values-demo.yaml
runtime/workdir/inesdata-deployment/dataspace/step-2/values-demo.yaml
```

### Criterios de aceptación
- El dataspace lógico ha sido creado sin errores.
- Los ficheros `values-demo.yaml` existen en las rutas esperadas.
- Los artefactos generados están listos para su uso directo por Helm en el NIVEL 6.

---

⬅️ [Nivel anterior: Nivel 4 – Preparación del entorno Deployer](../nivel-4/README.md)  
➡️ [Siguiente nivel: Nivel 6 – Despliegue del Dataspace](../nivel-6/README.md)
🏠 [Volver al README principal](/README.md)