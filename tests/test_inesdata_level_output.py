import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.inesdata.deployment import INESDataDeploymentAdapter
from adapters.inesdata.infrastructure import INESDataInfrastructureAdapter


class LevelOutputConfig:
    MINIKUBE_DRIVER = "docker"
    MINIKUBE_CPUS = 2
    MINIKUBE_MEMORY = "4096"
    NS_COMMON = "common"
    DS_NAME = "demo"

    def __init__(self, root):
        self.root = root

    def repo_dir(self):
        return os.path.join(self.root, "repo")

    def common_dir(self):
        return os.path.join(self.repo_dir(), "common")

    def values_path(self):
        return os.path.join(self.common_dir(), "values.yaml")

    def script_dir(self):
        return self.root

    def helm_release_common(self):
        return "common-srvs"

    def vault_keys_path(self):
        return os.path.join(self.root, "vault.json")

    def deployer_config_path(self):
        return os.path.join(self.root, "deployer.config")

    def generate_hosts(self):
        return []

    def namespace_demo(self):
        return "demo-ns"

    def python_exec(self):
        return "python3"

    def venv_path(self):
        return os.path.join(self.repo_dir(), ".venv")

    def repo_requirements_path(self):
        return os.path.join(self.repo_dir(), "requirements.txt")

    def registration_db_name(self):
        return "registration"

    def webportal_db_name(self):
        return "webportal"

    def registration_db_user(self):
        return "registration"

    def webportal_db_user(self):
        return "webportal"

    def registration_values_file(self):
        return os.path.join(self.registration_service_dir(), "values.yaml")

    def registration_service_dir(self):
        return os.path.join(self.repo_dir(), "dataspace", "registration-service")

    def helm_release_rs(self):
        return "registration-service"


class LevelOutputConfigAdapter:
    def copy_local_deployer_config(self):
        return None

    def generate_hosts(self, _ds_name):
        return []

    def load_deployer_config(self):
        return {"KC_URL": "http://keycloak.local"}


class FakeConnectorsAdapter:
    def force_clean_postgres_db(self, _db_name, _db_user):
        return None


class InesdataLevelOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.config = LevelOutputConfig(self.tmpdir.name)
        os.makedirs(self.config.common_dir(), exist_ok=True)
        os.makedirs(self.config.registration_service_dir(), exist_ok=True)
        with open(self.config.values_path(), "w", encoding="utf-8") as handle:
            handle.write("key: value\n")
        with open(self.config.registration_values_file(), "w", encoding="utf-8") as handle:
            handle.write("key: value\n")

        self.config_adapter = LevelOutputConfigAdapter()

    @staticmethod
    def _run(*_args, **_kwargs):
        return object()

    @staticmethod
    def _run_silent(*_args, **_kwargs):
        return ""

    def _make_infrastructure(self):
        return INESDataInfrastructureAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )

    def test_setup_cluster_prints_header_once_and_complete_on_success(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_unix_environment = lambda: None
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.wait_for_kubernetes_ready = lambda: True
        infrastructure.verify_cluster_ready_for_level2 = lambda: (True, None)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.setup_cluster()
            infrastructure.announce_level(1, "CLUSTER SETUP")
            infrastructure.complete_level(1)

        rendered = output.getvalue()
        self.assertEqual(rendered.count("LEVEL 1 - CLUSTER SETUP"), 1)
        self.assertEqual(rendered.count("LEVEL 1 COMPLETE"), 1)

    def test_deploy_infrastructure_does_not_print_complete_on_failure(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.sync_common_values = lambda: None
        infrastructure.reconcile_common_services_source_of_truth = lambda: None
        infrastructure.manage_hosts_entries = lambda _entries: None
        infrastructure.add_helm_repos = lambda: None
        infrastructure.deploy_helm_release = lambda *_args, **_kwargs: True
        infrastructure.wait_for_level2_service_pods = lambda *_args, **_kwargs: True
        infrastructure.wait_for_vault_pod = lambda *_args, **_kwargs: True
        infrastructure.setup_vault = lambda *_args, **_kwargs: True
        infrastructure.sync_vault_token_to_deployer_config = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (False, "pods unstable")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(RuntimeError):
                infrastructure.deploy_infrastructure()

        rendered = output.getvalue()
        self.assertEqual(rendered.count("LEVEL 2 - DEPLOY COMMON SERVICES"), 1)
        self.assertNotIn("LEVEL 2 COMPLETE", rendered)

    def test_deploy_dataspace_prints_complete_when_successful(self):
        infrastructure = self._make_infrastructure()
        deployment = INESDataDeploymentAdapter(
            run=lambda cmd, **_kwargs: "127.0.0.1" if cmd == "minikube ip" else object(),
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        deployment.connectors_adapter = FakeConnectorsAdapter()
        infrastructure.ensure_local_infra_access = lambda: True
        infrastructure.ensure_vault_unsealed = lambda: True
        infrastructure.deploy_helm_release = lambda *_args, **_kwargs: True
        infrastructure.wait_for_namespace_pods = lambda *_args, **_kwargs: True
        infrastructure.verify_dataspace_ready_for_level4 = lambda: (True, None)
        deployment.restart_registration_service = lambda: None
        deployment.update_helm_values_with_host_aliases = lambda *_args, **_kwargs: None

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch(
            "adapters.inesdata.deployment.ensure_python_requirements",
            lambda *_args, **_kwargs: None,
        ), mock.patch(
            "adapters.inesdata.deployment.requests.get",
            return_value=mock.Mock(status_code=200),
        ):
            deployment.deploy_dataspace()
            infrastructure.announce_level(3, "DATASPACE")
            infrastructure.complete_level(3)

        rendered = output.getvalue()
        self.assertEqual(rendered.count("LEVEL 3 - DATASPACE"), 1)
        self.assertEqual(rendered.count("LEVEL 3 COMPLETE"), 1)


if __name__ == "__main__":
    unittest.main()
