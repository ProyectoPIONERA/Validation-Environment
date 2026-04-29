import json
import os
import shlex
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
        self._announced_levels = set()
        self._completed_levels = set()

    def _auto_mode(self):
        return self.auto_mode_getter() if callable(self.auto_mode_getter) else bool(self.auto_mode_getter)

    @staticmethod
    def _fail(message, root_cause=None):
        if root_cause:
            raise RuntimeError(f"{message}. Root cause: {root_cause}")
        raise RuntimeError(message)

    @staticmethod
    def _print_unique_lines(output):
        previous = None
        for line in (output or "").splitlines():
            line = line.rstrip()
            if not line or line == previous:
                continue
            print(line)
            previous = line

    def _dataspace_name(self):
        getter = getattr(self.config, "dataspace_name", None)
        if callable(getter):
            return getter()
        return (getattr(self.config, "DS_NAME", "demo") or "demo").strip() or "demo"

    @staticmethod
    def _first_config_value(config, *keys):
        for key in keys:
            value = config.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _minio_admin_credentials(cls, config):
        return (
            cls._first_config_value(config, "MINIO_ADMIN_USER", "MINIO_USER"),
            cls._first_config_value(config, "MINIO_ADMIN_PASS", "MINIO_PASSWORD"),
        )

    def announce_level(self, level, title):
        if level in self._announced_levels:
            return
        print("\n========================================")
        print(f"LEVEL {level} - {title}")
        print("========================================\n")
        self._announced_levels.add(level)

    def complete_level(self, level):
        if level in self._completed_levels:
            return
        print(f"\nLEVEL {level} COMPLETE\n")
        self._completed_levels.add(level)

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

    def get_vm_ip(self):
        """Fetch the primary IP address of the VM using 'hostname -I'."""
        result = self.run("hostname -I", capture=True, silent=True)
        if result:
            ips = result.split()
            if ips:
                primary_ip = ips[0].strip()
                print(f"Detected VM External IP: {primary_ip}")
                return primary_ip
        return None

    def patch_ingress_external_ip(self):
        """Patches the Ingress Controller LoadBalancer with the VM's external IP."""
        vm_ip = self.get_vm_ip()
        if not vm_ip:
            print("Warning: Could not determine VM IP for ingress patching.")
            return

        print(f"Patching Ingress Controller with LoadBalancer IP: {vm_ip}")
        patch_json = json.dumps({"spec": {"externalIPs": [vm_ip]}})

        cmd = (
            f"kubectl patch svc ingress-nginx-controller "
            f"-n ingress-nginx --patch {shlex.quote(patch_json)}"
        )
        self.run(cmd, check=False)

    def get_hosts_path(self):
        import sys

        if self.is_wsl():
            return "/mnt/c/Windows/System32/drivers/etc/hosts"
        if sys.platform.startswith("linux"):
            return "/etc/hosts"
        if sys.platform == "darwin":
            return "/private/etc/hosts"
        return None

    def manage_hosts_entries(self, desired_entries, header_comment="# Dataspace Local Deployment", auto_confirm=None):
        hosts_path = self.get_hosts_path()

        default_header = "# Dataspace Local Deployment"
        header_comment = (header_comment or default_header).strip() or default_header
        if not header_comment.startswith("#"):
            header_comment = f"# {header_comment}"

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

        lines = content.splitlines()

        def line_matches_entry(line: str, entry: str) -> bool:
            stripped = line.strip()
            if not stripped.startswith(entry):
                return False
            if len(stripped) == len(entry):
                return True
            next_char = stripped[len(entry)]
            return next_char.isspace() or next_char == "#"

        def entry_present(entry: str) -> bool:
            return any(line_matches_entry(line, entry) for line in lines)

        def entry_present_under_header(entry: str, header: str) -> bool:
            current_header = None
            for line in lines:
                if line.lstrip().startswith("#"):
                    current_header = line.strip()
                    continue
                if line_matches_entry(line, entry) and current_header == header:
                    return True
            return False

        existing = [entry for entry in desired_entries if entry_present(entry)]
        missing = [entry for entry in desired_entries if not entry_present(entry)]

        needs_section_migration = False
        if header_comment != default_header:
            for entry in desired_entries:
                if entry_present(entry) and not entry_present_under_header(entry, header_comment):
                    needs_section_migration = True
                    break

        print("\nExisting entries:")
        for entry in existing or ["None"]:
            if entry:
                print(f"  {entry}")

        print("\nMissing entries:")
        for entry in missing or ["None"]:
            if entry:
                print(f"  {entry}")

        if not missing and not needs_section_migration:
            print("\nNo modifications needed to hosts file")
            return

        effective_auto = self._auto_mode() if auto_confirm is None else bool(auto_confirm)

        if effective_auto:
            choice = "Y"
            if self._auto_mode() and auto_confirm is None:
                print("\n[AUTO_MODE] Automatically adding entries to hosts file")
            else:
                print("\nAutomatically adding entries to hosts file")
        else:
            prompt = (
                "\nAdd missing entries to hosts file? (Y/N, default: Y): "
                if missing
                else "\nUpdate hosts section header? (Y/N, default: Y): "
            )
            try:
                choice = (input(prompt).strip().upper() or "Y")
            except EOFError:
                choice = "Y"

        if choice == "S":
            choice = "Y"
            return

        if choice != "Y":
            print("No changes made to hosts file")
            return

        try:
            if needs_section_migration:
                desired_unique = list(dict.fromkeys(desired_entries))
                desired_set = set(desired_unique)

                updated = lines[:]
                i = 0
                while i < len(updated):
                    if updated[i].strip() == default_header:
                        j = i + 1
                        block_entries = []
                        while j < len(updated) and not updated[j].lstrip().startswith("#"):
                            candidate = updated[j].strip()
                            if candidate:
                                block_entries.append(candidate)
                            j += 1

                        if block_entries and all(entry in desired_set for entry in block_entries):
                            updated[i] = header_comment

                        i = j
                        continue

                    i += 1

                cleaned = []
                current_header = None
                for line in updated:
                    if line.lstrip().startswith("#"):
                        current_header = line.strip()
                        cleaned.append(line)
                        continue

                    matched = next(
                        (entry for entry in desired_unique if line_matches_entry(line, entry)),
                        None,
                    )
                    if matched and current_header != header_comment:
                        continue

                    cleaned.append(line)

                present_under_target = set()
                current_header = None
                for line in cleaned:
                    if line.lstrip().startswith("#"):
                        current_header = line.strip()
                        continue
                    if current_header == header_comment:
                        for entry in desired_unique:
                            if line_matches_entry(line, entry):
                                present_under_target.add(entry)

                entries_to_add = [e for e in desired_unique if e not in present_under_target]
                if entries_to_add:
                    header_idx = None
                    for idx in range(len(cleaned) - 1, -1, -1):
                        if cleaned[idx].strip() == header_comment:
                            header_idx = idx
                            break

                    if header_idx is None:
                        if cleaned and cleaned[-1].strip() != "":
                            cleaned.append("")
                        cleaned.append(header_comment)
                        header_idx = len(cleaned) - 1

                    insert_at = len(cleaned)
                    for idx in range(header_idx + 1, len(cleaned)):
                        if cleaned[idx].lstrip().startswith("#"):
                            insert_at = idx
                            break

                    cleaned[insert_at:insert_at] = entries_to_add

                new_content = "\n".join(cleaned).rstrip("\n") + "\n"
                try:
                    with open(hosts_path, "w") as f:
                        f.write(new_content)
                except PermissionError:
                    import tempfile
                    fd, temp_path = tempfile.mkstemp()
                    try:
                        with os.fdopen(fd, 'w') as tmp:
                            tmp.write(new_content)
                        self.run(f"cat {temp_path} | sudo tee {hosts_path} > /dev/null", check=True)
                    finally:
                        os.remove(temp_path)

                print("Hosts file updated successfully")
            else:
                new_entries = f"\n{header_comment}\n" + "\n".join(missing) + "\n"
                try:
                    with open(hosts_path, "a") as f:
                        f.write(new_entries)
                except PermissionError:
                    import tempfile
                    fd, temp_path = tempfile.mkstemp()
                    try:
                        with os.fdopen(fd, 'w') as tmp:
                            tmp.write(new_entries)
                        self.run(f"cat {temp_path} | sudo tee -a {hosts_path} > /dev/null", check=True)
                    finally:
                        os.remove(temp_path)
                print("Entries added successfully")
        except PermissionError:
            print("Permission denied writing to hosts file.")
            if self.is_wsl() and hosts_path.startswith("/mnt/"):
                print("On WSL, the Windows hosts file may require Administrator privileges.")
                print("Edit it from Windows as admin: C:\\Windows\\System32\\drivers\\etc\\hosts")
            else:
                print("Try re-running with sudo.")
        except OSError as exc:
            print(f"Could not write to hosts file: {exc}")

    def deploy_helm_release(
        self,
        release_name,
        namespace,
        values_file="values.yaml",
        cwd=None,
        wait=True,
        timeout_seconds=None,
    ):
        print("Executing helm upgrade --install...")

        if isinstance(values_file, (list, tuple)):
            values_files = [str(path) for path in values_file if str(path).strip()]
        else:
            values_files = [str(values_file)]

        if not values_files:
            values_files = ["values.yaml"]

        values_args = " ".join(
            f"-f {shlex.quote(path)}"
            for path in values_files
        )

        cmd = (
            f"helm upgrade --install {shlex.quote(str(release_name))} . "
            f"-n {shlex.quote(str(namespace))} "
            f"--create-namespace "
            f"{values_args} "
        )
        if not wait:
            cmd += "--wait=false "
        if timeout_seconds:
            cmd += f"--timeout {int(timeout_seconds)}s "

        result = self.run(cmd, check=False, cwd=cwd)

        if result is None:
            print("Helm deployment failed")
            return False

        print("Release deployed successfully")
        return True

    def wait_for_deployment_rollout(self, namespace, deployment_name, timeout_seconds=180, label=None):
        namespace = (namespace or "").strip()
        deployment_name = (deployment_name or "").strip()
        if not namespace or not deployment_name:
            return False

        timeout_seconds = max(int(timeout_seconds or 180), 1)
        rollout_label = label or f"deployment/{deployment_name}"
        print(f"Waiting for {rollout_label} rollout...")

        result = self.run(
            f"kubectl rollout status deployment/{shlex.quote(deployment_name)} "
            f"-n {shlex.quote(namespace)} --timeout={timeout_seconds}s",
            capture=True,
            check=False,
        )

        if result is None:
            print(f"Timeout waiting for {rollout_label} rollout")
            self.run(
                f"kubectl get deployment {shlex.quote(deployment_name)} -n {shlex.quote(namespace)}",
                check=False,
            )
            self.run(f"kubectl get pods -n {shlex.quote(namespace)}", check=False)
            return False

        self._print_unique_lines(result)
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

    def _is_ignored_transient_hook_pod(self, namespace, pod_name):
        if "keycloak-config-cli" in pod_name:
            return True

        if "minio-post-job" in pod_name:
            return True

        if namespace != "ingress-nginx":
            return False

        return (
            pod_name.startswith("ingress-nginx-admission-create-")
            or pod_name.startswith("ingress-nginx-admission-patch-")
        )

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
            observed_relevant_pod = False

            for line in result.splitlines():
                columns = line.split()
                name = columns[0]
                ready = columns[1] if len(columns) > 1 else ""
                status = columns[2]

                if self._is_ignored_transient_hook_pod(namespace, name):
                    continue

                if status in ["CrashLoopBackOff", "Error", "ImagePullBackOff"]:
                    print(f"\nPod in error state: {name} ({status})")
                    self.run(f"kubectl get pods -n {namespace}", check=False)
                    return False

                if status == "Completed":
                    continue

                observed_relevant_pod = True

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

            if all_ready and observed_relevant_pod:
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
                observed_relevant_pod = False
                for line in result.splitlines():
                    columns = line.split()
                    if len(columns) < 3:
                        continue
                    name = columns[0]
                    ready = columns[1] if len(columns) > 1 else ""
                    status = columns[2]

                    if self._is_ignored_transient_hook_pod(namespace, name):
                        continue

                    if status == "Completed":
                        continue

                    if status == "Terminating":
                        continue

                    observed_relevant_pod = True

                    if status != "Running":
                        all_ready = False
                        break

                    if "/" in ready:
                        ready_current, ready_total = ready.split("/", 1)
                        if ready_current != ready_total:
                            all_ready = False
                            break

                if all_ready and observed_relevant_pod:
                    print("\nPods ready:")
                    self.run(f"kubectl get pods -n {namespace}")
                    return True

            if time.time() - start > timeout:
                print("Timeout waiting for pods")
                self.run(f"kubectl get pods -n {namespace}")
                return False

            time.sleep(1)

    def port_forward_service(self, namespace, pattern, local_port, remote_port, quiet=False, wait_timeout=None):
        pod = self.get_pod_by_name(namespace, pattern)

        if not pod:
            if not quiet:
                print(f"Pod with pattern '{pattern}' not found in {namespace}")
            return False

        self.run(f"pkill -f 'kubectl port-forward {pod}'", check=False, silent=quiet)

        process = subprocess.Popen(
            ["kubectl", "port-forward", pod, "-n", namespace, f"{local_port}:{remote_port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        deadline = time.time() + max(float(wait_timeout or getattr(self.config, "TIMEOUT_PORT", 30)), 1.0)

        while time.time() <= deadline:
            if process.poll() is not None:
                if not quiet:
                    print(f"Port-forward process for '{pod}' exited before local port {local_port} became reachable")
                return False

            if self._port_is_open("127.0.0.1", local_port, connect_timeout=0.25):
                return True

            time.sleep(0.25)

        if not quiet:
            print(f"Timed out waiting for port-forward to '{pod}' on local port {local_port}")
        return False

    def stop_port_forward_service(self, namespace, pattern, quiet=False):
        pod = self.get_pod_by_name(namespace, pattern)
        if not pod:
            return False
        return self.run(f"pkill -f 'kubectl port-forward {pod}'", check=False, silent=quiet) is not None

    @staticmethod
    def _port_is_open(host, port, connect_timeout=0.5):
        connect_timeout = max(min(float(connect_timeout), 2.0), 0.1)
        try:
            with socket.create_connection((host, port), timeout=connect_timeout):
                return True
        except OSError:
            return False

    def _ensure_local_service_access(
        self,
        service_label,
        namespace,
        pattern,
        local_port,
        remote_port,
        quiet=False,
        probe_timeout=None,
        wait_timeout=None,
    ):
        full_timeout = max(int(wait_timeout or getattr(self.config, "TIMEOUT_PORT", 30)), 1)
        probe_timeout = max(min(int(probe_timeout or 3), full_timeout), 1)

        if self.wait_for_port("127.0.0.1", local_port, timeout=probe_timeout):
            if not quiet:
                print(f"{service_label} accessible")
            return True, False

        if not quiet:
            print(f"{service_label} not accessible locally after {probe_timeout}s. Creating port-forward...")

        if not self.port_forward_service(
            namespace,
            pattern,
            local_port,
            remote_port,
            quiet=quiet,
            wait_timeout=full_timeout,
        ):
            if not quiet:
                print(f"Could not establish {service_label} access")
            return False, False

        if not quiet:
            print(f"{service_label} accessible via port-forward")
        return True, True

    def wait_for_port(self, host, port, timeout=None):
        timeout = timeout or self.config.TIMEOUT_PORT
        start = time.time()

        while True:
            if self._port_is_open(host, port, connect_timeout=0.5):
                return True

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

    def wait_for_level2_service_pods(self, namespace=None, timeout=None, require_vault_ready=False):
        namespace = namespace or self.config.NS_COMMON
        timeout = timeout or self.config.TIMEOUT_POD_WAIT
        print(f"\nWaiting for core services in namespace '{namespace}'...")
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

                    if self._is_ignored_transient_hook_pod(namespace, name):
                        continue

                    # Ignore completed hook/job pods so they do not replace the
                    # long-lived service pod we actually want to observe.
                    if status == "Completed":
                        continue

                    if status in ["CrashLoopBackOff", "ImagePullBackOff"]:
                        print(f"\nPod in error state: {name} ({status})")
                        self.run(f"kubectl get pods -n {namespace}", check=False)
                        return False

                    if status == "Error" and not self._is_ignored_transient_hook_pod(namespace, name):
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

                def is_ready(pod):
                    if pod is None or pod["status"] != "Running":
                        return False
                    ready = pod.get("ready", "")
                    if "/" not in ready:
                        return False
                    ready_current, ready_total = ready.split("/", 1)
                    return ready_current == ready_total

                all_present = all(expected.values())
                all_ready = all(
                    is_ready(pod)
                    for key, pod in expected.items()
                    if key != "vault" and pod is not None
                )
                if require_vault_ready:
                    vault_running = is_ready(expected["vault"])
                else:
                    vault_running = expected["vault"] is not None and expected["vault"]["status"] == "Running"

                if all_present and all_ready and vault_running:
                    print("\nCore services detected:")
                    self.run(f"kubectl get pods -n {namespace}", check=False)
                    return True

                if transient_error:
                    print(f"Waiting past transient hook state: {transient_error}")

            if time.time() - start_time > timeout:
                print("\nTimeout waiting for core services\n")
                self.run(f"kubectl get pods -n {namespace}", check=False)
                return False

            time.sleep(1)

    def _run_vault_status_command(self, pod_name, namespace):
        """Return Vault status stdout even when Vault exits non-zero while sealed."""
        command = [
            "kubectl",
            "exec",
            str(pod_name),
            "-n",
            str(namespace),
            "--",
            "vault",
            "status",
            "-format=json",
        ]
        try:
            result = subprocess.run(command, text=True, capture_output=True)
        except Exception as exc:
            return "", f"vault status command failed: {exc}"

        stdout = (result.stdout or "").strip()
        if stdout:
            return stdout, None

        stderr = (result.stderr or "").strip()
        if stderr:
            return "", f"vault status unavailable: {stderr}"
        if result.returncode != 0:
            return "", f"vault status unavailable: exit code {result.returncode}"
        return "", "vault status unavailable"

    def _read_vault_status(self, pod_name, namespace, attempts=10, poll_interval=3):
        attempts = max(1, int(attempts or 1))
        status_error = "vault status unavailable"

        for attempt in range(attempts):
            status_json, status_error = self._run_vault_status_command(pod_name, namespace)
            if status_json:
                try:
                    return json.loads(status_json), None
                except json.JSONDecodeError as exc:
                    return None, f"invalid vault status: {exc}"

            if attempt < attempts - 1:
                time.sleep(poll_interval)

        return None, status_error

    def _vault_root_token_valid(self, pod_name, namespace, root_token):
        if not root_token:
            return False

        token_lookup = self.run_silent(
            f"kubectl exec {pod_name} -n {namespace} -- "
            f"env VAULT_TOKEN={shlex.quote(root_token)} vault token lookup -format=json"
        )
        if not token_lookup:
            return False

        try:
            payload = json.loads(token_lookup)
        except json.JSONDecodeError:
            return False

        return bool(payload.get("data"))

    def setup_vault(self, namespace=None):
        namespace = namespace or self.config.NS_COMMON
        print("\nConfiguring Vault...")

        pod_name = self.get_pod_by_name(namespace, "vault")
        if not pod_name:
            print("Could not detect Vault pod")
            return False

        if not self.wait_for_pod_running(pod_name, namespace):
            return False

        vault_file_path = self.config.vault_keys_path()
        status_data, status_error = self._read_vault_status(pod_name, namespace)
        initialized = False
        sealed = True

        if status_data:
            initialized = status_data.get("initialized", False)
            sealed = status_data.get("sealed", True)
            print(f"Vault status: initialized={initialized}, sealed={sealed}")
        elif os.path.exists(vault_file_path):
            print(f"Vault status temporarily unavailable ({status_error}); reusing existing keys")
            initialized = True
            sealed = True
        else:
            print(f"Could not get Vault status: {status_error}")
            return False

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

        if initialized:
            ensure_vault_keys_file = getattr(self.config, "ensure_vault_keys_file", None)
            if callable(ensure_vault_keys_file):
                vault_file_path = ensure_vault_keys_file()

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

        if not self._vault_root_token_valid(pod_name, namespace, root_token):
            print(
                "Error: local Vault root token is not valid for the running Vault. "
                "The Vault persistent state and deployers/shared/common/init-keys-vault.json "
                "are out of sync. Recreate Level 2 common services or restore the current "
                "Vault root token before continuing."
            )
            return False

        print("Checking KV engine...")
        secrets_list = self.run_silent(
            f"kubectl exec {pod_name} -n {namespace} -- "
            f"env VAULT_TOKEN={shlex.quote(root_token)} vault secrets list -format=json"
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
                f"env VAULT_TOKEN={shlex.quote(root_token)} vault secrets enable -path=secret kv-v2"
            )
            if enable_kv:
                print("KV v2 engine enabled")
            else:
                print("Warning: KV v2 engine not enabled, continuing")
        else:
            print("KV v2 engine already enabled")

        final_status, final_status_error = self._read_vault_status(pod_name, namespace)
        if not final_status:
            print(f"Error: Could not get final Vault status: {final_status_error}")
            return False

        try:
            initialized = final_status.get("initialized", False)
            sealed = final_status.get("sealed", True)
            print("\nVault final status:")
            print(f"  Initialized: {initialized}")
            print(f"  Sealed: {sealed}\n")
            return initialized and not sealed
        except Exception as e:
            print(f"Error parsing final Vault status: {e}")
            return False

    def ensure_vault_unsealed(self, timeout=30, poll_interval=2):
        print("Checking Vault state...")
        pod = self.get_pod_by_name(self.config.NS_COMMON, "vault")

        if not pod:
            print("Vault pod not found")
            return False

        data, status_error = self._read_vault_status(pod, self.config.NS_COMMON)
        if not data:
            ensure_vault_keys_file = getattr(self.config, "ensure_vault_keys_file", None)
            vault_keys_path = ensure_vault_keys_file() if callable(ensure_vault_keys_file) else self.config.vault_keys_path()
            if not os.path.exists(vault_keys_path):
                print(f"Could not get Vault status: {status_error}")
                return False
            print(f"Vault status temporarily unavailable ({status_error}); trying existing unseal key")
            data = {"initialized": True, "sealed": True}

        if not data.get("initialized"):
            print("Vault not initialized")
            return False

        if data.get("sealed"):
            print("Vault sealed. Running unseal...")
            ensure_vault_keys_file = getattr(self.config, "ensure_vault_keys_file", None)
            vault_keys_path = ensure_vault_keys_file() if callable(ensure_vault_keys_file) else self.config.vault_keys_path()
            with open(vault_keys_path) as f:
                keys = json.load(f)
            unseal_key = keys["unseal_keys_hex"][0]
            unseal_result = self.run(
                f"kubectl exec {pod} -n {self.config.NS_COMMON} -- vault operator unseal {unseal_key}",
                check=False,
            )
            if unseal_result is None:
                print("Vault unseal command failed")
                return False
        else:
            print("Vault already unsealed")

        deadline = time.time() + max(int(timeout), 1)
        while time.time() <= deadline:
            final_data, _ = self._read_vault_status(pod, self.config.NS_COMMON)
            if final_data and final_data.get("initialized") and not final_data.get("sealed"):
                print("Vault ready and unsealed")
                return True
            time.sleep(max(poll_interval, 1))

        print("Vault did not become ready and unsealed in time")
        return False

    def sync_vault_token_to_deployer_config(self):
        ensure_vault_keys_file = getattr(self.config, "ensure_vault_keys_file", None)
        vault_json_path = ensure_vault_keys_file() if callable(ensure_vault_keys_file) else self.config.vault_keys_path()
        config_path = self._vault_token_deployer_config_path()

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

        print("Token obtained from Vault keys artifact")

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

    def _vault_token_deployer_config_path(self):
        infrastructure_config_path = getattr(self.config, "infrastructure_deployer_config_path", None)
        if callable(infrastructure_config_path):
            candidate = infrastructure_config_path()
            if os.path.exists(candidate):
                return candidate
        return self.config.deployer_config_path()

    def show_correspondence_table(self, values, config):
        rows = []

        def status(expected, current):
            return "OK" if expected == current else "DIFF"

        def add_row_value(logical_var, values_path, expected_value, current_value):
            rows.append([
                logical_var,
                values_path,
                expected_value,
                current_value,
                status(expected_value, current_value)
            ])

        def add_row(logical_var, values_path, config_var, current_value):
            add_row_value(logical_var, values_path, config.get(config_var), current_value)

        add_row("PG_PASSWORD", "postgresql.auth.postgresPassword", "PG_PASSWORD", values["postgresql"]["auth"]["postgresPassword"])
        add_row("PG_PASSWORD", "keycloak.externalDatabase.password", "PG_PASSWORD", values["keycloak"]["externalDatabase"]["password"])
        add_row("KC_USER", "keycloak.auth.adminUser", "KC_USER", values["keycloak"]["auth"]["adminUser"])
        add_row("KC_PASSWORD", "keycloak.auth.adminPassword", "KC_PASSWORD", values["keycloak"]["auth"]["adminPassword"])
        minio_user, minio_password = self._minio_admin_credentials(config)
        minio_values = values.get("minio", {})
        add_row_value("MINIO_USER", "minio.rootUser", minio_user, minio_values.get("rootUser"))
        add_row_value("MINIO_PASSWORD", "minio.rootPassword", minio_password, minio_values.get("rootPassword"))
        domain_base = config.get("DOMAIN_BASE")
        if domain_base:
            add_row_value("DOMAIN_BASE", "keycloak.ingress.hostname", f"auth.{domain_base}", values["keycloak"]["ingress"]["hostname"])
            add_row_value("DOMAIN_BASE", "keycloak.adminIngress.hostname", f"admin.auth.{domain_base}", values["keycloak"]["adminIngress"]["hostname"])
            add_row_value("DOMAIN_BASE", "minio.ingress.hosts", f"minio.{domain_base}", values.get("minio", {}).get("ingress", {}).get("hosts", [""])[0] if values.get("minio", {}).get("ingress", {}).get("hosts") else "")
            add_row_value("DOMAIN_BASE", "minio.consoleIngress.hosts", f"console.minio-s3.{domain_base}", values.get("minio", {}).get("consoleIngress", {}).get("hosts", [""])[0] if values.get("minio", {}).get("consoleIngress", {}).get("hosts") else "")


        for item in values["keycloak"]["keycloakConfigCli"]["extraEnv"]:
            if item["name"] == "KEYCLOAK_USER":
                add_row("KC_USER", "keycloakConfigCli.KEYCLOAK_USER", "KC_USER", item["value"])
            if item["name"] == "KEYCLOAK_PASSWORD":
                add_row("KC_PASSWORD", "keycloakConfigCli.KEYCLOAK_PASSWORD", "KC_PASSWORD", item["value"])

        print("\nConfiguration synchronization: deployer.config -> common/values.yaml\n")
        print(tabulate(rows, headers=["DEPLOYER.CONFIG", "COMMON/VALUES.YAML", "EXPECTED", "FOUND", "STATUS"], tablefmt="grid"))
        print()
        return any(row[4] == "DIFF" for row in rows)

    def apply_sync(self, values, config):
        pg_password = config.get("PG_PASSWORD")
        kc_user = config.get("KC_USER")
        kc_password = config.get("KC_PASSWORD")
        minio_user, minio_password = self._minio_admin_credentials(config)

        values["postgresql"]["auth"]["postgresPassword"] = pg_password
        values["postgresql"]["auth"]["password"] = pg_password
        values["keycloak"]["externalDatabase"]["password"] = pg_password
        values["keycloak"]["auth"]["adminUser"] = kc_user
        values["keycloak"]["auth"]["adminPassword"] = kc_password
        values.setdefault("minio", {})
        if minio_user:
            values["minio"]["rootUser"] = minio_user
        if minio_password:
            values["minio"]["rootPassword"] = minio_password

        domain_base = config.get("DOMAIN_BASE")
        if domain_base:
            values["keycloak"]["ingress"]["hostname"] = f"auth.{domain_base}"
            values["keycloak"]["adminIngress"]["hostname"] = f"admin.auth.{domain_base}"
            
            master_json_str = values["keycloak"]["keycloakConfigCli"]["configuration"]["master.json"]
            try:
                import json
                master_json_data = json.loads(master_json_str)
                if "attributes" not in master_json_data:
                    master_json_data["attributes"] = {}
                master_json_data["attributes"]["frontendUrl"] = f"http://admin.auth.{domain_base}"
                values["keycloak"]["keycloakConfigCli"]["configuration"]["master.json"] = json.dumps(master_json_data, indent=2)
            except Exception as e:
                print(f"Warning: Could not update frontendUrl in master.json: {e}")

            if "minio" in values and "ingress" in values["minio"]:
                values["minio"]["ingress"]["hosts"] = [f"minio.{domain_base}"]
            if "minio" in values and "consoleIngress" in values["minio"]:
                values["minio"]["consoleIngress"]["hosts"] = [f"console.minio-s3.{domain_base}"]

            # Also update TLS hosts if they exist
            if "extraTls" in values["keycloak"]["ingress"]:
                for tls in values["keycloak"]["ingress"]["extraTls"]:
                    tls["hosts"] = [f"auth.{domain_base}"]
            if "extraTls" in values["keycloak"]["adminIngress"]:
                for tls in values["keycloak"]["adminIngress"]["extraTls"]:
                    tls["hosts"] = [f"admin.auth.{domain_base}"]


        for item in values["keycloak"]["keycloakConfigCli"]["extraEnv"]:
            if item["name"] == "KEYCLOAK_USER":
                item["value"] = kc_user
            if item["name"] == "KEYCLOAK_PASSWORD":
                item["value"] = kc_password

        return values

    def sync_common_values(self):
        ensure_values_file = getattr(self.config, "ensure_common_values_file", None)
        values_path = ensure_values_file() if callable(ensure_values_file) else self.config.values_path()
        config_path = self.config.deployer_config_path()
        ds_name = self._dataspace_name()

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

    def _secret_value(self, namespace, secret_name, key):
        value = self.run_silent(
            f"kubectl get secret {secret_name} -n {namespace} "
            f"-o jsonpath='{{.data.{key}}}'"
        )
        if not value:
            return None

        decoded = self.run_silent(f"printf '%s' '{value}' | base64 -d")
        return decoded if decoded is not None else None

    def _common_services_release_exists(self):
        result = self.run_silent(
            f"helm status {self.config.helm_release_common()} -n {self.config.NS_COMMON}"
        )
        return result is not None

    def _common_services_release_recoverable_after_helm_failure(self):
        if not self._common_services_release_exists():
            return False

        print(
            "Helm reported a post-install failure, but the common services release exists. "
            "Continuing with framework-level checks."
        )
        return True

    def _common_services_config_drift(self):
        if not self._common_services_release_exists():
            return []

        config = self.config_adapter.load_deployer_config()
        expected_pg_password = config.get("PG_PASSWORD")
        expected_kc_password = config.get("KC_PASSWORD")
        expected_minio_user, expected_minio_password = self._minio_admin_credentials(config)

        drift = []

        actual_pg_password = self._secret_value(
            self.config.NS_COMMON, "common-srvs-postgresql", "postgres-password"
        )
        if actual_pg_password and expected_pg_password and actual_pg_password != expected_pg_password:
            drift.append("PostgreSQL secret does not match PG_PASSWORD from deployer.config")

        actual_kc_password = self._secret_value(
            self.config.NS_COMMON, "common-srvs-keycloak", "admin-password"
        )
        if actual_kc_password and expected_kc_password and actual_kc_password != expected_kc_password:
            drift.append("Keycloak secret does not match KC_PASSWORD from deployer.config")

        actual_minio_user = self._secret_value(
            self.config.NS_COMMON, "common-srvs-minio", "rootUser"
        )
        if actual_minio_user and expected_minio_user and actual_minio_user != expected_minio_user:
            drift.append("MinIO secret does not match MINIO_USER from deployer.config")

        actual_minio_password = self._secret_value(
            self.config.NS_COMMON, "common-srvs-minio", "rootPassword"
        )
        if actual_minio_password and expected_minio_password and actual_minio_password != expected_minio_password:
            drift.append("MinIO secret does not match MINIO_PASSWORD from deployer.config")

        return drift

    def reconcile_common_services_source_of_truth(self):
        drift = self._common_services_config_drift()
        if not drift:
            return

        print("\nDetected configuration drift in deployed common services:")
        for item in drift:
            print(f"- {item}")

        print("\nRecreating common services so deployer.config becomes the effective source of truth...")
        self.stop_port_forward_service(self.config.NS_COMMON, "postgresql", quiet=True)
        self.stop_port_forward_service(self.config.NS_COMMON, "vault", quiet=True)
        self.stop_port_forward_service(self.config.NS_COMMON, "minio", quiet=True)

        self.run(
            f"helm uninstall {self.config.helm_release_common()} -n {self.config.NS_COMMON}",
            check=False,
        )
        self.run(
            f"kubectl delete pvc --all -n {self.config.NS_COMMON}",
            check=False,
        )
        self.run(
            f"kubectl delete secret common-srvs-postgresql common-srvs-keycloak common-srvs-minio -n {self.config.NS_COMMON}",
            check=False,
        )
        time.sleep(5)

    def ensure_local_infra_access(self):
        print("\nVerifying local access to PostgreSQL, Vault and MinIO...")
        full_timeout = max(int(getattr(self.config, "TIMEOUT_PORT", 30)), 1)
        probe_timeout = max(min(3, full_timeout), 1)

        postgres_ok, _ = self._ensure_local_service_access(
            "PostgreSQL",
            self.config.NS_COMMON,
            "postgresql",
            self.config.PORT_POSTGRES,
            5432,
            probe_timeout=probe_timeout,
            wait_timeout=full_timeout,
        )
        if not postgres_ok:
            return False

        vault_ok, _ = self._ensure_local_service_access(
            "Vault",
            self.config.NS_COMMON,
            "vault",
            self.config.PORT_VAULT,
            8200,
            probe_timeout=probe_timeout,
            wait_timeout=full_timeout,
        )
        if not vault_ok:
            return False

        minio_ok, _ = self._ensure_local_service_access(
            "MinIO",
            self.config.NS_COMMON,
            "minio",
            getattr(self.config, "PORT_MINIO", 9000),
            9000,
            probe_timeout=probe_timeout,
            wait_timeout=full_timeout,
        )
        if not minio_ok:
            return False

        print("Local infrastructure OK\n")
        return True

    def wait_for_registration_service_schema(self, timeout=None, poll_interval=3, quiet=False):
        timeout = timeout or self.config.TIMEOUT_POD_WAIT
        if not quiet:
            print("\nWaiting for registration-service schema to be ready...")
        start = time.time()
        next_progress = start + max(float(poll_interval) * 5, 15)
        pg_host, pg_user, pg_password = self.config_adapter.get_pg_credentials()
        registration_db = self.config.registration_db_name()
        sql = "SELECT to_regclass('public.edc_participant');"

        while time.time() - start <= timeout:
            result = self.run_silent(
                f"PGPASSWORD={pg_password} psql -h {pg_host} -U {pg_user} "
                f"-d {registration_db} -t -A -c \"{sql}\""
            )

            if result and result.strip() == "edc_participant":
                if not quiet:
                    print("registration-service schema ready: public.edc_participant exists")
                return True

            if not quiet and time.time() >= next_progress:
                elapsed = int(time.time() - start)
                print(f"registration-service schema not ready yet ({elapsed}s elapsed)...")
                next_progress = time.time() + max(float(poll_interval) * 5, 15)

            time.sleep(poll_interval)

        if not quiet:
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
        next_progress = None

        try:
            local_timeout = max(int(getattr(self.config, "TIMEOUT_PORT", 30)), 1)
            actuator_ok, created_port_forward = self._ensure_local_service_access(
                "registration-service actuator",
                namespace,
                "registration-service",
                local_port,
                8080,
                quiet=True,
                probe_timeout=min(2, local_timeout),
                wait_timeout=local_timeout,
            )
            if not actuator_ok:
                self._last_registration_service_liquibase_issue = (
                    "temporary port-forward to registration-service actuator could not be established"
                )
                return False

            endpoint = f"http://127.0.0.1:{local_port}/api/actuator/liquibase"
            start = time.time()
            next_progress = start + max(float(poll_interval) * 5, 15)
            print("\nWaiting for registration-service Liquibase actuator...")

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

                if time.time() >= next_progress:
                    elapsed = int(time.time() - start)
                    detail = f" Last issue: {last_issue}" if last_issue else ""
                    print(f"registration-service Liquibase actuator not ready yet ({elapsed}s elapsed).{detail}")
                    next_progress = time.time() + max(float(poll_interval) * 5, 15)

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

    def wait_for_namespace_stability(self, namespace, duration=15, poll_interval=3, timeout=None):
        """Observe namespace health during a stability window."""
        print(f"\nObserving namespace '{namespace}' stability for {duration}s...")
        last_issue = None
        stable_since = None
        timeout = max(timeout or getattr(self.config, "TIMEOUT_NAMESPACE", 90), duration * 3)
        deadline = time.time() + timeout

        while time.time() < deadline:
            snapshot = self._pod_snapshot(namespace)
            if not snapshot:
                last_issue = f"no pods found in namespace '{namespace}'"
                stable_since = None
                time.sleep(poll_interval)
                continue

            unhealthy = []
            relevant_pods = []
            for pod in snapshot:
                # Ignore known transient hook jobs so the stability window
                # tracks the long-lived service pods instead.
                if self._is_ignored_transient_hook_pod(namespace, pod["name"]):
                    continue

                relevant_pods.append(pod)

            if not relevant_pods:
                last_issue = f"no relevant pods found in namespace '{namespace}'"
                stable_since = None
                time.sleep(poll_interval)
                continue

            for pod in relevant_pods:
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
        ingress_ready_timeout = max(int(getattr(self.config, "TIMEOUT_POD_WAIT", 120)), 300)
        ingress_stability_timeout = max(int(getattr(self.config, "TIMEOUT_NAMESPACE", 90)), 180)

        nodes = self.run_silent("kubectl get nodes --no-headers")
        if not nodes or " Ready " not in f" {nodes} ":
            return False, "kubectl does not report a Ready node"

        if not self.wait_for_pods("ingress-nginx", timeout=ingress_ready_timeout):
            return False, "ingress-nginx pods did not become ready"

        if not self.wait_for_namespace_stability(
            "ingress-nginx",
            duration=10,
            poll_interval=3,
            timeout=ingress_stability_timeout,
        ):
            return False, "ingress-nginx namespace did not remain stable"

        return True, None

    def verify_common_services_ready_for_level3(self):
        """Ensure Level 2 leaves common services stable enough for Level 3."""
        common_ready_timeout = max(int(getattr(self.config, "TIMEOUT_POD_WAIT", 120)), 300)
        common_stability_timeout = max(int(getattr(self.config, "TIMEOUT_NAMESPACE", 90)), 180)
        if not self.wait_for_level2_service_pods(
            self.config.NS_COMMON,
            timeout=common_ready_timeout,
            require_vault_ready=True,
        ):
            return False, "common services pods did not become ready"

        if not self.wait_for_namespace_stability(
            self.config.NS_COMMON,
            duration=12,
            poll_interval=3,
            timeout=common_stability_timeout,
        ):
            return False, "common services namespace did not remain stable"

        if not self.ensure_vault_unsealed():
            return False, "Vault is not initialized/unsealed"

        return True, None

    def verify_dataspace_ready_for_level4(self):
        """Ensure Level 3 leaves dataspace services stable enough for Level 4."""
        self._last_registration_service_liquibase_issue = None
        if not self.wait_for_namespace_stability(self.config.namespace_demo(), duration=12, poll_interval=3):
            return False, "dataspace namespace did not remain stable"

        quick_schema_timeout = 15
        final_schema_timeout = 105

        if self.wait_for_registration_service_schema(
            timeout=quick_schema_timeout,
            poll_interval=3,
            quiet=True,
        ):
            print("registration-service schema ready")
            return True, None

        print("registration-service schema not ready yet. Checking Liquibase actuator...")
        self.wait_for_registration_service_liquibase(timeout=60, poll_interval=3)

        if not self.wait_for_registration_service_schema(timeout=final_schema_timeout, poll_interval=3):
            if self._last_registration_service_liquibase_issue:
                print(
                    "Registration-service Liquibase check was inconclusive: "
                    f"{self._last_registration_service_liquibase_issue}"
                )
            return False, "registration-service schema was not ready"

        return True, None

    def _cluster_type(self):
        config = self.config_adapter.load_deployer_config()
        return str(config.get("CLUSTER_TYPE") or self.config.CLUSTER_TYPE).strip().lower()

    def _setup_cluster_minikube(self):
        if not self.ensure_wsl_docker_config():
            self._fail("Could not adjust WSL Docker configuration safely")

        print("Checking Minikube installation...")
        if self.run("which minikube", capture=True) is None:
            print("Installing Minikube...")
            self.run("curl -LO https://github.com/kubernetes/minikube/releases/latest/download/minikube-linux-amd64")
            self.run("sudo install minikube-linux-amd64 /usr/local/bin/minikube")
            self.run("rm -f minikube-linux-amd64")

        self.run("minikube version")

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
        if self.run_silent("minikube addons enable ingress") is None:
            print(
                "Warning: minikube reported a transient ingress addon enable failure; "
                "verifying ingress controller readiness directly."
            )

    def _setup_cluster_k3s(self):
        if self.run("which minikube", capture=True, check=False) is not None:
            print("Stopping and removing minikube before k3s setup...")
            self.run("minikube stop", check=False)
            self.run("minikube delete", check=False)

        print("Checking k3s installation...")
        if self.run("which k3s", capture=True) is None:
            print("Installing k3s (Traefik disabled, nginx-ingress will be installed via Helm)...")
            self.run("curl -sfL https://get.k3s.io | sh -s - --disable=traefik")
            # Make kubeconfig accessible to current user
            self.run("sudo chmod 644 /etc/rancher/k3s/k3s.yaml", check=False)
            kubeconfig = "/etc/rancher/k3s/k3s.yaml"
            if os.path.exists(kubeconfig):
                os.environ.setdefault("KUBECONFIG", kubeconfig)
        else:
            print("k3s already installed")
            self.run("sudo systemctl start k3s", check=False)

        if not self.wait_for_kubernetes_ready():
            self._fail("k3s cluster failed to initialize", root_cause="Kubernetes node did not become Ready")

        print("\nInstalling nginx-ingress via Helm...\n")
        self.run("helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx", check=False)
        self.run("helm repo update")
        ingress_installed = self.run_silent("helm status ingress-nginx -n ingress-nginx")
        if not ingress_installed:
            self.run(
                "helm install ingress-nginx ingress-nginx/ingress-nginx "
                "-n ingress-nginx --create-namespace "
                "--set controller.watchIngressWithoutClass=true "
                "--wait --timeout 120s"
            )
        else:
            print("nginx-ingress already installed, skipping")

        self._patch_ingress_nginx_allow_snippets()

    def _patch_ingress_nginx_allow_snippets(self):
        """Allow nginx-ingress configuration-snippet annotations (required for cookie flag patching)."""
        print("\nPatching ingress-nginx configmap to allow snippet annotations...")
        patch = json.dumps({
            "data": {
                "allow-snippet-annotations": "true",
                "annotations-risk-level": "Critical",
            }
        })
        self.run(
            f"kubectl patch configmap ingress-nginx-controller -n ingress-nginx "
            f"--type merge -p {shlex.quote(patch)}",
            check=False,
        )

    def _patch_keycloak_ingress_http_cookie_fix(self, namespace: str):
        """Strip Secure flag from Keycloak AUTH_SESSION_ID cookie so Chromium sends it over HTTP.

        Keycloak 24+ sets AUTH_SESSION_ID with Secure;SameSite=None unconditionally.
        nginx proxy_cookie_flags rewrites it to nosecure;SameSite=Lax before reaching the browser.
        Only applied in DEV/HTTP environments where the cluster serves HTTP.
        """
        snippet = (
            "proxy_set_header X-Forwarded-Proto http; "
            "proxy_set_header X-Forwarded-Ssl off; "
            "proxy_cookie_flags AUTH_SESSION_ID nosecure samesite=lax;"
        )
        for ingress_name in ("common-srvs-keycloak", "common-srvs-keycloak-admin"):
            self.run(
                f"kubectl annotate ingress {shlex.quote(ingress_name)} -n {shlex.quote(namespace)} "
                f"--overwrite "
                f"nginx.ingress.kubernetes.io/configuration-snippet={shlex.quote(snippet)} "
                f"nginx.ingress.kubernetes.io/ssl-redirect=false",
                check=False,
            )
        print("  Keycloak ingress cookie annotations applied.")

    def setup_cluster(self):
        self.announce_level(1, "CLUSTER SETUP")
        self.ensure_unix_environment()

        print("\nChecking Helm installation...")
        if self.run("which helm", capture=True) is None:
            self.run("sudo snap install helm --classic", check=False)
        self.run("helm version")

        cluster_type = self._cluster_type()
        print(f"\nCluster type: {cluster_type}")

        if cluster_type == "k3s":
            self._setup_cluster_k3s()
        else:
            self._setup_cluster_minikube()

        self.run("kubectl get pods -n ingress-nginx", check=False)
        self.patch_ingress_external_ip()
        cluster_ready, root_cause = self.verify_cluster_ready_for_level2()
        if not cluster_ready:
            self._fail("Level 1 did not leave the cluster ready for Level 2", root_cause=root_cause)
        self.complete_level(1)


    def deploy_infrastructure(self):
        self.announce_level(2, "DEPLOY COMMON SERVICES")

        if not self.ensure_wsl_docker_config():
            self._fail("Could not adjust WSL Docker configuration safely")

        repo_dir = self.config.repo_dir()
        common_dir = self.config.common_dir()
        values_path = self.config.values_path()

        if not os.path.isdir(repo_dir):
            self._fail(
                "Missing INESData deployer artifacts",
                root_cause=(
                    f"Expected {repo_dir}. The framework no longer clones "
                    "the legacy deployment repository automatically; deployers/inesdata must be part "
                    "of this repository checkout."
                ),
            )

        print("INESData deployer artifacts found")

        self.config_adapter.copy_local_deployer_config()

        print("\nSynchronizing configuration...\n")
        self.sync_common_values()
        self.reconcile_common_services_source_of_truth()

        print("\nConfiguring hosts...")
        print("[Networking] Configuring hosts for internal VM access...")
        print(f"Using cluster IP {self.config.get_cluster_ip()} for local resolution.")
        hosts_entries = self.config_adapter.generate_hosts(self._dataspace_name())
        self.manage_hosts_entries(hosts_entries)

        self.add_helm_repos()

        print("\nBuilding Helm dependencies...")
        self.run("helm dependency build", cwd=common_dir)

        print("\nDeploying common services...")
        common_release_exists = self._common_services_release_exists()
        common_services_deployed = self.deploy_helm_release(
            self.config.helm_release_common(),
            self.config.NS_COMMON,
            values_path,
            cwd=common_dir,
            wait=False,
            timeout_seconds=None if common_release_exists else 45,
        )
        if not common_services_deployed and not self._common_services_release_recoverable_after_helm_failure():
            self._fail("Error deploying common services")

        # In DEV (HTTP) mode, strip Secure flag from Keycloak AUTH_SESSION_ID cookie so
        # Chromium-based browsers send it over plain HTTP (Keycloak 24+ sets Secure unconditionally).
        deployer_config = self.config_adapter.load_deployer_config() or {}
        environment = str(deployer_config.get("ENVIRONMENT") or "DEV").strip().upper()
        if environment != "PRO":
            self._patch_keycloak_ingress_http_cookie_fix(self.config.NS_COMMON)

        # Keycloak can take noticeably longer than PostgreSQL/MinIO on fresh
        # installs, so give the pre-Vault readiness check the same minimum
        # budget we already use for the final Level 2 verification.
        pre_vault_timeout = max(int(getattr(self.config, "TIMEOUT_POD_WAIT", 120)), 180)
        if not self.wait_for_level2_service_pods(self.config.NS_COMMON, timeout=pre_vault_timeout):
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

        self.complete_level(2)

    def describe(self) -> str:
        return "INESDataInfrastructureAdapter contains infrastructure logic for INESData."
