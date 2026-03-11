import json
import os
import socket
import subprocess
import time
import requests

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
from tabulate import tabulate

from .config import INESDataConfigAdapter, InesdataConfig


yaml_ruamel = YAML()
yaml_ruamel.preserve_quotes = True
yaml_ruamel.indent(mapping=2, sequence=4, offset=2)


class INESDataInfrastructureAdapter:
    """Contains INESData infrastructure logic."""

    def __init__(self, run, run_silent, auto_mode_getter, config_adapter=None, config_cls=None):
        self.run = run
        self.run_silent = run_silent
        self.auto_mode_getter = auto_mode_getter
        self.config = config_cls or InesdataConfig
        self.config_adapter = config_adapter or INESDataConfigAdapter(self.config)
        self._last_registration_service_liquibase_issue = None

    def _auto_mode(self):
        return self.auto_mode_getter() if callable(self.auto_mode_getter) else bool(self.auto_mode_getter)

    @staticmethod
    def _fail(message, root_cause=None):
        if root_cause:
            raise RuntimeError(f"{message}. Root cause: {root_cause}")
        raise RuntimeError(message)

    def ensure_unix_environment(self):
        if os.name == "nt":
            print("Script must run on Linux, macOS, or WSL")
            raise SystemExit(1)

    def is_wsl(self):
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except Exception:
            return False

    def ensure_wsl_docker_config(self):
        if not self.is_wsl():
            return True

        docker_config_path = os.path.expanduser("~/.docker/config.json")
        print("\nWSL detected: validating Docker client config...")

        if not os.path.exists(docker_config_path):
            print("Docker config not found. Skipping WSL Docker config adjustment.")
            return True

        try:
            with open(docker_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError:
            print(f"Docker config is not valid JSON: {docker_config_path}")
            print("Skipping automatic adjustment.")
            return True
        except OSError as e:
            print(f"Could not read Docker config ({docker_config_path}): {e}")
            return True

        if not isinstance(config, dict):
            print(f"Docker config has unexpected format in {docker_config_path}")
            print("Skipping automatic adjustment.")
            return True

        if config.get("credsStore") != "desktop":
            print("No WSL Docker credsStore adjustment required.")
            return True

        config.pop("credsStore", None)
        try:
            with open(docker_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
                f.write("\n")
        except OSError as e:
            print(f"Could not write Docker config ({docker_config_path}): {e}")
            return False

        print(f"Removed credsStore=desktop from {docker_config_path}")
        return True

    def get_hosts_path(self):
        import sys

        if self.is_wsl():
            return "/mnt/c/Windows/System32/drivers/etc/hosts"
        if sys.platform.startswith("linux"):
            return "/etc/hosts"
        if sys.platform == "darwin":
            return "/private/etc/hosts"
        return None

    def manage_hosts_entries(self, desired_entries):
        hosts_path = self.get_hosts_path()

        if not hosts_path:
            print("OS not supported for automatic hosts modification")
            return

        print(f"\nHosts file: {hosts_path}")

        try:
            with open(hosts_path, "r") as f:
                content = f.read()
        except PermissionError:
            print("Permission denied reading hosts file")
            return

        existing = [entry for entry in desired_entries if entry in content]
        missing = [entry for entry in desired_entries if entry not in content]

        print("\nExisting entries:")
        for entry in existing or ["None"]:
            if entry:
                print(f"  {entry}")

        print("\nMissing entries:")
        for entry in missing or ["None"]:
            if entry:
                print(f"  {entry}")

        if not missing:
            print("\nNo modifications needed to hosts file")
            return

        if self._auto_mode():
            choice = "Y"
            print("\n[AUTO_MODE] Automatically adding entries to hosts file")
        else:
            choice = input("\nAdd missing entries to hosts file? (Y/N): ").strip().upper()

        if choice != "Y":
            print("No changes made to hosts file")
            return

        try:
            with open(hosts_path, "a") as f:
                f.write("\n# Dataspace Local Deployment\n")
                for line in missing:
                    f.write(line + "\n")
            print("Entries added successfully")
        except PermissionError:
            print("Permission denied writing to hosts file. Run with sudo.")

    def deploy_helm_release(self, release_name, namespace, values_file="values.yaml", cwd=None):
        print("Executing helm upgrade --install...")

        cmd = (
            f"helm upgrade --install {release_name} . "
            f"-n {namespace} "
            f"--create-namespace "
            f"-f {values_file} "
        )

        result = self.run(cmd, check=False, cwd=cwd)

        if result is None:
            print("Helm deployment failed")
            return False

        print("Release deployed successfully")
        return True

    def add_helm_repos(self):
        print("\nAdding Helm repositories...")
        for name, url in self.config.HELM_REPOS.items():
            self.run(f"helm repo add {name} {url}", check=False)
        self.run("helm repo update", check=False)

    def get_pod_by_name(self, namespace, pod_pattern):
        result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")

        if not result:
            return None

        for line in result.splitlines():
            if pod_pattern in line:
                return line.split()[0]

        return None

    def wait_for_pod_running(self, pod_name, namespace, timeout=None):
        timeout = timeout or self.config.TIMEOUT_NAMESPACE
        print(f"Waiting for pod {pod_name} to be running...")
        start = time.time()

        while True:
            result = self.run_silent(f"kubectl get pod {pod_name} -n {namespace} --no-headers")

            if result:
                cols = result.split()
                if len(cols) > 2 and cols[2] == "Running":
                    print(f"Pod {pod_name} is running")
                    return True

            if time.time() - start > timeout:
                print(f"Timeout waiting for pod {pod_name}")
                return False

            time.sleep(1)

    def wait_for_pods(self, namespace, timeout=None):
        timeout = timeout or self.config.TIMEOUT_POD_WAIT
        print(f"\nWaiting for pods in namespace '{namespace}' to be ready...")
        start_time = time.time()

        while True:
            result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")

            if not result:
                time.sleep(2)
                continue

            all_ready = True

            for line in result.splitlines():
                columns = line.split()
                name = columns[0]
                ready = columns[1] if len(columns) > 1 else ""
                status = columns[2]

                if status in ["CrashLoopBackOff", "Error", "ImagePullBackOff"]:
                    print(f"\nPod in error state: {name} ({status})")
                    self.run(f"kubectl get pods -n {namespace}", check=False)
                    return False

                if status == "Completed":
                    continue

                if status != "Running":
                    all_ready = False
                    continue

                if "/" in ready:
                    ready_current, ready_total = ready.split("/", 1)
                    if ready_current != ready_total:
                        all_ready = False
                        continue

                if not ready:
                    all_ready = False

            if all_ready:
                print("\nAll pods are running and ready\n")
                self.run(f"kubectl get pods -n {namespace}", check=False)
                return True

            if time.time() - start_time > timeout:
                print("\nTimeout waiting for pods to be ready\n")
                self.run(f"kubectl get pods -n {namespace}", check=False)
                return False

            time.sleep(1)

    def wait_for_namespace_pods(self, namespace, timeout=None):
        timeout = timeout or self.config.TIMEOUT_NAMESPACE
        print(f"\nWaiting for pods in namespace '{namespace}'...")
        start = time.time()

        while True:
            result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")

            if result:
                all_ready = True
                for line in result.splitlines():
                    columns = line.split()
                    if len(columns) < 3:
                        continue
                    ready = columns[1] if len(columns) > 1 else ""
                    status = columns[2]

                    if status == "Completed":
                        continue

                    if status != "Running":
                        all_ready = False
                        break

                    if "/" in ready:
                        ready_current, ready_total = ready.split("/", 1)
                        if ready_current != ready_total:
                            all_ready = False
                            break

                if all_ready:
                    print("\nPods ready:")
                    self.run(f"kubectl get pods -n {namespace}")
                    return True

            if time.time() - start > timeout:
                print("Timeout waiting for pods")
                self.run(f"kubectl get pods -n {namespace}")
                return False

            time.sleep(1)

    def port_forward_service(self, namespace, pattern, local_port, remote_port, quiet=False):
        pod = self.get_pod_by_name(namespace, pattern)

        if not pod:
            if not quiet:
                print(f"Pod with pattern '{pattern}' not found in {namespace}")
            return False

        self.run(f"pkill -f 'kubectl port-forward {pod}'", check=False, silent=quiet)

        subprocess.Popen(
            ["kubectl", "port-forward", pod, "-n", namespace, f"{local_port}:{remote_port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(3)
        return True

    def stop_port_forward_service(self, namespace, pattern, quiet=False):
        pod = self.get_pod_by_name(namespace, pattern)
        if not pod:
            return False
        return self.run(f"pkill -f 'kubectl port-forward {pod}'", check=False, silent=quiet) is not None

    def wait_for_port(self, host, port, timeout=None):
        timeout = timeout or self.config.TIMEOUT_PORT
        start = time.time()

        while True:
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                pass

            if time.time() - start > timeout:
                return False

            time.sleep(1)

    def wait_for_vault_pod(self, namespace=None, timeout=None):
        namespace = namespace or self.config.NS_COMMON
        timeout = timeout or self.config.TIMEOUT_NAMESPACE
        print("\nWaiting for Vault pod to be created...")
        start = time.time()

        while True:
            pod = self.get_pod_by_name(namespace, "vault")
            if pod:
                print("Vault pod detected")
                return True

            if time.time() - start > timeout:
                print("Timeout waiting for Vault pod")
                return False

            time.sleep(1)

    def wait_for_level2_service_pods(self, namespace=None, timeout=None):
        namespace = namespace or self.config.NS_COMMON
        timeout = timeout or self.config.TIMEOUT_POD_WAIT
        print(f"\nWaiting for Level 2 core services in namespace '{namespace}'...")
        start_time = time.time()
        expected_prefixes = (
            "common-srvs-keycloak-",
            "common-srvs-minio-",
            "common-srvs-postgresql-",
            "common-srvs-vault-",
        )

        while True:
            result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")

            if result:
                pods = {}
                transient_error = None

                for line in result.splitlines():
                    columns = line.split()
                    if len(columns) < 3:
                        continue

                    name = columns[0]
                    ready = columns[1] if len(columns) > 1 else ""
                    status = columns[2]

                    if status in ["CrashLoopBackOff", "ImagePullBackOff"]:
                        print(f"\nPod in error state: {name} ({status})")
                        self.run(f"kubectl get pods -n {namespace}", check=False)
                        return False

                    if status == "Error" and "keycloak-config-cli" not in name:
                        print(f"\nPod in error state: {name} ({status})")
                        self.run(f"kubectl get pods -n {namespace}", check=False)
                        return False

                    if any(name.startswith(prefix) for prefix in expected_prefixes):
                        pods[name] = {"ready": ready, "status": status}
                    elif status == "Error":
                        transient_error = transient_error or f"{name} ({status})"

                expected = {
                    "keycloak": None,
                    "minio": None,
                    "postgresql": None,
                    "vault": None,
                }
                for name, pod in pods.items():
                    if name.startswith("common-srvs-keycloak-"):
                        expected["keycloak"] = pod
                    elif name.startswith("common-srvs-minio-"):
                        expected["minio"] = pod
                    elif name.startswith("common-srvs-postgresql-"):
                        expected["postgresql"] = pod
                    elif name.startswith("common-srvs-vault-"):
                        expected["vault"] = pod

                all_present = all(expected.values())
                all_ready = all(
                    pod["status"] == "Running" and pod["ready"] == "1/1"
                    for key, pod in expected.items()
                    if key != "vault" and pod is not None
                )
                vault_running = expected["vault"] is not None and expected["vault"]["status"] == "Running"

                if all_present and all_ready and vault_running:
                    print("\nLevel 2 core services detected:")
                    self.run(f"kubectl get pods -n {namespace}", check=False)
                    return True

                if transient_error:
                    print(f"Waiting past transient hook state: {transient_error}")

            if time.time() - start_time > timeout:
                print("\nTimeout waiting for Level 2 core services\n")
                self.run(f"kubectl get pods -n {namespace}", check=False)
                return False

            time.sleep(1)

    def setup_vault(self, namespace=None):
        namespace = namespace or self.config.NS_COMMON
        print("\nConfiguring Vault...")

        pod_name = self.get_pod_by_name(namespace, "vault")
        if not pod_name:
            print("Could not detect Vault pod")
            return False

        if not self.wait_for_pod_running(pod_name, namespace):
            return False

        status_json = self.run_silent(f"kubectl exec {pod_name} -n {namespace} -- vault status -format=json")
        initialized = False
        sealed = True

        if status_json:
            try:
                data = json.loads(status_json)
                initialized = data.get("initialized", False)
                sealed = data.get("sealed", True)
                print(f"Vault status: initialized={initialized}, sealed={sealed}")
            except Exception as e:
                print(f"Error parsing Vault status: {e}")
                return False

        vault_file_path = self.config.vault_keys_path()

        if not initialized:
            print("Vault not initialized. Running init...")
            init_output = self.run_silent(
                f"kubectl exec {pod_name} -n {namespace} -- "
                "vault operator init -key-shares=1 -key-threshold=1 -format=json"
            )

            if not init_output:
                print("Error: vault operator init failed")
                return False

            os.makedirs(os.path.dirname(vault_file_path), exist_ok=True)
            try:
                with open(vault_file_path, "w") as f:
                    f.write(init_output)
                print("Vault keys file created")
            except IOError as e:
                print(f"Error writing Vault keys: {e}")
                return False
        else:
            print("Vault already initialized")

        try:
            with open(vault_file_path, "r") as f:
                keys = json.load(f)
        except FileNotFoundError:
            print("Error: Vault keys file not found")
            return False
        except json.JSONDecodeError:
            print("Error: Vault keys file corrupted")
            return False

        unseal_key = keys.get("unseal_keys_hex", [None])[0]
        root_token = keys.get("root_token")

        if not unseal_key or not root_token:
            print("Error: Invalid keys in Vault keys file")
            return False

        if sealed:
            print("Running unseal...")
            unseal_result = self.run_silent(
                f"kubectl exec {pod_name} -n {namespace} -- vault operator unseal {unseal_key}"
            )
            if not unseal_result:
                print("Error: vault operator unseal failed")
                return False
            print("Vault unsealed")
        else:
            print("Vault already unsealed")

        print("Checking KV engine...")
        secrets_list = self.run_silent(
            f"kubectl exec {pod_name} -n {namespace} -- "
            f"env VAULT_TOKEN={root_token} vault secrets list -format=json"
        )

        kv_exists = False
        if secrets_list:
            try:
                mounts = json.loads(secrets_list)
                kv_exists = "secret/" in mounts
            except Exception:
                pass

        if not kv_exists:
            print("Enabling KV v2 engine...")
            enable_kv = self.run_silent(
                f"kubectl exec {pod_name} -n {namespace} -- "
                f"env VAULT_TOKEN={root_token} vault secrets enable -path=secret kv-v2"
            )
            if enable_kv:
                print("KV v2 engine enabled")
            else:
                print("Warning: KV v2 engine not enabled, continuing")
        else:
            print("KV v2 engine already enabled")

        final_status_json = self.run_silent(f"kubectl exec {pod_name} -n {namespace} -- vault status -format=json")
        if not final_status_json:
            print("Error: Could not get final Vault status")
            return False

        try:
            status_data = json.loads(final_status_json)
            initialized = status_data.get("initialized", False)
            sealed = status_data.get("sealed", True)
            print("\nVault final status:")
            print(f"  Initialized: {initialized}")
            print(f"  Sealed: {sealed}\n")
            return initialized and not sealed
        except Exception as e:
            print(f"Error parsing final Vault status: {e}")
            return False

    def ensure_vault_unsealed(self):
        print("Checking Vault state...")
        pod = self.get_pod_by_name(self.config.NS_COMMON, "vault")

        if not pod:
            print("Vault pod not found")
            return False

        status = self.run_silent(f"kubectl exec {pod} -n {self.config.NS_COMMON} -- vault status -format=json")
        if not status:
            print("Could not get Vault status")
            return False

        data = json.loads(status)
        if not data.get("initialized"):
            print("Vault not initialized")
            return False

        if data.get("sealed"):
            print("Vault sealed. Running unseal...")
            with open(self.config.vault_keys_path()) as f:
                keys = json.load(f)
            unseal_key = keys["unseal_keys_hex"][0]
            self.run(f"kubectl exec {pod} -n {self.config.NS_COMMON} -- vault operator unseal {unseal_key}")
            print("Vault unsealed")
        else:
            print("Vault already unsealed")

        return True

    def sync_vault_token_to_deployer_config(self):
        vault_json_path = self.config.vault_keys_path()
        config_path = self.config.deployer_config_path()

        print("\nSynchronizing Vault token with deployer config...")

        if not os.path.exists(vault_json_path):
            print(f"File not found: {vault_json_path}")
            return False

        if not os.path.exists(config_path):
            print(f"File not found: {config_path}")
            return False

        try:
            with open(vault_json_path) as f:
                vault_data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: {vault_json_path} is corrupted")
            return False

        new_token = vault_data.get("root_token")
        if not new_token:
            print(f"Error: root_token not found in {vault_json_path}")
            return False

        print(f"Token obtained: {new_token[:20]}...")

        try:
            with open(config_path) as f:
                lines = f.readlines()
        except IOError as e:
            print(f"Error reading {config_path}: {e}")
            return False

        found = False
        updated_lines = []

        for line in lines:
            if line.strip().startswith("VT_TOKEN"):
                updated_lines.append(f"VT_TOKEN={new_token}\n")
                found = True
                print("VT_TOKEN line updated")
            else:
                updated_lines.append(line)

        if not found:
            if updated_lines and updated_lines[-1].strip():
                updated_lines.append("\n")
            updated_lines.append(f"VT_TOKEN={new_token}\n")
            print("VT_TOKEN line added")

        try:
            with open(config_path, "w") as f:
                f.writelines(updated_lines)
        except IOError as e:
            print(f"Error writing {config_path}: {e}")
            return False

        print("Vault token synchronized\n")
        return True

    def show_correspondence_table(self, values, config):
        rows = []

        def status(expected, current):
            return "OK" if expected == current else "DIFF"

        def add_row(logical_var, values_path, config_var, current_value):
            expected_value = config.get(config_var)
            rows.append([
                logical_var,
                values_path,
                expected_value,
                current_value,
                status(expected_value, current_value)
            ])

        add_row("PG_PASSWORD", "postgresql.auth.postgresPassword", "PG_PASSWORD", values["postgresql"]["auth"]["postgresPassword"])
        add_row("PG_PASSWORD", "keycloak.externalDatabase.password", "PG_PASSWORD", values["keycloak"]["externalDatabase"]["password"])
        add_row("KC_USER", "keycloak.auth.adminUser", "KC_USER", values["keycloak"]["auth"]["adminUser"])
        add_row("KC_PASSWORD", "keycloak.auth.adminPassword", "KC_PASSWORD", values["keycloak"]["auth"]["adminPassword"])

        for item in values["keycloak"]["keycloakConfigCli"]["extraEnv"]:
            if item["name"] == "KEYCLOAK_USER":
                add_row("KC_USER", "keycloakConfigCli.KEYCLOAK_USER", "KC_USER", item["value"])
            if item["name"] == "KEYCLOAK_PASSWORD":
                add_row("KC_PASSWORD", "keycloakConfigCli.KEYCLOAK_PASSWORD", "KC_PASSWORD", item["value"])

        print("\nConfiguration synchronization: deployer.config <-> common/values.yaml\n")
        print(tabulate(rows, headers=["DEPLOYER.CONFIG", "COMMON/VALUES.YAML", "EXPECTED", "FOUND", "STATUS"], tablefmt="grid"))
        print()
        return any(row[4] == "DIFF" for row in rows)

    def apply_sync(self, values, config):
        pg_password = config.get("PG_PASSWORD")
        kc_user = config.get("KC_USER")
        kc_password = config.get("KC_PASSWORD")

        values["postgresql"]["auth"]["postgresPassword"] = pg_password
        values["postgresql"]["auth"]["password"] = pg_password
        values["keycloak"]["externalDatabase"]["password"] = pg_password
        values["keycloak"]["auth"]["adminUser"] = kc_user
        values["keycloak"]["auth"]["adminPassword"] = kc_password

        for item in values["keycloak"]["keycloakConfigCli"]["extraEnv"]:
            if item["name"] == "KEYCLOAK_USER":
                item["value"] = kc_user
            if item["name"] == "KEYCLOAK_PASSWORD":
                item["value"] = kc_password

        return values

    def sync_common_values(self):
        values_path = self.config.values_path()
        config_path = self.config.deployer_config_path()
        ds_name = self.config.DS_NAME

        if not os.path.exists(values_path):
            print("File not found: common/values.yaml")
            return

        if not os.path.exists(config_path):
            print("File not found: deployer.config")
            return

        config = self.config_adapter.load_deployer_config()
        with open(values_path) as f:
            values = yaml_ruamel.load(f)

        has_diffs = self.show_correspondence_table(values, config)

        if has_diffs:
            if self._auto_mode():
                choice = "Y"
                print("[AUTO_MODE] Automatically applying detected changes")
            else:
                choice = input("Apply detected changes? (Y/N): ").strip().upper()

            if choice == "Y":
                values = self.apply_sync(values, config)
                master_json = values["keycloak"]["keycloakConfigCli"]["configuration"]["master.json"]
                values["keycloak"]["keycloakConfigCli"]["configuration"]["master.json"] = LiteralScalarString(master_json)
                with open(values_path, "w") as f:
                    yaml_ruamel.dump(values, f)
                print("Configuration synchronized\n")
            else:
                print("No changes applied\n")
                return
        else:
            print("No differences found\n")

        hosts = self.config_adapter.generate_hosts(ds_name)
        print("Hosts entries to add to your system:\n")
        for host in hosts:
            print(host)
        print()

    def ensure_local_infra_access(self):
        print("\nVerifying local access to PostgreSQL and Vault...")

        if not self.wait_for_port("127.0.0.1", self.config.PORT_POSTGRES):
            print("PostgreSQL not accessible. Creating port-forward...")
            self.port_forward_service(self.config.NS_COMMON, "postgresql", 5432, 5432)
            if not self.wait_for_port("127.0.0.1", self.config.PORT_POSTGRES):
                print("Could not establish PostgreSQL access")
                return False
        else:
            print("PostgreSQL accessible")

        if not self.wait_for_port("127.0.0.1", self.config.PORT_VAULT):
            print("Vault not accessible. Creating port-forward...")
            self.port_forward_service(self.config.NS_COMMON, "vault", 8200, 8200)
            if not self.wait_for_port("127.0.0.1", self.config.PORT_VAULT):
                print("Could not establish Vault access")
                return False
        else:
            print("Vault accessible")

        print("Local infrastructure OK\n")
        return True

    def wait_for_registration_service_schema(self, timeout=None, poll_interval=3):
        timeout = timeout or self.config.TIMEOUT_POD_WAIT
        print("\nWaiting for registration-service schema to be ready...")
        start = time.time()
        pg_host, pg_user, pg_password = self.config_adapter.get_pg_credentials()
        registration_db = self.config.registration_db_name()
        sql = "SELECT to_regclass('public.edc_participant');"

        while time.time() - start <= timeout:
            result = self.run_silent(
                f"PGPASSWORD={pg_password} psql -h {pg_host} -U {pg_user} "
                f"-d {registration_db} -t -A -c \"{sql}\""
            )

            if result and result.strip() == "edc_participant":
                print("registration-service schema ready: public.edc_participant exists")
                return True

            time.sleep(poll_interval)

        print("Timeout waiting for registration-service schema readiness")
        self.run(
            f"PGPASSWORD={pg_password} psql -h {pg_host} -U {pg_user} "
            f"-d {registration_db} -c \"\\dt public.*\"",
            check=False,
        )
        return False

    def wait_for_registration_service_liquibase(self, timeout=None, poll_interval=3):
        timeout = timeout or self.config.TIMEOUT_POD_WAIT
        local_port = self.config.PORT_REGISTRATION_SERVICE
        namespace = self.config.namespace_demo()
        created_port_forward = False
        last_issue = None

        try:
            if not self.wait_for_port("127.0.0.1", local_port, timeout=2):
                if self.port_forward_service(namespace, "registration-service", local_port, 8080, quiet=True):
                    created_port_forward = True
                else:
                    last_issue = "temporary port-forward to registration-service actuator could not be established"

            if not self.wait_for_port("127.0.0.1", local_port):
                self._last_registration_service_liquibase_issue = last_issue or "registration-service actuator was not reachable locally"
                return False

            endpoint = f"http://127.0.0.1:{local_port}/api/actuator/liquibase"
            start = time.time()

            while time.time() - start <= timeout:
                try:
                    response = requests.get(endpoint, timeout=5)
                    if response.status_code == 200:
                        payload = response.json()
                        if "liquibaseBeans" in payload:
                            self._last_registration_service_liquibase_issue = None
                            return True
                        last_issue = "liquibaseBeans not present in actuator response"
                    else:
                        last_issue = f"registration-service actuator returned HTTP {response.status_code}"
                except Exception:
                    last_issue = "registration-service actuator did not respond in time"

                time.sleep(poll_interval)

            self._last_registration_service_liquibase_issue = last_issue or "registration-service actuator did not confirm Liquibase readiness"
            return False
        finally:
            if created_port_forward:
                self.stop_port_forward_service(namespace, "registration-service", quiet=True)

    def wait_for_kubernetes_ready(self, timeout=180):
        print("\nWaiting for Kubernetes cluster to become ready...\n")
        start = time.time()

        while True:
            nodes = self.run_silent("kubectl get nodes")
            if nodes and " Ready " in nodes:
                print("Kubernetes node is Ready\n")
                return True

            if time.time() - start > timeout:
                print("Timeout waiting for Kubernetes node readiness")
                return False

            time.sleep(3)

    def _pod_snapshot(self, namespace):
        result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not result:
            return []

        snapshot = []
        for line in result.splitlines():
            columns = line.split()
            if len(columns) < 4:
                continue
            snapshot.append({
                "name": columns[0],
                "ready": columns[1],
                "status": columns[2],
                "restarts": columns[3],
            })
        return snapshot

    def wait_for_namespace_stability(self, namespace, duration=15, poll_interval=3):
        """Observe namespace health during a stability window."""
        print(f"\nObserving namespace '{namespace}' stability for {duration}s...")
        last_issue = None
        stable_since = None
        timeout = max(self.config.TIMEOUT_NAMESPACE, duration * 3)
        deadline = time.time() + timeout

        while time.time() < deadline:
            snapshot = self._pod_snapshot(namespace)
            if not snapshot:
                last_issue = f"no pods found in namespace '{namespace}'"
                stable_since = None
                time.sleep(poll_interval)
                continue

            unhealthy = []
            for pod in snapshot:
                if pod["status"] not in ("Running", "Completed"):
                    unhealthy.append(f"{pod['name']} ({pod['status']})")
                    continue

                if pod["status"] == "Running" and "/" in pod["ready"]:
                    ready_current, ready_total = pod["ready"].split("/", 1)
                    if ready_current != ready_total:
                        unhealthy.append(f"{pod['name']} readiness {pod['ready']}")

            if unhealthy:
                last_issue = ", ".join(unhealthy)
                stable_since = None
                time.sleep(poll_interval)
                continue

            if stable_since is None:
                stable_since = time.time()
                last_issue = None

            if time.time() - stable_since >= duration:
                print(f"Namespace '{namespace}' is stable\n")
                return True

            time.sleep(poll_interval)

        if last_issue:
            print(f"Namespace '{namespace}' failed stability window: {last_issue}")
            self.run(f"kubectl get pods -n {namespace}", check=False)
            return False

        print(f"Namespace '{namespace}' did not achieve a continuous {duration}s stability window in time")
        self.run(f"kubectl get pods -n {namespace}", check=False)
        return False

    def verify_cluster_ready_for_level2(self):
        """Ensure Level 1 leaves a cluster stable enough for Level 2."""
        status = self.run_silent("minikube status --output=json")
        if not status:
            return False, "minikube status unavailable"

        try:
            status_data = json.loads(status)
        except json.JSONDecodeError:
            return False, "minikube status output is not valid JSON"

        for key in ("Host", "Kubelet", "APIServer"):
            value = str(status_data.get(key, "")).lower()
            if value != "running":
                return False, f"{key} is '{status_data.get(key)}'"

        nodes = self.run_silent("kubectl get nodes --no-headers")
        if not nodes or " Ready " not in f" {nodes} ":
            return False, "kubectl does not report a Ready node"

        if not self.wait_for_pods("ingress-nginx", timeout=180):
            return False, "ingress-nginx pods did not become ready"

        if not self.wait_for_namespace_stability("ingress-nginx", duration=15, poll_interval=3):
            return False, "ingress-nginx namespace did not remain stable"

        return True, None

    def verify_common_services_ready_for_level3(self):
        """Ensure Level 2 leaves common services stable enough for Level 3."""
        if not self.wait_for_level2_service_pods(self.config.NS_COMMON, timeout=180):
            return False, "common services pods did not become ready"

        if not self.wait_for_namespace_stability(self.config.NS_COMMON, duration=20, poll_interval=3):
            return False, "common services namespace did not remain stable"

        if not self.ensure_vault_unsealed():
            return False, "Vault is not initialized/unsealed"

        return True, None

    def verify_dataspace_ready_for_level4(self):
        """Ensure Level 3 leaves dataspace services stable enough for Level 4."""
        if not self.wait_for_namespace_stability(self.config.namespace_demo(), duration=20, poll_interval=3):
            return False, "dataspace namespace did not remain stable"

        self.wait_for_registration_service_liquibase(timeout=60, poll_interval=3)

        if not self.wait_for_registration_service_schema(timeout=120, poll_interval=3):
            if self._last_registration_service_liquibase_issue:
                print(
                    "Registration-service Liquibase check was inconclusive: "
                    f"{self._last_registration_service_liquibase_issue}"
                )
            return False, "registration-service schema was not ready"

        return True, None

    def setup_cluster(self):
        print("\n========================================")
        print("LEVEL 1 - CLUSTER SETUP")
        print("========================================\n")

        self.ensure_unix_environment()
        if not self.ensure_wsl_docker_config():
            self._fail("Could not adjust WSL Docker configuration safely")

        print("Checking Minikube installation...")
        if self.run("which minikube", capture=True) is None:
            print("Installing Minikube...")
            self.run("curl -LO https://github.com/kubernetes/minikube/releases/latest/download/minikube-linux-amd64")
            self.run("sudo install minikube-linux-amd64 /usr/local/bin/minikube")
            self.run("rm -f minikube-linux-amd64")

        self.run("minikube version")

        print("\nChecking Helm installation...")
        if self.run("which helm", capture=True) is None:
            self.run("sudo snap install helm --classic", check=False)
        self.run("helm version")

        print("\nChecking Docker...")
        if self.run("docker info", capture=True, check=False) is None:
            self._fail("Docker is not running. Start Docker and retry")

        print("Docker is running")
        print("\nDeleting existing Minikube cluster (clean state)...\n")
        self.run("minikube delete", check=False)

        print("\nStarting fresh Minikube cluster...\n")
        self.run(
            f"minikube start --driver={self.config.MINIKUBE_DRIVER} "
            f"--cpus={self.config.MINIKUBE_CPUS} --memory={self.config.MINIKUBE_MEMORY}"
        )

        if not self.wait_for_kubernetes_ready():
            self._fail("Cluster failed to initialize", root_cause="Kubernetes node did not become Ready")

        print("\nEnabling ingress addon...\n")
        self.run("minikube addons enable ingress", check=False)
        self.run("kubectl get pods -n ingress-nginx", check=False)
        cluster_ready, root_cause = self.verify_cluster_ready_for_level2()
        if not cluster_ready:
            self._fail("Level 1 did not leave the cluster ready for Level 2", root_cause=root_cause)
        print("\nLEVEL 1 COMPLETE\n")

    def deploy_infrastructure(self):
        print("\n========================================")
        print("LEVEL 2 - DEPLOY COMMON SERVICES")
        print("========================================\n")

        if not self.ensure_wsl_docker_config():
            self._fail("Could not adjust WSL Docker configuration safely")

        repo_dir = self.config.repo_dir()
        common_dir = self.config.common_dir()
        values_path = self.config.values_path()

        if not os.path.exists(repo_dir):
            print("Cloning repository...")
            self.run(f"git clone {self.config.REPO_URL}", cwd=self.config.script_dir())
            self.config_adapter.copy_local_deployer_config()
        else:
            print("Repository exists")

        self.config_adapter.copy_local_deployer_config()

        print("\nSynchronizing configuration...\n")
        self.sync_common_values()

        print("\nConfiguring hosts...")
        hosts_entries = self.config_adapter.generate_hosts(self.config.DS_NAME)
        self.manage_hosts_entries(hosts_entries)

        self.add_helm_repos()

        print("\nBuilding Helm dependencies...")
        self.run("helm dependency build", cwd=common_dir)

        print("\nDeploying common services...")
        if not self.deploy_helm_release(self.config.helm_release_common(), self.config.NS_COMMON, values_path, cwd=common_dir):
            self._fail("Error deploying common services")

        if not self.wait_for_level2_service_pods(self.config.NS_COMMON):
            self._fail(
                "Services did not reach the pre-Vault-ready state",
                root_cause="Keycloak, MinIO and PostgreSQL must be 1/1 Running, and Vault must exist in Running state before setup",
            )

        if not self.wait_for_vault_pod(self.config.NS_COMMON):
            self._fail("Vault pod not detected")

        if not self.setup_vault(self.config.NS_COMMON):
            self._fail("Error configuring Vault")

        if not self.sync_vault_token_to_deployer_config():
            print("Warning: Could not synchronize Vault token")

        common_ready, root_cause = self.verify_common_services_ready_for_level3()
        if not common_ready:
            self._fail("Level 2 did not leave common services ready for Level 3", root_cause=root_cause)

        print("\nLEVEL 2 COMPLETE\n")

    def describe(self) -> str:
        return "INESDataInfrastructureAdapter contains infrastructure logic for INESData."

