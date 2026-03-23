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
    PORT_KEYCLOAK = 18081

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
        return {
            "KC_URL": "http://keycloak.local",
            "KC_USER": "admin",
            "KC_PASSWORD": "secret",
        }


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

    def test_setup_vault_reuses_existing_keys_when_status_is_temporarily_unavailable(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = lambda *_args, **_kwargs: "vault-0"
        infrastructure.wait_for_pod_running = lambda *_args, **_kwargs: True

        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"unseal_keys_hex":["abc"],"root_token":"root"}')

        infrastructure._read_vault_status = mock.Mock(
            side_effect=[
                (None, "vault status unavailable"),
                ({"initialized": True, "sealed": False}, None),
            ]
        )
        infrastructure.run_silent = mock.Mock(side_effect=[
            "unsealed",
            '{"secret/": {}}',
        ])

        self.assertTrue(infrastructure.setup_vault())
        called_commands = [call.args[0] for call in infrastructure.run_silent.call_args_list]
        self.assertFalse(any("vault operator init" in cmd for cmd in called_commands))
        self.assertTrue(any("vault operator unseal" in cmd for cmd in called_commands))

    def test_ensure_vault_unsealed_recovers_with_existing_keys_when_status_is_temporarily_unavailable(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = lambda *_args, **_kwargs: "vault-0"

        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"unseal_keys_hex":["abc"],"root_token":"root"}')

        infrastructure._read_vault_status = mock.Mock(
            side_effect=[
                (None, "vault status unavailable"),
                ({"initialized": True, "sealed": False}, None),
            ]
        )
        infrastructure.run = mock.Mock(return_value=object())

        self.assertTrue(infrastructure.ensure_vault_unsealed(timeout=2, poll_interval=1))
        infrastructure.run.assert_called_once()
        self.assertIn("vault operator unseal abc", infrastructure.run.call_args.args[0])

    def test_deploy_infrastructure_continues_when_helm_fails_but_release_exists(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.sync_common_values = lambda: None
        infrastructure.reconcile_common_services_source_of_truth = lambda: None
        infrastructure.manage_hosts_entries = lambda _entries: None
        infrastructure.add_helm_repos = lambda: None
        infrastructure.deploy_helm_release = lambda *_args, **_kwargs: False
        infrastructure._common_services_release_exists = lambda: True
        infrastructure.wait_for_level2_service_pods = lambda *_args, **_kwargs: True
        infrastructure.wait_for_vault_pod = lambda *_args, **_kwargs: True
        infrastructure.setup_vault = lambda *_args, **_kwargs: True
        infrastructure.sync_vault_token_to_deployer_config = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.deploy_infrastructure()

        rendered = output.getvalue()
        self.assertIn("Helm reported a post-install failure", rendered)
        self.assertIn("LEVEL 2 COMPLETE", rendered)

    def test_deploy_infrastructure_uses_extended_pre_vault_timeout_for_service_readiness(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.sync_common_values = lambda: None
        infrastructure.reconcile_common_services_source_of_truth = lambda: None
        infrastructure.manage_hosts_entries = lambda _entries: None
        infrastructure.add_helm_repos = lambda: None
        infrastructure.deploy_helm_release = lambda *_args, **_kwargs: True
        infrastructure.wait_for_vault_pod = lambda *_args, **_kwargs: True
        infrastructure.setup_vault = lambda *_args, **_kwargs: True
        infrastructure.sync_vault_token_to_deployer_config = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)
        infrastructure.config.TIMEOUT_POD_WAIT = 120

        seen = {}

        def fake_wait_for_level2_service_pods(*args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return True

        infrastructure.wait_for_level2_service_pods = fake_wait_for_level2_service_pods

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.deploy_infrastructure()

        self.assertEqual(seen["args"][0], infrastructure.config.NS_COMMON)
        self.assertEqual(seen["kwargs"]["timeout"], 180)

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
        deployment.wait_for_keycloak_admin_ready = lambda *_args, **_kwargs: True
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

    def test_wait_for_keycloak_admin_ready_retries_until_token_is_available(self):
        deployment = INESDataDeploymentAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=self._make_infrastructure(),
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        responses = iter([
            mock.Mock(status_code=401, json=lambda: {}),
            mock.Mock(status_code=200, json=lambda: {"access_token": "token"}),
        ])

        with mock.patch("adapters.inesdata.deployment.requests.post", side_effect=lambda *args, **kwargs: next(responses)):
            result = deployment.wait_for_keycloak_admin_ready("http://keycloak.local", "admin", "secret", timeout=1, poll_interval=0)

        self.assertTrue(result)

    def test_wait_for_keycloak_admin_ready_falls_back_to_local_port_forward(self):
        infrastructure = self._make_infrastructure()
        infrastructure.port_forward_service = mock.Mock(return_value=True)
        deployment = INESDataDeploymentAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )

        responses = iter([
            Exception("connection refused"),
            mock.Mock(status_code=200, json=lambda: {"access_token": "token"}),
        ])

        def fake_post(*_args, **_kwargs):
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch("adapters.inesdata.deployment.requests.post", side_effect=fake_post):
            result = deployment.wait_for_keycloak_admin_ready(
                "http://keycloak-admin.local",
                "admin",
                "secret",
                timeout=5,
                poll_interval=0,
            )

        self.assertTrue(result)
        infrastructure.port_forward_service.assert_called_once_with("common", "keycloak", 18081, 8080, quiet=True)

    def test_wait_for_level2_service_pods_allows_pre_setup_vault_running_state(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.NS_COMMON = "common"
        infrastructure.config.TIMEOUT_POD_WAIT = 1
        snapshots = iter([
            "\n".join([
                "common-srvs-keycloak-0 1/1 Running 0 1m",
                "common-srvs-minio-0 1/1 Running 0 1m",
                "common-srvs-postgresql-0 1/1 Running 0 1m",
                "common-srvs-vault-0 0/1 Running 0 1m",
            ]),
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_level2_service_pods("common", timeout=1, require_vault_ready=False)

        self.assertTrue(result)
        self.assertIn("Core services detected", output.getvalue())

    def test_wait_for_level2_service_pods_ignores_completed_hook_pods(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.NS_COMMON = "common"
        infrastructure.config.TIMEOUT_POD_WAIT = 1
        snapshots = iter([
            "\n".join([
                "common-srvs-keycloak-0 1/1 Running 0 1m",
                "common-srvs-minio-56c96fbbdf-abcde 1/1 Running 0 1m",
                "common-srvs-minio-post-job-xyz 0/1 Completed 0 1m",
                "common-srvs-postgresql-0 1/1 Running 0 1m",
                "common-srvs-vault-0 0/1 Running 0 1m",
            ]),
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_level2_service_pods("common", timeout=1, require_vault_ready=False)

        self.assertTrue(result)
        self.assertIn("Core services detected", output.getvalue())

    def test_wait_for_level2_service_pods_requires_vault_readiness_for_final_check(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.NS_COMMON = "common"
        infrastructure.config.TIMEOUT_POD_WAIT = 1
        snapshots = iter([
            "\n".join([
                "common-srvs-keycloak-0 1/1 Running 0 1m",
                "common-srvs-minio-0 1/1 Running 0 1m",
                "common-srvs-postgresql-0 1/1 Running 0 1m",
                "common-srvs-vault-0 0/1 Running 0 1m",
            ]),
            "\n".join([
                "common-srvs-keycloak-0 1/1 Running 0 1m",
                "common-srvs-minio-0 1/1 Running 0 1m",
                "common-srvs-postgresql-0 1/1 Running 0 1m",
                "common-srvs-vault-0 0/1 Running 0 1m",
            ]),
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_level2_service_pods("common", timeout=1, require_vault_ready=True)

        self.assertFalse(result)
        self.assertNotIn("Level 2 core services detected", output.getvalue())

    def test_wait_for_level2_service_pods_ignores_keycloak_config_cli_error(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.NS_COMMON = "common"
        infrastructure.config.TIMEOUT_POD_WAIT = 1
        snapshots = iter([
            "\n".join([
                "common-srvs-keycloak-0 1/1 Running 0 1m",
                "common-srvs-keycloak-config-cli-abcde 0/1 Error 1 10s",
                "common-srvs-minio-0 1/1 Running 0 1m",
                "common-srvs-postgresql-0 1/1 Running 0 1m",
                "common-srvs-vault-0 0/1 Running 0 1m",
            ]),
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_level2_service_pods("common", timeout=1, require_vault_ready=False)

        self.assertTrue(result)
        self.assertIn("Core services detected", output.getvalue())

    def test_deploy_infrastructure_uses_short_timeout_for_first_common_services_install(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.sync_common_values = lambda: None
        infrastructure.reconcile_common_services_source_of_truth = lambda: None
        infrastructure.manage_hosts_entries = lambda _entries: None
        infrastructure.add_helm_repos = lambda: None
        infrastructure._common_services_release_exists = lambda: False
        infrastructure.wait_for_level2_service_pods = lambda *_args, **_kwargs: True
        infrastructure.wait_for_vault_pod = lambda *_args, **_kwargs: True
        infrastructure.setup_vault = lambda *_args, **_kwargs: True
        infrastructure.sync_vault_token_to_deployer_config = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)

        seen = {}

        def fake_deploy(*_args, **kwargs):
            seen.update(kwargs)
            return True

        infrastructure.deploy_helm_release = fake_deploy

        infrastructure.deploy_infrastructure()

        self.assertEqual(seen.get("timeout_seconds"), 45)

    def test_deploy_infrastructure_does_not_force_short_timeout_for_existing_common_release(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.sync_common_values = lambda: None
        infrastructure.reconcile_common_services_source_of_truth = lambda: None
        infrastructure.manage_hosts_entries = lambda _entries: None
        infrastructure.add_helm_repos = lambda: None
        infrastructure._common_services_release_exists = lambda: True
        infrastructure.wait_for_level2_service_pods = lambda *_args, **_kwargs: True
        infrastructure.wait_for_vault_pod = lambda *_args, **_kwargs: True
        infrastructure.setup_vault = lambda *_args, **_kwargs: True
        infrastructure.sync_vault_token_to_deployer_config = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)

        seen = {}

        def fake_deploy(*_args, **kwargs):
            seen.update(kwargs)
            return True

        infrastructure.deploy_helm_release = fake_deploy

        infrastructure.deploy_infrastructure()

        self.assertIsNone(seen.get("timeout_seconds"))

    def test_wait_for_pods_ignores_ingress_nginx_admission_hook_jobs(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.TIMEOUT_POD_WAIT = 1
        snapshots = iter([
            "\n".join([
                "ingress-nginx-admission-create-sbjn6 0/1 Completed 0 1m",
                "ingress-nginx-admission-patch-8jwl2 0/1 Error 3 1m",
                "ingress-nginx-controller-596f8778bc-62hpq 0/1 Running 0 1m",
            ]),
            "\n".join([
                "ingress-nginx-admission-create-sbjn6 0/1 Completed 0 1m",
                "ingress-nginx-admission-patch-8jwl2 0/1 Error 3 1m",
                "ingress-nginx-controller-596f8778bc-62hpq 1/1 Running 0 1m",
            ]),
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch(
            "adapters.inesdata.infrastructure.time.sleep",
            return_value=None,
        ):
            result = infrastructure.wait_for_pods("ingress-nginx", timeout=1)

        self.assertTrue(result)
        self.assertIn("All pods are running and ready", output.getvalue())

    def test_wait_for_namespace_stability_ignores_ingress_nginx_admission_hook_jobs(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.TIMEOUT_NAMESPACE = 1
        infrastructure._pod_snapshot = lambda *_args, **_kwargs: [
            {
                "name": "ingress-nginx-admission-create-sbjn6",
                "ready": "0/1",
                "status": "Completed",
                "restarts": "0",
            },
            {
                "name": "ingress-nginx-admission-patch-8jwl2",
                "ready": "0/1",
                "status": "Error",
                "restarts": "3",
            },
            {
                "name": "ingress-nginx-controller-596f8778bc-62hpq",
                "ready": "1/1",
                "status": "Running",
                "restarts": "0",
            },
        ]

        clock = iter([0.0, 0.0, 0.01, 0.02, 0.03])
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch(
            "adapters.inesdata.infrastructure.time.time",
            side_effect=lambda: next(clock),
        ), mock.patch(
            "adapters.inesdata.infrastructure.time.sleep",
            return_value=None,
        ):
            result = infrastructure.wait_for_namespace_stability(
                "ingress-nginx",
                duration=0.01,
                poll_interval=0,
            )

        self.assertTrue(result)
        self.assertIn("Namespace 'ingress-nginx' is stable", output.getvalue())

    def test_wait_for_namespace_pods_ignores_keycloak_config_cli_error(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.TIMEOUT_NAMESPACE = 1
        snapshots = iter([
            "\n".join([
                "common-srvs-keycloak-config-cli-abcde 0/1 Error 1 10s",
                "common-srvs-keycloak-0 1/1 Running 0 1m",
            ]),
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_namespace_pods("common", timeout=1)

        self.assertTrue(result)
        self.assertIn("Pods ready:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
