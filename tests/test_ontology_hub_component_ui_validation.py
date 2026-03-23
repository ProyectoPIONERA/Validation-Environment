import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from validation.components.ontology_hub.component_runner import run_ontology_hub_component_validation
from validation.components.ontology_hub.ui_runner import run_ontology_hub_ui_validation


def _build_playwright_results_payload():
    spec_titles = [
        "PT5-OH-09: term search filters by tag and vocabulary in the public UI",
        "PT5-OH-10: version history and version resources are exposed from the vocabulary detail page",
        "PT5-OH-11: vocabulary detail displays metadata and descriptive sections",
        "PT5-OH-12: vocabulary detail exposes statistics and LOD usage markers",
        "PT5-OH-15: public UI and API documentation are published together",
    ]
    return {
        "stats": {
            "expected": len(spec_titles),
            "unexpected": 0,
            "flaky": 0,
            "skipped": 0,
        },
        "suites": [
            {
                "title": "ontology-hub-ui",
                "suites": [],
                "specs": [
                    {
                        "title": title,
                        "tests": [
                            {
                                "results": [
                                    {
                                        "status": "passed",
                                        "attachments": [
                                            {
                                                "name": "trace",
                                                "contentType": "application/zip",
                                                "path": "trace.zip",
                                            }
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                    for title in spec_titles
                ],
            }
        ],
    }


class OntologyHubComponentUIValidationTests(unittest.TestCase):
    def test_run_ontology_hub_ui_validation_persists_playwright_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _build_playwright_results_payload()

            def fake_subprocess_run(command, cwd=None, env=None):
                self.assertIn("PLAYWRIGHT_JSON_REPORT_FILE", env)
                with open(env["PLAYWRIGHT_JSON_REPORT_FILE"], "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
                return subprocess.CompletedProcess(command, 0)

            with mock.patch(
                "validation.components.ontology_hub.ui_runner.subprocess.run",
                side_effect=fake_subprocess_run,
            ):
                result = run_ontology_hub_ui_validation(
                    "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
                    experiment_dir=tmpdir,
                )

            self.assertEqual(result["component"], "ontology-hub")
            self.assertEqual(result["suite"], "ui")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["summary"]["total"], 5)
            self.assertEqual(result["summary"]["passed"], 5)
            self.assertEqual(len(result["executed_cases"]), 5)
            self.assertTrue(
                os.path.exists(result["artifacts"]["report_json"]),
                "Expected the synthesized UI suite report to be persisted",
            )
            self.assertTrue(
                os.path.exists(result["artifacts"]["json_report_file"]),
                "Expected the mocked Playwright JSON report to exist",
            )

    def test_run_ontology_hub_component_validation_combines_api_and_ui(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            api_result = {
                "component": "ontology-hub",
                "suite": "api",
                "status": "passed",
                "summary": {"total": 5, "passed": 5, "failed": 0, "skipped": 0},
                "executed_cases": [{"test_case_id": "PT5-OH-08", "type": "api"}],
                "artifacts": {"report_json": os.path.join(tmpdir, "api.json")},
            }
            ui_result = {
                "component": "ontology-hub",
                "suite": "ui",
                "status": "passed",
                "summary": {"total": 5, "passed": 5, "failed": 0, "skipped": 0},
                "executed_cases": [{"test_case_id": "PT5-OH-09", "type": "ui"}],
                "artifacts": {
                    "report_json": os.path.join(tmpdir, "ui.json"),
                    "test_results_dir": os.path.join(tmpdir, "ui", "test-results"),
                    "html_report_dir": os.path.join(tmpdir, "ui", "playwright-report"),
                    "blob_report_dir": os.path.join(tmpdir, "ui", "blob-report"),
                    "json_report_file": os.path.join(tmpdir, "ui", "results.json"),
                },
            }

            with (
                mock.patch(
                    "validation.components.ontology_hub.component_runner.run_ontology_hub_validation",
                    return_value=api_result,
                ),
                mock.patch(
                    "validation.components.ontology_hub.component_runner.run_ontology_hub_ui_validation",
                    return_value=ui_result,
                ),
            ):
                result = run_ontology_hub_component_validation(
                    "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
                    experiment_dir=tmpdir,
                )

            self.assertEqual(result["component"], "ontology-hub")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["summary"]["total"], 10)
            self.assertEqual(result["summary"]["passed"], 10)
            self.assertEqual(result["suites"]["api"]["status"], "passed")
            self.assertEqual(result["suites"]["ui"]["status"], "passed")
            self.assertEqual(len(result["executed_cases"]), 2)
            self.assertTrue(os.path.exists(result["artifacts"]["report_json"]))
            self.assertTrue(result["artifacts"]["ui_report_json"].endswith("ui.json"))


if __name__ == "__main__":
    unittest.main()
