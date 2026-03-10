import json
import os


class GraphBuilder:
    """Builds experiment graphs from aggregated control-plane and optional Kafka metrics."""

    def __init__(self, storage=None):
        self.storage = storage

    @staticmethod
    def _graphs_dir(experiment_dir):
        graphs_dir = os.path.join(experiment_dir, "graphs")
        os.makedirs(graphs_dir, exist_ok=True)
        return graphs_dir

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
    def _output_paths(experiment_dir):
        graphs_dir = GraphBuilder._graphs_dir(experiment_dir)
        return {
            "request_latency_avg": os.path.join(graphs_dir, "request_latency_avg.png"),
            "request_latency_percentiles": os.path.join(graphs_dir, "request_latency_percentiles.png"),
            "request_latency_histogram": os.path.join(graphs_dir, "request_latency_histogram.png"),
            "kafka_latency_percentiles": os.path.join(graphs_dir, "kafka_latency_percentiles.png"),
            "kafka_throughput": os.path.join(graphs_dir, "kafka_throughput.png"),
            "kafka_latency_per_run": os.path.join(graphs_dir, "kafka_latency_per_run.png"),
        }

    @staticmethod
    def _load_json_if_present(path):
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _load_aggregated_metrics(experiment_dir):
        data = GraphBuilder._load_json_if_present(GraphBuilder._aggregated_metrics_path(experiment_dir))
        if not isinstance(data, dict) or not data:
            return None
        return data

    @staticmethod
    def _load_kafka_metrics(experiment_dir):
        data = GraphBuilder._load_json_if_present(GraphBuilder._kafka_metrics_path(experiment_dir))
        if not data:
            return {"broker_source": None, "bootstrap_servers": None, "runs": []}

        broker_source = data.get("broker_source") if isinstance(data, dict) else None
        bootstrap_servers = data.get("bootstrap_servers") if isinstance(data, dict) else None
        runs = []

        if isinstance(data, dict) and "runs" in data and isinstance(data["runs"], list):
            for item in data["runs"]:
                if isinstance(item, dict) and isinstance(item.get("kafka_benchmark"), dict):
                    benchmark = item["kafka_benchmark"]
                    if benchmark.get("status") == "completed":
                        runs.append(benchmark)
            return {
                "broker_source": broker_source,
                "bootstrap_servers": bootstrap_servers,
                "runs": runs,
            }

        if isinstance(data, dict) and isinstance(data.get("kafka_benchmark"), dict):
            benchmark = data["kafka_benchmark"]
            if benchmark.get("status") == "completed":
                runs.append(benchmark)
            return {
                "broker_source": broker_source,
                "bootstrap_servers": bootstrap_servers,
                "runs": runs,
            }

        return {"broker_source": broker_source, "bootstrap_servers": bootstrap_servers, "runs": []}

    @staticmethod
    def _kafka_broker_subtitle(kafka_metadata):
        source = kafka_metadata.get("broker_source")
        if source == "auto-provisioned":
            return "Kafka broker: auto-provisioned"
        if source == "external":
            return "Kafka broker: external"
        return None

    @staticmethod
    def _average(values):
        numeric = [float(value) for value in values if value is not None]
        if not numeric:
            return 0.0
        return sum(numeric) / len(numeric)

    @staticmethod
    def _load_request_latencies(experiment_dir, aggregated_metrics):
        raw_path = GraphBuilder._raw_requests_path(experiment_dir)
        latencies = []

        if os.path.exists(raw_path):
            with open(raw_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    latency = item.get("latency_ms")
                    if latency is None:
                        latency = item.get("response_time_ms")
                    try:
                        if latency is not None:
                            latencies.append(float(latency))
                    except (TypeError, ValueError):
                        continue

        if latencies:
            return latencies

        return [
            float(metrics.get("average_latency_ms", 0))
            for metrics in aggregated_metrics.values()
            if metrics.get("average_latency_ms") is not None
        ]

    @staticmethod
    def _load_plot_backend():
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            return plt
        except Exception as exc:
            print(f"[WARNING] GraphBuilder could not import matplotlib: {exc}")
            return None

    @staticmethod
    def _truncate_labels(labels, limit=24):
        truncated = []
        for label in labels:
            text = str(label)
            truncated.append(text if len(text) <= limit else f"{text[:limit - 3]}...")
        return truncated

    def build(self, experiment_dir):
        """Generate all supported experiment graphs inside <experiment_dir>/graphs/."""
        aggregated_metrics = self._load_aggregated_metrics(experiment_dir)
        kafka_metadata = self._load_kafka_metrics(experiment_dir)
        kafka_runs = kafka_metadata["runs"]

        if not aggregated_metrics and not kafka_runs:
            print("[INFO] No aggregated_metrics.json or kafka_metrics.json found - skipping graph generation")
            return {}

        plt = self._load_plot_backend()
        if plt is None:
            return {}

        output_paths = self._output_paths(experiment_dir)
        generated_paths = {}

        if aggregated_metrics:
            requests = list(aggregated_metrics.keys())
            labels = self._truncate_labels(requests)
            averages = [aggregated_metrics[name].get("average_latency_ms", 0) for name in requests]
            p50_values = [aggregated_metrics[name].get("p50_latency_ms", 0) for name in requests]
            p95_values = [aggregated_metrics[name].get("p95_latency_ms", 0) for name in requests]
            p99_values = [aggregated_metrics[name].get("p99_latency_ms", 0) for name in requests]
            histogram_values = self._load_request_latencies(experiment_dir, aggregated_metrics)

            self._build_average_latency_chart(plt, labels, averages, output_paths["request_latency_avg"])
            self._build_percentiles_chart(
                plt,
                labels,
                p50_values,
                p95_values,
                p99_values,
                output_paths["request_latency_percentiles"],
                title="Latency percentiles per request",
            )
            self._build_histogram(
                plt,
                histogram_values,
                output_paths["request_latency_histogram"],
                title="Latency histogram",
                x_label="Latency (ms)",
            )

            generated_paths.update({
                "request_latency_avg": output_paths["request_latency_avg"],
                "request_latency_percentiles": output_paths["request_latency_percentiles"],
                "request_latency_histogram": output_paths["request_latency_histogram"],
            })

        if kafka_runs:
            labels = self._truncate_labels([str(item.get("run_index", index + 1)) for index, item in enumerate(kafka_runs)])
            p50_values = [item.get("p50_latency_ms") for item in kafka_runs]
            p95_values = [item.get("p95_latency_ms") for item in kafka_runs]
            p99_values = [item.get("p99_latency_ms") for item in kafka_runs]
            throughput_values = [item.get("throughput_messages_per_second", 0) for item in kafka_runs]
            avg_latency_values = [item.get("average_latency_ms", 0) for item in kafka_runs]
            subtitle = self._kafka_broker_subtitle(kafka_metadata)

            self._build_percentile_category_chart(
                plt,
                ["p50", "p95", "p99"],
                [
                    self._average(p50_values),
                    self._average(p95_values),
                    self._average(p99_values),
                ],
                output_paths["kafka_latency_percentiles"],
                title="Kafka latency percentiles",
                subtitle=subtitle,
            )
            self._build_single_series_bar_chart(
                plt,
                labels,
                throughput_values,
                output_paths["kafka_throughput"],
                title="Kafka throughput per run",
                y_label="Throughput (messages/s)",
                x_label="Run index",
                subtitle=subtitle,
            )

            generated_paths.update({
                "kafka_latency_percentiles": output_paths["kafka_latency_percentiles"],
                "kafka_throughput": output_paths["kafka_throughput"],
            })

            if len(kafka_runs) > 1:
                self._build_single_series_bar_chart(
                    plt,
                    labels,
                    avg_latency_values,
                    output_paths["kafka_latency_per_run"],
                    title="Kafka average latency per run",
                    y_label="Average latency (ms)",
                    x_label="Run index",
                    subtitle=subtitle,
                )
                generated_paths["kafka_latency_per_run"] = output_paths["kafka_latency_per_run"]

        print("Graph generation completed")
        return generated_paths

    def _build_average_latency_chart(self, plt, labels, averages, output_path):
        figure, axis = plt.subplots(figsize=(10, 6))
        axis.bar(labels, averages, color="#4C78A8")
        axis.set_title("Average latency per request")
        axis.set_ylabel("Average latency (ms)")
        axis.set_xlabel("Request")
        axis.tick_params(axis="x", rotation=35)
        figure.tight_layout()
        figure.savefig(output_path, dpi=150)
        plt.close(figure)

    def _build_percentiles_chart(self, plt, labels, p50_values, p95_values, p99_values, output_path, title):
        positions = list(range(len(labels)))
        width = 0.25

        figure, axis = plt.subplots(figsize=(11, 6))
        axis.bar([p - width for p in positions], p50_values, width=width, label="p50", color="#59A14F")
        axis.bar(positions, p95_values, width=width, label="p95", color="#F28E2B")
        axis.bar([p + width for p in positions], p99_values, width=width, label="p99", color="#E15759")
        axis.set_title(title)
        axis.set_ylabel("Latency (ms)")
        axis.set_xlabel("Request")
        axis.set_xticks(positions)
        axis.set_xticklabels(labels, rotation=35, ha="right")
        axis.legend()
        figure.tight_layout()
        figure.savefig(output_path, dpi=150)
        plt.close(figure)

    def _build_percentile_category_chart(self, plt, labels, values, output_path, title, subtitle=None):
        figure, axis = plt.subplots(figsize=(8, 6))
        chart_title = title if not subtitle else f"{title}\n{subtitle}"
        axis.bar(labels, values, color=["#59A14F", "#F28E2B", "#E15759"])
        axis.set_title(chart_title)
        axis.set_ylabel("Latency (ms)")
        axis.set_xlabel("Percentile")
        figure.tight_layout()
        figure.savefig(output_path, dpi=150)
        plt.close(figure)

    def _build_single_series_bar_chart(self, plt, labels, values, output_path, title, y_label, x_label="Run", subtitle=None):
        figure, axis = plt.subplots(figsize=(10, 6))
        chart_title = title if not subtitle else f"{title}\n{subtitle}"
        axis.bar(labels, values, color="#76B7B2")
        axis.set_title(chart_title)
        axis.set_ylabel(y_label)
        axis.set_xlabel(x_label)
        axis.tick_params(axis="x", rotation=20)
        figure.tight_layout()
        figure.savefig(output_path, dpi=150)
        plt.close(figure)

    def _build_histogram(self, plt, values, output_path, title, x_label):
        figure, axis = plt.subplots(figsize=(10, 6))
        bins = min(max(len(values), 1), 20)
        axis.hist(values, bins=bins, color="#F28E2B", edgecolor="black")
        axis.set_title(title)
        axis.set_xlabel(x_label)
        axis.set_ylabel("Frequency")
        figure.tight_layout()
        figure.savefig(output_path, dpi=150)
        plt.close(figure)

    def describe(self) -> str:
        return "GraphBuilder generates experiment graphs from aggregated metrics."

