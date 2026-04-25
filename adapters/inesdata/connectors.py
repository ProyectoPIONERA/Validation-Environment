import base64
import json
import os
import re
import shlex
import socket
import time
from urllib.parse import urlparse

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
        self._vault_management_token_verified = False

    def _auto_mode(self):
        return self.auto_mode_getter() if callable(self.auto_mode_getter) else bool(self.auto_mode_getter)

    @staticmethod
    def _is_connector_interface_pod(pod_name):
        """Support both historical '-inteface' and corrected '-interface' suffixes."""
        return "interface" in pod_name or "inteface" in pod_name

    @classmethod
    def _is_connector_runtime_pod(cls, pod_name):
        return pod_name.startswith("conn-") and not cls._is_connector_interface_pod(pod_name)

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

    @staticmethod
    def _first_config_value(config, *keys, default=None):
        for key in keys:
            value = config.get(key)
            if value not in (None, ""):
                return value
        return default

    @classmethod
    def _minio_admin_credentials(cls, config):
        return (
            cls._first_config_value(config, "MINIO_ADMIN_USER", "MINIO_USER", default="admin"),
            cls._first_config_value(config, "MINIO_ADMIN_PASS", "MINIO_PASSWORD", default="aPassword1234"),
        )

    @staticmethod
    def _connector_credentials_missing_requirements(creds_file_path):
        if not os.path.exists(creds_file_path):
            return []

        try:
            with open(creds_file_path, encoding="utf-8") as handle:
                credentials = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return ["valid-json"]

        required = {
            "database": ("name", "user", "passwd"),
            "certificates": ("path", "passwd"),
            "connector_user": ("user", "passwd"),
            "vault": ("path", "token"),
            "minio": ("user", "passwd", "access_key", "secret_key"),
        }
        missing = []
        for section, keys in required.items():
            value = credentials.get(section)
            if not isinstance(value, dict):
                missing.append(section)
                continue
            missing.extend(f"{section}.{key}" for key in keys if not value.get(key))
        return missing

    @staticmethod
    def _reserve_local_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return sock.getsockname()[1]

    @staticmethod
    def _should_attempt_local_fallback(exc):
        if exc is None:
            return False
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "connection refused",
                "failed to establish a new connection",
                "name or service not known",
                "temporary failure in name resolution",
                "nodename nor servname provided",
                "max retries exceeded",
                "timed out",
            )
        )

    @staticmethod
    def _is_truthy(value):
        return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    def _allow_connector_port_forward_fallback(self):
        env_value = os.environ.get("PIONERA_ALLOW_CONNECTOR_PORT_FORWARD_FALLBACK")
        if env_value is not None:
            return self._is_truthy(env_value)

        try:
            deployer_config = self.config_adapter.load_deployer_config() or {}
        except Exception:
            deployer_config = {}
        return self._is_truthy(
            deployer_config.get("ALLOW_CONNECTOR_PORT_FORWARD_FALLBACK")
            or deployer_config.get("CONNECTOR_PORT_FORWARD_FALLBACK")
        )

    def _should_sync_vault_token_to_deployer_config(self):
        for resolver_name in ("infrastructure_deployer_config_path", "deployer_config_path"):
            resolver = getattr(self.config, resolver_name, None)
            if callable(resolver) and os.path.exists(resolver()):
                return True
        return False

    @staticmethod
    def _vault_capabilities_allow_management(capabilities):
        capability_set = set(capabilities or [])
        if "root" in capability_set or "sudo" in capability_set:
            return True
        return bool({"create", "update"}.intersection(capability_set)) and "deny" not in capability_set

    def _verify_vault_management_token(self, ds_name=None):
        deployer_config = self.config_adapter.load_deployer_config() or {}
        vault_url = str(
            deployer_config.get("VT_URL") or deployer_config.get("VAULT_URL") or ""
        ).strip().rstrip("/")
        vault_token = str(deployer_config.get("VT_TOKEN") or "").strip()
        if not vault_url or not vault_token:
            print("Vault token validation failed: VT_URL/VT_TOKEN are not defined in deployer.config")
            return False

        headers = {"X-Vault-Token": vault_token}
        try:
            response = requests.get(
                f"{vault_url}/v1/auth/token/lookup-self",
                headers=headers,
                timeout=5,
                verify=False,
            )
        except requests.RequestException as exc:
            print(f"Vault token validation failed: Vault is not reachable ({exc})")
            return False

        if response.status_code != 200:
            print(
                "Vault token validation failed: lookup-self returned "
                f"HTTP {response.status_code}. The shared Vault keys artifact may be stale "
                "for the running Vault. Recreate Level 2 common services or restore the "
                "current Vault root token before deploying INESData connectors."
            )
            return False

        ds_name = ds_name or self._dataspace_name()
        paths = [
            "sys/policy/inesdata-preflight-secrets-policy",
            "auth/token/create",
            f"secret/data/{ds_name}/inesdata-preflight/public-key",
        ]
        try:
            response = requests.post(
                f"{vault_url}/v1/sys/capabilities-self",
                headers=headers,
                json={"paths": paths},
                timeout=5,
                verify=False,
            )
        except requests.RequestException as exc:
            print(f"Vault token capabilities check failed: Vault is not reachable ({exc})")
            return False

        if response.status_code != 200:
            print(
                "Vault token capabilities check failed: Vault returned "
                f"HTTP {response.status_code}. INESData connector bootstrap requires policy, "
                "token and secret creation permissions."
            )
            return False

        try:
            capabilities_payload = response.json()
        except ValueError:
            print("Vault token capabilities check failed: Vault returned an invalid JSON response")
            return False

        for path in paths:
            capabilities = capabilities_payload.get(path)
            if capabilities is None:
                capabilities = capabilities_payload.get("capabilities")
            if not self._vault_capabilities_allow_management(capabilities):
                print(
                    "Vault token capabilities check failed: token does not have management "
                    f"permissions for '{path}'. Recreate Level 2 common services or restore "
                    "the current Vault root token before deploying INESData connectors."
                )
                return False

        return True

    def _prepare_vault_management_access(self, ds_name=None):
        if self._vault_management_token_verified:
            return True

        if not self.infrastructure.ensure_local_infra_access():
            return False

        if not self.infrastructure.ensure_vault_unsealed():
            return False

        if self._should_sync_vault_token_to_deployer_config():
            sync_vault_token = getattr(self.infrastructure, "sync_vault_token_to_deployer_config", None)
            if callable(sync_vault_token) and not sync_vault_token():
                print("Could not synchronize Vault token into deployer.config")
                return False

        if not self._verify_vault_management_token(ds_name=ds_name):
            return False

        self._vault_management_token_verified = True
        return True

    def _connector_pod_name(self, connector_name, interface=False):
        namespace = self.config.namespace_demo()
        result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not result:
            return None

        preferred = []
        fallback = []
        for line in result.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue

            pod_name = parts[0]
            status = parts[2]
            if not pod_name.startswith(connector_name):
                continue

            is_interface = self._is_connector_interface_pod(pod_name)
            if interface != is_interface:
                continue

            if status == "Running":
                preferred.append(pod_name)
            else:
                fallback.append(pod_name)

        candidates = preferred or fallback
        return candidates[0] if candidates else None

    def _open_temporary_port_forward(self, namespace, pod_name, remote_port):
        port_forward_service = getattr(self.infrastructure, "port_forward_service", None)
        if not callable(port_forward_service) or not pod_name:
            return None

        local_port = self._reserve_local_port()
        if not port_forward_service(namespace, pod_name, local_port, remote_port, quiet=True):
            return None

        return {
            "namespace": namespace,
            "pod_name": pod_name,
            "local_port": local_port,
        }

    def _close_temporary_port_forward(self, port_forward_info):
        if not port_forward_info:
            return

        stop_port_forward_service = getattr(self.infrastructure, "stop_port_forward_service", None)
        if callable(stop_port_forward_service):
            stop_port_forward_service(
                port_forward_info["namespace"],
                port_forward_info["pod_name"],
                quiet=True,
            )

    def _start_connector_interface_fallback(self, connector_name):
        pod_name = self._connector_pod_name(connector_name, interface=True)
        if not pod_name:
            return None, None

        port_forward = self._open_temporary_port_forward(
            self.config.namespace_demo(),
            pod_name,
            remote_port=8080,
        )
        if not port_forward:
            return None, None

        url = f"http://127.0.0.1:{port_forward['local_port']}/inesdata-connector-interface/"
        return url, port_forward

    def _start_connector_management_api_fallback(self, connector_name):
        pod_name = self._connector_pod_name(connector_name, interface=False)
        if not pod_name:
            return None, None

        port_forward = self._open_temporary_port_forward(
            self.config.namespace_demo(),
            pod_name,
            remote_port=19193,
        )
        if not port_forward:
            return None, None

        url = f"http://127.0.0.1:{port_forward['local_port']}/management/v3/assets/request"
        return url, port_forward

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
            print("Check that the Keycloak hostname resolves through the active ingress/minikube tunnel.")
        else:
            print("Keycloak admin authentication did not become ready")
        return False

    def _bootstrap_connector_create_command(self, python_exec, connector_name, ds_name):
        return f"{python_exec} bootstrap.py connector create {connector_name} {ds_name}"

    def _bootstrap_connector_delete_command(self, python_exec, connector_name, ds_name):
        return f"{python_exec} bootstrap.py connector delete {connector_name} {ds_name}"

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

    @staticmethod
    def _connector_belongs_to_dataspace(connector_name, ds_name):
        suffix = f"-{ds_name}"
        return connector_name.endswith(suffix)

    def _discover_existing_connectors(self, ds_name, namespace):
        existing = set()

        # Credentials-based detection.
        creds_dir = os.path.join(
            self.config.repo_dir(),
            "deployments",
            "DEV",
            ds_name,
        )
        if os.path.isdir(creds_dir):
            for entry in os.listdir(creds_dir):
                if not (entry.startswith("credentials-connector-") and entry.endswith(".json")):
                    continue
                connector = entry[len("credentials-connector-"):-len(".json")]
                if connector and self._connector_belongs_to_dataspace(connector, ds_name):
                    existing.add(connector)

        # Helm releases-based detection.
        releases = self.run_silent(f"helm list -n {namespace} --no-headers")
        if releases:
            suffix = f"-{ds_name}"
            for line in releases.splitlines():
                parts = line.split()
                if not parts:
                    continue
                release = parts[0]
                if release.startswith("conn-") and release.endswith(suffix):
                    connector = release[:-len(suffix)]
                    if connector and self._connector_belongs_to_dataspace(connector, ds_name):
                        existing.add(connector)

        # Pod-based detection (best-effort).
        pods = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if pods:
            for line in pods.splitlines():
                cols = line.split()
                if not cols:
                    continue
                pod_name = cols[0]
                if not pod_name.startswith("conn-"):
                    continue
                base = pod_name.rsplit("-", 1)[0]
                if base.endswith("-inteface") or base.endswith("-interface"):
                    base = base.rsplit("-", 1)[0]
                if base and self._connector_belongs_to_dataspace(base, ds_name):
                    existing.add(base)

        return existing

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

    def _local_connector_image_override_path(self):
        override_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "build",
            "local-overrides",
            "connector-local-overrides.yaml",
        )
        if os.path.isfile(override_path) and os.path.getsize(override_path) > 0:
            return override_path
        return None

    def _framework_root_dir(self):
        resolver = getattr(self.config, "script_dir", None)
        if callable(resolver):
            return resolver()
        repo_resolver = getattr(self.config, "repo_dir", None)
        if callable(repo_resolver):
            return os.path.abspath(repo_resolver())
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def _level4_local_images_mode(self):
        try:
            deployer_config = self.config_adapter.load_deployer_config() or {}
        except Exception:
            deployer_config = {}
        raw_value = (
            os.environ.get("PIONERA_INESDATA_LOCAL_IMAGES_MODE")
            or os.environ.get("INESDATA_LOCAL_IMAGES_MODE")
            or deployer_config.get("INESDATA_LOCAL_IMAGES_MODE")
            or deployer_config.get("LEVEL4_INESDATA_LOCAL_IMAGES_MODE")
            or deployer_config.get("LEVEL4_LOCAL_IMAGES_MODE")
            or "auto"
        )
        mode = str(raw_value or "auto").strip().lower()
        if mode in {"0", "false", "no", "off", "disabled", "disable"}:
            return "disabled"
        if mode in {"1", "true", "yes", "on", "auto", ""}:
            return "auto"
        if mode in {"required", "require", "strict"}:
            return "required"
        print(f"Unknown INESData local images mode '{raw_value}'. Falling back to auto.")
        return "auto"

    def _maybe_prepare_level4_local_connector_images(self, namespace):
        mode = self._level4_local_images_mode()
        if mode == "disabled":
            print("Level 4 local INESData connector images disabled by configuration.")
            return True

        root_dir = self._framework_root_dir()
        adapter_dir = os.path.join(root_dir, "adapters", "inesdata")
        script_path = os.path.join(adapter_dir, "scripts", "local_build_load_deploy.sh")
        source_dirs = [
            os.path.join(adapter_dir, "sources", "inesdata-connector"),
            os.path.join(adapter_dir, "sources", "inesdata-connector-interface"),
        ]
        missing_sources = [path for path in source_dirs if not os.path.isdir(path)]

        if missing_sources:
            detail = ", ".join(os.path.relpath(path, root_dir) for path in missing_sources)
            if mode == "required":
                print(f"Required INESData local connector sources are missing: {detail}")
                return False
            print(f"Skipping Level 4 local connector image preparation; missing sources: {detail}")
            return True

        if not os.path.isfile(script_path):
            detail = os.path.relpath(script_path, root_dir)
            if mode == "required":
                print(f"Required INESData local image workflow script is missing: {detail}")
                return False
            print(f"Skipping Level 4 local connector image preparation; missing script: {detail}")
            return True

        platform_dir = self.config.repo_dir()
        command = " ".join(
            shlex.quote(part)
            for part in [
                "bash",
                script_path,
                "--apply",
                "--platform-dir",
                platform_dir,
                "--namespace",
                namespace,
                "--deploy-target",
                "connectors",
                "--skip-deploy",
            ]
        )

        print("\nPreparing local INESData connector images for Level 4...")
        print("This builds and loads inesdata-connector and inesdata-connector-interface before Helm deploy.")
        result = self.run(command, check=False)
        if result is None:
            print("Error preparing local INESData connector images for Level 4.")
            return False
        return True

    def get_deployed_connectors(self, namespace):
        result = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not result:
            return []

        connectors = []
        for line in result.splitlines():
            pod_name = line.split()[0]
            if self._is_connector_runtime_pod(pod_name):
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
        host = urlparse(url).hostname
        local_fallback = None
        allow_local_fallback = self._allow_connector_port_forward_fallback()
        if host:
            try:
                socket.gethostbyname(host)
            except OSError as exc:
                if allow_local_fallback:
                    local_url, local_fallback = self._start_connector_interface_fallback(connector_name)
                    if local_url:
                        url = local_url
                    else:
                        print(f"Connector host does not resolve locally: {host} ({exc})")
                        return False
                else:
                    print(f"Connector host does not resolve locally: {host} ({exc})")
                    print("Connector port-forward fallback is disabled; validate the ingress hostname instead.")
                    return False
        start = time.time()
        last_issue = None

        try:
            while True:
                try:
                    response = requests.get(url, timeout=5)
                    if response.status_code in [200, 302]:
                        print(f"Connector ready: {connector_name}")
                        return True
                    last_issue = f"HTTP {response.status_code}"
                except Exception as exc:
                    last_issue = str(exc)
                    if (
                        allow_local_fallback
                        and not local_fallback
                        and self._should_attempt_local_fallback(exc)
                    ):
                        local_url, local_fallback = self._start_connector_interface_fallback(connector_name)
                        if local_url:
                            url = local_url
                            continue

                if time.time() - start > timeout:
                    if last_issue:
                        print(f"Timeout waiting for connector: {connector_name} ({last_issue})")
                    else:
                        print(f"Timeout waiting for connector: {connector_name}")
                    return False

                time.sleep(3)
        finally:
            self._close_temporary_port_forward(local_fallback)

    def wait_for_management_api_ready(self, connector_name, timeout=180, poll_interval=3):
        print(f"Waiting for management API to be ready: {connector_name}")
        start = time.time()
        base_url = self.connector_base_url(connector_name)
        url = f"{base_url}/management/v3/assets/request"
        host = urlparse(url).hostname
        allow_local_fallback = self._allow_connector_port_forward_fallback()
        payload = {
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/"
            },
            "offset": 0,
            "limit": 1,
        }
        last_issue = None
        local_fallback = None

        if host:
            try:
                socket.gethostbyname(host)
            except OSError as exc:
                if allow_local_fallback:
                    local_url, local_fallback = self._start_connector_management_api_fallback(connector_name)
                    if local_url:
                        url = local_url
                    else:
                        print(f"Connector Management API host does not resolve locally: {host} ({exc})")
                        return False
                else:
                    print(f"Connector Management API host does not resolve locally: {host} ({exc})")
                    print("Connector port-forward fallback is disabled; validate the ingress hostname instead.")
                    return False

        try:
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
                    if response.status_code == 401:
                        last_issue = "HTTP 401"
                        self.invalidate_management_api_token(connector_name)
                        time.sleep(poll_interval)
                        continue
                    last_issue = f"HTTP {response.status_code}"
                except Exception as exc:
                    last_issue = str(exc)
                    if (
                        allow_local_fallback
                        and not local_fallback
                        and self._should_attempt_local_fallback(exc)
                    ):
                        local_url, local_fallback = self._start_connector_management_api_fallback(connector_name)
                        if local_url:
                            url = local_url
                            continue

                time.sleep(poll_interval)
        finally:
            self._close_temporary_port_forward(local_fallback)

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
                return False

        return True

    def _wait_for_connector_deployments(self, connector_name, timeout=300):
        namespace = self.config.namespace_demo()
        rollout_waiter = getattr(self.infrastructure, "wait_for_deployment_rollout", None)
        timeout = max(int(timeout or 300), 1)

        if callable(rollout_waiter):
            deployment_targets = [
                (connector_name, f"connector runtime '{connector_name}'"),
                (f"{connector_name}-inteface", f"connector interface '{connector_name}'"),
            ]
            for deployment_name, label in deployment_targets:
                if not rollout_waiter(
                    namespace,
                    deployment_name,
                    timeout_seconds=timeout,
                    label=label,
                ):
                    return False
            return True

        wait_for_namespace_pods = getattr(self.infrastructure, "wait_for_namespace_pods", None)
        if callable(wait_for_namespace_pods):
            return bool(wait_for_namespace_pods(namespace, timeout=timeout))
        return False

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
        return f"{keycloak_url}/realms/{self._dataspace_name()}/protocol/openid-connect/token"

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

    def invalidate_management_api_token(self, connector):
        self._management_token_cache.pop(connector, None)

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
            print(f"  Password: {'***REDACTED***' if connector_user.get('passwd') else 'N/A'}")

            print("\nDatabase Credentials:")
            db_creds = creds.get("database", {})
            print(f"  Database: {db_creds.get('name', 'N/A')}")
            print(f"  User: {db_creds.get('user', 'N/A')}")
            print(f"  Password: {'***REDACTED***' if db_creds.get('passwd') else 'N/A'}")
            print(f"  Host: {pg_host}")
            print(f"  DSN: postgresql://{pg_host}:5432/{db_creds.get('name', 'N/A')}")

            print("\nMinIO Credentials:")
            minio_creds = creds.get("minio", {})
            print(f"  User: {minio_creds.get('user', 'N/A')}")
            print(f"  Password: {'***REDACTED***' if minio_creds.get('passwd') else 'N/A'}")
            print(f"  Access Key: {'***REDACTED***' if minio_creds.get('access_key') else 'N/A'}")
            print(f"  Secret Key: {'***REDACTED***' if minio_creds.get('secret_key') else 'N/A'}")
            if minio_hostname:
                print(f"  API URL: http://{minio_hostname}")
            if domain_base:
                print(f"  Console URL: http://console.minio-s3.{domain_base}")

        print(f"\n{'='*60}\n")

    def setup_minio_bucket(self, namespace, ds_name, connector_name, creds_file_path):
        print("\nConfiguring MinIO...")

        deployer_config = self.config_adapter.load_deployer_config() or {}
        minio_endpoint = deployer_config.get("MINIO_ENDPOINT") or "http://127.0.0.1:9000"
        minio_admin_user, minio_admin_pass = self._minio_admin_credentials(deployer_config)

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
        minio_user_password = minio_creds.get("passwd")
        minio_access_key = minio_creds.get("access_key")
        minio_secret_key = minio_creds.get("secret_key")
        if not all([minio_user_password, minio_access_key, minio_secret_key]):
            print(f"MinIO credentials are incomplete in {creds_file_path}")
            return False

        mc = f"kubectl exec -n {namespace} {minio_pod} --"

        alias_result = self.run(
            f"{mc} mc alias set minio {shlex.quote(minio_endpoint)} "
            f"{shlex.quote(minio_admin_user)} {shlex.quote(minio_admin_pass)}",
            check=False,
            silent=True,
        )
        if alias_result is None:
            print(
                "MinIO admin alias could not be configured. "
                "Check MINIO_USER/MINIO_PASSWORD in deployers/infrastructure/deployer.config "
                "and recreate Level 2 if the running MinIO secret is stale."
            )
            return False

        bucket_name = f"{ds_name}-{connector_name}"
        bucket_result = self.run(
            f"{mc} mc mb --ignore-existing {shlex.quote(f'minio/{bucket_name}')}",
            check=False,
        )
        if bucket_result is None:
            print(f"MinIO bucket '{bucket_name}' could not be created or verified")
            return False

        add_user_result = self.run(
            f"{mc} mc admin user add minio {shlex.quote(connector_name)} {shlex.quote(minio_user_password)}",
            capture=True,
            check=False,
            silent=True,
        )
        if add_user_result is None:
            user_info = self.run_silent(
                f"{mc} mc admin user info minio {shlex.quote(connector_name)}"
            )
            if not user_info:
                print(f"MinIO user '{connector_name}' could not be created or verified")
                return False

        svcacct_info = self.run_silent(
            f"{mc} mc admin user svcacct list minio {shlex.quote(connector_name)}"
        )
        if not svcacct_info or minio_access_key not in svcacct_info:
            svcacct_result = self.run(
                f"{mc} mc admin user svcacct add minio {shlex.quote(connector_name)} "
                f"--access-key {shlex.quote(minio_access_key)} --secret-key {shlex.quote(minio_secret_key)}",
                capture=True,
                check=False,
                silent=True,
            )
            if svcacct_result is None:
                svcacct_info = self.run_silent(
                    f"{mc} mc admin user svcacct list minio {shlex.quote(connector_name)}"
                )
                if not svcacct_info or minio_access_key not in svcacct_info:
                    print(f"MinIO service account for '{connector_name}' could not be created or verified")
                    return False

        # Attach S3 policy to connector user (required for upload permissions) - FIX for BUG-001
        policy_name = f"policy-{ds_name}-{connector_name}"
        policy_file_path = os.path.join(
            self.config.repo_dir(),
            "deployments",
            "DEV",
            ds_name,
            f"{policy_name}.json"
        )

        if os.path.exists(policy_file_path):
            try:
                with open(policy_file_path) as f:
                    policy_content = json.load(f)

                policy_path_pod = f"/tmp/{policy_name}.json"

                # Encode policy as base64 and decode in the pod to avoid shell
                # quoting issues and kubectl cp dependency on `tar`.
                policy_b64 = base64.b64encode(json.dumps(policy_content).encode("utf-8")).decode("ascii")
                write_policy_result = self.run(
                    f"{mc} sh -c \"echo '{policy_b64}' | base64 -d > {policy_path_pod}\"",
                    check=False,
                    silent=True,
                )
                if write_policy_result is None:
                    print(f"Could not write MinIO policy file inside pod for '{connector_name}'")
                    return False

                # Create policy in MinIO (idempotent: ignore already-exists error)
                self.run(
                    f"{mc} mc admin policy create minio {policy_name} {policy_path_pod}",
                    check=False,
                    silent=True,
                )

                # Attach policy to user
                self.run(
                    f"{mc} mc admin policy attach minio {policy_name} --user {connector_name}",
                    check=False,
                    silent=True,
                )

                # Verify
                result = self.run_silent(
                    f"kubectl exec -n {namespace} {minio_pod} -- mc admin user info minio {connector_name}"
                )
                if result and policy_name in result:
                    print(f"MinIO policy '{policy_name}' attached to '{connector_name}'")
                else:
                    print(f"MinIO policy attach could not be verified for '{connector_name}'")
                    return False
            except (IOError, json.JSONDecodeError) as e:
                print(f"Could not attach MinIO policy: {e}")
                return False
        else:
            print(f"Policy file not found at {policy_file_path}")
            return False

        print("MinIO configured")
        return True

    def ensure_minio_policy_attached(self, connector_name, ds_name=None):
        """Idempotently ensure the S3 policy is attached to a connector MinIO user.

        Safe to call at any level; checks current state before taking action.
        """
        ds_name = ds_name or self._dataspace_name()
        namespace = self.config.NS_COMMON
        policy_name = f"policy-{ds_name}-{connector_name}"

        deployer_config = self.config_adapter.load_deployer_config() or {}
        minio_endpoint = deployer_config.get("MINIO_ENDPOINT") or "http://127.0.0.1:9000"
        minio_admin_user, minio_admin_pass = self._minio_admin_credentials(deployer_config)

        minio_pod = self.infrastructure.get_pod_by_name(namespace, self.config.service_minio())
        if not minio_pod:
            print(f"  MinIO pod not found — skipping policy ensure for {connector_name}")
            return False

        mc = f"kubectl exec -n {namespace} {minio_pod} --"
        alias_result = self.run(
            f"{mc} mc alias set minio {shlex.quote(minio_endpoint)} "
            f"{shlex.quote(minio_admin_user)} {shlex.quote(minio_admin_pass)}",
            check=False,
            silent=True,
        )
        if alias_result is None:
            print(f"  MinIO admin alias could not be configured for {connector_name}")
            return False

        user_info = self.run_silent(f"{mc} mc admin user info minio {shlex.quote(connector_name)}")
        if user_info and policy_name in user_info:
            print(f"  MinIO policy '{policy_name}' already present on '{connector_name}'")
            return True

        policy_file_path = os.path.join(
            self.config.repo_dir(),
            "deployments",
            "DEV",
            ds_name,
            f"{policy_name}.json",
        )
        if not os.path.exists(policy_file_path):
            print(f"  Warning: policy file not found: {policy_file_path}")
            return False

        try:
            with open(policy_file_path) as f:
                policy_content = json.load(f)
            if not policy_content:
                print(f"  Warning: policy file {policy_file_path} is empty")
                return False

            policy_path_pod = f"/tmp/{policy_name}.json"
            policy_b64 = base64.b64encode(json.dumps(policy_content).encode("utf-8")).decode("ascii")
            write_policy_result = self.run(
                f"{mc} sh -c \"echo '{policy_b64}' | base64 -d > {policy_path_pod}\"",
                check=False,
                silent=True,
            )
            if write_policy_result is None:
                print(f"  Warning: could not write MinIO policy file inside pod for {connector_name}")
                return False
            self.run(f"{mc} mc admin policy create minio {policy_name} {policy_path_pod}", check=False, silent=True)
            self.run(
                f"{mc} mc admin policy attach minio {policy_name} --user {shlex.quote(connector_name)}",
                check=False,
                silent=True,
            )

            user_info = self.run_silent(f"{mc} mc admin user info minio {shlex.quote(connector_name)}")
            if user_info and policy_name in user_info:
                print(f"  MinIO policy '{policy_name}' re-attached to '{connector_name}'")
                return True

            print(f"  Warning: policy attach could not be verified for '{connector_name}'")
            return False
        except (IOError, json.JSONDecodeError) as e:
            print(f"  Warning: could not attach MinIO policy: {e}")
            return False

    def ensure_all_minio_policies(self, connectors):
        """Ensure MinIO S3 policies are attached for every connector in the list."""
        print("\nEnsuring MinIO policies...")
        all_ok = all(self.ensure_minio_policy_attached(c) for c in connectors)
        if all_ok:
            print("All MinIO policies confirmed\n")
        else:
            print("Warning: one or more MinIO policies could not be confirmed\n")
        return all_ok

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

    def _remove_connector_values_file(self, connector_name):
        values_file = self.config.connector_values_file(connector_name)
        if os.path.exists(values_file):
            try:
                os.remove(values_file)
                print(f"Removed stale connector values file: {values_file}")
            except OSError as exc:
                print(f"Warning: could not remove stale values file {values_file}: {exc}")
        return values_file

    def _cleanup_connector_state(self, connector_name, repo_dir, ds_name, python_exec, namespace=None):
        values_file = self._remove_connector_values_file(connector_name)
        self.invalidate_management_api_token(connector_name)

        print(f"Cleaning connector: {connector_name}")
        delete_cmd = self._bootstrap_connector_delete_command(python_exec, connector_name, ds_name)
        self.run(delete_cmd, cwd=repo_dir, check=False)

        release_name = f"{connector_name}-{ds_name}"
        ns = namespace or self.config.namespace_demo()
        self.run(f"helm uninstall {release_name} -n {ns}", check=False)

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

        return values_file

    def create_connector(self, connector_name, connector_hostnames=None):
        print("\n========================================")
        print("LEVEL 4 - CREATE CONNECTOR")
        print("========================================\n")

        repo_dir = self.config.repo_dir()
        ds_name = self._dataspace_name()
        python_exec = self.config.python_exec()

        if not os.path.exists(repo_dir):
            print("Repository not found. Run Level 2 first")
            return False

        if not os.path.exists(self.config.venv_path()):
            print("Python environment not found. Run Level 3 first")
            return False

        if not self._prepare_vault_management_access(ds_name=ds_name):
            return False

        if not self.wait_for_keycloak_admin_ready():
            print("Keycloak admin API not ready for connector cleanup")
            return False

        values_file = self._cleanup_connector_state(connector_name, repo_dir, ds_name, python_exec)

        if not self.wait_for_keycloak_admin_ready():
            print("Keycloak admin API not ready for connector provisioning")
            return False

        print(f"Creating connector {connector_name}...")
        create_cmd = self._bootstrap_connector_create_command(python_exec, connector_name, ds_name)
        create_result = None
        creds_path = self.config.connector_credentials_path(connector_name)
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            create_result = self.run(create_cmd, cwd=repo_dir, check=False)
            missing_credentials = (
                self._connector_credentials_missing_requirements(creds_path)
                if create_result is not None
                else []
            )
            if create_result is not None and not missing_credentials:
                break
            if missing_credentials:
                print(
                    "Connector bootstrap produced incomplete credentials "
                    f"({', '.join(missing_credentials)}). Retrying cleanly..."
                )
                create_result = None
            if attempt < max_attempts:
                print(
                    f"Connector creation failed on attempt {attempt}. "
                    "Cleaning partial state and retrying after Keycloak readiness check..."
                )
                values_file = self._cleanup_connector_state(connector_name, repo_dir, ds_name, python_exec)
                if not self.wait_for_keycloak_admin_ready():
                    print("Keycloak admin API not ready for connector provisioning retry")
                    return False
                time.sleep(5)

        if create_result is None:
            print("Error: deployment failed")
            return False

        self.invalidate_management_api_token(connector_name)
        if not self.setup_minio_bucket(self.config.NS_COMMON, ds_name, connector_name, creds_path):
            print("Error: MinIO configuration failed")
            return False

        timeout = 10
        start = time.time()

        while not os.path.exists(values_file):
            if time.time() - start > timeout:
                print("Timeout waiting for values file generation")
                return False
            time.sleep(1)

        if not os.path.exists(values_file):
            print("Connector values file not found")
            return False

        connector_hostnames = connector_hostnames or [connector_name]
        self.update_connector_host_aliases(values_file, connector_hostnames)

        release_name = f"{connector_name}-{ds_name}"
        print(f"Deploying connector {connector_name}...")
        values_files = [os.path.basename(values_file)]
        local_image_override = self._local_connector_image_override_path()
        if local_image_override:
            values_files.append(local_image_override)
            print(f"Using local connector image overrides: {local_image_override}")

        if not self.infrastructure.deploy_helm_release(
            release_name,
            self.config.namespace_demo(),
            values_files,
            cwd=self.config.connector_dir()
        ):
            print("Error deploying connector")
            return False

        rollout_timeout = max(int(getattr(self.config, "TIMEOUT_POD_WAIT", 120)), 180)
        if not self._wait_for_connector_deployments(connector_name, timeout=rollout_timeout):
            print("Timeout waiting for connector deployment rollout")
            return False

        print("\nCONNECTORS CREATED\n")
        return True

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

    def connector_database_credentials_valid(self, connector_name):
        creds = self.load_connector_credentials(connector_name)
        if not creds:
            print(f"Connector credentials not found: {connector_name}")
            return False

        db_creds = creds.get("database", {})
        db_name = db_creds.get("name")
        db_user = db_creds.get("user")
        db_password = db_creds.get("passwd")
        pg_host, _, _ = self.config_adapter.get_pg_credentials()

        if not db_name or not db_user or not db_password:
            print(f"Incomplete database credentials for connector: {connector_name}")
            return False

        result = self.run_silent(
            f"PGPASSWORD={db_password} "
            f"psql -h {pg_host} -U {db_user} -d {db_name} -t -A -c \"SELECT 1;\""
        )

        if result and result.strip() == "1":
            return True

        print(
            f"Connector database credentials are stale or invalid: {connector_name} "
            f"(database={db_name}, user={db_user})"
        )
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
            if self._is_connector_runtime_pod(pod_name) and status != "Running":
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

    def validate_connectors_with_stabilization(self, connectors, retries=2, wait_seconds=20, backoff_factor=2):
        """Retry connector validation after short stabilization waits with light backoff."""
        if self.validate_connectors_deployment(connectors):
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
            if self.validate_connectors_deployment(connectors):
                print("Connector validation recovered after stabilization retry.")
                return True
            current_wait *= backoff_factor

        return False

    def show_connector_logs(self):
        namespace = self.config.namespace_demo()
        pods = self.run_silent(f"kubectl get pods -n {namespace} --no-headers")
        if not pods:
            print("No pods found in namespace")
            return

        connector_pods = []
        for line in pods.splitlines():
            pod_name = line.split()[0]
            if self._is_connector_runtime_pod(pod_name):
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

        repo_dir = self.config.repo_dir()
        python_exec = self.config.python_exec()

        if not os.path.exists(repo_dir):
            print("Repository not found. Run Level 2 first")
            return []

        if not os.path.exists(self.config.venv_path()):
            print("Python environment not found. Run Level 3 first")
            return []

        print("Ensuring INESData Python dependencies...")
        ensure_python_requirements(
            python_exec,
            self.config.repo_requirements_path(),
            label="INESData runtime",
        )

        dataspaces = self.load_dataspace_connectors()
        if not dataspaces:
            print("No dataspaces defined in deployer.config")
            return []

        first_namespace = dataspaces[0].get("namespace") or self.config.namespace_demo()
        if not self._maybe_prepare_level4_local_connector_images(first_namespace):
            return []

        all_connectors = set()
        infra_ready = False
        vault_ready = False

        for ds in dataspaces:
            ds_name = ds["name"]
            namespace = ds["namespace"]
            connectors = ds["connectors"]

            print(f"\nDataspace: {ds_name}")
            print(f"Namespace: {namespace}")
            print(f"Connectors defined: {connectors}\n")

            desired = set(connectors or [])
            existing = self._discover_existing_connectors(ds_name, namespace)
            stale = sorted(existing - desired)
            if stale:
                print(f"Found stale connectors for dataspace '{ds_name}': {stale}")
                if not infra_ready:
                    if not self.infrastructure.ensure_local_infra_access():
                        return []
                    infra_ready = True
                if not vault_ready:
                    if not self.infrastructure.ensure_vault_unsealed():
                        return []
                    vault_ready = True
                if not self._prepare_vault_management_access(ds_name=ds_name):
                    return []
                for stale_connector in stale:
                    self._cleanup_connector_state(stale_connector, repo_dir, ds_name, python_exec, namespace=namespace)

            for connector in connectors:
                all_connectors.add(connector)

                if self.connector_already_exists(connector, namespace):
                    if (
                        self.connector_is_healthy(connector, namespace)
                        and self.connector_database_credentials_valid(connector)
                    ):
                        print(f"Connector already running: {connector}")
                        print("Recreating connector to ensure a clean Level 4 deployment")
                    else:
                        print(f"Connector exists but is unhealthy or stale. Recreating: {connector}")

                print(f"Deploying connector: {connector}")
                values_file = self.config.connector_values_file(connector)
                if not self.create_connector(connector, connectors):
                    print(f"Aborting Level 4 because connector recreation failed: {connector}")
                    return []

                if not os.path.exists(values_file):
                    print(f"Values file not found: {values_file}")
                    return []

        all_connectors = list(all_connectors)
        print("\nAll connectors deployed or already existing\n")
        print("Configuring connector hosts...")
        connector_hosts = self.config_adapter.generate_connector_hosts(all_connectors)
        self.infrastructure.manage_hosts_entries(connector_hosts)
        self.wait_for_all_connectors(all_connectors)
        self._setup_nginx_proxy_if_configured()
        return all_connectors

    def _setup_nginx_proxy_if_configured(self):
        deployer_config = self.config_adapter.load_deployer_config() or {}
        public_hostname = str(deployer_config.get("PUBLIC_HOSTNAME", "")).strip()
        if not public_hostname:
            return

        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "deployers", "inesdata", "scripts", "setup-nginx-proxy.sh"
        )
        script_path = os.path.normpath(script_path)
        if not os.path.exists(script_path):
            print(f"  [nginx-proxy] Script not found: {script_path}")
            return

        minikube_ip = self.run("minikube ip", capture=True) or "192.168.49.2"
        minikube_ip = minikube_ip.strip()
        vm_ip = str(deployer_config.get("VM_COMMON_IP", "192.168.122.64")).strip() or "192.168.122.64"
        internal_domain = str(deployer_config.get("DOMAIN_BASE", "pionera.oeg.fi.upm.es")).strip()
        manual_cmd = f"bash {script_path} {minikube_ip} {vm_ip} {public_hostname} {internal_domain}"

        print(f"\n[Level 4] PUBLIC_HOSTNAME={public_hostname} — configuring nginx external proxy...")

        can_sudo = self.run("sudo -n true", check=False) is not None
        if not can_sudo:
            print(
                "  [nginx-proxy] sudo requires a password in this session.\n"
                "  Run once manually to enable external browser access:\n"
                f"  {manual_cmd}"
            )
            return

        result = self.run(manual_cmd, check=False)
        if result is None:
            print(
                "  [nginx-proxy] Script failed. Run manually:\n"
                f"  {manual_cmd}"
            )
        else:
            print(f"  [nginx-proxy] External access configured for https://{public_hostname}")

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
            if self._is_connector_runtime_pod(name):
                connectors.add("-".join(name.split("-")[:3]))

        return sorted(connectors)

    def describe(self) -> str:
        return "INESDataConnectorsAdapter contains connector logic for INESData."
