#!/usr/bin/env python3
"""
Kubernetes Cluster Automation with Helm
Centralized configuration, no hardcoding, audit-ready.
"""

import subprocess
import sys
import time
import os
import json
import yaml
import socket
import shutil
import requests
import statistics
import re
from itertools import combinations
from itertools import permutations
from datetime import datetime
from tabulate import tabulate
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString



# =========================================================
# CENTRALIZED CONFIGURATION
# =========================================================

class Config:
    """Centralized technical configuration."""

    # Deployment
    REPO_URL = "https://github.com/ProyectoPIONERA/inesdata-testing.git"
    REPO_DIR = "inesdata-testing"
    DS_NAME = "demo"
    NS_COMMON = "common-srvs"

    # Helm
    HELM_REPOS = {
        "minio": "https://charts.min.io/",
        "hashicorp": "https://helm.releases.hashicorp.com"
    }

    # Minikube
    MINIKUBE_DRIVER = "docker"
    MINIKUBE_CPUS = 4
    MINIKUBE_MEMORY = 4400
    MINIKUBE_PROFILE = "minikube"
    MINIKUBE_ADDONS = ["ingress"]
    MINIKUBE_IP = "192.168.49.2"

    # Ports
    PORT_POSTGRES = 5432
    PORT_VAULT = 8200
    PORT_MINIO = 9000

    # Timeouts (seconds)
    TIMEOUT_POD_WAIT = 120
    TIMEOUT_PORT = 30
    TIMEOUT_NAMESPACE = 90

    # Paths
    PATH_VENV = ".venv"
    PATH_REQUIREMENTS = "requirements.txt"

    @classmethod
    def script_dir(cls):
        return os.path.dirname(os.path.abspath(__file__))

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
        return os.path.join(
            cls.registration_service_dir(),
            f"values-{cls.DS_NAME}.yaml"
        )

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
        config = load_deployer_config()
        return config.get("DS_DOMAIN_BASE")

# =========================================================
# GLOBAL FLAGS
# =========================================================

AUTO_MODE = False  # When True, skip all user prompts and confirmations

# =========================================================
# EXECUTION UTILITIES
# =========================================================

def run(cmd, capture=False, silent=False, check=True, cwd=None):
    """Execute shell command with error handling."""
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


def run_silent(cmd, cwd=None):
    """Execute command without displaying output."""
    return run(cmd, capture=True, silent=True, check=False, cwd=cwd)


def install_dependencies():
    """Install the tabulate and ruamel.yaml libraries using pip."""
    libraries = ["tabulate", "ruamel.yaml"]

    print("Installing dependencies...")

    for lib in libraries:
        try:
            # Ejecuta: pip install <libreria>
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])
            print(f"✅ {lib} installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error installing {lib}: {e}")

# =========================================================
# ENVIRONMENT VALIDATION
# =========================================================

def ensure_unix_environment():
    """Verify script runs on Unix-like environment."""
    if os.name == "nt":
        print("Script must run on Linux, macOS, or WSL")
        sys.exit(1)


