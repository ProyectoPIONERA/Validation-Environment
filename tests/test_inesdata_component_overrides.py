import os
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import adapters.inesdata.components as components_module
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

    def test_ontology_hub_override_payload_adds_host_alias_for_public_self_url(self):
        adapter = self._make_adapter()

        with mock.patch.object(
            adapter,
            "_resolve_ontology_hub_self_host_alias_ip",
            return_value="10.102.17.235",
        ):
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
                "hostAliases": [
                    {
                        "ip": "10.102.17.235",
                        "hostnames": ["ontology-hub-demo.custom.ds.example.org"],
                    }
                ],
            },
        )

    def test_resolve_ontology_hub_self_host_alias_ip_prefers_explicit_valid_ip(self):
        adapter = self._make_adapter()

        ip = adapter._resolve_ontology_hub_self_host_alias_ip(
            {"ONTOLOGY_HUB_SELF_HOST_ALIAS_IP": "10.102.17.235"}
        )

        self.assertEqual(ip, "10.102.17.235")

    def test_resolve_ontology_hub_self_host_alias_ip_reads_ingress_service_cluster_ip(self):
        adapter = self._make_adapter()
        adapter.run_silent = mock.Mock(return_value="10.102.17.235")

        ip = adapter._resolve_ontology_hub_self_host_alias_ip({})

        self.assertEqual(ip, "10.102.17.235")
        adapter.run_silent.assert_called_once_with(
            "kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.clusterIP}'"
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

    def test_resolve_ontology_hub_source_dir_uses_canonical_checkout_even_if_override_is_present(self):
        adapter = self._make_adapter()
        sources_dir = os.path.join(
            os.path.dirname(os.path.abspath(components_module.__file__)),
            "sources",
            "Ontology-Hub",
        )
        fallback_dockerfile = os.path.join(sources_dir, "Dockerfile")

        def fake_isfile(path):
            if path == fallback_dockerfile:
                return True
            return False

        with mock.patch("adapters.inesdata.components.os.path.isfile", side_effect=fake_isfile):
            resolved = adapter._resolve_ontology_hub_source_dir(
                {"ONTOLOGY_HUB_SOURCE_DIR": "/tmp/custom-ontology-hub"}
            )

        self.assertEqual(resolved, sources_dir)

    def test_resolve_ontology_hub_source_dir_clones_when_sources_dir_exists_but_is_empty(self):
        adapter = self._make_adapter()
        sources_dir = os.path.join(
            os.path.dirname(os.path.abspath(components_module.__file__)),
            "sources",
        )
        ontology_hub_dir = os.path.join(sources_dir, "Ontology-Hub")
        dockerfile_path = os.path.join(ontology_hub_dir, "Dockerfile")

        clone_calls = []

        def fake_isfile(path):
            return path == dockerfile_path and len(clone_calls) > 0

        def fake_run(args, check):
            clone_calls.append((tuple(args), check))
            return None

        with (
            mock.patch("adapters.inesdata.components.os.path.isdir", side_effect=lambda path: path == ontology_hub_dir),
            mock.patch("adapters.inesdata.components.os.listdir", return_value=[]),
            mock.patch("adapters.inesdata.components.os.makedirs"),
            mock.patch("adapters.inesdata.components.os.rmdir"),
            mock.patch("adapters.inesdata.components.os.path.isfile", side_effect=fake_isfile),
            mock.patch("subprocess.run", side_effect=fake_run),
        ):
            resolved = adapter._resolve_ontology_hub_source_dir({})

        self.assertEqual(resolved, ontology_hub_dir)
        self.assertEqual(
            clone_calls,
            [
                (
                    (
                        "git",
                        "clone",
                        "https://github.com/ProyectoPIONERA/Ontology-Hub.git",
                        ontology_hub_dir,
                    ),
                    True,
                )
            ],
        )

    def test_resolve_ontology_hub_source_dir_fails_when_default_checkout_is_populated_but_invalid(self):
        adapter = self._make_adapter()
        ontology_hub_dir = os.path.join(
            os.path.dirname(os.path.abspath(components_module.__file__)),
            "sources",
            "Ontology-Hub",
        )

        with (
            mock.patch("adapters.inesdata.components.os.path.isdir", side_effect=lambda path: path == ontology_hub_dir),
            mock.patch("adapters.inesdata.components.os.listdir", return_value=["README.md"]),
            mock.patch("adapters.inesdata.components.os.path.isfile", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "Ontology-Hub source directory is not usable"):
                adapter._resolve_ontology_hub_source_dir({})

    def test_prepare_level6_local_image_builds_on_host_and_loads_into_minikube(self):
        adapter = self._make_adapter()
        deployer_config = {"LEVEL5_AUTO_BUILD_LOCAL_IMAGES": "false"}

        with (
            mock.patch.object(
                adapter,
                "_safe_load_yaml_file",
                return_value={"image": {"repository": "ontology-hub", "tag": "local"}},
            ),
            mock.patch.object(adapter, "_minikube_is_available", return_value=True),
            mock.patch.object(adapter, "_build_ontology_hub_image_on_host") as build_mock,
            mock.patch.object(adapter, "_load_image_into_minikube") as load_mock,
        ):
            result = adapter._maybe_prepare_level6_local_image(
                "ontology-hub",
                "/tmp/ontology-values.yaml",
                deployer_config,
            )

        self.assertTrue(result)
        build_mock.assert_called_once_with("ontology-hub:local", deployer_config)
        load_mock.assert_called_once_with("minikube", "ontology-hub:local")

    def test_prepare_level6_local_image_rebuilds_ontology_hub_without_consulting_host_cache(self):
        adapter = self._make_adapter()
        deployer_config = {"LEVEL5_AUTO_BUILD_LOCAL_IMAGES": "true"}

        with (
            mock.patch.object(
                adapter,
                "_safe_load_yaml_file",
                return_value={"image": {"repository": "ontology-hub", "tag": "local"}},
            ),
            mock.patch.object(adapter, "_minikube_is_available", return_value=True),
            mock.patch.object(adapter, "_host_has_image") as host_has_image_mock,
            mock.patch.object(adapter, "_build_ontology_hub_image_on_host") as build_mock,
            mock.patch.object(adapter, "_load_image_into_minikube") as load_mock,
        ):
            result = adapter._maybe_prepare_level6_local_image(
                "ontology-hub",
                "/tmp/ontology-values.yaml",
                deployer_config,
            )

        self.assertTrue(result)
        host_has_image_mock.assert_not_called()
        build_mock.assert_called_once_with("ontology-hub:local", deployer_config)
        load_mock.assert_called_once_with("minikube", "ontology-hub:local")

    def test_prepare_level6_local_image_rebuilds_ai_model_hub_even_when_cached_in_minikube(self):
        adapter = self._make_adapter()
        deployer_config = {"LEVEL5_AUTO_BUILD_LOCAL_IMAGES": "true"}

        with (
            mock.patch.object(
                adapter,
                "_safe_load_yaml_file",
                return_value={"image": {"repository": "eclipse-edc/data-dashboard", "tag": "local"}},
            ),
            mock.patch.object(adapter, "_minikube_is_available", return_value=True),
            mock.patch.object(adapter, "_minikube_has_image", return_value=True) as has_image_mock,
            mock.patch.object(adapter, "_build_ai_model_hub_image_on_host") as build_mock,
            mock.patch.object(adapter, "_load_image_into_minikube") as load_mock,
        ):
            result = adapter._maybe_prepare_level6_local_image(
                "ai-model-hub",
                "/tmp/ai-model-hub-values.yaml",
                deployer_config,
            )

        self.assertTrue(result)
        has_image_mock.assert_not_called()
        build_mock.assert_called_once_with("eclipse-edc/data-dashboard:local", deployer_config)
        load_mock.assert_called_once_with("minikube", "eclipse-edc/data-dashboard:local")

    def test_prepare_level6_local_image_fails_when_ontology_hub_chart_does_not_use_local_tag(self):
        adapter = self._make_adapter()
        deployer_config = {"LEVEL5_AUTO_BUILD_LOCAL_IMAGES": "true"}

        with (
            mock.patch.object(
                adapter,
                "_safe_load_yaml_file",
                return_value={"image": {"repository": "ontology-hub", "tag": "1.0.0"}},
            ),
            mock.patch.object(adapter, "_minikube_is_available", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "Ontology-Hub must use a local image in Level 5/6"):
                adapter._maybe_prepare_level6_local_image(
                    "ontology-hub",
                    "/tmp/ontology-values.yaml",
                    deployer_config,
                )

    def test_prepare_level6_local_image_fails_when_minikube_is_unavailable_for_ontology_hub(self):
        adapter = self._make_adapter()
        deployer_config = {"MINIKUBE_PROFILE": "custom-profile"}

        with (
            mock.patch.object(
                adapter,
                "_safe_load_yaml_file",
                return_value={"image": {"repository": "ontology-hub", "tag": "local"}},
            ),
            mock.patch.object(adapter, "_minikube_is_available", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "Minikube profile is not available for Ontology-Hub local image deployment"):
                adapter._maybe_prepare_level6_local_image(
                    "ontology-hub",
                    "/tmp/ontology-values.yaml",
                    deployer_config,
                )

    def test_wait_for_component_rollout_prefers_deployment_rollout(self):
        infrastructure = FakeInfrastructure()
        infrastructure.wait_for_deployment_rollout = mock.Mock(return_value=True)
        adapter = self._make_adapter(infrastructure=infrastructure)
        adapter._wait_for_pods_ready_by_selector = mock.Mock(return_value=True)

        result = adapter._wait_for_component_rollout(
            "demo",
            "demo-ontology-hub",
            timeout_seconds=1800,
            label="ontology-hub",
        )

        self.assertTrue(result)
        infrastructure.wait_for_deployment_rollout.assert_called_once_with(
            "demo",
            "demo-ontology-hub",
            timeout_seconds=1800,
            label="ontology-hub",
        )
        adapter._wait_for_pods_ready_by_selector.assert_not_called()

    def test_wait_for_component_rollout_falls_back_to_selector_wait_when_rollout_helper_missing(self):
        adapter = self._make_adapter()
        adapter._wait_for_pods_ready_by_selector = mock.Mock(return_value=True)

        result = adapter._wait_for_component_rollout(
            "demo",
            "demo-ontology-hub",
            timeout_seconds=1800,
            label="ontology-hub",
        )

        self.assertTrue(result)
        adapter._wait_for_pods_ready_by_selector.assert_called_once_with(
            "demo",
            "app.kubernetes.io/instance=demo-ontology-hub",
            timeout_seconds=1800,
            label="ontology-hub",
        )


if __name__ == "__main__":
    unittest.main()
