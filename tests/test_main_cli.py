import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

import main
from adapters.inesdata.adapter import InesdataAdapter


class FakeConfig:
    DS_NAME = "fake-ds"

    @staticmethod
    def ds_domain_base():
        return "example.local"


class FakeConfigAdapter:
    def load_deployer_config(self):
        return {"KC_URL": "http://keycloak.local", "DS_1_NAME": "fake-ds"}

    def primary_dataspace_name(self):
        return self.load_deployer_config().get("DS_1_NAME", "fake-ds")


class FakeConnectors:
    @staticmethod
    def build_connector_url(connector):
        return f"http://{connector}.example.local/interface"

    @staticmethod
    def load_connector_credentials(connector):
        return {
            "connector_user": {
                "user": f"{connector}-user",
                "passwd": "secret",
            }
        }

    @staticmethod
    def cleanup_test_entities(connector):
        return None

    @staticmethod
    def validation_test_entities_absent(connector):
        return True, []


class FakeAdapter:
    def __init__(self):
        self.config = FakeConfig
        self.config_adapter = FakeConfigAdapter()
        self.connectors = FakeConnectors()
        self.calls = []

    def deploy_infrastructure(self):
        self.calls.append("deploy_infrastructure")

    def deploy_dataspace(self):
        self.calls.append("deploy_dataspace")

    def build_recreate_dataspace_plan(self):
        return {
            "status": "planned",
            "adapter": "fake",
            "dataspace": "fake-ds",
            "namespace": "fake-ds",
            "runtime_dir": "/tmp/fake-ds",
            "preserves_shared_services": True,
            "invalidates_level_4_connectors": True,
        }

    def recreate_dataspace(self, confirm_dataspace=None):
        self.calls.append(f"recreate_dataspace:{confirm_dataspace}")
        return {"status": "recreated", "dataspace": confirm_dataspace}

    def deploy_connectors(self):
        self.calls.append("deploy_connectors")
        return ["conn-a", "conn-b"]

    def get_cluster_connectors(self):
        self.calls.append("get_cluster_connectors")
        return ["conn-a", "conn-b"]


class FakeAdapterWithInfrastructure(FakeAdapter):
    def __init__(self):
        super().__init__()
        self.infrastructure = object()


class KafkaTransferConsoleOutputTests(unittest.TestCase):
    def test_kafka_transfer_results_are_printed_with_neutral_summary(self):
        results = [
            {
                "provider": "conn-provider",
                "consumer": "conn-consumer",
                "status": "passed",
                "source_topic": "source-topic",
                "destination_topic": "destination-topic",
                "artifact_path": "/tmp/experiment/kafka_transfer/conn-provider__conn-consumer.json",
                "steps": [
                    {
                        "name": "create_kafka_asset",
                        "status": "passed",
                        "http_status": 200,
                        "asset_id": "asset-1",
                    },
                    {
                        "name": "measure_kafka_transfer_latency",
                        "status": "passed",
                        "messages_consumed": 10,
                        "average_latency_ms": 7.2,
                    },
                ],
                "metrics": {
                    "messages_produced": 10,
                    "messages_consumed": 10,
                    "average_latency_ms": 7.2,
                    "p50_latency_ms": 6.8,
                    "p95_latency_ms": 9.1,
                    "p99_latency_ms": 9.8,
                    "throughput_messages_per_second": 18.5,
                    "message_samples": [
                        {
                            "message_id": "msg-1",
                            "status": "consumed",
                            "latency_ms": 6.5,
                        }
                    ],
                },
            }
        ]

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main._print_kafka_edc_results(results)

        output = stdout.getvalue()
        self.assertIn("Kafka transfer validation results", output)
        self.assertIn("✓ PASS Kafka transfer: conn-provider -> conn-consumer", output)
        self.assertIn("PASS Kafka transfer: conn-provider -> conn-consumer", output)
        self.assertIn("Steps:", output)
        self.assertIn("✓ PASS create_kafka_asset", output)
        self.assertIn("PASS create_kafka_asset", output)
        self.assertIn("PASS measure_kafka_transfer_latency", output)
        self.assertIn("Messages: produced=10 consumed=10", output)
        self.assertIn("Latency: avg=7.2ms p50=6.8ms p95=9.1ms p99=9.8ms", output)
        self.assertIn("Throughput: 18.5 msg/s", output)
        self.assertNotIn("EDC+Kafka", output)
        self.assertNotIn("Message: id=msg-1", output)

    def test_kafka_transfer_results_mark_failed_and_skipped_status_with_icons(self):
        results = [
            {
                "provider": "conn-provider",
                "consumer": "conn-consumer",
                "status": "failed",
                "error": {"message": "boom"},
                "steps": [{"name": "create_asset", "status": "failed"}],
            },
            {
                "provider": "conn-provider",
                "consumer": "conn-consumer",
                "status": "skipped",
                "reason": "not_supported",
                "steps": [{"name": "create_asset", "status": "skipped"}],
            },
        ]

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            main._print_kafka_edc_results(results)

        output = stdout.getvalue()
        self.assertIn("✗ FAIL Kafka transfer: conn-provider -> conn-consumer (boom)", output)
        self.assertIn("✗ FAIL create_asset", output)
        self.assertIn("- SKIP Kafka transfer: conn-provider -> conn-consumer (not_supported)", output)
        self.assertIn("- SKIP create_asset", output)

    def test_kafka_transfer_results_can_print_message_samples_when_enabled(self):
        results = [
            {
                "provider": "conn-provider",
                "consumer": "conn-consumer",
                "status": "passed",
                "metrics": {
                    "messages_produced": 1,
                    "messages_consumed": 1,
                    "average_latency_ms": 3.4,
                    "p50_latency_ms": 3.4,
                    "p95_latency_ms": 3.4,
                    "p99_latency_ms": 3.4,
                    "throughput_messages_per_second": 2.0,
                    "message_samples": [
                        {
                            "message_id": "msg-1",
                            "status": "consumed",
                            "latency_ms": 3.4,
                        }
                    ],
                },
            }
        ]

        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {"PIONERA_KAFKA_TRANSFER_LOG_MESSAGES": "true"}, clear=False):
            with contextlib.redirect_stdout(stdout):
                main._print_kafka_edc_results(results)

        self.assertIn("Message: id=msg-1 status=consumed latency=3.4ms", stdout.getvalue())


class NoConnectorDeployAdapter:
    def deploy_infrastructure(self):
        return None

    def deploy_dataspace(self):
        return None


class NoConnectorsAdapter:
    def get_cluster_connectors(self):
        return []

    def deploy_connectors(self):
        return []


class FakeRunner:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self):
        return {"status": "run-ok", "adapter": type(self.kwargs["adapter"]).__name__}


class FakeValidationEngine:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self, connectors):
        return {"validated": list(connectors)}


class FakeMetricsCollector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def collect(self, connectors, experiment_dir=None):
        return {
            "connectors": list(connectors),
            "experiment_dir": experiment_dir,
            "kafka_enabled": self.kwargs.get("kafka_enabled", False),
        }

    def collect_kafka_benchmark(self, experiment_dir, run_index=1):
        if not self.kwargs.get("kafka_enabled"):
            return None
        return {
            "kafka_benchmark": {
                "status": "completed",
                "run_index": run_index,
            }
        }


class FakeStorage:
    @staticmethod
    def create_experiment_directory():
        return tempfile.mkdtemp(prefix="cli-test-")

    @staticmethod
    def save_experiment_metadata(experiment_dir, connectors):
        return None

    @staticmethod
    def newman_reports_dir(experiment_dir):
        path = tempfile.mkdtemp(prefix="cli-newman-", dir=experiment_dir)
        return path

    @staticmethod
    def save_raw_request_metrics_jsonl(results, experiment_dir):
        return None

    @staticmethod
    def save_aggregated_metrics(results, experiment_dir):
        return None

    @staticmethod
    def save_newman_results_json(results, experiment_dir):
        return None

    @staticmethod
    def save_test_results_json(results, experiment_dir):
        return None

    @staticmethod
    def save_negotiation_metrics_json(results, experiment_dir):
        return None

    @staticmethod
    def save_newman_request_metrics(results, experiment_dir):
        return None

    @staticmethod
    def save_kafka_metrics_json(results, experiment_dir):
        return None

    @staticmethod
    def save_kafka_edc_results_json(results, experiment_dir):
        return None

    @staticmethod
    def save(results, experiment_dir=None, file_name="experiment_results.json"):
        return file_name

    @staticmethod
    def create_comparison_directory(experiment_a, experiment_b):
        return tempfile.mkdtemp(prefix="cli-compare-")

    @staticmethod
    def save_comparison_json(results, comparison_dir, file_name="comparison_summary.json"):
        return os.path.join(comparison_dir, file_name)

    @staticmethod
    def save_comparison_markdown(content, comparison_dir, file_name="comparison_report.md"):
        return os.path.join(comparison_dir, file_name)


class FakeReportGenerator:
    def __init__(self, storage=None):
        self.storage = storage

    def generate(self, experiment_id):
        return {"experiment_id": experiment_id, "summary": True}

    def compare(self, experiment_a, experiment_b):
        return {
            "comparison_dir": "/tmp/comparison",
            "experiment_a": {"experiment_id": experiment_a},
            "experiment_b": {"experiment_id": experiment_b},
        }


class DryRunAwareAdapter(FakeAdapter):
    def __init__(self, dry_run=False):
        super().__init__()
        self.dry_run = dry_run


class TopologyAwareAdapter(FakeAdapter):
    def __init__(self, dry_run=False, topology="local"):
        super().__init__()
        self.dry_run = dry_run
        self.topology = topology


class PreviewAwareAdapter(FakeAdapter):
    def __init__(self, dry_run=False, topology="local"):
        super().__init__()
        self.dry_run = dry_run
        self.topology = topology

    def preview_deploy(self):
        return {
            "status": "ready",
            "topology": self.topology,
            "details": ["preflight-ok"],
        }


