import os
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.inesdata.components import INESDataComponentsAdapter
from adapters.inesdata.infrastructure import INESDataInfrastructureAdapter


class FakeConfig:
    DS_NAME = "demo"

    @classmethod
    def script_dir(cls):
        return "/tmp"

    @classmethod
    def repo_dir(cls):
        return "/tmp/repo"

    @classmethod
    def namespace_demo(cls):
        return "demo"


class FakeInfrastructure:
    def __init__(self):
        self.deploy_calls = []

    def ensure_local_infra_access(self):
        return True

    def ensure_vault_unsealed(self):
        return True

    def manage_hosts_entries(self, *args, **kwargs):
        return True

    def deploy_helm_release(self, *args, **kwargs):
        self.deploy_calls.append((args, kwargs))
        return True


class InesdataComponentOverridesTests(unittest.TestCase):
    def _make_adapter(self, infrastructure=None):
        return INESDataComponentsAdapter(
            run=mock.Mock(return_value="ok"),
            run_silent=mock.Mock(return_value=""),
            auto_mode_getter=lambda: True,
            infrastructure_adapter=infrastructure or FakeInfrastructure(),
            config_cls=FakeConfig,
        )

    def test_ontology_hub_hostname_prefers_deployer_config_inference(self):
        adapter = self._make_adapter()

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yaml", delete=False) as handle:
            yaml.safe_dump(
                {
                    "ingress": {
                        "enabled": True,
                        "host": "ontology-hub-demo.dev.ds.dataspaceunit.upm",
                    }
                },
                handle,
                sort_keys=False,
            )
            values_path = handle.name

        try:
            host = adapter._infer_component_hostname(
                "ontology-hub",
                values_path,
                {"DS_DOMAIN_BASE": "custom.ds.example.org"},
            )
        finally:
            os.unlink(values_path)

        self.assertEqual(host, "ontology-hub-demo.custom.ds.example.org")

    def test_ontology_hub_override_payload_derives_public_url_from_deployer_config(self):
        adapter = self._make_adapter()

        payload = adapter._component_values_override_payload(
            "ontology-hub",
            {"DS_DOMAIN_BASE": "custom.ds.example.org"},
        )

        self.assertEqual(
            payload,
            {
                "ingress": {
                    "enabled": True,
                    "host": "ontology-hub-demo.custom.ds.example.org",
                },
                "env": {
                    "SELF_HOST_URL": "http://ontology-hub-demo.custom.ds.example.org",
                    "BASE_URL": "http://ontology-hub-demo.custom.ds.example.org",
                },
            },
        )

    def test_deploy_helm_release_supports_multiple_values_files(self):
        run = mock.Mock(return_value="ok")
        infra = INESDataInfrastructureAdapter(
            run=run,
            run_silent=mock.Mock(return_value=""),
            auto_mode_getter=lambda: True,
        )

        result = infra.deploy_helm_release(
            "demo-ontology-hub",
            "demo",
            ["values-demo.yaml", "/tmp/ontology-hub-override.yaml"],
            cwd="/tmp/chart",
        )

        self.assertTrue(result)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertIn("-f values-demo.yaml", command)
        self.assertIn("-f /tmp/ontology-hub-override.yaml", command)
        self.assertEqual(run.call_args.kwargs["cwd"], "/tmp/chart")


if __name__ == "__main__":
    unittest.main()
