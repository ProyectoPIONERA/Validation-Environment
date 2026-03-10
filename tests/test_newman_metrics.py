import json
import os
import tempfile
import unittest
from unittest import mock

from framework.experiment_runner import ExperimentRunner
from framework.experiment_storage import ExperimentStorage
from framework.graph_builder import GraphBuilder
from framework.metrics_collector import MetricsCollector
from framework.newman_executor import NewmanExecutor
from framework.validation_engine import ValidationEngine


class _FakeAxis:
    def bar(self, *args, **kwargs):
        return None

    def hist(self, *args, **kwargs):
        return None

    def set_title(self, *args, **kwargs):
        return None

    def set_ylabel(self, *args, **kwargs):
        return None

    def set_xlabel(self, *args, **kwargs):
        return None

    def tick_params(self, *args, **kwargs):
        return None

    def set_xticks(self, *args, **kwargs):
        return None

    def set_xticklabels(self, *args, **kwargs):
        return None

    def legend(self, *args, **kwargs):
        return None


class _FakeFigure:
    def tight_layout(self):
        return None

    def savefig(self, path, dpi=None):
        with open(path, "wb") as f:
            f.write(b"fake-png")


class _FakePlotBackend:
    @staticmethod
    def subplots(figsize=None):
        return _FakeFigure(), _FakeAxis()

    @staticmethod
    def close(figure):
        return None


