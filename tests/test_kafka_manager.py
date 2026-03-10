import os
import unittest
from unittest import mock

from framework.kafka_manager import KafkaManager


class _FakeKafkaContainer:
    def __init__(self, image):
        self.image = image
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        return self

    def get_bootstrap_server(self):
        return "localhost:19092"

    def stop(self):
        self.stopped = True


class _FailingContainerLoader:
    def __call__(self, image):
        raise RuntimeError("docker unavailable")


class KafkaManagerTests(unittest.TestCase):
    def test_uses_already_running_kafka_without_starting_container(self):
        manager = KafkaManager(bootstrap_servers="localhost:9092")

        with mock.patch.object(KafkaManager, "is_kafka_available", return_value=True):
            bootstrap = manager.ensure_kafka_running()

        self.assertEqual(bootstrap, "localhost:9092")
        self.assertFalse(manager.started_by_framework)
        self.assertIsNone(manager.container)

    def test_auto_starts_kafka_container_when_broker_unavailable(self):
        manager = KafkaManager(container_class=_FakeKafkaContainer)

        with mock.patch.object(KafkaManager, "is_kafka_available", side_effect=[False, True]):
            bootstrap = manager.ensure_kafka_running()

        self.assertEqual(bootstrap, "localhost:19092")
        self.assertTrue(manager.started_by_framework)
        self.assertIsNotNone(manager.container)
        self.assertTrue(manager.container.started)

    def test_stop_kafka_only_stops_framework_managed_container(self):
        manager = KafkaManager(container_class=_FakeKafkaContainer)
        manager.container = _FakeKafkaContainer("confluentinc/cp-kafka:latest")
        manager.started_by_framework = True

        manager.stop_kafka()

        self.assertTrue(manager.container is None)
        self.assertFalse(manager.started_by_framework)

    def test_docker_unavailable_skips_auto_start(self):
        manager = KafkaManager(container_class=_FailingContainerLoader())

        with mock.patch.object(KafkaManager, "is_kafka_available", return_value=False):
            bootstrap = manager.ensure_kafka_running()

        self.assertIsNone(bootstrap)
        self.assertIn("docker unavailable", manager.last_error)

    def test_prefers_environment_bootstrap_servers_when_available(self):
        manager = KafkaManager(bootstrap_servers="localhost:9092")

        with mock.patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": "env-host:19092"}, clear=False):
            with mock.patch.object(KafkaManager, "is_kafka_available", side_effect=lambda value: value == "env-host:19092"):
                bootstrap = manager.ensure_kafka_running()

        self.assertEqual(bootstrap, "env-host:19092")


if __name__ == "__main__":
    unittest.main()