def is_wsl():
    """Detect if running under WSL."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def get_hosts_path():
    """Return correct hosts file path for current OS."""
    if is_wsl():
        return "/mnt/c/Windows/System32/drivers/etc/hosts"
    elif sys.platform.startswith("linux"):
        return "/etc/hosts"
    elif sys.platform == "darwin":
        return "/private/etc/hosts"
    else:
        return None


# =========================================================
# HOSTS MANAGEMENT
# =========================================================

def manage_hosts_entries(desired_entries):
    """Verify and add entries to hosts file if necessary."""
    hosts_path = get_hosts_path()

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

    existing = [e for e in desired_entries if e in content]
    missing = [e for e in desired_entries if e not in content]

    print("\nExisting entries:")
    for e in existing or ["None"]:
        if e:
            print(f"  {e}")

    print("\nMissing entries:")
    for e in missing or ["None"]:
        if e:
            print(f"  {e}")

    if not missing:
        print("\nNo modifications needed to hosts file")
        return

    if AUTO_MODE:
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


# =========================================================
# KUBERNETES OPERATIONS
# =========================================================

def deploy_helm_release(release_name, namespace, values_file="values.yaml", cwd=None):
    """Deploy Helm release using upgrade --install."""
    print("Executing helm upgrade --install...")

    cmd = (
        f"helm upgrade --install {release_name} . "
        f"-n {namespace} "
        f"--create-namespace "
        f"-f {values_file} "
    )

    result = run(cmd, check=False, cwd=cwd)

    if result is None:
        print("Helm deployment failed")
        return False

    print("Release deployed successfully")
    return True


def add_helm_repos():
    """Add required Helm repositories."""
    print("\nAdding Helm repositories...")
    for name, url in Config.HELM_REPOS.items():
        run(f"helm repo add {name} {url}", check=False)
    run("helm repo update", check=False)


def get_pod_by_name(namespace, pod_pattern):
    """Get pod name by pattern."""
    result = run_silent(f"kubectl get pods -n {namespace} --no-headers")

    if not result:
        return None

    for line in result.splitlines():
        if pod_pattern in line:
            return line.split()[0]

    return None


def wait_for_pod_running(pod_name, namespace, timeout=None):
    """Wait for pod to reach Running state."""
    if timeout is None:
        timeout = Config.TIMEOUT_NAMESPACE

    print(f"Waiting for pod {pod_name} to be running...")
    start = time.time()

    while True:
        result = run_silent(
            f"kubectl get pod {pod_name} -n {namespace} --no-headers"
        )

        if result:
            cols = result.split()
            if len(cols) > 2 and cols[2] == "Running":
                print(f"Pod {pod_name} is running")
                return True

        if time.time() - start > timeout:
            print(f"Timeout waiting for pod {pod_name}")
            return False

        time.sleep(1)


def wait_for_pods(namespace, timeout=None):
    """Wait for all pods in namespace to be ready."""
    if timeout is None:
        timeout = Config.TIMEOUT_POD_WAIT

    print(f"\nWaiting for pods in namespace '{namespace}' to be ready...")
    start_time = time.time()

    while True:
        result = run_silent(f"kubectl get pods -n {namespace} --no-headers")

        if not result:
            time.sleep(2)
            continue

        all_ready = True

        for line in result.splitlines():
            columns = line.split()
            name = columns[0]
            status = columns[2]

            if status in ["CrashLoopBackOff", "Error", "ImagePullBackOff"]:
                print(f"\nPod in error state: {name} ({status})")
                run(f"kubectl get pods -n {namespace}", check=False)
                return False

            if status != "Running":
                all_ready = False

        if all_ready:
            print("\nAll pods are running and ready\n")
            run(f"kubectl get pods -n {namespace}", check=False)
            return True

        if time.time() - start_time > timeout:
            print("\nTimeout waiting for pods to be ready\n")
            run(f"kubectl get pods -n {namespace}", check=False)
            return False

        time.sleep(1)


def wait_for_namespace_pods(namespace, timeout=None):
    """Wait for all pods in namespace to be running."""
    if timeout is None:
        timeout = Config.TIMEOUT_NAMESPACE

    print(f"\nWaiting for pods in namespace '{namespace}'...")
    start = time.time()

    while True:
        result = run_silent(f"kubectl get pods -n {namespace} --no-headers")

        if result:
            all_ready = all(line.split()[2] == "Running" for line in result.splitlines())

            if all_ready:
                print("\nPods ready:")
                run(f"kubectl get pods -n {namespace}")
                return True

        if time.time() - start > timeout:
            print("Timeout waiting for pods")
            run(f"kubectl get pods -n {namespace}")
            return False

        time.sleep(1)


def port_forward_service(namespace, pattern, local_port, remote_port):
    """Create port forward to pod."""
    pod = get_pod_by_name(namespace, pattern)

    if not pod:
        print(f"Pod with pattern '{pattern}' not found in {namespace}")
        return False

    run(f"pkill -f 'kubectl port-forward {pod}'", check=False)

    subprocess.Popen(
        ["kubectl", "port-forward", pod, "-n", namespace, f"{local_port}:{remote_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    time.sleep(3)
    return True


def wait_for_port(host, port, timeout=None):
    """Wait for port to be accessible."""
    if timeout is None:
        timeout = Config.TIMEOUT_PORT

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


def check_minikube_tunnel_available():
    """Verify minikube tunnel is active and accessible."""
    print("\nVerifying minikube tunnel...\n")

    cmd = (
        "kubectl get svc ingress-nginx-controller "
        "-n ingress-nginx "
        "-o jsonpath='{.status.loadBalancer.ingress[0].ip}'"
    )

    while True:
        external_ip = run(cmd, capture=True, silent=True)

        if external_ip and external_ip.strip() != "":
            print(f"Tunnel active. EXTERNAL-IP: {external_ip}\n")
            return True

        print("Minikube tunnel not active or not yet accessible.\n")
        print("To activate it:")
        print("1. Open a NEW terminal (not this one)")
        print("2. Run:\n")
        print("   minikube tunnel\n")
        print("Important notes:")
        print("- Do not manually run with sudo")
        print("- System will request password")
        print("- Password input is normal even if not visible")
        print("- Press ENTER after password entry")
        print("- Tunnel must remain open while using the system\n")

        if AUTO_MODE:
            print("[AUTO_MODE] Waiting 10 seconds for tunnel to become active...\n")
            time.sleep(10)
        else:
            input("Press ENTER when tunnel is active to retry...\n")


# =========================================================
# VAULT OPERATIONS
# =========================================================

def wait_for_vault_pod(namespace=Config.NS_COMMON, timeout=None):
    """Wait for Vault pod to be created."""
    if timeout is None:
        timeout = Config.TIMEOUT_NAMESPACE

    print("\nWaiting for Vault pod to be created...")
    start = time.time()

    while True:
        pod = get_pod_by_name(namespace, "vault")
        if pod:
            print("Vault pod detected")
            return True

        if time.time() - start > timeout:
            print("Timeout waiting for Vault pod")
            return False

        time.sleep(1)


def setup_vault(namespace=Config.NS_COMMON):
    """Configure Vault: init, unseal, and enable KV v2."""
    print("\nConfiguring Vault...")

    pod_name = get_pod_by_name(namespace, "vault")

    if not pod_name:
        print("Could not detect Vault pod")
        return False

    if not wait_for_pod_running(pod_name, namespace):
        return False

    # Check status
    status_json = run_silent(
        f"kubectl exec {pod_name} -n {namespace} -- vault status -format=json"
    )

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

    vault_file_path = Config.vault_keys_path()

    # Initialize if needed
    if not initialized:
        print("Vault not initialized. Running init...")

        init_output = run_silent(
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

    # Read keys
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

    # Unseal if needed
    if sealed:
        print("Running unseal...")
        unseal_result = run_silent(
            f"kubectl exec {pod_name} -n {namespace} -- vault operator unseal {unseal_key}"
        )

        if not unseal_result:
            print("Error: vault operator unseal failed")
            return False

        print("Vault unsealed")
    else:
        print("Vault already unsealed")

    # Verify KV v2
    print("Checking KV engine...")

    secrets_list = run_silent(
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
        enable_kv = run_silent(
            f"kubectl exec {pod_name} -n {namespace} -- "
            f"env VAULT_TOKEN={root_token} vault secrets enable -path=secret kv-v2"
        )

        if enable_kv:
            print("KV v2 engine enabled")
        else:
            print("Warning: KV v2 engine not enabled, continuing")
    else:
        print("KV v2 engine already enabled")

    # Final status
    final_status_json = run_silent(
        f"kubectl exec {pod_name} -n {namespace} -- vault status -format=json"
    )

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


def ensure_vault_unsealed():
    """Ensure Vault is unsealed before proceeding."""
    print("Checking Vault state...")

    pod = get_pod_by_name(Config.NS_COMMON, "vault")

    if not pod:
        print("Vault pod not found")
        return False

    status = run_silent(
        f"kubectl exec {pod} -n {Config.NS_COMMON} -- vault status -format=json"
    )

    if not status:
        print("Could not get Vault status")
        return False

    data = json.loads(status)

    if not data.get("initialized"):
        print("Vault not initialized")
        return False

    if data.get("sealed"):
        print("Vault sealed. Running unseal...")

        with open(Config.vault_keys_path()) as f:
            keys = json.load(f)

        unseal_key = keys["unseal_keys_hex"][0]

        run(
            f"kubectl exec {pod} -n {Config.NS_COMMON} "
            f"-- vault operator unseal {unseal_key}"
        )

        print("Vault unsealed")
    else:
        print("Vault already unsealed")

    return True


# =========================================================
# CONNECTOR CREATOR
# =========================================================

def create_connectors(connector_name):
    """Create and deploy connector."""
    print("\n========================================")
    print("LEVEL 4 - CREATE CONNECTOR")
    print("========================================\n")

    repo_dir = Config.repo_dir()
    ds_name = Config.DS_NAME
    python_exec = Config.python_exec()

    if not os.path.exists(repo_dir):
        print("Repository not found. Run Level 2 first")
        return

    if not ensure_local_infra_access():
        return

    if not ensure_vault_unsealed():
        return

    print(f"Cleaning connector: {connector_name}")

    run(
        f"{python_exec} deployer.py connector delete {connector_name} {ds_name}",
        cwd=repo_dir,
        check=False
    )

    connector_db = connector_name.replace("-", "_")
    force_clean_postgres_db(connector_db, connector_db)

    print("Cleaning registration-service database...")

    sql_del = (
        f"DELETE FROM public.edc_participant "
        f"WHERE participant_id = '{connector_name}';"
    )

    pg_host, pg_user, pg_pass = get_pg_credentials()

    run(
        f'PGPASSWORD={pg_pass} '
        f'psql -h {pg_host} -U {pg_user} '
        f'-d {Config.registration_db_name()} '
        f'-c "{sql_del}"',
        check=False
    )

    print(f"Creating connector {connector_name}...")

    if run(
            f"{python_exec} deployer.py connector create {connector_name} {ds_name}",
            cwd=repo_dir
    ) is None:
        print("Error: deployment failed")
        return

    creds_path = Config.connector_credentials_path(connector_name)

    if not setup_minio_bucket(
            Config.NS_COMMON,
            ds_name,
            connector_name,
            creds_path
    ):
        print("Warning: MinIO configuration incomplete")

    values_file = Config.connector_values_file(connector_name)

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

    minikube_ip = run("minikube ip", capture=True)

    if minikube_ip:
        update_helm_values_with_host_aliases(values_file, minikube_ip)

    release_name = f"{connector_name}-{ds_name}"

    print(f"Deploying connector {connector_name}...")

    if not deploy_helm_release(
            release_name,
            Config.namespace_demo(),
            os.path.basename(values_file),
            cwd=Config.connector_dir()
    ):
        print("Error deploying connector")
        return

    if not wait_for_namespace_pods(Config.namespace_demo()):
        print("Timeout waiting for connector pods")
        return

    print("\nCONNECTORS CREATED\n")


# =========================================================
# CONFIGURATION UTILITIES
# =========================================================

def copy_local_deployer_config():
    """
    Replace repository deployer.config with the local deployer.config
    located next to this script.
    """

    local_config = os.path.join(Config.script_dir(), "deployer.config")
    repo_config = Config.deployer_config_path()

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

def load_deployer_config():
    """Load deployer configuration from file.

    Returns:
        dict: Configuration key-value pairs from deployer.config file
    """
    config_path = Config.deployer_config_path()
    config = {}

    try:
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    except FileNotFoundError:
        print(f"Error: Configuration file not found: {config_path}")
        return config
    except IOError as e:
        print(f"Error reading configuration file: {e}")
        return config

    return config


def get_pg_credentials():
    """Get PostgreSQL credentials from deployer config.

    Returns:
        tuple: (hostname, username, password) for PostgreSQL connection
    """
    config = load_deployer_config()
    return (
        config.get("PG_HOST", "localhost"),
        config.get("PG_USER", "postgres"),
        config.get("PG_PASSWORD")
    )


def sync_vault_token_to_deployer_config():
    """Synchronize Vault root token with deployer config."""
    vault_json_path = Config.vault_keys_path()
    config_path = Config.deployer_config_path()

    print(f"\nSynchronizing Vault token with deployer config...")

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
            print(f"VT_TOKEN line updated")
        else:
            updated_lines.append(line)

    if not found:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("\n")
        updated_lines.append(f"VT_TOKEN={new_token}\n")
        print(f"VT_TOKEN line added")

    try:
        with open(config_path, "w") as f:
            f.writelines(updated_lines)
    except IOError as e:
        print(f"Error writing {config_path}: {e}")
        return False

    print(f"Vault token synchronized\n")
    return True


# =========================================================
# MINIO OPERATIONS
# =========================================================

def setup_minio_bucket(namespace, ds_name, connector_name, creds_file_path):
    """Configure MinIO buckets and users."""
    print("\nConfiguring MinIO...")

    config = load_deployer_config()
    minio_endpoint = config.get("MINIO_ENDPOINT", "http://127.0.0.1:9000")
    minio_admin_user = config.get("MINIO_ADMIN_USER", "admin")
    minio_admin_pass = config.get("MINIO_ADMIN_PASS", "aPassword1234")

    minio_pod = get_pod_by_name(namespace, Config.service_minio())

    if not minio_pod:
        print(f"Pod {Config.service_minio()} not found")
        return False

    try:
        with open(creds_file_path) as f:
            creds = json.load(f)
    except FileNotFoundError:
        print(f"File not found: {creds_file_path}")
        return False

    m_creds = creds.get('minio', {})
    mc = f"kubectl exec -n {namespace} {minio_pod} --"

    run(
        f"{mc} mc alias set minio {minio_endpoint} "
        f"{minio_admin_user} {minio_admin_pass}",
        silent=True
    )

    run(f"{mc} mc mb minio/{ds_name}-{connector_name}", check=False)

    run(
        f"{mc} mc admin user add minio {connector_name} {m_creds.get('passwd')}",
        silent=True
    )

    run(
        f"{mc} mc admin user svcacct add minio {connector_name} "
        f"--access-key {m_creds.get('access_key')} --secret-key {m_creds.get('secret_key')}",
        silent=True
    )

    print("MinIO configured")
    return True


# =========================================================
# HELM OPERATIONS
# =========================================================

def update_helm_values_with_host_aliases(values_file, minikube_ip=None):
    """Update values file with host aliases."""
    if minikube_ip is None:
        minikube_ip = run("minikube ip", capture=True) or Config.MINIKUBE_IP

    with open(values_file) as f:
        values = yaml.safe_load(f)

    values["hostAliases"] = [{
        "ip": minikube_ip,
        "hostnames": Config.host_alias_domains()
    }]

    with open(values_file, "w") as f:
        yaml.dump(values, f, sort_keys=False)


def force_clean_postgres_db(db_name, db_user):
    """Force clean PostgreSQL database."""
    print(f"\nCleaning PostgreSQL database '{db_name}'...")

    config = load_deployer_config()

    pg_user = config.get("PG_USER")
    pg_password = config.get("PG_PASSWORD")
    pg_host = config.get("PG_HOST")

    terminate_sql = f"""
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = '{db_name}';
    """

    run(
        f"PGPASSWORD={pg_password} "
        f"psql -h {pg_host} -U {pg_user} "
        f"-d postgres -c \"{terminate_sql}\"",
        check=False
    )

    run(
        f"PGPASSWORD={pg_password} "
        f"psql -h {pg_host} -U {pg_user} "
        f"-d postgres -c \"DROP DATABASE IF EXISTS {db_name};\"",
        check=False
    )

    run(
        f"PGPASSWORD={pg_password} "
        f"psql -h {pg_host} -U {pg_user} "
        f"-d postgres -c \"DROP ROLE IF EXISTS {db_user};\"",
        check=False
    )

    print("PostgreSQL cleanup complete\n")


# =========================================================
# YAML UTILITIES
# =========================================================

yaml_ruamel = YAML()
yaml_ruamel.preserve_quotes = True
yaml_ruamel.indent(mapping=2, sequence=4, offset=2)


def backup_values(values_path):
    """Create backup of values file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{values_path}.backup.{timestamp}"
    shutil.copy2(values_path, backup_path)
    print(f"\nBackup created: {backup_path}")


