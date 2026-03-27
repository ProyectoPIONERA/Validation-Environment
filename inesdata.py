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
import socket
import shutil
import statistics
import re
from itertools import combinations
from itertools import permutations
from datetime import datetime
from runtime_dependencies import ensure_runtime_dependencies


ensure_runtime_dependencies(
    requirements_path=os.path.join(os.path.dirname(__file__), "requirements.txt"),
    module_names=("yaml", "requests", "tabulate", "ruamel.yaml", "minio", "kafka"),
    label="legacy INESData entrypoint",
)

import yaml
import requests
import main as framework_cli
from tabulate import tabulate
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
from framework.experiment_storage import ExperimentStorage
from framework.kafka_edc_validation import KafkaEdcValidationSuite
from framework.newman_executor import NewmanExecutor
from framework.transfer_storage_verifier import TransferStorageVerifier
from framework.validation_engine import ValidationEngine
from framework.metrics_collector import MetricsCollector
from adapters.inesdata import InesdataAdapter, InesdataConfig



# =========================================================
# CENTRALIZED CONFIGURATION
# =========================================================

class Config:
    """Centralized technical configuration."""

    # Deployment
    REPO_URL = "https://github.com/ProyectoPIONERA/inesdata-deployment.git"
    REPO_DIR = "inesdata-deployment"
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
NEWMAN_EXECUTOR = NewmanExecutor()

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
        choice = input("\nAdd missing entries to hosts file? (Y/N, default: Y): ").strip().upper() or "Y"
    
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
        f"timeout 20 kubectl exec {pod} -n {Config.NS_COMMON} -- vault status -format=json"
    )

    if not status:
        ready_state = run_silent(
            f"kubectl get pod {pod} -n {Config.NS_COMMON} "
            "-o jsonpath='{.status.containerStatuses[0].ready}'"
        )
        if (ready_state or "").strip("'\"").lower() == "true":
            print("Vault status probe timed out, but the Vault pod is Ready. Assuming Vault is already unsealed.")
            return True
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

    print("\nConfiguration synchronization: deployer.config -> common/values.yaml\n")

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


INESDATA_ADAPTER = InesdataAdapter(
    run=run,
    run_silent=run_silent,
    auto_mode_getter=lambda: AUTO_MODE,
)
Config = InesdataConfig
copy_local_deployer_config = INESDATA_ADAPTER.config_adapter.copy_local_deployer_config
load_deployer_config = INESDATA_ADAPTER.config_adapter.load_deployer_config
get_pg_credentials = INESDATA_ADAPTER.config_adapter.get_pg_credentials
generate_hosts = INESDATA_ADAPTER.config_adapter.generate_hosts
sync_common_values = INESDATA_ADAPTER.infrastructure.sync_common_values
deploy_helm_release = INESDATA_ADAPTER.infrastructure.deploy_helm_release
add_helm_repos = INESDATA_ADAPTER.infrastructure.add_helm_repos
get_pod_by_name = INESDATA_ADAPTER.infrastructure.get_pod_by_name
wait_for_pods = INESDATA_ADAPTER.infrastructure.wait_for_pods
wait_for_namespace_pods = INESDATA_ADAPTER.infrastructure.wait_for_namespace_pods
port_forward_service = INESDATA_ADAPTER.infrastructure.port_forward_service
wait_for_port = INESDATA_ADAPTER.infrastructure.wait_for_port
wait_for_vault_pod = INESDATA_ADAPTER.infrastructure.wait_for_vault_pod
setup_vault = INESDATA_ADAPTER.infrastructure.setup_vault
ensure_vault_unsealed = INESDATA_ADAPTER.infrastructure.ensure_vault_unsealed
sync_vault_token_to_deployer_config = INESDATA_ADAPTER.infrastructure.sync_vault_token_to_deployer_config
ensure_local_infra_access = INESDATA_ADAPTER.infrastructure.ensure_local_infra_access
wait_for_kubernetes_ready = INESDATA_ADAPTER.infrastructure.wait_for_kubernetes_ready
load_dataspace_connectors = INESDATA_ADAPTER.connectors.load_dataspace_connectors
validate_connector_name = INESDATA_ADAPTER.connectors.validate_connector_name
build_connector_hostnames = INESDATA_ADAPTER.connectors.build_connector_hostnames
update_connector_host_aliases = INESDATA_ADAPTER.connectors.update_connector_host_aliases
get_deployed_connectors = INESDATA_ADAPTER.connectors.get_deployed_connectors
connector_already_exists = INESDATA_ADAPTER.connectors.connector_already_exists
build_connector_url = INESDATA_ADAPTER.connectors.build_connector_url
wait_for_connector_ready = INESDATA_ADAPTER.connectors.wait_for_connector_ready
wait_for_all_connectors = INESDATA_ADAPTER.connectors.wait_for_all_connectors
load_connector_credentials = INESDATA_ADAPTER.connectors.load_connector_credentials
display_connector_summary = INESDATA_ADAPTER.connectors.display_connector_summary
setup_minio_bucket = INESDATA_ADAPTER.connectors.setup_minio_bucket
ensure_all_minio_policies = INESDATA_ADAPTER.connectors.ensure_all_minio_policies
force_clean_postgres_db = INESDATA_ADAPTER.connectors.force_clean_postgres_db
create_connectors = INESDATA_ADAPTER.connectors.create_connector
show_connector_logs = INESDATA_ADAPTER.connectors.show_connector_logs
lvl_1 = INESDATA_ADAPTER.setup_cluster
lvl_2 = INESDATA_ADAPTER.deploy_infrastructure
lvl_3 = INESDATA_ADAPTER.deploy_dataspace


def _validate_connectors_with_stabilization(connectors, retries=2, wait_seconds=20, backoff_factor=2):
    """Retry connector validation after short stabilization waits with light backoff.

    This avoids false negatives immediately after rollout operations.
    """
    if validate_connectors_deployment(connectors):
        return True

    retries = max(int(retries or 0), 0)
    current_wait = max(int(wait_seconds or 0), 0)
    backoff_factor = max(int(backoff_factor or 1), 1)

    for attempt in range(1, retries + 1):
        print(
            f"\nConnector validation failed (attempt {attempt}/{retries + 1}). "
            f"Waiting {current_wait}s for stabilization before retry..."
        )
        if current_wait > 0:
            time.sleep(current_wait)
        if validate_connectors_deployment(connectors):
            print("Connector validation recovered after stabilization retry.")
            return True
        current_wait *= backoff_factor

    return False


def lvl_4():
    """Deploy connectors and run post-deployment checks."""
    all_connectors = INESDATA_ADAPTER.deploy_connectors()

    if not all_connectors:
        raise RuntimeError("Level 4 did not deploy any connectors")

    _maybe_apply_local_image_override_after_level_4()

    if not _validate_connectors_with_stabilization(all_connectors):
        print("\nConnector validation failed.")

        if not AUTO_MODE:
            inspect_logs = input("\nDo you want to inspect connector logs? (Y/N, default: Y): ").strip().upper() or "Y"
            if inspect_logs == "Y":
                print()
                show_connector_logs()
        else:
            print("[AUTO_MODE] Skipping log inspection")

        raise RuntimeError("Level 4 connectors were not stable enough for Level 6")

    print("\nStarting latency measurements...\n")
    METRICS_COLLECTOR.measure_all_connectors(all_connectors)

    print("\nConnector information:\n")
    for connector in all_connectors:
        display_connector_summary(connector)

    print("LEVEL 4 COMPLETE\n")

# =========================================================
# KAFKA LATENCY MEASUREMENTS
# =========================================================

def is_kafka_available():
    """Check if Kafka container is running and accessible.
    
    Returns:
        bool: True if Kafka is available, False otherwise
    """
    adapter_method = getattr(INESDATA_ADAPTER, "is_kafka_available", None)
    if callable(adapter_method):
        try:
            return bool(adapter_method())
        except Exception:
            return False
    return False


def ensure_kafka_topic(topic_name="kafka-stream-topic"):
    """Ensure Kafka topic exists, create if necessary.
    
    Args:
        topic_name: Name of the Kafka topic (default: kafka-stream-topic)
        
    Returns:
        bool: True if topic exists or was created, False otherwise
    """
    adapter_method = getattr(INESDATA_ADAPTER, "ensure_kafka_topic", None)
    if callable(adapter_method):
        try:
            return bool(adapter_method(topic_name))
        except Exception as e:
            print(f"Error managing Kafka topic: {e}")
            return False
    return False


METRICS_COLLECTOR = MetricsCollector(
    build_connector_url=build_connector_url,
    is_kafka_available=is_kafka_available,
    ensure_kafka_topic=ensure_kafka_topic,
    experiment_storage=ExperimentStorage,
    auto_mode=lambda: AUTO_MODE,
)
LEVEL6_KAFKA_METRICS_COLLECTOR = framework_cli.build_metrics_collector(
    INESDATA_ADAPTER,
    collector_cls=MetricsCollector,
    experiment_storage=ExperimentStorage,
    kafka_enabled=True,
)
LEVEL6_KAFKA_MANAGER = framework_cli.build_kafka_manager(INESDATA_ADAPTER)

