import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.edc.adapter import EdcAdapter
from adapters.edc.connectors import EDCConnectorsAdapter
from adapters.edc.deployment import EDCDeploymentAdapter


class SharedInfrastructureStub:
    def __init__(self, *, dataspace_ready=True, registration_pod="demo-registration-service-0", schema_ready=True):
        self.announced = []
        self.completed = []
        self.deploy_calls = 0
        self.dataspace_ready = dataspace_ready
        self.registration_pod = registration_pod
        self.schema_ready = schema_ready

    def verify_common_services_ready_for_level3(self):
        return True, []

    def verify_dataspace_ready_for_level4(self):
        return self.dataspace_ready, []

    def get_pod_by_name(self, namespace, partial_name):
        del namespace
        if partial_name == "registration-service":
            return self.registration_pod
        return None

    def wait_for_registration_service_schema(self, timeout=1, poll_interval=1, quiet=True):
        del timeout, poll_interval, quiet
        return self.schema_ready

    def announce_level(self, level, label):
        self.announced.append((level, label))

    def complete_level(self, level):
        self.completed.append(level)

    def deploy_infrastructure(self):
        self.deploy_calls += 1
        return "deploy-called"

    @staticmethod
    def _is_ignored_transient_hook_pod(namespace, pod_name):
        del namespace
        return "minio-post-job" in pod_name


class DeploymentDelegateStub:
    def __init__(self):
        self.deploy_calls = 0
        self.recreate_calls = []
        self.connectors_adapter = None

    def deploy_dataspace(self):
        self.deploy_calls += 1
        return "dataspace-deploy-called"

    def build_recreate_dataspace_plan(self):
        return {"dataspace": "demoedc", "adapter": "edc"}

    def recreate_dataspace(self, confirm_dataspace=None):
        self.recreate_calls.append(confirm_dataspace)
        return "dataspace-recreate-called"


class EdcConnectorConfig:
    MINIKUBE_IP = "192.168.49.2"
    EDC_MANAGED_LABEL = "edc"
    NS_COMMON = "common-srvs"

    @staticmethod
    def script_dir():
        return "/tmp/validation-environment"

    @staticmethod
    def repo_dir():
        return "/tmp/deployers/inesdata"

    @staticmethod
    def connector_credentials_path(connector_name):
        return os.path.join("/tmp", "default", f"credentials-connector-{connector_name}.json")

    @staticmethod
    def host_alias_domains():
        return [
            "keycloak.dev.ed.dataspaceunit.upm",
            "minio.dev.ed.dataspaceunit.upm",
        ]


class EdcConnectorConfigAdapter:
    def __init__(self, root):
        self.root = root

    @staticmethod
    def load_deployer_config():
        return {
            "ENVIRONMENT": "DEV",
            "DS_DOMAIN_BASE": "dev.ds.dataspaceunit.upm",
            "KEYCLOAK_HOSTNAME": "keycloak.dev.ed.dataspaceunit.upm",
            "MINIO_HOSTNAME": "minio.dev.ed.dataspaceunit.upm",
            "DATABASE_HOSTNAME": "postgresql.demo.svc.cluster.local",
            "VAULT_URL": "http://vault.common:8200",
        }

    @staticmethod
    def ds_domain_base():
        return "dev.ds.dataspaceunit.upm"

    @staticmethod
    def edc_connector_image_name():
        return "ghcr.io/proyectopionera/edc-connector"

    @staticmethod
    def edc_connector_image_tag():
        return "latest"

    @staticmethod
    def edc_connector_image_pull_policy():
        return "IfNotPresent"

    @staticmethod
    def edc_dashboard_enabled():
        return False

    @staticmethod
    def edc_dashboard_base_href():
        return "/edc-dashboard/"

    @staticmethod
    def edc_dashboard_image_name():
        return "validation-environment/edc-dashboard"

    @staticmethod
    def edc_dashboard_image_tag():
        return "latest"

    @staticmethod
    def edc_dashboard_image_pull_policy():
        return "IfNotPresent"

    @staticmethod
    def edc_dashboard_proxy_image_name():
        return "validation-environment/edc-dashboard-proxy"

    @staticmethod
    def edc_dashboard_proxy_image_tag():
        return "latest"

    @staticmethod
    def edc_dashboard_proxy_image_pull_policy():
        return "IfNotPresent"

    @staticmethod
    def edc_dashboard_proxy_auth_mode():
        return "service-account"

    @staticmethod
    def edc_dashboard_proxy_client_id():
        return "dataspace-users"

    @staticmethod
    def edc_dashboard_proxy_scope():
        return "openid profile email"

    @staticmethod
    def edc_dashboard_proxy_cookie_name():
        return "edc_dashboard_session"

    @staticmethod
    def deployment_environment_name():
        return "DEV"

    def edc_dataspace_runtime_dir(self, ds_name=None):
        return os.path.join(self.root, ds_name or "default")

    def edc_connector_values_file(self, connector_name, ds_name=None):
        return os.path.join(self.edc_dataspace_runtime_dir(ds_name=ds_name), f"values-{connector_name}.yaml")

    def edc_connector_certs_dir(self, ds_name=None):
        return os.path.join(self.edc_dataspace_runtime_dir(ds_name=ds_name), "certs")

    def edc_dashboard_runtime_dir(self, connector_name, ds_name=None):
        return os.path.join(self.edc_dataspace_runtime_dir(ds_name=ds_name), "dashboard", connector_name)

    def edc_dashboard_app_config_file(self, connector_name, ds_name=None):
        return os.path.join(self.edc_dashboard_runtime_dir(connector_name, ds_name=ds_name), "app-config.json")

    def edc_dashboard_connector_config_file(self, connector_name, ds_name=None):
        return os.path.join(
            self.edc_dashboard_runtime_dir(connector_name, ds_name=ds_name),
            "edc-connector-config.json",
        )

    def edc_dashboard_base_href_file(self, connector_name, ds_name=None):
        return os.path.join(self.edc_dashboard_runtime_dir(connector_name, ds_name=ds_name), "APP_BASE_HREF.txt")

    def edc_connector_policy_file(self, connector_name, ds_name=None):
        dataspace = ds_name or "default"
        return os.path.join(self.edc_dataspace_runtime_dir(ds_name=dataspace), f"policy-{dataspace}-{connector_name}.json")

    @staticmethod
    def edc_reference_repo_url():
        return "https://github.com/luciamartinnunez/Connector"

    def edc_connector_source_dir(self):
        return os.path.join(self.root, "source")

    def edc_connector_dir(self):
        return self.root

    @staticmethod
    def generate_connector_hosts(connectors):
        return [f"127.0.0.1 {connector}.dev.ds.dataspaceunit.upm" for connector in connectors]