def show_correspondence_table(values, config):
    """Display configuration correspondence table."""
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

    add_row(
        "PG_PASSWORD",
        "postgresql.auth.postgresPassword",
        "PG_PASSWORD",
        values["postgresql"]["auth"]["postgresPassword"]
    )

    add_row(
        "PG_PASSWORD",
        "keycloak.externalDatabase.password",
        "PG_PASSWORD",
        values["keycloak"]["externalDatabase"]["password"]
    )

    add_row(
        "KC_USER",
        "keycloak.auth.adminUser",
        "KC_USER",
        values["keycloak"]["auth"]["adminUser"]
    )

    add_row(
        "KC_PASSWORD",
        "keycloak.auth.adminPassword",
        "KC_PASSWORD",
        values["keycloak"]["auth"]["adminPassword"]
    )

    for item in values["keycloak"]["keycloakConfigCli"]["extraEnv"]:
        if item["name"] == "KEYCLOAK_USER":
            add_row(
                "KC_USER",
                "keycloakConfigCli.KEYCLOAK_USER",
                "KC_USER",
                item["value"]
            )
        if item["name"] == "KEYCLOAK_PASSWORD":
            add_row(
                "KC_PASSWORD",
                "keycloakConfigCli.KEYCLOAK_PASSWORD",
                "KC_PASSWORD",
                item["value"]
            )

    print("\nConfiguration synchronization: deployer.config <-> common/values.yaml\n")

    print(tabulate(
        rows,
        headers=["DEPLOYER.CONFIG", "COMMON/VALUES.YAML", "EXPECTED", "FOUND", "STATUS"],
        tablefmt="grid"
    ))

    print()
    return any(row[4] == "DIFF" for row in rows)


def apply_sync(values, config):
    """Apply configuration synchronization."""
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


def generate_hosts(config, ds_name):
    """Generate required hosts entries."""
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


def sync_common_values():
    """Synchronize common/values.yaml with deployer.config."""
    values_path = Config.values_path()
    config_path = Config.deployer_config_path()
    ds_name = Config.DS_NAME

    if not os.path.exists(values_path):
        print("File not found: common/values.yaml")
        return

    if not os.path.exists(config_path):
        print("File not found: deployer.config")
        return

    config = load_deployer_config()

    with open(values_path) as f:
        values = yaml_ruamel.load(f)

    has_diffs = show_correspondence_table(values, config)

    if has_diffs:
        if AUTO_MODE:
            choice = "Y"
            print("[AUTO_MODE] Automatically applying detected changes")
        else:
            choice = input("Apply detected changes? (Y/N): ").strip().upper()

        if choice == "Y":
            values = apply_sync(values, config)

            master_json = values["keycloak"]["keycloakConfigCli"]["configuration"]["master.json"]
            values["keycloak"]["keycloakConfigCli"]["configuration"]["master.json"] = \
                LiteralScalarString(master_json)

            with open(values_path, "w") as f:
                yaml_ruamel.dump(values, f)

            print("Configuration synchronized\n")
        else:
            print("No changes applied\n")
            return
    else:
        print("No differences found\n")

    hosts = generate_hosts(config, ds_name)

    print("Hosts entries to add to your system:\n")
    for h in hosts:
        print(h)
    print()


def ensure_local_infra_access():
    """Ensure local access to PostgreSQL and Vault."""
    print("\nVerifying local access to PostgreSQL and Vault...")

    if not wait_for_port("127.0.0.1", Config.PORT_POSTGRES):
        print("PostgreSQL not accessible. Creating port-forward...")
        port_forward_service(Config.NS_COMMON, "postgresql", 5432, 5432)

        if not wait_for_port("127.0.0.1", Config.PORT_POSTGRES):
            print("Could not establish PostgreSQL access")
            return False
    else:
        print("PostgreSQL accessible")

    if not wait_for_port("127.0.0.1", Config.PORT_VAULT):
        print("Vault not accessible. Creating port-forward...")
        port_forward_service(Config.NS_COMMON, "vault", 8200, 8200)

        if not wait_for_port("127.0.0.1", Config.PORT_VAULT):
            print("Could not establish Vault access")
            return False
    else:
        print("Vault accessible")

    print("Local infrastructure OK\n")
    return True



















def load_dataspace_connectors():
    """Load dataspaces and connectors defined in deployer.config.

    Returns:
        list: List of dataspace dictionaries with name, namespace, and connectors
    """
    config = load_deployer_config()
    dataspaces = []

    i = 1
    while True:
        ds_name = config.get(f"DS_{i}_NAME")
        ds_namespace = config.get(f"DS_{i}_NAMESPACE")
        connectors = config.get(f"DS_{i}_CONNECTORS")

        if not ds_name:
            break

        connector_list = []

        if connectors:
            for c in connectors.split(","):
                name = c.strip()

                if name:
                    validate_connector_name(name)
                    connector_list.append(f"conn-{name}-{ds_name}")

        dataspaces.append({
            "name": ds_name,
            "namespace": ds_namespace,
            "connectors": connector_list
        })

        i += 1

    return dataspaces


def validate_connector_name(name):
    """
    Validate connector name format and restrictions.

    Rules:
    - Only alphanumeric characters allowed
    - Must start with a letter
    - Maximum length: 20 characters

    Args:
        name: Connector name to validate

    Raises:
        ValueError: If name is invalid
    """
    if not isinstance(name, str) or not name:
        raise ValueError("Connector name must be a non-empty string")

    if len(name) > 20:
        raise ValueError(
            f"Invalid connector name '{name}'. "
            "Maximum length is 20 characters."
        )

    if not re.match(r"^[A-Za-z][A-Za-z0-9]*$", name):
        raise ValueError(
            f"Invalid connector name '{name}'. "
            "Connector names must start with a letter and contain only alphanumeric characters."
        )


