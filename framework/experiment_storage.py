import json
import os
from datetime import datetime


class ExperimentStorage:
    """Saves experiment metadata and results.

    This class centralizes filesystem persistence for experiment artifacts
    without changing the legacy storage formats or file names.
    """

    @staticmethod
    def create_experiment_directory():
        """Create timestamped directory for storing experiment results."""
        base_dir = "experiments"
        os.makedirs(base_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        experiment_dir = os.path.join(base_dir, f"experiment_{timestamp}")
        os.makedirs(experiment_dir, exist_ok=True)

        return experiment_dir

    @staticmethod
    def save_experiment_metadata(experiment_dir, connectors):
        """Save experiment metadata to JSON file."""
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "connectors": connectors,
            "num_connectors": len(connectors),
            "environment": "minikube",
            "measurement_type": "connector_latency"
        }

        metadata_file = os.path.join(experiment_dir, "metadata.json")

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=4)

        print(f"Experiment metadata saved: {metadata_file}")

    @staticmethod
    def save_latency_results_json(results, experiment_dir):
        """Save connector latency measurement results to JSON file."""
        file_name = os.path.join(experiment_dir, "latency_results.json")

        formatted_results = []
        for r in results:
            formatted_results.append({
                "source": r["source"],
                "target": r["target"],
                "url": r["url"],
                "status": r["status"],
                "avg_latency_sec": r["avg_latency_sec"],
                "min_latency_sec": r["min_latency_sec"],
                "max_latency_sec": r["max_latency_sec"],
                "std_latency_sec": r["std_latency_sec"]
            })

        with open(file_name, "w") as f:
            json.dump(formatted_results, f, indent=2)

        print(f"Latency results saved to {file_name}")

    @staticmethod
    def save_kafka_latency_results(results, experiment_dir):
        """Save Kafka latency measurement results to JSON file."""
        if not results:
            return

        file_name = os.path.join(experiment_dir, "kafka_latency_results.json")

        with open(file_name, "w") as f:
            json.dump(results, f, indent=2)

        print(f"Kafka latency results saved to {file_name}")

    @staticmethod
    def newman_reports_dir(experiment_dir):
        """Return the directory used for Newman JSON reports."""
        report_dir = os.path.join(experiment_dir, "newman_reports")
        os.makedirs(report_dir, exist_ok=True)
        return report_dir

    @staticmethod
    def save_raw_request_metrics_jsonl(results, experiment_dir):
        """Persist raw request metrics as JSON Lines for pandas-friendly loading."""
        file_name = os.path.join(experiment_dir, "raw_requests.jsonl")

        with open(file_name, "w", encoding="utf-8") as f:
            for result in results:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

        print(f"Raw request metrics saved to {file_name}")
        return file_name

    @staticmethod
    def save_aggregated_metrics(results, experiment_dir):
        """Persist aggregated request latency statistics as human-readable JSON."""
        file_name = os.path.join(experiment_dir, "aggregated_metrics.json")

        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"Aggregated metrics saved to {file_name}")
        return file_name

    @staticmethod
    def save_newman_request_metrics(results, experiment_dir):
        """Backward-compatible wrapper for raw Newman request metrics storage."""
        return ExperimentStorage.save_raw_request_metrics_jsonl(results, experiment_dir)

    @staticmethod
    def save_kafka_metrics_json(results, experiment_dir):
        """Persist Kafka benchmark results to JSON."""
        file_name = os.path.join(experiment_dir, "kafka_metrics.json")

        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"Kafka benchmark metrics saved to {file_name}")
        return file_name

    @staticmethod
    def save_summary_json(results, experiment_dir):
        """Persist normalized experiment summary to summary.json."""
        file_name = os.path.join(experiment_dir, "summary.json")

        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"Experiment summary saved to {file_name}")
        return file_name

    @staticmethod
    def save_summary_markdown(content, experiment_dir):
        """Persist human-readable experiment summary to summary.md."""
        file_name = os.path.join(experiment_dir, "summary.md")

        with open(file_name, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Experiment markdown summary saved to {file_name}")
        return file_name

    @staticmethod
    def save(results, experiment_dir=None, file_name="experiment_results.json"):
        """Save a generic experiment result bundle to JSON."""
        experiment_dir = experiment_dir or ExperimentStorage.create_experiment_directory()
        file_path = os.path.join(experiment_dir, file_name)

        with open(file_path, "w") as f:
            json.dump(results, f, indent=2)

        print(f"Experiment results saved to {file_path}")
        return file_path

    def describe(self) -> str:
        return "ExperimentStorage saves experiment results."

