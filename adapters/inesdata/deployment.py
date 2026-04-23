import os
import shlex
import shutil

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

    def _dataspace_name(self):
        getter = getattr(self.config, "dataspace_name", None)
        if callable(getter):
            return getter()
        return (getattr(self.config, "DS_NAME", "demo") or "demo").strip() or "demo"

    def _dataspace_namespace(self):
        namespace_getter = getattr(self.config, "namespace_demo", None)
        if callable(namespace_getter):
            namespace = namespace_getter()
            if namespace:
                return namespace
        return self._dataspace_name()

    def _dataspace_runtime_dir(self):
        runtime_dir_getter = getattr(self.config, "deployment_runtime_dir", None)
        if callable(runtime_dir_getter):
            return runtime_dir_getter()
        return os.path.join(
            self.config.repo_dir(),
            "deployments",
            "DEV",
            self._dataspace_name(),
        )

    def _adapter_name(self):
        adapter_name_getter = getattr(self.config, "adapter_name", None)
        if callable(adapter_name_getter):
            adapter_name = adapter_name_getter()
            if adapter_name:
                return str(adapter_name).strip().lower()
        return str(getattr(self.config, "ADAPTER_NAME", "inesdata") or "inesdata").strip().lower()

    def _safe_remove_runtime_dir(self, runtime_dir):
        if not runtime_dir:
            return False

        script_dir_getter = getattr(self.config, "script_dir", None)
        if not callable(script_dir_getter):
            return False

        deployments_root = os.path.abspath(
            os.path.join(script_dir_getter(), "deployers", self._adapter_name(), "deployments")
        )
        runtime_root = os.path.abspath(runtime_dir)
        if runtime_root == deployments_root or not runtime_root.startswith(deployments_root + os.sep):
            print(f"Skipping runtime cleanup outside managed deployments root: {runtime_dir}")
            return False

        if os.path.exists(runtime_root):
            shutil.rmtree(runtime_root)
            print(f"Removed generated dataspace runtime artifacts: {runtime_root}")
            return True
        return False

    def _validate_recreate_namespace(self, namespace):
        normalized = str(namespace or "").strip()
        forbidden = {
            "",
            "default",
            "kube-system",
            "kube-public",
            "kube-node-lease",
            "components",
            str(getattr(self.config, "NS_COMMON", "common-srvs") or "common-srvs").strip(),
        }
        if normalized in forbidden:
            raise RuntimeError(
                f"Refusing to recreate dataspace in protected namespace '{normalized}'. "
                "Use an isolated dataspace namespace."
            )
        return normalized

    def _wait_for_namespace_deleted(self, namespace, timeout=120, poll_interval=3):
        deadline = time.time() + timeout
        namespace_q = shlex.quote(namespace)
        while time.time() <= deadline:
            output = self.run_silent(f"kubectl get namespace {namespace_q} --no-headers")
            if not output:
                return True
            time.sleep(poll_interval)
        return False

    def build_recreate_dataspace_plan(self):
        ds_name = self._dataspace_name()
        namespace = self._dataspace_namespace()
        helm_release = self.config.helm_release_rs()
        return {
            "status": "planned",
            "adapter": self._adapter_name(),
            "dataspace": ds_name,
            "namespace": namespace,
            "runtime_dir": self._dataspace_runtime_dir(),
            "helm_releases": [helm_release],
            "actions": [
                "uninstall_dataspace_helm_releases",
                "delete_dataspace_namespace",
                "delete_dataspace_bootstrap_state",
                "remove_generated_runtime_artifacts",
                "run_level_3_again",
            ],
            "preserves_shared_services": True,
            "shared_services_namespace": getattr(self.config, "NS_COMMON", "common-srvs"),
            "invalidates_level_4_connectors": True,
        }

    def _cleanup_dataspace_before_recreate(self):
        ds_name = self._dataspace_name()
        namespace = self._validate_recreate_namespace(self._dataspace_namespace())
        helm_release = self.config.helm_release_rs()
        repo_dir = self.config.repo_dir()
        python_exec = self.config.python_exec()
        runtime_dir = self._dataspace_runtime_dir()

        print("\nCleaning existing dataspace Kubernetes resources...")
        self.run(
            f"helm uninstall {shlex.quote(helm_release)} -n {shlex.quote(namespace)}",
            check=False,
        )
        self.run(
            f"kubectl delete namespace {shlex.quote(namespace)} --ignore-not-found=true",
            check=False,
        )
        if not self._wait_for_namespace_deleted(namespace):
            raise RuntimeError(f"Timed out waiting for namespace '{namespace}' to be deleted")

        print("\nCleaning existing dataspace bootstrap state...")
        bootstrap_script = os.path.join(repo_dir, "bootstrap.py")
        if os.path.exists(bootstrap_script):
            self.run(
                f"{shlex.quote(python_exec)} bootstrap.py dataspace delete {shlex.quote(ds_name)}",
                cwd=repo_dir,
                check=False,
            )
        else:
            print(f"Bootstrap script not found at {bootstrap_script}; skipping bootstrap delete.")

        self._safe_remove_runtime_dir(runtime_dir)

    def recreate_dataspace(self, confirm_dataspace=None):
        ds_name = self._dataspace_name()
        if str(confirm_dataspace or "").strip() != ds_name:
            raise RuntimeError(
                f"Dataspace recreation requires explicit confirmation with the exact dataspace name '{ds_name}'."
            )

        plan = self.build_recreate_dataspace_plan()
        print("\n========================================")
        print("RECREATE DATASPACE")
        print("========================================")
        print(f"Adapter: {plan['adapter']}")
        print(f"Dataspace: {plan['dataspace']}")
        print(f"Namespace: {plan['namespace']}")
        print("Shared services will be preserved.")
        print("Level 4 connectors for this dataspace will be invalidated.\n")

        self._cleanup_dataspace_before_recreate()
        return self.deploy_dataspace()

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
            print("Check that the Keycloak hostname resolves through the active ingress/minikube tunnel.")
        else:
            print("Keycloak admin authentication did not become ready")
        return False

    def restart_registration_service(self):
        deployment_name = f"{self._dataspace_name()}-registration-service"
        namespace = self._dataspace_namespace()

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
        ds_name = self._dataspace_name()
        python_exec = self.config.python_exec()

        if not os.path.exists(repo_dir):
            self._fail("Repository not found. Run Level 2 first")

        if not self.infrastructure.ensure_local_infra_access():
            self._fail("Local access to PostgreSQL/Vault is not available")

        if not self.infrastructure.ensure_vault_unsealed():
            self._fail("Vault is not initialized or unsealed")

        reconcile_vault_state = getattr(self.infrastructure, "reconcile_vault_state_for_local_runtime", None)
        if callable(reconcile_vault_state) and not reconcile_vault_state():
            self._fail("Vault token could not be synchronized with the shared local runtime")

        sync_common_credentials = getattr(self.infrastructure, "sync_common_credentials_from_kubernetes", None)
        if callable(sync_common_credentials):
            sync_common_credentials()

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

        runtime_label = getattr(self.config, "RUNTIME_LABEL", "INESData")
        quiet_requirements = bool(getattr(self.config, "QUIET_REQUIREMENTS_INSTALL", False))
        print(f"Ensuring {runtime_label} Python dependencies...")
        ensure_python_requirements(
            python_exec,
            self.config.repo_requirements_path(),
            label=f"{runtime_label} runtime",
            quiet=quiet_requirements,
        )

        print("Cleaning previous databases...")
        connectors = getattr(self, "connectors_adapter", None)
        if connectors is None:
            raise RuntimeError("Deployment adapter requires a connectors adapter")

        connectors.force_clean_postgres_db(self.config.registration_db_name(), self.config.registration_db_user())
        connectors.force_clean_postgres_db(self.config.webportal_db_name(), self.config.webportal_db_user())

        print("Creating dataspace...")
        quiet_deployer_output = bool(getattr(self.config, "QUIET_SENSITIVE_DEPLOYER_OUTPUT", False))
        create_result = self.run(
            f"{python_exec} bootstrap.py dataspace create {ds_name}",
            cwd=repo_dir,
            capture=quiet_deployer_output,
            silent=quiet_deployer_output,
        )
        if create_result is None:
            self._fail("Error creating dataspace")
        if quiet_deployer_output:
            print("Dataspace bootstrap completed; sensitive deployer output suppressed")

        ensure_values_file = getattr(self.config, "ensure_registration_values_file", None)
        values_file = (
            ensure_values_file(refresh=True)
            if callable(ensure_values_file)
            else self.config.registration_values_file()
        )
        if not os.path.exists(values_file):
            self._fail("Registration service values file not found")

        minikube_ip = self.run("minikube ip", capture=True)
        if minikube_ip:
            self.update_helm_values_with_host_aliases(values_file, minikube_ip)

        print("\nDeploying registration-service...")
        if not self.infrastructure.deploy_helm_release(
            self.config.helm_release_rs(),
            self.config.namespace_demo(),
            values_file,
            cwd=self.config.registration_service_dir()
        ):
            self._fail("Error deploying registration-service")

        self.restart_registration_service()

        if not self.infrastructure.wait_for_dataspace_level3_pods(
            self.config.namespace_demo(),
            dataspace_name=ds_name,
        ):
            self._fail("Timeout waiting for dataspace pods")

        dataspace_ready, root_cause = self.infrastructure.verify_dataspace_ready_for_level4()
        if not dataspace_ready:
            self._fail("Level 3 did not leave the dataspace ready for Level 4", root_cause=root_cause)

        self.infrastructure.complete_level(3)
        print("Next step: run Level 4 to deploy or update the connectors for this dataspace.")

    def describe(self) -> str:
        return "INESDataDeploymentAdapter contains deployment logic for INESData."

