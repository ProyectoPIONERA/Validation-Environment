"""Stable INESData adapter facade import path."""

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

    def is_kafka_available(self):
        """Check if Kafka container is running and accessible."""
        try:
            result = self.run_silent("docker ps --filter name=kafka --format '{{.Names}}'")
            return bool(result and "kafka" in result.lower())
        except Exception:
            return False

    def ensure_kafka_topic(self, topic_name="kafka-stream-topic"):
        """Ensure Kafka topic exists, creating it when necessary."""
        if not self.is_kafka_available():
            print("Kafka container not running")
            return False

        try:
            result = self.run_silent(
                f"docker exec $(docker ps -q --filter name=kafka) "
                f"kafka-topics --list --bootstrap-server localhost:9092"
            )

            if result and topic_name in result:
                print(f"Kafka topic '{topic_name}' already exists")
                return True

            self.run_silent(
                f"docker exec $(docker ps -q --filter name=kafka) "
                f"kafka-topics --create --topic {topic_name} "
                f"--bootstrap-server localhost:9092 "
                f"--partitions 1 --replication-factor 1"
            )

            print(f"Created Kafka topic: {topic_name}")
            return True
        except Exception as exc:
            print(f"Error managing Kafka topic: {exc}")
            return False

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
