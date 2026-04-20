import json
import os
import tempfile
import unittest
from unittest import mock

from framework.experiment_storage import ExperimentStorage
from validation.orchestration import readiness


class Level6ReadinessTests(unittest.TestCase):
    def test_wait_for_validation_ready_persists_passed_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = readiness.wait_for_validation_ready(
                ["conn-a", "conn-b"],
                timeout_seconds=1.0,
                poll_interval_seconds=0.01,
                probe_management_api_fn=mock.Mock(return_value=(True, {"items": 1})),
                probe_catalog_fn=mock.Mock(return_value=(True, {"datasets": 0})),
                experiment_storage=ExperimentStorage,
                experiment_dir=tmpdir,
            )

            readiness_path = os.path.join(tmpdir, "level6_readiness.json")
            self.assertEqual(result["status"], "passed")
            self.assertTrue(os.path.exists(readiness_path))
            with open(readiness_path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            self.assertEqual(stored["status"], "passed")
            self.assertEqual(len(stored["gates"]), 4)

    def test_wait_for_validation_ready_reports_failed_gates(self):
        result = readiness.wait_for_validation_ready(
            ["conn-a"],
            timeout_seconds=0.01,
            poll_interval_seconds=0.01,
            probe_management_api_fn=mock.Mock(return_value=(False, "HTTP 401")),
            probe_catalog_fn=mock.Mock(return_value=(True, {"datasets": 0})),
            experiment_storage=ExperimentStorage,
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["gates"][0]["gate"], "management_api_smoke:conn-a")
        self.assertEqual(result["gates"][0]["status"], "failed")
        self.assertEqual(result["gates"][0]["error"], "HTTP 401")

    def test_probe_management_api_requires_token(self):
        connectors_adapter = mock.Mock()
        connectors_adapter.get_management_api_headers.return_value = None

        passed, detail = readiness.probe_management_api(
            "conn-a",
            connectors_adapter=connectors_adapter,
            requests_module=mock.Mock(),
        )

        self.assertFalse(passed)
        self.assertEqual(detail, "could not obtain management API token")


if __name__ == "__main__":
    unittest.main()
