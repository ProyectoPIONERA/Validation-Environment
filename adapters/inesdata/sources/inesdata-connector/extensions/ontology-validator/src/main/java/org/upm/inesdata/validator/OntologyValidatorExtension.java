package org.upm.inesdata.validator;

import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Provides;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.validator.spi.JsonObjectValidatorRegistry;

import static org.eclipse.edc.connector.controlplane.asset.spi.domain.Asset.EDC_ASSET_TYPE;

@Provides(OntologyValidatorExtension.class)
@Extension(OntologyValidatorExtension.NAME)
public class OntologyValidatorExtension implements ServiceExtension {

    public static final String NAME = "Ontology Validator Extension";

    @Inject
    private JsonObjectValidatorRegistry validatorRegistry;  // <---- INYECCIÓN REAL

    private Monitor monitor;

    @Override
    public String name() {
        return NAME;
    }

    @Override
    public void initialize(ServiceExtensionContext context) {
        monitor = context.getMonitor();
        monitor.info("🔥 OntologyValidatorExtension initialized!!");
    }

    @Override
    public void prepare() {

        String allowedDomain = "http://demo-ontology-hub.demo.svc.cluster.local";

        monitor.info("🧪 Registrando OntologyJsonValidator para dominio permitido: " + allowedDomain);

        // SI ESTA LÍNEA SE EJECUTA VERÁS EL LOG ARRIBA
        validatorRegistry.register(
                EDC_ASSET_TYPE,
                new OntologyJsonValidator(allowedDomain, monitor)
        );
    }
}