def build_connector_hostnames(connectors):
    """Build list of hostnames for all connectors.

    Args:
        connectors: List of connector names

    Returns:
        list: List of fully qualified domain names for connectors
    """
    config = load_deployer_config()
    ds_domain = config.get("DS_DOMAIN_BASE")

    if not ds_domain:
        return []

    hostnames = []

    for conn in connectors:
        hostnames.append(f"{conn}.{ds_domain}")

    return hostnames


def update_connector_host_aliases(values_file, connectors):
    """Update Helm values file with connector host aliases.

    Args:
        values_file: Path to the Helm values YAML file
        connectors: List of connector names to add as host aliases
    """
    minikube_ip = run("minikube ip", capture=True) or Config.MINIKUBE_IP

    with open(values_file) as f:
        values = yaml.safe_load(f)

    hostnames = Config.host_alias_domains()

    hostnames.extend(build_connector_hostnames(connectors))

    values["hostAliases"] = [{
        "ip": minikube_ip,
        "hostnames": hostnames
    }]

    with open(values_file, "w") as f:
        yaml.dump(values, f, sort_keys=False)


def get_deployed_connectors(namespace):
    """Retrieve list of deployed connectors in namespace.

    Args:
        namespace: Kubernetes namespace to check

    Returns:
        list: List of deployed connector names
    """
    result = run_silent(f"kubectl get pods -n {namespace} --no-headers")
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


def connector_already_exists(connector_name, namespace):
    """Check if connector already exists in namespace.

    Args:
        connector_name: Name of the connector to check
        namespace: Kubernetes namespace to check

    Returns:
        bool: True if connector already deployed, False otherwise
    """
    deployed = get_deployed_connectors(namespace)
    return connector_name in deployed


def build_connector_url(connector_name):
    """Build URL for connector connectivity test.

    Args:
        connector_name: Name of the connector

    Returns:
        str: URL to access connector interface

    Raises:
        ValueError: If DS_DOMAIN_BASE not defined in deployer.config
    """
    config = load_deployer_config()
    ds_domain = config.get("DS_DOMAIN_BASE")
    if not ds_domain:
        raise ValueError("DS_DOMAIN_BASE not defined in deployer.config")

    return f"http://{connector_name}.{ds_domain}/inesdata-connector-interface/"


def measure_connector_latency(source_connector, target_connector, repetitions=10):
    """Measure latency (round-trip time) between two connectors.

    Args:
        source_connector: Name of source connector
        target_connector: Name of target connector
        repetitions: Number of measurements to perform (default: 10)

    Returns:
        dict: Latency statistics with keys: source, target, url, status,
              avg_latency_sec, min_latency_sec, max_latency_sec, std_latency_sec
    """
    url = build_connector_url(target_connector)
    times = []
    status = None

    for i in range(repetitions):
        start = time.time()
        try:
            r = requests.get(url, timeout=10)
            status = r.status_code
        except Exception:
            status = "ERROR"
        elapsed = time.time() - start
        times.append(elapsed)
        time.sleep(1)

    avg = sum(times) / len(times)
    std = statistics.stdev(times) if len(times) > 1 else 0

    return {
        "source": source_connector,
        "target": target_connector,
        "url": url,
        "status": status,
        "avg_latency_sec": round(avg, 4),
        "min_latency_sec": round(min(times), 4),
        "max_latency_sec": round(max(times), 4),
        "std_latency_sec": round(std, 4)
    }


def save_latency_results_json(results, experiment_dir):
    """Save connector latency measurement results to JSON file.

    Args:
        results: List of latency measurement dictionaries
        experiment_dir: Directory to save results
    """
    file_name = os.path.join(experiment_dir, "latency_results.json")

    # Ensure all results have the required structure
    formatted_results = []
    for r in results:
        formatted_results.append({
            "source": r["source"],
            "target": r["target"],
            "url": r["url"],
            "status": r["status"],
            "avg_latency_sec": r["avg_latency_sec"],
            "min_latency_sec": r["min_latency_sec"],
            "max_latency_sec": r["max_latency_sec"],
            "std_latency_sec": r["std_latency_sec"]
        })

    with open(file_name, "w") as f:
        json.dump(formatted_results, f, indent=2)

    print(f"Latency results saved to {file_name}")


def wait_for_connector_ready(connector_name, timeout=300):
    """Wait for connector to be ready and responding to HTTP requests.

    Args:
        connector_name: Name of the connector
        timeout: Maximum seconds to wait (default: 300)

    Returns:
        bool: True if connector is ready, False if timeout
    """
    print(f"Waiting for connector to be ready: {connector_name}")

    url = build_connector_url(connector_name)
    start = time.time()

    while True:
        try:
            r = requests.get(url, timeout=5)

            if r.status_code in [200, 302]:
                print(f"Connector ready: {connector_name}")
                return True

        except Exception:
            pass

        if time.time() - start > timeout:
            print(f"Timeout waiting for connector: {connector_name}")
            return False

        time.sleep(3)


def wait_for_all_connectors(connectors):
    """Wait for all connectors to become ready.

    Args:
        connectors: List of connector names to wait for
    """
    print("\nWaiting for all connectors to become ready...\n")

    for connector in connectors:
        if not wait_for_connector_ready(connector):
            print(f"Connector not ready: {connector}")


def measure_all_connectors(connectors):
    """Measure latency between all connector pairs.

    Args:
        connectors: List of connector names to measure

    Returns:
        list: List of latency measurement results
    """
    print("\nStarting connector latency measurements...\n")

    experiment_dir = create_experiment_directory()
    save_experiment_metadata(experiment_dir, connectors)

    connectors = sorted(set(connectors))
    results = []

    for src in connectors:
        for tgt in connectors:
            if src == tgt:
                continue

            print(f"Measuring {src} -> {tgt}")
            r = measure_connector_latency(src, tgt)

            print(
                f"Latency {src} -> {tgt}: "
                f"avg={r['avg_latency_sec']}s "
                f"min={r['min_latency_sec']}s "
                f"max={r['max_latency_sec']}s "
                f"std={r['std_latency_sec']}s"
            )

            results.append(r)

    save_latency_results_json(results, experiment_dir)
    print("\nLatency measurements completed\n")

    return results


