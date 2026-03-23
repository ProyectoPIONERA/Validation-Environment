from itertools import permutations
import os

from .newman_executor import NewmanExecutor
from .experiment_storage import ExperimentStorage


class ValidationEngine:
    """Runs dataspace validation tests.

    Prepares Newman environment variables, executes validation collections,
    and orchestrates interoperability tests between connector pairs.
    """

    def __init__(
        self,
        newman_executor=None,
        load_connector_credentials=None,
        load_deployer_config=None,
        cleanup_test_entities=None,
        validation_test_entities_absent=None,
        ds_domain_resolver=None,
        ds_name="demo",
        transfer_storage_verifier=None,
    ):
        self.newman_executor = newman_executor or NewmanExecutor()
        self.load_connector_credentials = load_connector_credentials
        self.load_deployer_config = load_deployer_config
        self.cleanup_test_entities = cleanup_test_entities
        self.validation_test_entities_absent = validation_test_entities_absent
        self.ds_domain_resolver = ds_domain_resolver
        self.ds_name = ds_name
        self.transfer_storage_verifier = transfer_storage_verifier
        self.last_storage_checks = []

    def _require_dependency(self, dependency, name):
        if dependency is None:
            raise RuntimeError(f"ValidationEngine requires dependency: {name}")
        return dependency

    def build_newman_env(self, provider, consumer):
        """Build Newman environment variables for dataspace validation."""
        load_connector_credentials = self._require_dependency(
            self.load_connector_credentials,
            "load_connector_credentials"
        )
        load_deployer_config = self._require_dependency(
            self.load_deployer_config,
            "load_deployer_config"
        )
        ds_domain_resolver = self._require_dependency(
            self.ds_domain_resolver,
            "ds_domain_resolver"
        )

        provider_creds = load_connector_credentials(provider)
        consumer_creds = load_connector_credentials(consumer)

        if not provider_creds or not consumer_creds:
            raise ValueError("Missing connector credentials")

        config = load_deployer_config()

        ds_domain = ds_domain_resolver()
        dataspace = self.ds_name
        keycloak_url = config.get("KC_INTERNAL_URL") or config.get("KC_URL")

        if not keycloak_url.startswith("http"):
            keycloak_url = f"http://{keycloak_url}"

        return {
            "provider": provider,
            "consumer": consumer,
            "provider_user": provider_creds["connector_user"]["user"],
            "provider_password": provider_creds["connector_user"]["passwd"],
            "consumer_user": consumer_creds["connector_user"]["user"],
            "consumer_password": consumer_creds["connector_user"]["passwd"],
            "dsDomain": ds_domain,
            "dataspace": dataspace,
            "keycloakUrl": keycloak_url,
            "keycloakClientId": "dataspace-users",
            "providerProtocolAddress": f"http://{provider}:19194/protocol",
            "consumerProtocolAddress": f"http://{consumer}:19194/protocol",
            "e2e_expected_provider_bucket": f"{dataspace}-{provider}",
            "e2e_expected_consumer_bucket": f"{dataspace}-{consumer}",
        }

    def run_dataspace_validation(self, provider, consumer, experiment_dir=None, run_index=None):
        """Run dataspace validation tests for a provider-consumer pair."""
        cleanup_test_entities = self._require_dependency(
            self.cleanup_test_entities,
            "cleanup_test_entities"
        )
        validation_test_entities_absent = self._require_dependency(
            self.validation_test_entities_absent,
            "validation_test_entities_absent"
        )

        print(f"\n=== Testing pair ===")
        print(f"Provider : {provider}")
        print(f"Consumer : {consumer}\n")

        cleanup_test_entities(provider)
        cleanup_test_entities(consumer)

        for connector in (provider, consumer):
            is_clean, lingering_entities = validation_test_entities_absent(connector)
            if not is_clean:
                lingering = ", ".join(lingering_entities)
                print(
                    f"Warning: legacy test entities still exist after cleanup in "
                    f"{connector} ({lingering})"
                )

        report_dir = None
        if experiment_dir:
            pair_dir = f"{provider}__{consumer}"
            base_report_dir = ExperimentStorage.newman_reports_dir(experiment_dir)
            if run_index is not None:
                base_report_dir = os.path.join(base_report_dir, f"run_{int(run_index):03d}")
            report_dir = os.path.join(base_report_dir, pair_dir)
            os.makedirs(report_dir, exist_ok=True)

        env_vars = self.build_newman_env(provider, consumer)
        baseline_snapshot = None
        baseline_reason = None
        if self.transfer_storage_verifier is not None and experiment_dir:
            try:
                baseline_snapshot = self.transfer_storage_verifier.capture_consumer_bucket_snapshot(
                    consumer,
                    env_vars["e2e_expected_consumer_bucket"],
                )
            except Exception as exc:
                baseline_reason = str(exc)

        reports = self.newman_executor.run_validation_collections(env_vars, report_dir=report_dir)

        if self.transfer_storage_verifier is not None and report_dir:
            storage_check = self.transfer_storage_verifier.verify_consumer_transfer_persistence(
                provider,
                consumer,
                report_dir,
                before_snapshot=baseline_snapshot,
                baseline_reason=baseline_reason,
                experiment_dir=experiment_dir,
            )
            self.last_storage_checks.append(storage_check)

        return reports

    def run_all_dataspace_tests(self, connectors, experiment_dir=None, run_index=None):
        """Run dataspace interoperability tests for all connector pairs."""
        print("\n========================================")
        print("DATASPACE INTEROPERABILITY TESTS")
        print("========================================\n")

        pairs = list(permutations(connectors, 2))
        exported_reports = []
        self.last_storage_checks = []

        for provider, consumer in pairs:
            reports = self.run_dataspace_validation(
                provider,
                consumer,
                experiment_dir=experiment_dir,
                run_index=run_index,
            )
            if reports:
                exported_reports.extend(reports)

        return exported_reports

    def run(self, connectors, experiment_dir=None, run_index=None):
        """Generic entry point for experiment orchestration."""
        return self.run_all_dataspace_tests(connectors, experiment_dir=experiment_dir, run_index=run_index)

    def describe(self) -> str:
        return "ValidationEngine runs dataspace validation tests."