# Metrics collection helpers moved to framework.metrics_collector.MetricsCollector


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
        
        if "conn-" in pod_name and "interface" not in pod_name and "inteface" not in pod_name:
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
        
        if name.startswith("conn-") and "interface" not in name and "inteface" not in name:
            connector = "-".join(name.split("-")[:3])
            connectors.add(connector)
    
    return sorted(connectors)


connector_is_healthy = INESDATA_ADAPTER.connectors.connector_is_healthy
validate_connectors_deployment = INESDATA_ADAPTER.connectors.validate_connectors_deployment
get_connectors_from_cluster = INESDATA_ADAPTER.get_cluster_connectors

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

VALIDATION_ENGINE = ValidationEngine(
    newman_executor=NEWMAN_EXECUTOR,
    load_connector_credentials=load_connector_credentials,
    load_deployer_config=load_deployer_config,
    cleanup_test_entities=cleanup_test_entities,
    validation_test_entities_absent=INESDATA_ADAPTER.connectors.validation_test_entities_absent,
    ds_domain_resolver=Config.ds_domain_base,
    ds_name=Config.DS_NAME,
    transfer_storage_verifier=TransferStorageVerifier(
        load_connector_credentials=load_connector_credentials,
        load_deployer_config=load_deployer_config,
        experiment_storage=ExperimentStorage,
    ),
)

# Dataspace validation helpers moved to framework.validation_engine.ValidationEngine


def _save_level6_experiment_state(
    experiment_dir,
    connectors,
    *,
    status,
    validation_reports=None,
    newman_request_metrics=None,
    kafka_metrics=None,
    kafka_edc_results=None,
    storage_checks=None,
    ui_results=None,
    component_results=None,
    error=None,
):
    ui_validation = _aggregate_level6_ui_results(
        ui_results or [],
        experiment_dir=experiment_dir,
    )
    payload = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "source": "inesdata.py:level6",
        "connectors": list(connectors or []),
        "validation_reports": list(validation_reports or []),
        "newman_request_metrics": list(newman_request_metrics or []),
        "kafka_metrics": kafka_metrics,
        "kafka_edc_results": list(kafka_edc_results or []),
        "storage_checks": list(storage_checks or []),
        "ui_results": list(ui_results or []),
        "ui_validation": ui_validation,
        "component_results": list(component_results or []),
        "error": error,
    }
    ExperimentStorage.save(payload, experiment_dir=experiment_dir)
    return payload


def _run_level6_kafka_benchmark(experiment_dir):
    run_benchmark = getattr(LEVEL6_KAFKA_METRICS_COLLECTOR, "run_kafka_benchmark_experiment", None)
    if not callable(run_benchmark):
        return None
    try:
        return run_benchmark(
            experiment_dir,
            iterations=1,
            kafka_manager=LEVEL6_KAFKA_MANAGER,
        )
    finally:
        stop_kafka = getattr(LEVEL6_KAFKA_MANAGER, "stop_kafka", None)
        if callable(stop_kafka):
            stop_kafka()


LEVEL6_KAFKA_EDC_VALIDATOR = KafkaEdcValidationSuite(
    load_connector_credentials=load_connector_credentials,
    load_deployer_config=load_deployer_config,
    kafka_runtime_loader=INESDATA_ADAPTER.get_kafka_config,
    ensure_kafka_topic=INESDATA_ADAPTER.ensure_kafka_topic,
    kafka_manager=LEVEL6_KAFKA_MANAGER,
    experiment_storage=ExperimentStorage,
    ds_domain_resolver=Config.ds_domain_base,
    ds_name_loader=InesdataConfig.dataspace_name,
)


LEVEL6_UI_SMOKE_SPECS = (
    os.path.join("core", "01-login-readiness.spec.ts"),
    os.path.join("core", "04-consumer-catalog.spec.ts"),
)
LEVEL6_UI_DATASPACE_SPECS = (
    os.path.join("core", "03-provider-setup.spec.ts"),
    os.path.join("core", "03b-provider-policy-create.spec.ts"),
    os.path.join("core", "03c-provider-contract-definition-create.spec.ts"),
    os.path.join("core", "05-consumer-negotiation.spec.ts"),
    os.path.join("core", "06-consumer-transfer.spec.ts"),
)
LEVEL6_UI_OPS_SPEC = os.path.join("ops", "minio-bucket-visibility.spec.ts")
LEVEL6_UI_OPS_CONFIG = "playwright.ops.config.ts"


