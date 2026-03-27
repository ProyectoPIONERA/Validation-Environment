package org.upm.inesdata.validator;

import jakarta.json.JsonObject;
import jakarta.json.JsonString;
import jakarta.json.JsonValue;
import org.eclipse.edc.validator.spi.ValidationResult;
import org.eclipse.edc.validator.spi.Validator;
import org.eclipse.edc.spi.monitor.Monitor;

import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;

public class OntologyJsonValidator implements Validator<JsonObject> {

    private final Monitor monitor;
    private final String allowedDomain;

    public OntologyJsonValidator(String allowedDomain, Monitor monitor) {
        this.allowedDomain = allowedDomain;
        this.monitor = monitor;
    }

    @Override
    public ValidationResult validate(JsonObject input) {

        monitor.info("[OntologyValidator] Start validation.");

        Map<String, String> flat = new HashMap<>();
        flattenJson("", input, flat);

        String foundKey = null;
        String url = null;

        for (var e : flat.entrySet()) {
            if (e.getKey().endsWith("urlOntologyHub")) {
                foundKey = e.getKey();
                url = e.getValue();
                break;
            }
        }

        if (foundKey == null) {
            monitor.info("[OntologyValidator] No urlOntologyHub found.");
            return ValidationResult.success();
        }

        String cleanPath = normalizePath(foundKey);

        if (url == null || url.isBlank()) {
            monitor.info("[OntologyValidator] urlOntologyHub empty → success.");
            return ValidationResult.success();
        }

        // Validación de dominio — WARNING, no error
        if (allowedDomain != null && !allowedDomain.isBlank()) {
            if (!url.startsWith(allowedDomain)) {
                monitor.warning("[OntologyValidator] WARNING: Domain not allowed: " + url);
                return ValidationResult.success();  // ⚠️ NO bloquear
            }
        }

        // HEAD request para validar existencia
        try {
            URL target = new URL(url);
            HttpURLConnection http = (HttpURLConnection) target.openConnection();
            http.setRequestMethod("HEAD");
            http.setConnectTimeout(3000);
            http.setReadTimeout(3000);
            http.connect();

            int code = http.getResponseCode();
            monitor.info("[OntologyValidator] HEAD=" + code);

            if (code == 404 || code == 400) {
                monitor.warning("[OntologyValidator] WARNING: URL unreachable: HTTP " + code);
                return ValidationResult.success(); // ⚠️ NO bloquear
            }

        } catch (Exception e) {
            monitor.warning("[OntologyValidator] WARNING: Error reaching URL: " + e.getMessage());
            return ValidationResult.success(); // ⚠️ NO bloquear
        }

        return ValidationResult.success();
    }

    // Normaliza rutas JSON‑LD largas
    private String normalizePath(String path) {
        if (path == null) return "urlOntologyHub";
        String[] parts = path.split("\\.");
        StringBuilder sb = new StringBuilder();
        for (String p : parts) {
            if (p.startsWith("http")) {
                int i = p.lastIndexOf("/");
                if (i != -1 && i < p.length()-1) p = p.substring(i+1);
            }
            if (sb.length() > 0) sb.append(".");
            sb.append(p);
        }
        return sb.toString();
    }

    // Flatten JSON‑LD
    private void flattenJson(String prefix, JsonValue value, Map<String, String> flat) {
        switch (value.getValueType()) {

            case OBJECT:
                JsonObject obj = value.asJsonObject();

                if (obj.containsKey("@value")) {
                    flat.put(prefix, obj.getString("@value"));
                    return;
                }

                for (String key : obj.keySet()) {
                    String next = prefix.isEmpty() ? key : prefix + "." + key;
                    flattenJson(next, obj.get(key), flat);
                }
                break;

            case ARRAY:
                for (JsonValue item : value.asJsonArray()) {
                    flattenJson(prefix, item, flat);
                }
                break;

            case STRING:
                flat.put(prefix, ((JsonString) value).getString());
                break;

            default:
                flat.put(prefix, value.toString());
        }
    }
}