class EdcAdapterTests(unittest.TestCase):
    def test_edc_adapter_reuses_common_services_when_ready(self):
        adapter = EdcAdapter.__new__(EdcAdapter)
        adapter.infrastructure = SharedInfrastructureStub()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = adapter.deploy_infrastructure()

        self.assertTrue(result)
        self.assertEqual(adapter.infrastructure.deploy_calls, 0)
        self.assertEqual(adapter.infrastructure.announced, [(2, "DEPLOY COMMON SERVICES")])
        self.assertEqual(adapter.infrastructure.completed, [2])
        self.assertIn("Reusing them for EDC mode", output.getvalue())

    def test_preview_common_services_ignores_transient_minio_post_job(self):
        class PreviewConfig:
            NS_COMMON = "common-srvs"

        def run_silent(cmd, **_kwargs):
            if cmd == "kubectl get pods -n common-srvs --no-headers":
                return (
                    "common-srvs-keycloak-0 1/1 Running 0 1d\n"
                    "common-srvs-minio-56c96fbbdf-77qkg 1/1 Running 0 1d\n"
                    "common-srvs-minio-post-job-8fjdv 0/1 Completed 0 1d\n"
                    "common-srvs-postgresql-0 1/1 Running 0 1d\n"
                    "common-srvs-vault-0 1/1 Running 0 1d"
                )
            if cmd == "kubectl exec common-srvs-vault-0 -n common-srvs -- vault status -format=json":
                return '{"initialized": true, "sealed": false}'
            return ""

        adapter = EdcAdapter.__new__(EdcAdapter)
        adapter.config = PreviewConfig
        adapter.infrastructure = SharedInfrastructureStub()
        adapter.run_silent = run_silent

        preview = adapter._preview_common_services()

        self.assertEqual(preview["status"], "ready")
        self.assertEqual(preview["action"], "reuse")
        self.assertEqual(preview["services"]["minio"]["pod"], "common-srvs-minio-56c96fbbdf-77qkg")
        self.assertTrue(preview["services"]["minio"]["ready"])
        self.assertEqual(preview["issues"], [])


