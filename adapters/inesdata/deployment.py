import os

import requests
import yaml
import time

from .config import INESDataConfigAdapter, InesdataConfig
from runtime_dependencies import ensure_python_requirements


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

    @staticmethod
    def _fail(message, root_cause=None):
        if root_cause:
            raise RuntimeError(f"{message}. Root cause: {root_cause}")
        raise RuntimeError(message)

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

    @staticmethod
    def _print_unique_lines(output):
        previous = None
        for line in output.splitlines():
            line = line.rstrip()
            if not line or line == previous:
                continue
            print(line)
            previous = line

    def wait_for_keycloak_admin_ready(self, kc_url, kc_user, kc_password, timeout=120, poll_interval=3):
        print("Waiting for Keycloak admin authentication to become ready...")
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

    def restart_registration_service(self):
        deployment_name = f"{self.config.DS_NAME}-registration-service"
        namespace = self.config.namespace_demo()

        print("\nRestarting registration-service deployment to pick up the recreated database credentials...")
        if self.run(
            f"kubectl rollout restart deployment/{deployment_name} -n {namespace}",
            check=False,
        ) is None:
            self._fail("Could not restart registration-service deployment")

        rollout_output = self.run(
            f"kubectl rollout status deployment/{deployment_name} -n {namespace} --timeout=180s",
            capture=True,
            check=False,
        )
        if rollout_output is None:
            self._fail("registration-service deployment did not finish rolling out")
        self._print_unique_lines(rollout_output)

    def deploy_dataspace(self):
        self.infrastructure.announce_level(3, "DATASPACE")

        print("-------------------------------------------------")
        print("MINIKUBE TUNNEL REQUIRED")
        print()
        print("Open a new terminal and run:")
        print()
        print("minikube tunnel")
        print()
        print("The tunnel must remain active during the dataspace deployment.")
        print("When logs start appearing in the tunnel terminal, Linux may require your password")
        print("even if no explicit prompt is shown. Type your password there and press ENTER.")
        print()
        print("Return to this terminal and press ENTER to continue after starting the tunnel.")
        print("-------------------------------------------------\n")

        if not self._auto_mode():
            input()
        else:
            print("[AUTO_MODE] Skipping tunnel confirmation\n")

        repo_dir = self.config.repo_dir()
        ds_name = self.config.DS_NAME
        python_exec = self.config.python_exec()

        if not os.path.exists(repo_dir):
            self._fail("Repository not found. Run Level 2 first")

        if not self.infrastructure.ensure_local_infra_access():
            self._fail("Local access to PostgreSQL/Vault is not available")

        if not self.infrastructure.ensure_vault_unsealed():
            self._fail("Vault is not initialized or unsealed")

        print("Verifying Keycloak access...")
        deployer_config = self.config_adapter.load_deployer_config()
        kc_url = deployer_config.get("KC_URL")
        kc_user = deployer_config.get("KC_USER")
        kc_password = deployer_config.get("KC_PASSWORD")

        if not kc_url:
            self._fail("KC_URL not defined in deployer.config")
        if not kc_user or not kc_password:
            self._fail("KC_USER/KC_PASSWORD not defined in deployer.config")

        try:
            response = requests.get(f"{kc_url}/realms/master", timeout=5)
            if response.status_code not in (200, 302):
                self._fail("Keycloak not ready", root_cause=f"unexpected HTTP status {response.status_code}")
        except Exception:
            self._fail("Keycloak not accessible. Verify minikube tunnel")

        if not self.wait_for_keycloak_admin_ready(kc_url, kc_user, kc_password):
            self._fail("Keycloak admin API not ready", root_cause="admin authentication did not succeed in time")

        if not os.path.exists(self.config.venv_path()):
            print("Creating Python environment...")
            self.run("python3 -m venv .venv", cwd=repo_dir)

        print("Ensuring INESData Python dependencies...")
        ensure_python_requirements(
            python_exec,
            self.config.repo_requirements_path(),
            label="INESData runtime",
        )

        print("Cleaning previous databases...")
        connectors = getattr(self, "connectors_adapter", None)
        if connectors is None:
            raise RuntimeError("Deployment adapter requires a connectors adapter")

        connectors.force_clean_postgres_db(self.config.registration_db_name(), self.config.registration_db_user())
        connectors.force_clean_postgres_db(self.config.webportal_db_name(), self.config.webportal_db_user())

        print("Creating dataspace...")
        if self.run(f"{python_exec} deployer.py dataspace create {ds_name}", cwd=repo_dir) is None:
            self._fail("Error creating dataspace")

        values_file = self.config.registration_values_file()
        if not os.path.exists(values_file):
            self._fail("Registration service values file not found")

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
            self._fail("Error deploying registration-service")

        self.restart_registration_service()

        if not self.infrastructure.wait_for_namespace_pods(self.config.namespace_demo()):
            self._fail("Timeout waiting for dataspace pods")

        dataspace_ready, root_cause = self.infrastructure.verify_dataspace_ready_for_level4()
        if not dataspace_ready:
            self._fail("Level 3 did not leave the dataspace ready for Level 4", root_cause=root_cause)

        self.infrastructure.complete_level(3)

    def describe(self) -> str:
        return "INESDataDeploymentAdapter contains deployment logic for INESData."

