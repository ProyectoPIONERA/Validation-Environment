"""Deployment helpers for the generic EDC adapter."""

import os

from adapters.inesdata.config import InesdataConfig
from adapters.inesdata.deployment import INESDataDeploymentAdapter

from .config import EDCConfigAdapter, EdcConfig


class EdcSharedDataspaceConfig(EdcConfig):
    """Transitional Level 3 config that reuses the shared dataspace runtime."""

    REPO_DIR = InesdataConfig.REPO_DIR
    RUNTIME_LABEL = "shared dataspace"
    QUIET_REQUIREMENTS_INSTALL = True
    QUIET_SENSITIVE_DEPLOYER_OUTPUT = True

    @classmethod
    def python_exec(cls):
        return os.path.join(cls.venv_path(), "bin", "python")


class EDCDeploymentAdapter:
    """Thin deployment wrapper that reuses the local dataspace setup."""

    def __init__(self, run, run_silent, auto_mode_getter, infrastructure_adapter, config_adapter=None, config_cls=None, topology="local"):
        self.run = run
        self.run_silent = run_silent
        self.auto_mode_getter = auto_mode_getter
        self.infrastructure = infrastructure_adapter
        self.topology = topology or EdcConfig.DEFAULT_TOPOLOGY
        self.config = config_cls or EdcConfig
        self.config_adapter = config_adapter or EDCConfigAdapter(self.config, topology=self.topology)
        self.connectors_adapter = None
        self._delegate = INESDataDeploymentAdapter(
            run=run,
            run_silent=run_silent,
            auto_mode_getter=auto_mode_getter,
            infrastructure_adapter=infrastructure_adapter,
            config_adapter=self.config_adapter,
            config_cls=EdcSharedDataspaceConfig,
        )

    def _dataspace_namespace(self):
        namespace_getter = getattr(self.config, "namespace_demo", None)
        if callable(namespace_getter):
            namespace = namespace_getter()
            if namespace:
                return namespace

        config_adapter = getattr(self, "config_adapter", None)
        namespace_getter = getattr(config_adapter, "primary_dataspace_namespace", None)
        if callable(namespace_getter):
            namespace = namespace_getter()
            if namespace:
                return namespace

        return "demo"

    def _dataspace_ready_for_edc_level4(self):
        registration_pod_getter = getattr(self.infrastructure, "get_pod_by_name", None)
        schema_waiter = getattr(self.infrastructure, "wait_for_registration_service_schema", None)

        if not callable(registration_pod_getter):
            return False

        registration_pod = registration_pod_getter(self._dataspace_namespace(), "registration-service")
        if not registration_pod:
            return False

        if callable(schema_waiter):
            return bool(
                schema_waiter(
                    timeout=1,
                    poll_interval=1,
                    quiet=True,
                )
            )

        return True

    def deploy_dataspace(self):
        if self._dataspace_ready_for_edc_level4():
            self.infrastructure.announce_level(3, "DATASPACE")
            print("Existing shared dataspace is already ready for Level 4. Reusing it for EDC mode.")
            self.infrastructure.complete_level(3)
            return True

        self._delegate.connectors_adapter = self.connectors_adapter
        return self._delegate.deploy_dataspace()

    def build_recreate_dataspace_plan(self):
        self._delegate.connectors_adapter = self.connectors_adapter
        return self._delegate.build_recreate_dataspace_plan()

    def recreate_dataspace(self, confirm_dataspace=None):
        self._delegate.connectors_adapter = self.connectors_adapter
        return self._delegate.recreate_dataspace(confirm_dataspace=confirm_dataspace)

    def describe(self) -> str:
        return "EDCDeploymentAdapter reuses the local dataspace deployment flow for generic EDC."
