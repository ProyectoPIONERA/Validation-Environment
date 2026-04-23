package org.upm.inesdata.validator.persistence;

import org.eclipse.edc.connector.controlplane.transfer.spi.store.TransferProcessStore;
import org.eclipse.edc.spi.monitor.Monitor;
import org.upm.inesdata.validator.model.ValidationReport;

import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

/**
 * Persists RDF validation snapshots into {@link org.eclipse.edc.connector.controlplane.transfer.spi.types.TransferProcess}
 * {@code privateProperties} under {@code inesdata.rdf.validation.*}.
 * <p>
 * Always re-loads the transfer from the store immediately before merge+save to avoid overwriting
 * control-plane state advances (lost update) with a stale in-memory entity.
 */
public class TransferProcessValidationPersistence {
    private final TransferProcessStore transferProcessStore;
    private final Monitor monitor;

    public TransferProcessValidationPersistence(TransferProcessStore transferProcessStore, Monitor monitor) {
        this.transferProcessStore = transferProcessStore;
        this.monitor = monitor;
    }

    /**
     * Loads the latest {@code TransferProcess} by id, merges only RDF validation keys, then saves.
     */
    public void persistByTransferId(String transferId, ValidationReport report, String contextLabel) {
        if (transferId == null || transferId.isBlank()) {
            monitor.debug("Skip RDF validation persist: blank transferId context=" + contextLabel);
            return;
        }
        try {
            var latest = transferProcessStore.findById(transferId);
            if (latest == null) {
                monitor.debug("TransferProcess not found while persisting RDF validation report. transferId=" + transferId + " context=" + contextLabel);
                return;
            }
            if (!mergeRdfValidationPrivateProperties(latest, report)) {
                monitor.warning("Unable to merge privateProperties for RDF report transfer " + transferId + " (" + contextLabel + ")");
                return;
            }
            if (!saveTransferProcess(latest)) {
                monitor.warning("Unable to save TransferProcess while persisting RDF report for transfer " + transferId + " (" + contextLabel + ")");
            }
        } catch (Exception e) {
            monitor.warning("Unable to persist RDF validation report for transfer " + transferId
                    + " (" + contextLabel + "): " + describeException(e));
        }
    }

    /**
     * @deprecated Use {@link #persistByTransferId(String, ValidationReport, String)} so the entity is always re-fetched.
     * This method delegates by id and ignores any stale fields on the passed instance.
     */
    @Deprecated
    public void persist(org.eclipse.edc.connector.controlplane.transfer.spi.types.TransferProcess transferProcess,
                        ValidationReport report,
                        String contextLabel) {
        if (transferProcess == null || transferProcess.getId() == null) {
            return;
        }
        persistByTransferId(transferProcess.getId(), report, contextLabel);
    }

    private boolean mergeRdfValidationPrivateProperties(
            org.eclipse.edc.connector.controlplane.transfer.spi.types.TransferProcess transferProcess,
            ValidationReport report
    ) {
        var updates = report.toPersistableProperties();
        var combined = new HashMap<String, Object>();
        var existing = transferProcess.getPrivateProperties();
        if (existing != null) {
            combined.putAll(existing);
        }
        for (var e : updates.entrySet()) {
            combined.put(e.getKey(), e.getValue());
        }
        return applyPrivatePropertiesMap(transferProcess, combined);
    }

    private boolean applyPrivatePropertiesMap(
            org.eclipse.edc.connector.controlplane.transfer.spi.types.TransferProcess transferProcess,
            Map<String, Object> combined
    ) {
        try {
            var privateProperties = transferProcess.getPrivateProperties();
            if (privateProperties != null) {
                for (var e : combined.entrySet()) {
                    privateProperties.put(e.getKey(), e.getValue());
                }
                return true;
            }
        } catch (Exception e) {
            monitor.debug("Mutable privateProperties put failed, trying reflection: " + describeException(e));
        }

        try {
            var field = findField(transferProcess.getClass(), "privateProperties");
            if (field != null) {
                field.setAccessible(true);
                field.set(transferProcess, new HashMap<>(combined));
                return true;
            }
        } catch (Exception e) {
            monitor.debug("Unable to set TransferProcess.privateProperties by reflection: " + describeException(e));
        }

        return false;
    }

    private boolean saveTransferProcess(org.eclipse.edc.connector.controlplane.transfer.spi.types.TransferProcess transferProcess) {
        var storeClass = transferProcessStore.getClass();
        var persisted = invokeStoreMethod(storeClass, "save", transferProcess);
        if (persisted) {
            return true;
        }
        return invokeStoreMethod(storeClass, "update", transferProcess);
    }

    private boolean invokeStoreMethod(Class<?> storeClass,
                                      String methodName,
                                      org.eclipse.edc.connector.controlplane.transfer.spi.types.TransferProcess transferProcess) {
        for (Method method : storeClass.getMethods()) {
            if (!method.getName().equals(methodName) || method.getParameterCount() != 1) {
                continue;
            }
            if (!method.getParameterTypes()[0].isAssignableFrom(transferProcess.getClass())) {
                continue;
            }
            try {
                method.invoke(transferProcessStore, transferProcess);
                return true;
            } catch (Exception e) {
                monitor.debug("TransferProcessStore." + methodName + " failed for transfer "
                        + transferProcess.getId() + ": " + describeException(e));
            }
            return false;
        }
        return false;
    }

    private java.lang.reflect.Field findField(Class<?> type, String name) {
        var current = type;
        while (current != null) {
            try {
                return current.getDeclaredField(name);
            } catch (NoSuchFieldException ignored) {
                current = current.getSuperclass();
            }
        }
        return null;
    }

    private String describeException(Exception e) {
        var message = e.getMessage();
        return e.getClass().getSimpleName() + (message != null ? (": " + message) : "");
    }
}
