import json
import os
import re
import time

import requests
import yaml

from .config import INESDataConfigAdapter, InesdataConfig
from runtime_dependencies import ensure_python_requirements


class INESDataConnectorsAdapter:
    """Contains INESData connector lifecycle logic."""

    def __init__(self, run, run_silent, auto_mode_getter, infrastructure_adapter, config_adapter=None, config_cls=None):
        self.run = run
        self.run_silent = run_silent
        self.auto_mode_getter = auto_mode_getter
        self.infrastructure = infrastructure_adapter
        self.config = config_cls or InesdataConfig
        self.config_adapter = config_adapter or INESDataConfigAdapter(self.config)
        self._management_token_cache = {}

    def _auto_mode(self):
        return self.auto_mode_getter() if callable(self.auto_mode_getter) else bool(self.auto_mode_getter)

    @staticmethod
    def _fail(message, root_cause=None):
        if root_cause:
            raise RuntimeError(f"{message}. Root cause: {root_cause}")
        raise RuntimeError(message)

    def wait_for_keycloak_admin_ready(self, timeout=120, poll_interval=3):
        print("Waiting for Keycloak admin authentication to become ready...")
        deployer_config = self.config_adapter.load_deployer_config()
        kc_url = deployer_config.get("KC_URL")
        kc_user = deployer_config.get("KC_USER")
        kc_password = deployer_config.get("KC_PASSWORD")

        if not kc_url or not kc_user or not kc_password:
            print("Keycloak admin readiness check skipped: KC_URL/KC_USER/KC_PASSWORD missing")
            return False

        token_url = f"{kc_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
        last_issue = None
        start = time.time()

        while time.time() - start <= timeout:
            try:
                response = requests.post(
                    token_url,
                    data={
                        "grant_type": "password",
                        "client_id": "admin-cli",
                        "username": kc_user,
                        "password": kc_password,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=5,
                )
                if response.status_code == 200 and response.json().get("access_token"):
                    print("Keycloak admin authentication is ready")
                    return True
                last_issue = f"HTTP {response.status_code}"
            except Exception as exc:
                last_issue = str(exc)

            time.sleep(poll_interval)

        if last_issue:
            print(f"Keycloak admin authentication did not become ready: {last_issue}")
        else:
            print("Keycloak admin authentication did not become ready")
        return False

    def validate_connector_name(self, name):
        if not isinstance(name, str) or not name:
            raise ValueError("Connector name must be a non-empty string")

        if len(name) > 20:
            raise ValueError(f"Invalid connector name '{name}'. Maximum length is 20 characters.")

        if not re.match(r"^[A-Za-z][A-Za-z0-9]*$", name):
            raise ValueError(
                f"Invalid connector name '{name}'. Connector names must start with a letter and contain only alphanumeric characters."
            )

    def load_dataspace_connectors(self):
        deployer_config = self.config_adapter.load_deployer_config()
        dataspaces = []
        i = 1

        while True:
            ds_name = deployer_config.get(f"DS_{i}_NAME")
            ds_namespace = deployer_config.get(f"DS_{i}_NAMESPACE")
            connectors = deployer_config.get(f"DS_{i}_CONNECTORS")

            if not ds_name:
                break

            connector_list = []
            if connectors:
                for connector in connectors.split(","):
                    name = connector.strip()
                    if name:
                        self.validate_connector_name(name)
                        connector_list.append(f"conn-{name}-{ds_name}")

            dataspaces.append({
                "name": ds_name,
                "namespace": ds_namespace,
                "connectors": connector_list
            })
            i += 1

        return dataspaces

    def build_connector_hostnames(self, connectors):
        deployer_config = self.config_adapter.load_deployer_config()
        ds_domain = deployer_config.get("DS_DOMAIN_BASE")

        if not ds_domain:
            return []

        return [f"{connector}.{ds_domain}" for connector in connectors]

    def update_connector_host_aliases(self, values_file, connectors):
        minikube_ip = self.run("minikube ip", capture=True) or self.config.MINIKUBE_IP

        with open(values_file) as f:
            values = yaml.safe_load(f)

        hostnames = self.config.host_alias_domains()
        hostnames.extend(self.build_connector_hostnames(connectors))

        values["hostAliases"] = [{
            "ip": minikube_ip,
            "hostnames": hostnames
        }]

        with open(values_file, "w") as f:
            yaml.dump(values, f, sort_keys=False)

    def get_deployed_connectors(self, namespace):
        result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not result:
            return []

        connectors = []
        for line in result.splitlines():
            pod_name = line.split()[0]
            if pod_name.startswith("conn-") and "interface" not in pod_name:
                connector = pod_name.rsplit("-", 2)[0]
                if connector not in connectors:
                    connectors.append(connector)

        return connectors

    def connector_already_exists(self, connector_name, namespace):
        deployed = self.get_deployed_connectors(namespace)
        return connector_name in deployed

    def build_connector_url(self, connector_name):
        ds_domain = self.config_adapter.ds_domain_base()
        if not ds_domain:
            raise ValueError("DS_DOMAIN_BASE not defined in deployer.config")
        return f"http://{connector_name}.{ds_domain}/inesdata-connector-interface/"

    def wait_for_connector_ready(self, connector_name, timeout=300):
        print(f"Waiting for connector to be ready: {connector_name}")
        url = self.build_connector_url(connector_name)
        start = time.time()

        while True:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code in [200, 302]:
                    print(f"Connector ready: {connector_name}")
                    return True
            except Exception:
                pass

            if time.time() - start > timeout:
                print(f"Timeout waiting for connector: {connector_name}")
                return False

            time.sleep(3)

    def wait_for_management_api_ready(self, connector_name, timeout=180, poll_interval=3):
        print(f"Waiting for management API to be ready: {connector_name}")
        start = time.time()
        base_url = self.connector_base_url(connector_name)
        url = f"{base_url}/management/v3/assets/request"
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/"
            },
            "offset": 0,
            "limit": 1,
        }
        last_issue = None

        while time.time() - start <= timeout:
            headers = self.get_management_api_headers(connector_name)
            if not headers:
                last_issue = "could not obtain management API token"
                time.sleep(poll_interval)
                continue

            try:
                response = requests.post(url, headers=headers, json=payload, timeout=5)
                if response.status_code == 200:
                    print(f"Management API ready: {connector_name}")
                    return True
                last_issue = f"HTTP {response.status_code}"
            except Exception as exc:
                last_issue = str(exc)

            time.sleep(poll_interval)

        if last_issue:
            print(f"Management API not ready for {connector_name}: {last_issue}")
        else:
            print(f"Management API not ready for {connector_name}")
        return False

    def wait_for_all_connectors(self, connectors):
        print("\nWaiting for all connectors to become ready...\n")
        for connector in connectors:
            if not self.wait_for_connector_ready(connector):
                print(f"Connector not ready: {connector}")

    def load_connector_credentials(self, connector_name):
        creds_file = self.config.connector_credentials_path(connector_name)
        if not os.path.exists(creds_file):
            return None

        try:
            with open(creds_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def connector_base_url(self, connector):
        """Build base Management API URL for a connector."""
        domain = self.config.ds_domain_base()

        if not domain:
            raise ValueError("DS_DOMAIN_BASE not defined in deployer.config")

        return f"http://{connector}.{domain}"

    def get_management_api_auth(self, connector):
        """Get authentication credentials for connector management API."""
        creds = self.load_connector_credentials(connector)

        if not creds or "connector_user" not in creds:
            return None

        return (
            creds["connector_user"]["user"],
            creds["connector_user"]["passwd"]
        )

    def _keycloak_token_url(self):
        deployer_config = self.config_adapter.load_deployer_config()
        keycloak_url = deployer_config.get("KC_INTERNAL_URL") or deployer_config.get("KC_URL")
        if not keycloak_url:
            return None
        if not keycloak_url.startswith("http"):
            keycloak_url = f"http://{keycloak_url}"
        return f"{keycloak_url}/realms/{self.config.DS_NAME}/protocol/openid-connect/token"

    def get_management_api_token(self, connector):
        """Get a Bearer token for the connector management user."""
        if connector in self._management_token_cache:
            return self._management_token_cache[connector]

        auth = self.get_management_api_auth(connector)
        token_url = self._keycloak_token_url()
        if not auth or not token_url:
            return None

        try:
            response = requests.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": "dataspace-users",
                    "username": auth[0],
                    "password": auth[1],
                    "scope": "openid profile email",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            if response.status_code != 200:
                return None
            token = response.json().get("access_token")
            if token:
                self._management_token_cache[connector] = token
            return token
        except Exception:
            return None

    def get_management_api_headers(self, connector):
        """Build bearer-authenticated headers for the connector Management API."""
        token = self.get_management_api_token(connector)
        if not token:
            return None
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def asset_exists(self, connector, asset_id):
        headers = self.get_management_api_headers(connector)
        if not headers:
            return False

        base_url = self.connector_base_url(connector)
        url = f"{base_url}/management/v3/assets/{asset_id}"

        try:
            response = requests.get(url, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def policy_exists(self, connector, policy_id):
        headers = self.get_management_api_headers(connector)
        if not headers:
            return False

        base_url = self.connector_base_url(connector)
        url = f"{base_url}/management/v3/policydefinitions/{policy_id}"

        try:
            response = requests.get(url, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def contract_definition_exists(self, connector, contract_id):
        headers = self.get_management_api_headers(connector)
        if not headers:
            return False

        base_url = self.connector_base_url(connector)
        url = f"{base_url}/management/v3/contractdefinitions/{contract_id}"

        try:
            response = requests.get(url, headers=headers, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def delete_asset(self, connector, asset_id):
        headers = self.get_management_api_headers(connector)
        if not headers:
            return False

        base_url = self.connector_base_url(connector)
        url = f"{base_url}/management/v3/assets/{asset_id}"

        try:
            response = requests.delete(url, headers=headers, timeout=5)
            return response.status_code in (200, 204, 404)
        except Exception:
            return False

    def delete_policy(self, connector, policy_id):
        headers = self.get_management_api_headers(connector)
        if not headers:
            return False

        base_url = self.connector_base_url(connector)
        url = f"{base_url}/management/v3/policydefinitions/{policy_id}"

        try:
            response = requests.delete(url, headers=headers, timeout=5)
            return response.status_code in (200, 204, 404)
        except Exception:
            return False

    def delete_contract_definition(self, connector, contract_id):
        headers = self.get_management_api_headers(connector)
        if not headers:
            return False

        base_url = self.connector_base_url(connector)
        url = f"{base_url}/management/v3/contractdefinitions/{contract_id}"

        try:
            response = requests.delete(url, headers=headers, timeout=5)
            return response.status_code in (200, 204, 404)
        except Exception:
            return False

    def cleanup_test_entities(self, connector):
        """Clean up common validation test entities to keep tests idempotent."""
        test_entities = {
            "assets": [
                "test-asset-1",
                "test-asset-2",
                "asset-1",
                "asset-2",
                "test-document",
                "asset-test"
            ],
            "policies": [
                "test-policy-1",
                "test-policy-2",
                "policy-1",
                "policy-2",
                "use-eu",
                "policy-test"
            ],
            "contracts": [
                "test-contract-1",
                "test-contract-2",
                "contract-1",
                "contract-2",
                "contract-definition-1",
                "contract-test"
            ]
        }

        print(f"Cleaning up test entities from {connector}...")

        headers = self.get_management_api_headers(connector)
        if not headers:
            print(f"  Unable to authenticate against Management API for {connector}")
            print(f"Cleanup completed for {connector}\n")
            return

        for contract_id in test_entities["contracts"]:
            if self.delete_contract_definition(connector, contract_id):
                print(f"  Deleted contract definition: {contract_id}")
            else:
                print(f"  Could not delete contract definition: {contract_id}")

        for policy_id in test_entities["policies"]:
            if self.delete_policy(connector, policy_id):
                print(f"  Deleted policy: {policy_id}")
            else:
                print(f"  Could not delete policy: {policy_id}")

        for asset_id in test_entities["assets"]:
            if self.delete_asset(connector, asset_id):
                print(f"  Deleted asset: {asset_id}")
            else:
                print(f"  Could not delete asset: {asset_id}")

        print(f"Cleanup completed for {connector}\n")

    def validation_test_entities_absent(self, connector):
        """Return True only if the fixed validation entities are absent."""
        lingering_entities = []

        if self.asset_exists(connector, "asset-test"):
            lingering_entities.append("asset-test")
        if self.policy_exists(connector, "policy-test"):
            lingering_entities.append("policy-test")
        if self.contract_definition_exists(connector, "contract-test"):
            lingering_entities.append("contract-test")

        return len(lingering_entities) == 0, lingering_entities

    def display_connector_summary(self, connector_name):
        deployer_config = self.config_adapter.load_deployer_config()
        ds_domain = deployer_config.get("DS_DOMAIN_BASE")
        domain_base = deployer_config.get("DOMAIN_BASE")
        pg_host, _, _ = self.config_adapter.get_pg_credentials()
        minio_hostname = deployer_config.get("MINIO_HOSTNAME")

        if not ds_domain:
            return

        connector_root_url = f"http://{connector_name}.{ds_domain}"
        connector_interface_url = self.build_connector_url(connector_name)
        management_api_url = f"{connector_root_url}/management/v3"
        protocol_api_url = f"{connector_root_url}/protocol"
        creds = self.load_connector_credentials(connector_name)

        print(f"\n{'='*60}")
        print(f"CONNECTOR: {connector_name}")
        print(f"{'='*60}")
        print("\nURLs:")
        print(f"  Connector: {connector_root_url}")
        print(f"  Interface: {connector_interface_url}")
        print(f"  Management API: {management_api_url}")
        print(f"  Protocol API: {protocol_api_url}")

        if creds:
            print("\nConnector Credentials:")
            connector_user = creds.get("connector_user", {})
            print(f"  User: {connector_user.get('user', 'N/A')}")
            print(f"  Password: {connector_user.get('passwd', 'N/A')}")

            print("\nDatabase Credentials:")
            db_creds = creds.get("database", {})
            print(f"  Database: {db_creds.get('name', 'N/A')}")
            print(f"  User: {db_creds.get('user', 'N/A')}")
            print(f"  Password: {db_creds.get('passwd', 'N/A')}")
            print(f"  Host: {pg_host}")
            print(f"  DSN: postgresql://{pg_host}:5432/{db_creds.get('name', 'N/A')}")

            print("\nMinIO Credentials:")
            minio_creds = creds.get("minio", {})
            print(f"  User: {minio_creds.get('user', 'N/A')}")
            print(f"  Password: {minio_creds.get('passwd', 'N/A')}")
            print(f"  Access Key: {minio_creds.get('access_key', 'N/A')}")
            print(f"  Secret Key: {minio_creds.get('secret_key', 'N/A')}")
            if minio_hostname:
                print(f"  API URL: http://{minio_hostname}")
            if domain_base:
                print(f"  Console URL: http://console.minio-s3.{domain_base}")

        print(f"\n{'='*60}\n")

    def setup_minio_bucket(self, namespace, ds_name, connector_name, creds_file_path):
        print("\nConfiguring MinIO...")

        deployer_config = self.config_adapter.load_deployer_config()
        minio_endpoint = deployer_config.get("MINIO_ENDPOINT", "http://127.0.0.1:9000")
        minio_admin_user = deployer_config.get("MINIO_ADMIN_USER", "admin")
        minio_admin_pass = deployer_config.get("MINIO_ADMIN_PASS", "aPassword1234")

        minio_pod = self.infrastructure.get_pod_by_name(namespace, self.config.service_minio())
        if not minio_pod:
            print(f"Pod {self.config.service_minio()} not found")
            return False

        try:
            with open(creds_file_path) as f:
                creds = json.load(f)
        except FileNotFoundError:
            print(f"File not found: {creds_file_path}")
            return False

        minio_creds = creds.get("minio", {})
        mc = f"kubectl exec -n {namespace} {minio_pod} --"

        self.run(f"{mc} mc alias set minio {minio_endpoint} {minio_admin_user} {minio_admin_pass}", silent=True)
        self.run(f"{mc} mc mb minio/{ds_name}-{connector_name}", check=False)
        self.run(f"{mc} mc admin user add minio {connector_name} {minio_creds.get('passwd')}", silent=True)
        self.run(
            f"{mc} mc admin user svcacct add minio {connector_name} "
            f"--access-key {minio_creds.get('access_key')} --secret-key {minio_creds.get('secret_key')}",
            silent=True
        )

        print("MinIO configured")
        return True

    def force_clean_postgres_db(self, db_name, db_user):
        print(f"\nCleaning PostgreSQL database '{db_name}'...")

        pg_host, pg_user, pg_password = self.config_adapter.get_pg_credentials()
        terminate_sql = f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{db_name}';
        """

        self.run(
            f"PGPASSWORD={pg_password} psql -h {pg_host} -U {pg_user} -d postgres -c \"{terminate_sql}\"",
            check=False
        )
        self.run(
            f"PGPASSWORD={pg_password} psql -h {pg_host} -U {pg_user} -d postgres -c \"DROP DATABASE IF EXISTS {db_name};\"",
            check=False
        )
        self.run(
            f"PGPASSWORD={pg_password} psql -h {pg_host} -U {pg_user} -d postgres -c \"DROP ROLE IF EXISTS {db_user};\"",
            check=False
        )

        print("PostgreSQL cleanup complete\n")

    def create_connector(self, connector_name, connector_hostnames=None):
        print("\n========================================")
        print("LEVEL 4 - CREATE CONNECTOR")
        print("========================================\n")

        repo_dir = self.config.repo_dir()
        ds_name = self.config.DS_NAME
        python_exec = self.config.python_exec()

        if not os.path.exists(repo_dir):
            print("Repository not found. Run Level 2 first")
            return

        if not os.path.exists(self.config.venv_path()):
            print("Python environment not found. Run Level 3 first")
            return

        print("Ensuring INESData Python dependencies...")
        ensure_python_requirements(
            python_exec,
            self.config.repo_requirements_path(),
            label="INESData runtime",
        )

        if not self.infrastructure.ensure_local_infra_access():
            return

        if not self.infrastructure.ensure_vault_unsealed():
            return

        print(f"Cleaning connector: {connector_name}")
        self.run(f"{python_exec} deployer.py connector delete {connector_name} {ds_name}", cwd=repo_dir, check=False)

        connector_db = connector_name.replace("-", "_")
        self.force_clean_postgres_db(connector_db, connector_db)

        print("Cleaning registration-service database...")
        sql_del = (
            f"DELETE FROM public.edc_participant "
            f"WHERE participant_id = '{connector_name}';"
        )
        pg_host, pg_user, pg_pass = self.config_adapter.get_pg_credentials()
        self.run(
            f'PGPASSWORD={pg_pass} psql -h {pg_host} -U {pg_user} -d {self.config.registration_db_name()} -c "{sql_del}"',
            check=False
        )

        if not self.wait_for_keycloak_admin_ready():
            print("Keycloak admin API not ready for connector provisioning")
            return

        print(f"Creating connector {connector_name}...")
        create_cmd = f"{python_exec} deployer.py connector create {connector_name} {ds_name}"
        create_result = None
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            create_result = self.run(create_cmd, cwd=repo_dir, check=False)
            if create_result is not None:
                break
            if attempt < max_attempts:
                print(f"Connector creation failed on attempt {attempt}. Retrying after Keycloak readiness check...")
                if not self.wait_for_keycloak_admin_ready():
                    print("Keycloak admin API not ready for connector provisioning retry")
                    return
                time.sleep(5)

        if create_result is None:
            print("Error: deployment failed")
            return

        creds_path = self.config.connector_credentials_path(connector_name)
        if not self.setup_minio_bucket(self.config.NS_COMMON, ds_name, connector_name, creds_path):
            print("Warning: MinIO configuration incomplete")

        values_file = self.config.connector_values_file(connector_name)
        timeout = 10
        start = time.time()

        while not os.path.exists(values_file):
            if time.time() - start > timeout:
                print("Timeout waiting for values file generation")
                return
            time.sleep(1)

        if not os.path.exists(values_file):
            print("Connector values file not found")
            return

        connector_hostnames = connector_hostnames or [connector_name]
        self.update_connector_host_aliases(values_file, connector_hostnames)

        release_name = f"{connector_name}-{ds_name}"
        print(f"Deploying connector {connector_name}...")

        if not self.infrastructure.deploy_helm_release(
            release_name,
            self.config.namespace_demo(),
            os.path.basename(values_file),
            cwd=self.config.connector_dir()
        ):
            print("Error deploying connector")
            return

        if not self.infrastructure.wait_for_namespace_pods(self.config.namespace_demo()):
            print("Timeout waiting for connector pods")
            return

        print("\nCONNECTORS CREATED\n")

    def connector_is_healthy(self, connector_name, namespace):
        result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not result:
            return False

        for line in result.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            pod_name = parts[0]
            status = parts[2]
            if pod_name.startswith(connector_name):
                if status == "Running":
                    return True
                print(f"Connector pod unhealthy: {pod_name} ({status})")
                return False

        return False

    def validate_connectors_deployment(self, connectors):
        namespace = self.config.namespace_demo()

        print("\n========================================")
        print("VALIDATING CONNECTOR DEPLOYMENT")
        print("========================================\n")

        pods = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not pods:
            print("No pods found in namespace")
            return False

        failed = False
        for line in pods.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            pod_name = parts[0]
            status = parts[2]
            if "conn-" in pod_name and "interface" not in pod_name and status != "Running":
                print(f"Connector pod not running: {pod_name} ({status})")
                failed = True

        if failed:
            print("\nSome connectors are not running\n")
            self.run(f"kubectl get pods -n {namespace}", check=False)
            return False

        print("All connector pods are running\n")

        for connector in connectors:
            print(f"Checking HTTP availability: {connector}")
            if not self.wait_for_connector_ready(connector):
                print(f"Connector not reachable: {connector}")
                return False

            print(f"Checking Management API availability: {connector}")
            if not self.wait_for_management_api_ready(connector):
                print(f"Management API not reachable: {connector}")
                return False

        print("\nAll connectors reachable\n")
        return True

    def show_connector_logs(self):
        namespace = self.config.DS_NAME
        pods = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not pods:
            print("No pods found in namespace")
            return

        connector_pods = []
        for line in pods.splitlines():
            pod_name = line.split()[0]
            if "conn-" in pod_name and "interface" not in pod_name:
                connector_pods.append(pod_name)

        if not connector_pods:
            print("No connectors deployed")
            return

        print("Available connectors:\n")
        for i, pod in enumerate(connector_pods, 1):
            print(f"{i} - {pod}")

        choice = input("\nSelect connector for logs (number): ")
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(connector_pods):
            print("Invalid selection")
            return

        selected_pod = connector_pods[int(choice) - 1]
        follow = input("Follow logs in real-time? (Y/N): ").strip().upper()

        if follow == "Y":
            self.run(f"kubectl logs -f {selected_pod} -n {namespace}", check=False)
        else:
            self.run(f"kubectl logs {selected_pod} -n {namespace}", check=False)

    def deploy_connectors(self):
        print("\n========================================")
        print("DEPLOY CONNECTORS FROM CONFIG")
        print("========================================\n")

        dataspaces = self.load_dataspace_connectors()
        if not dataspaces:
            print("No dataspaces defined in deployer.config")
            return []

        all_connectors = set()

        for ds in dataspaces:
            ds_name = ds["name"]
            namespace = ds["namespace"]
            connectors = ds["connectors"]

            print(f"\nDataspace: {ds_name}")
            print(f"Namespace: {namespace}")
            print(f"Connectors defined: {connectors}\n")

            for connector in connectors:
                all_connectors.add(connector)

                if self.connector_already_exists(connector, namespace):
                    if self.connector_is_healthy(connector, namespace):
                        print(f"Connector already running: {connector}")
                        print("Skipping deployment\n")
                        continue
                    print(f"Connector exists but unhealthy. Redeploying: {connector}")

                print(f"Deploying connector: {connector}")
                values_file = self.config.connector_values_file(connector)
                self.create_connector(connector, connectors)

                if not os.path.exists(values_file):
                    print(f"Values file not found: {values_file}")
                    return []

        all_connectors = list(all_connectors)
        print("\nAll connectors deployed or already existing\n")
        print("Configuring connector hosts...")
        connector_hosts = self.config_adapter.generate_connector_hosts(all_connectors)
        self.infrastructure.manage_hosts_entries(connector_hosts)
        self.wait_for_all_connectors(all_connectors)
        return all_connectors

    def get_cluster_connectors(self):
        namespace = self.config.namespace_demo()
        output = self.run(f"kubectl get pods -n {namespace} --no-headers", capture=True)
        if not output:
            return []

        connectors = set()
        for line in output.splitlines():
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            if name.startswith("conn-") and "interface" not in name:
                connectors.add("-".join(name.split("-")[:3]))

        return sorted(connectors)

    def describe(self) -> str:
        return "INESDataConnectorsAdapter contains connector logic for INESData."

