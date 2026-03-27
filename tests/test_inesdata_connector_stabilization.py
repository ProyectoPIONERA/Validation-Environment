import contextlib
import io
import unittest
from unittest import mock

import inesdata


class ConnectorStabilizationTests(unittest.TestCase):
    def test_validate_connectors_with_stabilization_uses_backoff_and_recovers(self):
        output = io.StringIO()

        with (
            mock.patch.object(
                inesdata,
                "validate_connectors_deployment",
                side_effect=[False, False, True],
            ) as mock_validate,
            mock.patch.object(inesdata.time, "sleep") as mock_sleep,
            contextlib.redirect_stdout(output),
        ):
            result = inesdata._validate_connectors_with_stabilization(["conn-a"])

        self.assertTrue(result)
        self.assertEqual(mock_validate.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [mock.call(20), mock.call(40)])
        rendered = output.getvalue()
        self.assertIn("attempt 1/3", rendered)
        self.assertIn("attempt 2/3", rendered)
        self.assertIn("Connector validation recovered after stabilization retry.", rendered)

    def test_validate_connectors_with_stabilization_returns_false_after_exhausting_retries(self):
        output = io.StringIO()

        with (
            mock.patch.object(
                inesdata,
                "validate_connectors_deployment",
                side_effect=[False, False, False],
            ) as mock_validate,
            mock.patch.object(inesdata.time, "sleep") as mock_sleep,
            contextlib.redirect_stdout(output),
        ):
            result = inesdata._validate_connectors_with_stabilization(
                ["conn-a"],
                retries=2,
                wait_seconds=5,
                backoff_factor=3,
            )

        self.assertFalse(result)
        self.assertEqual(mock_validate.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [mock.call(5), mock.call(15)])
        rendered = output.getvalue()
        self.assertIn("attempt 1/3", rendered)
        self.assertIn("attempt 2/3", rendered)


if __name__ == "__main__":
    unittest.main()
