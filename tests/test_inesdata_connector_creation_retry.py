import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.inesdata.connectors import INESDataConnectorsAdapter


class ConnectorRetryConfig:
    DS_NAME = "demo"
    NS_COMMON = "common-srvs"
    PORT_KEYCLOAK = 18081

    def __init__(self, root):
        self.root = root

    def repo_dir(self):
        return self.root

    def venv_path(self):
        return os.path.join(self.root, ".venv")

    def python_exec(self):
        return "python3"

    def repo_requirements_path(self):
        return os.path.join(self.root, "requirements.txt")

    def registration_db_name(self):
        return "demo_rs"

    def connector_credentials_path(self, connector_name):
        return os.path.join(self.root, f"credentials-connector-{connector_name}.json")

    def connector_values_file(self, connector_name):
        return os.path.join(self.root, f"values-{connector_name}.yaml")

    def connector_dir(self):
        return self.root

    def namespace_demo(self):
        return "demo"

    def ds_domain_base(self):
        return "dev.ds.dataspaceunit.upm"

    def host_alias_domains(self):
        return []


class ConnectorRetryConfigAdapter:
    def __init__(self, root):
        self.root = root

    def get_pg_credentials(self):
        return "localhost", "postgres", "secret"

    def ds_domain_base(self):
        return "dev.ds.dataspaceunit.upm"

    def load_deployer_config(self):
        return {
            "KC_URL": "http://keycloak-admin.local",
            "KC_USER": "admin",
            "KC_PASSWORD": "secret",
        }

    def generate_connector_hosts(self, _connectors):
        return []


