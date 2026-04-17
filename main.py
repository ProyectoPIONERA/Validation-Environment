import argparse
import importlib
import inspect
import os

from runtime_dependencies import ensure_runtime_dependencies


ensure_runtime_dependencies(
    requirements_path=os.path.join(os.path.dirname(__file__), "requirements.txt"),
    module_names=("requests", "matplotlib", "kafka", "docker", "testcontainers", "yaml", "minio"),
    label="framework root",
)

from framework.experiment_runner import ExperimentRunner
from framework.experiment_storage import ExperimentStorage
from framework.kafka_manager import KafkaManager
from framework.metrics_collector import MetricsCollector
from framework.reporting.experiment_loader import ExperimentLoader
from framework.reporting.report_generator import ExperimentReportGenerator
from framework.transfer_storage_verifier import TransferStorageVerifier
from framework.validation_engine import ValidationEngine


ADAPTER_REGISTRY = {
    "inesdata": "adapters.inesdata.adapter:InesdataAdapter",
    "edc": "adapters.edc.adapter:EdcAdapter",
}

SUPPORTED_COMMANDS = ("deploy", "validate", "metrics", "run")
SUPPORTED_TOPOLOGIES = ("local",)


def resolve_adapter_class(adapter_name, adapter_registry=None):
    """Resolve an adapter class from the configured registry."""
    registry = adapter_registry or ADAPTER_REGISTRY

    if adapter_name not in registry:
        supported = ", ".join(sorted(registry))
        raise ValueError(f"Unsupported adapter '{adapter_name}'. Supported adapters: {supported}")

    try:
        module_path, class_name = registry[adapter_name].split(":", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as exc:
        raise ValueError(
            f"Failed to load adapter '{adapter_name}' from '{registry[adapter_name]}': {exc}"
        ) from exc


def build_adapter(adapter_name="inesdata", adapter_registry=None, dry_run=False, topology="local"):
    """Instantiate the selected dataspace adapter."""
    adapter_class = resolve_adapter_class(adapter_name, adapter_registry=adapter_registry)

    try:
        parameters = inspect.signature(adapter_class).parameters
    except (TypeError, ValueError):
        parameters = {}

    kwargs = {}
    if "dry_run" in parameters:
        kwargs["dry_run"] = dry_run

    if "topology" in parameters:
        kwargs["topology"] = topology

    if kwargs:
        return adapter_class(**kwargs)

    return adapter_class()


def _resolve_adapter_callable(adapter, *paths: str, default=None):
    for path in paths:
        current = adapter
        try:
            for attribute in path.split("."):
                current = getattr(current, attribute)
        except AttributeError:
            continue

        if callable(current) or current is not None:
            return current

    return default


def build_validation_engine(adapter, engine_cls=ValidationEngine):
    """Build a generic validation engine from adapter-provided dependencies."""
    cleanup_test_entities = _resolve_adapter_callable(
        adapter,
        "connectors.cleanup_test_entities",
        "cleanup_test_entities",
        default=lambda connector: None,
    )
    load_connector_credentials = _resolve_adapter_callable(
        adapter,
        "connectors.load_connector_credentials",
        "load_connector_credentials",
    )
    load_deployer_config = _resolve_adapter_callable(
        adapter,
        "config_adapter.load_deployer_config",
        "load_deployer_config",
    )
    validation_test_entities_absent = _resolve_adapter_callable(
        adapter,
        "connectors.validation_test_entities_absent",
        "validation_test_entities_absent",
        default=lambda connector: (True, []),
    )
    ds_domain_resolver = _resolve_adapter_callable(
        adapter,
        "config.ds_domain_base",
        "ds_domain_base",
    )
    ds_name = getattr(getattr(adapter, "config", None), "DS_NAME", "demo")
    transfer_storage_verifier = TransferStorageVerifier(
        load_connector_credentials=load_connector_credentials,
        load_deployer_config=load_deployer_config,
        experiment_storage=ExperimentStorage,
    )

    return engine_cls(
        load_connector_credentials=load_connector_credentials,
        load_deployer_config=load_deployer_config,
        cleanup_test_entities=cleanup_test_entities,
        validation_test_entities_absent=validation_test_entities_absent,
        ds_domain_resolver=ds_domain_resolver,
        ds_name=ds_name,
        transfer_storage_verifier=transfer_storage_verifier,
    )


def build_kafka_manager(adapter, manager_cls=KafkaManager, kafka_runtime_config=None):
    """Build a Kafka manager that can reuse external brokers or auto-provision one."""
    kafka_config_loader = _resolve_adapter_callable(
        adapter,
        "get_kafka_config",
        default=lambda: {},
    )
    return manager_cls(
        runtime_config=kafka_runtime_config or {},
        adapter_config_loader=kafka_config_loader,
    )


def build_metrics_collector(
    adapter,
    collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_enabled=False,
    kafka_runtime_config=None,
):
    """Build a generic metrics collector from adapter-provided dependencies."""
    build_connector_url = _resolve_adapter_callable(
        adapter,
        "connectors.build_connector_url",
        "build_connector_url",
    )
    is_kafka_available = _resolve_adapter_callable(
        adapter,
        "is_kafka_available",
    )
    ensure_kafka_topic = _resolve_adapter_callable(
        adapter,
        "ensure_kafka_topic",
    )
    auto_mode_getter = _resolve_adapter_callable(
        adapter,
        "auto_mode_getter",
        default=False,
    )
    kafka_config_loader = _resolve_adapter_callable(
        adapter,
        "get_kafka_config",
        default=lambda: {},
    )
    connector_log_fetcher = _resolve_connector_log_fetcher(adapter)

    return collector_cls(
        build_connector_url=build_connector_url,
        is_kafka_available=is_kafka_available,
        ensure_kafka_topic=ensure_kafka_topic,
        experiment_storage=experiment_storage,
        auto_mode=auto_mode_getter,
        kafka_enabled=kafka_enabled,
        kafka_config_loader=kafka_config_loader,
        kafka_runtime_config=kafka_runtime_config or {},
        connector_log_fetcher=connector_log_fetcher,
    )


def build_runner(
    adapter_name="inesdata",
    runner_cls=ExperimentRunner,
    adapter_registry=None,
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    dry_run=False,
    iterations=1,
    kafka_enabled=False,
    kafka_runtime_config=None,
    kafka_manager_cls=KafkaManager,
    baseline=False,
    topology="local",
):
    """Create the experiment runner with the selected adapter."""
    adapter = build_adapter(
        adapter_name,
        adapter_registry=adapter_registry,
        dry_run=dry_run,
        topology=topology,
    )
    validation_engine = build_validation_engine(adapter, engine_cls=validation_engine_cls)
    metrics_collector = build_metrics_collector(
        adapter,
        collector_cls=metrics_collector_cls,
        experiment_storage=experiment_storage,
        kafka_enabled=kafka_enabled,
        kafka_runtime_config=kafka_runtime_config,
    )
    kafka_manager = None
    if kafka_enabled:
        kafka_manager = build_kafka_manager(
            adapter,
            manager_cls=kafka_manager_cls,
            kafka_runtime_config=kafka_runtime_config,
        )
    return runner_cls(
        adapter=adapter,
        validation_engine=validation_engine,
        metrics_collector=metrics_collector,
        experiment_storage=experiment_storage,
        iterations=iterations,
        kafka_manager=kafka_manager,
        baseline=baseline,
    )


def build_dry_run_preview(
    adapter_name,
    command,
    adapter_registry=None,
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    iterations=1,
    kafka_enabled=False,
    baseline=False,
    topology="local",
):
    """Build a safe preview of what a command would execute."""
    adapter = build_adapter(
        adapter_name,
        adapter_registry=adapter_registry,
        dry_run=True,
        topology=topology,
    )
    preview = {
        "status": "dry-run",
        "adapter": adapter_name,
        "command": command,
        "adapter_class": type(adapter).__name__,
        "topology": topology,
        "dry_run": getattr(adapter, "dry_run", True),
        "iterations": iterations,
        "kafka_enabled": kafka_enabled,
        "baseline": baseline,
        "actions": [],
    }

    if command == "deploy":
        preview["actions"] = ["deploy_infrastructure", "deploy_dataspace", "deploy_connectors"]
        return preview

    if command == "validate":
        validation_engine = build_validation_engine(adapter, engine_cls=validation_engine_cls)
        preview["actions"] = ["resolve_connectors", "run_validation"]
        preview["validation_engine"] = type(validation_engine).__name__
        preview["cleanup_available"] = callable(
            _resolve_adapter_callable(
                adapter,
                "connectors.cleanup_test_entities",
                "cleanup_test_entities",
            )
        )
        return preview

    if command == "metrics":
        metrics_collector = build_metrics_collector(
            adapter,
            collector_cls=metrics_collector_cls,
            experiment_storage=experiment_storage,
            kafka_enabled=kafka_enabled,
        )
        preview["actions"] = ["resolve_connectors", "collect_metrics", "store_results"]
        if kafka_enabled:
            preview["actions"].append("run_kafka_benchmark")
        preview["metrics_collector"] = type(metrics_collector).__name__
        preview["kafka_config_available"] = callable(
            _resolve_adapter_callable(adapter, "get_kafka_config")
        ) or any(
            bool(value) for value in (
                __import__("os").getenv("KAFKA_BOOTSTRAP_SERVERS"),
                __import__("os").getenv("KAFKA_TOPIC_NAME"),
            )
        )
        return preview

    preview["actions"] = [
        "deploy_infrastructure",
        "deploy_dataspace",
        "deploy_connectors",
        "run_validation",
        "collect_metrics",
        "store_results",
    ]
    if kafka_enabled:
        preview["actions"].append("run_kafka_benchmark")
    preview["runner"] = ExperimentRunner.__name__
    return preview


def _resolve_connectors(adapter):
    connectors = _resolve_adapter_callable(adapter, "get_cluster_connectors")
    if callable(connectors):
        resolved = connectors()
        if resolved:
            return resolved

    deploy_connectors = _resolve_adapter_callable(adapter, "deploy_connectors")
    if callable(deploy_connectors):
        resolved = deploy_connectors()
        if resolved:
            return resolved

    raise RuntimeError("Unable to resolve connectors from the selected adapter")


def _resolve_connector_log_fetcher(adapter):
    run_silent = getattr(adapter, "run_silent", None)
    config = getattr(adapter, "config", None)
    namespace = getattr(config, "NS_DS", None) if config is not None else None

    if not callable(run_silent) or not namespace:
        return None

    def fetch_connector_logs(connectors, metadata=None):
        logs = {}
        for connector in connectors or []:
            pod_name = f"{connector}-controlplane"
            output = run_silent(f"kubectl logs {pod_name} -n {namespace} --tail=500")
            if output:
                logs[connector] = output
        return logs

    return fetch_connector_logs


def _save_experiment_metadata(storage, experiment_dir, connectors, **kwargs):
    save_method = storage.save_experiment_metadata
    try:
        parameters = inspect.signature(save_method).parameters
    except (TypeError, ValueError):
        parameters = {}

    if len(parameters) <= 2:
        return save_method(experiment_dir, connectors)

    filtered_kwargs = {key: value for key, value in kwargs.items() if key in parameters}
    return save_method(experiment_dir, connectors, **filtered_kwargs)


def run_deploy(adapter):
    """Deploy infrastructure and connectors using the selected adapter."""
    deploy_infrastructure = _resolve_adapter_callable(adapter, "deploy_infrastructure")
    if callable(deploy_infrastructure):
        deploy_infrastructure()

    deploy_dataspace = _resolve_adapter_callable(adapter, "deploy_dataspace")
    if callable(deploy_dataspace):
        deploy_dataspace()

    deploy_connectors = _resolve_adapter_callable(adapter, "deploy_connectors")
    if not callable(deploy_connectors):
        raise RuntimeError("Selected adapter does not support connector deployment")

    return deploy_connectors()


def run_validate(
    adapter,
    validation_engine_cls=ValidationEngine,
    experiment_storage=ExperimentStorage,
    baseline=False,
):
    """Run validation collections with the selected adapter."""
    connectors = _resolve_connectors(adapter)
    experiment_dir = experiment_storage.create_experiment_directory()
    _save_experiment_metadata(
        experiment_storage,
        experiment_dir,
        connectors,
        adapter=type(adapter).__name__,
        baseline=baseline,
    )
    experiment_storage.newman_reports_dir(experiment_dir)

    validation_engine = build_validation_engine(adapter, engine_cls=validation_engine_cls)
    run_method = validation_engine.run

    try:
        parameters = inspect.signature(run_method).parameters
    except (TypeError, ValueError):
        parameters = {}

    metrics_collector = build_metrics_collector(
        adapter,
        collector_cls=MetricsCollector,
        experiment_storage=experiment_storage,
    )
    validation_result = None
    validation_error = None

    try:
        if "experiment_dir" in parameters:
            validation_result = run_method(connectors, experiment_dir=experiment_dir)
        else:
            validation_result = run_method(connectors)
    except Exception as exc:
        validation_error = exc

    newman_request_metrics = None
    try:
        collect_newman_metrics = getattr(metrics_collector, "collect_experiment_newman_metrics", None)
        if callable(collect_newman_metrics):
            newman_request_metrics = collect_newman_metrics(experiment_dir)
        else:
            newman_request_metrics = metrics_collector.collect_newman_request_metrics(
                experiment_storage.newman_reports_dir(experiment_dir),
                experiment_dir=experiment_dir,
            )
    except Exception:
        if validation_error is None:
            raise
        print("[WARNING] Newman metrics collection failed after validation error")
        newman_request_metrics = []

    if validation_error is not None:
        raise validation_error

    return {
        "experiment_dir": experiment_dir,
        "validation": validation_result,
        "newman_request_metrics": newman_request_metrics,
        "storage_checks": list(getattr(validation_engine, "last_storage_checks", []) or []),
    }


def run_metrics(
    adapter,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_enabled=False,
    kafka_runtime_config=None,
    kafka_manager_cls=KafkaManager,
    baseline=False,
):
    """Run metrics collection with the selected adapter."""
    connectors = _resolve_connectors(adapter)
    metrics_collector = build_metrics_collector(
        adapter,
        collector_cls=metrics_collector_cls,
        experiment_storage=experiment_storage,
        kafka_enabled=kafka_enabled,
        kafka_runtime_config=kafka_runtime_config,
    )
    kafka_manager = None
    if kafka_enabled:
        kafka_manager = build_kafka_manager(
            adapter,
            manager_cls=kafka_manager_cls,
            kafka_runtime_config=kafka_runtime_config,
        )
    experiment_dir = experiment_storage.create_experiment_directory()
    _save_experiment_metadata(
        experiment_storage,
        experiment_dir,
        connectors,
        adapter=type(adapter).__name__,
        baseline=baseline,
    )
    metrics = metrics_collector.collect(connectors, experiment_dir=experiment_dir)

    kafka_metrics = None
    if kafka_enabled:
        try:
            helper = getattr(metrics_collector, "run_kafka_benchmark_experiment", None)
            if callable(helper):
                kafka_metrics = helper(
                    experiment_dir,
                    iterations=1,
                    kafka_manager=kafka_manager,
                )
            else:
                kafka_runtime_overrides = None
                broker_source = None
                bootstrap_servers = kafka_manager.ensure_kafka_running() if kafka_manager is not None else None
                if kafka_manager is not None:
                    broker_source = "auto-provisioned" if getattr(kafka_manager, "started_by_framework", False) else "external"
                if bootstrap_servers:
                    kafka_runtime_overrides = {"bootstrap_servers": bootstrap_servers}
                    collect_kafka = metrics_collector.collect_kafka_benchmark
                    try:
                        parameters = inspect.signature(collect_kafka).parameters
                    except (TypeError, ValueError):
                        parameters = {}

                    kwargs = {"run_index": 1}
                    if "kafka_runtime_overrides" in parameters:
                        kwargs["kafka_runtime_overrides"] = kafka_runtime_overrides
                    kafka_metrics = collect_kafka(experiment_dir, **kwargs)
                    if isinstance(kafka_metrics, dict):
                        if broker_source is not None:
                            kafka_metrics.setdefault("broker_source", broker_source)
                        if bootstrap_servers is not None:
                            kafka_metrics.setdefault("bootstrap_servers", bootstrap_servers)
                        experiment_storage.save_kafka_metrics_json(kafka_metrics, experiment_dir)
                else:
                    reason = getattr(kafka_manager, "last_error", None) or "Kafka broker unavailable and auto-provisioning failed"
                    kafka_metrics = {
                        "kafka_benchmark": {
                            "status": "skipped",
                            "reason": reason,
                        }
                    }
                    if broker_source is not None:
                        kafka_metrics["broker_source"] = broker_source
                    experiment_storage.save_kafka_metrics_json(kafka_metrics, experiment_dir)

            if kafka_metrics is not None:
                return {
                    "experiment_dir": experiment_dir,
                    "metrics": metrics,
                    "kafka_metrics": kafka_metrics,
                }
        finally:
            if kafka_manager is not None:
                kafka_manager.stop_kafka()

    return metrics


def print_available_adapters(adapter_registry=None):
    """Print all available adapters from the registry."""
    registry = adapter_registry or ADAPTER_REGISTRY
    for adapter_name in sorted(registry):
        print(adapter_name)
    return list(sorted(registry))


def create_parser(adapter_registry=None):
    """Create the CLI parser for the experimentation framework."""
    registry = adapter_registry or ADAPTER_REGISTRY
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Dataspace Experimentation Framework CLI",
        usage="python main.py list | python main.py <adapter> [command] [--topology local] [--dry-run] [--iterations N] [--kafka] [--baseline] | python main.py report <experiment_id> | python main.py compare <experiment_a> <experiment_b>",
        epilog=(
            "Examples:\n"
            "  python main.py inesdata deploy --topology local\n"
            "  python main.py edc validate --topology local\n"
            "  python main.py inesdata metrics --topology local\n"
            "  python main.py inesdata metrics --topology local --kafka\n"
            "  python main.py inesdata run --topology local\n"
            "  python main.py inesdata run --topology local --iterations 50\n"
            "  python main.py inesdata run --topology local --baseline\n"
            "  python main.py inesdata run --topology local --dry-run\n"
            "  python main.py report experiment_2026-03-10_12-00-00\n"
            "  python main.py compare experiment_A experiment_B\n"
            "  python main.py list"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "adapter",
        nargs="?",
        help=f"Adapter name ({', '.join(sorted(registry))}) or 'list'",
    )
    parser.add_argument(
        "command",
        nargs="?",
        help="Command to execute. Defaults to 'run'.",
    )
    parser.add_argument("extra", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument(
        "--topology",
        choices=SUPPORTED_TOPOLOGIES,
        default=SUPPORTED_TOPOLOGIES[0],
        help="Deployment topology to target (currently only 'local').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview command wiring without executing real deployments or validations.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of repeated experiment runs for the same scenario (default: 1).",
    )
    parser.add_argument(
        "--kafka",
        action="store_true",
        help="Enable the optional Kafka broker benchmark during the metrics phase.",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Mark the generated experiment as a baseline run.",
    )
    return parser


def main(
    argv=None,
    runner_cls=ExperimentRunner,
    adapter_registry=None,
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_manager_cls=KafkaManager,
    report_generator_cls=ExperimentReportGenerator,
):
    """Main entry point for the Dataspace Experimentation Framework."""
    parser = create_parser(adapter_registry=adapter_registry)
    args = parser.parse_args(argv)
    registry = adapter_registry or ADAPTER_REGISTRY

    if args.iterations < 1:
        parser.error("--iterations must be greater than or equal to 1")

    if not args.adapter:
        parser.print_help()
        return 1

    if args.adapter == "list":
        if args.command is not None:
            parser.error("'list' does not accept an additional command")
        return print_available_adapters(adapter_registry=registry)

    if args.adapter == "report":
        experiment_id = args.command
        if not experiment_id or args.extra:
            parser.error("'report' expects exactly one experiment identifier")
        generator = report_generator_cls(storage=experiment_storage)
        summary = generator.generate(experiment_id)
        return {
            "experiment_dir": ExperimentLoader.experiment_dir(experiment_id),
            "summary": summary,
        }

    if args.adapter == "compare":
        experiment_a = args.command
        experiment_b = args.extra[0] if args.extra else None
        if not experiment_a or not experiment_b or len(args.extra) != 1:
            parser.error("'compare' expects exactly two experiment identifiers")
        generator = report_generator_cls(storage=experiment_storage)
        return generator.compare(experiment_a, experiment_b)

    if args.adapter not in registry:
        parser.error(
            f"Unsupported adapter '{args.adapter}'. Available adapters: {', '.join(sorted(registry))}"
        )

    command = args.command or "run"
    if command not in SUPPORTED_COMMANDS:
        parser.error(
            f"argument command: invalid choice: '{command}' (choose from {', '.join(SUPPORTED_COMMANDS)})"
        )
    if args.extra:
        parser.error(f"unrecognized arguments: {' '.join(args.extra)}")

    if args.dry_run:
        return build_dry_run_preview(
            adapter_name=args.adapter,
            command=command,
            adapter_registry=registry,
            validation_engine_cls=validation_engine_cls,
            metrics_collector_cls=metrics_collector_cls,
            experiment_storage=experiment_storage,
            iterations=args.iterations,
            kafka_enabled=args.kafka,
            baseline=args.baseline,
            topology=args.topology,
        )

    try:
        adapter = build_adapter(
            args.adapter,
            adapter_registry=registry,
            dry_run=False,
            topology=args.topology,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if command == "deploy":
        return run_deploy(adapter)

    if command == "validate":
        return run_validate(
            adapter,
            validation_engine_cls=validation_engine_cls,
            experiment_storage=experiment_storage,
            baseline=args.baseline,
        )

    if command == "metrics":
        return run_metrics(
            adapter,
            metrics_collector_cls=metrics_collector_cls,
            experiment_storage=experiment_storage,
            kafka_enabled=args.kafka,
            kafka_manager_cls=kafka_manager_cls,
            baseline=args.baseline,
        )

    runner = build_runner(
        adapter_name=args.adapter,
        runner_cls=runner_cls,
        adapter_registry=registry,
        validation_engine_cls=validation_engine_cls,
        metrics_collector_cls=metrics_collector_cls,
        experiment_storage=experiment_storage,
        dry_run=False,
        iterations=args.iterations,
        kafka_enabled=args.kafka,
        kafka_manager_cls=kafka_manager_cls,
        baseline=args.baseline,
        topology=args.topology,
    )
    return runner.run()


if __name__ == "__main__":
    main()
