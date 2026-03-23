import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


COMPONENT_KEY = "ontology-hub"
PLAYWRIGHT_CONFIG_RELATIVE = os.path.join("..", "components", "ontology_hub", "ui", "playwright.config.js")
PLAYWRIGHT_WORKDIR = Path(__file__).resolve().parents[2] / "ui"
COMPONENT_UI_DIR = Path(__file__).resolve().parent / "ui"
PLAYWRIGHT_COMMAND = [os.path.join(".", "node_modules", ".bin", "playwright"), "test", "--config", PLAYWRIGHT_CONFIG_RELATIVE]

UI_CASE_METADATA: Dict[str, Dict[str, str]] = {
    "PT5-OH-09": {
        "mapping_status": "mapped",
        "automation_mode": "ui",
        "expected_result": "Resultados filtrados correctamente",
        "spec": "pt5_oh_09_filters.spec.js",
    },
    "PT5-OH-10": {
        "mapping_status": "partial",
        "automation_mode": "ui_partial",
        "expected_result": "Se muestra la version solicitada",
        "spec": "pt5_oh_10_versions.spec.js",
    },
    "PT5-OH-11": {
        "mapping_status": "mapped",
        "automation_mode": "ui",
        "expected_result": "Metadatos, codigo y graficos visibles",
        "spec": "pt5_oh_11_vocab_detail.spec.js",
    },
    "PT5-OH-12": {
        "mapping_status": "mapped",
        "automation_mode": "ui",
        "expected_result": "Metricas visibles conforme a lo definido",
        "spec": "pt5_oh_12_statistics.spec.js",
    },
    "PT5-OH-15": {
        "mapping_status": "mapped",
        "automation_mode": "ui",
        "expected_result": "Paridad funcional entre UI y API",
        "spec": "pt5_oh_15_ui_access.spec.js",
    },
}