class ConnectorCreationRetryTests(unittest.TestCase):
    def test_keycloak_readiness_falls_back_to_local_port_forward(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConnectorRetryConfig(tmpdir)
            config_adapter = ConnectorRetryConfigAdapter(tmpdir)

            class RecordingInfra:
                def __init__(self):
                    self.calls = []

                def port_forward_service(self, *args, **kwargs):
                    self.calls.append((args, kwargs))
                    return True

            infra = RecordingInfra()

            adapter = INESDataConnectorsAdapter(
                run=lambda *_args, **_kwargs: object(),
                run_silent=lambda *_args, **_kwargs: "",
                auto_mode_getter=lambda: True,
                infrastructure_adapter=infra,
                config_adapter=config_adapter,
                config_cls=config,
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

            with mock.patch("adapters.inesdata.connectors.requests.post", side_effect=fake_post):
                self.assertTrue(adapter.wait_for_keycloak_admin_ready(timeout=5, poll_interval=0))

            self.assertEqual(len(infra.calls), 1)
            self.assertEqual(infra.calls[0][0], ("common-srvs", "keycloak", 18081, 8080))
            self.assertEqual(infra.calls[0][1], {"quiet": True})

    def test_connector_ready_falls_back_to_local_interface_port_forward(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConnectorRetryConfig(tmpdir)
            config_adapter = ConnectorRetryConfigAdapter(tmpdir)

            class Infra:
                def __init__(self):
                    self.calls = []
                    self.stops = []

                def port_forward_service(self, *args, **kwargs):
                    self.calls.append((args, kwargs))
                    return True

                def stop_port_forward_service(self, *args, **kwargs):
                    self.stops.append((args, kwargs))
                    return True

            infra = Infra()

            adapter = INESDataConnectorsAdapter(
                run=lambda *_args, **_kwargs: object(),
                run_silent=lambda *_args, **_kwargs: "conn-a-demo-inteface-123 1/1 Running 0 1m",
                auto_mode_getter=lambda: True,
                infrastructure_adapter=infra,
                config_adapter=config_adapter,
                config_cls=config,
            )

            responses = iter([
                Exception("connection refused"),
                mock.Mock(status_code=200),
            ])

            def fake_get(*_args, **_kwargs):
                item = next(responses)
                if isinstance(item, Exception):
                    raise item
                return item

            with (
                mock.patch("adapters.inesdata.connectors.requests.get", side_effect=fake_get),
                mock.patch.object(adapter, "_reserve_local_port", return_value=19080),
            ):
                self.assertTrue(adapter.wait_for_connector_ready("conn-a-demo", timeout=5))

            self.assertEqual(
                infra.calls,
                [
                    (
                        ("demo", "conn-a-demo-inteface-123", 19080, 8080),
                        {"quiet": True},
                    )
                ],
            )
            self.assertEqual(
                infra.stops,
                [
                    (
                        ("demo", "conn-a-demo-inteface-123"),
                        {"quiet": True},
                    )
                ],
            )

    def test_management_api_ready_falls_back_to_local_runtime_port_forward(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConnectorRetryConfig(tmpdir)
            config_adapter = ConnectorRetryConfigAdapter(tmpdir)

            class Infra:
                def __init__(self):
                    self.calls = []
                    self.stops = []

                def port_forward_service(self, *args, **kwargs):
                    self.calls.append((args, kwargs))
                    return True

                def stop_port_forward_service(self, *args, **kwargs):
                    self.stops.append((args, kwargs))
                    return True

            infra = Infra()

            adapter = INESDataConnectorsAdapter(
                run=lambda *_args, **_kwargs: object(),
                run_silent=lambda *_args, **_kwargs: "conn-a-demo-123 1/1 Running 0 1m",
                auto_mode_getter=lambda: True,
                infrastructure_adapter=infra,
                config_adapter=config_adapter,
                config_cls=config,
            )
            adapter.get_management_api_headers = lambda *_args, **_kwargs: {"Authorization": "Bearer token"}
            adapter.invalidate_management_api_token = lambda *_args, **_kwargs: None

            responses = iter([
                Exception("connection refused"),
                mock.Mock(status_code=200),
            ])

            def fake_post(*_args, **_kwargs):
                item = next(responses)
                if isinstance(item, Exception):
                    raise item
                return item

            with (
                mock.patch("adapters.inesdata.connectors.requests.post", side_effect=fake_post),
                mock.patch.object(adapter, "_reserve_local_port", return_value=19193),
            ):
                self.assertTrue(adapter.wait_for_management_api_ready("conn-a-demo", timeout=5, poll_interval=0))

            self.assertEqual(
                infra.calls,
                [
                    (
                        ("demo", "conn-a-demo-123", 19193, 19193),
                        {"quiet": True},
                    )
                ],
            )
            self.assertEqual(
                infra.stops,
                [
                    (
                        ("demo", "conn-a-demo-123"),
                        {"quiet": True},
                    )
                ],
            )

    def test_create_connector_retries_after_initial_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConnectorRetryConfig(tmpdir)
            config_adapter = ConnectorRetryConfigAdapter(tmpdir)
            os.makedirs(config.repo_dir(), exist_ok=True)
            open(config.repo_requirements_path(), "w", encoding="utf-8").close()
            os.makedirs(config.venv_path(), exist_ok=True)

            calls = []

            def fake_run(cmd, **_kwargs):
                calls.append(cmd)
                if "deployer.py connector create" in cmd:
                    attempt = sum("deployer.py connector create" in item for item in calls)
                    if attempt == 1:
                        return None
                return object()

            adapter = INESDataConnectorsAdapter(
                run=fake_run,
                run_silent=lambda *_args, **_kwargs: "",
                auto_mode_getter=lambda: True,
                infrastructure_adapter=type(
                    "Infra",
                    (),
                    {
                        "ensure_local_infra_access": staticmethod(lambda: True),
                        "ensure_vault_unsealed": staticmethod(lambda: True),
                        "deploy_helm_release": staticmethod(lambda *_args, **_kwargs: True),
                        "wait_for_namespace_pods": staticmethod(lambda *_args, **_kwargs: True),
                        "manage_hosts_entries": staticmethod(lambda *_args, **_kwargs: None),
                        "get_pod_by_name": staticmethod(lambda *_args, **_kwargs: "minio"),
                    },
                )(),
                config_adapter=config_adapter,
                config_cls=config,
            )
            adapter.wait_for_keycloak_admin_ready = lambda *_args, **_kwargs: True
            adapter.setup_minio_bucket = lambda *_args, **_kwargs: True
            adapter.force_clean_postgres_db = lambda *_args, **_kwargs: None
            with open(config.connector_values_file("conn-a-demo"), "w", encoding="utf-8") as handle:
                handle.write("hostAliases: []\n")
            adapter.update_connector_host_aliases = lambda *_args, **_kwargs: None

            with mock.patch("adapters.inesdata.connectors.ensure_python_requirements", lambda *_args, **_kwargs: None):
                adapter.create_connector("conn-a-demo", ["conn-a-demo", "conn-b-demo"])

            create_calls = [call for call in calls if "deployer.py connector create" in call]
            self.assertEqual(len(create_calls), 2)

    def test_create_connector_waits_for_runtime_and_interface_rollouts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConnectorRetryConfig(tmpdir)
            config_adapter = ConnectorRetryConfigAdapter(tmpdir)
            os.makedirs(config.repo_dir(), exist_ok=True)
            os.makedirs(config.venv_path(), exist_ok=True)

            class RecordingInfra:
                def __init__(self):
                    self.rollout_calls = []
                    self.namespace_wait_calls = []

                @staticmethod
                def ensure_local_infra_access():
                    return True

                @staticmethod
                def ensure_vault_unsealed():
                    return True

                @staticmethod
                def deploy_helm_release(*_args, **_kwargs):
                    return True

                def wait_for_deployment_rollout(self, *args, **kwargs):
                    self.rollout_calls.append((args, kwargs))
                    return True

                def wait_for_namespace_pods(self, *args, **kwargs):
                    self.namespace_wait_calls.append((args, kwargs))
                    return True

                @staticmethod
                def manage_hosts_entries(*_args, **_kwargs):
                    return None

                @staticmethod
                def get_pod_by_name(*_args, **_kwargs):
                    return "minio"

            infra = RecordingInfra()

            adapter = INESDataConnectorsAdapter(
                run=lambda *_args, **_kwargs: object(),
                run_silent=lambda *_args, **_kwargs: "",
                auto_mode_getter=lambda: True,
                infrastructure_adapter=infra,
                config_adapter=config_adapter,
                config_cls=config,
            )
            adapter.wait_for_keycloak_admin_ready = lambda *_args, **_kwargs: True
            adapter.setup_minio_bucket = lambda *_args, **_kwargs: True
            adapter.force_clean_postgres_db = lambda *_args, **_kwargs: None
            adapter.update_connector_host_aliases = lambda *_args, **_kwargs: None

            with open(config.connector_values_file("conn-a-demo"), "w", encoding="utf-8") as handle:
                handle.write("hostAliases: []\n")

            adapter.create_connector("conn-a-demo", ["conn-a-demo", "conn-b-demo"])

            self.assertEqual(
                infra.rollout_calls,
                [
                    (
                        ("demo", "conn-a-demo"),
                        {"timeout_seconds": 180, "label": "connector runtime 'conn-a-demo'"},
                    ),
                    (
                        ("demo", "conn-a-demo-inteface"),
                        {"timeout_seconds": 180, "label": "connector interface 'conn-a-demo'"},
                    ),
                ],
            )
            self.assertEqual(infra.namespace_wait_calls, [])

    def test_deploy_connectors_recreates_healthy_existing_connectors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConnectorRetryConfig(tmpdir)
            config_adapter = ConnectorRetryConfigAdapter(tmpdir)
            os.makedirs(config.repo_dir(), exist_ok=True)
            open(config.repo_requirements_path(), "w", encoding="utf-8").close()
            os.makedirs(config.venv_path(), exist_ok=True)
            with open(config.connector_values_file("conn-a-demo"), "w", encoding="utf-8") as handle:
                handle.write("hostAliases: []\n")

            class Infra:
                def __init__(self):
                    self.host_entries = None

                def manage_hosts_entries(self, entries):
                    self.host_entries = entries
                    return None

            infra = Infra()

            adapter = INESDataConnectorsAdapter(
                run=lambda *_args, **_kwargs: object(),
                run_silent=lambda *_args, **_kwargs: "",
                auto_mode_getter=lambda: True,
                infrastructure_adapter=infra,
                config_adapter=config_adapter,
                config_cls=config,
            )
            adapter.load_dataspace_connectors = lambda: [
                {
                    "name": "demo",
                    "namespace": "demo",
                    "connectors": ["conn-a-demo"],
                }
            ]
            adapter.connector_already_exists = lambda *_args, **_kwargs: True
            adapter.connector_is_healthy = lambda *_args, **_kwargs: True
            adapter.connector_database_credentials_valid = lambda *_args, **_kwargs: True
            adapter.create_connector = mock.Mock()
            adapter.wait_for_all_connectors = mock.Mock()

            with mock.patch("adapters.inesdata.connectors.ensure_python_requirements", lambda *_args, **_kwargs: None):
                deployed = adapter.deploy_connectors()

            self.assertEqual(deployed, ["conn-a-demo"])
            adapter.create_connector.assert_called_once_with("conn-a-demo", ["conn-a-demo"])
            adapter.wait_for_all_connectors.assert_called_once_with(["conn-a-demo"])
            self.assertEqual(infra.host_entries, [])

    def test_create_connector_applies_detected_local_image_override_without_extra_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ConnectorRetryConfig(tmpdir)
            os.makedirs(config.repo_dir(), exist_ok=True)
            open(config.repo_requirements_path(), "w", encoding="utf-8").close()
            os.makedirs(config.venv_path(), exist_ok=True)

            class ConfigAdapterWithoutExplicitImageOverrides(ConnectorRetryConfigAdapter):
                def load_deployer_config(self):
                    return {
                        "KC_URL": "http://keycloak-admin.local",
                        "KC_USER": "admin",
                        "KC_PASSWORD": "secret",
                    }

            class RecordingInfra:
                def __init__(self):
                    self.deploy_calls = []

                @staticmethod
                def ensure_local_infra_access():
                    return True

                @staticmethod
                def ensure_vault_unsealed():
                    return True

                def deploy_helm_release(self, *args, **kwargs):
                    self.deploy_calls.append((args, kwargs))
                    return True

                @staticmethod
                def wait_for_namespace_pods(*_args, **_kwargs):
                    return True

                @staticmethod
                def manage_hosts_entries(*_args, **_kwargs):
                    return None

                @staticmethod
                def get_pod_by_name(*_args, **_kwargs):
                    return "minio"

            infra = RecordingInfra()

            adapter = INESDataConnectorsAdapter(
                run=lambda *_args, **_kwargs: object(),
                run_silent=lambda *_args, **_kwargs: "",
                auto_mode_getter=lambda: True,
                infrastructure_adapter=infra,
                config_adapter=ConfigAdapterWithoutExplicitImageOverrides(tmpdir),
                config_cls=config,
            )
            adapter.wait_for_keycloak_admin_ready = lambda *_args, **_kwargs: True
            adapter.setup_minio_bucket = lambda *_args, **_kwargs: True
            adapter.force_clean_postgres_db = lambda *_args, **_kwargs: None
            adapter.update_connector_host_aliases = lambda *_args, **_kwargs: None

            with open(config.connector_values_file("conn-a-demo"), "w", encoding="utf-8") as handle:
                handle.write("hostAliases: []\n")

            override_path = os.path.join(tmpdir, "connector-local-overrides.yaml")
            with open(override_path, "w", encoding="utf-8") as handle:
                handle.write("connector:\n  image:\n    name: local/inesdata/inesdata-connector\n    tag: dev\n")

            with (
                mock.patch("adapters.inesdata.connectors.ensure_python_requirements", lambda *_args, **_kwargs: None),
                mock.patch.object(adapter, "_local_connector_image_override_path", return_value=override_path),
            ):
                adapter.create_connector("conn-a-demo", ["conn-a-demo", "conn-b-demo"])

            self.assertEqual(len(infra.deploy_calls), 1)
            args, kwargs = infra.deploy_calls[0]
            self.assertEqual(args[0], "conn-a-demo-demo")
            self.assertEqual(args[1], "demo")
            self.assertEqual(args[2], ["values-conn-a-demo.yaml", override_path])
            self.assertEqual(kwargs["cwd"], config.connector_dir())


if __name__ == "__main__":
    unittest.main()
