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
        return {"KC_URL": "http://keycloak.local"}


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

    def deploy_connectors(self):
        self.calls.append("deploy_connectors")
        return ["conn-a", "conn-b"]

    def get_cluster_connectors(self):
        self.calls.append("get_cluster_connectors")
        return ["conn-a", "conn-b"]


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


class MainCliTests(unittest.TestCase):
    def setUp(self):
        self.fake_module = types.ModuleType("fake_adapter_module")
        self.fake_module.FakeAdapter = FakeAdapter
        self.fake_module.DryRunAwareAdapter = DryRunAwareAdapter
        self.registry = {"fake": "fake_adapter_module:FakeAdapter"}
        self.module_patcher = mock.patch.dict(
            sys.modules,
            {"fake_adapter_module": self.fake_module},
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

    def test_deploy_command_dispatches_to_adapter(self):
        adapter = FakeAdapter()
        result = main.run_deploy(adapter)

        self.assertEqual(result, ["conn-a", "conn-b"])
        self.assertEqual(
            adapter.calls,
            ["deploy_infrastructure", "deploy_dataspace", "deploy_connectors"],
        )

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

    def test_metrics_command_uses_metrics_collector(self):
        result = main.main(
            ["fake", "metrics"],
            adapter_registry=self.registry,
            metrics_collector_cls=FakeMetricsCollector,
            experiment_storage=FakeStorage,
        )

        self.assertEqual(result["connectors"], ["conn-a", "conn-b"])
        self.assertTrue(result["experiment_dir"].startswith("/tmp/cli-test-"))

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
        )

        self.assertIn("kafka_metrics", result)
        self.assertEqual(result["kafka_metrics"]["kafka_benchmark"]["status"], "completed")

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
