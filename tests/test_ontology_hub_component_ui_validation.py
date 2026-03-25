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
                self.assertIn("--workers=1", command)
                self.assertIn("PLAYWRIGHT_JSON_REPORT_FILE", env)
                with open(env["PLAYWRIGHT_JSON_REPORT_FILE"], "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
                return subprocess.CompletedProcess(command, 0)

            with mock.patch(
                "validation.components.ontology_hub.ui_runner.subprocess.run",
                side_effect=fake_subprocess_run,
            ), mock.patch(
                "validation.components.ontology_hub.ui_runner._wait_for_ontology_hub_ui_ready",
                return_value=True,
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
            self.assertEqual(result["pt5_summary"]["total"], 5)
            self.assertEqual(result["support_summary"]["total"], 0)
            self.assertTrue(all(case["case_group"] == "pt5" for case in result["executed_cases"]))
            self.assertGreaterEqual(len(result["evidence_index"]), 5)
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
                "executed_cases": [
                    {
                        "test_case_id": "PT5-OH-08",
                        "type": "api",
                        "evaluation": {"status": "passed", "assertions": []},
                    },
                    {
                        "test_case_id": "PT5-OH-15",
                        "type": "api",
                        "case_group": "pt5",
                        "validation_type": "integration",
                        "dataspace_dimension": "integration",
                        "mapping_status": "partial",
                        "coverage_status": "partial",
                        "execution_mode": "api",
                        "evaluation": {"status": "passed", "assertions": []},
                    },
                ],
                "evidence_index": [{"scope": "suite", "suite": "api", "artifact_name": "report_json", "path": "api.json"}],
                "artifacts": {"report_json": os.path.join(tmpdir, "api.json")},
            }
            ui_result = {
                "component": "ontology-hub",
                "suite": "ui",
                "status": "passed",
                "summary": {"total": 5, "passed": 5, "failed": 0, "skipped": 0},
                "executed_cases": [
                    {
                        "test_case_id": "PT5-OH-15",
                        "type": "ui",
                        "case_group": "pt5",
                        "validation_type": "integration",
                        "dataspace_dimension": "integration",
                        "mapping_status": "mapped",
                        "coverage_status": "automated",
                        "execution_mode": "ui",
                        "evaluation": {"status": "passed", "assertions": []},
                    },
                    {
                        "test_case_id": "OH-LOGIN",
                        "type": "ui",
                        "case_group": "support",
                        "validation_type": "support",
                        "dataspace_dimension": "support",
                        "mapping_status": "supporting",
                        "coverage_status": "automated",
                        "execution_mode": "ui_support",
                        "evaluation": {"status": "passed", "assertions": []},
                    },
                ],
                "evidence_index": [{"scope": "suite", "suite": "ui", "artifact_name": "report_json", "path": "ui.json"}],
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
            self.assertEqual(len(result["executed_cases"]), 4)
            self.assertEqual(result["pt5_summary"]["total"], 2)
            self.assertEqual(result["pt5_summary"]["passed"], 2)
            self.assertEqual(len(result["pt5_case_results"]), 2)
            self.assertEqual(result["support_summary"]["total"], 1)
            self.assertEqual(len(result["support_checks"]), 1)
            self.assertEqual(result["pt5_case_results"][1]["test_case_id"], "PT5-OH-15")
            self.assertEqual(set(result["pt5_case_results"][1]["source_suites"]), {"api", "ui"})
            self.assertEqual(result["pt5_case_results"][1]["traceability"], ["OntHub-54", "OntHub-55"])
            self.assertEqual(result["support_checks"][0]["traceability"], [])
            self.assertEqual(result["catalog_alignment"]["summary"]["declared_pt5_cases"], 16)
            self.assertEqual(result["catalog_alignment"]["summary"]["executed_pt5_cases"], 2)
            self.assertEqual(result["catalog_alignment"]["summary"]["uncovered_pt5_cases"], 14)
            self.assertEqual(result["catalog_alignment"]["summary"]["declared_support_checks"], 2)
            self.assertEqual(result["catalog_alignment"]["summary"]["executed_support_checks"], 1)
            self.assertEqual(result["catalog_alignment"]["summary"]["missing_support_checks"], 1)
            self.assertTrue(os.path.exists(result["artifacts"]["report_json"]))
            self.assertTrue(result["artifacts"]["ui_report_json"].endswith("ui.json"))
            self.assertTrue(os.path.exists(result["artifacts"]["pt5_case_results_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["support_checks_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["evidence_index_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["findings_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["catalog_alignment_json"]))


if __name__ == "__main__":
    unittest.main()
