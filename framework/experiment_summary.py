import json
import os
from datetime import datetime


class ExperimentSummaryBuilder:
    """Builds human-readable experiment summaries from stored artifacts."""

    def __init__(self, storage=None):
        self.storage = storage

    @staticmethod
    def _read_json_if_present(path):
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _read_jsonl_if_present(path):
        if not os.path.exists(path):
            return []

        items = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items

    @staticmethod
    def _metadata_path(experiment_dir):
        return os.path.join(experiment_dir, "metadata.json")

    @staticmethod
    def _aggregated_metrics_path(experiment_dir):
        return os.path.join(experiment_dir, "aggregated_metrics.json")

    @staticmethod
    def _kafka_metrics_path(experiment_dir):
        return os.path.join(experiment_dir, "kafka_metrics.json")

    @staticmethod
    def _raw_requests_path(experiment_dir):
        return os.path.join(experiment_dir, "raw_requests.jsonl")

    @staticmethod
    def _graph_files(experiment_dir):
        graphs_dir = os.path.join(experiment_dir, "graphs")
        if not os.path.isdir(graphs_dir):
            return []
        return sorted(
            file_name for file_name in os.listdir(graphs_dir)
            if file_name.lower().endswith(".png")
        )

    @staticmethod
    def _experiment_id(experiment_dir):
        return os.path.basename(os.path.normpath(experiment_dir))

    @staticmethod
    def _percentile(values, percentile):
        ordered = sorted(float(value) for value in values)
        if not ordered:
            return None
        if len(ordered) == 1:
            return round(float(ordered[0]), 2)

        rank = (len(ordered) - 1) * percentile
        lower_index = int(rank)
        upper_index = min(lower_index + 1, len(ordered) - 1)
        weight = rank - lower_index
        lower = float(ordered[lower_index])
        upper = float(ordered[upper_index])
        return round(lower + (upper - lower) * weight, 2)

    @staticmethod
    def _normalize_control_plane_metrics(aggregated_metrics):
        normalized = {}
        for request_name, metrics in sorted((aggregated_metrics or {}).items()):
            normalized[request_name] = {
                "average_latency_ms": metrics.get("average_latency_ms"),
                "p50_latency_ms": metrics.get("p50_latency_ms"),
                "p95_latency_ms": metrics.get("p95_latency_ms"),
                "p99_latency_ms": metrics.get("p99_latency_ms"),
            }
        return normalized

    def _control_plane_performance_from_raw(self, raw_requests):
        grouped = {}

        for item in raw_requests or []:
            collection = item.get("collection") or "(unknown)"
            request_name = item.get("request_name") or item.get("request") or "(unknown)"
            latency = item.get("latency_ms")
            if latency is None:
                latency = item.get("response_time_ms")
            try:
                latency_value = float(latency)
            except (TypeError, ValueError):
                continue

            grouped.setdefault((str(collection), str(request_name)), []).append(latency_value)

        performance = []
        for (collection, request_name), values in sorted(grouped.items()):
            performance.append({
                "collection": collection,
                "request_name": request_name,
                "average_latency_ms": round(sum(values) / len(values), 2),
                "p50_latency_ms": self._percentile(values, 0.50),
                "p95_latency_ms": self._percentile(values, 0.95),
                "p99_latency_ms": self._percentile(values, 0.99),
            })

        return performance

    def _control_plane_performance_fallback(self, aggregated_metrics):
        performance = []
        for request_name, metrics in sorted((aggregated_metrics or {}).items()):
            performance.append({
                "collection": "(aggregated)",
                "request_name": request_name,
                "average_latency_ms": metrics.get("average_latency_ms"),
                "p50_latency_ms": metrics.get("p50_latency_ms"),
                "p95_latency_ms": metrics.get("p95_latency_ms"),
                "p99_latency_ms": metrics.get("p99_latency_ms"),
            })
        return performance

    def _build_control_plane_performance(self, experiment_dir, aggregated_metrics):
        raw_requests = self._read_jsonl_if_present(self._raw_requests_path(experiment_dir))
        performance = self._control_plane_performance_from_raw(raw_requests)
        if performance:
            return performance
        return self._control_plane_performance_fallback(aggregated_metrics)

    @staticmethod
    def _slowest_operations(control_plane_performance):
        return sorted(
            control_plane_performance or [],
            key=lambda item: (item.get("average_latency_ms") is None, -(item.get("average_latency_ms") or 0)),
        )

    @staticmethod
    def _completed_kafka_runs(kafka_payload):
        if not isinstance(kafka_payload, dict):
            return []

        runs = []
        if isinstance(kafka_payload.get("kafka_benchmark"), dict):
            benchmark = kafka_payload["kafka_benchmark"]
            if benchmark.get("status") == "completed":
                runs.append(benchmark)
            return runs

        for item in kafka_payload.get("runs", []) or []:
            if not isinstance(item, dict):
                continue
            benchmark = item.get("kafka_benchmark")
            if isinstance(benchmark, dict) and benchmark.get("status") == "completed":
                runs.append(benchmark)
        return runs

    @staticmethod
    def _average_numeric(values):
        numeric = [float(value) for value in values if value is not None]
        if not numeric:
            return None
        return round(sum(numeric) / len(numeric), 2)

    def _normalize_kafka_metrics(self, kafka_payload):
        if not isinstance(kafka_payload, dict):
            return None

        completed_runs = self._completed_kafka_runs(kafka_payload)
        if not completed_runs:
            return None

        normalized = {
            "average_latency_ms": self._average_numeric([run.get("average_latency_ms") for run in completed_runs]),
            "p50_latency_ms": self._average_numeric([run.get("p50_latency_ms") for run in completed_runs]),
            "p95_latency_ms": self._average_numeric([run.get("p95_latency_ms") for run in completed_runs]),
            "p99_latency_ms": self._average_numeric([run.get("p99_latency_ms") for run in completed_runs]),
            "throughput_messages_per_second": self._average_numeric([
                run.get("throughput_messages_per_second") for run in completed_runs
            ]),
        }

        if len(completed_runs) > 1:
            normalized["runs"] = [
                {
                    "run_index": run.get("run_index"),
                    "average_latency_ms": run.get("average_latency_ms"),
                    "p50_latency_ms": run.get("p50_latency_ms"),
                    "p95_latency_ms": run.get("p95_latency_ms"),
                    "p99_latency_ms": run.get("p99_latency_ms"),
                    "throughput_messages_per_second": run.get("throughput_messages_per_second"),
                }
                for run in completed_runs
            ]

        return normalized

    def build_summary(self, experiment_dir, adapter=None, iterations=1, kafka_enabled=False, timestamp=None):
        metadata = self._read_json_if_present(self._metadata_path(experiment_dir)) or {}
        aggregated_metrics = self._read_json_if_present(self._aggregated_metrics_path(experiment_dir)) or {}
        kafka_payload = self._read_json_if_present(self._kafka_metrics_path(experiment_dir)) or {}

        broker_source = None
        if isinstance(kafka_payload, dict):
            broker_source = kafka_payload.get("broker_source")

        control_plane_metrics = self._normalize_control_plane_metrics(aggregated_metrics)
        control_plane_performance = self._build_control_plane_performance(experiment_dir, aggregated_metrics)
        slowest_operations = self._slowest_operations(control_plane_performance)

        summary = {
            "experiment_id": self._experiment_id(experiment_dir),
            "timestamp": timestamp or metadata.get("timestamp") or datetime.now().isoformat(),
            "adapter": adapter,
            "iterations": iterations,
            "kafka_enabled": bool(kafka_enabled),
            "broker_source": broker_source,
            "control_plane_metrics": control_plane_metrics,
            "control_plane_performance": control_plane_performance,
            "slowest_operations": slowest_operations,
            "kafka_metrics": self._normalize_kafka_metrics(kafka_payload),
            "generated_graphs": self._graph_files(experiment_dir),
        }
        return summary

    @staticmethod
    def _markdown_metadata_lines(summary):
        lines = [
            f"- **experiment_id**: `{summary.get('experiment_id')}`",
            f"- **timestamp**: `{summary.get('timestamp')}`",
            f"- **adapter**: `{summary.get('adapter')}`",
            f"- **iterations**: `{summary.get('iterations')}`",
            f"- **kafka_enabled**: `{summary.get('kafka_enabled')}`",
        ]
        if summary.get("broker_source"):
            lines.append(f"- **broker_source**: `{summary.get('broker_source')}`")
        return lines

    @staticmethod
    def _markdown_control_plane_table(control_plane_metrics):
        if not control_plane_metrics:
            return ["No control plane metrics available."]

        lines = [
            "| Collection | Request | Average latency (ms) | p50 | p95 | p99 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for item in control_plane_metrics:
            lines.append(
                f"| {item.get('collection')} | {item.get('request_name')} | {item.get('average_latency_ms')} | {item.get('p50_latency_ms')} | {item.get('p95_latency_ms')} | {item.get('p99_latency_ms')} |"
            )
        return lines

    @staticmethod
    def _markdown_slowest_operations(slowest_operations):
        if not slowest_operations:
            return ["No slow operations available."]

        lines = [
            "| Rank | Collection | Request | Average latency (ms) |",
            "| ---: | --- | --- | ---: |",
        ]
        for index, item in enumerate(slowest_operations, start=1):
            lines.append(
                f"| {index} | {item.get('collection')} | {item.get('request_name')} | {item.get('average_latency_ms')} |"
            )
        return lines

    @staticmethod
    def _markdown_kafka_section(kafka_metrics):
        if not kafka_metrics:
            return ["Kafka benchmark not available."]

        lines = [
            f"- **Average latency (ms)**: `{kafka_metrics.get('average_latency_ms')}`",
            f"- **p50 latency (ms)**: `{kafka_metrics.get('p50_latency_ms')}`",
            f"- **p95 latency (ms)**: `{kafka_metrics.get('p95_latency_ms')}`",
            f"- **p99 latency (ms)**: `{kafka_metrics.get('p99_latency_ms')}`",
            f"- **Throughput (messages/s)**: `{kafka_metrics.get('throughput_messages_per_second')}`",
        ]

        runs = kafka_metrics.get("runs") or []
        if runs:
            lines.extend([
                "",
                "| Run | Avg latency (ms) | p50 | p95 | p99 | Throughput (msg/s) |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ])
            for run in runs:
                lines.append(
                    f"| {run.get('run_index')} | {run.get('average_latency_ms')} | {run.get('p50_latency_ms')} | {run.get('p95_latency_ms')} | {run.get('p99_latency_ms')} | {run.get('throughput_messages_per_second')} |"
                )
        return lines

    @staticmethod
    def build_markdown(summary):
        lines = [
            "# Experiment Summary",
            "",
            "## Metadata",
            *ExperimentSummaryBuilder._markdown_metadata_lines(summary),
            "",
            "## Control Plane Performance",
            *ExperimentSummaryBuilder._markdown_control_plane_table(summary.get("control_plane_performance") or []),
            "",
            "## Slowest Operations",
            *ExperimentSummaryBuilder._markdown_slowest_operations(summary.get("slowest_operations") or []),
            "",
            "## Kafka Results",
            *ExperimentSummaryBuilder._markdown_kafka_section(summary.get("kafka_metrics")),
            "",
            "## Generated Graphs",
        ]

        graph_files = summary.get("generated_graphs") or []
        if graph_files:
            lines.extend(f"- `{file_name}`" for file_name in graph_files)
        else:
            lines.append("No graphs generated.")

        return "\n".join(lines) + "\n"

    def describe(self) -> str:
        return "ExperimentSummaryBuilder creates JSON and Markdown experiment summaries."