class NewmanMetricsTests(unittest.TestCase):
    @mock.patch("framework.newman_executor.subprocess.run")
    def test_run_newman_enables_json_reporter_and_export(self, mock_run):
        mock_run.return_value.returncode = 0
        executor = NewmanExecutor()

        with mock.patch.object(executor, "load_test_scripts", return_value="pm.test('ok')"):
            report_path = executor.run_newman(
                "validation/collections/01_environment_health.json",
                {"provider": "conn-a"},
                report_path="experiments/exp-1/newman_reports/report.json",
            )

        self.assertEqual(report_path, "experiments/exp-1/newman_reports/report.json")
        command = mock_run.call_args.args[0]
        self.assertIn("--reporters", command)
        self.assertIn("cli,json", command)
        self.assertIn("--reporter-json-export", command)
        self.assertIn("experiments/exp-1/newman_reports/report.json", command)

    def test_run_validation_collections_returns_report_paths(self):
        executor = NewmanExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(executor, "run_newman", side_effect=lambda path, env, report_path=None: report_path):
                reports = executor.run_validation_collections({"provider": "conn-a"}, report_dir=tmpdir)

        self.assertEqual(len(reports), 6)
        self.assertTrue(reports[0].endswith("01_environment_health.json"))
        self.assertTrue(reports[-1].endswith("06_consumer_transfer.json"))

    def test_parse_newman_report_extracts_request_metrics(self):
        collector = MetricsCollector()
        report = {
            "collection": {"info": {"name": "03_provider_setup"}},
            "run": {
                "executions": [
                    {
                        "item": {"name": "Create Asset"},
                        "request": {"url": {"raw": "http://example.test/management/v3/assets"}},
                        "response": {"code": 200, "responseTime": 42},
                        "cursor": {"started": "2026-03-07T10:00:00.000Z"}
                    },
                    {
                        "item": {"name": "List Assets"},
                        "request": {"url": {"path": ["management", "v3", "assets", "request"]}},
                        "response": {"code": 400, "responseTime": 17},
                        "cursor": {"started": "2026-03-07T10:00:01.000Z"}
                    }
                ]
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = os.path.join(tmpdir, "run_003")
            os.makedirs(run_dir, exist_ok=True)
            report_path = os.path.join(run_dir, "03_provider_setup.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f)

            metrics = collector.parse_newman_report(report_path)

        self.assertEqual(metrics, [
            {
                "run_index": 3,
                "run": 3,
                "request_name": "Create Asset",
                "request": "Create Asset",
                "collection": "03_provider_setup",
                "status_code": 200,
                "response_time_ms": 42,
                "latency_ms": 42,
                "timestamp": "2026-03-07T10:00:00.000Z",
                "endpoint": "http://example.test/management/v3/assets",
            },
            {
                "run_index": 3,
                "run": 3,
                "request_name": "List Assets",
                "request": "List Assets",
                "collection": "03_provider_setup",
                "status_code": 400,
                "response_time_ms": 17,
                "latency_ms": 17,
                "timestamp": "2026-03-07T10:00:01.000Z",
                "endpoint": "/management/v3/assets/request",
            }
        ])

    def test_collect_newman_request_metrics_aggregates_directory_and_saves(self):
        collector = MetricsCollector(experiment_storage=ExperimentStorage)
        sample_report = {
            "collection": {"info": {"name": "01_environment_health"}},
            "run": {
                "executions": [
                    {
                        "item": {"name": "Health"},
                        "request": {"url": {"raw": "http://example.test/health"}},
                        "response": {"code": 200, "responseTime": 11},
                        "cursor": {"started": "2026-03-07T10:00:00.000Z"}
                    }
                ]
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = ExperimentStorage.newman_reports_dir(tmpdir)
            run_dir = os.path.join(report_dir, "run_001")
            pair_dir = os.path.join(run_dir, "conn-a__conn-b")
            os.makedirs(pair_dir, exist_ok=True)
            report_path = os.path.join(pair_dir, "01_environment_health.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(sample_report, f)

            metrics = collector.collect_newman_request_metrics(report_dir, experiment_dir=tmpdir)
            raw_path = os.path.join(tmpdir, "raw_requests.jsonl")
            aggregated_path = os.path.join(tmpdir, "aggregated_metrics.json")

            self.assertTrue(os.path.exists(raw_path))
            self.assertTrue(os.path.exists(aggregated_path))

            with open(raw_path, "r", encoding="utf-8") as f:
                raw_lines = [line.rstrip("\n") for line in f]
            with open(aggregated_path, "r", encoding="utf-8") as f:
                aggregated = json.load(f)

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["request_name"], "Health")
        self.assertEqual(metrics[0]["run_index"], 1)
        self.assertEqual(len(raw_lines), 1)
        self.assertEqual(json.loads(raw_lines[0])["request_name"], "Health")
        self.assertIn("Health", aggregated)
        self.assertEqual(aggregated["Health"]["count"], 1)

    def test_graph_builder_generates_expected_graph_files(self):
        builder = GraphBuilder()
        aggregated_metrics = {
            "Create Asset": {
                "count": 3,
                "average_latency_ms": 45.0,
                "min_latency_ms": 38.0,
                "max_latency_ms": 55.0,
                "p50_latency_ms": 42.0,
                "p95_latency_ms": 53.7,
                "p99_latency_ms": 54.74,
            },
            "List Assets": {
                "count": 2,
                "average_latency_ms": 11.0,
                "min_latency_ms": 10.0,
                "max_latency_ms": 12.0,
                "p50_latency_ms": 11.0,
                "p95_latency_ms": 11.9,
                "p99_latency_ms": 11.98,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            ExperimentStorage.save_aggregated_metrics(aggregated_metrics, tmpdir)
            ExperimentStorage.save_raw_request_metrics_jsonl([
                {"request_name": "Create Asset", "latency_ms": 42},
                {"request_name": "Create Asset", "latency_ms": 38},
                {"request_name": "List Assets", "latency_ms": 12},
            ], tmpdir)
            with mock.patch.object(GraphBuilder, "_load_plot_backend", return_value=_FakePlotBackend):
                graph_paths = builder.build(tmpdir)

            self.assertEqual(set(graph_paths.keys()), {
                "request_latency_avg",
                "request_latency_percentiles",
                "request_latency_histogram",
            })
            for path in graph_paths.values():
                self.assertTrue(os.path.exists(path))
                self.assertIn(f"{os.sep}graphs{os.sep}", path)
                self.assertGreater(os.path.getsize(path), 0)

    def test_graph_builder_generates_optional_kafka_graphs(self):
        builder = GraphBuilder()

        with tempfile.TemporaryDirectory() as tmpdir:
            ExperimentStorage.save_aggregated_metrics({
                "Create Asset": {
                    "count": 1,
                    "average_latency_ms": 10.0,
                    "min_latency_ms": 10.0,
                    "max_latency_ms": 10.0,
                    "p50_latency_ms": 10.0,
                    "p95_latency_ms": 10.0,
                    "p99_latency_ms": 10.0,
                }
            }, tmpdir)
            ExperimentStorage.save_kafka_metrics_json({
                "broker_source": "auto-provisioned",
                "runs": [
                    {"kafka_benchmark": {"status": "completed", "run_index": 1, "average_latency_ms": 6.5, "p50_latency_ms": 5.0, "p95_latency_ms": 7.0, "p99_latency_ms": 9.0, "throughput_messages_per_second": 100.0}},
                    {"kafka_benchmark": {"status": "skipped", "run_index": 99, "reason": "ignored"}},
                    {"kafka_benchmark": {"status": "completed", "run_index": 2, "average_latency_ms": 7.5, "p50_latency_ms": 6.0, "p95_latency_ms": 8.0, "p99_latency_ms": 10.0, "throughput_messages_per_second": 120.0}},
                ]
            }, tmpdir)

            with mock.patch.object(GraphBuilder, "_load_plot_backend", return_value=_FakePlotBackend):
                graph_paths = builder.build(tmpdir)

            self.assertIn("kafka_latency_percentiles", graph_paths)
            self.assertIn("kafka_throughput", graph_paths)
            self.assertIn("kafka_latency_per_run", graph_paths)
            self.assertTrue(os.path.exists(graph_paths["kafka_latency_percentiles"]))
            self.assertTrue(os.path.exists(graph_paths["kafka_throughput"]))
            self.assertTrue(os.path.exists(graph_paths["kafka_latency_per_run"]))

    def test_graph_builder_skips_when_aggregated_metrics_missing(self):
        builder = GraphBuilder()

        with tempfile.TemporaryDirectory() as tmpdir:
            graph_paths = builder.build(tmpdir)

        self.assertEqual(graph_paths, {})

    def test_experiment_runner_invokes_graph_builder_after_completion(self):
        class FakeAdapter:
            def deploy_infrastructure(self):
                return None
            def deploy_dataspace(self):
                return None
            def deploy_connectors(self):
                return ["conn-a", "conn-b"]

        class FakeValidationEngine:
            def run(self, connectors, experiment_dir=None, run_index=None):
                return [{"report": "ok", "run_index": run_index}]

        class FakeMetricsCollector:
            def collect(self, connectors, experiment_dir=None, run_index=None):
                return [{"source": connectors[0], "target": connectors[1], "run_index": run_index}]
            def collect_newman_request_metrics(self, report_dir, experiment_dir=None):
                ExperimentStorage.save_aggregated_metrics({
                    "Health": {
                        "count": 1,
                        "average_latency_ms": 11.0,
                        "min_latency_ms": 11.0,
                        "max_latency_ms": 11.0,
                        "p50_latency_ms": 11.0,
                        "p95_latency_ms": 11.0,
                        "p99_latency_ms": 11.0,
                    }
                }, experiment_dir)
                return [{"request_name": "Health", "run_index": 1, "latency_ms": 11}]

        class FakeGraphBuilder:
            def __init__(self):
                self.called_with = None
            def build(self, experiment_dir):
                self.called_with = experiment_dir
                graphs_dir = os.path.join(experiment_dir, "graphs")
                os.makedirs(graphs_dir, exist_ok=True)
                output = os.path.join(graphs_dir, "request_latency_avg.png")
                with open(output, "wb") as f:
                    f.write(b"fake-png")
                return {"request_latency_avg": output}

        graph_builder = FakeGraphBuilder()
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(ExperimentStorage, "create_experiment_directory", return_value=tmpdir):
                runner = ExperimentRunner(
                    adapter=FakeAdapter(),
                    validation_engine=FakeValidationEngine(),
                    metrics_collector=FakeMetricsCollector(),
                    experiment_storage=ExperimentStorage,
                    graph_builder=graph_builder,
                )
                result = runner.run()

        self.assertEqual(graph_builder.called_with, result["experiment_dir"])
        self.assertIn("graphs", result)
        self.assertIn("request_latency_avg", result["graphs"])
        self.assertTrue(result["graphs"]["request_latency_avg"].endswith("request_latency_avg.png"))

    def test_experiment_runner_continues_when_graph_generation_fails(self):
        class FakeAdapter:
            def deploy_infrastructure(self):
                return None
            def deploy_dataspace(self):
                return None
            def deploy_connectors(self):
                return ["conn-a", "conn-b"]

        class FakeValidationEngine:
            def run(self, connectors, experiment_dir=None, run_index=None):
                return []

        class FakeMetricsCollector:
            def collect(self, connectors, experiment_dir=None, run_index=None):
                return []
            def collect_newman_request_metrics(self, report_dir, experiment_dir=None):
                ExperimentStorage.save_aggregated_metrics({
                    "Health": {
                        "count": 1,
                        "average_latency_ms": 11.0,
                        "min_latency_ms": 11.0,
                        "max_latency_ms": 11.0,
                        "p50_latency_ms": 11.0,
                        "p95_latency_ms": 11.0,
                        "p99_latency_ms": 11.0,
                    }
                }, experiment_dir)
                return []

        class FailingGraphBuilder:
            def build(self, experiment_dir):
                raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(ExperimentStorage, "create_experiment_directory", return_value=tmpdir):
                runner = ExperimentRunner(
                    adapter=FakeAdapter(),
                    validation_engine=FakeValidationEngine(),
                    metrics_collector=FakeMetricsCollector(),
                    experiment_storage=ExperimentStorage,
                    graph_builder=FailingGraphBuilder(),
                )
                result = runner.run()

        self.assertEqual(result["graphs"], {})

    def test_aggregate_newman_request_metrics_groups_and_computes_percentiles(self):
        collector = MetricsCollector()
        metrics = [
            {"request": "Create Asset", "latency_ms": 42},
            {"request": "Create Asset", "latency_ms": 38},
            {"request": "Create Asset", "latency_ms": 55},
            {"request": "List Assets", "latency_ms": 10},
            {"request": "List Assets", "latency_ms": 12},
        ]

        aggregated = collector.aggregate_newman_request_metrics(metrics)

        self.assertEqual(aggregated["Create Asset"]["count"], 3)
        self.assertEqual(aggregated["Create Asset"]["average_latency_ms"], 45.0)
        self.assertEqual(aggregated["Create Asset"]["min_latency_ms"], 38.0)
        self.assertEqual(aggregated["Create Asset"]["max_latency_ms"], 55.0)
        self.assertEqual(aggregated["Create Asset"]["p50_latency_ms"], 42.0)
        self.assertEqual(aggregated["List Assets"]["count"], 2)
        self.assertEqual(aggregated["List Assets"]["p50_latency_ms"], 11.0)
        self.assertGreaterEqual(
            aggregated["Create Asset"]["p99_latency_ms"],
            aggregated["Create Asset"]["p95_latency_ms"],
        )

    def test_aggregate_newman_request_metrics_handles_single_sample(self):
        collector = MetricsCollector()
        aggregated = collector.aggregate_newman_request_metrics([
            {"request_name": "Create Asset", "latency_ms": 42}
        ])

        self.assertEqual(aggregated, {
            "Create Asset": {
                "count": 1,
                "average_latency_ms": 42.0,
                "min_latency_ms": 42.0,
                "max_latency_ms": 42.0,
                "p50_latency_ms": 42.0,
                "p95_latency_ms": 42.0,
                "p99_latency_ms": 42.0,
            }
        })

    def test_aggregate_newman_request_metrics_ignores_invalid_entries(self):
        collector = MetricsCollector()
        aggregated = collector.aggregate_newman_request_metrics([
            {"request_name": "Create Asset", "latency_ms": 42},
            {"request_name": "Create Asset", "latency_ms": None},
            {"request_name": "Create Asset", "latency_ms": "bad"},
            {"latency_ms": 10},
        ])

        self.assertEqual(aggregated["Create Asset"]["count"], 1)
        self.assertEqual(len(aggregated), 1)

    def test_validation_engine_passes_experiment_dir_to_executor(self):
        fake_executor = mock.Mock()
        fake_executor.run_validation_collections.return_value = ["report.json"]
        engine = ValidationEngine(
            newman_executor=fake_executor,
            load_connector_credentials=lambda name: {"connector_user": {"user": name, "passwd": "secret"}},
            load_deployer_config=lambda: {"KC_URL": "http://keycloak.local"},
            cleanup_test_entities=lambda connector: None,
            ds_domain_resolver=lambda: "example.local",
            ds_name="demo",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            reports = engine.run(["conn-a", "conn-b"], experiment_dir=tmpdir)

        self.assertEqual(reports, ["report.json", "report.json"])
        self.assertEqual(fake_executor.run_validation_collections.call_count, 2)
        report_dir = fake_executor.run_validation_collections.call_args.kwargs["report_dir"]
        self.assertIn("newman_reports", report_dir)

    def test_experiment_runner_bundles_newman_request_metrics(self):
        class FakeAdapter:
            def deploy_infrastructure(self):
                return None
            def deploy_dataspace(self):
                return None
            def deploy_connectors(self):
                return ["conn-a", "conn-b"]

        class FakeValidationEngine:
            def run(self, connectors, experiment_dir=None, run_index=None):
                report_dir = os.path.join(
                    ExperimentStorage.newman_reports_dir(experiment_dir),
                    f"run_{run_index:03d}",
                )
                sample_report = {
                    "collection": {"info": {"name": "01_environment_health"}},
                    "run": {"executions": []}
                }
                os.makedirs(report_dir, exist_ok=True)
                report_path = os.path.join(report_dir, "01_environment_health.json")
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(sample_report, f)
                return [report_path]

        class FakeMetricsCollector:
            def __init__(self):
                self.collect_calls = []
            def collect(self, connectors, experiment_dir=None, run_index=None):
                self.collect_calls.append(run_index)
                return [{"source": connectors[0], "target": connectors[1], "run_index": run_index}]
            def collect_newman_request_metrics(self, report_dir, experiment_dir=None):
                return [
                    {"run_index": 1, "request_name": "Health", "collection": "01_environment_health", "status_code": 200, "response_time_ms": 11, "timestamp": None, "endpoint": "/health"},
                    {"run_index": 2, "request_name": "Health", "collection": "01_environment_health", "status_code": 200, "response_time_ms": 12, "timestamp": None, "endpoint": "/health"},
                ]

        metrics_collector = FakeMetricsCollector()
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(ExperimentStorage, "create_experiment_directory", return_value=tmpdir):
                runner = ExperimentRunner(
                    adapter=FakeAdapter(),
                    validation_engine=FakeValidationEngine(),
                    metrics_collector=metrics_collector,
                    experiment_storage=ExperimentStorage,
                    iterations=2,
                )
                result = runner.run()

        self.assertEqual(result["iterations"], 2)
        self.assertEqual(metrics_collector.collect_calls, [1, 2])
        self.assertEqual(result["newman_request_metrics"][0]["run_index"], 1)
        self.assertEqual(result["newman_request_metrics"][1]["run_index"], 2)
        self.assertEqual(len(result["validation"]), 2)


if __name__ == "__main__":
    unittest.main()