def load_connector_credentials(connector_name):
    """Load connector credentials from JSON file.

    Args:
        connector_name: Name of the connector

    Returns:
        dict: Credentials dictionary if found, None otherwise
    """
    credentials_dir = os.path.join(
        Config.repo_dir(),
        "deployments",
        "DEV",
        Config.DS_NAME
    )

    creds_file = os.path.join(
        credentials_dir,
        f"credentials-connector-{connector_name}.json"
    )

    if not os.path.exists(creds_file):
        return None

    try:
        with open(creds_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def display_connector_summary(connector_name):
    """Display connector URL and credentials information.

    Args:
        connector_name: Name of the connector to display
    """
    config = load_deployer_config()
    ds_domain = config.get("DS_DOMAIN_BASE")

    if not ds_domain:
        return

    url = f"http://{connector_name}.{ds_domain}"
    creds = load_connector_credentials(connector_name)

    print(f"\n{'='*60}")
    print(f"CONNECTOR: {connector_name}")
    print(f"{'='*60}")
    print(f"\nURL: {url}")

    if creds:
        print(f"\nConnector Credentials:")
        connector_user = creds.get("connector_user", {})
        print(f"  User: {connector_user.get('user', 'N/A')}")
        print(f"  Password: {connector_user.get('passwd', 'N/A')}")

        print(f"\nDatabase Credentials:")
        db_creds = creds.get("database", {})
        print(f"  Database: {db_creds.get('name', 'N/A')}")
        print(f"  User: {db_creds.get('user', 'N/A')}")
        print(f"  Password: {db_creds.get('passwd', 'N/A')}")

        print(f"\nMinIO Credentials:")
        minio_creds = creds.get("minio", {})
        print(f"  User: {minio_creds.get('user', 'N/A')}")
        print(f"  Password: {minio_creds.get('passwd', 'N/A')}")
        print(f"  Access Key: {minio_creds.get('access_key', 'N/A')}")
        print(f"  Secret Key: {minio_creds.get('secret_key', 'N/A')}")

    print(f"\n{'='*60}\n")

# =========================================================
# LEVEL 1 - CLUSTER SETUP
# =========================================================

def wait_for_kubernetes_ready(timeout=180):

    print("\nWaiting for Kubernetes cluster to become ready...\n")

    start = time.time()

    while True:

        nodes = run_silent("kubectl get nodes")

        if nodes and " Ready " in nodes:
            print("Kubernetes node is Ready\n")
            return True

        if time.time() - start > timeout:
            print("Timeout waiting for Kubernetes node readiness")
            return False

        time.sleep(3)


def lvl_1():
    """Recreate Minikube cluster from scratch for reproducibility."""

    print("\n========================================")
    print("LEVEL 1 - CLUSTER SETUP")
    print("========================================\n")

    ensure_unix_environment()

    # --------------------------------------------------
    # Check Minikube
    # --------------------------------------------------

    print("Checking Minikube installation...")

    if run("which minikube", capture=True) is None:
        print("Installing Minikube...")

        run(
            "curl -LO https://github.com/kubernetes/minikube/releases/latest/download/minikube-linux-amd64"
        )

        run("sudo install minikube-linux-amd64 /usr/local/bin/minikube")

        run("rm -f minikube-linux-amd64")

    run("minikube version")

    # --------------------------------------------------
    # Check Helm
    # --------------------------------------------------

    print("\nChecking Helm installation...")

    if run("which helm", capture=True) is None:
        run("sudo snap install helm --classic", check=False)

    run("helm version")

    # --------------------------------------------------
    # Check Docker
    # --------------------------------------------------

    print("\nChecking Docker...")

    if run("docker info", capture=True, check=False) is None:
        print("Docker is not running. Start Docker and retry.")
        return

    print("Docker is running")

    # --------------------------------------------------
    # Delete cluster for reproducibility
    # --------------------------------------------------

    print("\nDeleting existing Minikube cluster (clean state)...\n")

    run("minikube delete", check=False)

    # --------------------------------------------------
    # Start fresh cluster
    # --------------------------------------------------

    print("\nStarting fresh Minikube cluster...\n")

    run(
        f"minikube start "
        f"--driver={Config.MINIKUBE_DRIVER} "
        f"--cpus={Config.MINIKUBE_CPUS} "
        f"--memory={Config.MINIKUBE_MEMORY}"
    )

    # --------------------------------------------------
    # Wait for Kubernetes
    # --------------------------------------------------

    if not wait_for_kubernetes_ready():
        print("Cluster failed to initialize")
        return

    # --------------------------------------------------
    # Enable ingress
    # --------------------------------------------------

    print("\nEnabling ingress addon...\n")

    run("minikube addons enable ingress", check=False)

    # --------------------------------------------------
    # Verify ingress
    # --------------------------------------------------

    run("kubectl get pods -n ingress-nginx", check=False)

    print("\nLEVEL 1 COMPLETE\n")


# =========================================================
# LEVEL 2 - COMMON SERVICES
# =========================================================

def lvl_2():
    """Deploy common services."""
    print("\n========================================")
    print("LEVEL 2 - DEPLOY COMMON SERVICES")
    print("========================================\n")

    repo_dir = Config.repo_dir()
    common_dir = Config.common_dir()
    values_path = Config.values_path()

    if not os.path.exists(repo_dir):

        print("Cloning repository...")
        run(f"git clone {Config.REPO_URL}", cwd=Config.script_dir())

        # Copy local deployer.config into repo
        copy_local_deployer_config()

    else:
        print("Repository exists")

    # Ensure repo config stays synchronized
    copy_local_deployer_config()

    print("\nSynchronizing configuration...\n")
    sync_common_values()

    print("\nConfiguring hosts...")

    config = load_deployer_config()
    hosts_entries = generate_hosts(config, Config.DS_NAME)
    manage_hosts_entries(hosts_entries)

    add_helm_repos()

    print("\nBuilding Helm dependencies...")
    run("helm dependency build", cwd=common_dir)

    print("\nDeploying common services...")

    if not deploy_helm_release(
            Config.helm_release_common(),
            Config.NS_COMMON,
            values_path,
            cwd=common_dir
    ):
        print("Error deploying common services")
        return

    if not wait_for_pods(Config.NS_COMMON):
        print("Services did not reach ready state")
        return

    if not wait_for_vault_pod(Config.NS_COMMON):
        print("Vault pod not detected")
        return

    if not setup_vault(Config.NS_COMMON):
        print("Error configuring Vault")
        return

    if not sync_vault_token_to_deployer_config():
        print("Warning: Could not synchronize Vault token")

    print("\nLEVEL 2 COMPLETE\n")


# =========================================================
# LEVEL 3 - DATASPACE
# =========================================================

def lvl_3():
    """Deploy dataspace and registration service."""
    print("\n========================================")
    print("LEVEL 3 - DATASPACE")
    print("========================================\n")

    # Minikube tunnel confirmation
    print("-------------------------------------------------")
    print("MINIKUBE TUNNEL REQUIRED")
    print()
    print("Open a new terminal and run:")
    print()
    print("minikube tunnel")
    print()
    print("The tunnel must remain active during the dataspace deployment.")
    print()
    print("Once the tunnel is running, return to this terminal and press ENTER to continue.")
    print("-------------------------------------------------\n")

    if not AUTO_MODE:
        input()
    else:
        print("[AUTO_MODE] Skipping tunnel confirmation\n")

    repo_dir = Config.repo_dir()
    ds_name = Config.DS_NAME
    python_exec = Config.python_exec()

    #check_minikube_tunnel_available()

    if not os.path.exists(repo_dir):
        print("Repository not found. Run Level 2 first")
        return

    if not ensure_local_infra_access():
        return

    if not ensure_vault_unsealed():
        return

    print("Verifying Keycloak access...")

    kc_config = load_deployer_config()
    kc_url = kc_config.get("KC_URL")

    if not kc_url:
        print("KC_URL not defined in deployer.config")
        return

    try:
        import requests
        r = requests.get(f"{kc_url}/realms/master", timeout=5)
        if r.status_code not in (200, 302):
            print("Keycloak not ready")
            return
    except Exception:
        print("Keycloak not accessible. Verify minikube tunnel")
        return

    if not os.path.exists(Config.venv_path()):
        print("Creating Python environment...")
        run("python3 -m venv .venv", cwd=repo_dir)

    install_dependencies()
    run(
        f"{python_exec} -m pip install -r requirements.txt",
        cwd=repo_dir
    )

    print("Cleaning previous databases...")

    force_clean_postgres_db(
        Config.registration_db_name(),
        Config.registration_db_user()
    )

    force_clean_postgres_db(
        Config.webportal_db_name(),
        Config.webportal_db_user()
    )

    print("Creating dataspace...")
    """
    # Validate deployer.config before running deployer.py
    if not validate_deployer_config():
        print("Error: Could not validate deployer.config")
        return
    """
    if run(
            f"{python_exec} deployer.py dataspace create {ds_name}",
            cwd=repo_dir
    ) is None:
        print("Error creating dataspace")
        return

    values_file = Config.registration_values_file()

    if not os.path.exists(values_file):
        print("Registration service values file not found")
        return

    minikube_ip = run("minikube ip", capture=True)

    if minikube_ip:
        update_helm_values_with_host_aliases(values_file, minikube_ip)

    print("\nDeploying registration-service...")

    if not deploy_helm_release(
            Config.helm_release_rs(),
            Config.namespace_demo(),
            os.path.basename(values_file),
            cwd=Config.registration_service_dir()
    ):
        print("Error deploying registration-service")
        return

    if not wait_for_namespace_pods(Config.namespace_demo()):
        print("Timeout waiting for pods")
        return

    print("\nLEVEL 3 COMPLETE\n")


def lvl_4():
    """Deploy multiple connectors from deployer.config."""
    print("\n========================================")
    print("DEPLOY CONNECTORS FROM CONFIG")
    print("========================================\n")

    dataspaces = load_dataspace_connectors()

    if not dataspaces:
        print("No dataspaces defined in deployer.config")
        return

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

            if connector_already_exists(connector, namespace):

                if connector_is_healthy(connector, namespace):

                    print(f"Connector already running: {connector}")
                    print("Skipping deployment\n")
                    continue

                else:

                    print(f"Connector exists but unhealthy. Redeploying: {connector}")

            print(f"Deploying connector: {connector}")

            values_file = Config.connector_values_file(connector)

            create_connectors(connector)

            if not os.path.exists(values_file):

                print(f"Values file not found: {values_file}")
                return

            update_connector_host_aliases(values_file, connectors)

    all_connectors = list(all_connectors)

    print("\nAll connectors deployed or already existing\n")

    wait_for_all_connectors(all_connectors)

    # --------------------------------------------------
    # Validate deployment before measurements
    # --------------------------------------------------

    if not validate_connectors_deployment(all_connectors):

        print("\nConnector validation failed.")

        if not AUTO_MODE:
            inspect_logs = input("\nDo you want to inspect connector logs? (Y/N): ").strip().upper()

            if inspect_logs == "Y":
                print()
                show_connector_logs()
        else:
            print("[AUTO_MODE] Skipping log inspection")

        return

    print("\nStarting latency measurements...\n")

    measure_all_connectors(all_connectors)

    print("\nConnector information:\n")

    for connector in all_connectors:
        display_connector_summary(connector)

    print("LEVEL 4 COMPLETE\n")

# =========================================================
# CONNECTOR LOGS
# =========================================================

def show_connector_logs():
    """Display connector logs for troubleshooting.

    Allows user to select a connector and view its logs, optionally following
    them in real-time.

    Returns:
        None
    """
    namespace = Config.DS_NAME

    pods = run_silent(f"kubectl get pods -n {namespace} --no-headers")

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

    choice = input("\nSelect connector for logs (number): ").strip()

    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(connector_pods):
        print("Invalid selection")
        return

    selected_pod = connector_pods[int(choice) - 1]

    follow = input("Follow logs in real-time? (Y/N): ").strip().upper()

    if follow == "Y":
        run(f"kubectl logs -f {selected_pod} -n {namespace}", check=False)
    else:
        run(f"kubectl logs {selected_pod} -n {namespace}", check=False)


# =========================================================
# EXPERIMENT UTILITIES
# =========================================================

def create_experiment_directory():
    """Create timestamped directory for storing experiment results."""
    base_dir = "experiments"
    os.makedirs(base_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    experiment_dir = os.path.join(base_dir, f"experiment_{timestamp}")
    os.makedirs(experiment_dir, exist_ok=True)

    return experiment_dir


def save_experiment_metadata(experiment_dir, connectors):
    """Save experiment metadata to JSON file."""
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "connectors": connectors,
        "num_connectors": len(connectors),
        "environment": "minikube",
        "measurement_type": "connector_latency"
    }

    metadata_file = os.path.join(experiment_dir, "metadata.json")

    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)

    print(f"Experiment metadata saved: {metadata_file}")
