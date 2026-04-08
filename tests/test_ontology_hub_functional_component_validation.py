import os
import tempfile
import unittest
from unittest import mock

from validation.components.ontology_hub.functional.component_runner import (
    run_ontology_hub_component_validation,
)
from validation.components.ontology_hub.functional.ui_runner import (
    PLAYWRIGHT_WORKDIR,
    _prepare_functional_runtime,
    run_ontology_hub_functional_validation,
)


class OntologyHubFunctionalComponentValidationTests(unittest.TestCase):
    def test_functional_ui_runner_uses_validation_ui_as_workdir(self):
        self.assertTrue(str(PLAYWRIGHT_WORKDIR).endswith("Validation-Environment/validation/ui"))

    def test_functional_ui_runner_uses_framework_preparation_hook(self):
        with mock.patch(
            "validation.components.ontology_hub.functional.ui_runner._prepare_functional_runtime",
            return_value=(True, None),
        ) as prepare_mock, mock.patch(
            "validation.components.ontology_hub.functional.ui_runner.subprocess.run",
            side_effect=FileNotFoundError("playwright missing"),
        ):
            run_ontology_hub_functional_validation(
                "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
                experiment_dir=tempfile.mkdtemp(),
            )

        prepare_mock.assert_called_once()

    def test_prepare_functional_runtime_reports_preparation_failure(self):
        with mock.patch("inesdata._prepare_ontology_hub_for_functional", return_value=False):
            prepared, error = _prepare_functional_runtime({"baseUrl": "http://ontology-hub-demo.dev.ds.dataspaceunit.upm"})

        self.assertFalse(prepared)
        self.assertEqual(error["type"], "RuntimePreparationError")

    def test_functional_ui_runner_reports_reason_when_playwright_cannot_start(self):
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch(
            "validation.components.ontology_hub.functional.ui_runner._prepare_functional_runtime",
            return_value=(True, None),
        ), mock.patch(
            "validation.components.ontology_hub.functional.ui_runner.subprocess.run",
            side_effect=FileNotFoundError("playwright missing"),
        ):
            result = run_ontology_hub_functional_validation(
                "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
                experiment_dir=tmpdir,
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "playwright_runtime_unavailable")
        self.assertEqual(result["error"]["type"], "FileNotFoundError")

    def test_functional_ui_runner_fails_fast_when_preparation_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch(
            "validation.components.ontology_hub.functional.ui_runner._prepare_functional_runtime",
            return_value=(False, {"type": "RuntimePreparationError", "message": "prep failed"}),
        ), mock.patch(
            "validation.components.ontology_hub.functional.ui_runner.subprocess.run",
        ) as subprocess_mock:
            result = run_ontology_hub_functional_validation(
                "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
                experiment_dir=tmpdir,
            )

        subprocess_mock.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "functional_preparation_failed")
        self.assertEqual(result["error"]["message"], "prep failed")

    def test_component_runner_wraps_functional_suite_for_level6(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            functional_result = {
                "component": "ontology-hub",
                "suite": "functional",
                "status": "passed",
                "reason": None,
                "error": None,
                "summary": {"total": 27, "passed": 27, "failed": 0, "skipped": 0},
                "executed_cases": [
                    {
                        "test_case_id": "OH-APP-01",
                        "description": "home is available",
                        "case_group": "pt5",
                        "evaluation": {"status": "passed", "assertions": []},
                    },
                    {
                        "test_case_id": "OH-APP-02",
                        "description": "admin login works",
                        "case_group": "pt5",
                        "evaluation": {"status": "passed", "assertions": []},
                    },
                ],
                "pt5_summary": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
                "evidence_index": [
                    {
                        "scope": "suite",
                        "suite": "functional",
                        "artifact_name": "report_json",
                        "path": os.path.join(tmpdir, "functional.json"),
                    }
                ],
                "artifacts": {
                    "report_json": os.path.join(tmpdir, "functional.json"),
                    "test_results_dir": os.path.join(tmpdir, "functional", "test-results"),
                    "html_report_dir": os.path.join(tmpdir, "functional", "playwright-report"),
                    "blob_report_dir": os.path.join(tmpdir, "functional", "blob-report"),
                    "json_report_file": os.path.join(tmpdir, "functional", "results.json"),
                },
            }

            with mock.patch(
                "validation.components.ontology_hub.functional.component_runner.run_ontology_hub_functional_validation",
                return_value=functional_result,
            ):
                result = run_ontology_hub_component_validation(
                    "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
                    experiment_dir=tmpdir,
                )

            self.assertEqual(result["component"], "ontology-hub")
            self.assertEqual(result["status"], "passed")
            self.assertIsNone(result["reason"])
            self.assertEqual(result["suites"]["functional"]["status"], "passed")
            self.assertEqual(len(result["executed_cases"]), 2)
            self.assertEqual(result["pt5_summary"]["total"], 2)
            self.assertEqual(result["support_summary"]["total"], 0)
            self.assertTrue(os.path.exists(result["artifacts"]["report_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["pt5_case_results_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["support_checks_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["evidence_index_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["findings_json"]))
            self.assertTrue(os.path.exists(result["artifacts"]["catalog_alignment_json"]))
            self.assertTrue(
                result["artifacts"]["functional_report_json"].endswith("functional.json")
            )


if __name__ == "__main__":
    unittest.main()
