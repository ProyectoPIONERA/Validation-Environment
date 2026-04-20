import json
import os
import shutil

from deployers.infrastructure.lib.config_loader import load_layered_deployer_config
from deployers.infrastructure.lib.paths import (
    legacy_deployer_artifact_dir,
    resolve_shared_artifact_dir,
    shared_artifact_dir,
    use_shared_deployer_artifacts,
)


class InesdataConfig:
    """Centralized INESData technical configuration."""

    REPO_DIR = os.path.join("deployers", "inesdata")
    ADAPTER_NAME = "inesdata"
    DS_NAME = "demo"
    NS_COMMON = "common-srvs"

    HELM_REPOS = {
        "minio": "https://charts.min.io/",
        "hashicorp": "https://helm.releases.hashicorp.com"
    }

    MINIKUBE_DRIVER = "docker"
    MINIKUBE_CPUS = 6
    MINIKUBE_MEMORY = 8192
    MINIKUBE_PROFILE = "minikube"
    MINIKUBE_ADDONS = ["ingress"]
    MINIKUBE_IP = "192.168.49.2"

    PORT_POSTGRES = 5432
    PORT_VAULT = 8200
    PORT_MINIO = 9000
    PORT_REGISTRATION_SERVICE = 18080

    TIMEOUT_POD_WAIT = 120
    TIMEOUT_PORT = 30
    TIMEOUT_NAMESPACE = 90

    PATH_VENV = ".venv"
    PATH_REQUIREMENTS = "requirements.txt"

    @classmethod
    def script_dir(cls):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    @classmethod
    def repo_dir(cls):
        return os.path.join(cls.script_dir(), cls.REPO_DIR)

    @classmethod
    def common_dir(cls):
        return resolve_shared_artifact_dir("common", required_file="Chart.yaml")

    @classmethod
    def values_path(cls):
        if cls.use_shared_deployer_artifacts():
            return os.path.join(cls.shared_runtime_dir("common"), "values.yaml")
        return os.path.join(cls.common_dir(), "values.yaml")

    @classmethod
    def common_values_source_path(cls):
        return os.path.join(cls.common_dir(), "values.yaml")

    @classmethod
    def ensure_common_values_file(cls):
        values_path = cls.values_path()
        if not cls.use_shared_deployer_artifacts():
            return values_path

        source_path = cls.common_values_source_path()
        if not os.path.exists(values_path) and os.path.exists(source_path):
            os.makedirs(os.path.dirname(values_path), exist_ok=True)
            shutil.copy2(source_path, values_path)
        return values_path

    @classmethod
    def deployer_config_path(cls):
        return os.path.join(cls.script_dir(), "deployers", cls.ADAPTER_NAME, "deployer.config")

    @classmethod
    def deployer_config_example_path(cls):
        return os.path.join(cls.script_dir(), "deployers", cls.ADAPTER_NAME, "deployer.config.example")

    @classmethod
    def infrastructure_deployer_config_path(cls):
        return os.path.join(cls.script_dir(), "deployers", "infrastructure", "deployer.config")

    @classmethod
    def infrastructure_deployer_config_example_path(cls):
        return os.path.join(cls.script_dir(), "deployers", "infrastructure", "deployer.config.example")

    @classmethod
    def legacy_deployer_config_path(cls):
        return os.path.join(cls.repo_dir(), "deployer.config")

    @classmethod
    def vault_keys_path(cls):
        if cls.use_shared_deployer_artifacts():
            return cls.vault_keys_runtime_path()
        return os.path.join(cls.common_dir(), "init-keys-vault.json")

    @classmethod
    def vault_keys_runtime_path(cls):
        return str(shared_artifact_dir("common", "init-keys-vault.json"))

    @classmethod
    def adapter_runtime_vault_keys_path(cls):
        return os.path.join(cls.shared_runtime_dir("common"), "init-keys-vault.json")

    @classmethod
    def legacy_vault_keys_path(cls):
        return str(legacy_deployer_artifact_dir("inesdata", "common", "init-keys-vault.json"))

    @classmethod
    def ensure_vault_keys_file(cls):
        vault_keys_path = cls.vault_keys_path()
        if not cls.use_shared_deployer_artifacts():
            return vault_keys_path

        if os.path.exists(vault_keys_path):
            return vault_keys_path

        candidate_paths = [
            cls.adapter_runtime_vault_keys_path(),
            cls.legacy_vault_keys_path(),
        ]
        for legacy_path in candidate_paths:
            if not os.path.exists(legacy_path):
                continue
            os.makedirs(os.path.dirname(vault_keys_path), exist_ok=True)
            shutil.copy2(legacy_path, vault_keys_path)
            break
        return vault_keys_path

    @classmethod
    def adapter_name(cls):
        return str(getattr(cls, "ADAPTER_NAME", "inesdata") or "inesdata").strip().lower()

    @classmethod
    def use_shared_deployer_artifacts(cls):
        return use_shared_deployer_artifacts()

    @classmethod
    def deployment_environment_name(cls):
        adapter = INESDataConfigAdapter(cls)
        config = adapter.load_deployer_config()
        environment = str(config.get("ENVIRONMENT", "DEV")).strip().upper()
        return environment or "DEV"

    @classmethod
    def deployment_runtime_dir(cls):
        return os.path.join(
            cls.script_dir(),
            "deployers",
            cls.adapter_name(),
            "deployments",
            cls.deployment_environment_name(),
            cls.dataspace_name(),
        )

    @classmethod
    def shared_runtime_dir(cls, *parts):
        return os.path.join(cls.deployment_runtime_dir(), "shared", *parts)

    @classmethod
    def venv_path(cls):
        return os.path.join(cls.repo_dir(), cls.PATH_VENV)

    @classmethod
    def python_exec(cls):
        return os.path.join(cls.venv_path(), "bin", "python")

    @classmethod
    def repo_requirements_path(cls):
        return os.path.join(cls.repo_dir(), cls.PATH_REQUIREMENTS)

    @classmethod
    def helm_release_common(cls):
        return "common-srvs"

    @classmethod
    def dataspace_name(cls):
        adapter = INESDataConfigAdapter(cls)
        return adapter.primary_dataspace_name()

    @classmethod
    def dataspace_namespace(cls):
        adapter = INESDataConfigAdapter(cls)
        return adapter.primary_dataspace_namespace()

    @classmethod
    def helm_release_rs(cls):
        return f"{cls.dataspace_name()}-dataspace-rs"

    @classmethod
    def namespace_demo(cls):
        return cls.dataspace_namespace()

    @classmethod
    def registration_service_dir(cls):
        return resolve_shared_artifact_dir("dataspace", "registration-service", required_file="Chart.yaml")

    @classmethod
    def registration_values_file(cls):
        values_name = f"values-{cls.dataspace_name()}.yaml"
        if cls.use_shared_deployer_artifacts():
            return os.path.join(cls.shared_runtime_dir("dataspace", "registration-service"), values_name)
        return os.path.join(cls.registration_service_dir(), values_name)

    @classmethod
    def legacy_registration_service_dir(cls):
        return str(legacy_deployer_artifact_dir("inesdata", "dataspace", "registration-service"))

    @classmethod
    def legacy_registration_values_file(cls):
        return os.path.join(cls.legacy_registration_service_dir(), f"values-{cls.dataspace_name()}.yaml")

    @classmethod
    def ensure_registration_values_file(cls, refresh=False):
        values_file = cls.registration_values_file()
        if not cls.use_shared_deployer_artifacts():
            return values_file

        source_file = cls.legacy_registration_values_file()
        if (refresh or not os.path.exists(values_file)) and os.path.exists(source_file):
            os.makedirs(os.path.dirname(values_file), exist_ok=True)
            shutil.copy2(source_file, values_file)
        return values_file

    @classmethod
    def registration_db_name(cls):
        return f"{cls.dataspace_name()}_rs"

    @classmethod
    def registration_db_user(cls):
        return f"{cls.dataspace_name()}_rsusr"

    @classmethod
    def webportal_db_name(cls):
        return f"{cls.dataspace_name()}_wp"

    @classmethod
    def webportal_db_user(cls):
        return f"{cls.dataspace_name()}_wpusr"

    @classmethod
    def connector_dir(cls):
        return os.path.join(cls.repo_dir(), "connector")

    @classmethod
    def connector_values_file(cls, connector_name):
        return os.path.join(cls.connector_dir(), f"values-{connector_name}.yaml")

    @classmethod
    def connector_credentials_path(cls, connector_name):
        return os.path.join(
            cls.repo_dir(),
            "deployments",
            "DEV",
            cls.dataspace_name(),
            f"credentials-connector-{connector_name}.json"
        )

    @classmethod
    def service_vault(cls):
        return f"{cls.NS_COMMON}-vault-0"

    @classmethod
    def service_postgres(cls):
        return f"{cls.NS_COMMON}-postgresql-0"

    @classmethod
    def service_minio(cls):
        return "minio"

    @classmethod
    def host_alias_domains(cls):
        ds_name = cls.dataspace_name()
        ds_domain = cls.ds_domain_base() or "dev.ds.dataspaceunit.upm"
        return [
            "keycloak.dev.ed.dataspaceunit.upm",
            "keycloak-admin.dev.ed.dataspaceunit.upm",
            "minio.dev.ed.dataspaceunit.upm",
            "console.minio-s3.dev.ed.dataspaceunit.upm",
            f"registration-service-{ds_name}.{ds_domain}"
        ]

    @classmethod
    def ds_domain_base(cls):
        adapter = INESDataConfigAdapter(cls)
        return adapter.ds_domain_base()


