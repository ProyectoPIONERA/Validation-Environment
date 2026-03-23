import os
from datetime import datetime
from typing import Any, Dict

from validation.components.ontology_hub.runner import run_ontology_hub_validation
from validation.components.ontology_hub.ui_runner import run_ontology_hub_ui_validation


COMPONENT_KEY = "ontology-hub"


def _component_dir(experiment_dir: str | None) -> str | None:
    if not experiment_dir:
        return None
    path = os.path.join(experiment_dir, "components", COMPONENT_KEY)
    os.makedirs(path, exist_ok=True)
    return path


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    import json

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def _combine_status(api_status: str, ui_status: str) -> str:
    statuses = {api_status, ui_status}
    if "failed" in statuses:
        return "failed"
    if statuses == {"skipped"}:
        return "skipped"
    return "passed"


def run_ontology_hub_component_validation(base_url: str, experiment_dir: str | None = None) -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    normalized_base_url = (base_url or "").rstrip("/")

    api_result = run_ontology_hub_validation(normalized_base_url, experiment_dir=experiment_dir)
    ui_result = run_ontology_hub_ui_validation(normalized_base_url, experiment_dir=experiment_dir)

    summary = {
        "total": int(api_result.get("summary", {}).get("total", 0))
        + int(ui_result.get("summary", {}).get("total", 0)),
        "passed": int(api_result.get("summary", {}).get("passed", 0))
        + int(ui_result.get("summary", {}).get("passed", 0)),
        "failed": int(api_result.get("summary", {}).get("failed", 0))
        + int(ui_result.get("summary", {}).get("failed", 0)),
        "skipped": int(api_result.get("summary", {}).get("skipped", 0))
        + int(ui_result.get("summary", {}).get("skipped", 0)),
    }

    component_result: Dict[str, Any] = {
        "component": COMPONENT_KEY,
        "base_url": normalized_base_url,
        "timestamp": started_at,
        "status": _combine_status(api_result.get("status", "skipped"), ui_result.get("status", "skipped")),
        "summary": summary,
        "suites": {
            "api": api_result,
            "ui": ui_result,
        },
        "executed_cases": list(api_result.get("executed_cases") or []) + list(ui_result.get("executed_cases") or []),
    }

    component_dir = _component_dir(experiment_dir)
    if component_dir:
        report_path = os.path.join(component_dir, "ontology_hub_component_validation.json")
        _write_json(report_path, component_result)
        component_result["artifacts"] = {
            "report_json": report_path,
            "api_report_json": (api_result.get("artifacts") or {}).get("report_json"),
            "ui_report_json": (ui_result.get("artifacts") or {}).get("report_json"),
            "ui_test_results_dir": (ui_result.get("artifacts") or {}).get("test_results_dir"),
            "ui_html_report_dir": (ui_result.get("artifacts") or {}).get("html_report_dir"),
            "ui_blob_report_dir": (ui_result.get("artifacts") or {}).get("blob_report_dir"),
            "ui_json_report_file": (ui_result.get("artifacts") or {}).get("json_report_file"),
        }

    return component_result
