import os
import shlex
import shutil
import subprocess
import time

import requests
import yaml

from adapters.shared.config import resolve_shared_level3_bootstrap_runtime
from deployers.shared.lib.topology import LOCAL_TOPOLOGY, VM_SINGLE_TOPOLOGY, normalize_topology
from runtime_dependencies import ensure_python_requirements


class SharedDataspaceDeploymentAdapter:
    """Neutral Level 3 deployment flow reused by multiple adapters."""

    def __init__(self, run, run_silent, auto_mode_getter, infrastructure_adapter, config_adapter, config_cls):
        self.run = run
        self.run_silent = run_silent
        self.auto_mode_getter = auto_mode_getter
        self.infrastructure = infrastructure_adapter
        self.config = config_cls
        self.config_adapter = config_adapter

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

    def _registration_service_namespace(self):
        config_namespace_getter = getattr(self.config, "registration_service_namespace", None)
        if callable(config_namespace_getter):
            namespace = config_namespace_getter()
            if namespace:
                return str(namespace).strip()
        namespace_getter = getattr(self.config_adapter, "primary_registration_service_namespace", None)
        if callable(namespace_getter):
            try:
                namespace = namespace_getter()
            except Exception:
                namespace = None
            if namespace:
                return str(namespace).strip()
        return self._dataspace_namespace()

    def _dataspace_runtime_dir(self):
        bootstrap_runtime = resolve_shared_level3_bootstrap_runtime(self.config) or {}
        if bootstrap_runtime.get("runtime_dir"):
            return bootstrap_runtime["runtime_dir"]
        return os.path.join(self.config.repo_dir(), "deployments", "DEV", self._dataspace_name())

    def _bootstrap_dataspace_command(self, action, dataspace=None):
        runtime = resolve_shared_level3_bootstrap_runtime(self.config) or {}
        command_getter = runtime.get("bootstrap_dataspace_command")
        resolved_dataspace = dataspace or self._dataspace_name()
        if callable(command_getter):
            return command_getter(action, dataspace=resolved_dataspace)
        return (
            f"{shlex.quote(self.config.python_exec())} bootstrap.py "
            f"dataspace {shlex.quote(str(action))} {shlex.quote(str(resolved_dataspace))}"
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
        namespace = self._registration_service_namespace()
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
        namespace = self._validate_recreate_namespace(self._registration_service_namespace())
        helm_release = self.config.helm_release_rs()
        bootstrap_runtime = resolve_shared_level3_bootstrap_runtime(self.config) or {}
        repo_dir = bootstrap_runtime.get("repo_dir") or self.config.repo_dir()
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
        bootstrap_script = bootstrap_runtime.get("bootstrap_script") or os.path.join(repo_dir, "bootstrap.py")
        if os.path.exists(bootstrap_script):
            self.run(
                self._bootstrap_dataspace_command("delete", dataspace=ds_name),
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

        host_alias_domains = getattr(self.config_adapter, "host_alias_domains", None)
        if callable(host_alias_domains):
            hostnames = host_alias_domains(
                ds_name=self._dataspace_name(),
                ds_namespace=self._dataspace_namespace(),
            )
        else:
            hostnames = self.config.host_alias_domains()

        values["hostAliases"] = [{
            "ip": minikube_ip,
            "hostnames": hostnames
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

    @staticmethod
    def _sql_literal(value):
        return "'" + str(value).replace("'", "''") + "'"

    @staticmethod
    def _sql_identifier(value):
        return '"' + str(value).replace('"', '""') + '"'

    def _postgres_runtime(self):
        credentials_getter = getattr(self.config_adapter, "get_pg_credentials", None)
        if not callable(credentials_getter):
            return None

        pg_host, pg_user, pg_password = credentials_getter()
        port_getter = getattr(self.config_adapter, "get_pg_port", None)
        pg_port = port_getter() if callable(port_getter) else "5432"
        return {
            "host": str(pg_host or "localhost"),
            "port": str(pg_port or "5432"),
            "user": str(pg_user or "postgres"),
            "password": str(pg_password or ""),
        }

    def _run_postgres_admin_query(self, sql_text):
        runtime = self._postgres_runtime()
        if not runtime:
            self._fail("PostgreSQL cleanup is not configured for Level 3")

        env = os.environ.copy()
        env["PGPASSWORD"] = runtime["password"]
        return subprocess.run(
            [
                "psql",
                "-h",
                runtime["host"],
                "-p",
                runtime["port"],
                "-U",
                runtime["user"],
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-c",
                sql_text,
            ],
            text=True,
            capture_output=True,
            env=env,
        )

    def _postgres_cleanup_residual_state(self, database_name, database_user):
        checks = [
            (
                "database",
                f"SELECT 1 FROM pg_database WHERE datname = {self._sql_literal(database_name)};",
            ),
            (
                "role",
                f"SELECT 1 FROM pg_roles WHERE rolname = {self._sql_literal(database_user)};",
            ),
        ]
        residual = []
        for label, sql_text in checks:
            result = self._run_postgres_admin_query(sql_text)
            if result.returncode != 0:
                root_cause = (result.stderr or result.stdout or "").strip() or f"psql exited with code {result.returncode}"
                self._fail("Could not verify PostgreSQL cleanup state", root_cause=root_cause)
            if result.stdout.strip():
                residual.append(label)
        return residual

    def _cleanup_postgres_database_and_role_directly(self, database_name, database_user):
        statements = [
            (
                "terminate active sessions",
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                f"WHERE datname = {self._sql_literal(database_name)} "
                "AND pid <> pg_backend_pid();",
            ),
            (
                "drop database",
                f"DROP DATABASE IF EXISTS {self._sql_identifier(database_name)};",
            ),
            (
                "drop role",
                f"DROP ROLE IF EXISTS {self._sql_identifier(database_user)};",
            ),
        ]
        for label, sql_text in statements:
            result = self._run_postgres_admin_query(sql_text)
            if result.returncode != 0:
                root_cause = (result.stderr or result.stdout or "").strip() or f"psql exited with code {result.returncode}"
                self._fail(
                    f"PostgreSQL cleanup failed while trying to {label}",
                    root_cause=root_cause,
                )

    def _cleanup_level3_postgres_state(self, database_name, database_user, label):
        connectors = getattr(self, "connectors_adapter", None)
        cleanup_getter = getattr(connectors, "force_clean_postgres_db", None)
        if callable(cleanup_getter):
            cleanup_getter(database_name, database_user)

        residual = self._postgres_cleanup_residual_state(database_name, database_user)
        if not residual:
            return

        print(
            f"PostgreSQL cleanup for {label} left residual state "
            f"({', '.join(residual)}). Reconciling directly..."
        )
        self._cleanup_postgres_database_and_role_directly(database_name, database_user)
        residual = self._postgres_cleanup_residual_state(database_name, database_user)
        if residual:
            self._fail(
                f"PostgreSQL cleanup did not remove previous {label} state",
                root_cause=f"{', '.join(residual)} still present for {database_name}/{database_user}",
            )

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
        namespace = self._registration_service_namespace()

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

    def _show_minikube_tunnel_prompt(self):
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

    def _deploy_dataspace_runtime(
        self,
        *,
        topology=LOCAL_TOPOLOGY,
        require_tunnel_prompt=True,
        update_minikube_host_aliases=True,
    ):
        self.infrastructure.announce_level(3, "DATASPACE")
        normalized_topology = normalize_topology(topology)

        if require_tunnel_prompt:
            self._show_minikube_tunnel_prompt()
        else:
            print(
                f"Topology '{normalized_topology}' uses an existing cluster ingress. "
                "Skipping Minikube tunnel prompt.\n"
            )

        bootstrap_runtime = resolve_shared_level3_bootstrap_runtime(self.config) or {}
        repo_dir = bootstrap_runtime.get("repo_dir") or self.config.repo_dir()
        ds_name = self._dataspace_name()
        python_exec = bootstrap_runtime.get("python_exec") or self.config.python_exec()

        if not os.path.exists(repo_dir):
            self._fail("Repository not found. Run Level 2 first")

        requires_local_runtime_access = normalized_topology == LOCAL_TOPOLOGY

        if requires_local_runtime_access and not self.infrastructure.ensure_local_infra_access():
            self._fail("Local access to PostgreSQL/Vault is not available")

        if not self.infrastructure.ensure_vault_unsealed():
            self._fail("Vault is not initialized or unsealed")

        reconcile_vault_state = getattr(self.infrastructure, "reconcile_vault_state_for_local_runtime", None)
        if requires_local_runtime_access and callable(reconcile_vault_state) and not reconcile_vault_state():
            self._fail("Vault token could not be synchronized with the shared local runtime")

        sync_common_credentials = getattr(self.infrastructure, "sync_common_credentials_from_kubernetes", None)
        if callable(sync_common_credentials):
            sync_common_credentials()

        print("Verifying Keycloak access...")
        deployer_config = self.config_adapter.load_deployer_config()
        kc_url = deployer_config.get("KC_URL")
        kc_runtime_url = deployer_config.get("KC_INTERNAL_URL") or kc_url
        kc_user = deployer_config.get("KC_USER")
        kc_password = deployer_config.get("KC_PASSWORD")

        if not kc_runtime_url:
            self._fail("KC_INTERNAL_URL/KC_URL not defined in deployer.config")
        if not kc_user or not kc_password:
            self._fail("KC_USER/KC_PASSWORD not defined in deployer.config")

        try:
            response = requests.get(f"{kc_runtime_url}/realms/master", timeout=5)
            if response.status_code not in (200, 302):
                self._fail(
                    "Keycloak not ready",
                    root_cause=(
                        f"unexpected HTTP status {response.status_code} from "
                        f"{kc_runtime_url}/realms/master"
                    ),
                )
        except Exception:
            self._fail("Keycloak not accessible. Verify ingress hostname resolution")

        if not self.wait_for_keycloak_admin_ready(kc_runtime_url, kc_user, kc_password):
            self._fail("Keycloak admin API not ready", root_cause="admin authentication did not succeed in time")

        if not os.path.exists(self.config.venv_path()):
            print("Creating Python environment...")
            self.run("python3 -m venv .venv", cwd=repo_dir)

        runtime_label = getattr(self.config, "RUNTIME_LABEL", "dataspace")
        quiet_requirements = bool(getattr(self.config, "QUIET_REQUIREMENTS_INSTALL", False))
        print(f"Ensuring {runtime_label} Python dependencies...")
        ensure_python_requirements(
            python_exec,
            bootstrap_runtime.get("requirements_path") or self.config.repo_requirements_path(),
            label=f"{runtime_label} runtime",
            quiet=quiet_requirements,
        )

        print("Cleaning previous databases...")
        self._cleanup_level3_postgres_state(
            self.config.registration_db_name(),
            self.config.registration_db_user(),
            "registration-service",
        )
        self._cleanup_level3_postgres_state(
            self.config.webportal_db_name(),
            self.config.webportal_db_user(),
            "web portal",
        )

        print("Creating dataspace...")
        quiet_deployer_output = bool(getattr(self.config, "QUIET_SENSITIVE_DEPLOYER_OUTPUT", False))
        create_result = self.run(
            self._bootstrap_dataspace_command("create", dataspace=ds_name),
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

        if update_minikube_host_aliases:
            minikube_ip = self.run("minikube ip", capture=True)
            if minikube_ip:
                self.update_helm_values_with_host_aliases(values_file, minikube_ip)

        print("\nDeploying registration-service...")
        if not self.infrastructure.deploy_helm_release(
            self.config.helm_release_rs(),
            self._registration_service_namespace(),
            values_file,
            cwd=self.config.registration_service_dir()
        ):
            self._fail("Error deploying registration-service")

        self.restart_registration_service()

        if not self.infrastructure.wait_for_dataspace_level3_pods(
            self._registration_service_namespace(),
            dataspace_name=ds_name,
        ):
            self._fail("Timeout waiting for dataspace pods")

        dataspace_ready, root_cause = self.infrastructure.verify_dataspace_ready_for_level4()
        if not dataspace_ready:
            self._fail("Level 3 did not leave the dataspace ready for Level 4", root_cause=root_cause)

        self.infrastructure.complete_level(3)
        print("Next step: run Level 4 to deploy or update the connectors for this dataspace.")

    def deploy_dataspace(self):
        return self._deploy_dataspace_runtime()

    def deploy_dataspace_for_topology(self, topology=LOCAL_TOPOLOGY):
        normalized_topology = normalize_topology(topology)
        if normalized_topology == LOCAL_TOPOLOGY:
            return self.deploy_dataspace()
        if normalized_topology != VM_SINGLE_TOPOLOGY:
            raise RuntimeError(
                f"Level 3 deploy_dataspace_for_topology() is not implemented for topology "
                f"'{normalized_topology}' yet."
            )
        return self._deploy_dataspace_runtime(
            topology=normalized_topology,
            require_tunnel_prompt=False,
            update_minikube_host_aliases=False,
        )
