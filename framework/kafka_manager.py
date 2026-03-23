import os
import socket
import time

from .kafka_container_factory import KafkaContainerFactory
from .kafka_testcontainer import FrameworkKafkaContainer


class KafkaManager:
    """Ensures a Kafka broker is available for optional benchmarks."""

    def __init__(
        self,
        bootstrap_servers=None,
        runtime_config=None,
        adapter_config_loader=None,
        container_class=None,
        container_factory=None,
        image="confluentinc/cp-kafka:latest",
        wait_timeout_seconds=60,
        poll_interval_seconds=1,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.runtime_config = runtime_config or {}
        self.adapter_config_loader = adapter_config_loader
        self.container_class = container_class
        self.container_factory = container_factory or KafkaContainerFactory()
        self.image = image
        self.wait_timeout_seconds = wait_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.container = None
        self.started_by_framework = False
        self.last_error = None
        self.cluster_bootstrap_servers = None

    def _load_adapter_config(self):
        if callable(self.adapter_config_loader):
            config = self.adapter_config_loader()
            return config if isinstance(config, dict) else {}
        if isinstance(self.adapter_config_loader, dict):
            return self.adapter_config_loader
        return {}

    def _candidate_bootstrap_servers(self):
        candidates = []
        env_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
        adapter_bootstrap = self._load_adapter_config().get("bootstrap_servers")
        runtime_bootstrap = self.runtime_config.get("bootstrap_servers")

        for candidate in (env_bootstrap, runtime_bootstrap, adapter_bootstrap, self.bootstrap_servers):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    def _load_manager_config(self):
        config = {}
        config.update(self._load_adapter_config())
        config.update(self.runtime_config)
        config.setdefault("cluster_advertised_host", config.get("cluster_advertised_host") or "host.docker.internal")
        return config

    @staticmethod
    def _normalize_bootstrap_servers(bootstrap_servers):
        if bootstrap_servers is None:
            return []
        if isinstance(bootstrap_servers, (list, tuple, set)):
            values = bootstrap_servers
        else:
            values = str(bootstrap_servers).split(",")
        return [value.strip() for value in values if str(value).strip()]

    @staticmethod
    def _parse_host_port(address):
        address = str(address).strip()
        if "://" in address:
            address = address.split("://", 1)[1]
        if address.count(":") > 1 and address.startswith("["):
            host, _, port = address.rpartition(":")
            return host.strip("[]"), int(port or 9092)
        if ":" in address:
            host, port = address.rsplit(":", 1)
            return host, int(port or 9092)
        return address, 9092

    @classmethod
    def is_kafka_available(cls, bootstrap_servers):
        """Attempt a basic TCP connection to determine broker availability."""
        for address in cls._normalize_bootstrap_servers(bootstrap_servers):
            try:
                host, port = cls._parse_host_port(address)
                with socket.create_connection((host, port), timeout=2):
                    return True
            except Exception:
                continue
        return False

    def _load_container_class(self):
        if self.container_class is not None:
            return self.container_class

        try:
            return FrameworkKafkaContainer
        except Exception as exc:
            raise RuntimeError(
                f"testcontainers Kafka support is not available: {exc}"
            ) from exc

    def start_kafka(self):
        """Start a Kafka container and wait until the broker becomes available."""
        container_class = self._load_container_class()
        container = self.container_factory.create_container(
            container_class,
            self.image,
            config=self._load_manager_config(),
        )
        container.start()

        bootstrap_servers = None
        get_bootstrap_server = getattr(container, "get_bootstrap_server", None)
        get_cluster_bootstrap_server = getattr(container, "get_cluster_bootstrap_server", None)
        if callable(get_bootstrap_server):
            bootstrap_servers = get_bootstrap_server()
        else:
            bootstrap_servers = getattr(container, "bootstrap_servers", None)
        cluster_bootstrap_servers = None
        if callable(get_cluster_bootstrap_server):
            cluster_bootstrap_servers = get_cluster_bootstrap_server()

        deadline = time.time() + self.wait_timeout_seconds
        while time.time() < deadline:
            if bootstrap_servers and self.is_kafka_available(bootstrap_servers):
                self.container = container
                self.started_by_framework = True
                self.bootstrap_servers = bootstrap_servers
                self.cluster_bootstrap_servers = cluster_bootstrap_servers
                self.last_error = None
                return bootstrap_servers
            time.sleep(self.poll_interval_seconds)

        stop_method = getattr(container, "stop", None)
        if callable(stop_method):
            stop_method()
        raise RuntimeError("Kafka container started but broker did not become available in time")

    def ensure_kafka_running(self):
        """Return reachable bootstrap servers or try to auto-start Kafka."""
        previous_bootstrap_servers = self.bootstrap_servers
        previous_cluster_bootstrap_servers = self.cluster_bootstrap_servers
        previous_started_by_framework = self.started_by_framework
        for candidate in self._candidate_bootstrap_servers():
            if self.is_kafka_available(candidate):
                self.bootstrap_servers = candidate
                explicit_cluster_bootstrap_servers = self._load_manager_config().get("cluster_bootstrap_servers")
                if explicit_cluster_bootstrap_servers:
                    self.cluster_bootstrap_servers = explicit_cluster_bootstrap_servers
                elif candidate == previous_bootstrap_servers and previous_cluster_bootstrap_servers:
                    self.cluster_bootstrap_servers = previous_cluster_bootstrap_servers
                else:
                    self.cluster_bootstrap_servers = None
                self.started_by_framework = (
                    previous_started_by_framework and candidate == previous_bootstrap_servers and self.container is not None
                )
                self.last_error = None
                return candidate

        try:
            return self.start_kafka()
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[WARNING] Kafka auto-provisioning failed: {exc}")
            return None

    def stop_kafka(self):
        """Stop the Kafka container only if it was started by the framework."""
        if not self.started_by_framework or self.container is None:
            return

        try:
            stop_method = getattr(self.container, "stop", None)
            if callable(stop_method):
                stop_method()
        except Exception as exc:
            print(f"[WARNING] Failed to stop Kafka container cleanly: {exc}")
        finally:
            self.container = None
            self.started_by_framework = False
            self.cluster_bootstrap_servers = None

    def describe(self) -> str:
        return "KafkaManager ensures a Kafka broker is available for benchmarks."