class DeployShadowPreviewAdapter(FakeAdapter):
    def __init__(self, dry_run=False, topology="local"):
        super().__init__()
        self.dry_run = dry_run
        self.topology = topology

    def preview_deploy(self):
        return {
            "status": "dataspace-required",
            "shared_common_services": {
                "status": "ready",
                "action": "reuse",
            },
            "shared_dataspace": {
                "status": "missing",
                "action": "deploy_dataspace",
            },
            "connectors": {
                "status": "bootstrap-required",
                "action": "deploy_connectors",
            },
            "next_step": "Deploy dataspace first.",
        }


class FakeDeployer:
    def __init__(self, adapter=None, topology="local"):
        self.adapter = adapter
        self.topology = topology

    def name(self):
        return "fake"

    @staticmethod
    def supported_topologies():
        return ["local"]

    def resolve_context(self, topology="local"):
        return {
            "deployer": "fake",
            "topology": topology,
            "environment": "DEV",
            "dataspace_name": "fake-ds",
            "ds_domain_base": "example.local",
            "connectors": ["conn-a", "conn-b"],
            "components": [],
            "namespace_roles": {
                "registration_service_namespace": "fake-ds",
                "provider_namespace": "fake-ds",
                "consumer_namespace": "fake-ds",
            },
            "runtime_dir": "/tmp/fake-ds",
            "config": {
                "DS_1_NAME": "fake-ds",
                "KC_PASSWORD": "super-secret-password",
                "VT_TOKEN": "token-value",
            },
        }

    def get_cluster_connectors(self, context=None):
        return ["conn-deployer-a", "conn-deployer-b"]

    def get_validation_profile(self, context):
        return {
            "adapter": "fake",
            "newman_enabled": True,
            "test_data_cleanup_enabled": False,
            "playwright_enabled": False,
        }

    def deploy_infrastructure(self, context):
        return {"status": "infra-ok", "dataspace": context.dataspace_name}

    def deploy_dataspace(self, context):
        return {"status": "dataspace-ok", "namespace": context.namespace_roles.registration_service_namespace}

    def deploy_connectors(self, context):
        return ["conn-deployer-a", "conn-deployer-b"]

    def deploy_components(self, context):
        return {"deployed": list(context.components), "urls": {}}


class FakeVmDeployer(FakeDeployer):
    @staticmethod
    def supported_topologies():
        return ["local", "vm-single", "vm-distributed"]

    def resolve_context(self, topology="local"):
        context = super().resolve_context(topology=topology)
        if topology == "vm-single":
            context["topology_profile"] = {
                "name": "vm-single",
                "default_address": "192.0.2.10",
                "role_addresses": {
                    "common": "192.0.2.10",
                    "registration_service": "192.0.2.10",
                    "connectors": "192.0.2.10",
                    "components": "192.0.2.10",
                },
                "ingress_external_ip": "192.0.2.10",
                "routing_mode": "host",
            }
        return context