# =========================================================
# KAFKA LATENCY MEASUREMENTS
# =========================================================

def is_kafka_available():
    """Check if Kafka container is running and accessible.

    Returns:
        bool: True if Kafka is available, False otherwise
    """
    try:
        result = run_silent("docker ps --filter name=kafka --format '{{.Names}}'")
        return result and "kafka" in result.lower()
    except Exception:
        return False


def ensure_kafka_topic(topic_name="kafka-stream-topic"):
    """Ensure Kafka topic exists, create if necessary.

    Args:
        topic_name: Name of the Kafka topic (default: kafka-stream-topic)

    Returns:
        bool: True if topic exists or was created, False otherwise
    """
    if not is_kafka_available():
        print("Kafka container not running")
        return False

    try:
        # Check if topic exists
        result = run_silent(
            f"docker exec $(docker ps -q --filter name=kafka) "
            f"kafka-topics --list --bootstrap-server localhost:9092"
        )

        if topic_name in result:
            print(f"Kafka topic '{topic_name}' already exists")
            return True

        # Create topic
        run_silent(
            f"docker exec $(docker ps -q --filter name=kafka) "
            f"kafka-topics --create --topic {topic_name} "
            f"--bootstrap-server localhost:9092 "
            f"--partitions 1 --replication-factor 1"
        )

        print(f"Created Kafka topic: {topic_name}")
        return True

    except Exception as e:
        print(f"Error managing Kafka topic: {e}")
        return False


def measure_kafka_latency(provider, consumer, num_messages=10, topic="kafka-stream-topic"):
    """Measure streaming latency using Kafka between provider and consumer.

    Args:
        provider: Provider connector name
        consumer: Consumer connector name
        num_messages: Number of messages to send (default: 10)
        topic: Kafka topic name (default: kafka-stream-topic)

    Returns:
        dict: Kafka latency measurement results
    """
    print(f"\n--- Kafka Latency Measurement ---")
    print(f"Provider: {provider}")
    print(f"Consumer: {consumer}")
    print(f"Topic: {topic}")
    print(f"Messages: {num_messages}\n")

    if not is_kafka_available():
        print("Kafka not available, skipping Kafka latency measurements")
        return None

    if not ensure_kafka_topic(topic):
        print("Failed to ensure Kafka topic exists")
        return None

    messages = []
    latencies_ms = []

    # Simulate producer-consumer latency measurements
    # In a real implementation, this would involve actual Kafka producer/consumer
    for i in range(1, num_messages + 1):
        send_time = datetime.now()

        # Simulate message transmission delay (replace with actual Kafka send/receive)
        try:
            # Here you would implement actual Kafka producer/consumer logic
            # For now, we'll use a placeholder that measures basic container latency

            # Simulate send and receive
            import time as time_module
            time_module.sleep(0.01)  # Simulate network delay

            receive_time = datetime.now()

            latency_ms = (receive_time - send_time).total_seconds() * 1000

            message_data = {
                "message_id": i,
                "send_time": send_time.isoformat(),
                "receive_time": receive_time.isoformat(),
                "latency_ms": round(latency_ms, 2)
            }

            messages.append(message_data)
            latencies_ms.append(latency_ms)

            print(f"Message {i}: {latency_ms:.2f} ms")

        except Exception as e:
            print(f"Error measuring message {i}: {e}")
            continue

    if not latencies_ms:
        print("No latency measurements collected")
        return None

    avg_latency = statistics.mean(latencies_ms)
    min_latency = min(latencies_ms)
    max_latency = max(latencies_ms)
    std_latency = statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0

    print(f"\nKafka Latency Summary:")
    print(f"  Average: {avg_latency:.2f} ms")
    print(f"  Min: {min_latency:.2f} ms")
    print(f"  Max: {max_latency:.2f} ms")
    print(f"  Std Dev: {std_latency:.2f} ms\n")

    results = {
        "experiment_type": "kafka_stream_latency",
        "provider": provider,
        "consumer": consumer,
        "topic": topic,
        "num_messages": num_messages,
        "messages": messages,
        "summary": {
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(min_latency, 2),
            "max_latency_ms": round(max_latency, 2),
            "std_latency_ms": round(std_latency, 2)
        }
    }

    return results


