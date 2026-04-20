import unittest
from unittest import mock

from validation.orchestration import kafka


class Level6KafkaTests(unittest.TestCase):
    def test_should_run_kafka_edc_validation_delegates_to_flag(self):
        flag_enabled = mock.Mock(return_value=True)

        self.assertTrue(kafka.should_run_kafka_edc_validation(flag_enabled=flag_enabled))
        flag_enabled.assert_called_once_with("LEVEL6_RUN_KAFKA_EDC", False)

    def test_run_kafka_edc_validation_skips_when_not_enough_connectors(self):
        experiment_storage = mock.Mock()

        results = kafka.run_kafka_edc_validation(
            ["conn-a"],
            "/tmp/experiment",
            validator=mock.Mock(),
            experiment_storage=experiment_storage,
        )

        self.assertEqual(results[0]["status"], "skipped")
        self.assertEqual(results[0]["reason"], "not_enough_connectors")
        experiment_storage.save_kafka_edc_results_json.assert_not_called()

    def test_run_kafka_edc_validation_persists_results(self):
        validator = mock.Mock()
        validator.run_all.return_value = [{"status": "passed"}]
        experiment_storage = mock.Mock()

        results = kafka.run_kafka_edc_validation(
            ["conn-a", "conn-b"],
            "/tmp/experiment",
            validator=validator,
            experiment_storage=experiment_storage,
        )

        self.assertEqual(results, [{"status": "passed"}])
        validator.run_all.assert_called_once_with(
            ["conn-a", "conn-b"],
            experiment_dir="/tmp/experiment",
        )
        experiment_storage.save_kafka_edc_results_json.assert_called_once_with(
            [{"status": "passed"}],
            "/tmp/experiment",
        )


if __name__ == "__main__":
    unittest.main()