class MainCliTests(unittest.TestCase):
    def setUp(self):
        self.fake_module = types.ModuleType("fake_adapter_module")
        self.fake_module.FakeAdapter = FakeAdapter
        self.fake_module.DryRunAwareAdapter = DryRunAwareAdapter
        self.fake_module.TopologyAwareAdapter = TopologyAwareAdapter
        self.fake_module.PreviewAwareAdapter = PreviewAwareAdapter
        self.fake_module.DeployShadowPreviewAdapter = DeployShadowPreviewAdapter
        self.fake_deployer_module = types.ModuleType("fake_deployer_module")
        self.fake_deployer_module.FakeDeployer = FakeDeployer
        self.fake_deployer_module.FakeVmDeployer = FakeVmDeployer
        self.registry = {"fake": "fake_adapter_module:FakeAdapter"}
        self.deployer_registry = {
            "fake": "fake_deployer_module:FakeDeployer",
            "fakevm": "fake_deployer_module:FakeVmDeployer",
            "edc": "fake_deployer_module:FakeDeployer",
        }
        self.module_patcher = mock.patch.dict(
            sys.modules,
            {
                "fake_adapter_module": self.fake_module,
                "fake_deployer_module": self.fake_deployer_module,
            },
        )
        self.module_patcher.start()

    def tearDown(self):
        self.module_patcher.stop()

    def test_list_command_prints_available_adapters(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = main.main(["list"], adapter_registry=self.registry)

        self.assertEqual(result, ["fake"])
        self.assertIn("fake", stdout.getvalue())

    def test_build_validation_engine_wires_validation_cleanup_dependency(self):
        adapter = FakeAdapter()

        validation_engine = main.build_validation_engine(adapter)

        self.assertIsNotNone(validation_engine.validation_test_entities_absent)
        self.assertIsNotNone(validation_engine.transfer_storage_verifier)

    def test_build_validation_engine_uses_dynamic_dataspace_name_when_available(self):
        class DynamicConfig(FakeConfig):
            @staticmethod
            def dataspace_name():
                return "demoedc"

        adapter = FakeAdapter()
        adapter.config = DynamicConfig

        validation_engine = main.build_validation_engine(adapter)

        self.assertEqual(validation_engine.ds_name, "demoedc")

    def test_list_command_rejects_extra_argument(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
            main.main(["list", "run"], adapter_registry=self.registry)

        self.assertEqual(exc.exception.code, 2)
        self.assertIn("does not accept an additional command", stderr.getvalue())

    def test_missing_arguments_prints_help_and_returns_one(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = main.main([], adapter_registry=self.registry)

        self.assertEqual(result, 1)
        self.assertIn("usage:", stdout.getvalue().lower())

    def test_menu_command_exits_without_running_actions(self):
        stdout = io.StringIO()
        with mock.patch("builtins.input", side_effect=["Q"]), contextlib.redirect_stdout(stdout):
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertEqual(result["adapter"], "fake")
        self.assertIn("DATASPACE VALIDATION ENVIRONMENT", stdout.getvalue())
        self.assertIn("Active adapter: fake", stdout.getvalue())
        self.assertIn("[Full Deployment]", stdout.getvalue())
        self.assertIn("[Operations]", stdout.getvalue())
        self.assertIn("[More]", stdout.getvalue())
        self.assertIn("T - Tools", stdout.getvalue())
        self.assertIn("U - UI Validation", stdout.getvalue())
        self.assertIn("? - Help", stdout.getvalue())

    def test_menu_help_explains_available_options(self):
        stdout = io.StringIO()
        with mock.patch("builtins.input", side_effect=["?", "Q"]), contextlib.redirect_stdout(stdout):
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertIn("MENU HELP", stdout.getvalue())
        self.assertIn("0 - Use for a fresh or full rebuild", stdout.getvalue())
        self.assertIn("4 - Use when connector deployments changed", stdout.getvalue())
        self.assertIn("H - Use when browser or CLI access fails", stdout.getvalue())
        self.assertIn("[Tools Submenu]", stdout.getvalue())
        self.assertIn("1 - Use on a clean machine or after dependency issues", stdout.getvalue())
        self.assertIn("5 - Use during development after changing local images", stdout.getvalue())
        self.assertIn("6/X - Use only when you intentionally want to destroy and recreate", stdout.getvalue())
        self.assertIn("[UI Validation Submenu]", stdout.getvalue())
        self.assertIn("1 - Use to validate the INESData portal experience", stdout.getvalue())
        self.assertIn("3 - Use when AI Model Hub UI changed", stdout.getvalue())
        self.assertIn("Legacy shortcuts still work", stdout.getvalue())

    def test_tools_submenu_delegates_setup_and_developer_actions(self):
        with mock.patch("builtins.input", side_effect=["T", "1", "5", "B", "Q"]), mock.patch.object(
            main,
            "_run_legacy_menu_action",
            return_value=None,
        ) as legacy_action:
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertEqual(
            [call.args[0] for call in legacy_action.call_args_list],
            ["bootstrap", "local_images"],
        )

    def test_tools_submenu_recreate_dataspace_requires_exact_name(self):
        stdout = io.StringIO()
        with mock.patch("builtins.input", side_effect=["T", "6", "wrong-ds", "B", "Q"]), mock.patch.object(
            main,
            "run_recreate_dataspace",
            return_value={"status": "completed"},
        ) as recreate, contextlib.redirect_stdout(stdout):
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        recreate.assert_not_called()
        self.assertIn("Dataspace recreation cancelled", stdout.getvalue())

    def test_tools_submenu_recreate_dataspace_dispatches_when_confirmed(self):
        with mock.patch("builtins.input", side_effect=["T", "X", "fake-ds", "N", "B", "Q"]), mock.patch.object(
            main,
            "run_recreate_dataspace",
            return_value={"status": "completed", "dataspace": "fake-ds"},
        ) as recreate:
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        recreate.assert_called_once()
        self.assertEqual(recreate.call_args.kwargs["confirm_dataspace"], "fake-ds")
        self.assertFalse(recreate.call_args.kwargs["with_connectors"])

    def test_tools_submenu_recreate_dataspace_can_recreate_connectors(self):
        with mock.patch("builtins.input", side_effect=["T", "X", "fake-ds", "Y", "B", "Q"]), mock.patch.object(
            main,
            "run_recreate_dataspace",
            return_value={"status": "completed", "dataspace": "fake-ds"},
        ) as recreate:
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        recreate.assert_called_once()
        self.assertTrue(recreate.call_args.kwargs["with_connectors"])

    def test_menu_keeps_legacy_setup_and_developer_shortcuts(self):
        with mock.patch("builtins.input", side_effect=["B", "L", "Q"]), mock.patch.object(
            main,
            "_run_legacy_menu_action",
            return_value=None,
        ) as legacy_action:
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertEqual(
            [call.args[0] for call in legacy_action.call_args_list],
            ["bootstrap", "local_images"],
        )

    def test_ui_validation_submenu_delegates_component_actions(self):
        with mock.patch("builtins.input", side_effect=["U", "1", "2", "3", "B", "Q"]), mock.patch.object(
            main,
            "_run_legacy_menu_action",
            return_value=None,
        ) as legacy_action:
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertEqual(
            [call.args[0] for call in legacy_action.call_args_list],
            ["inesdata_ui", "ontology_hub_ui", "ai_model_hub_ui"],
        )

    def test_menu_keeps_legacy_component_ui_validation_shortcuts(self):
        with mock.patch("builtins.input", side_effect=["I", "O", "A", "Q"]), mock.patch.object(
            main,
            "_run_legacy_menu_action",
            return_value=None,
        ) as legacy_action:
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertEqual(
            [call.args[0] for call in legacy_action.call_args_list],
            ["inesdata_ui", "ontology_hub_ui", "ai_model_hub_ui"],
        )

    def test_migrated_bootstrap_action_does_not_import_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch.object(
            main.local_menu_tools,
            "run_framework_bootstrap_interactive",
            return_value="bootstrap-ok",
        ) as migrated_action:
            result = main._run_legacy_menu_action("bootstrap")

        self.assertEqual(result, "bootstrap-ok")
        migrated_action.assert_called_once_with()

    def test_migrated_cleanup_action_does_not_import_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch.object(
            main.local_menu_tools,
            "run_workspace_cleanup_interactive",
            return_value="cleanup-ok",
        ) as migrated_action:
            result = main._run_legacy_menu_action("cleanup")

        self.assertEqual(result, "cleanup-ok")
        migrated_action.assert_called_once_with()

    def test_migrated_local_images_action_does_not_import_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch.object(
            main.local_menu_tools,
            "run_local_images_workflow_interactive",
            return_value="images-ok",
        ) as migrated_action:
            result = main._run_legacy_menu_action("local_images")

        self.assertEqual(result, "images-ok")
        migrated_action.assert_called_once_with(active_adapter="inesdata")

    def test_migrated_recover_action_does_not_import_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch.object(
            main.local_menu_tools,
            "run_connector_recovery_after_wsl_restart",
            return_value="recover-ok",
        ) as migrated_action:
            result = main._run_legacy_menu_action("recover")

        self.assertEqual(result, "recover-ok")
        migrated_action.assert_called_once_with()

    def test_migrated_inesdata_ui_action_does_not_import_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch.object(
            main.ui_interactive_menu,
            "run_inesdata_ui_tests_interactive",
            return_value="inesdata-ui-ok",
        ) as migrated_action:
            result = main._run_legacy_menu_action("inesdata_ui")

        self.assertEqual(result, "inesdata-ui-ok")
        migrated_action.assert_called_once_with()

    def test_migrated_ontology_hub_ui_action_does_not_import_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch.object(
            main.ui_interactive_menu,
            "run_ontology_hub_ui_tests_interactive",
            return_value="ontology-ui-ok",
        ) as migrated_action:
            result = main._run_legacy_menu_action("ontology_hub_ui")

        self.assertEqual(result, "ontology-ui-ok")
        migrated_action.assert_called_once_with()

    def test_migrated_ai_model_hub_ui_action_does_not_import_inesdata_py(self):
        with mock.patch.dict(sys.modules, {"inesdata": None}), mock.patch.object(
            main.ui_interactive_menu,
            "run_ai_model_hub_ui_tests_interactive",
            return_value="ai-model-ui-ok",
        ) as migrated_action:
            result = main._run_legacy_menu_action("ai_model_hub_ui")

        self.assertEqual(result, "ai-model-ui-ok")
        migrated_action.assert_called_once_with()

    def test_menu_metrics_can_run_without_kafka_by_default(self):
        calls = []

        def fake_run_metrics(*args, **kwargs):
            calls.append(kwargs)
            return {"status": "metrics-ok", "kafka_enabled": kwargs.get("kafka_enabled")}

        with mock.patch("builtins.input", side_effect=["M", "Y", "N", "Q"]), mock.patch.object(
            main,
            "run_metrics",
            side_effect=fake_run_metrics,
        ):
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["kafka_enabled"])

    def test_menu_metrics_can_enable_kafka_benchmark(self):
        calls = []

        def fake_run_metrics(*args, **kwargs):
            calls.append(kwargs)
            return {"status": "metrics-ok", "kafka_enabled": kwargs.get("kafka_enabled")}

        with mock.patch("builtins.input", side_effect=["M", "Y", "Y", "Q"]), mock.patch.object(
            main,
            "run_metrics",
            side_effect=fake_run_metrics,
        ):
            result = main.main(
                ["menu"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "exited")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["kafka_enabled"])

    def test_menu_command_rejects_extra_arguments(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
            main.main(["menu", "extra"], adapter_registry=self.registry)

        self.assertEqual(exc.exception.code, 2)
        self.assertIn("does not accept additional arguments", stderr.getvalue())

    def test_run_level_invokes_level_two_adapter_method(self):
        adapter = FakeAdapter()

        result = main.run_level(adapter, 2, deployer_name="fake")

        self.assertEqual(result["level"], 2)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(adapter.calls, ["deploy_infrastructure"])

    def test_run_level_refuses_non_local_deployment_levels_until_vm_execution_exists(self):
        adapter = FakeAdapter()

        with self.assertRaises(RuntimeError) as error:
            main.run_level(adapter, 4, deployer_name="fake", topology="vm-single")

        self.assertIn("Real Level 4 execution is not enabled", str(error.exception))
        self.assertEqual(adapter.calls, [])

    def test_run_level_four_prepares_local_edc_image_when_missing_override(self):
        adapter = FakeAdapter()
        adapter.config_adapter.load_deployer_config = lambda: {
            "KC_URL": "http://keycloak.local",
            "DS_1_NAME": "fake-ds",
            "EDC_DASHBOARD_ENABLED": "true",
        }

        with mock.patch.object(
            main,
            "_prepare_edc_local_connector_image_override",
            return_value={
                "image_name": "validation-environment/edc-connector",
                "image_tag": "local",
                "minikube_profile": "minikube",
            },
        ) as image_prepare, mock.patch.object(
            main,
            "_prepare_edc_local_dashboard_images",
            return_value={"status": "prepared"},
        ) as dashboard_prepare, mock.patch.dict(os.environ, {}, clear=True):
            result = main.run_level(adapter, 4, deployer_name="edc", topology="local")

        self.assertEqual(result["level"], 4)
        self.assertEqual(result["result"], ["conn-a", "conn-b"])
        image_prepare.assert_called_once_with(adapter)
        dashboard_prepare.assert_called_once()

    def test_run_levels_reuses_one_adapter_for_selected_levels(self):
        result = main.run_levels(
            "fake",
            levels=[2, 3, 4],
            adapter_registry=self.registry,
            deployer_registry=self.deployer_registry,
            validation_engine_cls=FakeValidationEngine,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual([entry["level"] for entry in result["levels"]], [2, 3, 4])

    def test_default_command_runs_experiment_runner(self):
        result = main.main(
            ["fake"],
            runner_cls=FakeRunner,
            adapter_registry=self.registry,
            validation_engine_cls=FakeValidationEngine,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "run-ok")
        self.assertEqual(result["adapter"], "FakeAdapter")

    def test_run_command_can_return_deployer_shadow_plan_opt_in(self):
        adapter = FakeAdapter()

        with mock.patch.dict(os.environ, {"PIONERA_USE_DEPLOYER_RUN": "true"}, clear=False):
            result = main.run_run(
                adapter,
                deployer_name="fake",
                deployer_registry=self.deployer_registry,
                topology="local",
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["mode"], "shadow")
        self.assertEqual(result["operation"], "run")
        self.assertEqual(result["sequence"], ["deploy", "validate", "metrics"])
        self.assertEqual(result["validate"]["connectors"], ["conn-deployer-a", "conn-deployer-b"])
        self.assertEqual(result["validate"]["validation_profile"]["adapter"], "fake")
        self.assertEqual(result["metrics"]["connectors"], ["conn-deployer-a", "conn-deployer-b"])

    def test_run_command_can_execute_real_deployer_chain_only_for_edc(self):
        adapter = FakeAdapter()

        with mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_RUN": "true",
                "PIONERA_EXECUTE_DEPLOYER_RUN": "true",
                "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                "PIONERA_EDC_CONNECTOR_IMAGE_TAG": "clean1",
            },
            clear=False,
        ):
            result = main.run_run(
                adapter,
                deployer_name="edc",
                deployer_registry=self.deployer_registry,
                topology="local",
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["operation"], "run")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["sequence"], ["deploy", "validate", "metrics"])
        self.assertEqual(result["experiment_dir"], result["validation"]["experiment_dir"])
        self.assertEqual(result["experiment_dir"], result["metrics"]["experiment_dir"])
        self.assertEqual(result["deployment"]["connectors"], ["conn-deployer-a", "conn-deployer-b"])
        self.assertEqual(result["validation"]["validation"], {"validated": ["conn-deployer-a", "conn-deployer-b"]})
        self.assertEqual(result["metrics"]["connectors"], ["conn-deployer-a", "conn-deployer-b"])

    def test_run_command_execute_runs_playwright_when_profile_enables_it(self):
        adapter = FakeAdapter()

        def resolve_context_with_dashboard(self, topology="local"):
            return {
                "deployer": "edc",
                "topology": topology,
                "environment": "DEV",
                "dataspace_name": "fake-ds",
                "ds_domain_base": "example.local",
                "connectors": ["conn-a", "conn-b"],
                "components": [],
                "namespace_roles": {
                    "registration_service_namespace": "fake-ds",
                    "provider_namespace": "fake-ds",
                    "consumer_namespace": "fake-ds",
                },
                "runtime_dir": "/tmp/fake-ds",
                "config": {
                    "DS_1_NAME": "fake-ds",
                    "EDC_DASHBOARD_ENABLED": os.environ.get("PIONERA_EDC_DASHBOARD_ENABLED", "false"),
                    "EDC_DASHBOARD_PROXY_AUTH_MODE": os.environ.get(
                        "PIONERA_EDC_DASHBOARD_PROXY_AUTH_MODE",
                        "service-account",
                    ),
                },
            }

        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "fake",
                "newman_enabled": True,
                "test_data_cleanup_enabled": False,
                "playwright_enabled": True,
                "playwright_config": "validation/ui/playwright.edc.config.ts",
            },
        ), mock.patch.object(
            FakeDeployer,
            "resolve_context",
            new=resolve_context_with_dashboard,
        ), mock.patch.object(
            main,
            "run_playwright_validation",
            return_value={"status": "passed", "summary": {"total_specs": 2}},
        ) as playwright_runner, mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_RUN": "true",
                "PIONERA_EXECUTE_DEPLOYER_RUN": "true",
                "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                "PIONERA_EDC_CONNECTOR_IMAGE_TAG": "clean1",
            },
            clear=False,
        ):
            result = main.run_run(
                adapter,
                deployer_name="edc",
                deployer_registry=self.deployer_registry,
                topology="local",
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["validation"]["playwright"]["status"], "passed")
        self.assertEqual(result["validation"]["playwright"]["summary"]["total_specs"], 2)
        playwright_runner.assert_called_once()

    def test_run_command_execute_can_disable_profile_playwright_explicitly(self):
        adapter = FakeAdapter()

        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "fake",
                "newman_enabled": True,
                "test_data_cleanup_enabled": False,
                "playwright_enabled": True,
                "playwright_config": "validation/ui/playwright.edc.config.ts",
            },
        ), mock.patch.object(
            main,
            "run_playwright_validation",
        ) as playwright_runner, mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_RUN": "true",
                "PIONERA_EXECUTE_DEPLOYER_RUN": "true",
                "PIONERA_ENABLE_DEPLOYER_PLAYWRIGHT": "false",
                "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                "PIONERA_EDC_CONNECTOR_IMAGE_TAG": "clean1",
            },
            clear=False,
        ):
            result = main.run_run(
                adapter,
                deployer_name="edc",
                deployer_registry=self.deployer_registry,
                topology="local",
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["validation"]["playwright"]["status"], "skipped")
        self.assertEqual(result["validation"]["playwright"]["reason"], "disabled")
        playwright_runner.assert_not_called()

    def test_run_command_execute_runs_test_data_cleanup_when_profile_enables_it(self):
        adapter = FakeAdapter()

        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "fake",
                "newman_enabled": True,
                "test_data_cleanup_enabled": True,
                "playwright_enabled": False,
            },
        ), mock.patch.object(
            main,
            "run_pre_validation_cleanup",
            return_value={"status": "completed", "summary": {"deleted_total": 2}},
        ) as cleanup_runner, mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_RUN": "true",
                "PIONERA_EXECUTE_DEPLOYER_RUN": "true",
                "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                "PIONERA_EDC_CONNECTOR_IMAGE_TAG": "clean1",
            },
            clear=False,
        ):
            result = main.run_run(
                adapter,
                deployer_name="edc",
                deployer_registry=self.deployer_registry,
                topology="local",
                validation_engine_cls=FakeValidationEngine,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["validation"]["test_data_cleanup"]["status"], "completed")
        cleanup_runner.assert_called_once()
        cleanup_kwargs = cleanup_runner.call_args.kwargs
        self.assertEqual(cleanup_kwargs["connectors"], ["conn-deployer-a", "conn-deployer-b"])

    def test_build_adapter_passes_topology_when_supported(self):
        adapter = main.build_adapter(
            "topology",
            adapter_registry={"topology": "fake_adapter_module:TopologyAwareAdapter"},
            dry_run=True,
            topology="local",
        )

        self.assertTrue(adapter.dry_run)
        self.assertEqual(adapter.topology, "local")

    def test_build_deployer_wraps_existing_adapter_without_changing_cli_flow(self):
        adapter = FakeAdapter()

        deployer = main.build_deployer(
            "fake",
            deployer_registry=self.deployer_registry,
            adapter_registry=self.registry,
            adapter=adapter,
            topology="local",
        )

        self.assertEqual(deployer.name(), "fake")
        self.assertIs(deployer.adapter, adapter)
        self.assertEqual(deployer.topology, "local")

    def test_build_deployer_orchestrator_returns_safe_internal_orchestrator(self):
        adapter = FakeAdapter()

        orchestrator = main.build_deployer_orchestrator(
            "fake",
            deployer_registry=self.deployer_registry,
            adapter_registry=self.registry,
            adapter=adapter,
            topology="local",
        )

        result = orchestrator.validate(topology="local")

        self.assertEqual(result["context"].dataspace_name, "fake-ds")
        self.assertEqual(result["profile"].adapter, "fake")
        self.assertEqual(result["connectors"], ["conn-deployer-a", "conn-deployer-b"])

    def test_deploy_command_dispatches_to_adapter(self):
        adapter = FakeAdapter()
        result = main.run_deploy(adapter)

        self.assertEqual(result, ["conn-a", "conn-b"])
        self.assertEqual(
            adapter.calls,
            ["deploy_infrastructure", "deploy_dataspace", "deploy_connectors"],
        )

    def test_deploy_command_can_return_shadow_plan_via_deployer_opt_in(self):
        adapter = FakeAdapter()

        with mock.patch.dict(os.environ, {"PIONERA_USE_DEPLOYER_DEPLOY": "true"}, clear=False):
            result = main.run_deploy(
                adapter,
                deployer_name="fake",
                deployer_registry=self.deployer_registry,
                topology="local",
            )

        self.assertEqual(result["mode"], "shadow")
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["deployer_name"], "fake")
        self.assertEqual(result["namespace_roles"]["provider_namespace"], "fake-ds")
        self.assertEqual(result["deployer_context"]["dataspace_name"], "fake-ds")
        self.assertEqual(result["deployer_context"]["config"]["KC_PASSWORD"], "***REDACTED***")
        self.assertEqual(result["deployer_context"]["config"]["VT_TOKEN"], "***REDACTED***")
        self.assertEqual(result["hosts_plan"]["level_3"], ["registration-service-fake-ds.example.local"])
        self.assertEqual(
            result["hosts_plan"]["level_4"],
            ["conn-a.example.local", "conn-b.example.local"],
        )
        self.assertEqual(result["validation_profile"]["adapter"], "fake")
        self.assertEqual(adapter.calls, [])

    def test_deploy_command_non_local_uses_deployer_shadow_plan_by_default(self):
        adapter = FakeAdapter()

        result = main.run_deploy(
            adapter,
            deployer_name="fakevm",
            deployer_registry=self.deployer_registry,
            topology="vm-single",
        )

        self.assertEqual(result["mode"], "shadow")
        self.assertEqual(result["topology"], "vm-single")
        self.assertEqual(result["hosts_plan"]["address"], "192.0.2.10")
        self.assertEqual(adapter.calls, [])

    def test_deploy_shadow_plan_includes_level_plan_from_adapter_preflight(self):
        adapter = DeployShadowPreviewAdapter(topology="local")

        with mock.patch.dict(os.environ, {"PIONERA_USE_DEPLOYER_DEPLOY": "true"}, clear=False):
            result = main.run_deploy(
                adapter,
                deployer_name="fake",
                deployer_registry=self.deployer_registry,
                topology="local",
            )

        self.assertEqual(result["preflight"]["status"], "dataspace-required")
        self.assertEqual(result["level_plan"]["level_1_2"]["status"], "ready")
        self.assertEqual(result["level_plan"]["level_3"]["status"], "missing")
        self.assertEqual(result["level_plan"]["level_4"]["status"], "bootstrap-required")
        self.assertEqual(result["level_plan"]["level_5"]["status"], "not-applicable")

    def test_deploy_command_can_execute_real_deployer_only_for_edc(self):
        adapter = FakeAdapter()

        with mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EXECUTE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                "PIONERA_EDC_CONNECTOR_IMAGE_TAG": "clean1",
            },
            clear=False,
        ):
            result = main.run_deploy(
                adapter,
                deployer_name="edc",
                deployer_registry=self.deployer_registry,
                topology="local",
            )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["deployer_name"], "edc")
        self.assertEqual(result["deployment"]["infrastructure"]["status"], "infra-ok")
        self.assertEqual(result["deployment"]["dataspace"]["status"], "dataspace-ok")
        self.assertEqual(result["deployment"]["connectors"], ["conn-deployer-a", "conn-deployer-b"])
        self.assertEqual(result["validation_profile"]["adapter"], "fake")
        self.assertEqual(result["hosts_sync"]["status"], "skipped")

    def test_deploy_command_can_sync_hosts_when_explicitly_enabled(self):
        adapter = FakeAdapter()

        with tempfile.NamedTemporaryFile("w+", encoding="utf-8") as hosts_file, mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EXECUTE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                "PIONERA_EDC_CONNECTOR_IMAGE_TAG": "clean1",
                "PIONERA_SYNC_HOSTS": "true",
                "PIONERA_HOSTS_FILE": hosts_file.name,
            },
            clear=False,
        ):
            hosts_file.write("127.0.0.1 localhost\n")
            hosts_file.flush()
            result = main.run_deploy(
                adapter,
                deployer_name="edc",
                deployer_registry=self.deployer_registry,
                topology="local",
            )
            hosts_file.seek(0)
            hosts_content = hosts_file.read()

        self.assertEqual(result["hosts_sync"]["status"], "updated")
        self.assertIn("# BEGIN Validation-Environment dataspace fake-ds", hosts_content)
        self.assertIn("127.0.0.1 registration-service-fake-ds.example.local", hosts_content)
        self.assertIn("127.0.0.1 conn-a.example.local", hosts_content)

    def test_hosts_command_plans_entries_without_modifying_hosts_by_default(self):
        adapter = FakeAdapter()

        result = main.run_hosts(
            adapter,
            deployer_name="fake",
            deployer_registry=self.deployer_registry,
            topology="local",
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["hosts_sync"]["reason"], "disabled")
        self.assertEqual(result["hosts_plan"]["level_3"], ["registration-service-fake-ds.example.local"])
        self.assertEqual(result["hosts_plan"]["level_4"], ["conn-a.example.local", "conn-b.example.local"])

    def test_hosts_command_vm_single_uses_vm_address_from_context(self):
        adapter = FakeAdapter()

        result = main.run_hosts(
            adapter,
            deployer_name="fakevm",
            deployer_registry=self.deployer_registry,
            topology="vm-single",
        )

        self.assertEqual(result["hosts_plan"]["address"], "192.0.2.10")
        self.assertIn(
            "192.0.2.10 registration-service-fake-ds.example.local",
            result["hosts_plan"]["blocks"]["dataspace fake-ds"],
        )
        self.assertIn(
            "192.0.2.10 conn-a.example.local",
            result["hosts_plan"]["blocks"]["connectors fake fake-ds"],
        )

    def test_hosts_command_applies_only_missing_entries_when_enabled(self):
        adapter = FakeAdapter()

        with tempfile.NamedTemporaryFile("w+", encoding="utf-8") as hosts_file, mock.patch.dict(
            os.environ,
            {
                "PIONERA_SYNC_HOSTS": "true",
                "PIONERA_HOSTS_FILE": hosts_file.name,
            },
            clear=False,
        ):
            hosts_file.write("127.0.0.1 localhost\n127.0.0.1 conn-a.example.local\n")
            hosts_file.flush()
            result = main.run_hosts(
                adapter,
                deployer_name="fake",
                deployer_registry=self.deployer_registry,
                topology="local",
            )
            hosts_file.seek(0)
            hosts_content = hosts_file.read()

        self.assertEqual(result["status"], "updated")
        self.assertIn("127.0.0.1 conn-a.example.local", result["hosts_sync"]["skipped_existing"]["connectors fake fake-ds"])
        self.assertIn("127.0.0.1 conn-b.example.local", hosts_content)
        self.assertEqual(hosts_content.count("conn-a.example.local"), 1)

    def test_deploy_command_prepares_local_edc_image_when_missing_override(self):
        adapter = FakeAdapter()
        adapter.config_adapter.load_deployer_config = lambda: {
            "KC_URL": "http://keycloak.local",
            "DS_1_NAME": "fake-ds",
            "EDC_DASHBOARD_ENABLED": "true",
        }

        with mock.patch.object(
            main,
            "_prepare_edc_local_connector_image_override",
            return_value={
                "image_name": "validation-environment/edc-connector",
                "image_tag": "local",
                "minikube_profile": "minikube",
            },
        ) as image_prepare, mock.patch.object(
            main,
            "_prepare_edc_local_dashboard_images",
            return_value={"status": "prepared"},
        ) as dashboard_prepare, mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EXECUTE_DEPLOYER_DEPLOY": "true",
            },
            clear=True,
        ):
            result = main.run_deploy(
                adapter,
                deployer_name="edc",
                deployer_registry=self.deployer_registry,
                topology="local",
            )

        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["deployment"]["connectors"], ["conn-deployer-a", "conn-deployer-b"])
        image_prepare.assert_called_once_with(adapter)
        dashboard_prepare.assert_called_once()

    def test_deploy_command_refuses_real_edc_execution_with_partial_image_override(self):
        adapter = FakeAdapter()

        with mock.patch.object(main, "_prepare_edc_local_connector_image_override") as image_prepare, \
                mock.patch.dict(
                    os.environ,
                    {
                        "PIONERA_USE_DEPLOYER_DEPLOY": "true",
                        "PIONERA_EXECUTE_DEPLOYER_DEPLOY": "true",
                        "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                    },
                    clear=True,
                ):
            with self.assertRaises(RuntimeError) as exc:
                main.run_deploy(
                    adapter,
                    deployer_name="edc",
                    deployer_registry=self.deployer_registry,
                    topology="local",
                )

        self.assertIn("EDC connector image overrides", str(exc.exception))
        image_prepare.assert_not_called()

    def test_prepare_edc_local_dashboard_images_builds_dashboard_and_proxy(self):
        adapter = FakeAdapter()
        config = {
            "DS_1_NAME": "fake-ds",
            "EDC_DASHBOARD_ENABLED": "true",
            "EDC_DASHBOARD_IMAGE_NAME": "validation-environment/edc-dashboard",
            "EDC_DASHBOARD_IMAGE_TAG": "local-ui",
            "EDC_DASHBOARD_PROXY_IMAGE_NAME": "validation-environment/edc-dashboard-proxy",
            "EDC_DASHBOARD_PROXY_IMAGE_TAG": "local-proxy",
        }

        with mock.patch("main.subprocess.run", return_value=mock.Mock(returncode=0)) as run_command, \
                mock.patch.dict(os.environ, {}, clear=True):
            result = main._prepare_edc_local_dashboard_images(adapter, config)
            dashboard_tag = os.environ["PIONERA_EDC_DASHBOARD_IMAGE_TAG"]
            proxy_tag = os.environ["PIONERA_EDC_DASHBOARD_PROXY_IMAGE_TAG"]

        self.assertEqual(result["status"], "prepared")
        self.assertEqual(result["dashboard_image"], "validation-environment/edc-dashboard:local-ui")
        self.assertEqual(result["dashboard_proxy_image"], "validation-environment/edc-dashboard-proxy:local-proxy")
        self.assertEqual(run_command.call_count, 2)
        self.assertIn("build_dashboard_image.sh", run_command.call_args_list[0].args[0][1])
        self.assertIn("build_dashboard_proxy_image.sh", run_command.call_args_list[1].args[0][1])
        self.assertEqual(dashboard_tag, "local-ui")
        self.assertEqual(proxy_tag, "local-proxy")

    def test_deploy_command_refuses_real_edc_execution_on_shared_demo_dataspace(self):
        adapter = FakeAdapter()
        adapter.config_adapter = types.SimpleNamespace(
            load_deployer_config=lambda: {
                "KC_URL": "http://keycloak.local",
                "DS_1_NAME": "demo",
            },
            primary_dataspace_name=lambda: "demo",
        )

        with mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EXECUTE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EDC_CONNECTOR_IMAGE_NAME": "validation-environment/edc-connector",
                "PIONERA_EDC_CONNECTOR_IMAGE_TAG": "clean1",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as exc:
                main.run_deploy(
                    adapter,
                    deployer_name="edc",
                    deployer_registry=self.deployer_registry,
                    topology="local",
                )

        self.assertIn("shared dataspace 'demo'", str(exc.exception))

    def test_deploy_command_keeps_shadow_mode_for_non_edc_even_if_execution_flag_is_enabled(self):
        adapter = FakeAdapter()

        with mock.patch.dict(
            os.environ,
            {
                "PIONERA_USE_DEPLOYER_DEPLOY": "true",
                "PIONERA_EXECUTE_DEPLOYER_DEPLOY": "true",
            },
            clear=False,
        ):
            result = main.run_deploy(
                adapter,
                deployer_name="fake",
                deployer_registry=self.deployer_registry,
                topology="local",
            )

        self.assertEqual(result["mode"], "shadow")

    def test_deploy_command_requires_connector_deployment(self):
        with self.assertRaises(RuntimeError):
            main.run_deploy(NoConnectorDeployAdapter())

    def test_validate_command_uses_validation_engine(self):
        result = main.main(
            ["fake", "validate"],
            adapter_registry=self.registry,
            validation_engine_cls=FakeValidationEngine,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["validation"], {"validated": ["conn-a", "conn-b"]})
        self.assertEqual(result["newman_request_metrics"], [])
        self.assertEqual(result["storage_checks"], [])
        self.assertTrue(result["experiment_dir"].startswith("/tmp/cli-test-"))
        self.assertEqual(result["test_data_cleanup"]["status"], "skipped")
        self.assertEqual(result["test_data_cleanup"]["reason"], "disabled")

    def test_validate_command_uses_deployer_resolution_by_default_when_available(self):
        result = main.main(
            ["fake", "validate"],
            adapter_registry=self.registry,
            deployer_registry=self.deployer_registry,
            validation_engine_cls=FakeValidationEngine,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["validation"], {"validated": ["conn-deployer-a", "conn-deployer-b"]})
        self.assertEqual(result["validation_profile"]["adapter"], "fake")
        self.assertTrue(result["validation_profile"]["newman_enabled"])
        self.assertFalse(result["validation_profile"]["playwright_enabled"])
        self.assertEqual(result["deployer_context"]["dataspace_name"], "fake-ds")
        self.assertEqual(result["deployer_context"]["config"]["KC_PASSWORD"], "***REDACTED***")
        self.assertEqual(result["deployer_context"]["config"]["VT_TOKEN"], "***REDACTED***")

    def test_validate_command_runs_kafka_edc_after_newman_for_supported_adapter(self):
        events = []

        class RecordingValidationEngine(FakeValidationEngine):
            def run(self, connectors):
                events.append("validation")
                return super().run(connectors)

        class RecordingMetricsCollector:
            def collect_experiment_newman_metrics(self, experiment_dir):
                events.append("newman_metrics")
                return [{"request": "login"}]

        class KafkaReadyAdapter(FakeAdapter):
            def get_kafka_config(self):
                return {"bootstrap_servers": "localhost:9092"}

        class InesdataValidationDeployer(FakeDeployer):
            def get_validation_profile(self, context):
                return {
                    "adapter": "inesdata",
                    "newman_enabled": True,
                    "test_data_cleanup_enabled": False,
                    "playwright_enabled": False,
                }

        def run_kafka(connectors, experiment_dir, *, validator, experiment_storage):
            events.append("kafka_edc")
            return [{"status": "passed", "provider": connectors[0], "consumer": connectors[1]}]

        self.fake_module.KafkaReadyAdapter = KafkaReadyAdapter
        self.fake_deployer_module.InesdataValidationDeployer = InesdataValidationDeployer
        registry = {
            **self.registry,
            "fake": "fake_adapter_module:KafkaReadyAdapter",
        }
        deployer_registry = {
            **self.deployer_registry,
            "fake": "fake_deployer_module:InesdataValidationDeployer",
        }

        with mock.patch.object(
            main,
            "build_metrics_collector",
            return_value=RecordingMetricsCollector(),
        ), mock.patch.object(
            main,
            "build_kafka_edc_validation_suite",
            return_value=mock.Mock(),
        ), mock.patch.object(
            main,
            "run_kafka_edc_validation",
            side_effect=run_kafka,
        ):
            result = main.main(
                ["fake", "validate"],
                adapter_registry=registry,
                deployer_registry=deployer_registry,
                validation_engine_cls=RecordingValidationEngine,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(events, ["validation", "newman_metrics", "kafka_edc"])
        self.assertEqual(result["kafka_edc_results"][0]["status"], "passed")

    def test_validate_command_runs_test_data_cleanup_when_enabled(self):
        with mock.patch.object(
            main,
            "run_pre_validation_cleanup",
            return_value={"status": "completed", "summary": {"deleted_total": 3}},
        ) as cleanup_runner, mock.patch.dict(
            os.environ,
            {
                "PIONERA_TEST_DATA_CLEANUP": "true",
                "PIONERA_TEST_DATA_CLEANUP_MODE": "dry-run",
            },
            clear=False,
        ):
            result = main.main(
                ["fake", "validate"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["test_data_cleanup"]["status"], "completed")
        cleanup_runner.assert_called_once()
        cleanup_kwargs = cleanup_runner.call_args.kwargs
        self.assertEqual(cleanup_kwargs["connectors"], ["conn-deployer-a", "conn-deployer-b"])
        self.assertEqual(cleanup_kwargs["mode"], "dry-run")
        self.assertTrue(cleanup_kwargs["report_enabled"])

    def test_level6_public_endpoint_preflight_builds_dataspace_and_connector_urls(self):
        adapter = FakeAdapterWithInfrastructure()
        context = types.SimpleNamespace(
            topology="local",
            dataspace_name="fake-ds",
            ds_domain_base="example.local",
            config={
                "KC_URL": "http://keycloak-admin.example.local",
                "KC_INTERNAL_URL": "http://keycloak.example.local",
                "MINIO_HOSTNAME": "minio.example.local",
            },
        )

        with mock.patch.object(
            main,
            "ensure_public_endpoints_accessible",
            return_value={"status": "passed", "checked": []},
        ) as preflight:
            result = main._ensure_level6_public_endpoint_access(
                adapter,
                ["conn-a"],
                context,
            )

        self.assertEqual(result["status"], "passed")
        endpoints = preflight.call_args.args[0]
        urls = {endpoint["url"] for endpoint in endpoints}
        self.assertIn("http://keycloak-admin.example.local", urls)
        self.assertIn("http://keycloak.example.local", urls)
        self.assertIn("http://minio.example.local", urls)
        self.assertIn("http://registration-service-fake-ds.example.local", urls)
        self.assertIn("http://conn-a.example.local/interface", urls)

    def test_cleanup_failure_hint_explains_local_artifact_credential_mismatch(self):
        cleanup_result = {
            "connectors": [
                {
                    "errors": [
                        {
                            "message": (
                                "Token request for conn-a failed with HTTP 401: "
                                '{"error":"invalid_grant","error_description":"Invalid user credentials"}'
                            )
                        }
                    ],
                    "storage": {
                        "errors": [
                            {
                                "message": (
                                    "S3 operation failed; code: InvalidAccessKeyId, "
                                    "message: The Access Key Id you provided does not exist"
                                )
                            }
                        ]
                    },
                }
            ]
        }

        hint = main._test_data_cleanup_failure_hint(cleanup_result)

        self.assertIn("Local deployment artifacts are out of sync", hint)
        self.assertIn("Run Level 4 again from this same checkout", hint)

    def test_validate_command_runs_test_data_cleanup_when_profile_enables_it_by_default(self):
        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "fake",
                "newman_enabled": True,
                "test_data_cleanup_enabled": True,
                "playwright_enabled": False,
            },
        ), mock.patch.object(
            main,
            "run_pre_validation_cleanup",
            return_value={"status": "completed", "summary": {"deleted_total": 1}},
        ) as cleanup_runner:
            result = main.main(
                ["fake", "validate"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["test_data_cleanup"]["status"], "completed")
        cleanup_runner.assert_called_once()

    def test_validate_command_can_disable_profile_test_data_cleanup_explicitly(self):
        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "fake",
                "newman_enabled": True,
                "test_data_cleanup_enabled": True,
                "playwright_enabled": False,
            },
        ), mock.patch.object(
            main,
            "run_pre_validation_cleanup",
        ) as cleanup_runner, mock.patch.dict(
            os.environ,
            {"PIONERA_DISABLE_TEST_DATA_CLEANUP": "true"},
            clear=False,
        ):
            result = main.main(
                ["fake", "validate"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["test_data_cleanup"]["status"], "skipped")
        self.assertEqual(result["test_data_cleanup"]["reason"], "disabled")
        cleanup_runner.assert_not_called()

    def test_validate_command_fails_clearly_when_test_data_cleanup_fails(self):
        with mock.patch.object(
            main,
            "run_pre_validation_cleanup",
            return_value={
                "status": "failed",
                "report_path": "/tmp/experiment/cleanup/test_data_cleanup.json",
            },
        ), mock.patch.dict(
            os.environ,
            {"PIONERA_TEST_DATA_CLEANUP": "true"},
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as exc:
                main.main(
                    ["fake", "validate"],
                    adapter_registry=self.registry,
                    deployer_registry=self.deployer_registry,
                    validation_engine_cls=FakeValidationEngine,
                    experiment_storage=FakeStorage,
                )

        self.assertIn("Pre-validation test data cleanup failed", str(exc.exception))
        self.assertIn("test_data_cleanup.json", str(exc.exception))

    def test_validate_command_can_disable_deployer_resolution_explicitly(self):
        with mock.patch.dict(os.environ, {"PIONERA_DISABLE_DEPLOYER_VALIDATE": "true"}, clear=False):
            result = main.main(
                ["fake", "validate"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["validation"], {"validated": ["conn-a", "conn-b"]})
        self.assertIsNone(result["validation_profile"])
        self.assertIsNone(result["deployer_context"])

    def test_validate_command_can_run_playwright_when_profile_enables_it(self):
        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "fake",
                "newman_enabled": True,
                "playwright_enabled": True,
                "playwright_config": "validation/ui/playwright.edc.config.ts",
            },
        ), mock.patch.object(
            main,
            "run_playwright_validation",
            return_value={"status": "passed", "summary": {"total_specs": 3}},
        ) as playwright_runner:
            result = main.main(
                ["fake", "validate"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["validation"], {"validated": ["conn-deployer-a", "conn-deployer-b"]})
        self.assertEqual(result["playwright"]["status"], "passed")
        self.assertEqual(result["playwright"]["summary"]["total_specs"], 3)
        playwright_runner.assert_called_once()

    def test_validate_command_can_disable_profile_playwright_explicitly(self):
        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "fake",
                "newman_enabled": True,
                "playwright_enabled": True,
                "playwright_config": "validation/ui/playwright.edc.config.ts",
            },
        ), mock.patch.object(main, "run_playwright_validation") as playwright_runner, mock.patch.dict(
            os.environ,
            {"PIONERA_DISABLE_DEPLOYER_PLAYWRIGHT": "true"},
            clear=False,
        ):
            result = main.main(
                ["fake", "validate"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                validation_engine_cls=FakeValidationEngine,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["playwright"]["status"], "skipped")
        self.assertEqual(result["playwright"]["reason"], "disabled")
        playwright_runner.assert_not_called()

    def test_validate_command_fails_clearly_when_edc_playwright_is_enabled_but_dashboard_is_disabled(self):
        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "edc",
                "newman_enabled": True,
                "playwright_enabled": True,
                "playwright_config": "validation/ui/playwright.edc.config.ts",
            },
        ), mock.patch.dict(
            os.environ,
            {"PIONERA_ENABLE_DEPLOYER_PLAYWRIGHT": "true"},
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as exc:
                main.main(
                    ["fake", "validate"],
                    adapter_registry=self.registry,
                    deployer_registry={"fake": "fake_deployer_module:FakeDeployer"},
                    validation_engine_cls=FakeValidationEngine,
                    experiment_storage=FakeStorage,
                )

        self.assertIn("EDC_DASHBOARD_ENABLED=true", str(exc.exception))

    def test_validate_command_fails_clearly_when_edc_playwright_auth_mode_is_not_oidc_bff(self):
        def resolve_context_without_oidc(self, topology="local"):
            return {
                "deployer": "edc",
                "topology": topology,
                "environment": "DEV",
                "dataspace_name": "fake-ds",
                "ds_domain_base": "example.local",
                "connectors": ["conn-a", "conn-b"],
                "components": [],
                "namespace_roles": {
                    "registration_service_namespace": "fake-ds",
                    "provider_namespace": "fake-ds",
                    "consumer_namespace": "fake-ds",
                },
                "runtime_dir": "/tmp/fake-ds",
                "config": {
                    "DS_1_NAME": "fake-ds",
                    "EDC_DASHBOARD_ENABLED": "true",
                    "EDC_DASHBOARD_PROXY_AUTH_MODE": "service-account",
                },
            }

        with mock.patch.object(
            FakeDeployer,
            "get_validation_profile",
            return_value={
                "adapter": "edc",
                "newman_enabled": True,
                "playwright_enabled": True,
                "playwright_config": "validation/ui/playwright.edc.config.ts",
            },
        ), mock.patch.object(
            FakeDeployer,
            "resolve_context",
            new=resolve_context_without_oidc,
        ), mock.patch.dict(
            os.environ,
            {"PIONERA_ENABLE_DEPLOYER_PLAYWRIGHT": "true"},
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as exc:
                main.main(
                    ["fake", "validate"],
                    adapter_registry=self.registry,
                    deployer_registry={"fake": "fake_deployer_module:FakeDeployer"},
                    validation_engine_cls=FakeValidationEngine,
                    experiment_storage=FakeStorage,
                )

        self.assertIn("EDC_DASHBOARD_PROXY_AUTH_MODE=oidc-bff", str(exc.exception))

    def test_validate_command_allows_edc_playwright_when_dashboard_runtime_artifacts_exist(self):
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_dir = os.path.join(runtime_root, "fake-ds")
            dashboard_dir = os.path.join(runtime_dir, "dashboard", "conn-a")
            os.makedirs(dashboard_dir, exist_ok=True)
            with open(os.path.join(dashboard_dir, "app-config.json"), "w", encoding="utf-8") as handle:
                handle.write("{}\n")
            with open(
                os.path.join(dashboard_dir, "edc-connector-config.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("[]\n")
            with open(os.path.join(runtime_dir, "values-conn-a.yaml"), "w", encoding="utf-8") as handle:
                handle.write("dashboard:\n  authMode: oidc-bff\n")

            def resolve_context_from_runtime(self, topology="local"):
                return {
                    "deployer": "edc",
                    "topology": topology,
                    "environment": "DEV",
                    "dataspace_name": "fake-ds",
                    "ds_domain_base": "example.local",
                    "connectors": ["conn-a", "conn-b"],
                    "components": [],
                    "namespace_roles": {
                        "registration_service_namespace": "fake-ds",
                        "provider_namespace": "fake-ds",
                        "consumer_namespace": "fake-ds",
                    },
                    "runtime_dir": runtime_dir,
                    "config": {
                        "DS_1_NAME": "fake-ds",
                        "EDC_DASHBOARD_ENABLED": "false",
                        "EDC_DASHBOARD_PROXY_AUTH_MODE": "service-account",
                    },
                }

            with mock.patch.object(
                FakeDeployer,
                "get_validation_profile",
                return_value={
                    "adapter": "edc",
                    "newman_enabled": True,
                    "playwright_enabled": True,
                    "playwright_config": "validation/ui/playwright.edc.config.ts",
                },
            ), mock.patch.object(
                FakeDeployer,
                "resolve_context",
                new=resolve_context_from_runtime,
            ), mock.patch.object(
                main,
                "run_playwright_validation",
                return_value={"status": "passed", "summary": {"total_specs": 5}},
            ) as playwright_runner, mock.patch.object(
                main,
                "_wait_for_edc_dashboard_readiness",
                return_value={"status": "passed", "gates": []},
            ) as readiness_probe, mock.patch.dict(
                os.environ,
                {"PIONERA_ENABLE_DEPLOYER_PLAYWRIGHT": "true"},
                clear=False,
            ):
                result = main.main(
                    ["fake", "validate"],
                    adapter_registry=self.registry,
                    deployer_registry={"fake": "fake_deployer_module:FakeDeployer"},
                    validation_engine_cls=FakeValidationEngine,
                    experiment_storage=FakeStorage,
                )

        self.assertEqual(result["playwright"]["status"], "passed")
        self.assertEqual(result["playwright"]["summary"]["total_specs"], 5)
        playwright_runner.assert_called_once()
        readiness_probe.assert_called_once()

    def test_validate_command_fails_clearly_when_edc_dashboard_services_are_not_ready(self):
        with tempfile.TemporaryDirectory() as runtime_root:
            runtime_dir = os.path.join(runtime_root, "fake-ds")
            dashboard_dir = os.path.join(runtime_dir, "dashboard", "conn-a")
            os.makedirs(dashboard_dir, exist_ok=True)
            with open(os.path.join(dashboard_dir, "app-config.json"), "w", encoding="utf-8") as handle:
                handle.write("{}\n")
            with open(
                os.path.join(dashboard_dir, "edc-connector-config.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("[]\n")
            with open(os.path.join(runtime_dir, "values-conn-a.yaml"), "w", encoding="utf-8") as handle:
                handle.write("dashboard:\n  authMode: oidc-bff\n")

            def resolve_context_from_runtime(self, topology="local"):
                return {
                    "deployer": "edc",
                    "topology": topology,
                    "environment": "DEV",
                    "dataspace_name": "fake-ds",
                    "ds_domain_base": "example.local",
                    "connectors": ["conn-a"],
                    "components": [],
                    "namespace_roles": {
                        "registration_service_namespace": "fake-ds",
                        "provider_namespace": "fake-ds",
                        "consumer_namespace": "fake-ds",
                    },
                    "runtime_dir": runtime_dir,
                    "config": {
                        "DS_1_NAME": "fake-ds",
                        "EDC_DASHBOARD_ENABLED": "false",
                        "EDC_DASHBOARD_PROXY_AUTH_MODE": "service-account",
                    },
                }

            with mock.patch.object(
                FakeDeployer,
                "get_validation_profile",
                return_value={
                    "adapter": "edc",
                    "newman_enabled": True,
                    "playwright_enabled": True,
                    "playwright_config": "validation/ui/playwright.edc.config.ts",
                },
            ), mock.patch.object(
                FakeDeployer,
                "resolve_context",
                new=resolve_context_from_runtime,
            ), mock.patch.object(
                main,
                "_wait_for_edc_dashboard_readiness",
                return_value={
                    "status": "failed",
                    "artifact": "/tmp/dashboard_readiness.json",
                    "gates": [
                        {
                            "service": "conn-a-dashboard",
                            "ready": False,
                            "detail": "service has no ready endpoints",
                        }
                    ],
                },
            ), mock.patch.object(main, "run_playwright_validation") as playwright_runner, mock.patch.dict(
                os.environ,
                {"PIONERA_ENABLE_DEPLOYER_PLAYWRIGHT": "true"},
                clear=False,
            ):
                with self.assertRaises(RuntimeError) as exc:
                    main.main(
                        ["fake", "validate"],
                        adapter_registry=self.registry,
                        deployer_registry={"fake": "fake_deployer_module:FakeDeployer"},
                        validation_engine_cls=FakeValidationEngine,
                        experiment_storage=FakeStorage,
                    )

        self.assertIn("dashboard and dashboard-proxy services", str(exc.exception))
        self.assertIn("conn-a-dashboard: service has no ready endpoints", str(exc.exception))
        playwright_runner.assert_not_called()

    def test_metrics_command_uses_metrics_collector(self):
        result = main.main(
            ["fake", "metrics"],
            adapter_registry=self.registry,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
            deployer_registry=self.deployer_registry,
        )

        self.assertEqual(result["connectors"], ["conn-deployer-a", "conn-deployer-b"])
        self.assertTrue(result["experiment_dir"].startswith("/tmp/cli-test-"))
        self.assertEqual(result["deployer_context"]["dataspace_name"], "fake-ds")
        self.assertEqual(result["deployer_context"]["config"]["KC_PASSWORD"], "***REDACTED***")
        self.assertEqual(result["deployer_context"]["config"]["VT_TOKEN"], "***REDACTED***")

    def test_metrics_command_can_disable_deployer_resolution_explicitly(self):
        with mock.patch.dict(os.environ, {"PIONERA_DISABLE_DEPLOYER_METRICS": "true"}, clear=False):
            result = main.main(
                ["fake", "metrics"],
                adapter_registry=self.registry,
                metrics_collector_cls=FakeMetricsCollector,
                experiment_storage=FakeStorage,
                deployer_registry=self.deployer_registry,
            )

        self.assertEqual(result["connectors"], ["conn-a", "conn-b"])
        self.assertIsNone(result["deployer_context"])

    def test_metrics_command_can_enable_kafka_benchmark(self):
        class FakeKafkaManager:
            def __init__(self, *args, **kwargs):
                self.last_error = None
            def ensure_kafka_running(self):
                return "localhost:9092"
            def stop_kafka(self):
                return None

        result = main.main(
            ["fake", "metrics", "--kafka"],
            adapter_registry=self.registry,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
            kafka_manager_cls=FakeKafkaManager,
            deployer_registry=self.deployer_registry,
        )

        self.assertIn("kafka_metrics", result)
        self.assertEqual(result["kafka_metrics"]["kafka_benchmark"]["status"], "completed")
        self.assertEqual(result["deployer_context"]["dataspace_name"], "fake-ds")

    def test_invalid_adapter_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            main.main(["unknown"], adapter_registry=self.registry)

    def test_invalid_command_raises_system_exit(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
            main.main(["fake", "unknown"], adapter_registry=self.registry)

        self.assertEqual(exc.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue().lower())

    def test_report_command_generates_summary_for_existing_experiment(self):
        result = main.main(
            ["report", "experiment_2026-03-10_12-00-00"],
            adapter_registry=self.registry,
            report_generator_cls=FakeReportGenerator,
        )

        self.assertEqual(result["summary"]["experiment_id"], "experiment_2026-03-10_12-00-00")

    def test_compare_command_dispatches_to_report_generator(self):
        result = main.main(
            ["compare", "experiment_A", "experiment_B"],
            adapter_registry=self.registry,
            report_generator_cls=FakeReportGenerator,
        )

        self.assertEqual(result["experiment_a"]["experiment_id"], "experiment_A")
        self.assertEqual(result["experiment_b"]["experiment_id"], "experiment_B")

    def test_resolve_adapter_class_fails_cleanly_for_missing_module(self):
        with self.assertRaises(ValueError) as exc:
            main.resolve_adapter_class(
                "broken",
                {"broken": "missing.module:MissingAdapter"},
            )

        self.assertIn("Failed to load adapter 'broken'", str(exc.exception))

    def test_resolve_adapter_class_fails_cleanly_for_missing_class(self):
        with self.assertRaises(ValueError) as exc:
            main.resolve_adapter_class(
                "broken",
                {"broken": "fake_adapter_module:MissingAdapter"},
            )

        self.assertIn("Failed to load adapter 'broken'", str(exc.exception))

    def test_main_raises_parser_error_for_broken_adapter_registration(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as exc:
            main.main(["broken"], adapter_registry={"broken": "fake_adapter_module:MissingAdapter"})

        self.assertEqual(exc.exception.code, 2)
        self.assertIn("Failed to load adapter 'broken'", stderr.getvalue())

    def test_resolve_connectors_raises_when_adapter_cannot_provide_any(self):
        with self.assertRaises(RuntimeError):
            main._resolve_connectors(NoConnectorsAdapter())

    def test_real_inesdata_adapter_builds_framework_collaborators(self):
        adapter = InesdataAdapter(
            run=lambda *args, **kwargs: None,
            run_silent=lambda *args, **kwargs: "",
            auto_mode_getter=lambda: True,
        )

        validation_engine = main.build_validation_engine(adapter)
        metrics_collector = main.build_metrics_collector(adapter)

        self.assertIs(validation_engine.load_connector_credentials.__self__, adapter.connectors)
        self.assertIs(validation_engine.load_connector_credentials.__func__, adapter.connectors.load_connector_credentials.__func__)
        self.assertIs(validation_engine.load_deployer_config.__self__, adapter.config_adapter)
        self.assertIs(validation_engine.load_deployer_config.__func__, adapter.config_adapter.load_deployer_config.__func__)
        self.assertIs(validation_engine.cleanup_test_entities.__self__, adapter.connectors)
        self.assertIs(validation_engine.cleanup_test_entities.__func__, adapter.connectors.cleanup_test_entities.__func__)
        self.assertIs(metrics_collector.build_connector_url.__self__, adapter.connectors)
        self.assertIs(metrics_collector.build_connector_url.__func__, adapter.connectors.build_connector_url.__func__)
        self.assertIs(metrics_collector.is_kafka_available.__self__, adapter)
        self.assertIs(metrics_collector.is_kafka_available.__func__, adapter.is_kafka_available.__func__)
        self.assertIs(metrics_collector.ensure_kafka_topic.__self__, adapter)
        self.assertIs(metrics_collector.ensure_kafka_topic.__func__, adapter.ensure_kafka_topic.__func__)
        self.assertTrue(metrics_collector.auto_mode())

    def test_build_adapter_passes_dry_run_when_supported(self):
        registry = {"fake": "fake_adapter_module:DryRunAwareAdapter"}
        adapter = main.build_adapter("fake", adapter_registry=registry, dry_run=True)

        self.assertIsInstance(adapter, DryRunAwareAdapter)
        self.assertTrue(adapter.dry_run)

    def test_run_command_dry_run_returns_preview_without_executing_runner(self):
        result = main.main(
            ["fake", "run", "--dry-run"],
            runner_cls=FakeRunner,
            adapter_registry=self.registry,
            validation_engine_cls=FakeValidationEngine,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(result["command"], "run")
        self.assertIn("deploy_connectors", result["actions"])
        self.assertEqual(result["runner"], "ExperimentRunner")

    def test_run_command_dry_run_includes_iterations(self):
        result = main.main(
            ["fake", "run", "--dry-run", "--iterations", "5"],
            runner_cls=FakeRunner,
            adapter_registry=self.registry,
            validation_engine_cls=FakeValidationEngine,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["iterations"], 5)

    def test_metrics_command_dry_run_reports_kafka_capability(self):
        result = main.main(
            ["fake", "metrics", "--dry-run", "--kafka"],
            adapter_registry=self.registry,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "dry-run")
        self.assertTrue(result["kafka_enabled"])

    def test_deploy_command_dry_run_includes_adapter_preflight_when_available(self):
        result = main.main(
            ["preview", "deploy", "--dry-run", "--topology", "local"],
            adapter_registry={"preview": "fake_adapter_module:PreviewAwareAdapter"},
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "dry-run")
        self.assertIn("preflight", result)
        self.assertEqual(result["preflight"]["status"], "ready")
        self.assertEqual(result["preflight"]["topology"], "local")

    def test_deploy_command_dry_run_can_include_deployer_orchestrator_preview_opt_in(self):
        with mock.patch.dict(os.environ, {"PIONERA_ENABLE_DEPLOYER_DRY_RUN": "true"}, clear=False):
            result = main.main(
                ["fake", "deploy", "--dry-run", "--topology", "local"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                experiment_storage=FakeStorage,
            )

        self.assertEqual(result["status"], "dry-run")
        self.assertIn("deployer_orchestrator", result)
        self.assertEqual(result["deployer_orchestrator"]["status"], "available")
        self.assertEqual(result["deployer_orchestrator"]["deployer"], "fake")
        self.assertEqual(result["deployer_orchestrator"]["context"]["dataspace_name"], "fake-ds")
        self.assertIn("deploy_components", result["deployer_orchestrator"]["actions"])
        self.assertEqual(
            result["deployer_orchestrator"]["context"]["config"]["KC_PASSWORD"],
            "***REDACTED***",
        )
        self.assertEqual(
            result["deployer_orchestrator"]["context"]["config"]["VT_TOKEN"],
            "***REDACTED***",
        )
        self.assertEqual(
            result["deployer_orchestrator"]["context"]["config"]["DS_1_NAME"],
            "fake-ds",
        )

    def test_hosts_command_dry_run_includes_hosts_plan(self):
        result = main.main(
            ["fake", "hosts", "--dry-run", "--topology", "local"],
            adapter_registry=self.registry,
            deployer_registry=self.deployer_registry,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(result["command"], "hosts")
        self.assertIn("plan_hosts_entries", result["actions"])
        self.assertEqual(result["hosts_plan"]["level_3"], ["registration-service-fake-ds.example.local"])

    def test_recreate_dataspace_dry_run_includes_protected_plan(self):
        result = main.main(
            ["fake", "recreate-dataspace", "--dry-run", "--topology", "local"],
            adapter_registry=self.registry,
            deployer_registry=self.deployer_registry,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(result["command"], "recreate-dataspace")
        self.assertIn("require_exact_dataspace_confirmation", result["actions"])
        self.assertIn("skip_level_4_connectors", result["actions"])
        self.assertFalse(result["with_connectors"])
        self.assertEqual(result["recreate_dataspace_plan"]["dataspace"], "fake-ds")
        self.assertTrue(result["recreate_dataspace_plan"]["preserves_shared_services"])

    def test_recreate_dataspace_dry_run_can_include_connectors(self):
        result = main.main(
            ["fake", "recreate-dataspace", "--dry-run", "--topology", "local", "--with-connectors"],
            adapter_registry=self.registry,
            deployer_registry=self.deployer_registry,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "dry-run")
        self.assertTrue(result["with_connectors"])
        self.assertIn("run_level_4_connectors", result["actions"])

    def test_recreate_dataspace_command_requires_exact_confirmation(self):
        with self.assertRaises(RuntimeError) as exc:
            main.main(
                ["fake", "recreate-dataspace", "--topology", "local"],
                adapter_registry=self.registry,
                deployer_registry=self.deployer_registry,
                experiment_storage=FakeStorage,
            )

        self.assertIn("--confirm-dataspace fake-ds", str(exc.exception))

    def test_recreate_dataspace_command_dispatches_to_adapter_when_confirmed(self):
        result = main.main(
            [
                "fake",
                "recreate-dataspace",
                "--topology",
                "local",
                "--confirm-dataspace",
                "fake-ds",
            ],
            adapter_registry=self.registry,
            deployer_registry=self.deployer_registry,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["dataspace"], "fake-ds")
        self.assertEqual(result["result"]["status"], "recreated")
        self.assertFalse(result["with_connectors"])
        self.assertIsNone(result["connectors"])
        self.assertIn("Run Level 4 again", result["next_step"])

    def test_recreate_dataspace_command_can_recreate_connectors_when_requested(self):
        result = main.main(
            [
                "fake",
                "recreate-dataspace",
                "--topology",
                "local",
                "--confirm-dataspace",
                "fake-ds",
                "--with-connectors",
            ],
            adapter_registry=self.registry,
            deployer_registry=self.deployer_registry,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["with_connectors"])
        self.assertEqual(result["connectors"]["level"], 4)
        self.assertEqual(result["connectors"]["name"], "Deploy Connectors")
        self.assertIn("Run Level 6", result["next_step"])

    def test_default_command_passes_iterations_to_runner(self):
        class IterationAwareRunner:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            def run(self):
                return {"iterations": self.kwargs["iterations"]}

        result = main.main(
            ["fake", "--iterations", "3"],
            runner_cls=IterationAwareRunner,
            adapter_registry=self.registry,
            validation_engine_cls=FakeValidationEngine,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["iterations"], 3)

    def test_run_command_passes_baseline_flag_to_runner(self):
        class BaselineAwareRunner:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            def run(self):
                return {"baseline": self.kwargs["baseline"]}

        result = main.main(
            ["fake", "run", "--baseline"],
            runner_cls=BaselineAwareRunner,
            adapter_registry=self.registry,
            validation_engine_cls=FakeValidationEngine,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertTrue(result["baseline"])
