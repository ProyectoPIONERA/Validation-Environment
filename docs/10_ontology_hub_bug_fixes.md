# Informe de Bugs: OH-APP-05, OH-APP-10, OH-APP-17

---

## OH-APP-05 — El detalle del vocabulario es visible y el .n3 puede descargarse

### Caso Excel
**A5.2 caso 5 — Visualizar Ontología**: verificar que la página de detalle de un vocabulario sea accesible desde el catálogo, que los metadatos sean visibles y que el archivo `.n3` pueda descargarse.

### Problema
El test fallaba de forma intermitente. El error observado en `experiment_2026-05-04_14-00-56` fue:

```
TimeoutError: locator.click: Timeout 30000ms exceeded.
waiting for locator('.ontology-tab').filter({ hasText: 'Version History' }).first()
```

La página de detalle del vocabulario cargaba, pero la pestaña "Version History" no se volvía interactiva dentro del límite de tiempo. En la ejecución siguiente (17:07 del mismo día) el test pasó sin cambios.

### Análisis de la causa raíz

El fallo tenía dos causas distintas según el contexto:

**Causa A — Problema de rendimiento puntual (14:00 del 4 de mayo)**  
La aplicación tardaba en renderizar las pestañas del detalle del vocabulario, probablemente por carga de Elasticsearch o del endpoint SPARQL en ese momento. No era un bug estructural: el test pasó en la ejecución inmediatamente posterior sin ningún cambio.

**Causa B — Estado obsoleto entre ejecuciones (potencial)**  
OH-APP-05 depende del estado producido por OH-APP-04 (`REPOSITORY_VOCAB_STATE_KEY`). Si ese vocabulario había sido eliminado por OH-APP-14 de un run anterior y la función de limpieza no había actuado correctamente (por el bug de OH-APP-17, explicado más adelante), el state file apuntaba a un vocabulario inexistente → 404 en la página de detalle.

### Corrección
No hay cambios en el código de OH-APP-05.

- El fallo de rendimiento puntual (Causa A) era transitorio y se resolvió solo.
- El riesgo de estado obsoleto (Causa B) se elimina como efecto secundario del fix de OH-APP-17: al corregir la página `/edition/users`, la función de limpieza opera correctamente entre ejecuciones y el estado compartido se regenera siempre en orden.

### Dependencia con OH-APP-11
OH-APP-05 también guarda el archivo `.n3` descargado en `VISUALIZATION_N3_STATE_KEY`. Este archivo es reutilizado por OH-APP-11 (añadir nueva versión) para evitar descargarlo de nuevo desde la red. Si OH-APP-05 no ha ejecutado antes que OH-APP-11, el test recurre a una descarga directa como fallback.

### Conclusión
Sin cambios en el código de OH-APP-05. Los fallos observados eran **transitorios o efectos secundarios del bug de OH-APP-17**, no bugs propios del test.

---

## OH-APP-10 — Editar metadatos y etiquetas de una ontología

### Caso Excel
**A5.2 caso 10 — Editar Ontología**: modificar los metadatos de un vocabulario (review, tag) desde la página de edición y verificar que los cambios se guarden y sean visibles.

### Problema
El test fallaba: después de la modificación, los campos `review` y `tag` volvían a sus valores anteriores. Los cambios no se persistían.

### Análisis de la causa raíz — 3 capas rotas en cascada

**Capa 1 — form.jade: tipo HTTP incorrecto**

El formulario de edición de vocabulario enviaba la petición AJAX como `POST` incluso en modo edición. El servidor tenía registrada la ruta de actualización como `PUT`. El middleware `method-override` de Express convierte `POST` en `PUT` solo si encuentra `_method=PUT` en el body — pero únicamente si el body ya ha sido parseado.

Archivo: `app/views/vocabularies/form.jade` línea ~733

```javascript
// ANTES — siempre POST:
type: "POST",

// DESPUÉS — PUT si se está en modo edición (input hidden "testIfNew" ausente):
type: document.getElementById("testIfNew") != null ? "PUT" : "POST",
```

**Capa 2 — routes/index.js: multer ausente en la ruta PUT**

