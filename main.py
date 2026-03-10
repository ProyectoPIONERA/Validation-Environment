import argparse
import importlib
import inspect

from framework.experiment_runner import ExperimentRunner
from framework.experiment_storage import ExperimentStorage
from framework.kafka_manager import KafkaManager
from framework.metrics_collector import MetricsCollector
from framework.validation_engine import ValidationEngine


ADAPTER_REGISTRY = {
    "inesdata": "adapters.inesdata.adapter:InesdataAdapter",
}

SUPPORTED_COMMANDS = ("deploy", "validate", "metrics", "run")


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


def build_adapter(adapter_name="inesdata", adapter_registry=None, dry_run=False):
    """Instantiate the selected dataspace adapter."""
    adapter_class = resolve_adapter_class(adapter_name, adapter_registry=adapter_registry)

    try:
        parameters = inspect.signature(adapter_class).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "dry_run" in parameters:
        return adapter_class(dry_run=dry_run)

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
    ds_domain_resolver = _resolve_adapter_callable(
        adapter,
        "config.ds_domain_base",
        "ds_domain_base",
    )
    ds_name = getattr(getattr(adapter, "config", None), "DS_NAME", "demo")

    return engine_cls(
        load_connector_credentials=load_connector_credentials,
        load_deployer_config=load_deployer_config,
        cleanup_test_entities=cleanup_test_entities,
        ds_domain_resolver=ds_domain_resolver,
        ds_name=ds_name,
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

    return collector_cls(
        build_connector_url=build_connector_url,
        is_kafka_available=is_kafka_available,
        ensure_kafka_topic=ensure_kafka_topic,
        experiment_storage=experiment_storage,
        auto_mode=auto_mode_getter,
        kafka_enabled=kafka_enabled,
        kafka_config_loader=kafka_config_loader,
        kafka_runtime_config=kafka_runtime_config or {},
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
):
    """Create the experiment runner with the selected adapter."""
    adapter = build_adapter(adapter_name, adapter_registry=adapter_registry, dry_run=dry_run)
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
):
    """Build a safe preview of what a command would execute."""
    adapter = build_adapter(adapter_name, adapter_registry=adapter_registry, dry_run=True)
    preview = {
        "status": "dry-run",
        "adapter": adapter_name,
        "command": command,
        "adapter_class": type(adapter).__name__,
        "dry_run": getattr(adapter, "dry_run", True),
        "iterations": iterations,
        "kafka_enabled": kafka_enabled,
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


def run_validate(adapter, validation_engine_cls=ValidationEngine, experiment_storage=ExperimentStorage):
    """Run validation collections with the selected adapter."""
    connectors = _resolve_connectors(adapter)
    experiment_dir = experiment_storage.create_experiment_directory()
    experiment_storage.save_experiment_metadata(experiment_dir, connectors)

    validation_engine = build_validation_engine(adapter, engine_cls=validation_engine_cls)
    run_method = validation_engine.run

    try:
        parameters = inspect.signature(run_method).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "experiment_dir" in parameters:
        validation_result = run_method(connectors, experiment_dir=experiment_dir)
    else:
        validation_result = run_method(connectors)

    metrics_collector = build_metrics_collector(
        adapter,
        collector_cls=MetricsCollector,
        experiment_storage=experiment_storage,
    )
    newman_request_metrics = metrics_collector.collect_newman_request_metrics(
        experiment_storage.newman_reports_dir(experiment_dir),
        experiment_dir=experiment_dir,
    )

    return {
        "experiment_dir": experiment_dir,
        "validation": validation_result,
        "newman_request_metrics": newman_request_metrics,
    }


def run_metrics(
    adapter,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_enabled=False,
    kafka_runtime_config=None,
    kafka_manager_cls=KafkaManager,
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
    experiment_storage.save_experiment_metadata(experiment_dir, connectors)
    metrics = metrics_collector.collect(connectors, experiment_dir=experiment_dir)

    kafka_metrics = None
    if kafka_enabled:
        try:
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

            if kafka_metrics is not None:
                experiment_storage.save_kafka_metrics_json(kafka_metrics, experiment_dir)
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
        usage="python main.py list | python main.py <adapter> [command] [--dry-run] [--iterations N] [--kafka]",
        epilog=(
            "Examples:\n"
            "  python main.py inesdata deploy\n"
            "  python main.py inesdata validate\n"
            "  python main.py inesdata metrics\n"
            "  python main.py inesdata metrics --kafka\n"
            "  python main.py inesdata run\n"
            "  python main.py inesdata run --iterations 50\n"
            "  python main.py inesdata run --dry-run\n"
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
        choices=SUPPORTED_COMMANDS,
        help="Command to execute. Defaults to 'run'.",
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
    return parser


def main(
    argv=None,
    runner_cls=ExperimentRunner,
    adapter_registry=None,
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_manager_cls=KafkaManager,
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

    if args.adapter not in registry:
        parser.error(
            f"Unsupported adapter '{args.adapter}'. Available adapters: {', '.join(sorted(registry))}"
        )

    command = args.command or "run"

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
        )

    try:
        adapter = build_adapter(args.adapter, adapter_registry=registry, dry_run=False)
    except ValueError as exc:
        parser.error(str(exc))

    if command == "deploy":
        return run_deploy(adapter)

    if command == "validate":
        return run_validate(
            adapter,
            validation_engine_cls=validation_engine_cls,
            experiment_storage=experiment_storage,
        )

    if command == "metrics":
        return run_metrics(
            adapter,
            metrics_collector_cls=metrics_collector_cls,
            experiment_storage=experiment_storage,
            kafka_enabled=args.kafka,
            kafka_manager_cls=kafka_manager_cls,
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
    )
    return runner.run()


if __name__ == "__main__":
    main()
