import json
import os
import tempfile
import unittest
from unittest import mock

import inesdata
from framework.experiment_storage import ExperimentStorage
from framework.metrics_collector import MetricsCollector


class KafkaBenchmarkSmokeTests(unittest.TestCase):
    def test_run_kafka_benchmark_experiment_persists_completed_payload(self):
        class FakeKafkaBenchmark:
            def run(self, experiment_id=None, run_index=1, runtime_overrides=None):
                return {
                    "kafka_benchmark": {
                        "status": "completed",
                        "experiment_id": experiment_id,
                        "run_index": run_index,
                        "average_latency_ms": 8.5,
                        "p50_latency_ms": 8.0,
                        "p95_latency_ms": 10.0,
                        "p99_latency_ms": 11.0,
                        "throughput_messages_per_second": 120.0,
                    }
                }

        class FakeKafkaManager:
            started_by_framework = False
            last_error = None

            def ensure_kafka_running(self):
                return "localhost:19092"

        collector = MetricsCollector(
            experiment_storage=ExperimentStorage,
            kafka_enabled=True,
            kafka_metrics_collector=FakeKafkaBenchmark(),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            payload = collector.run_kafka_benchmark_experiment(
                tmpdir,
                iterations=2,
                kafka_manager=FakeKafkaManager(),
            )

            kafka_metrics_path = os.path.join(tmpdir, "kafka_metrics.json")
            self.assertTrue(os.path.exists(kafka_metrics_path))
            with open(kafka_metrics_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)

        self.assertEqual(payload["broker_source"], "external")
        self.assertEqual(payload["bootstrap_servers"], "localhost:19092")
        self.assertEqual(len(payload["runs"]), 2)
        self.assertEqual(stored["runs"][0]["kafka_benchmark"]["status"], "completed")

    def test_run_kafka_benchmark_experiment_persists_skipped_payload(self):
        class FakeKafkaManager:
            started_by_framework = True
            last_error = "docker unavailable"

            def ensure_kafka_running(self):
                return None

        collector = MetricsCollector(
            experiment_storage=ExperimentStorage,
            kafka_enabled=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            payload = collector.run_kafka_benchmark_experiment(
                tmpdir,
                iterations=1,
                kafka_manager=FakeKafkaManager(),
            )

            with open(os.path.join(tmpdir, "kafka_metrics.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

        self.assertEqual(payload["kafka_benchmark"]["status"], "skipped")
        self.assertEqual(payload["broker_source"], "auto-provisioned")
        self.assertIn("docker unavailable", stored["kafka_benchmark"]["reason"])

    def test_level6_persists_kafka_metrics_into_experiment_state(self):
        original_isdir = os.path.isdir
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                mock.patch.object(inesdata.NEWMAN_EXECUTOR, "is_available", return_value=True),
                mock.patch.object(inesdata, "get_connectors_from_cluster", return_value=["conn-a", "conn-b"]),
                mock.patch.object(inesdata, "validate_connectors_deployment", return_value=True),
                mock.patch.object(inesdata, "ensure_all_minio_policies", return_value=None),
                mock.patch.object(inesdata.VALIDATION_ENGINE, "run_all_dataspace_tests", return_value=[]),
                mock.patch.object(
                    inesdata.LEVEL6_KAFKA_METRICS_COLLECTOR,
                    "run_kafka_benchmark_experiment",
                    return_value={
                        "kafka_benchmark": {
                            "status": "completed",
                            "run_index": 1,
                            "average_latency_ms": 8.5,
                        },
                        "broker_source": "external",
                        "bootstrap_servers": "localhost:19092",
                    },
                ) as mock_kafka,
                mock.patch.object(inesdata.ExperimentStorage, "create_experiment_directory", return_value=tmpdir),
                mock.patch.object(
                    inesdata.os.path,
                    "isdir",
                    side_effect=lambda path: False if path == os.path.join(inesdata.Config.script_dir(), "validation", "ui") else original_isdir(path),
                ),
            ):
                inesdata.lvl_6()

            with open(os.path.join(tmpdir, "experiment_results.json"), "r", encoding="utf-8") as handle:
                stored = json.load(handle)

        mock_kafka.assert_called_once()
        self.assertEqual(stored["kafka_metrics"]["kafka_benchmark"]["status"], "completed")
        self.assertEqual(stored["kafka_metrics"]["bootstrap_servers"], "localhost:19092")


if __name__ == "__main__":
    unittest.main()
