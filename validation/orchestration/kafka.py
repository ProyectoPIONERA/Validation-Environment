"""Kafka-related optional validation helpers for Level 6."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


def should_run_kafka_edc_validation(
    *,
    flag_enabled: Callable[[str, bool], bool],
) -> bool:
    return flag_enabled("LEVEL6_RUN_KAFKA_EDC", False)


def run_kafka_edc_validation(
    connectors: list[str],
    experiment_dir: str,
    *,
    validator: Any,
    experiment_storage: Any,
) -> list[dict[str, Any]]:
    if len(connectors) < 2:
        return [
            {
                "status": "skipped",
                "reason": "not_enough_connectors",
                "timestamp": datetime.now().isoformat(),
            }
        ]

    results = validator.run_all(connectors, experiment_dir=experiment_dir) or []
    results = list(results)
    experiment_storage.save_kafka_edc_results_json(results, experiment_dir)
    return results
