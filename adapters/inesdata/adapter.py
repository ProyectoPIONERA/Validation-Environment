"""Stable INESData adapter facade import path."""

import os
import shlex
import socket
import subprocess

from .config import INESDataConfigAdapter, InesdataConfig
from .connectors import INESDataConnectorsAdapter
from .deployment import INESDataDeploymentAdapter
from .infrastructure import INESDataInfrastructureAdapter


class InesdataAdapter:
    """Facade for all INESData-specific deployment and cluster operations."""

    @staticmethod
    def _default_run(cmd, capture=False, silent=False, check=True, cwd=None):
        if not silent:
            print(f"\nExecuting: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                text=True,
                capture_output=capture,
                cwd=cwd
            )

            if result.returncode != 0:
                if check:
                    print(f"Command failed with exit code {result.returncode}")
                return None

            if capture:
                return result.stdout.strip()

            return result
        except Exception as e:
            print(f"Execution error: {e}")
            return None

    @classmethod
    def _default_run_silent(cls, cmd, cwd=None):
        return cls._default_run(cmd, capture=True, silent=True, check=False, cwd=cwd)

    def __init__(self, run=None, run_silent=None, auto_mode_getter=lambda: False, config_cls=None, dry_run=False):
        run = run or self._default_run
        run_silent = run_silent or self._default_run_silent
        self.run = run
        self.run_silent = run_silent
        self.auto_mode_getter = auto_mode_getter
        self.dry_run = dry_run
        self.config = config_cls or InesdataConfig
        self.config_adapter = INESDataConfigAdapter(self.config)
        self.infrastructure = INESDataInfrastructureAdapter(
            run=run,
            run_silent=run_silent,
            auto_mode_getter=auto_mode_getter,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        self.deployment = INESDataDeploymentAdapter(
            run=run,
            run_silent=run_silent,
            auto_mode_getter=auto_mode_getter,
            infrastructure_adapter=self.infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        self.connectors = INESDataConnectorsAdapter(
            run=run,
            run_silent=run_silent,
            auto_mode_getter=auto_mode_getter,
            infrastructure_adapter=self.infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        self.deployment.connectors_adapter = self.connectors
        self.connectors.deployment_adapter = self.deployment

    def setup_cluster(self):
        return self.infrastructure.setup_cluster()

    def deploy_infrastructure(self):
        return self.infrastructure.deploy_infrastructure()

    def deploy_dataspace(self):
        return self.deployment.deploy_dataspace()

    def deploy_connectors(self):
        return self.connectors.deploy_connectors()

    def wait_for_all_connectors(self, connectors):
        return self.connectors.wait_for_all_connectors(connectors)

    def get_cluster_connectors(self):
        return self.connectors.get_cluster_connectors()

    def load_deployer_config(self):
        return self.config_adapter.load_deployer_config()

    def load_connector_credentials(self, connector_name):
        return self.connectors.load_connector_credentials(connector_name)

    def build_connector_url(self, connector_name):
        return self.connectors.build_connector_url(connector_name)

    def cleanup_test_entities(self, connector_name):
        return self.connectors.cleanup_test_entities(connector_name)

    def _kafka_runtime_config(self):
        loader = getattr(self.config_adapter, "kafka_runtime_config", None)
        if callable(loader):
            config = loader()
            if isinstance(config, dict):
                return dict(config)
        return {}

    def _kafka_container_name(self):
        return self._kafka_runtime_config().get("container_name", "kafka-local")

    def _kafka_bootstrap_servers(self):
        return self._kafka_runtime_config().get("bootstrap_servers", "localhost:9092")

    @staticmethod
    def _parse_kafka_address(address):
        address = str(address or "").strip()
        if "://" in address:
            address = address.split("://", 1)[1]
        if address.count(":") > 1 and address.startswith("["):
            host, _, port = address.rpartition(":")
            return host.strip("[]"), int(port or 9092)
        if ":" in address:
            host, port = address.rsplit(":", 1)
            return host, int(port or 9092)
        return address, 9092

    def _is_kafka_bootstrap_reachable(self):
        bootstrap_servers = self._kafka_bootstrap_servers()
        for candidate in str(bootstrap_servers or "").split(","):
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                host, port = self._parse_kafka_address(candidate)
                with socket.create_connection((host, port), timeout=2):
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _load_kafka_admin_dependencies():
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError

        return KafkaAdminClient, NewTopic, TopicAlreadyExistsError

    def _kafka_admin_config(self):
        runtime = self.get_kafka_config()
        config = {
            "bootstrap_servers": runtime.get("bootstrap_servers", "localhost:9092"),
            "client_id": "inesdata-framework-topic-admin",
        }

        security_protocol = runtime.get("security_protocol")
        if security_protocol:
            config["security_protocol"] = security_protocol

        sasl_mechanism = runtime.get("sasl_mechanism")
        if sasl_mechanism:
            config["sasl_mechanism"] = sasl_mechanism

        username = runtime.get("username")
        password = runtime.get("password")
        if username not in (None, ""):
            config["sasl_plain_username"] = username
        if password not in (None, ""):
            config["sasl_plain_password"] = password

        return config

    def _ensure_kafka_topic_via_admin(self, topic_name):
        kafka_admin_client, new_topic_cls, topic_exists_exc = self._load_kafka_admin_dependencies()
        admin_client = kafka_admin_client(**self._kafka_admin_config())
        created = False

        try:
            existing_topics = set(admin_client.list_topics() or [])
            if topic_name in existing_topics:
                print(f"Kafka topic '{topic_name}' already exists")
                return True

            topic = new_topic_cls(name=topic_name, num_partitions=1, replication_factor=1)
            try:
                admin_client.create_topics([topic])
                created = True
            except topic_exists_exc:
                pass

            existing_topics = set(admin_client.list_topics() or [])
            if topic_name in existing_topics:
                if created:
                    print(f"Created Kafka topic: {topic_name}")
                else:
                    print(f"Kafka topic '{topic_name}' already exists")
                return True

            print(f"Kafka topic '{topic_name}' could not be verified after creation")
            return False
        finally:
            close_method = getattr(admin_client, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    pass

    def _resolve_kafka_container_id(self):
        container_name = self._kafka_container_name()
        result = self.run_silent(
            f"docker ps --filter name={shlex.quote(container_name)} --format '{{{{.ID}}}}'"
        )
        if not result:
            return None
        return result.splitlines()[0].strip() or None

    def is_kafka_available(self):
        """Check if Kafka container is running and accessible."""
        try:
            return self._is_kafka_bootstrap_reachable() or bool(self._resolve_kafka_container_id())
        except Exception:
            return False

    def ensure_kafka_topic(self, topic_name="kafka-stream-topic"):
        """Ensure Kafka topic exists, creating it when necessary."""
        try:
            return self._ensure_kafka_topic_via_admin(topic_name)
        except Exception as exc:
            print(f"Kafka admin topic ensure failed via bootstrap servers: {exc}")

        if not self.is_kafka_available():
            print("Kafka container not running")
            return False

        try:
            container_id = self._resolve_kafka_container_id()
            bootstrap_servers = self._kafka_bootstrap_servers()
            if not container_id:
                print("Kafka container id could not be resolved")
                return False

            result = self.run_silent(
                f"docker exec {shlex.quote(container_id)} "
                f"kafka-topics --list --bootstrap-server {shlex.quote(bootstrap_servers)}"
            )

            if result and topic_name in result:
                print(f"Kafka topic '{topic_name}' already exists")
                return True

            self.run_silent(
                f"docker exec {shlex.quote(container_id)} "
                f"kafka-topics --create --topic {shlex.quote(topic_name)} "
                f"--bootstrap-server {shlex.quote(bootstrap_servers)} "
                f"--partitions 1 --replication-factor 1"
            )

            print(f"Created Kafka topic: {topic_name}")
            return True
        except Exception as exc:
            print(f"Error managing Kafka topic: {exc}")
            return False

    def get_kafka_config(self):
        """Return centralized Kafka configuration for local INESData setups."""
        config = self._kafka_runtime_config()

        optional_env_mapping = {
            "security_protocol": "KAFKA_SECURITY_PROTOCOL",
            "sasl_mechanism": "KAFKA_SASL_MECHANISM",
            "username": "KAFKA_USERNAME",
            "password": "KAFKA_PASSWORD",
            "container_env_file": "KAFKA_CONTAINER_ENV_FILE",
        }
        for key, env_name in optional_env_mapping.items():
            value = os.getenv(env_name)
            if key not in config and value not in (None, ""):
                config[key] = value

        return config

    def describe(self) -> str:
        return (
            "InesdataAdapter encapsulates Kubernetes, Helm, Vault, MinIO, "
            "connector and inesdata-deployment logic for INESData."
        )


__all__ = [
    "InesdataAdapter",
    "InesdataConfig",
    "INESDataConfigAdapter",
    "INESDataInfrastructureAdapter",
    "INESDataDeploymentAdapter",
    "INESDataConnectorsAdapter",
]
