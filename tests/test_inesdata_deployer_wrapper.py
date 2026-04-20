import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deployers.inesdata.deployer import InesdataDeployer


class FakeConfig:
    NS_COMMON = "common-srvs"

    @staticmethod
    def repo_dir():
        return "/tmp/deployers/inesdata"


class FakeConfigAdapter:
    def load_deployer_config(self):
        return {
            "DS_1_NAME": "demo",
            "DS_1_NAMESPACE": "demo",
            "DS_1_CONNECTORS": "citycouncil,company",
            "DS_DOMAIN_BASE": "dev.ds.dataspaceunit.upm",
            "COMPONENTS": "ontology-hub,ai-model-hub",
        }

    @staticmethod
    def primary_dataspace_name():
        return "demo"

    @staticmethod
    def primary_dataspace_namespace():
        return "demo"

    @staticmethod
    def ds_domain_base():
        return "dev.ds.dataspaceunit.upm"


class FakeConnectors:
    @staticmethod
    def load_dataspace_connectors():
        return [
            {
                "name": "demo",
                "namespace": "demo",
                "connectors": ["conn-citycouncil-demo", "conn-company-demo"],
            }
        ]


class FakeAdapter:
    def __init__(self):
        self.config = FakeConfig
        self.config_adapter = FakeConfigAdapter()
        self.connectors = FakeConnectors()
        self.infrastructure = object()
        self.run = lambda *args, **kwargs: None
        self.run_silent = lambda *args, **kwargs: None
        self.calls = []

    def deploy_infrastructure(self):
        self.calls.append("deploy_infrastructure")
        return {"status": "infra-ok"}

    def deploy_dataspace(self):
        self.calls.append("deploy_dataspace")
        return {"status": "dataspace-ok"}

    def deploy_connectors(self):
        self.calls.append("deploy_connectors")
        return ["conn-citycouncil-demo", "conn-company-demo"]

    def get_cluster_connectors(self):
        self.calls.append("get_cluster_connectors")
        return ["conn-citycouncil-demo", "conn-company-demo"]


class FailedConnectorAdapter(FakeAdapter):
    def deploy_connectors(self):
        self.calls.append("deploy_connectors")
        return []


class FakeComponentsAdapter:
    def __init__(self):
        self.calls = []

    def deploy_components(self, components):
        self.calls.append(list(components))
        return {"deployed": list(components), "urls": {"ontology-hub": "http://ontology-hub-demo"}}


class InesdataDeployerWrapperTests(unittest.TestCase):
    def test_name_and_supported_topologies_are_stable(self):
        deployer = InesdataDeployer(adapter=FakeAdapter(), components_adapter=FakeComponentsAdapter(), config_cls=FakeConfig)

        self.assertEqual(deployer.name(), "inesdata")
        self.assertEqual(deployer.supported_topologies(), ["local"])

    def test_resolve_context_uses_existing_inesdata_conventions(self):
        deployer = InesdataDeployer(adapter=FakeAdapter(), components_adapter=FakeComponentsAdapter(), config_cls=FakeConfig)

        context = deployer.resolve_context(topology="local")

        self.assertEqual(context.deployer, "inesdata")
        self.assertEqual(context.topology, "local")
        self.assertEqual(context.dataspace_name, "demo")
        self.assertEqual(context.ds_domain_base, "dev.ds.dataspaceunit.upm")
        self.assertEqual(context.connectors, ["conn-citycouncil-demo", "conn-company-demo"])
        self.assertEqual(context.components, ["ontology-hub", "ai-model-hub"])
        self.assertEqual(context.namespace_roles.common_services_namespace, "common-srvs")
        self.assertEqual(context.namespace_roles.registration_service_namespace, "demo")
        self.assertTrue(context.runtime_dir.endswith("/tmp/deployers/inesdata/deployments/DEV/demo"))

    def test_deploy_methods_delegate_to_existing_adapter(self):
        adapter = FakeAdapter()
        deployer = InesdataDeployer(adapter=adapter, components_adapter=FakeComponentsAdapter(), config_cls=FakeConfig)
        context = deployer.resolve_context(topology="local")

        self.assertEqual(deployer.deploy_infrastructure(context), {"status": "infra-ok"})
        self.assertEqual(deployer.deploy_dataspace(context), {"status": "dataspace-ok"})
        self.assertEqual(
            deployer.deploy_connectors(context),
            ["conn-citycouncil-demo", "conn-company-demo"],
        )
        self.assertEqual(
            adapter.calls,
            ["deploy_infrastructure", "deploy_dataspace", "deploy_connectors"],
        )

    def test_deploy_connectors_raises_when_adapter_reports_no_deployed_connectors(self):
        deployer = InesdataDeployer(
            adapter=FailedConnectorAdapter(),
            components_adapter=FakeComponentsAdapter(),
            config_cls=FakeConfig,
        )
        context = deployer.resolve_context(topology="local")

        with self.assertRaises(RuntimeError) as ctx:
            deployer.deploy_connectors(context)

        self.assertIn("INESData connector deployment finished without deployed connectors", str(ctx.exception))
        self.assertIn("conn-citycouncil-demo", str(ctx.exception))

    def test_deploy_components_uses_existing_components_adapter(self):
        components_adapter = FakeComponentsAdapter()
        deployer = InesdataDeployer(adapter=FakeAdapter(), components_adapter=components_adapter, config_cls=FakeConfig)
        context = deployer.resolve_context(topology="local")

        result = deployer.deploy_components(context)

        self.assertEqual(result["deployed"], ["ontology-hub", "ai-model-hub"])
        self.assertEqual(components_adapter.calls, [["ontology-hub", "ai-model-hub"]])

    def test_validation_profile_matches_current_inesdata_ui_suite(self):
        deployer = InesdataDeployer(adapter=FakeAdapter(), components_adapter=FakeComponentsAdapter(), config_cls=FakeConfig)
        context = deployer.resolve_context(topology="local")

        profile = deployer.get_validation_profile(context)

        self.assertTrue(profile.newman_enabled)
        self.assertTrue(profile.test_data_cleanup_enabled)
        self.assertTrue(profile.playwright_enabled)
        self.assertEqual(profile.playwright_config, "validation/ui/playwright.config.ts")
        self.assertTrue(profile.component_validation_enabled)
        self.assertEqual(profile.component_groups, ["ontology-hub", "ai-model-hub"])


if __name__ == "__main__":
    unittest.main()