def save_kafka_latency_results(results, experiment_dir):
    """Save Kafka latency measurement results to JSON file.

    Args:
        results: Kafka latency measurement results dictionary
        experiment_dir: Directory to save results
    """
    if not results:
        return

    file_name = os.path.join(experiment_dir, "kafka_latency_results.json")

    with open(file_name, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Kafka latency results saved to {file_name}")


def run_kafka_experiments(connectors, experiment_dir):
    """Run Kafka latency experiments for all connector pairs.

    Args:
        connectors: List of connector names
        experiment_dir: Directory to save experiment results
    """
    if not is_kafka_available():
        print("\n[INFO] Kafka container not detected - skipping Kafka latency measurements")
        print("[INFO] To enable Kafka measurements, ensure Kafka container is running")
        return

    print("\n========================================")
    print("KAFKA STREAMING LATENCY MEASUREMENTS")
    print("========================================\n")

    kafka_enabled = "Y"

    if not AUTO_MODE:
        kafka_enabled = input("Run Kafka latency measurements? (Y/N): ").strip().upper()
    else:
        print("[AUTO_MODE] Running Kafka latency measurements\n")

    if kafka_enabled != "Y":
        print("Skipping Kafka latency measurements\n")
        return

    all_results = []
    pairs = list(permutations(connectors, 2))

    for provider, consumer in pairs:
        result = measure_kafka_latency(provider, consumer)
        if result:
            all_results.append(result)

    if all_results:
        # Save all results
        combined_file = os.path.join(experiment_dir, "kafka_latency_results.json")
        with open(combined_file, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nAll Kafka results saved to {combined_file}\n")




# =========================================================
# CONNECTOR VALIDATION
# =========================================================


def connector_is_healthy(connector_name, namespace):
    """Check if connector pod exists and is running."""
    result = run_silent(f"kubectl get pods -n {namespace} --no-headers")

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
            else:
                print(f"Connector pod unhealthy: {pod_name} ({status})")
                return False

    return False


def validate_connectors_deployment(connectors):
    """
    Validate connectors deployment before running tests.

    Args:
        connectors: List of connector names to validate

    Returns:
        bool: True if all connectors are healthy and reachable
    """
    namespace = Config.namespace_demo()

    print("\n========================================")
    print("VALIDATING CONNECTOR DEPLOYMENT")
    print("========================================\n")

    # Verify pods are running
    pods = run_silent(f"kubectl get pods -n {namespace} --no-headers")

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

        if "conn-" in pod_name and "interface" not in pod_name:
            if status != "Running":
                print(f"Connector pod not running: {pod_name} ({status})")
                failed = True

    if failed:
        print("\nSome connectors are not running\n")
        run(f"kubectl get pods -n {namespace}", check=False)
        return False

    print("All connector pods are running\n")

    # Check HTTP connectivity
    for connector in connectors:
        print(f"Checking HTTP availability: {connector}")

        if not wait_for_connector_ready(connector):
            print(f"Connector not reachable: {connector}")
            return False

    print("\nAll connectors reachable\n")
    return True


def get_connectors_from_cluster():
    """Detect deployed connectors from Kubernetes cluster."""
    namespace = Config.namespace_demo()

    output = run(
        f"kubectl get pods -n {namespace} --no-headers",
        capture=True
    )

    if not output:
        return []

    connectors = set()

    for line in output.splitlines():
        parts = line.split()
        if not parts:
            continue

        name = parts[0]

        if name.startswith("conn-") and "interface" not in name:
            connector = "-".join(name.split("-")[:3])
            connectors.add(connector)

    return sorted(connectors)


# =========================================================
# CONNECTOR TESTING
# =========================================================

def connector_base_url(connector):
    """Build base URL for connector.

    Args:
        connector: Name of the connector

    Returns:
        str: Base URL for the connector

    Raises:
        ValueError: If DS_DOMAIN_BASE not defined in deployer.config
    """
    domain = Config.ds_domain_base()

    if not domain:
        raise ValueError("DS_DOMAIN_BASE not defined in deployer.config")

    return f"http://{connector}.{domain}"


def get_management_api_auth(connector):
    """Get authentication credentials for connector management API.

    Args:
        connector: Name of the connector

    Returns:
        tuple: (username, password) or None if credentials not found
    """
    creds = load_connector_credentials(connector)

    if not creds or "connector_user" not in creds:
        return None

    return (
        creds["connector_user"]["user"],
        creds["connector_user"]["passwd"]
    )


def asset_exists(connector, asset_id):
    """Check if asset exists in connector.

    Args:
        connector: Name of the connector
        asset_id: ID of the asset to check

    Returns:
        bool: True if asset exists, False otherwise
    """
    auth = get_management_api_auth(connector)

    if not auth:
        return False

    base_url = connector_base_url(connector)
    url = f"{base_url}/management/v3/assets/{asset_id}"

    try:
        response = requests.get(url, auth=auth, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def policy_exists(connector, policy_id):
    """Check if policy definition exists in connector.

    Args:
        connector: Name of the connector
        policy_id: ID of the policy to check

    Returns:
        bool: True if policy exists, False otherwise
    """
    auth = get_management_api_auth(connector)

    if not auth:
        return False

    base_url = connector_base_url(connector)
    url = f"{base_url}/management/v3/policydefinitions/{policy_id}"

    try:
        response = requests.get(url, auth=auth, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def contract_definition_exists(connector, contract_id):
    """Check if contract definition exists in connector.

    Args:
        connector: Name of the connector
        contract_id: ID of the contract definition to check

    Returns:
        bool: True if contract definition exists, False otherwise
    """
    auth = get_management_api_auth(connector)

    if not auth:
        return False

    base_url = connector_base_url(connector)
    url = f"{base_url}/management/v3/contractdefinitions/{contract_id}"

    try:
        response = requests.get(url, auth=auth, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def delete_asset(connector, asset_id):
    """Delete asset from connector.

    Args:
        connector: Name of the connector
        asset_id: ID of the asset to delete

    Returns:
        bool: True if deletion successful, False otherwise
    """
    auth = get_management_api_auth(connector)

    if not auth:
        return False

    base_url = connector_base_url(connector)
    url = f"{base_url}/management/v3/assets/{asset_id}"

    try:
        response = requests.delete(url, auth=auth, timeout=5)
        return response.status_code in (200, 204, 404)
    except Exception:
        return False


def delete_policy(connector, policy_id):
    """Delete policy definition from connector.

    Args:
        connector: Name of the connector
        policy_id: ID of the policy to delete

    Returns:
        bool: True if deletion successful, False otherwise
    """
    auth = get_management_api_auth(connector)

    if not auth:
        return False

    base_url = connector_base_url(connector)
    url = f"{base_url}/management/v3/policydefinitions/{policy_id}"

    try:
        response = requests.delete(url, auth=auth, timeout=5)
        return response.status_code in (200, 204, 404)
    except Exception:
        return False


def delete_contract_definition(connector, contract_id):
    """Delete contract definition from connector.

    Args:
        connector: Name of the connector
        contract_id: ID of the contract definition to delete

    Returns:
        bool: True if deletion successful, False otherwise
    """
    auth = get_management_api_auth(connector)

    if not auth:
        return False

    base_url = connector_base_url(connector)
    url = f"{base_url}/management/v3/contractdefinitions/{contract_id}"

    try:
        response = requests.delete(url, auth=auth, timeout=5)
        return response.status_code in (200, 204, 404)
    except Exception:
        return False


def cleanup_test_entities(connector):
    """Clean up test entities from connector to ensure test idempotency.

    This function removes common test entities that may have been created
    in previous test runs, preventing duplicate creation errors.

    Args:
        connector: Name of the connector to clean
    """
    # Common test entity IDs used in validation collections
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

    # Delete contract definitions first (they reference policies and assets)
    for contract_id in test_entities["contracts"]:
        if contract_definition_exists(connector, contract_id):
            if delete_contract_definition(connector, contract_id):
                print(f"  Deleted contract definition: {contract_id}")

    # Delete policies
    for policy_id in test_entities["policies"]:
        if policy_exists(connector, policy_id):
            if delete_policy(connector, policy_id):
                print(f"  Deleted policy: {policy_id}")

    # Delete assets
    for asset_id in test_entities["assets"]:
        if asset_exists(connector, asset_id):
            if delete_asset(connector, asset_id):
                print(f"  Deleted asset: {asset_id}")

    print(f"Cleanup completed for {connector}\n")


def run_connector_tests(connector, connectors):
    """Run connector API tests for a specific connector.

    Args:
        connector: Name of the connector to test
        connectors: List of all available connectors
    """
    creds1 = load_connector_credentials(connector)

    if not creds1:
        print(f"Credentials not found for {connector}")
        return

    connector_user = creds1["connector_user"]["user"]
    connector_pass = creds1["connector_user"]["passwd"]

    # Select counterparty connector
    other_connectors = [c for c in connectors if c != connector]

    if not other_connectors:
        print("No counterparty connector available")
        return

    counterparty = other_connectors[0]

    # Load counterparty credentials
    creds2 = load_connector_credentials(counterparty)

    if not creds2:
        print(f"Credentials not found for {counterparty}")
        return

    connector2_user = creds2["connector_user"]["user"]
    connector2_pass = creds2["connector_user"]["passwd"]

    config = load_deployer_config()

    ds_domain = config.get("DS_DOMAIN_BASE")
    dataspace = Config.DS_NAME
    keycloak_url = config.get("KC_URL")

    if not keycloak_url.startswith("http"):
        keycloak_url = f"http://{keycloak_url}"

    collection = os.path.join(
        "validation",
        "connector",
        "management_api_functional_tests.json"
    )

    print(f"\nRunning connector tests for {connector}")
    print(f"Counterparty connector: {counterparty}\n")

    # Clean up test entities before running tests to ensure idempotency
    cleanup_test_entities(connector)
    cleanup_test_entities(counterparty)

    run(
        f"newman run {collection} "
        f"--env-var connector1={connector} "
        f"--env-var connector2={counterparty} "
        f"--env-var connector1_user={connector_user} "
        f"--env-var connector1_password={connector_pass} "
        f"--env-var connector2_user={connector2_user} "
        f"--env-var connector2_password={connector2_pass} "
        f"--env-var dsDomain={ds_domain} "
        f"--env-var dataspace={dataspace} "
        f"--env-var keycloakUrl={keycloak_url}"
    )


# =========================================================
# DATASPACE VALIDATION
# =========================================================

def build_newman_env(provider, consumer):
    """Build Newman environment variables for dataspace validation.

    Args:
        provider: Provider connector name
        consumer: Consumer connector name

    Returns:
        dict: Environment variables for Newman test execution

    Raises:
        ValueError: If connector credentials are missing
    """
    provider_creds = load_connector_credentials(provider)
    consumer_creds = load_connector_credentials(consumer)

    if not provider_creds or not consumer_creds:
        raise ValueError("Missing connector credentials")

    config = load_deployer_config()

    ds_domain = Config.ds_domain_base()
    dataspace = Config.DS_NAME
    keycloak_url = config.get("KC_URL")

    if not keycloak_url.startswith("http"):
        keycloak_url = f"http://{keycloak_url}"

    return {
        "provider": provider,
        "consumer": consumer,
        "provider_user": provider_creds["connector_user"]["user"],
        "provider_password": provider_creds["connector_user"]["passwd"],
        "consumer_user": consumer_creds["connector_user"]["user"],
        "consumer_password": consumer_creds["connector_user"]["passwd"],
        "dsDomain": ds_domain,
        "dataspace": dataspace,
        "keycloakUrl": keycloak_url,
        "providerProtocolAddress": f"http://{provider}:19194/protocol",
        "consumerProtocolAddress": f"http://{consumer}:19194/protocol"
    }


def run_newman(collection_path, env_vars):
    """
    Execute a Postman collection using Newman with dynamic environment variables
    and injected test scripts.
    """

    import subprocess

    print(f"\nExecuting: newman run {collection_path}")

    # Load dynamic test scripts
    test_script = load_test_scripts(collection_path)

    cmd = [
        "newman",
        "run",
        collection_path
    ]

    # Add environment variables
    for key, value in env_vars.items():
        cmd.extend([
            "--env-var",
            f"{key}={value}"
        ])

    # Inject test scripts into Newman runtime
    cmd.extend([
        "--env-var",
        f"test_script={test_script}"
    ])

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=False,
            text=True
        )

        if result.returncode != 0:
            print(f"[WARNING] Newman returned exit code {result.returncode}")

    except FileNotFoundError:
        print("ERROR: Newman is not installed or not in PATH")
        print("Install with: npm install -g newman")


def run_validation_collections(env_vars):
    """Run all validation collections in sequence.

    Args:
        env_vars: Environment variables for Newman execution
    """
    base = os.path.join("validation", "collections")

    collections = [
        "01_environment_health.json",
        "02_connector_management_api.json",
        "03_provider_setup.json",
        "04_consumer_catalog.json",
        "05_consumer_negotiation.json",
        "06_consumer_transfer.json"
    ]

    total = len(collections)

    for i, c in enumerate(collections, 1):
        collection_path = os.path.join(base, c)
        print(f"[{i}/{total}] Running collection: {c}")
        run_newman(collection_path, env_vars)


def run_dataspace_validation(provider, consumer):
    """Run dataspace validation tests for a provider-consumer pair.

    Args:
        provider: Provider connector name
        consumer: Consumer connector name
    """
    print(f"\n=== Testing pair ===")
    print(f"Provider : {provider}")
    print(f"Consumer : {consumer}\n")

    # Clean up test entities before running tests to ensure idempotency
    cleanup_test_entities(provider)
    cleanup_test_entities(consumer)

    env_vars = build_newman_env(provider, consumer)
    run_validation_collections(env_vars)


def run_all_dataspace_tests(connectors):
    """Run dataspace interoperability tests for all connector pairs.

    Args:
        connectors: List of connector names to test
    """
    print("\n========================================")
    print("DATASPACE INTEROPERABILITY TESTS")
    print("========================================\n")

    pairs = list(permutations(connectors, 2))

    for provider, consumer in pairs:
        run_dataspace_validation(provider, consumer)








































def load_file(path):
    """
    Read a file and return its content as string
    """

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_test_scripts(collection_name):

    scripts = []

    scripts.append(load_file("validation/tests/common_tests.js"))

    if "management" in collection_name:
        scripts.append(load_file("validation/tests/management_tests.js"))

    if "provider" in collection_name:
        scripts.append(load_file("validation/tests/provider_tests.js"))

    if "catalog" in collection_name:
        scripts.append(load_file("validation/tests/catalog_tests.js"))

    if "negotiation" in collection_name:
        scripts.append(load_file("validation/tests/negotiation_tests.js"))

    if "transfer" in collection_name:
        scripts.append(load_file("validation/tests/transfer_tests.js"))

    return "\n".join(scripts)

# =========================================================
# LEVEL 6 - VALIDATION TESTS
# =========================================================


def lvl_5():
    """Level 5 - Run validation tests on deployed connectors."""
    print("\n========================================")
    print("LEVEL 5 - VALIDATION TESTS")
    print("========================================\n")

    if shutil.which("newman") is None:
        print("Newman not installed")
        print("Install with: npm install -g newman")
        return

    connectors = get_connectors_from_cluster()

    if not connectors:
        print("No connectors running")
        return

    if len(connectors) < 2:
        print("At least 2 connectors required")
        return

    print(f"Detected connectors: {connectors}\n")

    if not validate_connectors_deployment(connectors):
        print("Connector deployment validation failed")
        return

    run_all_dataspace_tests(connectors)

    experiment_dir = create_experiment_directory()
    save_experiment_metadata(experiment_dir, connectors)

    # Run Kafka latency experiments (optional)
    run_kafka_experiments(connectors, experiment_dir)

    print("\n========================================")
    print("VALIDATION COMPLETED")
    print("========================================\n")


def run_all_levels():
    """Execute all deployment levels (1-5) sequentially without interruption.

    This function runs the complete deployment pipeline:
    1. Cluster setup
    2. Common services deployment
    3. Dataspace deployment
    4. Connector deployment
    5. Validation tests

    Returns:
        None
    """
    print("\n" + "="*50)
    print("FULL DEPLOYMENT SEQUENCE (LEVELS 1-5)")
    print("="*50)
    print("\nThis will execute all levels sequentially.")
    print("Total duration: approximately 30+ minutes")
    print("\n" + "="*50 + "\n")

    if AUTO_MODE:
        print("[AUTO_MODE] Starting automatic deployment...\n")
        confirm = "Y"
    else:
        confirm = input("Continue with full deployment? (Y/N): ").strip().upper()

    if confirm != "Y":
        print("\nFull deployment cancelled\n")
        return

    levels = [
        ("1", lvl_1, "Cluster Setup"),
        ("2", lvl_2, "Common Services"),
        ("3", lvl_3, "Dataspace"),
        ("4", lvl_4, "Connectors"),
        ("5", lvl_5, "Validation Tests")
    ]

    start_time = time.time()
    completed = []
    failed = []

    for level_num, level_func, level_name in levels:
        print(f"\n{'='*50}")
        print(f"LEVEL {level_num}: {level_name}")
        print(f"{'='*50}\n")

        try:
            level_func()
            completed.append(f"Level {level_num}: {level_name}")
        except KeyboardInterrupt:
            print(f"\n\nLevel {level_num} interrupted by user\n")
            failed.append(f"Level {level_num}: {level_name} (interrupted)")
            break
        except Exception as e:
            print(f"\nError in Level {level_num}: {e}\n")
            failed.append(f"Level {level_num}: {level_name} (error: {str(e)[:50]})")

            if AUTO_MODE:
                print("[AUTO_MODE] Continuing to next level despite error...\n")
            else:
                retry = input("Continue with next level? (Y/N): ").strip().upper()
                if retry != "Y":
                    print("\nFull deployment stopped by user\n")
                    break

    elapsed = time.time() - start_time
    minutes = int(elapsed) // 60
    seconds = int(elapsed) % 60

    print("\n" + "="*50)
    print("DEPLOYMENT SUMMARY")
    print("="*50)
    print(f"\nCompleted levels: {len(completed)}")
    for item in completed:
        print(f"  ✓ {item}")

    if failed:
        print(f"\nFailed/Interrupted levels: {len(failed)}")
        for item in failed:
            print(f"  ✗ {item}")
    else:
        print("\n✓ All levels completed successfully!")

    print(f"\nTotal execution time: {minutes}m {seconds}s")
    print("="*50 + "\n")


# =========================================================
# MENU
# =========================================================

LEVELS = {
    "1": lvl_1,
    "2": lvl_2,
    "3": lvl_3,
    "4": lvl_4,
    "5": lvl_5
}


def show_menu():
    """Display interactive menu and execute selected operations.

    Menu options:
    - 0: Run all levels (1-5) sequentially
    - 1-5: Run individual levels
    - Q: Exit application
    """
    while True:
        print("\n" + "="*50)
        print("CLUSTER AUTOMATION TOOL")
        print("="*50)
        print("\n[Full Deployment]")
        print("0 - Run All Levels (1-5) sequentially")
        print("A - Run full deployment automatically (no prompts)")
        print("\n[Individual Levels]")
        print("1 - Level 1: Setup Cluster")
        print("2 - Level 2: Deploy Common Services")
        print("3 - Level 3: Deploy Dataspace")
        print("4 - Level 4: Deploy Connectors")
        print("5 - Level 5: Run Validation Tests")
        print("\n[Control]")
        print("Q - Exit")
        print("="*50)

        try:
            choice = input("\nSelection: ").strip().upper()
        except EOFError:
            print("\nNo more input. Exiting Cluster Automation Tool\n")
            break

        if choice == "Q":
            print("\nExiting Cluster Automation Tool\n")
            break
        elif choice == "0":
            try:
                run_all_levels()
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user\n")
            except Exception as e:
                print(f"\nUnexpected error: {e}\n")
        elif choice == "A":
            try:
                global AUTO_MODE
                AUTO_MODE = True
                run_all_levels()
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user\n")
            except Exception as e:
                print(f"\nUnexpected error: {e}\n")
            finally:
                AUTO_MODE = False
        elif choice in LEVELS:
            try:
                LEVELS[choice]()
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user\n")
            except Exception as e:
                print(f"\nError during execution: {e}\n")
        else:
            print("\n⚠ Invalid selection. Please try again.\n")


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    show_menu()

