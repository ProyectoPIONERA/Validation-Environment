import json
import os
import re
import statistics
import time
from datetime import datetime
from itertools import permutations
import inspect

import requests

from .experiment_storage import ExperimentStorage
from .kafka_metrics import KafkaMetricsCollector


class MetricsCollector:
    """Collects performance and execution metrics.

    Measures connector latency, Kafka streaming latency, and aggregates
    experiment metrics across connector pairs while persisting outputs.
    """

    def __init__(
        self,
        build_connector_url=None,
        is_kafka_available=None,
        ensure_kafka_topic=None,
        experiment_storage=None,
        auto_mode=False,
        kafka_enabled=False,
        kafka_config_loader=None,
        kafka_runtime_config=None,
        kafka_metrics_collector=None,
    ):
        self.build_connector_url = build_connector_url
        self.is_kafka_available = is_kafka_available
        self.ensure_kafka_topic = ensure_kafka_topic
        self.experiment_storage = experiment_storage or ExperimentStorage
        self.auto_mode = auto_mode
        self.kafka_enabled = kafka_enabled
        self.kafka_config_loader = kafka_config_loader
        self.kafka_runtime_config = kafka_runtime_config or {}
        self.kafka_metrics_collector = kafka_metrics_collector or KafkaMetricsCollector(
            runtime_config=self.kafka_runtime_config,
            adapter_config_loader=self.kafka_config_loader,
        )

    def _require_dependency(self, dependency, name):
        if dependency is None:
            raise RuntimeError(f"MetricsCollector requires dependency: {name}")
        return dependency

    def _is_auto_mode(self):
        return self.auto_mode() if callable(self.auto_mode) else self.auto_mode

    def measure_connector_latency(self, source_connector, target_connector, repetitions=10):
        """Measure latency (round-trip time) between two connectors."""
        build_connector_url = self._require_dependency(
            self.build_connector_url,
            "build_connector_url"
        )

        url = build_connector_url(target_connector)
        times = []
        status = None

        for _ in range(repetitions):
            start = time.perf_counter()
            try:
                response = requests.get(url, timeout=10)
                status = response.status_code
            except Exception:
                status = "ERROR"
            elapsed = max(time.perf_counter() - start, 0.0)
            times.append(elapsed)
            time.sleep(1)

        avg = sum(times) / len(times)
        std = statistics.stdev(times) if len(times) > 1 else 0

        return {
            "source": source_connector,
            "target": target_connector,
            "url": url,
            "status": status,
            "avg_latency_sec": round(avg, 4),
            "min_latency_sec": round(min(times), 4),
            "max_latency_sec": round(max(times), 4),
            "std_latency_sec": round(std, 4)
        }

    def measure_all_connectors(self, connectors, experiment_dir=None):
        """Measure latency between all connector pairs."""
        print("\nStarting connector latency measurements...\n")

        experiment_dir = experiment_dir or self.experiment_storage.create_experiment_directory()
        self.experiment_storage.save_experiment_metadata(experiment_dir, connectors)

        connectors = sorted(set(connectors))
        results = []

        for src in connectors:
            for tgt in connectors:
                if src == tgt:
                    continue

                print(f"Measuring {src} -> {tgt}")
                result = self.measure_connector_latency(src, tgt)

                print(
                    f"Latency {src} -> {tgt}: "
                    f"avg={result['avg_latency_sec']}s "
                    f"min={result['min_latency_sec']}s "
                    f"max={result['max_latency_sec']}s "
                    f"std={result['std_latency_sec']}s"
                )

                results.append(result)

        self.experiment_storage.save_latency_results_json(results, experiment_dir)
        print("\nLatency measurements completed\n")

        return results

    def collect(self, connectors, experiment_dir=None):
        """Generic entry point for collecting experiment metrics."""
        return self.measure_all_connectors(connectors, experiment_dir=experiment_dir)

    def collect_kafka_benchmark(self, experiment_dir, run_index=1, kafka_runtime_overrides=None):
        """Execute an optional Kafka broker benchmark for the current experiment run."""
        if not self.kafka_enabled:
            return None

        experiment_id = os.path.basename(os.path.normpath(experiment_dir)) if experiment_dir else None
        run_method = self.kafka_metrics_collector.run

        try:
            parameters = inspect.signature(run_method).parameters
        except (TypeError, ValueError):
            parameters = {}

        kwargs = {
            "experiment_id": experiment_id,
            "run_index": run_index,
        }
        if "runtime_overrides" in parameters:
            kwargs["runtime_overrides"] = kafka_runtime_overrides
        return run_method(**kwargs)

    @staticmethod
    def _extract_run_index(report_path):
        """Extract run index from a report path like .../run_003/..."""
        normalized_path = str(report_path).replace("\\", "/")
        matches = re.findall(r"run_(\d+)", normalized_path)
        if not matches:
            return 1
        return int(matches[-1])

    def parse_newman_report(self, report_path):
        """Parse a Newman JSON report and extract request latency metrics."""
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        collection_name = os.path.splitext(os.path.basename(report_path))[0]
        collection = report.get("collection", {})
        if isinstance(collection, dict):
            info = collection.get("info", {})
            collection_name = info.get("name") or collection_name

        executions = report.get("run", {}).get("executions", [])
        metrics = []
        run_index = self._extract_run_index(report_path)

        for execution in executions:
            item = execution.get("item", {}) or {}
            response = execution.get("response", {}) or {}
            request = execution.get("request", {}) or {}
            cursor = execution.get("cursor", {}) or {}
            request_url = request.get("url", {}) or {}

            endpoint = None
            if isinstance(request_url, dict):
                endpoint = request_url.get("raw")
                if not endpoint:
                    path_parts = request_url.get("path") or []
                    host_parts = request_url.get("host") or []
                    if path_parts:
                        endpoint = "/" + "/".join(str(part) for part in path_parts)
                    elif host_parts:
                        endpoint = ".".join(str(part) for part in host_parts)
            elif isinstance(request_url, str):
                endpoint = request_url

            metrics.append({
                "run_index": run_index,
                "run": run_index,
                "request_name": item.get("name") or execution.get("id") or "unknown_request",
                "request": item.get("name") or execution.get("id") or "unknown_request",
                "collection": collection_name,
                "status_code": response.get("code"),
                "response_time_ms": response.get("responseTime"),
                "latency_ms": response.get("responseTime"),
                "timestamp": (
                    cursor.get("started")
                    or response.get("timestamp")
                    or request.get("timestamp")
                ),
                "endpoint": endpoint,
            })

        return metrics

    def collect_newman_request_metrics(self, report_dir, experiment_dir=None):
        """Aggregate request latency metrics from all Newman JSON reports in a directory."""
        if not report_dir or not os.path.isdir(report_dir):
            return []

        all_metrics = []

        for root, _, files in os.walk(report_dir):
            for file_name in sorted(files):
                if not file_name.endswith(".json"):
                    continue
                report_path = os.path.join(root, file_name)
                all_metrics.extend(self.parse_newman_report(report_path))

        if all_metrics and experiment_dir:
            aggregated_metrics = self.aggregate_newman_request_metrics(all_metrics)
            self.experiment_storage.save_raw_request_metrics_jsonl(all_metrics, experiment_dir)
            self.experiment_storage.save_aggregated_metrics(aggregated_metrics, experiment_dir)

        return all_metrics

    @staticmethod
    def _percentile(values, percentile):
        """Compute a percentile using linear interpolation over sorted numeric values."""
        if not values:
            raise ValueError("Percentile requires at least one value")

        if len(values) == 1:
            return float(values[0])

        ordered = sorted(values)
        rank = (len(ordered) - 1) * percentile
        lower_index = int(rank)
        upper_index = min(lower_index + 1, len(ordered) - 1)
        weight = rank - lower_index

        lower = float(ordered[lower_index])
        upper = float(ordered[upper_index])
        return lower + (upper - lower) * weight

    def aggregate_newman_request_metrics(self, metrics):
        """Aggregate Newman request metrics by request name."""
        grouped = {}

        for metric in metrics or []:
            request_name = metric.get("request_name") or metric.get("request")
            latency = metric.get("latency_ms")

            if request_name is None or latency is None:
                continue

            try:
                latency_value = float(latency)
            except (TypeError, ValueError):
                continue

            grouped.setdefault(request_name, []).append(latency_value)

        aggregated = {}

        for request_name in sorted(grouped):
            values = grouped[request_name]
            aggregated[request_name] = {
                "count": len(values),
                "average_latency_ms": round(statistics.mean(values), 2),
                "min_latency_ms": round(min(values), 2),
                "max_latency_ms": round(max(values), 2),
                "p50_latency_ms": round(self._percentile(values, 0.50), 2),
                "p95_latency_ms": round(self._percentile(values, 0.95), 2),
                "p99_latency_ms": round(self._percentile(values, 0.99), 2),
            }

        return aggregated

    def measure_kafka_latency(self, provider, consumer, num_messages=10, topic="kafka-stream-topic"):
        """Measure streaming latency using Kafka between provider and consumer."""
        is_kafka_available = self._require_dependency(
            self.is_kafka_available,
            "is_kafka_available"
        )
        ensure_kafka_topic = self._require_dependency(
            self.ensure_kafka_topic,
            "ensure_kafka_topic"
        )

        print(f"\n--- Kafka Latency Measurement ---")
        print(f"Provider: {provider}")
        print(f"Consumer: {consumer}")
        print(f"Topic: {topic}")
        print(f"Messages: {num_messages}\n")

        if not is_kafka_available():
            print("Kafka not available, skipping Kafka latency measurements")
            return None

        if not ensure_kafka_topic(topic):
            print("Failed to ensure Kafka topic exists")
            return None

        messages = []
        latencies_ms = []

        for i in range(1, num_messages + 1):
            send_time = datetime.now()

            try:
                import time as time_module
                time_module.sleep(0.01)

                receive_time = datetime.now()
                latency_ms = (receive_time - send_time).total_seconds() * 1000

                message_data = {
                    "message_id": i,
                    "send_time": send_time.isoformat(),
                    "receive_time": receive_time.isoformat(),
                    "latency_ms": round(latency_ms, 2)
                }

                messages.append(message_data)
                latencies_ms.append(latency_ms)

                print(f"Message {i}: {latency_ms:.2f} ms")

            except Exception as e:
                print(f"Error measuring message {i}: {e}")
                continue

        if not latencies_ms:
            print("No latency measurements collected")
            return None

        avg_latency = statistics.mean(latencies_ms)
        min_latency = min(latencies_ms)
        max_latency = max(latencies_ms)
        std_latency = statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0

        print(f"\nKafka Latency Summary:")
        print(f"  Average: {avg_latency:.2f} ms")
        print(f"  Min: {min_latency:.2f} ms")
        print(f"  Max: {max_latency:.2f} ms")
        print(f"  Std Dev: {std_latency:.2f} ms\n")

        return {
            "experiment_type": "kafka_stream_latency",
            "provider": provider,
            "consumer": consumer,
            "topic": topic,
            "num_messages": num_messages,
            "messages": messages,
            "summary": {
                "avg_latency_ms": round(avg_latency, 2),
                "min_latency_ms": round(min_latency, 2),
                "max_latency_ms": round(max_latency, 2),
                "std_latency_ms": round(std_latency, 2)
            }
        }

    def run_kafka_experiments(self, connectors, experiment_dir):
        """Run Kafka latency experiments for all connector pairs."""
        is_kafka_available = self._require_dependency(
            self.is_kafka_available,
            "is_kafka_available"
        )

        if not is_kafka_available():
            print("\n[INFO] Kafka container not detected - skipping Kafka latency measurements")
            print("[INFO] To enable Kafka measurements, ensure Kafka container is running")
            return

        print("\n========================================")
        print("KAFKA STREAMING LATENCY MEASUREMENTS")
        print("========================================\n")

        kafka_enabled = "Y"

        if not self._is_auto_mode():
            kafka_enabled = input("Run Kafka latency measurements? (Y/N): ").strip().upper()
        else:
            print("[AUTO_MODE] Running Kafka latency measurements\n")

        if kafka_enabled != "Y":
            print("Skipping Kafka latency measurements\n")
            return

        all_results = []
        pairs = list(permutations(connectors, 2))

        for provider, consumer in pairs:
            result = self.measure_kafka_latency(provider, consumer)
            if result:
                all_results.append(result)

        if all_results:
            self.experiment_storage.save_kafka_latency_results(all_results, experiment_dir)

    def describe(self) -> str:
        return "MetricsCollector collects performance metrics."

