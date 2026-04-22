import argparse
import contextlib
import importlib
import inspect
import json
import os
import subprocess
import sys
import time

from runtime_dependencies import ensure_runtime_dependencies


ensure_runtime_dependencies(
    requirements_path=os.path.join(os.path.dirname(__file__), "requirements.txt"),
    module_names=("requests", "matplotlib", "kafka", "docker", "testcontainers", "yaml", "minio", "tabulate"),
    label="framework root",
    module_requirements={
        "requests": "requests",
        "matplotlib": "matplotlib",
        "kafka": "kafka-python",
        "docker": "docker",
        "testcontainers": "testcontainers",
        "yaml": "PyYAML",
        "minio": "minio",
        "tabulate": "tabulate",
    },
)

from framework.experiment_runner import ExperimentRunner
from framework.experiment_storage import ExperimentStorage
from framework.kafka_edc_validation import KafkaEdcValidationSuite
from framework.kafka_manager import KafkaManager
from framework.metrics_collector import MetricsCollector
from framework.reporting.experiment_loader import ExperimentLoader
from framework.reporting.report_generator import ExperimentReportGenerator
from framework.transfer_storage_verifier import TransferStorageVerifier
from framework.validation_engine import ValidationEngine
from framework import local_menu_tools
from deployers.infrastructure.lib.hosts_manager import (
    apply_managed_blocks,
    blocks_as_dict,
    build_context_host_blocks,
    hostnames_by_level,
)
from deployers.infrastructure.lib.orchestrator import DeployerOrchestrator
from deployers.infrastructure.lib.topology import SUPPORTED_TOPOLOGIES as DEPLOYER_SUPPORTED_TOPOLOGIES
from validation.core.test_data_cleanup import run_pre_validation_cleanup
from validation.orchestration.hosts import (
    ensure_public_endpoints_accessible,
    normalize_public_endpoint_url,
)
from validation.orchestration.kafka import run_kafka_edc_validation
from validation.ui import interactive_menu as ui_interactive_menu
from validation.ui.ui_runner import run_playwright_validation


ADAPTER_REGISTRY = {
    "inesdata": "adapters.inesdata.adapter:InesdataAdapter",
    "edc": "adapters.edc.adapter:EdcAdapter",
}
DEPLOYER_REGISTRY = {
    "inesdata": "deployers.inesdata.deployer:InesdataDeployer",
    "edc": "deployers.edc.deployer:EdcDeployer",
}

SUPPORTED_COMMANDS = ("deploy", "validate", "metrics", "run", "hosts", "recreate-dataspace")
SUPPORTED_TOPOLOGIES = DEPLOYER_SUPPORTED_TOPOLOGIES
LEVEL_DESCRIPTIONS = {
    1: "Setup Cluster",
    2: "Deploy Common Services",
    3: "Deploy Dataspace",
    4: "Deploy Connectors",
    5: "Deploy Components",
    6: "Run Validation Tests",
}


def _env_flag(name, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in ("1", "true", "yes", "on")


@contextlib.contextmanager
def _temporary_environment(overrides=None):
    updates = dict(overrides or {})
    if not updates:
        yield
        return

    sentinel = object()
    previous = {}
    try:
        for key, value in updates.items():
            previous[key] = os.environ.get(key, sentinel)
            os.environ[key] = str(value)
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextlib.contextmanager
def _temporary_adapter_auto_mode(adapter, enabled=True):
    targets = [
        adapter,
        getattr(adapter, "deployment", None),
        getattr(getattr(adapter, "deployment", None), "_delegate", None),
        getattr(adapter, "connectors", None),
        getattr(adapter, "infrastructure", None),
    ]
    sentinel = object()
    previous = []
    try:
        for target in targets:
            if target is None or not hasattr(target, "auto_mode_getter"):
                continue
            previous.append((target, getattr(target, "auto_mode_getter", sentinel)))
            setattr(target, "auto_mode_getter", lambda enabled=enabled: bool(enabled))
        yield
    finally:
        for target, old_value in previous:
            if old_value is sentinel:
                delattr(target, "auto_mode_getter")
            else:
                setattr(target, "auto_mode_getter", old_value)


_REDACTED_VALUE = "***REDACTED***"
_SENSITIVE_KEY_MARKERS = (
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "SECRET",
    "CLIENT_SECRET",
    "ACCESS_KEY",
    "SECRET_KEY",
    "PRIVATE_KEY",
)


def _is_sensitive_preview_key(key):
    normalized = str(key or "").strip().upper()
    if not normalized:
        return False
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _sanitize_preview_data(value, parent_key=None):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if _is_sensitive_preview_key(key):
                sanitized[key] = _REDACTED_VALUE
            else:
                sanitized[key] = _sanitize_preview_data(item, parent_key=key)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_preview_data(item, parent_key=parent_key) for item in value]
    return value


def _mapping_flag(mapping, key, default=False):
    if not isinstance(mapping, dict):
        return default
    raw_value = mapping.get(key)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in ("1", "true", "yes", "on")


def _edc_dashboard_runtime_present(deployer_context):
    runtime_dir = str(getattr(deployer_context, "runtime_dir", "") or "").strip()
    connectors = list(getattr(deployer_context, "connectors", []) or [])
    if not runtime_dir or not connectors:
        return False

    for connector in connectors:
        dashboard_dir = os.path.join(runtime_dir, "dashboard", connector)
        if os.path.isfile(os.path.join(dashboard_dir, "app-config.json")) and os.path.isfile(
            os.path.join(dashboard_dir, "edc-connector-config.json")
        ):
            return True
    return False


