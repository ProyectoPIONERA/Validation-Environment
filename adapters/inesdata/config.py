import json
import os
import shutil


class InesdataConfig:
    """Centralized INESData technical configuration."""

    REPO_URL = "https://github.com/ProyectoPIONERA/inesdata-testing.git"
    REPO_DIR = "inesdata-testing"
    DS_NAME = "demo"
    NS_COMMON = "common-srvs"

    HELM_REPOS = {
        "minio": "https://charts.min.io/",
        "hashicorp": "https://helm.releases.hashicorp.com"
    }

    MINIKUBE_DRIVER = "docker"
    MINIKUBE_CPUS = 4
    MINIKUBE_MEMORY = 4400
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
        return os.path.join(cls.repo_dir(), "common")

    @classmethod
    def values_path(cls):
        return os.path.join(cls.common_dir(), "values.yaml")

    @classmethod
    def deployer_config_path(cls):
        return os.path.join(cls.repo_dir(), "deployer.config")

    @classmethod
    def vault_keys_path(cls):
        return os.path.join(cls.common_dir(), "init-keys-vault.json")

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
    def helm_release_rs(cls):
        return f"{cls.DS_NAME}-dataspace-rs"

    @classmethod
    def namespace_demo(cls):
        return cls.DS_NAME

    @classmethod
    def registration_service_dir(cls):
        return os.path.join(cls.repo_dir(), "dataspace", "registration-service")

    @classmethod
    def registration_values_file(cls):
        return os.path.join(cls.registration_service_dir(), f"values-{cls.DS_NAME}.yaml")

    @classmethod
    def registration_db_name(cls):
        return f"{cls.DS_NAME}_rs"

    @classmethod
    def registration_db_user(cls):
        return f"{cls.DS_NAME}_rsusr"

    @classmethod
    def webportal_db_name(cls):
        return f"{cls.DS_NAME}_wp"

    @classmethod
    def webportal_db_user(cls):
        return f"{cls.DS_NAME}_wpusr"

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
            cls.DS_NAME,
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
        return [
            "keycloak.dev.ed.dataspaceunit.upm",
            "keycloak-admin.dev.ed.dataspaceunit.upm",
            "minio.dev.ed.dataspaceunit.upm",
            "console.minio-s3.dev.ed.dataspaceunit.upm",
            f"registration-service-{cls.DS_NAME}.dev.ds.dataspaceunit.upm"
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
        local_config = os.path.join(self.config.script_dir(), "deployer.config")
        repo_config = self.config.deployer_config_path()

        if not os.path.exists(local_config):
            print("Local deployer.config not found. Skipping copy.")
            return False

        try:
            shutil.copy2(local_config, repo_config)
            print("Local deployer.config copied into repository\n")
            return True
        except Exception as e:
            print(f"Error copying deployer.config: {e}")
            return False

    def load_deployer_config(self):
        config_path = self.config.deployer_config_path()
        values = {}

        try:
            with open(config_path) as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        values[key.strip()] = value.strip()
        except FileNotFoundError:
            print(f"Error: Configuration file not found: {config_path}")
            return values
        except IOError as e:
            print(f"Error reading configuration file: {e}")
            return values

        return values

    def get_pg_credentials(self):
        config = self.load_deployer_config()
        return (
            config.get("PG_HOST", "localhost"),
            config.get("PG_USER", "postgres"),
            config.get("PG_PASSWORD")
        )

    def generate_hosts(self, ds_name=None):
        config = self.load_deployer_config()
        ds_name = ds_name or self.config.DS_NAME
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

    def ds_domain_base(self):
        config = self.load_deployer_config()
        return config.get("DS_DOMAIN_BASE")

    def describe(self) -> str:
        return "INESDataConfigAdapter contains configuration logic for INESData."