def _component_dir(experiment_dir: str | None) -> str | None:
    if not experiment_dir:
        return None
    path = os.path.join(experiment_dir, "components", COMPONENT_KEY)
    os.makedirs(path, exist_ok=True)
    return path


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def _build_ui_artifact_paths(experiment_dir: str | None) -> Dict[str, str]:
    if experiment_dir:
        base_dir = os.path.join(experiment_dir, "components", COMPONENT_KEY, "ui")
    else:
        base_dir = str(COMPONENT_UI_DIR)

    paths = {
        "base_dir": base_dir,
        "output_dir": os.path.join(base_dir, "test-results"),
        "html_report_dir": os.path.join(base_dir, "playwright-report"),
        "blob_report_dir": os.path.join(base_dir, "blob-report"),
        "json_report_file": os.path.join(base_dir, "results.json"),
        "report_json": os.path.join(base_dir, "ontology_hub_ui_validation.json"),
    }
    for path in paths.values():
        if path.endswith(".json"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            os.makedirs(path, exist_ok=True)
    return paths


def _iter_specs(suites: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for suite in suites or []:
        for child_suite in suite.get("suites") or []:
            yield from _iter_specs([child_suite])
        for spec in suite.get("specs") or []:
            yield spec


def _spec_result_status(spec: Dict[str, Any]) -> str:
    tests = spec.get("tests") or []
    if not tests:
        return "skipped"
    results = tests[0].get("results") or []
    if not results:
        return "skipped"
    return (results[-1].get("status") or "skipped").lower()


def _attachments_from_spec(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    tests = spec.get("tests") or []
    if not tests:
        return []
    results = tests[0].get("results") or []
    if not results:
        return []
    attachments = results[-1].get("attachments") or []
    normalized: List[Dict[str, str]] = []
    for attachment in attachments:
        normalized.append(
            {
                "name": attachment.get("name", ""),
                "content_type": attachment.get("contentType", ""),
                "path": attachment.get("path", ""),
            }
        )
    return normalized


def _extract_executed_cases(report_payload: Dict[str, Any], base_url: str) -> List[Dict[str, Any]]:
    executed_cases: List[Dict[str, Any]] = []
    for spec in _iter_specs(report_payload.get("suites") or []):
        title = spec.get("title") or ""
        case_id = title.split(":", 1)[0].strip()
        metadata = UI_CASE_METADATA.get(case_id)
        if not metadata:
            continue
        status = _spec_result_status(spec)
        executed_cases.append(
            {
                "test_case_id": case_id,
                "description": title.split(":", 1)[1].strip() if ":" in title else title,
                "type": "ui",
                "mapping_status": metadata["mapping_status"],
                "automation_mode": metadata["automation_mode"],
                "request": {
                    "runner": "playwright",
                    "spec": metadata["spec"],
                    "base_url": base_url,
                },
                "response": {
                    "status": status,
                    "attachments": _attachments_from_spec(spec),
                },
                "evaluation": {
                    "status": status,
                    "assertions": [],
                },
                "expected_result": metadata["expected_result"],
            }
        )
    return executed_cases


def _load_results_summary(results_path: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    with open(results_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    stats = payload.get("stats") or {}
    summary = {
        "total": int(stats.get("expected", 0))
        + int(stats.get("unexpected", 0))
        + int(stats.get("flaky", 0))
        + int(stats.get("skipped", 0)),
        "passed": int(stats.get("expected", 0)),
        "failed": int(stats.get("unexpected", 0)) + int(stats.get("flaky", 0)),
        "skipped": int(stats.get("skipped", 0)),
    }
    return summary, _extract_executed_cases(payload, "")


def run_ontology_hub_ui_validation(base_url: str, experiment_dir: str | None = None) -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    normalized_base_url = (base_url or "").rstrip("/")
    artifact_paths = _build_ui_artifact_paths(experiment_dir)
    env = {
        **os.environ,
        "ONTOLOGY_HUB_BASE_URL": normalized_base_url,
        "PLAYWRIGHT_OUTPUT_DIR": artifact_paths["output_dir"],
        "PLAYWRIGHT_HTML_REPORT_DIR": artifact_paths["html_report_dir"],
        "PLAYWRIGHT_BLOB_REPORT_DIR": artifact_paths["blob_report_dir"],
        "PLAYWRIGHT_JSON_REPORT_FILE": artifact_paths["json_report_file"],
    }

    error = None
    exit_code = None
    status = "skipped"
    try:
        result = subprocess.run(
            PLAYWRIGHT_COMMAND,
            cwd=str(PLAYWRIGHT_WORKDIR),
            env=env,
        )
        exit_code = result.returncode
        status = "passed" if result.returncode == 0 else "failed"
    except OSError as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    if os.path.exists(artifact_paths["json_report_file"]):
        with open(artifact_paths["json_report_file"], "r", encoding="utf-8") as handle:
            report_payload = json.load(handle)
        stats = report_payload.get("stats") or {}
        summary = {
            "total": int(stats.get("expected", 0))
            + int(stats.get("unexpected", 0))
            + int(stats.get("flaky", 0))
            + int(stats.get("skipped", 0)),
            "passed": int(stats.get("expected", 0)),
            "failed": int(stats.get("unexpected", 0)) + int(stats.get("flaky", 0)),
            "skipped": int(stats.get("skipped", 0)),
        }
        executed_cases = _extract_executed_cases(report_payload, normalized_base_url)
        if summary["failed"] > 0:
            status = "failed"
        elif summary["passed"] > 0:
            status = "passed"
        elif summary["skipped"] == summary["total"] and summary["total"] > 0:
            status = "skipped"
    else:
        total_cases = len(UI_CASE_METADATA)
        summary = {
            "total": total_cases,
            "passed": 0,
            "failed": 0 if status == "skipped" else total_cases,
            "skipped": total_cases if status == "skipped" else 0,
        }
        executed_cases = [
            {
                "test_case_id": case_id,
                "description": case_id,
                "type": "ui",
                "mapping_status": metadata["mapping_status"],
                "automation_mode": metadata["automation_mode"],
                "request": {
                    "runner": "playwright",
                    "spec": metadata["spec"],
                    "base_url": normalized_base_url,
                },
                "response": {"status": status, "attachments": []},
                "evaluation": {"status": status, "assertions": []},
                "expected_result": metadata["expected_result"],
            }
            for case_id, metadata in UI_CASE_METADATA.items()
        ]

    suite_result: Dict[str, Any] = {
        "component": COMPONENT_KEY,
        "suite": "ui",
        "status": status,
        "timestamp": started_at,
        "base_url": normalized_base_url,
        "summary": summary,
        "executed_cases": executed_cases,
        "playwright_config": PLAYWRIGHT_CONFIG_RELATIVE,
        "specs": [metadata["spec"] for metadata in UI_CASE_METADATA.values()],
        "exit_code": exit_code,
        "error": error,
        "artifacts": {
            "report_json": artifact_paths["report_json"],
            "test_results_dir": artifact_paths["output_dir"],
            "html_report_dir": artifact_paths["html_report_dir"],
            "blob_report_dir": artifact_paths["blob_report_dir"],
            "json_report_file": artifact_paths["json_report_file"],
        },
    }
    _write_json(artifact_paths["report_json"], suite_result)
    return suite_result
