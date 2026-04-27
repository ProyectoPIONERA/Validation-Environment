import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.inesdata.deployment import INESDataDeploymentAdapter
from adapters.inesdata.infrastructure import INESDataInfrastructureAdapter
from adapters.shared.infrastructure import SharedFoundationInfrastructureAdapter


class LevelOutputConfig:
    MINIKUBE_DRIVER = "docker"
    MINIKUBE_CPUS = 2
    MINIKUBE_MEMORY = "4096"
    NS_COMMON = "common"
    DS_NAME = "demo"
    PORT_KEYCLOAK = 18081
    PORT_POSTGRES = 5432
    PORT_VAULT = 8200
    PORT_MINIO = 9000
    PORT_REGISTRATION_SERVICE = 18080
    TIMEOUT_PORT = 30
    TIMEOUT_POD_WAIT = 120
    TIMEOUT_NAMESPACE = 90

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

    def registration_service_namespace(self):
        return "demo-core-ns"

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
    def __init__(self, deployer_config=None):
        self.deployer_config = dict(deployer_config or {})

    def copy_local_deployer_config(self):
        return None

    def generate_hosts(self, _ds_name):
        return []

    def load_deployer_config(self):
        base = {
            "KC_URL": "http://keycloak.local",
            "KC_USER": "admin",
            "KC_PASSWORD": "secret",
        }
        base.update(self.deployer_config)
        return base

    def get_pg_credentials(self):
        return ("127.0.0.1", "postgres", "postgres")

    def get_pg_port(self):
        return "5432"


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

    def test_setup_cluster_warns_when_ingress_addon_enable_times_out_but_verification_passes(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_unix_environment = lambda: None
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.wait_for_kubernetes_ready = lambda: True
        infrastructure.verify_cluster_ready_for_level2 = lambda: (True, None)
        infrastructure.run = mock.Mock(return_value=object())
        infrastructure.run_silent = mock.Mock(
            side_effect=lambda command, *_args, **_kwargs: None
            if command == "minikube -p minikube addons enable ingress"
            else ""
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.setup_cluster()

        self.assertIn(
            "Warning: minikube reported a transient ingress addon enable failure",
            output.getvalue(),
        )

    def test_setup_cluster_uses_minikube_settings_from_shared_deployer_config(self):
        self.config_adapter = LevelOutputConfigAdapter(
            {
                "MINIKUBE_DRIVER": "docker",
                "MINIKUBE_CPUS": "4",
                "MINIKUBE_MEMORY": "8192",
                "MINIKUBE_PROFILE": "vm-local",
            }
        )
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_unix_environment = lambda: None
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.wait_for_kubernetes_ready = lambda: True
        infrastructure.verify_cluster_ready_for_level2 = lambda: (True, None)
        infrastructure.run = mock.Mock(return_value=object())
        infrastructure.run_silent = mock.Mock(return_value="")

        with contextlib.redirect_stdout(io.StringIO()):
            infrastructure.setup_cluster()

        infrastructure.run.assert_any_call("minikube delete -p vm-local", check=False)
        infrastructure.run.assert_any_call(
            "minikube start -p vm-local --driver=docker --cpus=4 --memory=8192"
        )
        infrastructure.run_silent.assert_any_call("minikube -p vm-local addons enable ingress")

    def test_setup_cluster_preflight_reports_ready_for_vm_single(self):
        infrastructure = SharedFoundationInfrastructureAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        infrastructure.ensure_unix_environment = lambda: None

        command_results = {
            "which kubectl": "/usr/bin/kubectl",
            "kubectl version --client=true": "Client Version: v1.30.0",
            "which helm": "/usr/bin/helm",
            "helm version --short": "v3.15.0+g1234567",
            "kubectl config current-context": "vm-single-context",
            "kubectl cluster-info": "Kubernetes control plane is running",
            "kubectl get nodes --no-headers": "vm-node Ready control-plane 1d v1.30.0",
            "kubectl get ingressclass -o name": "ingressclass.networking.k8s.io/nginx",
            "kubectl get storageclass -o name": "storageclass.storage.k8s.io/standard",
            "kubectl auth can-i create namespace": "yes",
        }
        infrastructure.run = mock.Mock(side_effect=lambda command, **_kwargs: command_results.get(command))

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.setup_cluster_preflight(topology="vm-single")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["mode"], "preflight")
        self.assertEqual(result["topology"], "vm-single")
        self.assertEqual(result["current_context"], "vm-single-context")
        self.assertEqual(result["cluster_creation"], "skipped")
        self.assertIn("LEVEL 1 - CLUSTER PREFLIGHT", output.getvalue())
        self.assertIn("Topology 'vm-single' uses an existing Kubernetes cluster.", output.getvalue())
        self.assertEqual(result["checks"][-1]["label"], "create namespace permission")
        self.assertEqual(result["checks"][-1]["status"], "passed")

    def test_deploy_infrastructure_for_topology_skips_hosts_sync_for_vm_single(self):
        infrastructure = SharedFoundationInfrastructureAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.sync_common_values = lambda: None
        infrastructure.reconcile_common_services_source_of_truth = lambda: None
        infrastructure.manage_hosts_entries = mock.Mock()
        infrastructure.add_helm_repos = lambda: None
        infrastructure._common_services_release_exists = lambda: False
        infrastructure.deploy_helm_release = mock.Mock(return_value=True)
        infrastructure.wait_for_level2_service_pods = lambda *_args, **_kwargs: True
        infrastructure.wait_for_vault_pod = lambda *_args, **_kwargs: True
        infrastructure.setup_vault = lambda *_args, **_kwargs: True
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure._repair_failed_common_services_helm_release = lambda *_args, **_kwargs: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)
        infrastructure.run = mock.Mock(return_value=object())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.deploy_infrastructure_for_topology("vm-single")

        rendered = output.getvalue()
        self.assertIn("Skipping client-side hosts synchronization for topology 'vm-single'.", rendered)
        self.assertIn("LEVEL 2 COMPLETE", rendered)
        infrastructure.manage_hosts_entries.assert_not_called()
        infrastructure.deploy_helm_release.assert_called_once()

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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (False, "pods unstable")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(RuntimeError):
                infrastructure.deploy_infrastructure()

        rendered = output.getvalue()
        self.assertEqual(rendered.count("LEVEL 2 - DEPLOY COMMON SERVICES"), 1)
        self.assertNotIn("LEVEL 2 COMPLETE", rendered)

    def test_deploy_infrastructure_fails_without_cloning_legacy_repository(self):
        shutil.rmtree(self.config.repo_dir())
        run = mock.Mock(return_value=object())
        infrastructure = INESDataInfrastructureAdapter(
            run=run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        infrastructure.ensure_wsl_docker_config = lambda: True

        with self.assertRaisesRegex(RuntimeError, "no longer clones the legacy deployment repository"):
            infrastructure.deploy_infrastructure()

        self.assertFalse(any("git clone" in call.args[0] for call in run.call_args_list))

    def test_read_vault_status_accepts_json_stdout_when_cli_exits_nonzero(self):
        infrastructure = self._make_infrastructure()
        completed = mock.Mock(
            returncode=2,
            stdout='{"initialized": false, "sealed": true}',
            stderr="Vault is sealed",
        )

        with mock.patch("adapters.inesdata.infrastructure.subprocess.run", return_value=completed) as run:
            status, error = infrastructure._read_vault_status(
                "common-srvs-vault-0",
                "common-srvs",
                attempts=1,
                poll_interval=0,
            )

        self.assertIsNone(error)
        self.assertEqual(status["initialized"], False)
        self.assertEqual(status["sealed"], True)
        run.assert_called_once_with(
            [
                "kubectl",
                "exec",
                "common-srvs-vault-0",
                "-n",
                "common-srvs",
                "--",
                "vault",
                "status",
                "-format=json",
            ],
            text=True,
            capture_output=True,
        )

    def test_read_vault_status_retries_until_vault_cli_returns_stdout(self):
        infrastructure = self._make_infrastructure()
        responses = [
            mock.Mock(returncode=1, stdout="", stderr="connection refused"),
            mock.Mock(returncode=2, stdout='{"initialized": false, "sealed": true}', stderr="Vault is sealed"),
        ]

        with mock.patch("adapters.inesdata.infrastructure.subprocess.run", side_effect=responses), mock.patch(
            "adapters.inesdata.infrastructure.time.sleep",
        ) as sleep:
            status, error = infrastructure._read_vault_status(
                "common-srvs-vault-0",
                "common-srvs",
                attempts=2,
                poll_interval=0,
            )

        self.assertIsNone(error)
        self.assertEqual(status["initialized"], False)
        self.assertEqual(status["sealed"], True)
        sleep.assert_called_once_with(0)

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
            '{"data":{"id":"root"}}',
            '{"secret/": {}}',
        ])

        self.assertTrue(infrastructure.setup_vault())
        called_commands = [call.args[0] for call in infrastructure.run_silent.call_args_list]
        self.assertFalse(any("vault operator init" in cmd for cmd in called_commands))
        self.assertTrue(any("vault operator unseal" in cmd for cmd in called_commands))

    def test_setup_vault_fails_when_existing_root_token_is_stale(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = lambda *_args, **_kwargs: "vault-0"
        infrastructure.wait_for_pod_running = lambda *_args, **_kwargs: True

        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"unseal_keys_hex":["abc"],"root_token":"stale-root"}')

        infrastructure._read_vault_status = mock.Mock(
            return_value=({"initialized": True, "sealed": False}, None)
        )
        infrastructure.run_silent = mock.Mock(return_value=None)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertFalse(infrastructure.setup_vault())

        self.assertIn("local Vault root token is not valid", output.getvalue())
        called_commands = [call.args[0] for call in infrastructure.run_silent.call_args_list]
        self.assertTrue(any("vault token lookup" in cmd for cmd in called_commands))
        self.assertFalse(any("vault secrets enable" in cmd for cmd in called_commands))

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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)
        infrastructure._common_services_release_recoverable_after_helm_failure = mock.Mock(return_value=True)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.deploy_infrastructure()

        rendered = output.getvalue()
        self.assertIn("LEVEL 2 COMPLETE", rendered)
        infrastructure._common_services_release_recoverable_after_helm_failure.assert_called_once_with()

    def test_deploy_infrastructure_waits_for_runtime_when_helm_times_out_but_release_is_still_converging(self):
        infrastructure = self._make_infrastructure()
        infrastructure.ensure_wsl_docker_config = lambda: True
        infrastructure.sync_common_values = lambda: None
        infrastructure.reconcile_common_services_source_of_truth = lambda: None
        infrastructure.manage_hosts_entries = lambda _entries: None
        infrastructure.add_helm_repos = lambda: None
        infrastructure.deploy_helm_release = mock.Mock(return_value=False)
        infrastructure._common_services_release_exists = lambda: False
        infrastructure._common_services_release_status = mock.Mock(return_value="failed")
        infrastructure._common_services_release_recoverable_after_helm_failure = mock.Mock(
            return_value=False
        )
        infrastructure._common_services_has_terminal_runtime_errors = mock.Mock(return_value=False)
        infrastructure.wait_for_level2_service_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_vault_pod = lambda *_args, **_kwargs: True
        infrastructure.setup_vault = lambda *_args, **_kwargs: True
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure._repair_failed_common_services_helm_release = lambda *_args, **_kwargs: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.deploy_infrastructure()

        self.assertIn("LEVEL 2 COMPLETE", output.getvalue())
        self.assertIn("cold-start runtime finished converging", output.getvalue())
        infrastructure._common_services_release_recoverable_after_helm_failure.assert_called_once_with()
        infrastructure._common_services_has_terminal_runtime_errors.assert_called_once_with()
        infrastructure.wait_for_level2_service_pods.assert_called_once_with(
            infrastructure.config.NS_COMMON,
            timeout=180,
        )

    def test_deploy_infrastructure_repairs_failed_helm_release_after_runtime_readiness(self):
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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)
        infrastructure._common_services_release_status = mock.Mock(side_effect=["failed", "deployed"])
        infrastructure._common_services_release_recoverable_after_helm_failure = mock.Mock(
            side_effect=[True, False]
        )
        infrastructure.deploy_helm_release = mock.Mock(side_effect=[False, True])

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.deploy_infrastructure()

        self.assertEqual(infrastructure.deploy_helm_release.call_count, 2)
        repair_call = infrastructure.deploy_helm_release.call_args_list[1]
        self.assertEqual(repair_call.kwargs["timeout_seconds"], 180)
        rendered = output.getvalue()
        self.assertIn("Re-running Helm after runtime readiness", rendered)
        self.assertIn("Helm release status recovered to deployed", rendered)
        self.assertIn("LEVEL 2 COMPLETE", rendered)

    def test_deploy_infrastructure_skips_failed_helm_repair_for_recoverable_hook_issue(self):
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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)
        infrastructure._common_services_release_status = lambda: "failed"
        infrastructure._common_services_release_recoverable_after_helm_failure = mock.Mock(return_value=True)
        infrastructure.deploy_helm_release = mock.Mock(return_value=False)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            infrastructure.deploy_infrastructure()

        self.assertEqual(infrastructure.deploy_helm_release.call_count, 1)
        self.assertGreaterEqual(
            infrastructure._common_services_release_recoverable_after_helm_failure.call_count,
            2,
        )
        self.assertIn("Skipping Helm release repair", output.getvalue())
        self.assertIn("LEVEL 2 COMPLETE", output.getvalue())

    def test_common_services_release_status_parses_helm_json(self):
        infrastructure = self._make_infrastructure()
        infrastructure.run_silent = mock.Mock(return_value='{"info":{"status":"deployed"}}')

        self.assertEqual(infrastructure.common_services_release_status(), "deployed")
        infrastructure.run_silent.assert_called_once_with("helm status common-srvs -n common -o json")

    def test_common_services_release_recoverable_after_helm_failure_allows_only_ignored_hook_issue(self):
        infrastructure = self._make_infrastructure()
        infrastructure._common_services_release_status = lambda: "failed"
        infrastructure.run_silent = mock.Mock(
            return_value="\n".join(
                [
                    "common-srvs-keycloak-0 1/1 Running 0 1m",
                    "common-srvs-minio-0 1/1 Running 0 1m",
                    "common-srvs-minio-post-job-xyz 0/1 Error 1 10s",
                    "common-srvs-postgresql-0 1/1 Running 0 1m",
                    "common-srvs-vault-0 1/1 Running 0 1m",
                ]
            )
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure._common_services_release_recoverable_after_helm_failure()

        self.assertTrue(result)
        self.assertIn("only ignored hook pods remain outside the ready set", output.getvalue())

    def test_common_services_release_recoverable_after_helm_failure_rejects_non_hook_error_pod(self):
        infrastructure = self._make_infrastructure()
        infrastructure._common_services_release_status = lambda: "failed"
        infrastructure.run_silent = mock.Mock(
            return_value="\n".join(
                [
                    "common-srvs-keycloak-0 1/1 Running 0 1m",
                    "common-srvs-minio-0 0/1 Error 1 10s",
                    "common-srvs-postgresql-0 1/1 Running 0 1m",
                    "common-srvs-vault-0 1/1 Running 0 1m",
                ]
            )
        )

        self.assertFalse(infrastructure._common_services_release_recoverable_after_helm_failure())

    def test_common_services_has_terminal_runtime_errors_detects_non_hook_crashloop(self):
        infrastructure = self._make_infrastructure()
        infrastructure.run_silent = mock.Mock(
            return_value="\n".join(
                [
                    "common-srvs-keycloak-keycloak-config-cli-abc 0/1 Error 0 10s",
                    "common-srvs-keycloak-0 0/1 CrashLoopBackOff 3 30s",
                    "common-srvs-minio-0 1/1 Running 0 1m",
                ]
            )
        )

        self.assertTrue(infrastructure._common_services_has_terminal_runtime_errors())

    def test_verify_common_services_ready_for_level3_fails_when_helm_release_failed(self):
        infrastructure = self._make_infrastructure()
        infrastructure._common_services_release_status = lambda: "failed"
        infrastructure._common_services_release_recoverable_after_helm_failure = mock.Mock(return_value=False)
        infrastructure.wait_for_level2_service_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_namespace_stability = mock.Mock(return_value=True)
        infrastructure.ensure_vault_unsealed = mock.Mock(return_value=True)

        ready, root_cause = infrastructure.verify_common_services_ready_for_level3()

        self.assertFalse(ready)
        self.assertEqual(root_cause, "common services Helm release is failed")
        infrastructure.wait_for_level2_service_pods.assert_not_called()
        infrastructure.wait_for_namespace_stability.assert_not_called()
        infrastructure.ensure_vault_unsealed.assert_not_called()

    def test_verify_common_services_ready_for_level3_allows_recoverable_failed_release(self):
        infrastructure = self._make_infrastructure()
        infrastructure._common_services_release_status = lambda: "failed"
        infrastructure._common_services_release_recoverable_after_helm_failure = mock.Mock(return_value=True)
        infrastructure.wait_for_level2_service_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_namespace_stability = mock.Mock(return_value=True)
        infrastructure.ensure_vault_unsealed = mock.Mock(return_value=True)

        ready, root_cause = infrastructure.verify_common_services_ready_for_level3()

        self.assertTrue(ready)
        self.assertIsNone(root_cause)
        infrastructure._common_services_release_recoverable_after_helm_failure.assert_called_once_with()
        infrastructure.wait_for_level2_service_pods.assert_called_once_with(
            "common",
            timeout=300,
            require_vault_ready=True,
        )
        infrastructure.wait_for_namespace_stability.assert_called_once_with(
            "common",
            duration=12,
            poll_interval=3,
            timeout=180,
        )
        infrastructure.ensure_vault_unsealed.assert_called_once_with()

    def test_verify_common_services_ready_for_level3_fails_fast_when_helm_release_missing(self):
        infrastructure = self._make_infrastructure()
        infrastructure._common_services_release_status = lambda: None
        infrastructure.wait_for_level2_service_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_namespace_stability = mock.Mock(return_value=True)
        infrastructure.ensure_vault_unsealed = mock.Mock(return_value=True)

        ready, root_cause = infrastructure.verify_common_services_ready_for_level3()

        self.assertFalse(ready)
        self.assertEqual(root_cause, "common services Helm release not found")
        infrastructure.wait_for_level2_service_pods.assert_not_called()
        infrastructure.wait_for_namespace_stability.assert_not_called()
        infrastructure.ensure_vault_unsealed.assert_not_called()

    def test_reset_common_services_for_level4_repair_uses_temporary_vault_backup(self):
        infrastructure = self._make_infrastructure()
        infrastructure.stop_port_forward_service = mock.Mock()
        infrastructure.run = mock.Mock(return_value=object())
        infrastructure.run_silent = mock.Mock(return_value="")
        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"root_token":"stale"}')

        result = infrastructure.reset_common_services_for_level4_repair(reason="test mismatch")

        self.assertTrue(result)
        self.assertFalse(os.path.exists(self.config.vault_keys_path()))
        self.assertIsNotNone(infrastructure._vault_repair_temp_backup)
        self.assertTrue(os.path.exists(infrastructure._vault_repair_temp_backup["backup_path"]))
        infrastructure.stop_port_forward_service.assert_has_calls(
            [
                mock.call("common", "postgresql", quiet=True),
                mock.call("common", "vault", quiet=True),
                mock.call("common", "minio", quiet=True),
            ]
        )
        commands = [call.args[0] for call in infrastructure.run.call_args_list]
        self.assertIn("helm uninstall common-srvs -n common", commands)
        self.assertIn("kubectl delete namespace common --ignore-not-found=true", commands)
        infrastructure.finalize_common_services_level4_repair(success=True)
        self.assertIsNone(infrastructure._vault_repair_temp_backup)

    def test_failed_common_services_repair_restores_temporary_vault_backup(self):
        infrastructure = self._make_infrastructure()
        infrastructure.stop_port_forward_service = mock.Mock()
        infrastructure.run = mock.Mock(return_value=object())
        infrastructure.run_silent = mock.Mock(return_value="common Active")
        infrastructure._wait_for_namespace_absent = mock.Mock(return_value=False)
        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"root_token":"stale"}')

        result = infrastructure.reset_common_services_for_level4_repair(reason="test mismatch")

        self.assertFalse(result)
        self.assertTrue(os.path.exists(self.config.vault_keys_path()))
        with open(self.config.vault_keys_path(), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '{"root_token":"stale"}')
        self.assertIsNone(infrastructure._vault_repair_temp_backup)

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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
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
        infrastructure.reconcile_vault_state_for_local_runtime = mock.Mock(return_value=True)
        infrastructure.sync_common_credentials_from_kubernetes = mock.Mock(return_value=True)
        infrastructure.deploy_helm_release = lambda *_args, **_kwargs: True
        infrastructure.wait_for_dataspace_level3_pods = lambda *_args, **_kwargs: True
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
        ), mock.patch(
            "adapters.shared.deployment.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            deployment.deploy_dataspace()
            infrastructure.announce_level(3, "DATASPACE")
            infrastructure.complete_level(3)

        rendered = output.getvalue()
        self.assertEqual(rendered.count("LEVEL 3 - DATASPACE"), 1)
        self.assertEqual(rendered.count("LEVEL 3 COMPLETE"), 1)
        self.assertIn("Next step: run Level 4", rendered)
        infrastructure.reconcile_vault_state_for_local_runtime.assert_called_once()
        infrastructure.sync_common_credentials_from_kubernetes.assert_called_once()

    def test_deploy_dataspace_prefers_kc_internal_url_for_keycloak_readiness(self):
        infrastructure = self._make_infrastructure()
        deployment = INESDataDeploymentAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        deployment.connectors_adapter = FakeConnectorsAdapter()
        infrastructure.ensure_local_infra_access = mock.Mock(return_value=True)
        infrastructure.ensure_vault_unsealed = lambda: True
        infrastructure.reconcile_vault_state_for_local_runtime = mock.Mock(return_value=True)
        infrastructure.sync_common_credentials_from_kubernetes = mock.Mock(return_value=True)
        infrastructure.deploy_helm_release = lambda *_args, **_kwargs: True
        infrastructure.wait_for_dataspace_level3_pods = lambda *_args, **_kwargs: True
        infrastructure.verify_dataspace_ready_for_level4 = lambda: (True, None)
        deployment.restart_registration_service = lambda: None
        deployment.update_helm_values_with_host_aliases = mock.Mock()
        deployment.wait_for_keycloak_admin_ready = mock.Mock(return_value=True)
        deployment.config_adapter.load_deployer_config = lambda: {
            "KC_URL": "http://admin.auth.dev.ed.dataspaceunit.upm",
            "KC_INTERNAL_URL": "http://auth.dev.ed.dataspaceunit.upm",
            "KC_USER": "admin",
            "KC_PASSWORD": "secret",
        }

        with mock.patch(
            "adapters.inesdata.deployment.ensure_python_requirements",
            lambda *_args, **_kwargs: None,
        ), mock.patch(
            "adapters.inesdata.deployment.requests.get",
            return_value=mock.Mock(status_code=200),
        ) as mocked_get, mock.patch(
            "adapters.shared.deployment.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            deployment.deploy_dataspace()

        mocked_get.assert_called_once_with(
            "http://auth.dev.ed.dataspaceunit.upm/realms/master",
            timeout=5,
        )
        deployment.wait_for_keycloak_admin_ready.assert_called_once_with(
            "http://auth.dev.ed.dataspaceunit.upm",
            "admin",
            "secret",
        )

    def test_deploy_dataspace_reports_guidance_when_keycloak_urls_are_missing(self):
        infrastructure = self._make_infrastructure()
        deployment = INESDataDeploymentAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        deployment.connectors_adapter = FakeConnectorsAdapter()
        infrastructure.ensure_local_infra_access = mock.Mock(return_value=True)
        infrastructure.ensure_vault_unsealed = lambda: True
        infrastructure.reconcile_vault_state_for_local_runtime = mock.Mock(return_value=True)
        infrastructure.sync_common_credentials_from_kubernetes = mock.Mock(return_value=False)
        deployment.config_adapter.load_deployer_config = lambda: {
            "KC_USER": "admin",
            "KC_PASSWORD": "secret",
        }

        with self.assertRaises(RuntimeError) as exc:
            deployment.deploy_dataspace()

        message = str(exc.exception)
        self.assertIn("KC_INTERNAL_URL/KC_URL not defined in deployer.config", message)
        self.assertIn("deployers/infrastructure/deployer.config.example", message)

    def test_deploy_dataspace_for_vm_single_skips_tunnel_prompt_and_minikube_host_aliases(self):
        infrastructure = self._make_infrastructure()
        run = mock.Mock(return_value=object())
        deployment = INESDataDeploymentAdapter(
            run=run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        deployment.connectors_adapter = FakeConnectorsAdapter()
        infrastructure.ensure_local_infra_access = mock.Mock(return_value=True)
        infrastructure.ensure_vault_unsealed = lambda: True
        infrastructure.reconcile_vault_state_for_local_runtime = mock.Mock(return_value=True)
        infrastructure.sync_common_credentials_from_kubernetes = mock.Mock(return_value=True)
        infrastructure.deploy_helm_release = lambda *_args, **_kwargs: True
        infrastructure.wait_for_dataspace_level3_pods = lambda *_args, **_kwargs: True
        infrastructure.verify_dataspace_ready_for_level4 = lambda: (True, None)
        deployment.wait_for_keycloak_admin_ready = lambda *_args, **_kwargs: True
        deployment.restart_registration_service = lambda: None
        deployment.update_helm_values_with_host_aliases = mock.Mock()

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch(
            "adapters.inesdata.deployment.ensure_python_requirements",
            lambda *_args, **_kwargs: None,
        ), mock.patch(
            "adapters.inesdata.deployment.requests.get",
            return_value=mock.Mock(status_code=200),
        ), mock.patch(
            "adapters.shared.deployment.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            deployment.deploy_dataspace_for_topology("vm-single")

        rendered = output.getvalue()
        self.assertIn("Topology 'vm-single' uses an existing cluster ingress.", rendered)
        self.assertNotIn("MINIKUBE TUNNEL REQUIRED", rendered)
        self.assertIn("Next step: run Level 4", rendered)
        infrastructure.ensure_local_infra_access.assert_not_called()
        infrastructure.reconcile_vault_state_for_local_runtime.assert_not_called()
        infrastructure.sync_common_credentials_from_kubernetes.assert_called_once()
        deployment.update_helm_values_with_host_aliases.assert_not_called()
        self.assertFalse(any(call.args and call.args[0] == "minikube ip" for call in run.call_args_list))

    def test_level3_postgres_cleanup_reconciles_residual_role_directly(self):
        deployment = INESDataDeploymentAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=self._make_infrastructure(),
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        deployment.connectors_adapter = mock.Mock()
        deployment.connectors_adapter.force_clean_postgres_db = mock.Mock()

        subprocess_results = [
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="1\n", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
        ]

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch(
            "adapters.shared.deployment.subprocess.run",
            side_effect=subprocess_results,
        ):
            deployment._cleanup_level3_postgres_state("demoedc_rs", "demoedc_rsusr", "registration-service")

        deployment.connectors_adapter.force_clean_postgres_db.assert_called_once_with(
            "demoedc_rs",
            "demoedc_rsusr",
        )
        self.assertIn("Reconciling directly", output.getvalue())

    def test_level3_postgres_cleanup_fails_when_residual_state_persists(self):
        deployment = INESDataDeploymentAdapter(
            run=self._run,
            run_silent=self._run_silent,
            auto_mode_getter=lambda: True,
            infrastructure_adapter=self._make_infrastructure(),
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        deployment.connectors_adapter = mock.Mock()
        deployment.connectors_adapter.force_clean_postgres_db = mock.Mock()

        subprocess_results = [
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="1\n", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="1\n", stderr=""),
        ]

        with mock.patch(
            "adapters.shared.deployment.subprocess.run",
            side_effect=subprocess_results,
        ):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL cleanup did not remove previous registration-service state"):
                deployment._cleanup_level3_postgres_state("demoedc_rs", "demoedc_rsusr", "registration-service")

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

    def test_wait_for_keycloak_admin_ready_uses_configured_hostname_without_port_forward(self):
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

        def fake_post(*_args, **_kwargs):
            raise Exception("connection refused")

        with mock.patch("adapters.inesdata.deployment.requests.post", side_effect=fake_post):
            result = deployment.wait_for_keycloak_admin_ready(
                "http://keycloak-admin.local",
                "admin",
                "secret",
                timeout=0.01,
                poll_interval=0,
            )

        self.assertFalse(result)
        infrastructure.port_forward_service.assert_not_called()

    def test_ensure_local_infra_access_uses_short_probe_before_creating_port_forward(self):
        infrastructure = self._make_infrastructure()
        infrastructure.wait_for_port = mock.Mock(side_effect=[False, True, True])
        infrastructure.port_forward_service = mock.Mock(return_value=True)
        infrastructure._postgres_connection_works = mock.Mock(return_value=True)

        result = infrastructure.ensure_local_infra_access()

        self.assertTrue(result)
        infrastructure.wait_for_port.assert_any_call("127.0.0.1", 5432, timeout=3)
        infrastructure.wait_for_port.assert_any_call("127.0.0.1", 8200, timeout=3)
        infrastructure.wait_for_port.assert_any_call("127.0.0.1", 9000, timeout=3)
        infrastructure.port_forward_service.assert_called_once_with(
            "common",
            "postgresql",
            5432,
            5432,
            quiet=False,
            wait_timeout=30,
        )

    def test_ensure_local_infra_access_releases_stale_postgres_port_forward(self):
        infrastructure = self._make_infrastructure()
        infrastructure.wait_for_port = mock.Mock(side_effect=[True, True, True])
        infrastructure._postgres_connection_works = mock.Mock(side_effect=[False, True])
        infrastructure._release_stale_postgres_port_forward = mock.Mock(return_value=True)
        infrastructure.port_forward_service = mock.Mock(return_value=True)

        with mock.patch.dict(os.environ, {}, clear=False):
            result = infrastructure.ensure_local_infra_access()

            self.assertTrue(result)
            self.assertEqual(os.environ.get("PIONERA_PG_PORT"), "5432")

        infrastructure.port_forward_service.assert_called_once_with(
            "common",
            "postgresql",
            5432,
            5432,
            quiet=False,
            wait_timeout=30,
        )
        self.assertFalse(os.path.exists(self.config.deployer_config_path()))

    def test_ensure_local_infra_access_fails_when_postgres_port_is_external(self):
        infrastructure = self._make_infrastructure()
        infrastructure.wait_for_port = mock.Mock(side_effect=[True, True])
        infrastructure._postgres_connection_works = mock.Mock(return_value=False)
        infrastructure._release_stale_postgres_port_forward = mock.Mock(return_value=False)
        infrastructure._describe_local_port_listener = mock.Mock(return_value="postgres pid=123")
        infrastructure.port_forward_service = mock.Mock(return_value=True)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.ensure_local_infra_access()

        self.assertFalse(result)
        infrastructure.port_forward_service.assert_not_called()
        self.assertIn("did not terminate unknown processes", output.getvalue())

    def test_apply_sync_updates_minio_values_from_shared_config(self):
        infrastructure = self._make_infrastructure()
        values = {
            "postgresql": {
                "auth": {
                    "postgresPassword": "old",
                    "password": "old",
                }
            },
            "keycloak": {
                "externalDatabase": {"password": "old"},
                "auth": {
                    "adminUser": "old",
                    "adminPassword": "old",
                },
                "keycloakConfigCli": {
                    "extraEnv": [
                        {"name": "KEYCLOAK_USER", "value": "old"},
                        {"name": "KEYCLOAK_PASSWORD", "value": "old"},
                    ]
                },
            },
            "minio": {
                "rootUser": "old",
                "rootPassword": "old",
            },
        }

        updated = infrastructure.apply_sync(
            values,
            {
                "PG_PASSWORD": "pg-secret",
                "KC_USER": "admin",
                "KC_PASSWORD": "kc-secret",
                "MINIO_USER": "minio-admin",
                "MINIO_PASSWORD": "minio-secret",
            },
        )

        self.assertEqual(updated["minio"]["rootUser"], "minio-admin")
        self.assertEqual(updated["minio"]["rootPassword"], "minio-secret")

    def test_sync_vault_token_validates_artifact_before_updating_config(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = mock.Mock(return_value="vault-0")
        infrastructure._vault_root_token_valid = mock.Mock(return_value=True)
        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"root_token": "artifact-token"}\n')
        with open(self.config.deployer_config_path(), "w", encoding="utf-8") as handle:
            handle.write("VT_TOKEN=old-token\n")

        result = infrastructure.sync_vault_token_to_deployer_config()

        self.assertTrue(result)
        with open(self.config.deployer_config_path(), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "VT_TOKEN=artifact-token\n")
        infrastructure._vault_root_token_valid.assert_called_once_with("vault-0", "common", "artifact-token")

    def test_sync_vault_token_keeps_existing_valid_config_when_artifact_is_stale(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = mock.Mock(return_value="vault-0")
        infrastructure._vault_root_token_valid = mock.Mock(side_effect=[False, True, True])
        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"unseal_keys_hex":["abc"],"root_token": "stale-artifact-token"}\n')
        with open(self.config.deployer_config_path(), "w", encoding="utf-8") as handle:
            handle.write("VT_TOKEN=current-valid-token\n")

        result = infrastructure.sync_vault_token_to_deployer_config()

        self.assertTrue(result)
        with open(self.config.deployer_config_path(), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "VT_TOKEN=current-valid-token\n")
        with open(self.config.vault_keys_path(), encoding="utf-8") as handle:
            vault_data = json.load(handle)
        self.assertEqual(vault_data["root_token"], "current-valid-token")
        self.assertEqual(infrastructure._vault_root_token_valid.call_count, 3)

    def test_sync_vault_token_does_not_overwrite_config_when_artifact_and_config_are_stale(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = mock.Mock(return_value="vault-0")
        infrastructure._vault_root_token_valid = mock.Mock(side_effect=[False, False])
        with open(self.config.vault_keys_path(), "w", encoding="utf-8") as handle:
            handle.write('{"root_token": "stale-artifact-token"}\n')
        with open(self.config.deployer_config_path(), "w", encoding="utf-8") as handle:
            handle.write("VT_TOKEN=stale-config-token\n")

        result = infrastructure.sync_vault_token_to_deployer_config()

        self.assertFalse(result)
        with open(self.config.deployer_config_path(), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "VT_TOKEN=stale-config-token\n")

    def test_sync_common_credentials_from_kubernetes_replaces_local_placeholders(self):
        infrastructure = self._make_infrastructure()
        with open(self.config.deployer_config_path(), "w", encoding="utf-8") as handle:
            handle.write(
                "PG_HOST=localhost\n"
                "PG_USER=postgres\n"
                "PG_PASSWORD=CHANGE_ME\n"
                "KC_USER=admin\n"
                "KC_PASSWORD=change-me\n"
                "MINIO_USER=admin\n"
                "MINIO_PASSWORD=CHANGE_ME\n"
                "MINIO_ADMIN_USER=admin\n"
                "MINIO_ADMIN_PASS=CHANGE_ME\n"
            )
        secret_values = {
            ("common", "common-srvs-postgresql", "postgres-password"): "real-pg",
            ("common", "common-srvs-keycloak", "admin-user"): "admin",
            ("common", "common-srvs-keycloak", "admin-password"): "real-kc",
            ("common", "common-srvs-minio", "rootUser"): "minio-admin",
            ("common", "common-srvs-minio", "rootPassword"): "real-minio",
        }
        infrastructure._secret_value = lambda namespace, secret, key: secret_values.get((namespace, secret, key))

        result = infrastructure.sync_common_credentials_from_kubernetes()

        self.assertTrue(result)
        with open(self.config.deployer_config_path(), encoding="utf-8") as handle:
            config_text = handle.read()
        self.assertIn("PG_PASSWORD=real-pg\n", config_text)
        self.assertIn("KC_PASSWORD=real-kc\n", config_text)
        self.assertIn("MINIO_USER=minio-admin\n", config_text)
        self.assertIn("MINIO_PASSWORD=real-minio\n", config_text)
        self.assertIn("MINIO_ADMIN_USER=minio-admin\n", config_text)
        self.assertIn("MINIO_ADMIN_PASS=real-minio\n", config_text)
        self.assertIn("PG_HOST=localhost\n", config_text)

    def test_sync_common_credentials_from_kubernetes_updates_stale_local_values(self):
        infrastructure = self._make_infrastructure()
        with open(self.config.deployer_config_path(), "w", encoding="utf-8") as handle:
            handle.write(
                "PG_PASSWORD=custom-pg\n"
                "KC_PASSWORD=custom-kc\n"
                "DOMAIN_BASE=dev.ed.dataspaceunit.upm\n"
                "KC_INTERNAL_URL=http://keycloak.dev.ed.dataspaceunit.upm\n"
                "KC_URL=http://keycloak-admin.dev.ed.dataspaceunit.upm\n"
                "KEYCLOAK_HOSTNAME=keycloak.dev.ed.dataspaceunit.upm\n"
                "KEYCLOAK_ADMIN_HOSTNAME=keycloak-admin.dev.ed.dataspaceunit.upm\n"
            )
        secret_values = {
            ("common", "common-srvs-postgresql", "postgres-password"): "real-pg",
            ("common", "common-srvs-keycloak", "admin-user"): "admin",
            ("common", "common-srvs-keycloak", "admin-password"): "real-kc",
        }
        infrastructure._secret_value = lambda namespace, secret, key: secret_values.get((namespace, secret, key))

        result = infrastructure.sync_common_credentials_from_kubernetes()

        self.assertTrue(result)
        with open(self.config.deployer_config_path(), encoding="utf-8") as handle:
            config_text = handle.read()
        self.assertIn("PG_PASSWORD=real-pg\n", config_text)
        self.assertIn("KC_PASSWORD=real-kc\n", config_text)
        self.assertIn("KC_USER=admin\n", config_text)
        self.assertIn("KC_INTERNAL_URL=http://auth.dev.ed.dataspaceunit.upm\n", config_text)
        self.assertIn("KC_URL=http://admin.auth.dev.ed.dataspaceunit.upm\n", config_text)
        self.assertIn("KEYCLOAK_HOSTNAME=auth.dev.ed.dataspaceunit.upm\n", config_text)
        self.assertIn("KEYCLOAK_ADMIN_HOSTNAME=admin.auth.dev.ed.dataspaceunit.upm\n", config_text)

    def test_port_forward_service_waits_for_port_to_open(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = lambda *_args, **_kwargs: "vault-0"
        infrastructure.run = mock.Mock(return_value=object())
        process = mock.Mock()
        process.poll.side_effect = [None, None, None]

        with mock.patch(
            "adapters.inesdata.infrastructure.subprocess.Popen",
            return_value=process,
        ), mock.patch.object(
            infrastructure,
            "_port_is_open",
            side_effect=[False, False, True],
        ), mock.patch(
            "adapters.inesdata.infrastructure.time.sleep",
            return_value=None,
        ):
            result = infrastructure.port_forward_service(
                "common",
                "vault",
                8200,
                8200,
                quiet=True,
                wait_timeout=1,
            )

        self.assertTrue(result)
        self.assertGreaterEqual(process.poll.call_count, 2)

    def test_port_forward_service_fails_fast_when_process_exits(self):
        infrastructure = self._make_infrastructure()
        infrastructure.get_pod_by_name = lambda *_args, **_kwargs: "vault-0"
        infrastructure.run = mock.Mock(return_value=object())
        process = mock.Mock()
        process.poll.return_value = 1

        with mock.patch(
            "adapters.inesdata.infrastructure.subprocess.Popen",
            return_value=process,
        ), mock.patch.object(
            infrastructure,
            "_port_is_open",
            return_value=False,
        ):
            result = infrastructure.port_forward_service(
                "common",
                "vault",
                8200,
                8200,
                quiet=True,
                wait_timeout=1,
            )

        self.assertFalse(result)

    def test_wait_for_registration_service_schema_quiet_probe_skips_timeout_diagnostics(self):
        infrastructure = self._make_infrastructure()
        infrastructure.run_silent = mock.Mock(return_value="")
        infrastructure.run = mock.Mock(return_value=object())

        with mock.patch("adapters.inesdata.infrastructure.time.sleep", return_value=None):
            result = infrastructure.wait_for_registration_service_schema(
                timeout=1,
                poll_interval=0,
                quiet=True,
            )

        self.assertFalse(result)
        infrastructure.run.assert_not_called()

    def test_wait_for_registration_service_liquibase_uses_local_service_access_helper(self):
        infrastructure = self._make_infrastructure()
        infrastructure._ensure_local_service_access = mock.Mock(return_value=(True, True))
        infrastructure.stop_port_forward_service = mock.Mock(return_value=True)

        with mock.patch(
            "adapters.inesdata.infrastructure.requests.get",
            return_value=mock.Mock(status_code=200, json=lambda: {"liquibaseBeans": {}}),
        ):
            result = infrastructure.wait_for_registration_service_liquibase(timeout=1, poll_interval=0)

        self.assertTrue(result)
        infrastructure._ensure_local_service_access.assert_called_once_with(
            "registration-service actuator",
            "demo-core-ns",
            "registration-service",
            18080,
            8080,
            quiet=True,
            probe_timeout=2,
            wait_timeout=30,
        )
        infrastructure.stop_port_forward_service.assert_called_once_with(
            "demo-core-ns",
            "registration-service",
            quiet=True,
        )

    def test_wait_for_deployment_rollout_uses_kubectl_rollout_status(self):
        infrastructure = self._make_infrastructure()
        infrastructure.run = mock.Mock(return_value='deployment "demo-app" successfully rolled out\n')

        result = infrastructure.wait_for_deployment_rollout(
            "demo-ns",
            "demo-app",
            timeout_seconds=240,
            label="demo app",
        )

        self.assertTrue(result)
        infrastructure.run.assert_called_once_with(
            "kubectl rollout status deployment/demo-app -n demo-ns --timeout=240s",
            capture=True,
            check=False,
        )

    def test_verify_dataspace_ready_for_level4_skips_liquibase_when_schema_probe_passes(self):
        infrastructure = self._make_infrastructure()
        infrastructure.wait_for_dataspace_level3_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_registration_service_schema = mock.Mock(return_value=True)
        infrastructure.wait_for_registration_service_liquibase = mock.Mock(return_value=True)

        ready, root_cause = infrastructure.verify_dataspace_ready_for_level4()

        self.assertTrue(ready)
        self.assertIsNone(root_cause)
        infrastructure.wait_for_dataspace_level3_pods.assert_called_once_with(
            "demo-core-ns",
            dataspace_name="demo",
        )
        infrastructure.wait_for_registration_service_schema.assert_called_once_with(
            timeout=15,
            poll_interval=3,
            quiet=True,
        )
        infrastructure.wait_for_registration_service_liquibase.assert_not_called()

    def test_verify_dataspace_ready_for_level4_uses_quick_then_remaining_schema_timeouts(self):
        infrastructure = self._make_infrastructure()
        infrastructure.wait_for_dataspace_level3_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_registration_service_schema = mock.Mock(side_effect=[False, True])
        infrastructure.wait_for_registration_service_liquibase = mock.Mock(return_value=True)

        ready, root_cause = infrastructure.verify_dataspace_ready_for_level4()

        self.assertTrue(ready)
        self.assertIsNone(root_cause)
        self.assertEqual(
            infrastructure.wait_for_registration_service_schema.call_args_list,
            [
                mock.call(timeout=15, poll_interval=3, quiet=True),
                mock.call(timeout=105, poll_interval=3),
            ],
        )
        infrastructure.wait_for_registration_service_liquibase.assert_called_once_with(timeout=60, poll_interval=3)

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

    def test_deploy_infrastructure_uses_startup_budget_timeout_for_first_common_services_install(self):
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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)

        seen = {}

        def fake_deploy(*_args, **kwargs):
            seen.update(kwargs)
            return True

        infrastructure.deploy_helm_release = fake_deploy

        infrastructure.deploy_infrastructure()

        self.assertEqual(seen.get("timeout_seconds"), 180)

    def test_deploy_infrastructure_reuses_longer_pod_wait_budget_for_first_common_services_install(self):
        infrastructure = self._make_infrastructure()
        infrastructure.config.TIMEOUT_POD_WAIT = 240
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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
        infrastructure.verify_common_services_ready_for_level3 = lambda: (True, None)

        seen = {}

        def fake_deploy(*_args, **kwargs):
            seen.update(kwargs)
            return True

        infrastructure.deploy_helm_release = fake_deploy

        infrastructure.deploy_infrastructure()

        self.assertEqual(seen.get("timeout_seconds"), 240)

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
        infrastructure.reconcile_vault_state_for_local_runtime = lambda: True
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

    def test_verify_cluster_ready_for_level2_uses_extended_ingress_timeouts(self):
        infrastructure = self._make_infrastructure()
        infrastructure.run_silent = mock.Mock(
            side_effect=[
                '{"Host":"Running","Kubelet":"Running","APIServer":"Running"}',
                "minikube Ready control-plane",
            ]
        )
        infrastructure.wait_for_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_namespace_stability = mock.Mock(return_value=True)

        ready, root_cause = infrastructure.verify_cluster_ready_for_level2()

        self.assertTrue(ready)
        self.assertIsNone(root_cause)
        infrastructure.wait_for_pods.assert_called_once_with("ingress-nginx", timeout=300)
        infrastructure.wait_for_namespace_stability.assert_called_once_with(
            "ingress-nginx",
            duration=10,
            poll_interval=3,
            timeout=180,
        )

    def test_verify_common_services_ready_for_level3_uses_extended_timeouts(self):
        infrastructure = self._make_infrastructure()
        infrastructure._common_services_release_status = lambda: "deployed"
        infrastructure.wait_for_level2_service_pods = mock.Mock(return_value=True)
        infrastructure.wait_for_namespace_stability = mock.Mock(return_value=True)
        infrastructure.ensure_vault_unsealed = mock.Mock(return_value=True)

        ready, root_cause = infrastructure.verify_common_services_ready_for_level3()

        self.assertTrue(ready)
        self.assertIsNone(root_cause)
        infrastructure.wait_for_level2_service_pods.assert_called_once_with(
            "common",
            timeout=300,
            require_vault_ready=True,
        )
        infrastructure.wait_for_namespace_stability.assert_called_once_with(
            "common",
            duration=12,
            poll_interval=3,
            timeout=180,
        )

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

    def test_wait_for_dataspace_level3_pods_ignores_existing_connector_pods(self):
        infrastructure = self._make_infrastructure()
        snapshots = iter([
            "\n".join([
                "conn-citycouncil-demo-6b54bbfc5b-mrclj 0/1 Init:0/1 59 24h",
                "conn-company-demo-ff686689d-h2t5q 0/1 Init:0/1 36 24h",
                "demo-registration-service-58d99859cd-wqz8g 1/1 Running 0 91s",
            ]),
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_dataspace_level3_pods(
                "demo",
                dataspace_name="demo",
                timeout=1,
            )

        self.assertTrue(result)
        rendered = output.getvalue()
        self.assertIn("Level 3 dataspace pods ready", rendered)
        self.assertIn("Ignoring non-Level 3 pods", rendered)

    def test_wait_for_dataspace_level3_pods_waits_for_stale_rollout_error_to_disappear(self):
        infrastructure = self._make_infrastructure()
        infrastructure.run = mock.Mock(return_value=object())
        snapshots = iter([
            "\n".join([
                "demoedc-registration-service-5b67fb6944-djqgd 0/1 Error 0 19s",
                "demoedc-registration-service-5795c78bbb-vz97j 0/1 ContainerCreating 0 5s",
            ]),
            "\n".join([
                "demoedc-registration-service-5b67fb6944-djqgd 0/1 Error 0 19s",
                "demoedc-registration-service-5795c78bbb-vz97j 1/1 Running 0 19s",
            ]),
            "demoedc-registration-service-5795c78bbb-vz97j 1/1 Running 0 20s",
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")

        output = io.StringIO()
        with mock.patch("adapters.inesdata.infrastructure.time.sleep", return_value=None), contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_dataspace_level3_pods(
                "demoedc",
                dataspace_name="demoedc",
                timeout=3,
            )

        self.assertTrue(result)
        rendered = output.getvalue()
        self.assertIn("Waiting for stale Level 3 rollout pods to disappear", rendered)
        self.assertIn("Level 3 dataspace pods ready", rendered)
        infrastructure.run.assert_called_once_with("kubectl get pods -n demoedc", check=False)

    def test_wait_for_dataspace_level3_pods_tolerates_transient_error_before_running(self):
        infrastructure = self._make_infrastructure()
        infrastructure.run = mock.Mock(return_value=object())
        snapshots = iter([
            "demo-registration-service-677f49d885-nbm85 0/1 Error 0 3s",
            "demo-registration-service-677f49d885-nbm85 1/1 Running 1 5s",
        ])
        infrastructure.run_silent = lambda *_args, **_kwargs: next(snapshots, "")
        clock = iter([0.0, 0.0, 1.0, 2.0])

        output = io.StringIO()
        with mock.patch(
            "adapters.inesdata.infrastructure.time.time",
            side_effect=lambda: next(clock),
        ), mock.patch(
            "adapters.inesdata.infrastructure.time.sleep",
            return_value=None,
        ), contextlib.redirect_stdout(output):
            result = infrastructure.wait_for_dataspace_level3_pods(
                "demo",
                dataspace_name="demo",
                timeout=3,
            )

        self.assertTrue(result)
        rendered = output.getvalue()
        self.assertIn("Waiting for transient Level 3 pod errors to recover", rendered)
        self.assertIn("Level 3 dataspace pods ready", rendered)
        infrastructure.run.assert_called_once_with("kubectl get pods -n demo", check=False)


if __name__ == "__main__":
    unittest.main()
