from datetime import datetime
import inspect

from .experiment_storage import ExperimentStorage
from .experiment_summary import ExperimentSummaryBuilder
from .graph_builder import GraphBuilder


class ExperimentRunner:
    """Orchestrates dataspace experiments end-to-end.

    Coordinates adapter-driven deployment, validation execution,
    metrics collection, and experiment result persistence.
    """

    def __init__(
        self,
        adapter,
        validation_engine=None,
        metrics_collector=None,
        experiment_storage=None,
        deploy_dataspace=True,
        iterations=1,
        graph_builder=None,
        kafka_manager=None,
        summary_builder=None,
    ):
        self.adapter = adapter
        self.validation_engine = validation_engine
        self.metrics_collector = metrics_collector
        self.experiment_storage = experiment_storage or ExperimentStorage
        self.deploy_dataspace = deploy_dataspace
        self.iterations = iterations
        self.graph_builder = graph_builder or GraphBuilder(storage=self.experiment_storage)
        self.kafka_manager = kafka_manager
        self.summary_builder = summary_builder or ExperimentSummaryBuilder(storage=self.experiment_storage)

    def _call_if_available(self, obj, method_name, *args, **kwargs):
        method = getattr(obj, method_name, None)
        if callable(method):
            return method(*args, **kwargs)
        return None

    def _require_connectors(self, connectors):
        if not connectors:
            raise RuntimeError("ExperimentRunner could not resolve connectors from the adapter")
        return list(connectors)

    def _run_validation(self, connectors, experiment_dir=None, run_index=None):
        if self.validation_engine is None:
            return None

        run_method = getattr(self.validation_engine, "run", None)
        if callable(run_method):
            try:
                parameters = inspect.signature(run_method).parameters
            except (TypeError, ValueError):
                parameters = {}

            kwargs = {}
            if "experiment_dir" in parameters:
                kwargs["experiment_dir"] = experiment_dir
            if "run_index" in parameters:
                kwargs["run_index"] = run_index
            return run_method(connectors, **kwargs)

        fallback = getattr(self.validation_engine, "run_all_dataspace_tests", None)
        if callable(fallback):
            try:
                parameters = inspect.signature(fallback).parameters
            except (TypeError, ValueError):
                parameters = {}

            kwargs = {}
            if "experiment_dir" in parameters:
                kwargs["experiment_dir"] = experiment_dir
            if "run_index" in parameters:
                kwargs["run_index"] = run_index
            return fallback(connectors, **kwargs)

        raise RuntimeError("Validation engine does not expose a supported run method")

    def _collect_metrics(self, connectors, experiment_dir, run_index=None):
        if self.metrics_collector is None:
            return None

        collect_method = getattr(self.metrics_collector, "collect", None)
        if callable(collect_method):
            try:
                parameters = inspect.signature(collect_method).parameters
            except (TypeError, ValueError):
                parameters = {}

            kwargs = {"experiment_dir": experiment_dir}
            if "run_index" in parameters:
                kwargs["run_index"] = run_index
            return collect_method(connectors, **kwargs)

        fallback = getattr(self.metrics_collector, "measure_all_connectors", None)
        if callable(fallback):
            try:
                parameters = inspect.signature(fallback).parameters
            except (TypeError, ValueError):
                parameters = {}

            kwargs = {"experiment_dir": experiment_dir}
            if "run_index" in parameters:
                kwargs["run_index"] = run_index
            return fallback(connectors, **kwargs)

        raise RuntimeError("Metrics collector does not expose a supported collect method")

    def _build_graphs(self, experiment_dir):
        if self.graph_builder is None:
            return {}

        build_method = getattr(self.graph_builder, "build", None)
        if not callable(build_method):
            raise RuntimeError("Graph builder does not expose a supported build method")

        try:
            return build_method(experiment_dir)
        except Exception as exc:
            print(f"[WARNING] Graph generation failed: {exc}")
            return {}

    def _build_summary(self, experiment_dir, timestamp, kafka_enabled):
        if self.summary_builder is None:
            return {}

        build_method = getattr(self.summary_builder, "build_summary", None)
        if not callable(build_method):
            raise RuntimeError("Summary builder does not expose a supported build_summary method")

        try:
            summary = build_method(
                experiment_dir,
                adapter=type(self.adapter).__name__ if self.adapter is not None else None,
                iterations=self.iterations,
                kafka_enabled=kafka_enabled,
                timestamp=timestamp,
            )
            markdown_builder = getattr(self.summary_builder, "build_markdown", None)
            markdown = markdown_builder(summary) if callable(markdown_builder) else None

            self.experiment_storage.save_summary_json(summary, experiment_dir)
            if markdown is not None:
                self.experiment_storage.save_summary_markdown(markdown, experiment_dir)

            return {
                "summary_json": "summary.json",
                "summary_markdown": "summary.md" if markdown is not None else None,
            }
        except Exception as exc:
            print(f"[WARNING] Summary generation failed: {exc}")
            return {}

    @staticmethod
    def _build_kafka_skip_payload(reason, broker_source=None, bootstrap_servers=None):
        payload = {
            "kafka_benchmark": {
                "status": "skipped",
                "reason": reason,
            }
        }
        if broker_source is not None:
            payload["broker_source"] = broker_source
        if bootstrap_servers is not None:
            payload["bootstrap_servers"] = bootstrap_servers
        return payload

    @staticmethod
    def _broker_source_from_manager(kafka_manager):
        if kafka_manager is None:
            return None
        return "auto-provisioned" if getattr(kafka_manager, "started_by_framework", False) else "external"

    def _collect_kafka_metrics(self, experiment_dir, iterations):
        if self.metrics_collector is None:
            return None

        collect_kafka = getattr(self.metrics_collector, "collect_kafka_benchmark", None)
        if not callable(collect_kafka):
            return None

        kafka_enabled = bool(getattr(self.metrics_collector, "kafka_enabled", False))
        if not kafka_enabled:
            return None

        kafka_runtime_overrides = None
        bootstrap_servers = None
        broker_source = None
        if self.kafka_manager is not None:
            bootstrap_servers = self.kafka_manager.ensure_kafka_running()
            broker_source = self._broker_source_from_manager(self.kafka_manager)
            if not bootstrap_servers:
                reason = self.kafka_manager.last_error or "Kafka broker unavailable and auto-provisioning failed"
                skipped = self._build_kafka_skip_payload(
                    reason,
                    broker_source=broker_source,
                    bootstrap_servers=bootstrap_servers,
                )
                self.experiment_storage.save_kafka_metrics_json(skipped, experiment_dir)
                return skipped
            kafka_runtime_overrides = {"bootstrap_servers": bootstrap_servers}

        kafka_results = []
        try:
            parameters = inspect.signature(collect_kafka).parameters
        except (TypeError, ValueError):
            parameters = {}

        for run_index in range(1, iterations + 1):
            kwargs = {"run_index": run_index}
            if "kafka_runtime_overrides" in parameters:
                kwargs["kafka_runtime_overrides"] = kafka_runtime_overrides
            result = collect_kafka(experiment_dir, **kwargs)
            if result is not None:
                kafka_results.append(result)

        if not kafka_results:
            return None

        if len(kafka_results) == 1:
            persisted_payload = dict(kafka_results[0])
        else:
            persisted_payload = {"runs": kafka_results}

        if broker_source is not None:
            persisted_payload["broker_source"] = broker_source
        if bootstrap_servers is not None:
            persisted_payload["bootstrap_servers"] = bootstrap_servers

        self.experiment_storage.save_kafka_metrics_json(persisted_payload, experiment_dir)
        return persisted_payload

    def run(self):
        """Run the complete experiment lifecycle."""
        experiment_dir = None
        try:
            self._call_if_available(self.adapter, "deploy_infrastructure")

            if self.deploy_dataspace:
                self._call_if_available(self.adapter, "deploy_dataspace")

            connectors = self._call_if_available(self.adapter, "deploy_connectors")
            if not connectors:
                connectors = self._call_if_available(self.adapter, "get_cluster_connectors")
            connectors = self._require_connectors(connectors)

            experiment_dir = self.experiment_storage.create_experiment_directory()
            self.experiment_storage.save_experiment_metadata(experiment_dir, connectors)

            iteration_results = []

            for run_index in range(1, self.iterations + 1):
                validation_result = self._run_validation(
                    connectors,
                    experiment_dir=experiment_dir,
                    run_index=run_index,
                )
                metrics = self._collect_metrics(
                    connectors,
                    experiment_dir,
                    run_index=run_index,
                )
                iteration_results.append({
                    "run_index": run_index,
                    "validation": validation_result,
                    "metrics": metrics,
                })

            validation_result = iteration_results[0]["validation"] if self.iterations == 1 else iteration_results
            metrics = iteration_results[0]["metrics"] if self.iterations == 1 else iteration_results

            newman_request_metrics = None
            if self.metrics_collector is not None:
                collect_newman_metrics = getattr(self.metrics_collector, "collect_newman_request_metrics", None)
                if callable(collect_newman_metrics):
                    newman_request_metrics = collect_newman_metrics(
                        self.experiment_storage.newman_reports_dir(experiment_dir),
                        experiment_dir=experiment_dir,
                    )

            kafka_metrics = self._collect_kafka_metrics(experiment_dir, self.iterations)

            timestamp = datetime.now().isoformat()
            bundle = {
                "timestamp": timestamp,
                "iterations": self.iterations,
                "connectors": connectors,
                "validation": validation_result,
                "metrics": metrics,
                "newman_request_metrics": newman_request_metrics,
                "kafka_metrics": kafka_metrics,
            }

            self.experiment_storage.save(bundle, experiment_dir=experiment_dir)
            graph_paths = self._build_graphs(experiment_dir)
            summary_files = self._build_summary(
                experiment_dir,
                timestamp=timestamp,
                kafka_enabled=bool(getattr(self.metrics_collector, "kafka_enabled", False)),
            )

            return {
                "experiment_dir": experiment_dir,
                "iterations": self.iterations,
                "connectors": connectors,
                "validation": validation_result,
                "metrics": metrics,
                "newman_request_metrics": newman_request_metrics,
                "kafka_metrics": kafka_metrics,
                "graphs": graph_paths,
                "summary_files": summary_files,
            }
        finally:
            if self.kafka_manager is not None:
                self.kafka_manager.stop_kafka()

    def describe(self) -> str:
        return "ExperimentRunner orchestrates dataspace experiments."