def _edc_dashboard_runtime_auth_mode(deployer_context):
    runtime_dir = str(getattr(deployer_context, "runtime_dir", "") or "").strip()
    connectors = list(getattr(deployer_context, "connectors", []) or [])
    if not runtime_dir or not connectors:
        return None

    for connector in connectors:
        values_file = os.path.join(runtime_dir, f"values-{connector}.yaml")
        if not os.path.isfile(values_file):
            continue
        try:
            with open(values_file, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    stripped = raw_line.strip()
                    if not stripped.startswith("authMode:"):
                        continue
                    auth_mode = stripped.split(":", 1)[1].strip().strip("'\"")
                    if auth_mode:
                        return auth_mode.lower()
        except OSError:
            continue
    return None


def _edc_dashboard_namespace(deployer_context):
    namespace_roles = getattr(deployer_context, "namespace_roles", None)
    namespace = str(getattr(namespace_roles, "provider_namespace", "") or "").strip()
    if namespace:
        return namespace
    namespace = str(getattr(namespace_roles, "consumer_namespace", "") or "").strip()
    if namespace:
        return namespace
    return str(getattr(deployer_context, "dataspace_name", "") or "").strip()


def _positive_float_env(name, default):
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return float(default)
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        print(f"[WARNING] Ignoring invalid {name}={raw_value!r}; using {default}")
        return float(default)


def _kubectl_endpoint_ready(namespace, service_name):
    command = [
        "kubectl",
        "get",
        "endpoints",
        service_name,
        "-n",
        namespace,
        "-o",
        "json",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "kubectl is not available"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or f"kubectl returned exit code {result.returncode}"

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False, "kubectl endpoint output is not valid JSON"

    subsets = payload.get("subsets") or []
    for subset in subsets:
        addresses = subset.get("addresses") or []
        ports = subset.get("ports") or []
        if addresses and ports:
            return True, f"{len(addresses)} endpoint address(es)"
    return False, "service has no ready endpoints"


def _probe_edc_dashboard_readiness(deployer_context):
    namespace = _edc_dashboard_namespace(deployer_context)
    connectors = list(getattr(deployer_context, "connectors", []) or [])
    gates = []

    if not namespace:
        return {
            "status": "failed",
            "namespace": namespace,
            "connectors": connectors,
            "gates": [{"gate": "namespace", "ready": False, "detail": "namespace is empty"}],
        }

    if not connectors:
        return {
            "status": "failed",
            "namespace": namespace,
            "connectors": connectors,
            "gates": [{"gate": "connectors", "ready": False, "detail": "no connectors resolved"}],
        }

    for connector in connectors:
        for suffix in ("dashboard", "dashboard-proxy"):
            service_name = f"{connector}-{suffix}"
            ready, detail = _kubectl_endpoint_ready(namespace, service_name)
            gates.append({
                "gate": f"{suffix}:{connector}",
                "namespace": namespace,
                "service": service_name,
                "ready": ready,
                "detail": detail,
            })

    status = "passed" if all(gate["ready"] for gate in gates) else "failed"
    return {
        "status": status,
        "namespace": namespace,
        "connectors": connectors,
        "gates": gates,
    }


def _write_edc_dashboard_readiness(experiment_dir, readiness):
    if not experiment_dir:
        return None
    output_dir = os.path.join(experiment_dir, "ui", "edc")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "dashboard_readiness.json")
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(readiness, handle, indent=2)
    return output_path


def _wait_for_edc_dashboard_readiness(deployer_context, experiment_dir=None):
    timeout = _positive_float_env("PIONERA_EDC_DASHBOARD_READINESS_TIMEOUT_SECONDS", 90)
    poll_interval = _positive_float_env("PIONERA_EDC_DASHBOARD_READINESS_POLL_SECONDS", 3)
    deadline = time.monotonic() + timeout
    readiness = None

    while True:
        readiness = _probe_edc_dashboard_readiness(deployer_context)
        readiness["timeout_seconds"] = timeout
        readiness["poll_interval_seconds"] = poll_interval
        if readiness.get("status") == "passed":
            readiness["artifact"] = _write_edc_dashboard_readiness(experiment_dir, readiness)
            return readiness

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            readiness["artifact"] = _write_edc_dashboard_readiness(experiment_dir, readiness)
            return readiness

        time.sleep(min(poll_interval, remaining))


def _edc_dashboard_readiness_failure_message(readiness):
    failed_gates = [
        gate for gate in readiness.get("gates", [])
        if not gate.get("ready")
    ]
    if not failed_gates:
        return "EDC dashboard readiness did not pass"

    details = []
    for gate in failed_gates[:6]:
        service = gate.get("service") or gate.get("gate")
        detail = gate.get("detail") or "not ready"
        details.append(f"{service}: {detail}")
    if len(failed_gates) > 6:
        details.append(f"... and {len(failed_gates) - 6} more")

    artifact = readiness.get("artifact")
    artifact_text = f" Details saved in {artifact}." if artifact else ""
    return (
        "Playwright validation for 'edc' requires the dashboard and dashboard-proxy "
        "services to have ready endpoints. Missing readiness: "
        + "; ".join(details)
        + artifact_text
    )


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


def resolve_deployer_class(deployer_name, deployer_registry=None):
    """Resolve a deployer wrapper class from the configured registry."""
    registry = deployer_registry or DEPLOYER_REGISTRY

    if deployer_name not in registry:
        supported = ", ".join(sorted(registry))
        raise ValueError(f"Unsupported deployer '{deployer_name}'. Supported deployers: {supported}")

    try:
        module_path, class_name = registry[deployer_name].split(":", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as exc:
        raise ValueError(
            f"Failed to load deployer '{deployer_name}' from '{registry[deployer_name]}': {exc}"
        ) from exc


def build_deployer(
    deployer_name="inesdata",
    deployer_registry=None,
    adapter_registry=None,
    dry_run=False,
    topology="local",
    adapter=None,
):
    """Instantiate the selected deployer wrapper without altering the active CLI flow."""
    deployer_class = resolve_deployer_class(deployer_name, deployer_registry=deployer_registry)
    resolved_adapter = adapter or build_adapter(
        deployer_name,
        adapter_registry=adapter_registry,
        dry_run=dry_run,
        topology=topology,
    )

    try:
        parameters = inspect.signature(deployer_class).parameters
    except (TypeError, ValueError):
        parameters = {}

    kwargs = {}
    if "adapter" in parameters:
        kwargs["adapter"] = resolved_adapter
    if "topology" in parameters:
        kwargs["topology"] = topology

    if kwargs:
        return deployer_class(**kwargs)

    return deployer_class()


def build_deployer_orchestrator(
    deployer_name="inesdata",
    deployer_registry=None,
    adapter_registry=None,
    dry_run=False,
    topology="local",
    adapter=None,
    validation_executor=None,
):
    """Build the future deployer orchestrator without changing production command routing."""
    deployer = build_deployer(
        deployer_name=deployer_name,
        deployer_registry=deployer_registry,
        adapter_registry=adapter_registry,
        dry_run=dry_run,
        topology=topology,
        adapter=adapter,
    )
    return DeployerOrchestrator(deployer, validation_executor=validation_executor)


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
    ds_name = "demo"
    config = getattr(adapter, "config", None)
    dataspace_name_getter = getattr(config, "dataspace_name", None)
    if callable(dataspace_name_getter):
        resolved_name = dataspace_name_getter()
        if resolved_name:
            ds_name = resolved_name
    else:
        config_adapter = getattr(adapter, "config_adapter", None)
        dataspace_name_getter = getattr(config_adapter, "primary_dataspace_name", None)
        if callable(dataspace_name_getter):
            resolved_name = dataspace_name_getter()
            if resolved_name:
                ds_name = resolved_name
        else:
            ds_name = getattr(config, "DS_NAME", "demo")
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


def _adapter_level6_kafka_name(adapter, validation_profile=None, deployer_name=None):
    candidates = []
    if validation_profile is not None:
        candidates.append(getattr(validation_profile, "adapter", ""))
    if deployer_name:
        candidates.append(deployer_name)
    try:
        candidates.append(_infer_deployer_name_from_adapter(adapter))
    except Exception:
        pass

    for candidate in candidates:
        normalized = str(candidate or "").strip().lower()
        if normalized:
            return normalized
    return ""


def _supports_level6_kafka_edc(adapter, validation_profile=None, deployer_name=None):
    adapter_name = _adapter_level6_kafka_name(
        adapter,
        validation_profile=validation_profile,
        deployer_name=deployer_name,
    )
    if adapter_name not in {"edc", "inesdata"}:
        return False

    return callable(_resolve_adapter_callable(adapter, "get_kafka_config"))


def _dataspace_name_loader(adapter):
    config = getattr(adapter, "config", None)
    dataspace_name_getter = getattr(config, "dataspace_name", None)
    if callable(dataspace_name_getter):
        return dataspace_name_getter

    config_adapter = getattr(adapter, "config_adapter", None)
    dataspace_name_getter = getattr(config_adapter, "primary_dataspace_name", None)
    if callable(dataspace_name_getter):
        return dataspace_name_getter

    return lambda: getattr(config, "DS_NAME", "demo")


def build_kafka_edc_validation_suite(
    adapter,
    suite_cls=KafkaEdcValidationSuite,
    experiment_storage=ExperimentStorage,
    kafka_manager_cls=KafkaManager,
):
    """Build the Level 6 functional EDC+Kafka validator from adapter hooks."""
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
    kafka_runtime_loader = _resolve_adapter_callable(
        adapter,
        "get_kafka_config",
        default=lambda: {},
    )
    ensure_kafka_topic = _resolve_adapter_callable(
        adapter,
        "ensure_kafka_topic",
    )

    missing_dependencies = [
        name
        for name, dependency in (
            ("load_connector_credentials", load_connector_credentials),
            ("load_deployer_config", load_deployer_config),
            ("ds_domain_resolver", ds_domain_resolver),
        )
        if not callable(dependency)
    ]
    if missing_dependencies:
        missing = ", ".join(missing_dependencies)
        raise RuntimeError(f"Kafka transfer validation cannot run because adapter is missing: {missing}")

    kafka_manager = build_kafka_manager(adapter, manager_cls=kafka_manager_cls)
    return suite_cls(
        load_connector_credentials=load_connector_credentials,
        load_deployer_config=load_deployer_config,
        kafka_runtime_loader=kafka_runtime_loader,
        ensure_kafka_topic=ensure_kafka_topic,
        kafka_manager=kafka_manager,
        experiment_storage=experiment_storage,
        ds_domain_resolver=ds_domain_resolver,
        ds_name_loader=_dataspace_name_loader(adapter),
    )


def _save_kafka_edc_results(results, experiment_dir, experiment_storage=ExperimentStorage):
    saver = getattr(experiment_storage, "save_kafka_edc_results_json", None)
    if callable(saver):
        saver(results, experiment_dir)


def _format_console_metric(value, suffix=""):
    if value in (None, ""):
        return "n/a"
    return f"{value}{suffix}"


def _console_status_label(status):
    status_labels = {
        "passed": "✓ PASS",
        "failed": "✗ FAIL",
        "skipped": "- SKIP",
    }
    normalized = str(status or "unknown").lower()
    return status_labels.get(normalized, f"? {str(status or 'unknown').upper()}")


def _print_kafka_transfer_steps(result, indent="    "):
    steps = result.get("steps") if isinstance(result, dict) else None
    if not isinstance(steps, list) or not steps:
        return

    detail_keys = (
        "http_status",
        "state",
        "topic",
        "asset_id",
        "agreement_id",
        "transfer_id",
        "messages_consumed",
        "average_latency_ms",
    )
    print(f"{indent}Steps:")
    for step in steps:
        if not isinstance(step, dict):
            continue
        status = _console_status_label(step.get("status", "unknown"))
        name = step.get("name", "unknown_step")
        details = [
            f"{key}={step[key]}"
            for key in detail_keys
            if step.get(key) not in (None, "")
        ]
        suffix = f" ({', '.join(details)})" if details else ""
        print(f"{indent}  {status} {name}{suffix}")


def _print_kafka_edc_results(results):
    print("Kafka transfer validation results:")
    verbose_messages = _env_flag(
        "PIONERA_KAFKA_TRANSFER_LOG_MESSAGES",
        _env_flag("KAFKA_TRANSFER_LOG_MESSAGES", False),
    )
    for result in results or []:
        provider = result.get("provider", "unknown-provider")
        consumer = result.get("consumer", "unknown-consumer")
        status = result.get("status", "unknown")
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        artifact_path = result.get("artifact_path")
        if status == "passed":
            print(f"  {_console_status_label(status)} Kafka transfer: {provider} -> {consumer}")
            _print_kafka_transfer_steps(result)
            if result.get("source_topic") or result.get("destination_topic"):
                print(f"    Topics: {result.get('source_topic')} -> {result.get('destination_topic')}")
            if metrics:
                print(
                    "    Messages: "
                    f"produced={_format_console_metric(metrics.get('messages_produced'))} "
                    f"consumed={_format_console_metric(metrics.get('messages_consumed'))}"
                )
                print(
                    "    Latency: "
                    f"avg={_format_console_metric(metrics.get('average_latency_ms'), 'ms')} "
                    f"p50={_format_console_metric(metrics.get('p50_latency_ms'), 'ms')} "
                    f"p95={_format_console_metric(metrics.get('p95_latency_ms'), 'ms')} "
                    f"p99={_format_console_metric(metrics.get('p99_latency_ms'), 'ms')}"
                )
                print(
                    "    Throughput: "
                    f"{_format_console_metric(metrics.get('throughput_messages_per_second'), ' msg/s')}"
                )
                if verbose_messages:
                    for sample in metrics.get("message_samples") or []:
                        print(
                            "    Message: "
                            f"id={sample.get('message_id')} "
                            f"status={sample.get('status')} "
                            f"latency={sample.get('latency_ms', 'n/a')}ms"
                        )
            if artifact_path:
                print(f"    Artifact: {artifact_path}")
        elif status == "failed":
            error = (result.get("error") or {}).get("message", "unknown reason")
            print(f"  {_console_status_label(status)} Kafka transfer: {provider} -> {consumer} ({error})")
            _print_kafka_transfer_steps(result)
            if artifact_path:
                print(f"    Artifact: {artifact_path}")
        else:
            reason = result.get("reason", "unknown reason")
            print(f"  {_console_status_label(status)} Kafka transfer: {provider} -> {consumer} ({reason})")
            _print_kafka_transfer_steps(result)
            if artifact_path:
                print(f"    Artifact: {artifact_path}")


def run_level6_kafka_edc_after_newman(
    adapter,
    connectors,
    experiment_dir,
    *,
    validation_profile=None,
    deployer_name=None,
    experiment_storage=ExperimentStorage,
    suite_cls=KafkaEdcValidationSuite,
    kafka_manager_cls=KafkaManager,
):
    """Run the functional EDC+Kafka suite automatically after Newman in Level 6."""
    if not _supports_level6_kafka_edc(
        adapter,
        validation_profile=validation_profile,
        deployer_name=deployer_name,
    ):
        return []

    print("\nRunning Kafka transfer validation suite...")
    try:
        validator = build_kafka_edc_validation_suite(
            adapter,
            suite_cls=suite_cls,
            experiment_storage=experiment_storage,
            kafka_manager_cls=kafka_manager_cls,
        )
        results = run_kafka_edc_validation(
            list(connectors or []),
            experiment_dir,
            validator=validator,
            experiment_storage=experiment_storage,
        )
    except Exception as exc:
        results = [
            {
                "status": "failed",
                "reason": "execution_error",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        ]
        _save_kafka_edc_results(results, experiment_dir, experiment_storage=experiment_storage)

    _print_kafka_edc_results(results)
    return list(results or [])


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
    deployer_registry=None,
    include_deployer_dry_run=None,
    with_connectors=False,
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

    if include_deployer_dry_run is None:
        include_deployer_dry_run = _env_flag(
            "PIONERA_ENABLE_DEPLOYER_DRY_RUN",
            default=str(topology or "local").strip().lower() != "local",
        )

    if include_deployer_dry_run:
        preview["deployer_orchestrator"] = _build_deployer_dry_run_preview(
            adapter_name=adapter_name,
            command=command,
            topology=topology,
            adapter=adapter,
            adapter_registry=adapter_registry,
            deployer_registry=deployer_registry,
        )

    adapter_preview = _resolve_adapter_preview(adapter, command)
    if adapter_preview is not None:
        preview["preflight"] = adapter_preview

    if command == "deploy":
        preview["actions"] = ["deploy_infrastructure", "deploy_dataspace", "deploy_connectors"]
        return preview

    if command == "validate":
        validation_engine = build_validation_engine(adapter, engine_cls=validation_engine_cls)
        preview["actions"] = ["resolve_connectors", "run_pre_validation_cleanup_if_enabled", "run_validation"]
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

    if command == "hosts":
        preview["actions"] = ["resolve_deployer_context", "plan_hosts_entries"]
        try:
            _resolved_name, context = _resolve_deployer_context(
                adapter,
                deployer_name=adapter_name,
                deployer_registry=deployer_registry,
                topology=topology,
            )
            preview["hosts_plan"] = _build_shadow_host_sync_plan(context)
        except Exception as exc:
            preview["hosts_plan"] = {
                "status": "unavailable",
                "reason": str(exc),
            }
        return preview

    if command == "recreate-dataspace":
        preview["actions"] = [
            "resolve_deployer_context",
            "render_recreate_dataspace_plan",
            "require_exact_dataspace_confirmation",
            "delete_selected_dataspace_resources",
            "run_level_3_again",
        ]
        if with_connectors:
            preview["actions"].append("run_level_4_connectors")
        else:
            preview["actions"].append("skip_level_4_connectors")
        preview["with_connectors"] = bool(with_connectors)
        try:
            _resolved_name, context = _resolve_deployer_context(
                adapter,
                deployer_name=adapter_name,
                deployer_registry=deployer_registry,
                topology=topology,
            )
            preview["recreate_dataspace_plan"] = _build_recreate_dataspace_plan(adapter, context)
        except Exception as exc:
            preview["recreate_dataspace_plan"] = {
                "status": "unavailable",
                "reason": str(exc),
            }
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


def _resolve_adapter_preview(adapter, command):
    preview_method = _resolve_adapter_callable(adapter, f"preview_{command}")
    if callable(preview_method):
        return preview_method()

    preview_method = _resolve_adapter_callable(adapter, "preview_command")
    if callable(preview_method):
        return preview_method(command)

    return None


def _build_deployer_dry_run_preview(
    adapter_name,
    command,
    topology="local",
    adapter=None,
    adapter_registry=None,
    deployer_registry=None,
):
    orchestrator = build_deployer_orchestrator(
        deployer_name=adapter_name,
        deployer_registry=deployer_registry,
        adapter_registry=adapter_registry,
        adapter=adapter,
        dry_run=True,
        topology=topology,
    )
    context = orchestrator.resolve_context(topology=topology)
    deployer = orchestrator.deployer
    preview = {
        "status": "available",
        "deployer": getattr(deployer, "name", lambda: type(deployer).__name__.lower())(),
        "deployer_class": type(deployer).__name__,
        "topology": topology,
        "context": _sanitize_preview_data(context.as_dict()),
    }

    if command == "deploy":
        preview["actions"] = [
            "resolve_context",
            "deploy_infrastructure",
            "deploy_dataspace",
            "deploy_connectors",
            "deploy_components",
        ]
        return preview

    profile = orchestrator.get_validation_profile(context)
    if command == "validate":
        preview["actions"] = [
            "resolve_context",
            "get_validation_profile",
            "run_pre_validation_cleanup_if_enabled",
            "run_newman_if_enabled",
            "run_playwright_if_enabled",
            "run_component_validation_if_enabled",
        ]
        preview["validation_profile"] = profile.as_dict()
        return preview

    if command == "metrics":
        preview["actions"] = [
            "resolve_context",
            "resolve_connectors",
            "collect_metrics",
        ]
        return preview

    if command == "hosts":
        preview["actions"] = [
            "resolve_context",
            "plan_hosts_entries",
            "apply_hosts_entries_if_explicitly_enabled",
        ]
        preview["hosts_plan"] = _build_shadow_host_sync_plan(context)
        return preview

    if command == "recreate-dataspace":
        preview["actions"] = [
            "resolve_context",
            "render_recreate_dataspace_plan",
            "require_exact_dataspace_confirmation",
            "delete_selected_dataspace_resources",
            "run_level_3_again",
        ]
        return preview

    preview["actions"] = [
        "resolve_context",
        "deploy_infrastructure",
        "deploy_dataspace",
        "deploy_connectors",
        "deploy_components",
        "get_validation_profile",
        "run_pre_validation_cleanup_if_enabled",
        "run_newman_if_enabled",
        "run_playwright_if_enabled",
        "run_component_validation_if_enabled",
        "collect_metrics",
    ]
    preview["validation_profile"] = profile.as_dict()
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


def _infer_deployer_name_from_adapter(adapter):
    config = getattr(adapter, "config", None)
    adapter_name = getattr(config, "ADAPTER_NAME", None) if config is not None else None
    if adapter_name:
        return str(adapter_name).strip().lower()

    adapter_type_name = type(adapter).__name__.lower()
    if "edc" in adapter_type_name:
        return "edc"
    if "inesdata" in adapter_type_name:
        return "inesdata"
    return adapter_type_name


def _should_use_deployer_validate():
    if _env_flag("PIONERA_DISABLE_DEPLOYER_VALIDATE", default=False):
        return False

    raw_value = os.getenv("PIONERA_USE_DEPLOYER_VALIDATE")
    if raw_value is None:
        return True

    return _env_flag("PIONERA_USE_DEPLOYER_VALIDATE", default=True)


def _should_run_deployer_playwright(force=False, validation_profile=None):
    if _env_flag("PIONERA_DISABLE_DEPLOYER_PLAYWRIGHT", default=False):
        return False
    if force:
        return True
    if os.getenv("PIONERA_ENABLE_DEPLOYER_PLAYWRIGHT") is not None:
        return _env_flag("PIONERA_ENABLE_DEPLOYER_PLAYWRIGHT", default=False)
    return bool(getattr(validation_profile, "playwright_enabled", False))


def _should_run_test_data_cleanup(validation_profile=None):
    if _env_flag("PIONERA_DISABLE_TEST_DATA_CLEANUP", default=False):
        return False
    if os.getenv("PIONERA_TEST_DATA_CLEANUP") is not None:
        return _env_flag("PIONERA_TEST_DATA_CLEANUP", default=False)
    return bool(getattr(validation_profile, "test_data_cleanup_enabled", False))


def _test_data_cleanup_mode():
    return str(os.getenv("PIONERA_TEST_DATA_CLEANUP_MODE") or "safe").strip().lower() or "safe"


def _should_write_test_data_cleanup_report():
    return _env_flag("PIONERA_TEST_DATA_CLEANUP_REPORT", default=True)


def _append_public_endpoint(endpoints, seen, label, url):
    normalized_url = normalize_public_endpoint_url(url)
    if not normalized_url or normalized_url in seen:
        return
    seen.add(normalized_url)
    endpoints.append({"label": label, "url": normalized_url})


def _level6_public_endpoint_candidates(adapter, connectors, deployer_context):
    endpoints = []
    seen = set()
    config = dict(getattr(deployer_context, "config", {}) or {})
    ds_domain = str(getattr(deployer_context, "ds_domain_base", "") or "").strip()
    dataspace = str(getattr(deployer_context, "dataspace_name", "") or "").strip()

    _append_public_endpoint(endpoints, seen, "Keycloak admin", config.get("KC_URL"))
    _append_public_endpoint(endpoints, seen, "Keycloak public", config.get("KC_INTERNAL_URL"))
    _append_public_endpoint(endpoints, seen, "Keycloak hostname", config.get("KEYCLOAK_HOSTNAME"))
    _append_public_endpoint(endpoints, seen, "MinIO API", config.get("MINIO_HOSTNAME"))

    if dataspace and ds_domain:
        _append_public_endpoint(
            endpoints,
            seen,
            "Registration service",
            f"http://registration-service-{dataspace}.{ds_domain}",
        )

    connector_adapter = getattr(adapter, "connectors", None)
    connector_base_url = getattr(connector_adapter, "connector_base_url", None)
    build_connector_url = getattr(connector_adapter, "build_connector_url", None)
    for connector in connectors or []:
        url = None
        if callable(connector_base_url):
            try:
                url = connector_base_url(connector)
            except Exception:
                url = None
        if not url and callable(build_connector_url):
            try:
                url = build_connector_url(connector)
            except Exception:
                url = None
        _append_public_endpoint(endpoints, seen, f"Connector {connector}", url)

    return endpoints


def _ensure_level6_public_endpoint_access(adapter, connectors, deployer_context):
    if not _env_flag("PIONERA_LEVEL6_PUBLIC_ENDPOINT_PREFLIGHT", default=True):
        return {"status": "skipped", "reason": "disabled"}
    if deployer_context is None:
        return {"status": "skipped", "reason": "missing-deployer-context"}
    if getattr(adapter, "infrastructure", None) is None:
        return {"status": "skipped", "reason": "adapter-has-no-infrastructure-adapter"}

    topology = str(getattr(deployer_context, "topology", "local") or "local").strip().lower()
    endpoints = _level6_public_endpoint_candidates(adapter, connectors, deployer_context)
    if not endpoints:
        return {"status": "skipped", "reason": "no-public-endpoints"}

    print("\nVerifying public ingress hostnames...")
    result = ensure_public_endpoints_accessible(endpoints, topology=topology)
    print("Public ingress hostnames OK\n")
    return result


def _cleanup_failure_messages(cleanup_result):
    messages = []
    for connector in cleanup_result.get("connectors") or []:
        for error in connector.get("errors") or []:
            message = str(error.get("message") or "").strip()
            if message:
                messages.append(message)
        storage = connector.get("storage") or {}
        for error in storage.get("errors") or []:
            message = str(error.get("message") or "").strip()
            if message:
                messages.append(message)
    return messages


def _test_data_cleanup_failure_hint(cleanup_result):
    messages = _cleanup_failure_messages(cleanup_result)
    if not messages:
        return ""

    joined = "\n".join(messages)
    keycloak_credentials_mismatch = (
        "invalid_grant" in joined
        or "Invalid user credentials" in joined
        or "Token request" in joined and "HTTP 401" in joined
    )
    minio_credentials_mismatch = "InvalidAccessKeyId" in joined

    if keycloak_credentials_mismatch and minio_credentials_mismatch:
        return (
            " Local deployment artifacts are out of sync with the running dataspace "
            "credentials in Keycloak and MinIO. Run Level 4 again from this same checkout "
            "before Level 6, or run Level 6 from the checkout that deployed the current connectors."
        )
    if keycloak_credentials_mismatch:
        return (
            " Local connector credentials do not match Keycloak. Run Level 4 again from this "
            "same checkout before Level 6, or validate from the checkout that deployed the connectors."
        )
    if minio_credentials_mismatch:
        return (
            " Local connector storage credentials do not match MinIO. Run Level 4 again from this "
            "same checkout before Level 6, or validate from the checkout that deployed the connectors."
        )
    return ""


def _run_test_data_cleanup_if_enabled(adapter, connectors, deployer_context, experiment_dir, validation_profile=None):
    if not _should_run_test_data_cleanup(validation_profile=validation_profile):
        return {
            "status": "skipped",
            "reason": "disabled",
        }

    if deployer_context is None:
        return {
            "status": "skipped",
            "reason": "missing-deployer-context",
        }

    infrastructure = getattr(adapter, "infrastructure", None)
    ensure_local_access = getattr(infrastructure, "ensure_local_infra_access", None)
    if callable(ensure_local_access) and not ensure_local_access():
        raise RuntimeError(
            "Pre-validation test data cleanup failed. Local infrastructure access is not ready."
        )

    cleanup_result = run_pre_validation_cleanup(
        adapter=adapter,
        context=deployer_context,
        connectors=list(connectors or []),
        experiment_dir=experiment_dir,
        mode=_test_data_cleanup_mode(),
        report_enabled=_should_write_test_data_cleanup_report(),
    )
    if cleanup_result.get("status") == "failed":
        report_path = cleanup_result.get("report_path")
        hint = _test_data_cleanup_failure_hint(cleanup_result)
        detail = f" See {report_path} for details." if report_path else ""
        raise RuntimeError(f"Pre-validation test data cleanup failed.{hint}{detail}")
    return cleanup_result


def _legacy_validation_runtime(adapter):
    return {
        "connectors": _resolve_connectors(adapter),
        "validation_profile": None,
        "deployer_context": None,
        "deployer_name": None,
    }


def _should_use_deployer_metrics():
    if _env_flag("PIONERA_DISABLE_DEPLOYER_METRICS", default=False):
        return False

    raw_value = os.getenv("PIONERA_USE_DEPLOYER_METRICS")
    if raw_value is None:
        return True

    return _env_flag("PIONERA_USE_DEPLOYER_METRICS", default=True)


def _should_use_deployer_deploy():
    if _env_flag("PIONERA_DISABLE_DEPLOYER_DEPLOY", default=False):
        return False

    raw_value = os.getenv("PIONERA_USE_DEPLOYER_DEPLOY")
    if raw_value is None:
        return False

    return _env_flag("PIONERA_USE_DEPLOYER_DEPLOY", default=False)


def _should_sync_deployer_hosts():
    if _env_flag("PIONERA_DISABLE_HOSTS_SYNC", default=False):
        return False
    return _env_flag("PIONERA_SYNC_HOSTS", default=False)


def _deployer_hosts_address_override():
    value = str(os.getenv("PIONERA_HOSTS_ADDRESS") or "").strip()
    return value or None


def _deployer_hosts_default_address(context=None):
    override = _deployer_hosts_address_override()
    if override:
        return override

    topology_profile = getattr(context, "topology_profile", None)
    default_address = str(getattr(topology_profile, "default_address", "") or "").strip()
    return default_address or "127.0.0.1"


def _deployer_hosts_file():
    return str(os.getenv("PIONERA_HOSTS_FILE") or "").strip()


def _should_use_deployer_run():
    if _env_flag("PIONERA_DISABLE_DEPLOYER_RUN", default=False):
        return False

    raw_value = os.getenv("PIONERA_USE_DEPLOYER_RUN")
    if raw_value is None:
        return False

    return _env_flag("PIONERA_USE_DEPLOYER_RUN", default=False)


def _should_execute_deployer_deploy(deployer_name=None, topology="local"):
    if not _should_use_deployer_deploy():
        return False
    if not _env_flag("PIONERA_EXECUTE_DEPLOYER_DEPLOY", default=False):
        return False

    normalized_deployer = str(deployer_name or "").strip().lower()
    normalized_topology = str(topology or "local").strip().lower()
    return normalized_deployer == "edc" and normalized_topology == "local"


def _should_execute_deployer_run(deployer_name=None, topology="local"):
    if not _should_use_deployer_run():
        return False
    if not _env_flag("PIONERA_EXECUTE_DEPLOYER_RUN", default=False):
        return False

    normalized_deployer = str(deployer_name or "").strip().lower()
    normalized_topology = str(topology or "local").strip().lower()
    return normalized_deployer == "edc" and normalized_topology == "local"


def _legacy_metrics_runtime(adapter):
    return {
        "connectors": _resolve_connectors(adapter),
        "deployer_context": None,
        "deployer_name": None,
    }


def _resolve_validation_runtime(adapter, deployer_name=None, deployer_registry=None, topology="local"):
    if not _should_use_deployer_validate():
        return _legacy_validation_runtime(adapter)

    try:
        resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
        orchestrator = build_deployer_orchestrator(
            deployer_name=resolved_deployer_name,
            deployer_registry=deployer_registry,
            adapter=adapter,
            topology=topology,
        )
        context = orchestrator.resolve_context(topology=topology)
        profile = orchestrator.get_validation_profile(context)
        connectors = orchestrator.get_cluster_connectors(context)
        if not connectors:
            connectors = _resolve_connectors(adapter)
    except Exception:
        if _env_flag("PIONERA_REQUIRE_DEPLOYER_VALIDATE", default=False):
            raise
        return _legacy_validation_runtime(adapter)

    return {
        "connectors": connectors,
        "validation_profile": profile,
        "deployer_context": context,
        "deployer_name": resolved_deployer_name,
    }


def _resolve_metrics_runtime(adapter, deployer_name=None, deployer_registry=None, topology="local"):
    if not _should_use_deployer_metrics():
        return _legacy_metrics_runtime(adapter)

    try:
        resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
        orchestrator = build_deployer_orchestrator(
            deployer_name=resolved_deployer_name,
            deployer_registry=deployer_registry,
            adapter=adapter,
            topology=topology,
        )
        context = orchestrator.resolve_context(topology=topology)
        connectors = orchestrator.get_cluster_connectors(context)
        if not connectors:
            connectors = _resolve_connectors(adapter)
    except Exception:
        if _env_flag("PIONERA_REQUIRE_DEPLOYER_METRICS", default=False):
            raise
        return _legacy_metrics_runtime(adapter)

    return {
        "connectors": connectors,
        "deployer_context": context,
        "deployer_name": resolved_deployer_name,
    }


def _resolve_deployer_context(adapter, deployer_name=None, deployer_registry=None, topology="local"):
    resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
    orchestrator = build_deployer_orchestrator(
        deployer_name=resolved_deployer_name,
        deployer_registry=deployer_registry,
        adapter=adapter,
        topology=topology,
    )
    return resolved_deployer_name, orchestrator.resolve_context(topology=topology)


def _build_shadow_host_sync_plan(context):
    address_override = _deployer_hosts_address_override()
    blocks = build_context_host_blocks(context, address=address_override)
    levels = hostnames_by_level(blocks)
    topology_profile = getattr(context, "topology_profile", None)
    return {
        "status": "planned",
        "hosts_file": _deployer_hosts_file() or None,
        "address": _deployer_hosts_default_address(context),
        "address_override": address_override,
        "topology_profile": (
            topology_profile.as_dict()
            if hasattr(topology_profile, "as_dict")
            else None
        ),
        "blocks": blocks_as_dict(blocks),
        "level_1_2": levels["level_1_2"],
        "level_3": levels["level_3"],
        "level_4": levels["level_4"],
        "level_5": levels["level_5"],
    }


def _sync_deployer_hosts_if_enabled(context):
    plan = _build_shadow_host_sync_plan(context)
    if not _should_sync_deployer_hosts():
        return {
            "status": "skipped",
            "reason": "disabled",
            "plan": plan,
        }

    hosts_file = _deployer_hosts_file()
    if not hosts_file:
        raise RuntimeError(
            "PIONERA_SYNC_HOSTS=true requires PIONERA_HOSTS_FILE to point to the hosts file to update. "
            "For Windows from WSL this is usually /mnt/c/Windows/System32/drivers/etc/hosts."
        )

    blocks = build_context_host_blocks(context, address=_deployer_hosts_address_override())
    result = apply_managed_blocks(hosts_file, blocks)
    return {
        "status": "updated" if result["changed"] else "unchanged",
        "hosts_file": result["hosts_file"],
        "changed": result["changed"],
        "blocks": result["blocks"],
        "skipped_existing": result.get("skipped_existing", {}),
    }


def _resolve_shadow_deploy_preflight(adapter):
    preview = _resolve_adapter_preview(adapter, "deploy")
    if isinstance(preview, dict):
        return _sanitize_preview_data(preview)
    return None


def _build_shadow_level_plan(context, preflight=None):
    components = list(getattr(context, "components", []) or [])
    level_plan = {
        "level_1_2": {
            "action": "deploy_infrastructure",
            "namespace_roles": ["common_services_namespace"],
            "status": "planned",
            "details": None,
        },
        "level_3": {
            "action": "deploy_dataspace",
            "namespace_roles": [
                "registration_service_namespace",
                "provider_namespace",
                "consumer_namespace",
            ],
            "status": "planned",
            "details": None,
        },
        "level_4": {
            "action": "deploy_connectors",
            "namespace_roles": ["provider_namespace", "consumer_namespace"],
            "status": "planned",
            "details": None,
        },
        "level_5": {
            "action": "deploy_components",
            "namespace_roles": ["components_namespace"],
            "status": "planned" if components else "not-applicable",
            "details": {"components": components} if components else {"components": []},
        },
    }

    if not isinstance(preflight, dict):
        return level_plan

    shared_common_services = preflight.get("shared_common_services")
    if isinstance(shared_common_services, dict):
        level_plan["level_1_2"]["status"] = shared_common_services.get("status", "planned")
        level_plan["level_1_2"]["details"] = shared_common_services

    shared_dataspace = preflight.get("shared_dataspace")
    if isinstance(shared_dataspace, dict):
        level_plan["level_3"]["status"] = shared_dataspace.get("status", "planned")
        level_plan["level_3"]["details"] = shared_dataspace

    connectors = preflight.get("connectors")
    if isinstance(connectors, dict):
        level_plan["level_4"]["status"] = connectors.get("status", "planned")
        level_plan["level_4"]["details"] = connectors

    if isinstance(preflight.get("components"), dict):
        component_preview = preflight["components"]
        level_plan["level_5"]["status"] = component_preview.get("status", level_plan["level_5"]["status"])
        level_plan["level_5"]["details"] = component_preview

    if isinstance(preflight.get("status"), str):
        overall_status = preflight["status"]
        if overall_status == "ready" and not components and level_plan["level_5"]["status"] == "not-applicable":
            level_plan["level_5"]["details"] = {"components": []}

    return level_plan


def _build_deployer_deploy_shadow_plan(adapter, deployer_name=None, deployer_registry=None, topology="local"):
    resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
    orchestrator = build_deployer_orchestrator(
        deployer_name=resolved_deployer_name,
        deployer_registry=deployer_registry,
        adapter=adapter,
        topology=topology,
    )
    context = orchestrator.resolve_context(topology=topology)
    profile = orchestrator.get_validation_profile(context)
    preflight = _resolve_shadow_deploy_preflight(adapter)

    return {
        "mode": "shadow",
        "status": "planned",
        "deployer_name": resolved_deployer_name,
        "topology": topology,
        "actions": [
            "resolve_context",
            "plan_infrastructure",
            "plan_dataspace",
            "plan_connectors",
            "plan_components",
            "plan_validation_after_deploy",
        ],
        "namespace_roles": context.namespace_roles.as_dict(),
        "deployer_context": _sanitize_preview_data(context.as_dict()),
        "hosts_plan": _build_shadow_host_sync_plan(context),
        "level_plan": _build_shadow_level_plan(context, preflight=preflight),
        "preflight": preflight,
        "validation_profile": profile.as_dict(),
    }


def _edc_local_connector_image_defaults():
    return {
        "name": os.getenv("PIONERA_EDC_LOCAL_CONNECTOR_IMAGE_NAME", "validation-environment/edc-connector"),
        "tag": os.getenv("PIONERA_EDC_LOCAL_CONNECTOR_IMAGE_TAG", "local"),
    }


def _edc_local_dashboard_image_defaults(config, adapter):
    config_cls = getattr(adapter, "config", None)
    return {
        "dashboard_name": str(
            config.get("EDC_DASHBOARD_IMAGE_NAME")
            or os.getenv("PIONERA_EDC_DASHBOARD_IMAGE_NAME")
            or getattr(config_cls, "EDC_DASHBOARD_IMAGE_NAME", "validation-environment/edc-dashboard")
            or ""
        ).strip(),
        "dashboard_tag": str(
            config.get("EDC_DASHBOARD_IMAGE_TAG")
            or os.getenv("PIONERA_EDC_DASHBOARD_IMAGE_TAG")
            or getattr(config_cls, "EDC_DASHBOARD_IMAGE_TAG", "latest")
            or ""
        ).strip(),
        "proxy_name": str(
            config.get("EDC_DASHBOARD_PROXY_IMAGE_NAME")
            or os.getenv("PIONERA_EDC_DASHBOARD_PROXY_IMAGE_NAME")
            or getattr(config_cls, "EDC_DASHBOARD_PROXY_IMAGE_NAME", "validation-environment/edc-dashboard-proxy")
            or ""
        ).strip(),
        "proxy_tag": str(
            config.get("EDC_DASHBOARD_PROXY_IMAGE_TAG")
            or os.getenv("PIONERA_EDC_DASHBOARD_PROXY_IMAGE_TAG")
            or getattr(config_cls, "EDC_DASHBOARD_PROXY_IMAGE_TAG", "latest")
            or ""
        ).strip(),
    }


def _edc_local_minikube_profile(adapter):
    env_profile = os.getenv("PIONERA_MINIKUBE_PROFILE") or os.getenv("MINIKUBE_PROFILE")
    if env_profile:
        return env_profile.strip() or "minikube"

    config_adapter = getattr(adapter, "config_adapter", None)
    config_loader = getattr(config_adapter, "load_deployer_config", None)
    config = dict(config_loader() or {}) if callable(config_loader) else {}
    return str(config.get("MINIKUBE_PROFILE") or "minikube").strip() or "minikube"


def _prepare_edc_local_connector_image_override(adapter):
    if _env_flag("PIONERA_SKIP_EDC_LOCAL_CONNECTOR_IMAGE_BUILD", default=False):
        raise RuntimeError(
            "EDC Level 4 local execution needs a connector image, but automatic local image "
            "preparation was disabled with PIONERA_SKIP_EDC_LOCAL_CONNECTOR_IMAGE_BUILD=true."
        )

    image = _edc_local_connector_image_defaults()
    image_name = str(image["name"] or "").strip()
    image_tag = str(image["tag"] or "").strip()
    if not image_name or not image_tag:
        raise RuntimeError(
            "EDC local connector image defaults are invalid. Set "
            "PIONERA_EDC_LOCAL_CONNECTOR_IMAGE_NAME and PIONERA_EDC_LOCAL_CONNECTOR_IMAGE_TAG."
        )

    root_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(root_dir, "adapters", "edc", "scripts", "build_image.sh")
    if not os.path.isfile(script_path):
        raise RuntimeError(f"EDC connector image build script not found: {script_path}")

    minikube_profile = _edc_local_minikube_profile(adapter)
    command = [
        "bash",
        script_path,
        "--apply",
        "--image",
        image_name,
        "--tag",
        image_tag,
        "--minikube-profile",
        minikube_profile,
    ]

    print(
        "EDC connector image overrides are not configured. "
        f"Preparing local image automatically: {image_name}:{image_tag}"
    )
    result = subprocess.run(command, cwd=root_dir, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "Automatic EDC connector image preparation failed. "
            f"Command returned exit code {result.returncode}: {' '.join(command)}"
        )

    os.environ["PIONERA_EDC_CONNECTOR_IMAGE_NAME"] = image_name
    os.environ["PIONERA_EDC_CONNECTOR_IMAGE_TAG"] = image_tag
    os.environ.setdefault("PIONERA_EDC_CONNECTOR_IMAGE_PULL_POLICY", "IfNotPresent")
    return {
        "image_name": image_name,
        "image_tag": image_tag,
        "minikube_profile": minikube_profile,
    }


def _run_edc_local_image_script(script_path, minikube_profile, env):
    root_dir = os.path.dirname(os.path.abspath(__file__))
    command = [
        "bash",
        script_path,
        "--apply",
        "--minikube-profile",
        minikube_profile,
    ]
    result = subprocess.run(command, cwd=root_dir, check=False, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            "Automatic EDC local image preparation failed. "
            f"Command returned exit code {result.returncode}: {' '.join(command)}"
        )


def _prepare_edc_local_dashboard_images(adapter, config):
    if not _mapping_flag(config, "EDC_DASHBOARD_ENABLED", default=False):
        return {"status": "skipped", "reason": "dashboard-disabled"}

    if _env_flag("PIONERA_SKIP_EDC_LOCAL_DASHBOARD_IMAGE_BUILD", default=False):
        return {"status": "skipped", "reason": "disabled-by-env"}

    images = _edc_local_dashboard_image_defaults(config, adapter)
    missing = [key for key, value in images.items() if not value]
    if missing:
        raise RuntimeError(
            "EDC dashboard local image defaults are invalid. Missing: "
            + ", ".join(sorted(missing))
        )

    root_dir = os.path.dirname(os.path.abspath(__file__))
    dashboard_script = os.path.join(root_dir, "adapters", "edc", "scripts", "build_dashboard_image.sh")
    proxy_script = os.path.join(root_dir, "adapters", "edc", "scripts", "build_dashboard_proxy_image.sh")
    for script_path in (dashboard_script, proxy_script):
        if not os.path.isfile(script_path):
            raise RuntimeError(f"EDC dashboard image build script not found: {script_path}")

    minikube_profile = _edc_local_minikube_profile(adapter)
    env = dict(os.environ)
    env["PIONERA_EDC_DASHBOARD_IMAGE_NAME"] = images["dashboard_name"]
    env["PIONERA_EDC_DASHBOARD_IMAGE_TAG"] = images["dashboard_tag"]
    env["PIONERA_EDC_DASHBOARD_PROXY_IMAGE_NAME"] = images["proxy_name"]
    env["PIONERA_EDC_DASHBOARD_PROXY_IMAGE_TAG"] = images["proxy_tag"]

    print(
        "EDC dashboard is enabled. Preparing local dashboard images automatically: "
        f"{images['dashboard_name']}:{images['dashboard_tag']} and "
        f"{images['proxy_name']}:{images['proxy_tag']}"
    )
    _run_edc_local_image_script(dashboard_script, minikube_profile, env)
    _run_edc_local_image_script(proxy_script, minikube_profile, env)

    os.environ["PIONERA_EDC_DASHBOARD_IMAGE_NAME"] = images["dashboard_name"]
    os.environ["PIONERA_EDC_DASHBOARD_IMAGE_TAG"] = images["dashboard_tag"]
    os.environ["PIONERA_EDC_DASHBOARD_PROXY_IMAGE_NAME"] = images["proxy_name"]
    os.environ["PIONERA_EDC_DASHBOARD_PROXY_IMAGE_TAG"] = images["proxy_tag"]
    os.environ.setdefault("PIONERA_EDC_DASHBOARD_IMAGE_PULL_POLICY", "IfNotPresent")
    os.environ.setdefault("PIONERA_EDC_DASHBOARD_PROXY_IMAGE_PULL_POLICY", "IfNotPresent")
    return {
        "status": "prepared",
        "dashboard_image": f"{images['dashboard_name']}:{images['dashboard_tag']}",
        "dashboard_proxy_image": f"{images['proxy_name']}:{images['proxy_tag']}",
        "minikube_profile": minikube_profile,
    }


def _ensure_safe_edc_deployer_execution(adapter, deployer_name=None, topology="local"):
    normalized_deployer = str(deployer_name or _infer_deployer_name_from_adapter(adapter)).strip().lower()
    if normalized_deployer != "edc":
        return

    config_adapter = getattr(adapter, "config_adapter", None)
    config_loader = getattr(config_adapter, "load_deployer_config", None)
    config = dict(config_loader() or {}) if callable(config_loader) else {}
    normalized_topology = str(topology or "local").strip().lower()

    dataspace_name = ""
    primary_dataspace_name = getattr(config_adapter, "primary_dataspace_name", None)
    if callable(primary_dataspace_name):
        dataspace_name = str(primary_dataspace_name() or "").strip()
    if not dataspace_name:
        dataspace_name = str(
            config.get("DS_1_NAME")
            or os.getenv("PIONERA_DS_1_NAME")
            or ""
        ).strip()

    shared_dataspaces = {"demo"}
    allow_shared_dataspace = str(
        os.getenv("PIONERA_ALLOW_SHARED_EDC_DEPLOY", "false")
    ).strip().lower() in {"1", "true", "yes", "on"}

    if dataspace_name.lower() in shared_dataspaces and not allow_shared_dataspace:
        raise RuntimeError(
            "Real deployer execution for EDC refuses to target the shared dataspace "
            f"'{dataspace_name}'. Use an isolated dataspace such as 'demoedc' or set "
            "PIONERA_ALLOW_SHARED_EDC_DEPLOY=true to bypass this protection explicitly."
        )

    explicit_image_name = str(
        config.get("EDC_CONNECTOR_IMAGE_NAME")
        or os.getenv("PIONERA_EDC_CONNECTOR_IMAGE_NAME")
        or ""
    ).strip()
    explicit_image_tag = str(
        config.get("EDC_CONNECTOR_IMAGE_TAG")
        or os.getenv("PIONERA_EDC_CONNECTOR_IMAGE_TAG")
        or ""
    ).strip()

    config_cls = getattr(adapter, "config", None)
    default_image_name = str(
        getattr(config_cls, "EDC_CONNECTOR_IMAGE_NAME", "ghcr.io/proyectopionera/edc-connector") or ""
    ).strip()
    default_image_tag = str(
        getattr(config_cls, "EDC_CONNECTOR_IMAGE_TAG", "latest") or ""
    ).strip()

    if not explicit_image_name or not explicit_image_tag:
        if normalized_topology == "local" and not explicit_image_name and not explicit_image_tag:
            prepared = _prepare_edc_local_connector_image_override(adapter)
            explicit_image_name = prepared["image_name"]
            explicit_image_tag = prepared["image_tag"]
        else:
            raise RuntimeError(
                "Real deployer execution for EDC requires explicit EDC connector image overrides. "
                "Set PIONERA_EDC_CONNECTOR_IMAGE_NAME and PIONERA_EDC_CONNECTOR_IMAGE_TAG first."
            )

    if not explicit_image_name or not explicit_image_tag:
        raise RuntimeError(
            "Real deployer execution for EDC requires explicit EDC connector image overrides. "
            "Set PIONERA_EDC_CONNECTOR_IMAGE_NAME and PIONERA_EDC_CONNECTOR_IMAGE_TAG first."
        )

    if explicit_image_name == default_image_name and explicit_image_tag == default_image_tag:
        raise RuntimeError(
            "Real deployer execution for EDC refuses to use the default connector image "
            f"'{default_image_name}:{default_image_tag}'. Provide an explicit working image override."
        )

    if normalized_topology == "local":
        _prepare_edc_local_dashboard_images(adapter, config)


def _execute_deployer_deploy(adapter, deployer_name=None, deployer_registry=None, topology="local"):
    resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
    _ensure_safe_edc_deployer_execution(adapter, deployer_name=resolved_deployer_name, topology=topology)
    orchestrator = build_deployer_orchestrator(
        deployer_name=resolved_deployer_name,
        deployer_registry=deployer_registry,
        adapter=adapter,
        topology=topology,
    )
    deployment = orchestrator.deploy(topology=topology)
    context = deployment["context"]
    profile = orchestrator.get_validation_profile(context)
    hosts_sync = _sync_deployer_hosts_if_enabled(context)

    return {
        "mode": "execute",
        "status": "completed",
        "deployer_name": resolved_deployer_name,
        "topology": topology,
        "namespace_roles": context.namespace_roles.as_dict(),
        "deployer_context": _sanitize_preview_data(context.as_dict()),
        "hosts_sync": hosts_sync,
        "deployment": {
            "infrastructure": deployment.get("infrastructure"),
            "dataspace": deployment.get("dataspace"),
            "connectors": deployment.get("connectors"),
            "components": deployment.get("components"),
        },
        "validation_profile": profile.as_dict(),
    }


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


def run_hosts(adapter, deployer_name=None, deployer_registry=None, topology="local"):
    """Plan or apply local hosts entries for the selected deployer context."""
    resolved_deployer_name, context = _resolve_deployer_context(
        adapter,
        deployer_name=deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )
    plan = _build_shadow_host_sync_plan(context)
    sync = _sync_deployer_hosts_if_enabled(context)
    return {
        "status": sync.get("status", "planned"),
        "deployer_name": resolved_deployer_name,
        "topology": topology,
        "dataspace": getattr(context, "dataspace_name", None),
        "hosts_plan": plan,
        "hosts_sync": sync,
    }


def _build_recreate_dataspace_plan(adapter, context):
    plan_getter = _resolve_adapter_callable(
        adapter,
        "build_recreate_dataspace_plan",
        "deployment.build_recreate_dataspace_plan",
    )
    adapter_plan = dict(plan_getter() or {}) if callable(plan_getter) else {}
    namespace_roles = getattr(context, "namespace_roles", None)
    namespace = getattr(namespace_roles, "registration_service_namespace", "") if namespace_roles else ""
    dataspace_name = getattr(context, "dataspace_name", "") or adapter_plan.get("dataspace")
    adapter_plan.setdefault("status", "planned")
    adapter_plan.setdefault("dataspace", dataspace_name)
    adapter_plan.setdefault("namespace", namespace or dataspace_name)
    adapter_plan.setdefault("runtime_dir", getattr(context, "runtime_dir", ""))
    adapter_plan.setdefault("preserves_shared_services", True)
    adapter_plan.setdefault("invalidates_level_4_connectors", True)
    adapter_plan.setdefault(
        "actions",
        [
            "uninstall_dataspace_helm_releases",
            "delete_dataspace_namespace",
            "delete_dataspace_bootstrap_state",
            "remove_generated_runtime_artifacts",
            "run_level_3_again",
        ],
    )
    adapter_plan["deployer_context"] = _sanitize_preview_data(context.as_dict())
    return adapter_plan


def run_recreate_dataspace(
    adapter,
    deployer_name=None,
    deployer_registry=None,
    topology="local",
    confirm_dataspace=None,
    with_connectors=False,
):
    """Recreate only the selected dataspace after exact-name confirmation."""
    resolved_deployer_name, context = _resolve_deployer_context(
        adapter,
        deployer_name=deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )
    plan = _build_recreate_dataspace_plan(adapter, context)
    dataspace_name = str(plan.get("dataspace") or "").strip()
    confirmation = str(confirm_dataspace or os.getenv("PIONERA_RECREATE_DATASPACE_CONFIRM") or "").strip()
    if confirmation != dataspace_name:
        raise RuntimeError(
            "Dataspace recreation is destructive and requires exact confirmation. "
            f"Provide --confirm-dataspace {dataspace_name}."
        )

    recreate = _resolve_adapter_callable(adapter, "recreate_dataspace", "deployment.recreate_dataspace")
    if not callable(recreate):
        raise RuntimeError(f"Adapter '{resolved_deployer_name}' does not expose recreate_dataspace()")

    with _temporary_adapter_auto_mode(adapter, enabled=True):
        result = recreate(confirm_dataspace=confirmation)
        connector_result = None
        next_step = "Run Level 4 again for this adapter because recreated Level 3 invalidates existing connectors."

        if with_connectors:
            try:
                connector_result = run_level(
                    adapter,
                    4,
                    deployer_name=resolved_deployer_name,
                    deployer_registry=deployer_registry,
                    topology=topology,
                )
                next_step = "Run Level 6 to validate the recreated dataspace and connectors."
            except Exception as exc:
                raise RuntimeError(
                    "Dataspace was recreated, but automatic Level 4 connector recreation failed. "
                    "Fix the Level 4 issue and run Level 4 manually for this adapter."
                ) from exc

    return {
        "status": "completed",
        "deployer_name": resolved_deployer_name,
        "topology": topology,
        "dataspace": dataspace_name,
        "plan": plan,
        "result": result,
        "with_connectors": bool(with_connectors),
        "connectors": connector_result,
        "next_step": next_step,
    }


def run_deploy(adapter, deployer_name=None, deployer_registry=None, topology="local"):
    """Deploy infrastructure and connectors using the selected adapter."""
    if _should_use_deployer_deploy() or str(topology or "local").strip().lower() != "local":
        if _should_execute_deployer_deploy(deployer_name=deployer_name, topology=topology):
            return _execute_deployer_deploy(
                adapter,
                deployer_name=deployer_name,
                deployer_registry=deployer_registry,
                topology=topology,
            )
        return _build_deployer_deploy_shadow_plan(
            adapter,
            deployer_name=deployer_name,
            deployer_registry=deployer_registry,
            topology=topology,
        )

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
    deployer_name=None,
    deployer_registry=None,
    topology="local",
    validation_engine_cls=ValidationEngine,
    experiment_storage=ExperimentStorage,
    experiment_dir=None,
    save_metadata=True,
    baseline=False,
    force_playwright=False,
    kafka_edc_validation_suite_cls=KafkaEdcValidationSuite,
    kafka_manager_cls=KafkaManager,
):
    """Run validation collections with the selected adapter."""
    validation_runtime = _resolve_validation_runtime(
        adapter,
        deployer_name=deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )
    connectors = validation_runtime["connectors"]
    validation_profile = validation_runtime["validation_profile"]
    deployer_context = validation_runtime["deployer_context"]
    hosts_sync = (
        _sync_deployer_hosts_if_enabled(deployer_context)
        if deployer_context is not None
        else {"status": "skipped", "reason": "missing-deployer-context"}
    )
    experiment_dir = experiment_dir or experiment_storage.create_experiment_directory()
    if save_metadata:
        _save_experiment_metadata(
            experiment_storage,
            experiment_dir,
            connectors,
            adapter=type(adapter).__name__,
            baseline=baseline,
        )
    experiment_storage.newman_reports_dir(experiment_dir)
    public_endpoint_preflight = _ensure_level6_public_endpoint_access(
        adapter,
        connectors,
        deployer_context,
    )
    test_data_cleanup = _run_test_data_cleanup_if_enabled(
        adapter,
        connectors,
        deployer_context,
        experiment_dir,
        validation_profile=validation_profile,
    )

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

    kafka_edc_results = run_level6_kafka_edc_after_newman(
        adapter,
        connectors,
        experiment_dir,
        validation_profile=validation_profile,
        deployer_name=validation_runtime.get("deployer_name") or deployer_name,
        experiment_storage=experiment_storage,
        suite_cls=kafka_edc_validation_suite_cls,
        kafka_manager_cls=kafka_manager_cls,
    )

    playwright_result = None
    if validation_profile is not None:
        if not getattr(validation_profile, "playwright_enabled", False):
            playwright_result = {
                "status": "skipped",
                "reason": "disabled-in-profile",
            }
        elif deployer_context is None:
            playwright_result = {
                "status": "skipped",
                "reason": "missing-deployer-context",
            }
        elif not _should_run_deployer_playwright(force=force_playwright, validation_profile=validation_profile):
            playwright_result = {
                "status": "skipped",
                "reason": "disabled",
            }
        else:
            is_edc_playwright = getattr(validation_profile, "adapter", "").strip().lower() == "edc"
            dashboard_runtime_present = _edc_dashboard_runtime_present(deployer_context) if is_edc_playwright else False
            if (
                is_edc_playwright
                and not (
                    _mapping_flag(getattr(deployer_context, "config", {}), "EDC_DASHBOARD_ENABLED", default=False)
                    or dashboard_runtime_present
                )
            ):
                raise RuntimeError(
                    "Playwright validation for 'edc' requires EDC_DASHBOARD_ENABLED=true and a deployed dashboard runtime"
                )
            edc_dashboard_auth_mode = str(
                getattr(deployer_context, "config", {}).get(
                    "EDC_DASHBOARD_PROXY_AUTH_MODE",
                    "",
                )
            ).strip().lower()
            if (
                is_edc_playwright
                and edc_dashboard_auth_mode != "oidc-bff"
            ):
                runtime_auth_mode = _edc_dashboard_runtime_auth_mode(deployer_context)
                if runtime_auth_mode:
                    edc_dashboard_auth_mode = runtime_auth_mode
                if edc_dashboard_auth_mode != "oidc-bff":
                    raise RuntimeError(
                        "Playwright validation for 'edc' requires EDC_DASHBOARD_PROXY_AUTH_MODE=oidc-bff"
                    )
            if not getattr(validation_profile, "playwright_config", None):
                raise RuntimeError(
                    "Validation profile enables Playwright but does not define a playwright_config"
                )
            if is_edc_playwright:
                readiness = _wait_for_edc_dashboard_readiness(
                    deployer_context,
                    experiment_dir=experiment_dir,
                )
                if readiness.get("status") != "passed":
                    raise RuntimeError(_edc_dashboard_readiness_failure_message(readiness))
            playwright_result = run_playwright_validation(
                profile=validation_profile,
                context=deployer_context,
                experiment_dir=experiment_dir,
            )
            if playwright_result.get("status") != "passed":
                raise RuntimeError(
                    f"Playwright validation failed with status '{playwright_result.get('status')}'"
                )

    return {
        "experiment_dir": experiment_dir,
        "validation": validation_result,
        "newman_request_metrics": newman_request_metrics,
        "kafka_edc_results": kafka_edc_results,
        "storage_checks": list(getattr(validation_engine, "last_storage_checks", []) or []),
        "playwright": playwright_result,
        "test_data_cleanup": test_data_cleanup,
        "public_endpoint_preflight": public_endpoint_preflight,
        "hosts_sync": hosts_sync,
        "validation_profile": (
            validation_profile.as_dict()
            if validation_profile is not None
            else None
        ),
        "deployer_context": (
            _sanitize_preview_data(deployer_context.as_dict())
            if deployer_context is not None
            else None
        ),
    }


def run_metrics(
    adapter,
    deployer_name=None,
    deployer_registry=None,
    topology="local",
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    experiment_dir=None,
    save_metadata=True,
    kafka_enabled=False,
    kafka_runtime_config=None,
    kafka_manager_cls=KafkaManager,
    baseline=False,
):
    """Run metrics collection with the selected adapter."""
    metrics_runtime = _resolve_metrics_runtime(
        adapter,
        deployer_name=deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )
    connectors = metrics_runtime["connectors"]
    hosts_sync = (
        _sync_deployer_hosts_if_enabled(metrics_runtime["deployer_context"])
        if metrics_runtime["deployer_context"] is not None
        else {"status": "skipped", "reason": "missing-deployer-context"}
    )
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
    experiment_dir = experiment_dir or experiment_storage.create_experiment_directory()
    if save_metadata:
        _save_experiment_metadata(
            experiment_storage,
            experiment_dir,
            connectors,
            adapter=type(adapter).__name__,
            baseline=baseline,
        )
    metrics = metrics_collector.collect(connectors, experiment_dir=experiment_dir)
    sanitized_deployer_context = (
        _sanitize_preview_data(metrics_runtime["deployer_context"].as_dict())
        if metrics_runtime["deployer_context"] is not None
        else None
    )

    if isinstance(metrics, dict):
        metrics = dict(metrics)
        metrics.setdefault("deployer_context", sanitized_deployer_context)

    def _build_metrics_result(kafka_metrics_value=None):
        payload = {
            "experiment_dir": experiment_dir,
            "connectors": list(connectors),
            "metrics": metrics,
            "kafka_metrics": kafka_metrics_value,
            "deployer_context": sanitized_deployer_context,
            "hosts_sync": hosts_sync,
        }
        if isinstance(metrics, dict):
            payload.update(metrics)
            payload.setdefault("experiment_dir", experiment_dir)
            payload.setdefault("connectors", list(connectors))
            payload.setdefault("deployer_context", sanitized_deployer_context)
            payload.setdefault("hosts_sync", hosts_sync)
            payload["metrics"] = metrics
            payload["kafka_metrics"] = kafka_metrics_value
        return payload

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
                return _build_metrics_result(kafka_metrics)
        finally:
            if kafka_manager is not None:
                kafka_manager.stop_kafka()

    return _build_metrics_result(kafka_metrics)


def _build_deployer_run_shadow_plan(
    adapter,
    deployer_name=None,
    deployer_registry=None,
    topology="local",
):
    resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
    deploy_plan = _build_deployer_deploy_shadow_plan(
        adapter,
        deployer_name=resolved_deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )
    validation_runtime = _resolve_validation_runtime(
        adapter,
        deployer_name=resolved_deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )
    metrics_runtime = _resolve_metrics_runtime(
        adapter,
        deployer_name=resolved_deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )

    return {
        "mode": "shadow",
        "operation": "run",
        "status": "planned",
        "deployer_name": resolved_deployer_name,
        "topology": topology,
        "sequence": [
            "deploy",
            "validate",
            "metrics",
        ],
        "deploy": deploy_plan,
        "validate": {
            "connectors": list(validation_runtime["connectors"] or []),
            "validation_profile": (
                validation_runtime["validation_profile"].as_dict()
                if validation_runtime["validation_profile"] is not None
                else None
            ),
            "deployer_context": (
                _sanitize_preview_data(validation_runtime["deployer_context"].as_dict())
                if validation_runtime["deployer_context"] is not None
                else None
            ),
        },
        "metrics": {
            "connectors": list(metrics_runtime["connectors"] or []),
            "deployer_context": (
                _sanitize_preview_data(metrics_runtime["deployer_context"].as_dict())
                if metrics_runtime["deployer_context"] is not None
                else None
            ),
        },
    }


def run_run(
    adapter,
    deployer_name=None,
    deployer_registry=None,
    topology="local",
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_enabled=False,
    kafka_runtime_config=None,
    kafka_manager_cls=KafkaManager,
    baseline=False,
):
    """Run the experimental deployer-backed deploy+validate+metrics chain."""
    resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
    if _should_execute_deployer_run(deployer_name=resolved_deployer_name, topology=topology):
        environment_overrides = {}
        if resolved_deployer_name == "edc" and os.getenv("PIONERA_EDC_DASHBOARD_ENABLED") is None:
            environment_overrides["PIONERA_EDC_DASHBOARD_ENABLED"] = "true"
        if (
            resolved_deployer_name == "edc"
            and not os.getenv("PIONERA_EDC_DASHBOARD_PROXY_AUTH_MODE")
        ):
            environment_overrides["PIONERA_EDC_DASHBOARD_PROXY_AUTH_MODE"] = "oidc-bff"

        with _temporary_environment(environment_overrides):
            deployment = _execute_deployer_deploy(
                adapter,
                deployer_name=resolved_deployer_name,
                deployer_registry=deployer_registry,
                topology=topology,
            )
            shared_experiment_dir = experiment_storage.create_experiment_directory()
            _save_experiment_metadata(
                experiment_storage,
                shared_experiment_dir,
                deployment["deployment"]["connectors"],
                adapter=type(adapter).__name__,
                baseline=baseline,
            )
            validation = run_validate(
                adapter,
                deployer_name=resolved_deployer_name,
                deployer_registry=deployer_registry,
                topology=topology,
                validation_engine_cls=validation_engine_cls,
                experiment_storage=experiment_storage,
                experiment_dir=shared_experiment_dir,
                save_metadata=False,
                baseline=baseline,
            )
            metrics = run_metrics(
                adapter,
                deployer_name=resolved_deployer_name,
                deployer_registry=deployer_registry,
                topology=topology,
                metrics_collector_cls=metrics_collector_cls,
                experiment_storage=experiment_storage,
                experiment_dir=shared_experiment_dir,
                save_metadata=False,
                kafka_enabled=kafka_enabled,
                kafka_runtime_config=kafka_runtime_config,
                kafka_manager_cls=kafka_manager_cls,
                baseline=baseline,
            )
        return {
            "mode": "execute",
            "operation": "run",
            "status": "completed",
            "deployer_name": resolved_deployer_name,
            "topology": topology,
            "experiment_dir": shared_experiment_dir,
            "sequence": [
                "deploy",
                "validate",
                "metrics",
            ],
            "namespace_roles": deployment["namespace_roles"],
            "deployer_context": deployment["deployer_context"],
            "hosts_sync": deployment.get("hosts_sync"),
            "deployment": deployment["deployment"],
            "validation": validation,
            "metrics": metrics,
            "validation_profile": deployment["validation_profile"],
        }

    return _build_deployer_run_shadow_plan(
        adapter,
        deployer_name=resolved_deployer_name,
        deployer_registry=deployer_registry,
        topology=topology,
    )


def run_level(
    adapter,
    level,
    deployer_name=None,
    deployer_registry=None,
    topology="local",
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    baseline=False,
):
    """Run one numbered level using the selected adapter/deployer context."""
    try:
        level_id = int(level)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid level: {level}") from exc

    if level_id not in LEVEL_DESCRIPTIONS:
        supported = ", ".join(str(value) for value in sorted(LEVEL_DESCRIPTIONS))
        raise ValueError(f"Unsupported level '{level_id}'. Supported levels: {supported}")

    resolved_deployer_name = deployer_name or _infer_deployer_name_from_adapter(adapter)
    level_name = LEVEL_DESCRIPTIONS[level_id]
    normalized_topology = str(topology or "local").strip().lower()
    if normalized_topology != "local" and level_id in {1, 2, 3, 4, 5}:
        raise RuntimeError(
            f"Real Level {level_id} execution is not enabled for topology '{normalized_topology}' yet. "
            "Use the deployer dry-run/hosts plan first, then enable VM execution once the topology-specific "
            "deployment path is implemented."
        )

    if level_id == 1:
        setup_cluster = _resolve_adapter_callable(adapter, "setup_cluster")
        if not callable(setup_cluster):
            raise RuntimeError(f"Adapter '{resolved_deployer_name}' does not expose Level 1 setup_cluster()")
        result = setup_cluster()
    elif level_id == 2:
        deploy_infrastructure = _resolve_adapter_callable(adapter, "deploy_infrastructure")
        if not callable(deploy_infrastructure):
            raise RuntimeError(f"Adapter '{resolved_deployer_name}' does not expose Level 2 deploy_infrastructure()")
        result = deploy_infrastructure()
    elif level_id == 3:
        deploy_dataspace = _resolve_adapter_callable(adapter, "deploy_dataspace")
        if not callable(deploy_dataspace):
            raise RuntimeError(f"Adapter '{resolved_deployer_name}' does not expose Level 3 deploy_dataspace()")
        result = deploy_dataspace()
    elif level_id == 4:
        if resolved_deployer_name == "edc":
            _ensure_safe_edc_deployer_execution(
                adapter,
                deployer_name=resolved_deployer_name,
                topology=topology,
            )
        deploy_connectors = _resolve_adapter_callable(adapter, "deploy_connectors")
        if not callable(deploy_connectors):
            raise RuntimeError(f"Adapter '{resolved_deployer_name}' does not expose Level 4 deploy_connectors()")
        result = deploy_connectors()
        if not result:
            raise RuntimeError(f"Level 4 finished without deployed connectors for adapter '{resolved_deployer_name}'")
    elif level_id == 5:
        orchestrator = build_deployer_orchestrator(
            deployer_name=resolved_deployer_name,
            deployer_registry=deployer_registry,
            adapter=adapter,
            topology=topology,
        )
        context = orchestrator.resolve_context(topology=topology)
        deploy_components = getattr(orchestrator.deployer, "deploy_components", None)
        if not callable(deploy_components):
            raise RuntimeError(f"Deployer '{resolved_deployer_name}' does not expose Level 5 deploy_components()")
        result = deploy_components(context)
    else:
        result = run_validate(
            adapter,
            deployer_name=resolved_deployer_name,
            deployer_registry=deployer_registry,
            topology=topology,
            validation_engine_cls=validation_engine_cls,
            experiment_storage=experiment_storage,
            baseline=baseline,
        )

    return {
        "level": level_id,
        "name": level_name,
        "status": "completed",
        "result": result,
    }


def run_levels(
    adapter_name,
    levels=None,
    adapter_registry=None,
    deployer_registry=None,
    topology="local",
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    baseline=False,
):
    """Run a sequence of numbered levels with one adapter instance."""
    selected_levels = [int(level) for level in (levels or sorted(LEVEL_DESCRIPTIONS))]
    adapter = build_adapter(
        adapter_name,
        adapter_registry=adapter_registry,
        dry_run=False,
        topology=topology,
    )

    completed = []
    for level_id in selected_levels:
        completed.append(
            run_level(
                adapter,
                level_id,
                deployer_name=adapter_name,
                deployer_registry=deployer_registry,
                topology=topology,
                validation_engine_cls=validation_engine_cls,
                metrics_collector_cls=metrics_collector_cls,
                experiment_storage=experiment_storage,
                baseline=baseline,
            )
        )

    return {
        "status": "completed",
        "adapter": adapter_name,
        "topology": topology,
        "levels": completed,
    }


def _interactive_read(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _interactive_confirm(prompt, default=False):
    default_label = "Y/n" if default else "y/N"
    answer = _interactive_read(f"{prompt} ({default_label}): ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "s", "si", "sí"}


def _print_interactive_menu(adapter_name, adapter_registry=None):
    registry = adapter_registry or ADAPTER_REGISTRY
    adapters = ", ".join(sorted(registry))
    print()
    print("=" * 50)
    print("DATASPACE VALIDATION ENVIRONMENT")
    print("=" * 50)
    print(f"Active adapter: {adapter_name}")
    print(f"Available adapters: {adapters}")
    print()
    print("[Full Deployment]")
    print("0 - Run All Levels (1-6) sequentially")
    print()
    print("[Individual Levels]")
    for level_id in sorted(LEVEL_DESCRIPTIONS):
        print(f"{level_id} - Level {level_id}: {LEVEL_DESCRIPTIONS[level_id]}")
    print()
    print("[Operations]")
    print("S - Select adapter")
    print("P - Preview deployment plan")
    print("H - Plan/apply hosts entries")
    print("M - Run metrics / benchmarks")
    print()
    print("[More]")
    print("T - Tools")
    print("U - UI Validation")
    print()
    print("[Control]")
    print("? - Help")
    print("Q - Exit")
    print("=" * 50)


def _print_interactive_help():
    print()
    print("=" * 50)
    print("MENU HELP")
    print("=" * 50)
    print("[Deployment]")
    print("0 - Use for a fresh or full rebuild when you want Levels 1-6 executed in order.")
    print("1 - Use when the local Kubernetes/Minikube cluster is missing or needs to be prepared.")
    print("2 - Use when shared services such as Keycloak, MinIO, PostgreSQL or Vault are missing or outdated.")
    print("3 - Use when the dataspace base or registration-service must be deployed or refreshed.")
    print("4 - Use when connector deployments changed, or when switching/redeploying the selected adapter.")
    print("5 - Use when optional component services changed, for example AI Model Hub or Ontology Hub.")
    print("6 - Use after deployment changes to validate the selected adapter with cleanup, Newman, storage checks and Playwright when enabled.")
    print()
    print("[Operations]")
    print("S - Use when you want to switch between adapters, for example inesdata and edc.")
    print("P - Use before deploying to inspect the plan without changing the environment.")
    print("H - Use when browser or CLI access fails because local hostnames are missing.")
    print(
        "M - Use when you only need metrics or standalone benchmarks. "
        "It does not replace Level 6 validation; Kafka E2E validation runs automatically in Level 6."
    )
    print()
    print("[Tools Submenu]")
    print("T - Open Tools.")
    print("  1 - Use on a clean machine or after dependency issues to install/repair framework dependencies.")
    print("  2 - Use when diagnosing local readiness issues before deploying or validating.")
    print("  3 - Use after a WSL restart when connectors are still deployed but local access needs recovery.")
    print("  4 - Use when generated files, caches or previous results make the workspace hard to reason about.")
    print("  5 - Use during development after changing local images that must be rebuilt and loaded.")
    print("      In the image submenu, options 1-3 keep the legacy INESData shortcuts.")
    print("      Options 4-7 use explicit image recipes for the active adapter.")
    print("  6/X - Use only when you intentionally want to destroy and recreate the selected dataspace.")
    print("  B - Back to the main menu.")
    print()
    print("[UI Validation Submenu]")
    print("U - Open UI Validation.")
    print("  1 - Use to validate the INESData portal experience independently from full Level 6.")
    print("  2 - Use when Ontology Hub UI changed or after deploying ontology-related components.")
    print("  3 - Use when AI Model Hub UI changed or after deploying AI Model Hub components.")
    print("  B - Back to the main menu.")
    print()
    print("[Compatibility]")
    print("Legacy shortcuts still work from the main menu: B, D, R, C, L, I, O and A.")
    print("Q - Exit the menu.")
    print("=" * 50)


def _select_adapter_interactive(current_adapter, adapter_registry=None):
    registry = adapter_registry or ADAPTER_REGISTRY
    print()
    print("Available adapters:")
    for index, adapter_name in enumerate(sorted(registry), start=1):
        marker = " (current)" if adapter_name == current_adapter else ""
        print(f"{index} - {adapter_name}{marker}")
    print("B - Back")

    choice = _interactive_read("\nSelection: ").strip().upper()
    if not choice or choice == "B":
        return current_adapter

    adapters = sorted(registry)
    try:
        index = int(choice) - 1
    except ValueError:
        print("Invalid selection.")
        return current_adapter

    if index < 0 or index >= len(adapters):
        print("Invalid selection.")
        return current_adapter
    return adapters[index]


def _print_action_result(result):
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2, default=str))
    elif result is not None:
        print(result)


def _print_tools_menu():
    print()
    print("=" * 50)
    print("TOOLS")
    print("=" * 50)
    print("1 - Bootstrap Framework Dependencies")
    print("2 - Run Framework Doctor")
    print("3 - Recover Connectors After WSL Restart")
    print("4 - Cleanup Workspace")
    print("5 - Build and Deploy Local Images")
    print("6/X - Recreate Dataspace")
    print("B - Back")
    print("=" * 50)


def _print_ui_validation_menu():
    print()
    print("=" * 50)
    print("UI VALIDATION")
    print("=" * 50)
    print("1 - INESData Tests (Normal/Live/Debug)")
    print("2 - Ontology Hub Tests (Normal/Live/Debug)")
    print("3 - AI Model Hub Tests (Normal/Live/Debug)")
    print("B - Back")
    print("=" * 50)


def _run_recreate_dataspace_interactive(
    current_adapter="inesdata",
    adapter_registry=None,
    deployer_registry=None,
    topology="local",
):
    adapter = build_adapter(current_adapter, adapter_registry=adapter_registry, topology=topology)
    resolved_deployer_name, context = _resolve_deployer_context(
        adapter,
        deployer_name=current_adapter,
        deployer_registry=deployer_registry,
        topology=topology,
    )
    plan = _build_recreate_dataspace_plan(adapter, context)
    dataspace_name = str(plan.get("dataspace") or "").strip()

    print()
    print("=" * 50)
    print("RECREATE DATASPACE PLAN")
    print("=" * 50)
    print(f"Adapter: {resolved_deployer_name}")
    print(f"Topology: {topology}")
    print(f"Dataspace: {dataspace_name}")
    print(f"Namespace: {plan.get('namespace')}")
    print("Shared services: preserved")
    print("Level 4 connectors: invalidated and must be redeployed")
    print("=" * 50)

    confirmation = _interactive_read(
        f"Type the exact dataspace name '{dataspace_name}' to continue: "
    ).strip()
    if confirmation != dataspace_name:
        print("Dataspace recreation cancelled.")
        return None

    with_connectors = _interactive_confirm("Recreate Level 4 connectors now?", default=False)

    return run_recreate_dataspace(
        adapter,
        deployer_name=current_adapter,
        deployer_registry=deployer_registry,
        topology=topology,
        confirm_dataspace=confirmation,
        with_connectors=with_connectors,
    )


def _run_tools_submenu(
    current_adapter="inesdata",
    adapter_registry=None,
    deployer_registry=None,
    topology="local",
):
    actions = {
        "1": "bootstrap",
        "2": "doctor",
        "3": "recover",
        "4": "cleanup",
        "5": "local_images",
    }
    recreate_choices = {"6", "X"}

    while True:
        _print_tools_menu()
        choice = _interactive_read("\nTools selection: ").strip().upper()
        if not choice or choice == "B":
            return

        if choice in recreate_choices:
            _print_action_result(
                _run_recreate_dataspace_interactive(
                    current_adapter=current_adapter,
                    adapter_registry=adapter_registry,
                    deployer_registry=deployer_registry,
                    topology=topology,
                )
            )
            continue

        action_name = actions.get(choice)
        if action_name is None:
            print("Invalid tools selection. Please try again.")
            continue
        _run_legacy_menu_action(action_name, current_adapter=current_adapter)


def _run_ui_validation_submenu():
    actions = {
        "1": "inesdata_ui",
        "2": "ontology_hub_ui",
        "3": "ai_model_hub_ui",
    }

    while True:
        _print_ui_validation_menu()
        choice = _interactive_read("\nUI validation selection: ").strip().upper()
        if not choice or choice == "B":
            return

        action_name = actions.get(choice)
        if action_name is None:
            print("Invalid UI validation selection. Please try again.")
            continue
        _run_legacy_menu_action(action_name)


def _run_legacy_menu_action(action_name, current_adapter="inesdata"):
    """Run compatibility menu shortcuts through the migrated main.py modules."""
    migrated_actions = {
        "bootstrap": local_menu_tools.run_framework_bootstrap_interactive,
        "doctor": local_menu_tools.run_framework_doctor,
        "recover": local_menu_tools.run_connector_recovery_after_wsl_restart,
        "cleanup": local_menu_tools.run_workspace_cleanup_interactive,
        "inesdata_ui": ui_interactive_menu.run_inesdata_ui_tests_interactive,
        "ontology_hub_ui": ui_interactive_menu.run_ontology_hub_ui_tests_interactive,
        "ai_model_hub_ui": ui_interactive_menu.run_ai_model_hub_ui_tests_interactive,
    }
    if action_name == "local_images":
        return local_menu_tools.run_local_images_workflow_interactive(active_adapter=current_adapter)

    migrated_action = migrated_actions.get(action_name)
    if callable(migrated_action):
        return migrated_action()

    raise ValueError(f"Unknown legacy menu action: {action_name}")


def run_interactive_menu(
    adapter_registry=None,
    deployer_registry=None,
    validation_engine_cls=ValidationEngine,
    metrics_collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_manager_cls=KafkaManager,
    topology="local",
):
    """Run a guided menu equivalent to the legacy numbered-level workflow."""
    registry = adapter_registry or ADAPTER_REGISTRY
    current_adapter = "inesdata" if "inesdata" in registry else sorted(registry)[0]

    while True:
        _print_interactive_menu(current_adapter, adapter_registry=registry)
        choice = _interactive_read("\nSelection: ").strip().upper()

        if not choice or choice == "Q":
            print("\nExiting Dataspace Validation Environment\n")
            return {"status": "exited", "adapter": current_adapter}

        try:
            if choice in {"?", "HELP"}:
                _print_interactive_help()
                continue

            if choice == "S":
                current_adapter = _select_adapter_interactive(current_adapter, adapter_registry=registry)
                continue

            if choice == "T":
                _run_tools_submenu(
                    current_adapter=current_adapter,
                    adapter_registry=registry,
                    deployer_registry=deployer_registry,
                    topology=topology,
                )
                continue

            if choice == "U":
                _run_ui_validation_submenu()
                continue

            if choice == "B":
                _run_legacy_menu_action("bootstrap")
                continue

            if choice == "D":
                _run_legacy_menu_action("doctor")
                continue

            if choice == "R":
                _run_legacy_menu_action("recover")
                continue

            if choice == "C":
                _run_legacy_menu_action("cleanup")
                continue

            if choice == "L":
                _run_legacy_menu_action("local_images", current_adapter=current_adapter)
                continue

            if choice == "I":
                _run_legacy_menu_action("inesdata_ui")
                continue

            if choice == "O":
                _run_legacy_menu_action("ontology_hub_ui")
                continue

            if choice == "A":
                _run_legacy_menu_action("ai_model_hub_ui")
                continue

            if choice == "P":
                preview = build_dry_run_preview(
                    adapter_name=current_adapter,
                    command="deploy",
                    adapter_registry=registry,
                    deployer_registry=deployer_registry,
                    validation_engine_cls=validation_engine_cls,
                    metrics_collector_cls=metrics_collector_cls,
                    experiment_storage=experiment_storage,
                    topology=topology,
                    include_deployer_dry_run=True,
                )
                _print_action_result(preview)
                continue

            if choice == "H":
                adapter = build_adapter(current_adapter, adapter_registry=registry, topology=topology)
                if _should_sync_deployer_hosts() and not _interactive_confirm(
                    "PIONERA_SYNC_HOSTS is enabled. Apply changes to the hosts file?",
                    default=False,
                ):
                    print("Hosts operation cancelled.")
                    continue
                _print_action_result(
                    run_hosts(
                        adapter,
                        deployer_name=current_adapter,
                        deployer_registry=deployer_registry,
                        topology=topology,
                    )
                )
                continue

            if choice == "M":
                if not _interactive_confirm(f"Run metrics for {current_adapter}?", default=False):
                    print("Metrics cancelled.")
                    continue
                kafka_enabled = _interactive_confirm("Enable standalone Kafka broker benchmark?", default=False)
                adapter = build_adapter(current_adapter, adapter_registry=registry, topology=topology)
                _print_action_result(
                    run_metrics(
                        adapter,
                        deployer_name=current_adapter,
                        deployer_registry=deployer_registry,
                        topology=topology,
                        metrics_collector_cls=metrics_collector_cls,
                        experiment_storage=experiment_storage,
                        kafka_enabled=kafka_enabled,
                        kafka_manager_cls=kafka_manager_cls,
                    )
                )
                continue

            if choice == "0":
                if not _interactive_confirm(
                    f"Run all levels 1-6 for {current_adapter}?",
                    default=False,
                ):
                    print("Full level execution cancelled.")
                    continue
                _print_action_result(
                    run_levels(
                        current_adapter,
                        levels=sorted(LEVEL_DESCRIPTIONS),
                        adapter_registry=registry,
                        deployer_registry=deployer_registry,
                        topology=topology,
                        validation_engine_cls=validation_engine_cls,
                        metrics_collector_cls=metrics_collector_cls,
                        experiment_storage=experiment_storage,
                    )
                )
                continue

            if choice in {str(level_id) for level_id in LEVEL_DESCRIPTIONS}:
                level_id = int(choice)
                if not _interactive_confirm(
                    f"Run Level {level_id}: {LEVEL_DESCRIPTIONS[level_id]} for {current_adapter}?",
                    default=False,
                ):
                    print(f"Level {level_id} cancelled.")
                    continue
                _print_action_result(
                    run_levels(
                        current_adapter,
                        levels=[level_id],
                        adapter_registry=registry,
                        deployer_registry=deployer_registry,
                        topology=topology,
                        validation_engine_cls=validation_engine_cls,
                        metrics_collector_cls=metrics_collector_cls,
                        experiment_storage=experiment_storage,
                    )
                )
                continue

            print("Invalid selection. Please try again.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.\n")
        except Exception as exc:
            print(f"\nOperation error: {exc}\n")


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
        usage="python main.py menu | python main.py list | python main.py <adapter> [command] [--topology local|vm-single|vm-distributed] [--dry-run] [--iterations N] [--kafka] [--baseline] | python main.py report <experiment_id> | python main.py compare <experiment_a> <experiment_b>",
        epilog=(
            "Examples:\n"
            "  python main.py menu\n"
            "  python main.py inesdata deploy --topology local\n"
            "  PIONERA_VM_EXTERNAL_IP=192.0.2.10 python main.py edc hosts --topology vm-single\n"
            "  python main.py edc validate --topology local\n"
            "  python main.py edc hosts --topology local\n"
            "  python main.py edc recreate-dataspace --topology local --confirm-dataspace demoedc\n"
            "  python main.py edc recreate-dataspace --topology local --confirm-dataspace demoedc --with-connectors\n"
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
        help=f"Adapter name ({', '.join(sorted(registry))}) or 'list'/'menu'",
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
        help="Deployment topology to target.",
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
    parser.add_argument(
        "--confirm-dataspace",
        default=None,
        help="Exact dataspace name required by destructive operations such as recreate-dataspace.",
    )
    parser.add_argument(
        "--with-connectors",
        action="store_true",
        help="After recreate-dataspace, run Level 4 connectors for the same adapter.",
    )
    return parser


def main(
    argv=None,
    runner_cls=ExperimentRunner,
    adapter_registry=None,
    deployer_registry=None,
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
        if argv is None and sys.stdin.isatty():
            return run_interactive_menu(
                adapter_registry=registry,
                deployer_registry=deployer_registry,
                validation_engine_cls=validation_engine_cls,
                metrics_collector_cls=metrics_collector_cls,
                experiment_storage=experiment_storage,
                kafka_manager_cls=kafka_manager_cls,
                topology=args.topology,
            )
        parser.print_help()
        return 1

    if args.adapter == "menu":
        if args.command is not None or args.extra:
            parser.error("'menu' does not accept additional arguments")
        return run_interactive_menu(
            adapter_registry=registry,
            deployer_registry=deployer_registry,
            validation_engine_cls=validation_engine_cls,
            metrics_collector_cls=metrics_collector_cls,
            experiment_storage=experiment_storage,
            kafka_manager_cls=kafka_manager_cls,
            topology=args.topology,
        )

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
        try:
            preview = build_dry_run_preview(
                adapter_name=args.adapter,
                command=command,
                adapter_registry=registry,
                deployer_registry=deployer_registry,
                validation_engine_cls=validation_engine_cls,
                metrics_collector_cls=metrics_collector_cls,
                experiment_storage=experiment_storage,
                iterations=args.iterations,
                kafka_enabled=args.kafka,
                baseline=args.baseline,
                topology=args.topology,
                with_connectors=args.with_connectors,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(preview, indent=2, default=str))
        return preview

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
        try:
            result = run_deploy(
                adapter,
                deployer_name=args.adapter,
                deployer_registry=deployer_registry,
                topology=args.topology,
            )
        except ValueError as exc:
            parser.error(str(exc))
        if isinstance(result, dict) and result.get("mode") in {"shadow", "execute"}:
            print(json.dumps(result, indent=2, default=str))
        return result

    if command == "validate":
        try:
            return run_validate(
                adapter,
                deployer_name=args.adapter,
                deployer_registry=deployer_registry,
                topology=args.topology,
                validation_engine_cls=validation_engine_cls,
                experiment_storage=experiment_storage,
                baseline=args.baseline,
            )
        except ValueError as exc:
            parser.error(str(exc))

    if command == "metrics":
        try:
            return run_metrics(
                adapter,
                deployer_name=args.adapter,
                deployer_registry=deployer_registry,
                topology=args.topology,
                metrics_collector_cls=metrics_collector_cls,
                experiment_storage=experiment_storage,
                kafka_enabled=args.kafka,
                kafka_manager_cls=kafka_manager_cls,
                baseline=args.baseline,
            )
        except ValueError as exc:
            parser.error(str(exc))

    if command == "hosts":
        try:
            result = run_hosts(
                adapter,
                deployer_name=args.adapter,
                deployer_registry=deployer_registry,
                topology=args.topology,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, default=str))
        return result

    if command == "recreate-dataspace":
        result = run_recreate_dataspace(
            adapter,
            deployer_name=args.adapter,
            deployer_registry=deployer_registry,
            topology=args.topology,
            confirm_dataspace=args.confirm_dataspace,
            with_connectors=args.with_connectors,
        )
        print(json.dumps(result, indent=2, default=str))
        return result

    if _should_use_deployer_run():
        result = run_run(
            adapter,
            deployer_name=args.adapter,
            deployer_registry=deployer_registry,
            topology=args.topology,
            validation_engine_cls=validation_engine_cls,
            metrics_collector_cls=metrics_collector_cls,
            experiment_storage=experiment_storage,
            kafka_enabled=args.kafka,
            kafka_manager_cls=kafka_manager_cls,
            baseline=args.baseline,
        )
        if isinstance(result, dict) and result.get("mode") in {"shadow", "execute"}:
            print(json.dumps(result, indent=2, default=str))
        return result

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