class EdcDeploymentTests(unittest.TestCase):
    def test_edc_deployment_reuses_dataspace_when_ready(self):
        deployment = EDCDeploymentAdapter.__new__(EDCDeploymentAdapter)
        deployment.infrastructure = SharedInfrastructureStub()
        deployment._delegate = DeploymentDelegateStub()
        deployment.config = type("Config", (), {"namespace_demo": staticmethod(lambda: "demoedc")})
        deployment.config_adapter = None

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = deployment.deploy_dataspace()

        self.assertTrue(result)
        self.assertEqual(deployment._delegate.deploy_calls, 0)
        self.assertEqual(deployment.infrastructure.announced, [(3, "DATASPACE")])
        self.assertEqual(deployment.infrastructure.completed, [3])
        self.assertIn("Reusing it for EDC mode", output.getvalue())

    def test_edc_deployment_reuses_dataspace_when_registration_service_is_ready_even_if_namespace_is_unstable(self):
        deployment = EDCDeploymentAdapter.__new__(EDCDeploymentAdapter)
        deployment.infrastructure = SharedInfrastructureStub(dataspace_ready=False, registration_pod="demoedc-registration-service-0", schema_ready=True)
        deployment._delegate = DeploymentDelegateStub()
        deployment.config = type("Config", (), {"namespace_demo": staticmethod(lambda: "demoedc")})
        deployment.config_adapter = None

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = deployment.deploy_dataspace()

        self.assertTrue(result)
        self.assertEqual(deployment._delegate.deploy_calls, 0)
        self.assertEqual(deployment.infrastructure.announced, [(3, "DATASPACE")])
        self.assertEqual(deployment.infrastructure.completed, [3])
        self.assertIn("Reusing it for EDC mode", output.getvalue())

    def test_edc_deployment_uses_shared_dataspace_runtime_for_level3_only(self):
        deployment = EDCDeploymentAdapter(
            run=lambda *_args, **_kwargs: None,
            run_silent=lambda *_args, **_kwargs: "",
            auto_mode_getter=lambda: True,
            infrastructure_adapter=SharedInfrastructureStub(),
        )

        self.assertTrue(deployment.config.repo_dir().endswith("Validation-Environment/deployers/edc"))
        self.assertTrue(deployment._delegate.config.repo_dir().endswith("Validation-Environment/deployers/inesdata"))
        self.assertTrue(
            deployment._delegate.config.python_exec().endswith(
                "Validation-Environment/deployers/inesdata/.venv/bin/python"
            )
        )
        self.assertEqual(deployment._delegate.config.RUNTIME_LABEL, "shared dataspace")
        self.assertTrue(deployment._delegate.config.QUIET_SENSITIVE_DEPLOYER_OUTPUT)

    def test_edc_deployment_stages_shared_dataspace_credentials_into_edc_runtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_repo = os.path.join(tmpdir, "deployers", "inesdata")
            target_repo = os.path.join(tmpdir, "deployers", "edc")
            source_dir = os.path.join(source_repo, "deployments", "DEV", "demoedc")
            os.makedirs(source_dir, exist_ok=True)
            source_file = os.path.join(source_dir, "credentials-dataspace-demoedc.json")
            with open(source_file, "w", encoding="utf-8") as handle:
                json.dump({"registration_service_database": {"name": "demoedc_rs"}}, handle)

            class SourceConfig:
                @staticmethod
                def repo_dir():
                    return source_repo

            class ConfigAdapter:
                @staticmethod
                def primary_dataspace_name():
                    return "demoedc"

                @staticmethod
                def deployment_environment_name():
                    return "DEV"

                @staticmethod
                def edc_dataspace_runtime_dir(ds_name=None):
                    return os.path.join(target_repo, "deployments", "DEV", ds_name or "demoedc")

            deployment = EDCDeploymentAdapter.__new__(EDCDeploymentAdapter)
            deployment._delegate = type("Delegate", (), {"config": SourceConfig})()
            deployment.config_adapter = ConfigAdapter()

            staged = deployment._stage_shared_dataspace_credentials()

            target_file = os.path.join(target_repo, "deployments", "DEV", "demoedc", "credentials-dataspace-demoedc.json")
            self.assertEqual(staged, target_file)
            self.assertTrue(os.path.isfile(target_file))
            self.assertFalse(os.path.exists(source_file))
            self.assertFalse(os.path.exists(source_dir))

    def test_edc_deployment_recreate_dataspace_delegates_to_shared_level3_flow(self):
        deployment = EDCDeploymentAdapter.__new__(EDCDeploymentAdapter)
        deployment.infrastructure = SharedInfrastructureStub()
        deployment._delegate = DeploymentDelegateStub()
        deployment.connectors_adapter = object()

        plan = deployment.build_recreate_dataspace_plan()
        result = deployment.recreate_dataspace(confirm_dataspace="demoedc")

        self.assertEqual(plan["dataspace"], "demoedc")
        self.assertEqual(result, "dataspace-recreate-called")
        self.assertEqual(deployment._delegate.recreate_calls, ["demoedc"])
        self.assertIs(deployment._delegate.connectors_adapter, deployment.connectors_adapter)


