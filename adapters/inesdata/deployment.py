import os

import requests
import yaml

from .config import INESDataConfigAdapter, InesdataConfig


class INESDataDeploymentAdapter:
    """Contains INESData deployment logic."""

    def __init__(self, run, run_silent, auto_mode_getter, infrastructure_adapter, config_adapter=None, config_cls=None):
        self.run = run
        self.run_silent = run_silent
        self.auto_mode_getter = auto_mode_getter
        self.infrastructure = infrastructure_adapter
        self.config = config_cls or InesdataConfig
        self.config_adapter = config_adapter or INESDataConfigAdapter(self.config)

    def _auto_mode(self):
        return self.auto_mode_getter() if callable(self.auto_mode_getter) else bool(self.auto_mode_getter)

    def install_dependencies(self):
        import subprocess
        import sys

        libraries = ["tabulate", "ruamel.yaml"]
        print("Installing dependencies...")

        for lib in libraries:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", lib])
                print(f"{lib} installed successfully.")
            except subprocess.CalledProcessError as e:
                print(f"Error installing {lib}: {e}")

    def update_helm_values_with_host_aliases(self, values_file, minikube_ip=None):
        if minikube_ip is None:
            minikube_ip = self.run("minikube ip", capture=True) or self.config.MINIKUBE_IP

        with open(values_file) as f:
            values = yaml.safe_load(f)

        values["hostAliases"] = [{
            "ip": minikube_ip,
            "hostnames": self.config.host_alias_domains()
        }]

        with open(values_file, "w") as f:
            yaml.dump(values, f, sort_keys=False)

    def deploy_dataspace(self):
        print("\n========================================")
        print("LEVEL 3 - DATASPACE")
        print("========================================\n")

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

        if not self._auto_mode():
            input()
        else:
            print("[AUTO_MODE] Skipping tunnel confirmation\n")

        repo_dir = self.config.repo_dir()
        ds_name = self.config.DS_NAME
        python_exec = self.config.python_exec()

        if not os.path.exists(repo_dir):
            print("Repository not found. Run Level 2 first")
            return

        if not self.infrastructure.ensure_local_infra_access():
            return

        if not self.infrastructure.ensure_vault_unsealed():
            return

        print("Verifying Keycloak access...")
        deployer_config = self.config_adapter.load_deployer_config()
        kc_url = deployer_config.get("KC_URL")

        if not kc_url:
            print("KC_URL not defined in deployer.config")
            return

        try:
            response = requests.get(f"{kc_url}/realms/master", timeout=5)
            if response.status_code not in (200, 302):
                print("Keycloak not ready")
                return
        except Exception:
            print("Keycloak not accessible. Verify minikube tunnel")
            return

        if not os.path.exists(self.config.venv_path()):
            print("Creating Python environment...")
            self.run("python3 -m venv .venv", cwd=repo_dir)

        self.install_dependencies()
        self.run(f"{python_exec} -m pip install -r requirements.txt", cwd=repo_dir)

        print("Cleaning previous databases...")
        connectors = getattr(self, "connectors_adapter", None)
        if connectors is None:
            raise RuntimeError("Deployment adapter requires a connectors adapter")

        connectors.force_clean_postgres_db(self.config.registration_db_name(), self.config.registration_db_user())
        connectors.force_clean_postgres_db(self.config.webportal_db_name(), self.config.webportal_db_user())

        print("Creating dataspace...")
        if self.run(f"{python_exec} deployer.py dataspace create {ds_name}", cwd=repo_dir) is None:
            print("Error creating dataspace")
            return

        values_file = self.config.registration_values_file()
        if not os.path.exists(values_file):
            print("Registration service values file not found")
            return

        minikube_ip = self.run("minikube ip", capture=True)
        if minikube_ip:
            self.update_helm_values_with_host_aliases(values_file, minikube_ip)

        print("\nDeploying registration-service...")
        if not self.infrastructure.deploy_helm_release(
            self.config.helm_release_rs(),
            self.config.namespace_demo(),
            os.path.basename(values_file),
            cwd=self.config.registration_service_dir()
        ):
            print("Error deploying registration-service")
            return

        if not self.infrastructure.wait_for_namespace_pods(self.config.namespace_demo()):
            print("Timeout waiting for pods")
            return

        print("\nLEVEL 3 COMPLETE\n")

    def describe(self) -> str:
        return "INESDataDeploymentAdapter contains deployment logic for INESData."