class INESDataConfigAdapter:
    """Contains INESData configuration access logic."""

    def __init__(self, config_cls=None):
        self.config = config_cls or InesdataConfig

    def copy_local_deployer_config(self):
        local_config = self.config.deployer_config_path()
        repo_config = self.config.legacy_deployer_config_path()

        if not os.path.exists(local_config):
            print(f"Local INESData deployer.config not found: {local_config}. Skipping copy.")
            return False

        if os.path.abspath(local_config) == os.path.abspath(repo_config):
            return True

        try:
            os.makedirs(os.path.dirname(repo_config), exist_ok=True)
            shutil.copy2(local_config, repo_config)
            print("Local INESData deployer.config copied into repository\n")
            return True
        except Exception as e:
            print(f"Error copying deployer.config: {e}")
            return False

    def _infrastructure_deployer_config_path(self):
        resolver = getattr(self.config, "infrastructure_deployer_config_path", None)
        if callable(resolver):
            return resolver()
        script_dir = getattr(self.config, "script_dir", None)
        if callable(script_dir):
            return os.path.join(script_dir(), "deployers", "infrastructure", "deployer.config")
        return ""

    def load_deployer_config(self):
        adapter_config_path = self.config.deployer_config_path()
        return load_layered_deployer_config(
            [
                self._infrastructure_deployer_config_path(),
                adapter_config_path,
            ]
        )

    @staticmethod
    def _resolve_optional_path(base_dir, raw_path):
        if not raw_path:
            return None

        candidate = str(raw_path).strip()
        if not candidate:
            return None

        if os.path.isabs(candidate):
            return candidate

        return os.path.abspath(os.path.join(base_dir, candidate))

    def kafka_runtime_config(self):
        """Return centralized Kafka runtime settings sourced from deployer.config."""
        config = self.load_deployer_config()
        base_dir = self.config.script_dir()

        runtime = {
            "bootstrap_servers": config.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            "topic_name": config.get("KAFKA_TOPIC_NAME", "kafka-stream-topic"),
            "topic_strategy": config.get("KAFKA_TOPIC_STRATEGY", "STATIC_TOPIC"),
            "security_protocol": config.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
            "container_name": config.get("KAFKA_CONTAINER_NAME", "kafka-local"),
            "container_image": config.get("KAFKA_CONTAINER_IMAGE", "confluentinc/cp-kafka:7.5.2"),
        }

        optional_mapping = {
            "sasl_mechanism": "KAFKA_SASL_MECHANISM",
            "username": "KAFKA_USERNAME",
            "password": "KAFKA_PASSWORD",
            "cluster_bootstrap_servers": "KAFKA_CLUSTER_BOOTSTRAP_SERVERS",
            "cluster_advertised_host": "KAFKA_CLUSTER_ADVERTISED_HOST",
            "message_count": "KAFKA_MESSAGE_COUNT",
            "message_size_bytes": "KAFKA_MESSAGE_SIZE_BYTES",
            "poll_timeout_seconds": "KAFKA_POLL_TIMEOUT_SECONDS",
            "consumer_group_prefix": "KAFKA_CONSUMER_GROUP_PREFIX",
            "request_timeout_ms": "KAFKA_REQUEST_TIMEOUT_MS",
            "api_timeout_ms": "KAFKA_API_TIMEOUT_MS",
            "max_block_ms": "KAFKA_MAX_BLOCK_MS",
            "consumer_request_timeout_ms": "KAFKA_CONSUMER_REQUEST_TIMEOUT_MS",
            "topic_ready_timeout_seconds": "KAFKA_TOPIC_READY_TIMEOUT_SECONDS",
        }
        for key, config_key in optional_mapping.items():
            value = config.get(config_key)
            if value not in (None, ""):
                runtime[key] = value

        container_env_file = self._resolve_optional_path(base_dir, config.get("KAFKA_CONTAINER_ENV_FILE"))
        if container_env_file:
            runtime["container_env_file"] = container_env_file

        return runtime

    def get_pg_credentials(self):
        config = self.load_deployer_config()
        return (
            config.get("PG_HOST", "localhost"),
            config.get("PG_USER", "postgres"),
            config.get("PG_PASSWORD")
        )

    def primary_dataspace_name(self):
        config = self.load_deployer_config()
        configured = (config.get("DS_1_NAME") or "").strip()
        if configured:
            return configured
        fallback = getattr(self.config, "DS_NAME", "demo")
        return (fallback or "demo").strip() or "demo"

    def primary_dataspace_namespace(self):
        config = self.load_deployer_config()
        configured = (config.get("DS_1_NAMESPACE") or "").strip()
        if configured:
            return configured
        return self.primary_dataspace_name()

    def generate_hosts(self, ds_name=None):
        config = self.load_deployer_config()
        ds_name = ds_name or self.primary_dataspace_name()
        hosts = []

        if config.get("KEYCLOAK_HOSTNAME"):
            hosts.append(f"127.0.0.1 {config.get('KEYCLOAK_HOSTNAME')}")

        if config.get("MINIO_HOSTNAME"):
            hosts.append(f"127.0.0.1 {config.get('MINIO_HOSTNAME')}")

        domain = config.get("DOMAIN_BASE")
        ds_domain = config.get("DS_DOMAIN_BASE")

        if domain:
            hosts.append(f"127.0.0.1 keycloak-admin.{domain}")
            hosts.append(f"127.0.0.1 console.minio-s3.{domain}")

        if ds_domain and ds_name:
            hosts.append(f"127.0.0.1 registration-service-{ds_name}.{ds_domain}")

        return hosts

    def generate_connector_hosts(self, connectors):
        config = self.load_deployer_config()
        ds_domain = config.get("DS_DOMAIN_BASE")
        if not ds_domain:
            return []

        hosts = []
        for connector in connectors or []:
            hosts.append(f"127.0.0.1 {connector}.{ds_domain}")
        return hosts

    def ds_domain_base(self):
        config = self.load_deployer_config()
        return config.get("DS_DOMAIN_BASE")

    def describe(self) -> str:
        return "INESDataConfigAdapter contains configuration logic for INESData."

