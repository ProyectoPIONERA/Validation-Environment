import os
import unittest
from unittest import mock

from framework.kafka_container_factory import KafkaContainerFactory
from framework.kafka_manager import KafkaManager


class _FakeKafkaContainer:
    def __init__(self, image):
        self.image = image
        self.started = False
        self.stopped = False
        self.cluster_host = "host.docker.internal"

    def start(self):
        self.started = True
        return self

    def get_bootstrap_server(self):
        return "localhost:19092"

    def get_cluster_bootstrap_server(self):
        return f"{self.cluster_host}:29092"

    def with_cluster_advertised_host(self, host):
        self.cluster_host = host
        return self

    def stop(self):
        self.stopped = True


class _FailingContainerLoader:
    def __call__(self, image):
        raise RuntimeError("docker unavailable")


class _RecordingFactory(KafkaContainerFactory):
    def __init__(self):
        self.calls = []

    def create_container(self, container_class, image, config=None):
        self.calls.append({
            "container_class": container_class,
            "image": image,
            "config": dict(config or {}),
        })
        container = container_class(image)
        with_cluster_advertised_host = getattr(container, "with_cluster_advertised_host", None)
        cluster_advertised_host = (config or {}).get("cluster_advertised_host")
        if cluster_advertised_host and callable(with_cluster_advertised_host):
            updated = with_cluster_advertised_host(cluster_advertised_host)
            if updated is not None:
                container = updated
        return container


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
        self.assertEqual(manager.cluster_bootstrap_servers, "host.docker.internal:29092")
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

    def test_reuses_framework_broker_without_losing_cluster_bootstrap_servers(self):
        manager = KafkaManager(bootstrap_servers="localhost:19092")
        manager.cluster_bootstrap_servers = "host.docker.internal:29092"
        manager.started_by_framework = True
        manager.container = _FakeKafkaContainer("confluentinc/cp-kafka:latest")

        with mock.patch.object(KafkaManager, "is_kafka_available", side_effect=lambda value: value == "localhost:19092"):
            bootstrap = manager.ensure_kafka_running()

        self.assertEqual(bootstrap, "localhost:19092")
        self.assertEqual(manager.cluster_bootstrap_servers, "host.docker.internal:29092")
        self.assertTrue(manager.started_by_framework)

    def test_start_kafka_uses_container_factory_with_runtime_config(self):
        factory = _RecordingFactory()
        manager = KafkaManager(
            container_class=_FakeKafkaContainer,
            container_factory=factory,
            runtime_config={
                "container_env_file": "/tmp/fake.env",
                "cluster_advertised_host": "cluster.kafka.internal",
            },
        )

        with mock.patch.object(KafkaManager, "is_kafka_available", side_effect=[False, True]):
            bootstrap = manager.ensure_kafka_running()

        self.assertEqual(bootstrap, "localhost:19092")
        self.assertEqual(factory.calls[0]["config"]["container_env_file"], "/tmp/fake.env")
        self.assertEqual(factory.calls[0]["config"]["cluster_advertised_host"], "cluster.kafka.internal")
        self.assertEqual(manager.cluster_bootstrap_servers, "cluster.kafka.internal:29092")


if __name__ == "__main__":
    unittest.main()

