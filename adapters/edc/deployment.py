"""Deployment helpers for the generic EDC adapter."""

import os
import shutil

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

    def _stage_shared_dataspace_credentials(self):
        """Move shared Level 3 credentials into the EDC runtime tree.

        The transitional EDC Level 3 flow reuses the INESData bootstrap script,
        which writes some credentials relative to its own deployer directory.
        For auditability, the generated EDC dataspace state must live under
        deployers/edc/deployments instead of deployers/inesdata/deployments.
        """
        delegate_config = getattr(getattr(self, "_delegate", None), "config", None)
        source_repo_getter = getattr(delegate_config, "repo_dir", None)
        if not callable(source_repo_getter):
            return None

        dataspace_getter = getattr(self.config_adapter, "primary_dataspace_name", None)
        environment_getter = getattr(self.config_adapter, "deployment_environment_name", None)
        runtime_getter = getattr(self.config_adapter, "edc_dataspace_runtime_dir", None)
        if not (callable(dataspace_getter) and callable(environment_getter) and callable(runtime_getter)):
            return None

        dataspace = str(dataspace_getter() or "").strip()
        environment = str(environment_getter() or "DEV").strip().upper() or "DEV"
        if not dataspace:
            return None

        source_dir = os.path.join(source_repo_getter(), "deployments", environment, dataspace)
        source_file = os.path.join(source_dir, f"credentials-dataspace-{dataspace}.json")
        if not os.path.isfile(source_file):
            return None

        target_dir = runtime_getter(ds_name=dataspace)
        target_file = os.path.join(target_dir, os.path.basename(source_file))
        os.makedirs(target_dir, exist_ok=True)

        if os.path.abspath(source_file) != os.path.abspath(target_file):
            shutil.copy2(source_file, target_file)
            try:
                os.remove(source_file)
                if os.path.isdir(source_dir) and not os.listdir(source_dir):
                    os.rmdir(source_dir)
            except OSError as exc:
                print(f"Warning: could not clean transitional EDC Level 3 artifact {source_file}: {exc}")
        return target_file

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
            self._stage_shared_dataspace_credentials()
            self.infrastructure.complete_level(3)
            return True

        self._delegate.connectors_adapter = self.connectors_adapter
        result = self._delegate.deploy_dataspace()
        self._stage_shared_dataspace_credentials()
        return result

    def build_recreate_dataspace_plan(self):
        self._delegate.connectors_adapter = self.connectors_adapter
        return self._delegate.build_recreate_dataspace_plan()

    def recreate_dataspace(self, confirm_dataspace=None):
        self._delegate.connectors_adapter = self.connectors_adapter
        return self._delegate.recreate_dataspace(confirm_dataspace=confirm_dataspace)

    def describe(self) -> str:
        return "EDCDeploymentAdapter reuses the local dataspace deployment flow for generic EDC."