class EdcConnectorAdapterTests(unittest.TestCase):
    class OidcEdcConnectorConfigAdapter(EdcConnectorConfigAdapter):
        @staticmethod
        def edc_dashboard_proxy_auth_mode():
            return "oidc-bff"

    def _make_adapter(self, root):
        adapter = EDCConnectorsAdapter.__new__(EDCConnectorsAdapter)
        adapter.topology = "local"
        adapter.run = lambda *_args, **_kwargs: None
        adapter.run_silent = lambda cmd, **_kwargs: "192.168.49.2" if cmd == "minikube ip" else ""
        adapter.config = type(
            "RuntimeEdcConnectorConfig",
            (EdcConnectorConfig,),
            {
                "script_dir": staticmethod(lambda: root),
                "repo_dir": staticmethod(lambda: "/tmp/deployers/edc"),
                "connector_credentials_path": staticmethod(
                    lambda connector_name: os.path.join(
                        root,
                        "demoedc",
                        f"credentials-connector-{connector_name}.json",
                    )
                ),
            },
        )
        adapter.config_adapter = EdcConnectorConfigAdapter(root)
        adapter.load_connector_credentials = lambda _connector: {
            "database": {
                "name": "db_conn_citycounciledc_demoedc",
                "user": "conn-citycounciledc-demoedc",
                "passwd": "secret-db",
            },
            "minio": {
                "access_key": "minio-access-key",
                "secret_key": "minio-secret-key",
            },
            "vault": {
                "token": "vault-token",
            },
            "connector_user": {
                "user": "connector-user",
                "passwd": "connector-password",
            },
        }
        return adapter

    def _make_oidc_adapter(self, root):
        adapter = self._make_adapter(root)
        adapter.config_adapter = self.OidcEdcConnectorConfigAdapter(root)
        return adapter

    def _make_runtime_prerequisites_adapter(
        self,
        root,
        repo_dir,
        venv_dir,
        chart_dir,
        requirements_path,
        native_bootstrap=False,
    ):
        adapter = EDCConnectorsAdapter.__new__(EDCConnectorsAdapter)
        adapter.config = type(
            "RuntimePrerequisitesConfig",
            (),
            {
                "EDC_NATIVE_BOOTSTRAP": native_bootstrap,
                "repo_dir": staticmethod(lambda: repo_dir),
                "python_exec": staticmethod(lambda: "/usr/bin/python3"),
                "venv_path": staticmethod(lambda: venv_dir),
                "repo_requirements_path": staticmethod(lambda: requirements_path),
                "deployer_config_path": staticmethod(
                    lambda: os.path.join(root, "deployers", "edc", "deployer.config")
                ),
                "infrastructure_deployer_config_path": staticmethod(
                    lambda: os.path.join(root, "deployers", "infrastructure", "deployer.config")
                ),
            },
        )
        adapter.config_adapter = type(
            "RuntimePrerequisitesConfigAdapter",
            (),
            {
                "edc_connector_dir": lambda _self: chart_dir,
                "edc_bootstrap_script": lambda _self: os.path.join(repo_dir, "bootstrap.py"),
            },
        )()
        return adapter

    def test_prepare_runtime_prerequisites_skips_vault_token_sync_without_local_edc_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "repo")
            venv_dir = os.path.join(tmpdir, "venv")
            chart_dir = os.path.join(tmpdir, "chart")
            requirements_path = os.path.join(tmpdir, "requirements.txt")
            os.makedirs(repo_dir)
            os.makedirs(venv_dir)
            os.makedirs(chart_dir)
            with open(os.path.join(repo_dir, "bootstrap.py"), "w", encoding="utf-8") as handle:
                handle.write("")
            with open(requirements_path, "w", encoding="utf-8") as handle:
                handle.write("")

            adapter = self._make_runtime_prerequisites_adapter(
                tmpdir,
                repo_dir,
                venv_dir,
                chart_dir,
                requirements_path,
            )
            infrastructure = mock.Mock()
            infrastructure.ensure_local_infra_access.return_value = True
            infrastructure.ensure_vault_unsealed.return_value = True
            infrastructure.sync_vault_token_to_deployer_config.return_value = True
            adapter.infrastructure = infrastructure

            with mock.patch("adapters.edc.connectors.ensure_python_requirements") as requirements_mock:
                result = adapter._prepare_runtime_prerequisites()

        self.assertEqual(result, (repo_dir, "/usr/bin/python3"))
        requirements_mock.assert_called_once_with(
            "/usr/bin/python3",
            requirements_path,
            label="EDC runtime",
            quiet=True,
        )
        infrastructure.sync_vault_token_to_deployer_config.assert_not_called()

    def test_prepare_runtime_prerequisites_syncs_vault_token_when_local_edc_config_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "repo")
            venv_dir = os.path.join(tmpdir, "venv")
            chart_dir = os.path.join(tmpdir, "chart")
            requirements_path = os.path.join(tmpdir, "requirements.txt")
            config_path = os.path.join(tmpdir, "deployers", "edc", "deployer.config")
            os.makedirs(repo_dir)
            os.makedirs(venv_dir)
            os.makedirs(chart_dir)
            os.makedirs(os.path.dirname(config_path))
            with open(os.path.join(repo_dir, "bootstrap.py"), "w", encoding="utf-8") as handle:
                handle.write("")
            with open(requirements_path, "w", encoding="utf-8") as handle:
                handle.write("")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write("VT_TOKEN=old-token\n")

            adapter = self._make_runtime_prerequisites_adapter(
                tmpdir,
                repo_dir,
                venv_dir,
                chart_dir,
                requirements_path,
            )
            infrastructure = mock.Mock()
            infrastructure.ensure_local_infra_access.return_value = True
            infrastructure.ensure_vault_unsealed.return_value = True
            infrastructure.sync_vault_token_to_deployer_config.return_value = True
            adapter.infrastructure = infrastructure

            with mock.patch("adapters.edc.connectors.ensure_python_requirements") as requirements_mock:
                result = adapter._prepare_runtime_prerequisites()

        self.assertEqual(result, (repo_dir, "/usr/bin/python3"))
        requirements_mock.assert_called_once_with(
            "/usr/bin/python3",
            requirements_path,
            label="EDC runtime",
            quiet=True,
        )
        infrastructure.sync_vault_token_to_deployer_config.assert_called_once()

    def test_prepare_runtime_prerequisites_syncs_vault_token_when_shared_infrastructure_config_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "repo")
            venv_dir = os.path.join(tmpdir, "venv")
            chart_dir = os.path.join(tmpdir, "chart")
            requirements_path = os.path.join(tmpdir, "requirements.txt")
            config_path = os.path.join(tmpdir, "deployers", "infrastructure", "deployer.config")
            os.makedirs(repo_dir)
            os.makedirs(venv_dir)
            os.makedirs(chart_dir)
            os.makedirs(os.path.dirname(config_path))
            with open(os.path.join(repo_dir, "bootstrap.py"), "w", encoding="utf-8") as handle:
                handle.write("")
            with open(requirements_path, "w", encoding="utf-8") as handle:
                handle.write("")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write("VT_TOKEN=old-token\n")

            adapter = self._make_runtime_prerequisites_adapter(
                tmpdir,
                repo_dir,
                venv_dir,
                chart_dir,
                requirements_path,
            )
            infrastructure = mock.Mock()
            infrastructure.ensure_local_infra_access.return_value = True
            infrastructure.ensure_vault_unsealed.return_value = True
            infrastructure.sync_vault_token_to_deployer_config.return_value = True
            adapter.infrastructure = infrastructure

            with mock.patch("adapters.edc.connectors.ensure_python_requirements"):
                result = adapter._prepare_runtime_prerequisites()

        self.assertEqual(result, (repo_dir, "/usr/bin/python3"))
        infrastructure.sync_vault_token_to_deployer_config.assert_called_once()

    def test_prepare_runtime_prerequisites_fails_when_vault_token_is_stale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "repo")
            venv_dir = os.path.join(tmpdir, "venv")
            chart_dir = os.path.join(tmpdir, "chart")
            requirements_path = os.path.join(tmpdir, "requirements.txt")
            config_path = os.path.join(tmpdir, "deployers", "infrastructure", "deployer.config")
            os.makedirs(repo_dir)
            os.makedirs(venv_dir)
            os.makedirs(chart_dir)
            os.makedirs(os.path.dirname(config_path))
            with open(os.path.join(repo_dir, "bootstrap.py"), "w", encoding="utf-8") as handle:
                handle.write("")
            with open(requirements_path, "w", encoding="utf-8") as handle:
                handle.write("")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write("VT_TOKEN=old-token\n")

            adapter = self._make_runtime_prerequisites_adapter(
                tmpdir,
                repo_dir,
                venv_dir,
                chart_dir,
                requirements_path,
            )
            adapter.config_adapter.load_deployer_config = lambda: {
                "VT_URL": "http://vault.local:8200",
                "VT_TOKEN": "stale-token",
            }
            infrastructure = mock.Mock()
            infrastructure.ensure_local_infra_access.return_value = True
            infrastructure.ensure_vault_unsealed.return_value = True
            infrastructure.sync_vault_token_to_deployer_config.return_value = True
            adapter.infrastructure = infrastructure

            stale_response = mock.Mock(status_code=403)
            output = io.StringIO()
            with mock.patch("adapters.edc.connectors.ensure_python_requirements"):
                with mock.patch("adapters.edc.connectors.requests.get", return_value=stale_response):
                    with contextlib.redirect_stdout(output):
                        result = adapter._prepare_runtime_prerequisites()

        self.assertEqual(result, (None, None))
        self.assertIn("Vault token validation failed", output.getvalue())
        self.assertIn("stale", output.getvalue())

    def test_prepare_runtime_prerequisites_uses_native_edc_bootstrap_without_legacy_venv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "deployers", "edc")
            chart_dir = os.path.join(tmpdir, "connector")
            venv_dir = os.path.join(tmpdir, "missing-venv")
            requirements_path = os.path.join(tmpdir, "missing-requirements.txt")
            os.makedirs(repo_dir)
            os.makedirs(chart_dir)
            with open(os.path.join(repo_dir, "bootstrap.py"), "w", encoding="utf-8") as handle:
                handle.write("")

            adapter = self._make_runtime_prerequisites_adapter(
                tmpdir,
                repo_dir,
                venv_dir,
                chart_dir,
                requirements_path,
                native_bootstrap=True,
            )
            infrastructure = mock.Mock()
            infrastructure.ensure_local_infra_access.return_value = True
            infrastructure.ensure_vault_unsealed.return_value = True
            infrastructure.sync_vault_token_to_deployer_config.return_value = True
            adapter.infrastructure = infrastructure

            with mock.patch("adapters.edc.connectors.ensure_python_requirements") as requirements_mock:
                result = adapter._prepare_runtime_prerequisites()

        self.assertEqual(result, (repo_dir, "/usr/bin/python3"))
        requirements_mock.assert_not_called()
        infrastructure.sync_vault_token_to_deployer_config.assert_not_called()

    def test_connector_values_payload_maps_edc_runtime_and_shared_services(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = self._make_adapter(tmpdir)

            payload = adapter._connector_values_payload(
                "conn-citycounciledc-demoedc",
                "demoedc",
                [
                    "conn-citycounciledc-demoedc",
                    "conn-companyedc-demoedc",
                ],
            )

        self.assertEqual(payload["connector"]["image"]["name"], "ghcr.io/proyectopionera/edc-connector")
        self.assertEqual(payload["connector"]["configuration"]["configFilePath"], "/opt/connector/config/connector-configuration.properties")
        self.assertEqual(payload["connector"]["ingress"]["hostname"], "conn-citycounciledc-demoedc.dev.ds.dataspaceunit.upm")
        self.assertEqual(payload["connector"]["minio"]["accesskey"], "minio-access-key")
        self.assertEqual(payload["connector"]["minio"]["secretkey"], "minio-secret-key")
        self.assertEqual(payload["services"]["keycloak"]["hostname"], "keycloak.dev.ed.dataspaceunit.upm")
        self.assertEqual(payload["services"]["minio"]["bucket"], "demoedc-conn-citycounciledc-demoedc")
        self.assertEqual(payload["services"]["vault"]["path"], "demoedc/conn-citycounciledc-demoedc/")
        self.assertFalse(payload["dashboard"]["enabled"])
        self.assertEqual(payload["dashboard"]["baseHref"], "/edc-dashboard/")
        self.assertEqual(payload["dashboard"]["runtime"]["appConfig"]["appTitle"], "EDC Dashboard - conn-citycounciledc-demoedc")
        self.assertEqual(
            payload["dashboard"]["runtime"]["connectorConfig"][0]["managementUrl"],
            "/edc-dashboard-api/connectors/conn-citycounciledc-demoedc/management",
        )
        self.assertEqual(
            payload["dashboard"]["runtime"]["connectorConfig"][0]["controlUrl"],
            "/edc-dashboard-api/connectors/conn-citycounciledc-demoedc/control",
        )
        self.assertEqual(payload["dashboard"]["proxy"]["image"]["name"], "validation-environment/edc-dashboard-proxy")
        self.assertEqual(payload["dashboard"]["proxy"]["config"]["authMode"], "service-account")
        self.assertEqual(
            payload["dashboard"]["proxy"]["config"]["connectors"][0]["managementTarget"],
            "http://conn-citycounciledc-demoedc:19193/management",
        )
        self.assertEqual(
            payload["dashboard"]["proxy"]["auth"]["connectors"][0]["password"],
            "connector-password",
        )
        self.assertEqual(
            payload["hostAliases"][0]["hostnames"],
            [
                "keycloak.dev.ed.dataspaceunit.upm",
                "minio.dev.ed.dataspaceunit.upm",
                "conn-citycounciledc-demoedc.dev.ds.dataspaceunit.upm",
                "conn-companyedc-demoedc.dev.ds.dataspaceunit.upm",
            ],
        )

    def test_connector_values_payload_maps_oidc_bff_proxy_without_connector_passwords(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = self._make_oidc_adapter(tmpdir)

            payload = adapter._connector_values_payload(
                "conn-citycounciledc-demoedc",
                "demoedc",
                [
                    "conn-citycounciledc-demoedc",
                    "conn-companyedc-demoedc",
                ],
            )

        proxy_config = payload["dashboard"]["proxy"]["config"]
        self.assertEqual(proxy_config["authMode"], "oidc-bff")
        self.assertEqual(proxy_config["clientId"], "dataspace-users")
        self.assertEqual(proxy_config["scope"], "openid profile email")
        self.assertEqual(
            proxy_config["authorizationUrl"],
            "http://keycloak.dev.ed.dataspaceunit.upm/realms/demoedc/protocol/openid-connect/auth",
        )
        self.assertEqual(
            proxy_config["logoutUrl"],
            "http://keycloak.dev.ed.dataspaceunit.upm/realms/demoedc/protocol/openid-connect/logout",
        )
        self.assertEqual(proxy_config["callbackPath"], "/edc-dashboard-api/auth/callback")
        self.assertEqual(proxy_config["loginPath"], "/edc-dashboard-api/auth/login")
        self.assertEqual(proxy_config["logoutPath"], "/edc-dashboard-api/auth/logout")
        self.assertEqual(proxy_config["cookieName"], "edc_dashboard_session")
        self.assertFalse(proxy_config["cookieSecure"])
        self.assertEqual(payload["dashboard"]["proxy"]["auth"]["connectors"], [])

    def test_render_values_file_writes_chart_values_into_edc_deployment_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = self._make_adapter(tmpdir)

            values_path = adapter._render_values_file(
                "conn-citycounciledc-demoedc",
                "demoedc",
                [
                    "conn-citycounciledc-demoedc",
                    "conn-companyedc-demoedc",
                ],
            )

            self.assertTrue(os.path.exists(values_path))
            with open(values_path, "r", encoding="utf-8") as handle:
                rendered = yaml.safe_load(handle)

        self.assertIn(os.path.join("demoedc", "values-conn-citycounciledc-demoedc.yaml"), values_path)
        self.assertEqual(rendered["connector"]["name"], "conn-citycounciledc-demoedc")
        self.assertEqual(rendered["connector"]["dataspace"], "demoedc")
        self.assertEqual(rendered["services"]["db"]["name"], "db_conn_citycounciledc_demoedc")
        self.assertIn("dashboard", rendered)
        self.assertEqual(rendered["dashboard"]["runtime"]["baseHref"], "/edc-dashboard/")

    def test_render_values_file_generates_dashboard_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = self._make_adapter(tmpdir)

            adapter._render_values_file(
                "conn-citycounciledc-demoedc",
                "demoedc",
                [
                    "conn-citycounciledc-demoedc",
                    "conn-companyedc-demoedc",
                ],
            )

            app_config_path = adapter.config_adapter.edc_dashboard_app_config_file(
                "conn-citycounciledc-demoedc",
                ds_name="demoedc",
            )
            connector_config_path = adapter.config_adapter.edc_dashboard_connector_config_file(
                "conn-citycounciledc-demoedc",
                ds_name="demoedc",
            )
            base_href_path = adapter.config_adapter.edc_dashboard_base_href_file(
                "conn-citycounciledc-demoedc",
                ds_name="demoedc",
            )

            self.assertTrue(os.path.exists(app_config_path))
            self.assertTrue(os.path.exists(connector_config_path))
            self.assertTrue(os.path.exists(base_href_path))

            with open(app_config_path, "r", encoding="utf-8") as handle:
                app_config = json.load(handle)
            with open(connector_config_path, "r", encoding="utf-8") as handle:
                connector_config = json.load(handle)
            with open(base_href_path, "r", encoding="utf-8") as handle:
                base_href = handle.read()

        self.assertEqual(app_config["appTitle"], "EDC Dashboard - conn-citycounciledc-demoedc")
        self.assertFalse(app_config["enableUserConfig"])
        self.assertEqual(connector_config[0]["connectorName"], "conn-citycounciledc-demoedc")
        self.assertEqual(
            connector_config[0]["protocolUrl"],
            "/edc-dashboard-api/connectors/conn-citycounciledc-demoedc/protocol",
        )
        self.assertEqual(base_href, "/edc-dashboard/")

    def test_stage_bootstrap_artifacts_copies_certs_and_rewrites_credentials_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = self._make_adapter(tmpdir)
            repo_dir = os.path.join(tmpdir, "bootstrap")
            source_dir = os.path.join(repo_dir, "deployments", "DEV", "demoedc")
            source_certs_dir = os.path.join(source_dir, "certs")
            os.makedirs(source_certs_dir, exist_ok=True)

            credentials_path = os.path.join(source_dir, "credentials-connector-conn-citycounciledc-demoedc.json")
            with open(credentials_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "certificates": {
                            "path": "deployments/DEV/demoedc/certs",
                            "passwd": "certificate-password",
                        }
                    },
                    handle,
                )

            with open(os.path.join(source_dir, "credentials-dataspace-demoedc.json"), "w", encoding="utf-8") as handle:
                json.dump({"realm_manager": {"user": "manager"}}, handle)

            with open(
                os.path.join(source_dir, "policy-demoedc-conn-citycounciledc-demoedc.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump({"Version": "2012-10-17"}, handle)

            for suffix in ("public.crt", "private.key", "store.p12"):
                with open(
                    os.path.join(source_certs_dir, f"conn-citycounciledc-demoedc-{suffix}"),
                    "w",
                    encoding="utf-8",
                ) as handle:
                    handle.write(f"dummy-{suffix}")

            staged = adapter._stage_bootstrap_artifacts(
                "conn-citycounciledc-demoedc",
                "demoedc",
                repo_dir,
            )

            staged_credentials_path = staged["credentials"]
            staged_certs_dir = staged["certs"]
            with open(staged_credentials_path, "r", encoding="utf-8") as handle:
                staged_credentials = json.load(handle)
            self.assertTrue(os.path.exists(staged_certs_dir))
            self.assertEqual(
                staged_credentials["certificates"]["path"],
                adapter._runtime_relative_path(staged_certs_dir),
            )
            self.assertTrue(
                os.path.exists(
                    os.path.join(
                        staged_certs_dir,
                        "conn-citycounciledc-demoedc-public.crt",
                    )
                )
            )

    def test_stage_bootstrap_artifacts_keeps_native_runtime_in_place_when_source_matches_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = self._make_adapter(tmpdir)
            repo_dir = os.path.join(tmpdir, "deployers", "edc")
            runtime_dir = os.path.join(repo_dir, "deployments", "DEV", "demoedc")
            certs_dir = os.path.join(runtime_dir, "certs")
            os.makedirs(certs_dir, exist_ok=True)
            adapter.config_adapter.edc_dataspace_runtime_dir = lambda ds_name=None: runtime_dir
            adapter.config_adapter.edc_connector_certs_dir = lambda ds_name=None: certs_dir

            credentials_path = os.path.join(runtime_dir, "credentials-connector-conn-citycounciledc-demoedc.json")
            with open(credentials_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "certificates": {
                            "path": "deployers/edc/deployments/DEV/demoedc/certs",
                            "passwd": "certificate-password",
                        }
                    },
                    handle,
                )
            with open(
                os.path.join(runtime_dir, "policy-demoedc-conn-citycounciledc-demoedc.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump({"Version": "2012-10-17"}, handle)
            with open(
                os.path.join(certs_dir, "conn-citycounciledc-demoedc-public.crt"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("dummy-public.crt")

            staged = adapter._stage_bootstrap_artifacts(
                "conn-citycounciledc-demoedc",
                "demoedc",
                repo_dir,
            )

        self.assertEqual(staged["credentials"], credentials_path)
        self.assertEqual(staged["certs"], certs_dir)
        self.assertEqual(
            staged["policy"],
            os.path.join(runtime_dir, "policy-demoedc-conn-citycounciledc-demoedc.json"),
        )

    def test_deploy_connectors_refuses_to_replace_non_edc_resources(self):
        adapter = EDCConnectorsAdapter.__new__(EDCConnectorsAdapter)
        adapter._prepare_runtime_prerequisites = lambda: ("/tmp/repo", "/tmp/python")
        adapter.load_dataspace_connectors = lambda: [
            {
                "name": "demo",
                "namespace": "demo",
                "connectors": ["conn-citycouncil-demo"],
            }
        ]
        adapter._conflicting_runtime_resources = lambda connector, namespace: [
            "deployment/conn-citycouncil-demo"
        ]

        with self.assertRaises(RuntimeError) as ctx:
            adapter.deploy_connectors()

        self.assertIn("Refusing to deploy generic EDC connector", str(ctx.exception))
        self.assertIn("deployment/conn-citycouncil-demo", str(ctx.exception))

    def test_preview_deploy_connectors_reports_render_summary_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = self._make_adapter(tmpdir)
            adapter.load_dataspace_connectors = lambda: [
                {
                    "name": "demoedc",
                    "namespace": "demoedc",
                    "connectors": [
                        "conn-citycounciledc-demoedc",
                    ],
                }
            ]
            adapter._conflicting_runtime_resources = lambda connector, namespace: []

            preview = adapter.preview_deploy_connectors()

        self.assertEqual(preview["status"], "ready")
        connector = preview["dataspaces"][0]["connectors"][0]
        self.assertEqual(connector["status"], "ready")
        self.assertTrue(connector["credentials_present"])
        self.assertFalse(connector["bootstrap_required"])
        self.assertIsNotNone(connector["render_summary"])
        self.assertEqual(
            connector["render_summary"]["management_api_url"],
            "http://conn-citycounciledc-demoedc.dev.ds.dataspaceunit.upm/management/v3",
        )
        self.assertEqual(
            connector["render_summary"]["dsp_url"],
            "http://conn-citycounciledc-demoedc.dev.ds.dataspaceunit.upm/protocol",
        )
        self.assertNotIn("secret-db", str(connector["render_summary"]))
        self.assertNotIn("vault-token", str(connector["render_summary"]))

    def test_prepare_connector_prerequisites_recreates_partial_bootstrap_when_runtime_is_missing(self):
        adapter = EDCConnectorsAdapter.__new__(EDCConnectorsAdapter)
        adapter.load_connector_credentials = lambda connector: {"database": {"name": "db", "user": "user", "passwd": "pw"}}
        adapter._edc_runtime_present = lambda connector, namespace: False
        adapter.wait_for_keycloak_admin_ready = lambda: True
        adapter.config_adapter = EdcConnectorConfigAdapter("/tmp")
        adapter._remove_edc_values_file = lambda connector, ds_name=None: None
        cleanup_calls = []
        adapter._cleanup_connector_state = lambda connector, repo_dir, ds_name, python_exec, namespace=None: cleanup_calls.append(
            (connector, ds_name, namespace)
        )
        adapter.run = lambda cmd, cwd=None, check=False: object()
        adapter.invalidate_management_api_token = lambda connector: None
        adapter.config = type(
            "Config",
            (),
            {
                "connector_credentials_path": staticmethod(lambda connector: "/tmp/missing-creds.json"),
                "NS_COMMON": "common-srvs",
            },
        )
        adapter.setup_minio_bucket = lambda namespace, ds_name, connector, credentials_path: True
        adapter.ensure_minio_policy_attached = lambda connector, ds_name=None: True

        result = adapter._prepare_connector_prerequisites(
            "conn-citycounciledc-demoedc",
            "demoedc",
            "demoedc",
            "/tmp/repo",
            "/tmp/python",
        )

        self.assertTrue(result)
        self.assertEqual(
            cleanup_calls,
            [("conn-citycounciledc-demoedc", "demoedc", "demoedc")],
        )


if __name__ == "__main__":
    unittest.main()