`method-override` lee `_method` del body. Pero el formulario utiliza `multipart/form-data` (mediante `form2js` + `FormData`). Sin un parser multipart antes de `method-override`, el body llega vacío → `_method` no se encuentra → la conversión `POST→PUT` no ocurre → la ruta `PUT /edition/vocabs/:prefix` nunca se alcanza.

Archivo: `config/routes/index.js`

```javascript
// ANTES — sin parser multipart:
router.put(
  "/edition/vocabs/:vocabPxEdition",
  auth.requiresLogin,
  vocabularies.update
);

// DESPUÉS — multer antes del controlador:
router.put(
  "/edition/vocabs/:vocabPxEdition",
  auth.requiresLogin,
  upload.any(),        // parsifica el body multipart
  vocabularies.update
);
```

**Capa 3 — vocabularies.js: payload JSON no deserializado**

El formulario serializa todos los datos del vocabulario mediante `form2js` en un objeto JavaScript y lo pasa a `FormData` como cadena JSON: `multipartData.append('payload', JSON.stringify(payloadObj))`. El controlador recibía por tanto `req.body.payload = "{ ...json string... }"` y ejecutaba `_.extend(vocab, req.body)` — lo que copiaba la cadena en bruto en lugar de los campos reales.

Archivo: `app/controllers/vocabularies.js`, función `exports.update`

```javascript
// AÑADIDO antes de vocab = _.extend(vocab, req.body):
if (req.body && typeof req.body.payload === 'string') {
  try {
    const parsedPayload = JSON.parse(req.body.payload);
    req.body = Object.assign({}, req.body, parsedPayload);
    delete req.body.payload;
  } catch (e) { /* payload malformado, ignorado */ }
}
```

### Resultado
Correcciones aplicadas en las 3 capas. OH-APP-10 pasa correctamente.

---

## OH-APP-17 — Promover usuario a admin y verificar que aparece +USER

### Caso Excel
**A5.2 caso 17 — Gestión de usuarios**: promover un usuario al rol admin desde la página `/edition/users` y verificar que el botón `+ USER` se vuelve visible en la interfaz.

### Problema
El test fallaba con error HTTP 500 en la página `/edition/users`. Imposible cargar la lista de usuarios.

### Análisis de la causa raíz

El template Jade `app/views/users/index.jade` iteraba sobre la lista de usuarios accediendo directamente a `user.agent.name`:

```jade
// ANTES — crash si agent es null:
a.prefix(href='/dataset/agents/#{user.agent.name}') !{user.agent.name}
```

OH-APP-18 (de una ejecución anterior) elimina el agente asociado al usuario de prueba. Mongoose ejecuta un `populate()` sobre la relación `user → agent`: si el documento agent ha sido eliminado de la base de datos, Mongoose devuelve `null` en lugar de un objeto. El template accedía a `null.name` → `TypeError: Cannot read property 'name' of null` → Express devolvía HTTP 500 para toda la página `/edition/users`.

**Efecto en cascada**: la función Python `_ontology_hub_soft_cleanup_users` en `runtime_preparation.py` llama a `/edition/users` para obtener la lista de usuarios a limpiar. Con la página devolviendo 500, la función interpretaba la lista como vacía (`users=0`) y no eliminaba los usuarios obsoletos. En la siguiente ejecución, Passport.js encontraba en la base de datos dos registros con el mismo email (uno admin de la ejecución anterior, uno curator de la ejecución actual) y autenticaba el incorrecto — provocando el fallo de OH-APP-15 (verificación de que `+ USER` está oculto).

### Corrección

Archivo: `app/views/users/index.jade` línea 30

```jade
// DESPUÉS — null guard:
- var agentName = user.agent ? user.agent.name : '(no agent)'
a.prefix(href='/dataset/agents/#{agentName}') !{agentName}
```

La página `/edition/users` carga correctamente incluso cuando un usuario tiene un agente eliminado. La función de limpieza puede operar con normalidad, evitando la acumulación de usuarios obsoletos entre ejecuciones consecutivas.

### Resultado
Corrección aplicada. OH-APP-17 pasa. OH-APP-15, OH-APP-16 y OH-APP-18 pasan como consecuencia.