def _env_flag_enabled(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _config_or_env_flag_enabled(name, default=False):
    if name in os.environ:
        return _env_flag_enabled(name, default=default)

    deployer_config = load_deployer_config() or {}
    raw = deployer_config.get(name)
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _build_level6_ui_artifact_paths(experiment_dir, connector):
    base_dir = os.path.join(experiment_dir, "ui", connector)
    paths = {
        "base_dir": base_dir,
        "output_dir": os.path.join(base_dir, "test-results"),
        "html_report_dir": os.path.join(base_dir, "playwright-report"),
        "blob_report_dir": os.path.join(base_dir, "blob-report"),
        "json_report_file": os.path.join(base_dir, "results.json"),
        "report_json": os.path.join(base_dir, "ui_core_validation.json"),
    }
    for path in paths.values():
        if path.endswith(".json"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            os.makedirs(path, exist_ok=True)
    return paths


def _build_level6_ui_ops_artifact_paths(experiment_dir):
    base_dir = os.path.join(experiment_dir, "ui-ops", "minio-console")
    paths = {
        "base_dir": base_dir,
        "output_dir": os.path.join(base_dir, "test-results"),
        "html_report_dir": os.path.join(base_dir, "playwright-report"),
        "blob_report_dir": os.path.join(base_dir, "blob-report"),
        "json_report_file": os.path.join(base_dir, "results.json"),
        "report_json": os.path.join(base_dir, "ui_ops_validation.json"),
    }
    for path in paths.values():
        if path.endswith(".json"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            os.makedirs(path, exist_ok=True)
    return paths


def _build_level6_ui_dataspace_artifact_paths(experiment_dir, provider_connector, consumer_connector):
    base_dir = os.path.join(experiment_dir, "ui-dataspace", f"{provider_connector}__{consumer_connector}")
    paths = {
        "base_dir": base_dir,
        "output_dir": os.path.join(base_dir, "test-results"),
        "html_report_dir": os.path.join(base_dir, "playwright-report"),
        "blob_report_dir": os.path.join(base_dir, "blob-report"),
        "json_report_file": os.path.join(base_dir, "results.json"),
        "report_json": os.path.join(base_dir, "ui_dataspace_validation.json"),
    }
    for path in paths.values():
        if path.endswith(".json"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            os.makedirs(path, exist_ok=True)
    return paths


def _run_level6_ui_smoke(ui_test_dir, connector, portal_url, portal_user, portal_pass, experiment_dir):
    artifact_paths = _build_level6_ui_artifact_paths(experiment_dir, connector)
    env = {
        **os.environ,
        "PORTAL_BASE_URL": portal_url,
        "PORTAL_USER": portal_user,
        "PORTAL_PASSWORD": portal_pass,
        "PLAYWRIGHT_OUTPUT_DIR": artifact_paths["output_dir"],
        "PLAYWRIGHT_HTML_REPORT_DIR": artifact_paths["html_report_dir"],
        "PLAYWRIGHT_BLOB_REPORT_DIR": artifact_paths["blob_report_dir"],
        "PLAYWRIGHT_JSON_REPORT_FILE": artifact_paths["json_report_file"],
    }
    specs = list(LEVEL6_UI_SMOKE_SPECS)
    print(f"  Level 6 UI smoke profile for {connector}: {', '.join(specs)}")
    command = ["npx", "playwright", "test", *specs]
    error = None
    try:
        result = subprocess.run(
            command,
            cwd=ui_test_dir,
            env=env,
        )
        status = "passed" if result.returncode == 0 else "failed"
        exit_code = result.returncode
    except OSError as exc:
        status = "skipped"
        exit_code = None
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    result = {
        "connector": connector,
        "test": "ui-core-smoke",
        "status": status,
        "exit_code": exit_code,
        "portal_url": portal_url,
        "specs": specs,
        "artifacts": {
            "test_results_dir": artifact_paths["output_dir"],
            "html_report_dir": artifact_paths["html_report_dir"],
            "blob_report_dir": artifact_paths["blob_report_dir"],
            "json_report_file": artifact_paths["json_report_file"],
            "report_json": artifact_paths["report_json"],
        },
        "error": error,
    }
    return _enrich_level6_ui_result(result)


def _run_level6_ui_dataspace(ui_test_dir, provider_connector, consumer_connector, experiment_dir):
    artifact_paths = _build_level6_ui_dataspace_artifact_paths(
        experiment_dir,
        provider_connector,
        consumer_connector,
    )
    env = {
        **os.environ,
        "UI_PROVIDER_CONNECTOR": provider_connector,
        "UI_CONSUMER_CONNECTOR": consumer_connector,
        # Level 6 validates the end-to-end publication flow, not upload stress limits.
        # A smaller default fixture keeps the UI upload deterministic on shared clusters
        # while still exercising the real storage/upload path.
        "PORTAL_TEST_FILE_MB": os.environ.get("PORTAL_TEST_FILE_MB") or "10",
        "PLAYWRIGHT_OUTPUT_DIR": artifact_paths["output_dir"],
        "PLAYWRIGHT_HTML_REPORT_DIR": artifact_paths["html_report_dir"],
        "PLAYWRIGHT_BLOB_REPORT_DIR": artifact_paths["blob_report_dir"],
        "PLAYWRIGHT_JSON_REPORT_FILE": artifact_paths["json_report_file"],
    }
    specs = list(LEVEL6_UI_DATASPACE_SPECS)
    print(
        f"  Level 6 UI dataspace profile for {provider_connector} -> "
        f"{consumer_connector}: {', '.join(specs)}"
    )
    # These flows share the same provider/consumer pair and stress catalog propagation.
    # Running them serially in Level 6 avoids false negatives caused by concurrent UI workers.
    command = ["npx", "playwright", "test", "--workers=1", *specs]
    error = None
    try:
        result = subprocess.run(
            command,
            cwd=ui_test_dir,
            env=env,
        )
        status = "passed" if result.returncode == 0 else "failed"
        exit_code = result.returncode
    except OSError as exc:
        status = "skipped"
        exit_code = None
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    result = {
        "provider_connector": provider_connector,
        "consumer_connector": consumer_connector,
        "test": "ui-core-dataspace",
        "status": status,
        "exit_code": exit_code,
        "specs": specs,
        "artifacts": {
            "test_results_dir": artifact_paths["output_dir"],
            "html_report_dir": artifact_paths["html_report_dir"],
            "blob_report_dir": artifact_paths["blob_report_dir"],
            "json_report_file": artifact_paths["json_report_file"],
            "report_json": artifact_paths["report_json"],
        },
        "error": error,
    }
    return _enrich_level6_ui_result(result)


def _wait_for_level6_keycloak_readiness() -> bool:
    deployer_config = load_deployer_config() or {}
    if not all(
        deployer_config.get(key)
        for key in ("KC_URL", "KC_USER", "KC_PASSWORD")
    ):
        print("Keycloak readiness check skipped: KC_URL/KC_USER/KC_PASSWORD missing")
        return True

    connectors_adapter = getattr(INESDATA_ADAPTER, "connectors", None)
    wait_for_keycloak_admin_ready = getattr(connectors_adapter, "wait_for_keycloak_admin_ready", None)
    if not callable(wait_for_keycloak_admin_ready):
        print("Keycloak readiness check skipped: connector adapter does not expose wait_for_keycloak_admin_ready")
        return True

    return bool(wait_for_keycloak_admin_ready())


def _run_level6_ui_ops(ui_test_dir, provider_connector, consumer_connector, experiment_dir):
    artifact_paths = _build_level6_ui_ops_artifact_paths(experiment_dir)
    env = {
        **os.environ,
        "UI_PROVIDER_CONNECTOR": provider_connector,
        "UI_CONSUMER_CONNECTOR": consumer_connector,
        "PLAYWRIGHT_OPS_OUTPUT_DIR": artifact_paths["output_dir"],
        "PLAYWRIGHT_OPS_HTML_REPORT_DIR": artifact_paths["html_report_dir"],
        "PLAYWRIGHT_OPS_BLOB_REPORT_DIR": artifact_paths["blob_report_dir"],
        "PLAYWRIGHT_OPS_JSON_REPORT_FILE": artifact_paths["json_report_file"],
    }
    command = [
        "npx",
        "playwright",
        "test",
        "--config",
        LEVEL6_UI_OPS_CONFIG,
        LEVEL6_UI_OPS_SPEC,
    ]
    error = None
    try:
        result = subprocess.run(
            command,
            cwd=ui_test_dir,
            env=env,
        )
        status = "passed" if result.returncode == 0 else "failed"
        exit_code = result.returncode
    except OSError as exc:
        status = "skipped"
        exit_code = None
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    result = {
        "test": "ui-ops-minio-console",
        "status": status,
        "exit_code": exit_code,
        "provider_connector": provider_connector,
        "consumer_connector": consumer_connector,
        "specs": [LEVEL6_UI_OPS_SPEC],
        "playwright_config": LEVEL6_UI_OPS_CONFIG,
        "artifacts": {
            "test_results_dir": artifact_paths["output_dir"],
            "html_report_dir": artifact_paths["html_report_dir"],
            "blob_report_dir": artifact_paths["blob_report_dir"],
            "json_report_file": artifact_paths["json_report_file"],
            "report_json": artifact_paths["report_json"],
        },
        "error": error,
    }
    return _enrich_level6_ui_result(result)


def _enrich_level6_ui_result(result):
    try:
        from validation.ui.reporting import enrich_level6_ui_result
    except Exception as exc:  # pragma: no cover - defensive import guard
        enriched = dict(result or {})
        enriched["reporting_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        return enriched

    try:
        return enrich_level6_ui_result(result or {})
    except Exception as exc:  # pragma: no cover - defensive integration guard
        enriched = dict(result or {})
        enriched["reporting_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        return enriched


def _aggregate_level6_ui_results(ui_results, experiment_dir):
    try:
        from validation.ui.reporting import aggregate_level6_ui_results
    except Exception as exc:  # pragma: no cover - defensive import guard
        return {
            "scope": "dataspace_ui",
            "status": "not_run" if not ui_results else "skipped",
            "summary": {
                "total": len(list(ui_results or [])),
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "not_run": 0 if ui_results else 1,
            },
            "suite_runs": [],
            "executed_cases": [],
            "dataspace_cases": [],
            "support_checks": [],
            "ops_checks": [],
            "execution_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "dataspace_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "support_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "ops_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "catalog_coverage_summary": {
                "dataspace_cases": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "support_checks": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "ops_checks": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            },
            "evidence_index": [],
            "findings": [],
            "catalog_alignment": {},
            "artifacts": {},
            "reporting_error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

    try:
        return aggregate_level6_ui_results(ui_results or [], experiment_dir=experiment_dir)
    except Exception as exc:  # pragma: no cover - defensive integration guard
        return {
            "scope": "dataspace_ui",
            "status": "not_run" if not ui_results else "skipped",
            "summary": {
                "total": len(list(ui_results or [])),
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "not_run": 0 if ui_results else 1,
            },
            "suite_runs": [],
            "executed_cases": [],
            "dataspace_cases": [],
            "support_checks": [],
            "ops_checks": [],
            "execution_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "dataspace_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "support_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "ops_summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "catalog_coverage_summary": {
                "dataspace_cases": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "support_checks": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "ops_checks": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            },
            "evidence_index": [],
            "findings": [],
            "catalog_alignment": {},
            "artifacts": {},
            "reporting_error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }


def _configured_optional_components():
    deployer_config = load_deployer_config() or {}
    raw = (deployer_config.get("COMPONENTS") or "").strip()
    if not raw:
        return []
    return [token.strip().lower().replace("_", "-") for token in raw.split(",") if token.strip()]


def _should_run_level6_kafka_edc_validation():
    return _config_or_env_flag_enabled("LEVEL6_RUN_KAFKA_EDC", default=False)


def _run_level6_kafka_edc_validation(connectors, experiment_dir):
    if len(connectors) < 2:
        return [
            {
                "status": "skipped",
                "reason": "not_enough_connectors",
                "timestamp": datetime.now().isoformat(),
            }
        ]

    results = LEVEL6_KAFKA_EDC_VALIDATOR.run_all(connectors, experiment_dir=experiment_dir) or []
    ExperimentStorage.save_kafka_edc_results_json(results, experiment_dir)
    return results


def _should_run_level6_component_validation():
    components = _configured_optional_components()
    if not components:
        return False

    raw = os.environ.get("LEVEL6_RUN_COMPONENT_VALIDATION")
    if raw is None:
        return True

    return _env_flag_enabled("LEVEL6_RUN_COMPONENT_VALIDATION", default=True)


def _run_level6_component_validations(experiment_dir):
    from adapters.inesdata.components import INESDataComponentsAdapter
    from validation.components.runner import run_component_validations

    components = _configured_optional_components()
    if not components:
        return []

    components_adapter = INESDataComponentsAdapter(
        run=run,
        run_silent=run_silent,
        auto_mode_getter=lambda: AUTO_MODE,
        infrastructure_adapter=INESDATA_ADAPTER.infrastructure,
        config_adapter=INESDATA_ADAPTER.config_adapter,
        config_cls=InesdataConfig,
    )
    component_urls = components_adapter.infer_component_urls(components)

    results = run_component_validations(component_urls, experiment_dir=experiment_dir)
    resolved_components = {result.get("component") for result in results}
    for component in components:
        if component not in resolved_components:
            results.append(
                {
                    "component": component,
                    "status": "skipped",
                    "reason": "component_url_not_inferred",
                    "timestamp": datetime.now().isoformat(),
                }
            )
    return results


def _connector_hosts_resolve(connectors):
    unresolved = []
    domain = Config.ds_domain_base()
    if not domain:
        return unresolved

    for connector in connectors or []:
        host = f"{connector}.{domain}"
        try:
            socket.gethostbyname(host)
        except OSError:
            unresolved.append(host)

    return unresolved


def _ensure_level6_connector_hosts(connectors):
    connector_hosts = INESDATA_ADAPTER.config_adapter.generate_connector_hosts(connectors)
    if connector_hosts:
        INESDATA_ADAPTER.infrastructure.manage_hosts_entries(
            connector_hosts,
            header_comment="# Dataspace Connector Hosts",
        )

    unresolved = _connector_hosts_resolve(connectors)
    if unresolved:
        joined = ", ".join(unresolved)
        raise RuntimeError(
            "Connector hostnames do not resolve locally. "
            f"Check /etc/hosts and minikube tunnel for: {joined}"
        )


def _ensure_level6_connectors_ready():
    if not ensure_vault_unsealed():
        raise RuntimeError("Vault is sealed or unavailable")

    connectors = get_connectors_from_cluster()
    if connectors:
        return connectors

    print("No running connectors detected after Vault recovery. Waiting for demo namespace pods...")
    INESDATA_ADAPTER.infrastructure.wait_for_namespace_pods(
        Config.namespace_demo(),
        timeout=120,
    )
    return get_connectors_from_cluster()

# =========================================================
# LEVEL 6 - VALIDATION TESTS
# =========================================================

def lvl_6():
    """Level 6 - Run validation tests on deployed connectors."""
    print("\n========================================")
    print("LEVEL 6 - VALIDATION TESTS")
    print("========================================\n")
    
    if not NEWMAN_EXECUTOR.is_available():
        raise RuntimeError("Newman not installed. Install with: npm install or npm install -g newman")

    connectors = _ensure_level6_connectors_ready()
    
    if not connectors:
        raise RuntimeError("No connectors running after Vault recovery")

    _ensure_level6_connector_hosts(connectors)
    
    if len(connectors) < 2:
        raise RuntimeError("At least 2 connectors required")
    
    print(f"Detected connectors: {connectors}\n")
    experiment_dir = ExperimentStorage.create_experiment_directory()
    ExperimentStorage.save_experiment_metadata(experiment_dir, connectors)
    ExperimentStorage.newman_reports_dir(experiment_dir)

    validation_reports = []
    newman_request_metrics = []
    kafka_metrics = None
    kafka_edc_results = []
    storage_checks = []
    ui_results = []
    component_results = []
    _save_level6_experiment_state(
        experiment_dir,
        connectors,
        status="running",
        validation_reports=validation_reports,
        newman_request_metrics=newman_request_metrics,
        kafka_metrics=kafka_metrics,
        kafka_edc_results=kafka_edc_results,
        storage_checks=storage_checks,
        ui_results=ui_results,
        component_results=component_results,
    )

    try:
        if not validate_connectors_deployment(connectors):
            raise RuntimeError("Connector deployment validation failed")

        # Ensure MinIO S3 policies are attached for all connectors (idempotent, survives MinIO restarts)
        ensure_all_minio_policies(connectors)

        if not _wait_for_level6_keycloak_readiness():
            raise RuntimeError("Keycloak authentication readiness check failed")

        VALIDATION_ENGINE.last_storage_checks = []
        validation_reports = VALIDATION_ENGINE.run_all_dataspace_tests(
            connectors,
            experiment_dir=experiment_dir,
        ) or []
        storage_checks = list(getattr(VALIDATION_ENGINE, "last_storage_checks", []) or [])
        _save_level6_experiment_state(
            experiment_dir,
            connectors,
            status="running",
            validation_reports=validation_reports,
            newman_request_metrics=newman_request_metrics,
            kafka_metrics=kafka_metrics,
            kafka_edc_results=kafka_edc_results,
            storage_checks=storage_checks,
            ui_results=ui_results,
            component_results=component_results,
        )

        newman_request_metrics = METRICS_COLLECTOR.collect_experiment_newman_metrics(experiment_dir) or []
        _save_level6_experiment_state(
            experiment_dir,
            connectors,
            status="running",
            validation_reports=validation_reports,
            newman_request_metrics=newman_request_metrics,
            kafka_metrics=kafka_metrics,
            kafka_edc_results=kafka_edc_results,
            storage_checks=storage_checks,
            ui_results=ui_results,
            component_results=component_results,
        )

        if _should_run_level6_kafka_edc_validation():
            print("\nRunning optional EDC+Kafka transfer validation suite...")
            kafka_edc_results = _run_level6_kafka_edc_validation(connectors, experiment_dir) or []
            for result in kafka_edc_results:
                provider = result.get("provider", "unknown-provider")
                consumer = result.get("consumer", "unknown-consumer")
                status = result.get("status", "unknown")
                if status == "passed":
                    print(f"  EDC+Kafka validation passed for {provider} -> {consumer}")
                elif status == "failed":
                    error = (result.get("error") or {}).get("message", "unknown reason")
                    print(f"  Warning: EDC+Kafka validation failed for {provider} -> {consumer} ({error})")
                else:
                    reason = result.get("reason", "unknown reason")
                    print(f"  EDC+Kafka validation skipped for {provider} -> {consumer} ({reason})")

            _save_level6_experiment_state(
                experiment_dir,
                connectors,
                status="running",
                validation_reports=validation_reports,
                newman_request_metrics=newman_request_metrics,
                kafka_metrics=kafka_metrics,
                kafka_edc_results=kafka_edc_results,
                storage_checks=storage_checks,
                ui_results=ui_results,
                component_results=component_results,
            )

        kafka_metrics = _run_level6_kafka_benchmark(experiment_dir)
        _save_level6_experiment_state(
            experiment_dir,
            connectors,
            status="running",
            validation_reports=validation_reports,
            newman_request_metrics=newman_request_metrics,
            kafka_metrics=kafka_metrics,
            kafka_edc_results=kafka_edc_results,
            storage_checks=storage_checks,
            ui_results=ui_results,
            component_results=component_results,
        )

        # Run the stable Playwright smoke suite for each connector
        ui_test_dir = os.path.join(Config.script_dir(), "validation", "ui")
        if os.path.isdir(ui_test_dir):
            for connector in connectors:
                creds = load_connector_credentials(connector)
                if not creds:
                    print(f"  No credentials for {connector}, skipping UI smoke tests")
                    ui_results.append({
                        "connector": connector,
                        "test": "ui-core-smoke",
                        "status": "skipped",
                        "reason": "missing_credentials",
                    })
                    continue
                portal_url = build_connector_url(connector)
                portal_user = creds.get("connector_user", {}).get("user", "")
                portal_pass = creds.get("connector_user", {}).get("passwd", "")
                print(f"\nRunning UI core smoke suite for {connector}...")
                ui_result = _run_level6_ui_smoke(
                    ui_test_dir,
                    connector,
                    portal_url,
                    portal_user,
                    portal_pass,
                    experiment_dir,
                )
                ui_results.append(ui_result)
                if ui_result["status"] == "failed":
                    print(
                        f"  Warning: UI core smoke suite failed for {connector} "
                        f"(exit {ui_result['exit_code']})"
                    )
                elif ui_result["status"] == "skipped":
                    skip_reason = (ui_result.get("error") or {}).get("message", "unknown reason")
                    print(f"  Warning: UI core smoke suite skipped for {connector} ({skip_reason})")
                else:
                    print(f"  UI core smoke suite passed for {connector}")

            if _config_or_env_flag_enabled("LEVEL6_RUN_UI_DATASPACE", default=True):
                if len(connectors) < 2:
                    print("Warning: not enough connectors for UI dataspace suite — skipping")
                    ui_results.append({
                        "test": "ui-core-dataspace",
                        "status": "skipped",
                        "reason": "not_enough_connectors",
                    })
                else:
                    provider_connector = os.environ.get("UI_PROVIDER_CONNECTOR") or connectors[0]
                    consumer_connector = os.environ.get("UI_CONSUMER_CONNECTOR") or next(
                        (connector for connector in connectors if connector != provider_connector),
                        connectors[1],
                    )
                    print(
                        f"\nRunning UI dataspace suite for "
                        f"{provider_connector} -> {consumer_connector}..."
                    )
                    ui_result = _run_level6_ui_dataspace(
                        ui_test_dir,
                        provider_connector,
                        consumer_connector,
                        experiment_dir,
                    )
                    ui_results.append(ui_result)
                    if ui_result["status"] == "failed":
                        print(
                            f"  Warning: UI dataspace suite failed for "
                            f"{provider_connector} -> {consumer_connector} "
                            f"(exit {ui_result['exit_code']})"
                        )
                    elif ui_result["status"] == "skipped":
                        skip_reason = (ui_result.get("error") or {}).get("message", "unknown reason")
                        print(
                            f"  Warning: UI dataspace suite skipped for "
                            f"{provider_connector} -> {consumer_connector} ({skip_reason})"
                        )
                    else:
                        print(
                            f"  UI dataspace suite passed for "
                            f"{provider_connector} -> {consumer_connector}"
                        )

            if _config_or_env_flag_enabled("LEVEL6_RUN_UI_OPS", default=False):
                if len(connectors) < 2:
                    print("Warning: not enough connectors for optional UI ops suite — skipping")
                    ui_results.append({
                        "test": "ui-ops-minio-console",
                        "status": "skipped",
                        "reason": "not_enough_connectors",
                    })
                else:
                    provider_connector = os.environ.get("UI_PROVIDER_CONNECTOR") or connectors[0]
                    consumer_connector = os.environ.get("UI_CONSUMER_CONNECTOR") or next(
                        (connector for connector in connectors if connector != provider_connector),
                        connectors[1],
                    )
                    print(
                        f"\nRunning optional UI ops MinIO suite for "
                        f"{provider_connector} -> {consumer_connector}..."
                    )
                    ui_ops_result = _run_level6_ui_ops(
                        ui_test_dir,
                        provider_connector,
                        consumer_connector,
                        experiment_dir,
                    )
                    ui_results.append(ui_ops_result)
                    if ui_ops_result["status"] == "failed":
                        print(
                            "  Warning: optional UI ops MinIO suite failed "
                            f"(exit {ui_ops_result['exit_code']})"
                        )
                    elif ui_ops_result["status"] == "skipped":
                        skip_reason = (ui_ops_result.get("error") or {}).get("message", "unknown reason")
                        print(f"  Warning: optional UI ops MinIO suite skipped ({skip_reason})")
                    else:
                        print("  Optional UI ops MinIO suite passed")
        else:
            print("Warning: validation/ui directory not found — skipping UI smoke tests")

        if _should_run_level6_component_validation():
            print("\nRunning component validation suite...")
            try:
                component_results = _run_level6_component_validations(experiment_dir) or []
            except Exception as exc:
                component_results = [
                    {
                        "component": "_component-validation",
                        "status": "failed",
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                        "timestamp": datetime.now().isoformat(),
                    }
                ]

            for result in component_results:
                component = result.get("component", "unknown-component")
                status = result.get("status", "unknown")
                if status == "passed":
                    print(f"  Component validation passed for {component}")
                elif status == "failed":
                    print(f"  Warning: component validation failed for {component}")
                else:
                    reason = result.get("reason") or (result.get("error") or {}).get("message", "unknown reason")
                    print(f"  Component validation skipped for {component} ({reason})")

        _save_level6_experiment_state(
            experiment_dir,
            connectors,
            status="completed",
            validation_reports=validation_reports,
            newman_request_metrics=newman_request_metrics,
            kafka_metrics=kafka_metrics,
            kafka_edc_results=kafka_edc_results,
            storage_checks=storage_checks,
            ui_results=ui_results,
            component_results=component_results,
        )
    except Exception as exc:
        if not newman_request_metrics:
            try:
                newman_request_metrics = METRICS_COLLECTOR.collect_experiment_newman_metrics(experiment_dir) or []
            except Exception as metrics_exc:
                print(f"[WARNING] Newman metrics collection failed during Level 6 error handling: {metrics_exc}")
        if kafka_metrics is None:
            try:
                kafka_metrics = _run_level6_kafka_benchmark(experiment_dir)
            except Exception as kafka_exc:
                print(f"[WARNING] Kafka benchmark failed during Level 6 error handling: {kafka_exc}")
        _save_level6_experiment_state(
            experiment_dir,
            connectors,
            status="failed",
            validation_reports=validation_reports,
            newman_request_metrics=newman_request_metrics,
            kafka_metrics=kafka_metrics,
            kafka_edc_results=kafka_edc_results,
            storage_checks=storage_checks,
            ui_results=ui_results,
            component_results=component_results,
            error={
                "type": type(exc).__name__,
                "message": str(exc),
            },
        )
        raise

    print("\n========================================")
    print("VALIDATION COMPLETED")
    print("========================================\n")


# =========================================================
# LEVEL 5 - DEPLOY COMPONENTS
# =========================================================

def lvl_5():
    """Level 5 - Deploy optional component services via Helm charts.

    Uses Helm charts discovered in the platform repo (inesdata-deployment) under:
    - components/<component>/

    The default selection can be provided via deployer.config:
    - COMPONENTS=ontology-hub,ai-model-hub,semantic-virtualization
    """
    from adapters.inesdata.components import INESDataComponentsAdapter

    print("\n========================================")
    print("LEVEL 5 - DEPLOY COMPONENTS")
    print("========================================\n")

    # Keep platform repo deployer.config in sync with the local one.
    try:
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            copy_local_deployer_config()
    except Exception:
        pass

    components_adapter = INESDataComponentsAdapter(
        run=run,
        run_silent=run_silent,
        auto_mode_getter=lambda: AUTO_MODE,
        infrastructure_adapter=INESDATA_ADAPTER.infrastructure,
        config_adapter=INESDATA_ADAPTER.config_adapter,
        config_cls=InesdataConfig,
    )

    available = []
    try:
        available = components_adapter.list_deployable_components()
    except Exception:
        available = []

    deployer_config = load_deployer_config() or {}
    raw = (deployer_config.get("COMPONENTS") or "").strip()
    components = [token.strip() for token in (raw or "").split(",") if token.strip()]
    if not components:
        print("COMPONENTS not set; skipping component deployment\n")
        return []

    if not available:
        raise RuntimeError(
            "COMPONENTS is set but no component charts were discovered in inesdata-deployment. "
            "Update the platform repo (git pull) or re-run Level 2."
        )

    print("Components to deploy:")
    print("- " + "\n- ".join(components))
    print()

    result = components_adapter.deploy_components(components)
    deployed = result.get("deployed") or []
    urls = result.get("urls") or {}

    if deployed:
        print("\nComponents deployed:")
        for component in deployed:
            url = urls.get(component)
            if url:
                print(f"- {component}: {url}")
            else:
                print(f"- {component}")
        print()

    return deployed


def run_all_levels():
    """Execute all deployment levels (1-6) sequentially without interruption.
    
    This function runs the complete deployment pipeline:
    1. Cluster setup
    2. Common services deployment
    3. Dataspace deployment
    4. Connector deployment
    5. Component services deployment
    6. Validation tests
    
    Returns:
        None
    """
    print("\n" + "="*50)
    print("FULL DEPLOYMENT SEQUENCE (LEVELS 1-6)")
    print("="*50)
    print("\nThis will execute all levels sequentially.")
    print("Total duration: environment-dependent; may take 15+ minutes")
    print("\n" + "="*50 + "\n")

    if not _ensure_local_deployer_config_ready_for_levels(CONFIG_GUARDED_LEVELS):
        return
    
    if AUTO_MODE:
        print("[AUTO_MODE] Starting automatic deployment...\n")
        confirm = "Y"
    else:
        confirm = input("Continue with full deployment? (Y/N, default: Y): ").strip().upper() or "Y"

    if confirm != "Y":
        print("\nFull deployment cancelled\n")
        return
    
    levels = [
        ("1", lvl_1, "Cluster Setup"),
        ("2", lvl_2, "Common Services"),
        ("3", lvl_3, "Dataspace"),
        ("4", lvl_4, "Connectors"),
        ("5", lvl_5, "Components"),
        ("6", lvl_6, "Validation Tests"),
    ]
    
    start_time = time.time()
    completed = []
    failed = []
    
    for level_num, level_func, level_name in levels:
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
                print("[AUTO_MODE] Stopping automatic deployment after failure to avoid cascading errors.\n")
                break

            retry = input("Continue with next level? (Y/N, default: Y): ").strip().upper() or "Y"
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
    "5": lvl_5,
    "6": lvl_6,
}

LOCAL_WORKFLOW_SCRIPT_REL_PATH = os.path.join(
    "adapters", "inesdata", "scripts", "local_build_load_deploy.sh"
)
FRAMEWORK_BOOTSTRAP_SCRIPT_REL_PATH = os.path.join("scripts", "bootstrap_framework.sh")
CLEAN_WORKSPACE_SCRIPT_REL_PATH = os.path.join("scripts", "clean_workspace.sh")
LOCAL_IMAGE_OVERRIDE_AFTER_LEVEL4_KEY = "LOCAL_IMAGE_OVERRIDE_AFTER_LEVEL4"
LOCAL_IMAGE_OVERRIDE_COMPONENT_KEY = "LOCAL_IMAGE_OVERRIDE_COMPONENT"
LOCAL_IMAGE_OVERRIDE_SKIP_PREBUILD_KEY = "LOCAL_IMAGE_OVERRIDE_SKIP_PREBUILD"
LOCAL_IMAGE_OVERRIDE_DEFAULT_ENABLED = True
LOCAL_IMAGE_OVERRIDE_DEFAULT_COMPONENT = "connector-interface"
LOCAL_IMAGE_OVERRIDE_DEFAULT_SKIP_PREBUILD = False
LOCAL_IMAGE_OVERRIDE_ALLOWED_COMPONENTS = {
    "connector",
    "connector-interface",
    "registration-service",
    "public-portal-backend",
    "public-portal-frontend",
}
FRAMEWORK_DOCTOR_SYSTEM_COMMANDS = (
    ("python3", ["python3", "--version"], "Instala Python 3 y el paquete venv del sistema."),
    ("git", ["git", "--version"], "Instala Git en la máquina anfitriona."),
    ("docker", ["docker", "--version"], "Instala Docker y verifica que el daemon esté accesible."),
    ("minikube", ["minikube", "version"], "Instala Minikube para usar los niveles 1-6."),
    ("helm", ["helm", "version", "--short"], "Instala Helm para desplegar charts de INESData."),
    ("kubectl", ["kubectl", "version", "--client=true"], "Instala kubectl para operar el clúster."),
    ("psql", ["psql", "--version"], "Instala el cliente de PostgreSQL."),
    ("node", ["node", "--version"], "Instala Node.js para Newman y Playwright."),
    ("npm", ["npm", "--version"], "Instala npm junto con Node.js."),
)
CONFIG_GUARDED_LEVELS = {"2", "3", "4", "5", "6"}
OPTIONAL_DEPLOYER_CONFIG_KEYS = {
    "COMPONENTS",
    "KAFKA_BOOTSTRAP_SERVERS",
    "KAFKA_TOPIC_NAME",
    "KAFKA_TOPIC_STRATEGY",
    "KAFKA_SECURITY_PROTOCOL",
    "KAFKA_SASL_MECHANISM",
    "KAFKA_USERNAME",
    "KAFKA_PASSWORD",
    "KAFKA_CONTAINER_NAME",
    "KAFKA_CONTAINER_IMAGE",
    "KAFKA_CONTAINER_ENV_FILE",
    "KAFKA_MESSAGE_COUNT",
    "KAFKA_MESSAGE_SIZE_BYTES",
    "KAFKA_POLL_TIMEOUT_SECONDS",
    "KAFKA_CONSUMER_GROUP_PREFIX",
    "KAFKA_REQUEST_TIMEOUT_MS",
    "KAFKA_API_TIMEOUT_MS",
    "KAFKA_MAX_BLOCK_MS",
    "KAFKA_CONSUMER_REQUEST_TIMEOUT_MS",
    "KAFKA_TOPIC_READY_TIMEOUT_SECONDS",
    "KAFKA_DATAPLANE_SINK_PARTITION_SIZE",
}


def _parse_bool_config(value, default):
    """Parse deployer.config booleans and fallback to the provided default."""
    if value is None:
        return default

    normalized = str(value).strip().lower()
    if not normalized:
        return default

    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise RuntimeError(
        f"Invalid boolean value '{value}'. Use one of: 1,true,yes,on,0,false,no,off"
    )


def _resolve_local_image_override_config():
    """Read optional post-Level-4 local image override settings from deployer.config."""
    deployer_config = load_deployer_config() or {}
    enabled_raw = deployer_config.get(LOCAL_IMAGE_OVERRIDE_AFTER_LEVEL4_KEY)
    component_raw = deployer_config.get(LOCAL_IMAGE_OVERRIDE_COMPONENT_KEY)
    skip_prebuild_raw = deployer_config.get(LOCAL_IMAGE_OVERRIDE_SKIP_PREBUILD_KEY)

    enabled = _parse_bool_config(enabled_raw, LOCAL_IMAGE_OVERRIDE_DEFAULT_ENABLED)
    skip_prebuild = _parse_bool_config(skip_prebuild_raw, LOCAL_IMAGE_OVERRIDE_DEFAULT_SKIP_PREBUILD)

    component = (
        component_raw
        if component_raw is not None
        else LOCAL_IMAGE_OVERRIDE_DEFAULT_COMPONENT
    )
    component = component.strip() if isinstance(component, str) else str(component).strip()
    if not component:
        component = LOCAL_IMAGE_OVERRIDE_DEFAULT_COMPONENT

    if component and component not in LOCAL_IMAGE_OVERRIDE_ALLOWED_COMPONENTS:
        allowed = ", ".join(sorted(LOCAL_IMAGE_OVERRIDE_ALLOWED_COMPONENTS))
        raise RuntimeError(
            f"Invalid {LOCAL_IMAGE_OVERRIDE_COMPONENT_KEY}: '{component}'. Allowed values: {allowed}"
        )

    return {
        "enabled": enabled,
        "component": component,
        "skip_prebuild": skip_prebuild,
    }


def _local_deployer_config_path():
    """Return the user-facing deployer.config path next to inesdata.py."""
    return os.path.join(Config.script_dir(), "deployer.config")


def _local_deployer_config_example_path():
    """Return the local deployer.config.example path next to inesdata.py."""
    return os.path.join(Config.script_dir(), "deployer.config.example")


def _required_local_deployer_config_keys():
    """Use deployer.config.example as the baseline contract for guarded levels."""
    example_path = _local_deployer_config_example_path()
    example_values = _read_local_key_value_config(example_path)
    if example_values:
        return sorted(key for key in example_values if key not in OPTIONAL_DEPLOYER_CONFIG_KEYS)

    return [
        "ENVIRONMENT",
        "PG_HOST",
        "PG_USER",
        "PG_PASSWORD",
        "KC_URL",
        "KC_USER",
        "KC_PASSWORD",
        "KC_INTERNAL_URL",
        "VT_URL",
        "VT_TOKEN",
        "DATABASE_HOSTNAME",
        "KEYCLOAK_HOSTNAME",
        "MINIO_HOSTNAME",
        "VAULT_URL",
        "DOMAIN_BASE",
        "DS_DOMAIN_BASE",
        "MINIO_USER",
        "MINIO_PASSWORD",
        "DS_1_NAME",
        "DS_1_NAMESPACE",
        "DS_1_CONNECTORS",
    ]


def _validate_local_deployer_config_for_levels(level_ids):
    """Validate that the local deployer.config exists and has the baseline keys."""
    normalized_levels = {str(level_id) for level_id in (level_ids or [])}
    if not (normalized_levels & CONFIG_GUARDED_LEVELS):
        return True, []

    config_path = _local_deployer_config_path()
    if not os.path.exists(config_path):
        return False, [f"Missing local deployer.config: {config_path}"]

    config_values = _read_local_key_value_config(config_path)
    missing_keys = [key for key in _required_local_deployer_config_keys() if not config_values.get(key)]
    if missing_keys:
        return False, [f"Missing required keys in deployer.config: {', '.join(missing_keys)}"]

    return True, []


def _ensure_local_deployer_config_ready_for_levels(level_ids):
    """Print a friendly message and block guarded levels when config is missing or incomplete."""
    ready, issues = _validate_local_deployer_config_for_levels(level_ids)
    if ready:
        return True

    levels_text = ", ".join(sorted({str(level_id) for level_id in (level_ids or [])}))
    print("\nCannot continue because deployer.config is missing or incomplete.")
    if levels_text:
        print(f"Guarded levels requested: {levels_text}")
    for issue in issues:
        print(f"- {issue}")
    print("\nSuggested next steps:")
    print(f"- Run: bash {FRAMEWORK_BOOTSTRAP_SCRIPT_REL_PATH}")
    print("- Or use option B in the menu to bootstrap the framework")
    print("- Review deployer.config before retrying the guarded levels\n")
    return False


def _maybe_apply_local_image_override_after_level_4():
    """Optionally run local build/load/deploy after Level 4 to avoid pinned image rollback."""
    override_config = _resolve_local_image_override_config()
    if not override_config["enabled"]:
        return

    platform_dirs = _detect_platform_dirs_from_adapter_configs()
    if not platform_dirs:
        raise RuntimeError(
            "Local image override is enabled but no platform directory was detected from adapter REPO_DIR"
        )

    extra_args = ["--platform-dir", platform_dirs[0]]

    if override_config["component"]:
        extra_args.extend(["--component", override_config["component"]])

    if override_config["skip_prebuild"]:
        extra_args.append("--skip-prebuild")

    print("\nApplying local image override after Level 4...")
    print(f"  Component: {override_config['component'] or 'all'}")
    print(f"  Skip pre-build: {'yes' if override_config['skip_prebuild'] else 'no'}")

    if not _execute_local_images_workflow(extra_args):
        raise RuntimeError("Post-Level-4 local image override failed")



def _extract_repo_dir_from_adapter_config(config_path):
    """Read REPO_DIR constant from adapter config.py without importing the module."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    match = re.search(
        r'^\s*REPO_DIR\s*=\s*["\']([^"\']+)["\']',
        content,
        re.MULTILINE,
    )
    if not match:
        return None

    repo_dir = match.group(1).strip()
    return repo_dir or None


def _detect_platform_dirs_from_adapter_configs():
    """Detect platform directories from adapter REPO_DIR values and validate they exist."""
    adapters_dir = os.path.join(Config.script_dir(), "adapters")
    platform_dirs = []
    seen = set()

    if os.path.isdir(adapters_dir):
        for adapter_name in sorted(os.listdir(adapters_dir)):
            config_path = os.path.join(adapters_dir, adapter_name, "config.py")
            if not os.path.isfile(config_path):
                continue

            repo_dir = _extract_repo_dir_from_adapter_config(config_path)
            if not repo_dir or repo_dir in seen:
                continue

            repo_abs_path = os.path.join(Config.script_dir(), repo_dir)
            if os.path.isdir(repo_abs_path):
                platform_dirs.append(repo_dir)
                seen.add(repo_dir)

    default_repo_dir = getattr(InesdataConfig, "REPO_DIR", None)
    if default_repo_dir and os.path.isdir(os.path.join(Config.script_dir(), default_repo_dir)):
        if default_repo_dir in platform_dirs:
            platform_dirs.remove(default_repo_dir)
        platform_dirs.insert(0, default_repo_dir)

    return platform_dirs


def _confirm_local_workflow():
    """Ask for confirmation before execution."""
    while True:
        try:
            confirm = input("\nConfirm execution? (Y/N, default: Y): ").strip().upper() or "Y"
        except EOFError:
            return False

        if confirm in ("Y", "N"):
            return confirm == "Y"

        print("Please answer Y or N.")


def _execute_local_images_workflow(extra_args):
    """Execute local build/load/deploy script with --apply and provided args."""
    script_path = os.path.join(Config.script_dir(), LOCAL_WORKFLOW_SCRIPT_REL_PATH)
    if not os.path.isfile(script_path):
        print(f"\nLocal workflow script not found: {script_path}\n")
        return False

    command = ["bash", script_path, "--apply", *extra_args]

    print(f"\nLaunching local workflow: {' '.join(command)}\n")
    result = subprocess.run(command, cwd=Config.script_dir())

    if result.returncode == 0:
        print("\nWorkflow completed successfully.\n")
        return True

    print("\nWorkflow failed. Check logs above.\n")
    return False


def _run_command_capture(args, cwd=None):
    """Run a command and capture a compact one-line summary."""
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    return result.returncode, output


def _doctor_item(category, name, status, details, remediation=None):
    return {
        "category": category,
        "name": name,
        "status": status,
        "details": details,
        "remediation": remediation,
    }


def _read_local_key_value_config(path):
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                normalized = line.strip()
                if normalized and "=" in normalized and not normalized.startswith("#"):
                    key, value = normalized.split("=", 1)
                    values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


def _collect_framework_doctor_report():
    """Inspect local readiness to execute the framework from a fresh machine."""
    root_dir = Config.script_dir()
    ui_dir = os.path.join(root_dir, "validation", "ui")
    root_venv_python = os.path.join(root_dir, ".venv", "bin", "python")
    local_newman = os.path.join(root_dir, "node_modules", ".bin", "newman")
    local_playwright = os.path.join(ui_dir, "node_modules", ".bin", "playwright")
    deployer_config_path = os.path.join(root_dir, "deployer.config")
    deployer_example_path = os.path.join(root_dir, "deployer.config.example")
    platform_repo_dir = os.path.join(root_dir, Config.REPO_DIR)

    checks = []

    for command_name, version_args, remediation in FRAMEWORK_DOCTOR_SYSTEM_COMMANDS:
        resolved = shutil.which(command_name)
        if not resolved:
            checks.append(
                _doctor_item(
                    "system",
                    command_name,
                    "missing",
                    "Command not found in PATH",
                    remediation,
                )
            )
            continue

        return_code, version_text = _run_command_capture(version_args)
        details = version_text.splitlines()[0].strip() if version_text else resolved
        status = "ok" if return_code == 0 else "warning"
        if return_code != 0:
            details = details or f"{command_name} returned exit code {return_code}"
        checks.append(_doctor_item("system", command_name, status, details, remediation))

    if os.path.exists(root_venv_python):
        return_code, version_text = _run_command_capture([root_venv_python, "--version"])
        checks.append(
            _doctor_item(
                "framework",
                "root .venv",
                "ok" if return_code == 0 else "warning",
                version_text.splitlines()[0].strip() if version_text else root_venv_python,
                f"Run: bash {FRAMEWORK_BOOTSTRAP_SCRIPT_REL_PATH}",
            )
        )
    else:
        checks.append(
            _doctor_item(
                "framework",
                "root .venv",
                "missing",
                f"Missing virtual environment interpreter: {root_venv_python}",
                f"Run: bash {FRAMEWORK_BOOTSTRAP_SCRIPT_REL_PATH}",
            )
        )

    current_python = os.path.realpath(sys.executable)
    expected_root = os.path.realpath(os.path.join(root_dir, ".venv"))
    active_status = "ok" if current_python.startswith(expected_root) else "warning"
    active_details = current_python
    active_remediation = None
    if active_status != "ok":
        active_remediation = "Activate the root virtual environment with: source .venv/bin/activate"
    checks.append(_doctor_item("framework", "active python", active_status, active_details, active_remediation))

    if os.path.exists(local_newman):
        return_code, version_text = _run_command_capture([local_newman, "--version"], cwd=root_dir)
        checks.append(
            _doctor_item(
                "framework",
                "newman",
                "ok" if return_code == 0 else "warning",
                version_text or local_newman,
                "Run: npm install",
            )
        )
    else:
        global_newman = shutil.which("newman")
        if global_newman:
            return_code, version_text = _run_command_capture([global_newman, "--version"], cwd=root_dir)
            checks.append(
                _doctor_item(
                    "framework",
                    "newman",
                    "ok" if return_code == 0 else "warning",
                    version_text.splitlines()[0].strip() if version_text else global_newman,
                    "Prefer a local install with: npm install",
                )
            )
        else:
            checks.append(
                _doctor_item(
                    "framework",
                    "newman",
                    "missing",
                    "Neither local nor global Newman is available",
                    "Run: npm install",
                )
            )

    if os.path.exists(local_playwright):
        return_code, version_text = _run_command_capture([local_playwright, "--version"], cwd=ui_dir)
        checks.append(
            _doctor_item(
                "ui",
                "playwright cli",
                "ok" if return_code == 0 else "warning",
                version_text.splitlines()[0].strip() if version_text else local_playwright,
                f"Run: bash {FRAMEWORK_BOOTSTRAP_SCRIPT_REL_PATH}",
            )
        )

        list_return_code, browser_text = _run_command_capture(
            [local_playwright, "install", "--list"],
            cwd=ui_dir,
        )
        browser_status = "ok"
        browser_details = "Playwright browsers detected"
        if list_return_code != 0:
            browser_status = "warning"
            browser_details = "Unable to query installed Playwright browsers"
        elif "Browsers:" not in browser_text:
            browser_status = "warning"
            browser_details = "Playwright browsers do not appear to be installed"
        else:
            browser_lines = [line.strip() for line in browser_text.splitlines() if line.strip().startswith("/")]
            if browser_lines:
                browser_details = browser_lines[0]
        checks.append(
            _doctor_item(
                "ui",
                "playwright browsers",
                browser_status,
                browser_details,
                "Run: cd validation/ui && npx playwright install",
            )
        )
    else:
        checks.append(
            _doctor_item(
                "ui",
                "playwright cli",
                "missing",
                f"Missing Playwright binary: {local_playwright}",
                f"Run: bash {FRAMEWORK_BOOTSTRAP_SCRIPT_REL_PATH}",
            )
        )

    if os.path.exists(deployer_config_path):
        config_values = _read_local_key_value_config(deployer_config_path)
        required_keys = [key for key in ("DOMAIN_BASE", "DS_DOMAIN_BASE") if not config_values.get(key)]
        status = "ok" if not required_keys else "warning"
        details = deployer_config_path
        remediation = None
        if required_keys:
            details = f"Missing required keys in deployer.config: {', '.join(required_keys)}"
            remediation = "Edit deployer.config before running the deployment levels."
        checks.append(_doctor_item("config", "deployer.config", status, details, remediation))

        kafka_bootstrap = config_values.get("KAFKA_BOOTSTRAP_SERVERS")
        if kafka_bootstrap:
            checks.append(
                _doctor_item(
                    "kafka",
                    "bootstrap servers",
                    "ok",
                    kafka_bootstrap,
                    None,
                )
            )

        kafka_env_file = config_values.get("KAFKA_CONTAINER_ENV_FILE")
        if kafka_env_file:
            resolved_env_file = kafka_env_file
            if not os.path.isabs(resolved_env_file):
                resolved_env_file = os.path.abspath(os.path.join(root_dir, resolved_env_file))
            exists = os.path.exists(resolved_env_file)
            checks.append(
                _doctor_item(
                    "kafka",
                    "container env file",
                    "ok" if exists else "warning",
                    resolved_env_file if exists else f"Missing Kafka env file: {resolved_env_file}",
                    None if exists else "Create the Kafka env file or remove KAFKA_CONTAINER_ENV_FILE from deployer.config.",
                )
            )
    else:
        remediation = None
        if os.path.exists(deployer_example_path):
            remediation = "Run the bootstrap script or copy deployer.config.example to deployer.config."
        checks.append(
            _doctor_item(
                "config",
                "deployer.config",
                "missing",
                "Local deployer.config is missing",
                remediation,
            )
        )

    if os.path.isdir(platform_repo_dir):
        checks.append(
            _doctor_item(
                "config",
                "inesdata-deployment repo",
                "ok",
                platform_repo_dir,
                None,
            )
        )
    else:
        checks.append(
            _doctor_item(
                "config",
                "inesdata-deployment repo",
                "warning",
                "The platform repository is not present yet; Level 2 can clone it automatically.",
                "Run Level 2 or clone the platform repository manually if needed.",
            )
        )

    hosts_path = get_hosts_path()
    if hosts_path and os.path.exists(hosts_path):
        writable = os.access(hosts_path, os.W_OK)
        status = "ok" if writable else "warning"
        details = f"{hosts_path} ({'writable' if writable else 'requires elevated privileges'})"
        remediation = None if writable else "Run with sufficient privileges when the framework needs to update hosts."
        checks.append(_doctor_item("config", "hosts file", status, details, remediation))
    else:
        checks.append(
            _doctor_item(
                "config",
                "hosts file",
                "warning",
                "Hosts file path is not available for automatic update on this OS.",
                "Update the required host entries manually.",
            )
        )

    if shutil.which("pgrep"):
        tunnel_result = subprocess.run(
            ["pgrep", "-af", "minikube tunnel"],
            text=True,
            capture_output=True,
            check=False,
        )
        if tunnel_result.returncode == 0 and (tunnel_result.stdout or "").strip():
            tunnel_status = "ok"
            tunnel_details = "minikube tunnel process detected"
            tunnel_remediation = None
        else:
            tunnel_status = "warning"
            tunnel_details = "minikube tunnel not detected"
            tunnel_remediation = "Before Level 3, run: minikube tunnel"
    else:
        tunnel_status = "warning"
        tunnel_details = "pgrep is not available, so the tunnel process cannot be inspected automatically"
        tunnel_remediation = "Before Level 3, verify manually that minikube tunnel is running."
    checks.append(_doctor_item("runtime", "minikube tunnel", tunnel_status, tunnel_details, tunnel_remediation))

    if any(item["status"] == "missing" for item in checks):
        overall_status = "not_ready"
    elif any(item["status"] == "warning" for item in checks):
        overall_status = "ready_with_warnings"
    else:
        overall_status = "ready"

    return {
        "status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }


def run_framework_doctor():
    """Print a local readiness report for the framework and Level 6 validation."""
    report = _collect_framework_doctor_report()

    print("\n" + "=" * 50)
    print("FRAMEWORK DOCTOR")
    print("=" * 50)
    print(f"\nOverall status: {report['status']}\n")

    rows = [
        [
            item["category"],
            item["name"],
            item["status"],
            item["details"],
        ]
        for item in report["checks"]
    ]
    print(tabulate(rows, headers=["Category", "Check", "Status", "Details"], tablefmt="github"))

    remediations = [
        f"- {item['name']}: {item['remediation']}"
        for item in report["checks"]
        if item.get("remediation") and item.get("status") != "ok"
    ]
    if remediations:
        print("\nRecommended actions:")
        print("\n".join(remediations))

    print()
    return report


def run_framework_bootstrap_interactive():
    """Run local bootstrap to prepare Python, Newman, Playwright and deployer.config."""
    script_path = os.path.join(Config.script_dir(), FRAMEWORK_BOOTSTRAP_SCRIPT_REL_PATH)
    if not os.path.isfile(script_path):
        print(f"\nBootstrap script not found: {script_path}\n")
        return None

    try:
        confirm = input("\nRun framework bootstrap now? (Y/N, default: Y): ").strip().upper() or "Y"
    except EOFError:
        confirm = "N"

    if confirm != "Y":
        print("\nBootstrap cancelled.\n")
        return None

    command = ["bash", script_path]
    print(f"\nLaunching framework bootstrap: {' '.join(command)}\n")
    result = subprocess.run(command, cwd=Config.script_dir())

    if result.returncode == 0:
        print("\nFramework bootstrap completed successfully.\n")
    else:
        print("\nFramework bootstrap failed. Check logs above.\n")

    return result.returncode


def run_local_images_workflow_interactive():
    """Build and deploy local images (with developer sub-options)."""
    platform_dirs = _detect_platform_dirs_from_adapter_configs()

    if not platform_dirs:
        print("\nNo platform dir detected from adapter REPO_DIR values.\n")
        return None

    platform_dir = platform_dirs[0]

    while True:
        print("\n" + "="*50)
        print("BUILD & DEPLOY LOCAL IMAGES")
        print("="*50)
        print("1 - Build and deploy ALL local images")
        print("2 - Build and deploy ONLY connectors")
        print("3 - Build and deploy ONLY inesdata-connector-interface")
        print("B - Back")

        try:
            sub_choice = input("\nSelection: ").strip().upper()
        except EOFError:
            print("\nNo input. Returning to main menu.\n")
            return None

        if sub_choice == "B":
            return None
        elif sub_choice not in {"1", "2", "3"}:
            print("\nInvalid selection. Please try again.\n")
            continue

        if not _confirm_local_workflow():
            print("\nExecution cancelled.\n")
            return None

        extra_args = ["--platform-dir", platform_dir]
        if sub_choice == "2":
            extra_args += ["--component", "connector"]
        elif sub_choice == "3":
            extra_args += ["--component", "connector-interface"]

        _execute_local_images_workflow(extra_args)
        return None


def run_workspace_cleanup_interactive():
    """Run workspace cleanup script in apply mode."""
    script_path = os.path.join(Config.script_dir(), CLEAN_WORKSPACE_SCRIPT_REL_PATH)
    if not os.path.isfile(script_path):
        print(f"\nCleanup script not found: {script_path}\n")
        return None

    while True:
        print("\n" + "="*50)
        print("WORKSPACE CLEANUP")
        print("="*50)
        print("1 - Apply cleanup")
        print("    Removes __pycache__, *.pyc and tool caches")
        print("2 - Apply cleanup + include results")
        print("    Also removes experiments/, newman/ and Playwright results")
        print("B - Back")

        try:
            choice = input("\nSelection: ").strip().upper()
        except EOFError:
            print("\nNo input. Returning to main menu.\n")
            return None

        if choice == "B":
            return None

        if choice not in {"1", "2"}:
            print("\nInvalid selection. Please try again.\n")
            continue

        command = ["bash", script_path, "--apply"]
        mode_label = "cleanup"
        if choice == "2":
            command.append("--include-results")
            mode_label = "cleanup + include results"

        try:
            confirm = input(f"\nRun {mode_label}? (Y/N, default: N): ").strip().upper()
        except EOFError:
            confirm = "N"

        if confirm != "Y":
            print("\nCleanup cancelled.\n")
            return None

        print(f"\nLaunching cleanup: {' '.join(command)}\n")
        result = subprocess.run(command, cwd=Config.script_dir())

        if result.returncode == 0:
            print("\nCleanup completed successfully.\n")
        else:
            print("\nCleanup failed. Check logs above.\n")

        return None


def run_new_cli_interactive():
    """Launch the new framework CLI from the legacy interactive menu."""
    print("\n" + "="*50)
    print("NEW DATASPACE FRAMEWORK CLI")
    print("="*50)
    print("\nAvailable adapters:")

    adapters = framework_cli.print_available_adapters()

    try:
        adapter = input("\nAdapter (default: inesdata): ").strip().lower() or "inesdata"
    except EOFError:
        print("\nNo adapter provided. Returning to legacy menu.\n")
        return None

    if adapter not in adapters:
        print(f"\nUnknown adapter: {adapter}")
        print("Returning to legacy menu.\n")
        return None

    try:
        command = input("Command [deploy/validate/metrics/run] (default: run): ").strip().lower() or "run"
    except EOFError:
        print("\nNo command provided. Returning to legacy menu.\n")
        return None

    if command not in framework_cli.SUPPORTED_COMMANDS:
        print(f"\nUnsupported command: {command}")
        print("Returning to legacy menu.\n")
        return None

    try:
        dry_run_choice = input("Dry run? (Y/N, default: N): ").strip().upper()
    except EOFError:
        dry_run_choice = "N"

    argv = [adapter, command]

    if dry_run_choice == "Y":
        argv.append("--dry-run")

    print(f"\nLaunching new CLI: python main.py {' '.join(argv)}\n")

    try:
        result = framework_cli.main(argv)
    except SystemExit as exc:
        print(f"\nCLI exited with code {exc.code}. Returning to legacy menu.\n")
        return None
    except Exception as exc:
        print(f"\nCLI execution error: {exc}\n")
        return None

    if isinstance(result, (dict, list)):
        print("CLI result:\n")
        print(json.dumps(result, indent=2, default=str))
        print()
    elif result is not None:
        print(f"CLI result: {result}\n")

    return result


def show_menu():
    """Display interactive menu and execute selected operations.
    
    Menu options:
    - 0: Run all levels (1-6) sequentially
    - 1-6: Run individual levels
    - B: Bootstrap local framework dependencies
    - D: Run local readiness doctor
    - N: Launch new framework CLI
    - C: Run workspace cleanup script
    - L: Build and deploy local images
    - Q: Exit application
    """
    while True:
        print("\n" + "="*50)
        print("CLUSTER AUTOMATION TOOL")
        print("="*50)
        print("\n[Full Deployment]")
        print("0 - Run All Levels (1-6) sequentially")
        print("\n[Individual Levels]")
        print("1 - Level 1: Setup Cluster")
        print("2 - Level 2: Deploy Common Services")
        print("3 - Level 3: Deploy Dataspace")
        print("4 - Level 4: Deploy Connectors")
        print("5 - Level 5: Deploy Components")
        print("6 - Level 6: Run Validation Tests")
        print("\n[Setup]")
        print("B - Bootstrap Framework Dependencies")
        print("D - Run Framework Doctor")
        print("\n[Modern CLI]")
        print("N - Use new framework CLI")
        print("\n[Developer]")
        print("C - Cleanup Workspace")
        print("L - Build and Deploy Local Images")
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
        elif choice == "N":
            try:
                run_new_cli_interactive()
            except KeyboardInterrupt:
                print("\n\nCLI execution cancelled by user\n")
        elif choice == "B":
            try:
                run_framework_bootstrap_interactive()
            except KeyboardInterrupt:
                print("\n\nFramework bootstrap cancelled by user\n")
        elif choice == "D":
            try:
                run_framework_doctor()
            except KeyboardInterrupt:
                print("\n\nFramework doctor cancelled by user\n")
        elif choice == "C":
            try:
                run_workspace_cleanup_interactive()
            except KeyboardInterrupt:
                print("\n\nWorkspace cleanup cancelled by user\n")
        elif choice == "L":
            try:
                run_local_images_workflow_interactive()
            except KeyboardInterrupt:
                print("\n\nBuild and deploy local images cancelled by user\n")
        elif choice in LEVELS:
            if choice in CONFIG_GUARDED_LEVELS and not _ensure_local_deployer_config_ready_for_levels({choice}):
                continue
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
