import unittest
from unittest import mock

from validation.components.runner import run_component_validations, summarize_component_results


class ComponentValidationRunnerTests(unittest.TestCase):
    def test_unregistered_component_is_reported_as_skipped(self):
        results = run_component_validations(
            {
                "unknown-component": "http://unknown.example.local",
            }
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "skipped")
        self.assertEqual(results[0]["reason"], "no_validator_registered")

    def test_registered_component_uses_configured_runner(self):
        fake_runner = mock.Mock(
            return_value={
                "component": "ontology-hub",
                "status": "passed",
                "summary": {"total": 10, "passed": 10, "failed": 0, "skipped": 0},
                "suites": {
                    "api": {"status": "passed"},
                    "ui": {"status": "passed"},
                },
            }
        )

        with mock.patch.dict(
            "validation.components.runner.COMPONENT_RUNNERS",
            {"ontology-hub": fake_runner},
            clear=False,
        ):
            results = run_component_validations(
                {"ontology-hub": "http://ontology-hub-demo.dev.ds.dataspaceunit.upm"},
                experiment_dir="/tmp/fake-experiment",
            )

        fake_runner.assert_called_once_with(
            "http://ontology-hub-demo.dev.ds.dataspaceunit.upm",
            experiment_dir="/tmp/fake-experiment",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["component"], "ontology-hub")
        self.assertEqual(results[0]["status"], "passed")
        self.assertIn("suites", results[0])

    def test_summary_counts_statuses(self):
        summary = summarize_component_results(
            [
                {"status": "passed"},
                {"status": "failed"},
                {"status": "skipped"},
            ]
        )

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
