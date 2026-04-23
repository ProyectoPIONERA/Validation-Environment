package org.upm.inesdata.validator.model;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ValidationReport {
    public final String transferId;
    public final String assetId;
    /** Filled when {@code DataFlowStartMessage} has no assetId but the transfer process does (e.g. provider PUSH). */
    public String resolvedAssetId;
    public final String destinationType;
    public final Instant timestamp = Instant.now();
    public ValidationStatus status = ValidationStatus.SKIPPED;
    public String format = "unknown";
    public String message = "";
    public String ontologyUrl = "";
    public String shaclUrl = "";
    public final List<String> errors = new ArrayList<>();

    public ValidationReport(String transferId, String assetId, String destinationType) {
        this.transferId = transferId;
        this.assetId = assetId;
        this.resolvedAssetId = assetId;
        this.destinationType = destinationType;
    }

    public String effectiveAssetId() {
        if (resolvedAssetId != null && !resolvedAssetId.isBlank()) {
            return resolvedAssetId;
        }
        return assetId;
    }

    public String toJson() {
        var escapedErrors = errors.stream()
                .map(ValidationReport::escapeJson)
                .map(s -> "\"" + s + "\"")
                .reduce((a, b) -> a + "," + b)
                .orElse("");

        return "{"
                + "\"transferId\":\"" + escapeJson(transferId) + "\","
                + "\"assetId\":\"" + escapeJson(effectiveAssetId() == null ? "" : effectiveAssetId()) + "\","
                + "\"destinationType\":\"" + escapeJson(destinationType == null ? "" : destinationType) + "\","
                + "\"status\":\"" + escapeJson(status.name()) + "\","
                + "\"format\":\"" + escapeJson(format) + "\","
                + "\"message\":\"" + escapeJson(message) + "\","
                + "\"ontologyUrl\":\"" + escapeJson(ontologyUrl) + "\","
                + "\"shaclUrl\":\"" + escapeJson(shaclUrl) + "\","
                + "\"timestamp\":\"" + timestamp + "\","
                + "\"errors\":[" + escapedErrors + "]"
                + "}";
    }

    public Map<String, String> toPersistableProperties() {
        var properties = new LinkedHashMap<String, String>();
        properties.put(ValidationPersistenceKeys.STATUS, status != null ? status.name() : ValidationStatus.SKIPPED.name());
        properties.put(ValidationPersistenceKeys.MESSAGE, safeValue(message));
        properties.put(ValidationPersistenceKeys.TRANSFER_ID, safeValue(transferId));
        properties.put(ValidationPersistenceKeys.ASSET_ID, safeValue(effectiveAssetId()));
        properties.put(ValidationPersistenceKeys.FORMAT, safeValue(format));
        properties.put(ValidationPersistenceKeys.ONTOLOGY_URL, safeValue(ontologyUrl));
        properties.put(ValidationPersistenceKeys.SHACL_URL, safeValue(shaclUrl));
        properties.put(ValidationPersistenceKeys.ERRORS, String.join("; ", errors));
        properties.put(ValidationPersistenceKeys.TIMESTAMP, timestamp.toString());
        return properties;
    }

    private static String safeValue(String value) {
        return value == null ? "" : value;
    }

    private static String escapeJson(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
