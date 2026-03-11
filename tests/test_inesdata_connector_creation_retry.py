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

    def load_deployer_config(self):
        return {
            "KC_URL": "http://keycloak-admin.local",
            "KC_USER": "admin",
            "KC_PASSWORD": "secret",
        }


class ConnectorCreationRetryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
