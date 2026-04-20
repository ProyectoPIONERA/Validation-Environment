"""Readiness probes used by Level 6 validation."""

from __future__ import annotations

import time
from datetime import datetime
from itertools import permutations
from typing import Any, Callable


def build_management_health_payload() -> dict[str, Any]:
    return {
        "@context": {
            "@vocab": "https://w3id.org/edc/v0.0.1/ns/"
        },
        "offset": 0,
        "limit": 1,
        "filterExpression": [],
    }


def build_catalog_payload(provider: str, consumer: str, validation_engine: Any) -> dict[str, Any]:
    env_vars = validation_engine.build_newman_env(provider, consumer)
    return {
        "@context": {
            "@vocab": "https://w3id.org/edc/v0.0.1/ns/"
        },
        "@type": "CatalogRequest",
        "counterPartyAddress": env_vars["providerProtocolAddress"],
        "counterPartyId": provider,
        "protocol": "dataspace-protocol-http",
        "querySpec": {
            "offset": 0,
            "limit": 1,
            "filterExpression": [],
        },
    }


def probe_management_api(connector: str, *, connectors_adapter: Any, requests_module: Any) -> tuple[bool, Any]:
    headers = connectors_adapter.get_management_api_headers(connector)
    if not headers:
        return False, "could not obtain management API token"

    base_url = connectors_adapter.connector_base_url(connector)
    response = requests_module.post(
        f"{base_url}/management/v3/assets/request",
        headers=headers,
        json=build_management_health_payload(),
        timeout=5,
    )
    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"

    try:
        body = response.json()
    except ValueError:
        return False, "response body is not valid JSON"

    if not isinstance(body, list):
        return False, "management response is not a JSON array"

    return True, {"items": len(body)}


def probe_catalog(
    provider: str,
    consumer: str,
    *,
    connectors_adapter: Any,
    validation_engine: Any,
    requests_module: Any,
) -> tuple[bool, Any]:
    headers = connectors_adapter.get_management_api_headers(consumer)
    if not headers:
        return False, "could not obtain consumer management API token"

    consumer_base_url = connectors_adapter.connector_base_url(consumer)
    response = requests_module.post(
        f"{consumer_base_url}/management/v3/catalog/request",
        headers=headers,
        json=build_catalog_payload(provider, consumer, validation_engine),
        timeout=10,
    )
    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"

    try:
        body = response.json()
    except ValueError:
        return False, "catalog response is not valid JSON"

    if not isinstance(body, dict):
        return False, "catalog response is not a JSON object"

    datasets = body.get("dcat:dataset")
    if datasets is None:
        datasets = body.get("dataset")
    if datasets is None:
        return False, "catalog response missing dataset field"

    if isinstance(datasets, list):
        dataset_count = len(datasets)
    elif isinstance(datasets, dict):
        dataset_count = 1
    else:
        dataset_count = 0

    return True, {"datasets": dataset_count}


def wait_for_validation_ready(
    connectors: list[str],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    probe_management_api_fn: Callable[[str], tuple[bool, Any]],
    probe_catalog_fn: Callable[[str, str], tuple[bool, Any]],
    experiment_storage: Any,
    experiment_dir: str | None = None,
) -> dict[str, Any]:
    started_at = time.time()
    deadline = started_at + timeout_seconds
    gates: list[dict[str, Any]] = []

    pending_checks = []
    for connector in connectors or []:
        pending_checks.append({
            "name": f"management_api_smoke:{connector}",
            "probe": lambda connector_name=connector: probe_management_api_fn(connector_name),
            "attempts": 0,
        })

    for provider, consumer in permutations(connectors or [], 2):
        pending_checks.append({
            "name": f"catalog_smoke:{provider}->{consumer}",
            "probe": lambda provider_name=provider, consumer_name=consumer: probe_catalog_fn(provider_name, consumer_name),
            "attempts": 0,
        })

    while pending_checks and time.time() <= deadline:
        remaining_checks = []
        for check in pending_checks:
            check["attempts"] += 1
            gate_started_at = time.time()
            try:
                passed, detail = check["probe"]()
            except Exception as exc:
                passed = False
                detail = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }

            if passed:
                gates.append({
                    "gate": check["name"],
                    "status": "passed",
                    "attempts": check["attempts"],
                    "duration_seconds": round(time.time() - started_at, 3),
                    "probe_duration_seconds": round(time.time() - gate_started_at, 3),
                    "detail": detail,
                })
                continue

            check["last_error"] = detail
            remaining_checks.append(check)

        pending_checks = remaining_checks
        if pending_checks and time.time() <= deadline:
            time.sleep(poll_interval_seconds)

    for check in pending_checks:
        gates.append({
            "gate": check["name"],
            "status": "failed",
            "attempts": check["attempts"],
            "duration_seconds": round(time.time() - started_at, 3),
            "error": check.get("last_error"),
        })

    readiness = {
        "status": "passed" if not pending_checks else "failed",
        "timestamp": datetime.now().isoformat(),
        "connectors": list(connectors or []),
        "timeout_seconds": timeout_seconds,
        "poll_interval_seconds": poll_interval_seconds,
        "total_duration_seconds": round(time.time() - started_at, 3),
        "gates": gates,
    }

    if experiment_dir:
        experiment_storage.save(
            readiness,
            experiment_dir=experiment_dir,
            file_name="level6_readiness.json",
        )

    if readiness["status"] == "passed":
        print(
            "Level 6 validation readiness confirmed in "
            f"{readiness['total_duration_seconds']}s"
        )
    else:
        print(
            "Level 6 validation readiness did not converge within "
            f"{timeout_seconds}s"
        )

    return readiness
