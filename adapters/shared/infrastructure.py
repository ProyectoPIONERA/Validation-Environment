"""Shared foundation infrastructure helpers reused by multiple adapters."""

import subprocess

from adapters.inesdata.infrastructure import INESDataInfrastructureAdapter
from deployers.shared.lib.topology import LOCAL_TOPOLOGY, VM_SINGLE_TOPOLOGY, VM_DISTRIBUTED_TOPOLOGY, normalize_topology


class SharedFoundationInfrastructureAdapter(INESDataInfrastructureAdapter):
    """Neutral facade for shared Level 1-2 foundation logic."""

    def setup_cluster_preflight(self, topology=LOCAL_TOPOLOGY):
        """Prepare and validate the cluster required by VM-based execution."""
        normalized_topology = normalize_topology(topology)
        if normalized_topology == LOCAL_TOPOLOGY:
            return self.setup_cluster()
        if normalized_topology == VM_DISTRIBUTED_TOPOLOGY:
            return self._setup_cluster_preflight_vm_distributed()
        if normalized_topology != VM_SINGLE_TOPOLOGY:
            raise RuntimeError(
                f"Level 1 preflight is not implemented for topology '{normalized_topology}' yet."
            )

        cluster_runtime = self._cluster_runtime_config()
        cluster_type = cluster_runtime.get("cluster_type", "minikube")
        print(
            "Topology 'vm-single' uses a Kubernetes cluster managed on the VM.\n"
            f"Level 1 will prepare the managed {cluster_type} cluster to keep runs reproducible."
        )
        self.setup_cluster()
        print("Managed vm-single cluster recreated. Running cluster preflight checks.")

        checks = []

        def run_check(
            command,
            label,
            *,
            require_output=False,
            failure_message=None,
            validator=None,
            detail_override=None,
        ):
            result = self.run(command, capture=True, check=False)
            detail = str(result or "").strip()
            ok = result is not None and (not require_output or bool(detail))
            if ok and callable(validator):
                ok = bool(validator(detail))
            checks.append(
                {
                    "label": label,
                    "command": command,
                    "status": "passed" if ok else "failed",
                    "detail": detail_override if detail_override is not None else detail,
                }
            )
            if not ok:
                self._fail(failure_message or f"Level 1 vm-single preflight failed during {label}")
            return detail

        print("Checking kubectl...")
        run_check("which kubectl", "kubectl binary", require_output=True, failure_message="kubectl is not installed")
        run_check(
            "kubectl version --client=true",
            "kubectl client version",
            require_output=True,
            failure_message="kubectl client is not available",
        )

        print("\nChecking Helm...")
        run_check("which helm", "helm binary", require_output=True, failure_message="Helm is not installed")
        run_check(
            "helm version --short",
            "helm version",
            require_output=True,
            failure_message="Helm is not available",
        )

        print("\nChecking cluster access...")
        current_context = run_check(
            "kubectl config current-context",
            "kubectl current context",
            require_output=True,
            failure_message="kubectl has no active context configured",
        )
        run_check(
            "kubectl cluster-info",
            "cluster info",
            require_output=True,
            failure_message="kubectl cannot reach the target cluster",
        )
        run_check(
            "kubectl get nodes --no-headers",
            "cluster nodes",
            require_output=True,
            failure_message="the target cluster returned no schedulable nodes",
        )

        print("\nChecking ingress and storage primitives...")
        run_check(
            "kubectl get ingressclass -o name",
            "ingress classes",
            require_output=True,
            failure_message="no IngressClass is available in the target cluster",
        )
        run_check(
            "kubectl get storageclass -o name",
            "storage classes",
            require_output=True,
            failure_message="no StorageClass is available in the target cluster",
        )

        print("\nChecking namespace permissions...")
        run_check(
            "kubectl auth can-i create namespace",
            "create namespace permission",
            require_output=True,
            failure_message="the active kubectl identity cannot create namespaces",
            validator=lambda detail: detail.strip().lower() in {"yes", "true"},
            detail_override="yes",
        )

        self.complete_level(1)
        return {
            "status": "ready",
            "mode": "managed-recreate",
            "topology": normalized_topology,
            "cluster_runtime": cluster_type,
            "current_context": current_context,
            "cluster_creation": "recreated",
            "checks": checks,
        }

    def deploy_infrastructure_for_topology(self, topology=LOCAL_TOPOLOGY):
        """Run Level 2 foundation deployment using the safest topology-aware path."""
        normalized_topology = normalize_topology(topology)
        if normalized_topology == LOCAL_TOPOLOGY:
            return self.deploy_infrastructure()
        if normalized_topology not in (VM_SINGLE_TOPOLOGY, VM_DISTRIBUTED_TOPOLOGY):
            raise RuntimeError(
                f"Level 2 deploy_infrastructure_for_topology() is not implemented for topology "
                f"'{normalized_topology}' yet."
            )

        if normalized_topology == VM_DISTRIBUTED_TOPOLOGY:
            deployer_config = self.config_adapter.load_deployer_config() or {}
            ingress_ip = deployer_config.get("INGRESS_EXTERNAL_IP") or deployer_config.get("VM_COMMON_IP") or None
            result = self._deploy_infrastructure_runtime(ingress_ip=ingress_ip)
            self._sync_nginx_stream_proxy_vm_distributed()
            self._sync_nginx_http_proxy_vm_distributed()
            return result

        return self._deploy_infrastructure_runtime(
            skip_hosts=True,
            host_sync_message=(
                f"Skipping client-side hosts synchronization for topology '{normalized_topology}'. "
                "Use the dedicated hosts command if you need local name resolution."
            ),
        )

    def _setup_cluster_preflight_vm_distributed(self):
        """Level 1 preflight for vm-distributed: verify all 3 cluster kubeconfigs are reachable."""
        import shlex as _shlex
        config = self._cluster_runtime_config()
        checks = []

        kubeconfigs = {
            "common (pioneer40)": config.get("k3s_kubeconfig") or "",
            "provider (pioneer20)": config.get("K3S_KUBECONFIG_PROVIDER") or "",
            "consumer (pioneer3)": config.get("K3S_KUBECONFIG_CONSUMER") or "",
        }

        # Also try loading from deployer config directly
        deployer_config = {}
        try:
            deployer_config = self.config_adapter.load_deployer_config() or {}
        except Exception:
            pass
        if not kubeconfigs["provider (pioneer20)"]:
            kubeconfigs["provider (pioneer20)"] = deployer_config.get("K3S_KUBECONFIG_PROVIDER") or ""
        if not kubeconfigs["consumer (pioneer3)"]:
            kubeconfigs["consumer (pioneer3)"] = deployer_config.get("K3S_KUBECONFIG_CONSUMER") or ""

        print("Topology 'vm-distributed' uses 3 separate k3s clusters.")
        print("Level 1 will verify connectivity to all cluster nodes.\n")

        all_ok = True
        for label, kubeconfig in kubeconfigs.items():
            if not kubeconfig:
                print(f"[SKIP] {label}: kubeconfig not configured")
                checks.append({"label": label, "status": "skipped", "detail": "kubeconfig not set"})
                continue
            kc_env = f"KUBECONFIG={_shlex.quote(kubeconfig)} "
            result = self.run(f"{kc_env}kubectl get nodes --no-headers", capture=True, check=False)
            ok = result is not None and bool(str(result).strip())
            status = "passed" if ok else "failed"
            checks.append({"label": label, "kubeconfig": kubeconfig, "status": status, "detail": str(result or "").strip()[:200]})
            if ok:
                print(f"[OK]   {label}: {str(result or '').strip().splitlines()[0]}")
            else:
                print(f"[FAIL] {label}: cannot reach cluster — check kubeconfig path and cluster status")
                all_ok = False

        if not all_ok:
            self._fail("One or more vm-distributed clusters are unreachable. Fix kubeconfig paths before proceeding.")

        self._ensure_k3s_kubelet_config_vm_distributed(deployer_config)

        self.complete_level(1)
        return {"status": "ready", "topology": VM_DISTRIBUTED_TOPOLOGY, "checks": checks}

    def _ensure_k3s_kubelet_config_vm_distributed(self, deployer_config=None):
        """Write kubelet-arg config to /etc/rancher/k3s/config.yaml on all vm-distributed nodes."""
        K3S_CONFIG = "/etc/rancher/k3s/config.yaml"
        KUBELET_CONFIG = (
            "kubelet-arg:\n"
            '  - "eviction-hard=nodefs.available<500Mi,imagefs.available<500Mi,nodefs.inodesFree<5%"\n'
            '  - "image-gc-high-threshold=95"\n'
            '  - "image-gc-low-threshold=90"\n'
        )
        config = deployer_config or {}
        remote_ips = []
        for key in ("VM_PROVIDER_IP", "VM_CONSUMER_IP"):
            ip = str(config.get(key) or "").strip()
            if ip:
                remote_ips.append(ip)

        print("Ensuring k3s kubelet config on all vm-distributed nodes...")

        # Local (common VM)
        try:
            proc = subprocess.run(
                ["sudo", "tee", K3S_CONFIG],
                input=KUBELET_CONFIG, text=True, capture_output=True,
            )
            if proc.returncode == 0:
                print(f"[OK]   local: wrote {K3S_CONFIG}")
            else:
                print(f"[WARN] local: could not write {K3S_CONFIG}: {proc.stderr.strip()}")
        except Exception as exc:
            print(f"[WARN] local: kubelet config write skipped: {exc}")

        # Remote VMs
        for ip in remote_ips:
            try:
                proc = subprocess.run(
                    ["ssh", f"pionera@{ip}", f"sudo tee {K3S_CONFIG}"],
                    input=KUBELET_CONFIG, text=True, capture_output=True,
                )
                if proc.returncode == 0:
                    print(f"[OK]   {ip}: wrote {K3S_CONFIG}")
                else:
                    print(f"[WARN] {ip}: could not write {K3S_CONFIG}: {proc.stderr.strip()}")
            except Exception as exc:
                print(f"[WARN] {ip}: kubelet config write skipped: {exc}")

    def _sync_nginx_http_proxy_vm_distributed(self):
        """Write nginx HTTP server blocks for vm-distributed dataspace and connector hostnames.

        Generates /etc/nginx/sites-enabled/pionera-vm-distributed-<ds>.conf on the common VM
        and writes connector proxy blocks on the remote provider/consumer VMs via SSH.
        """
        try:
            deployer_config = self.config_adapter.load_deployer_config() or {}
        except Exception:
            deployer_config = {}

        common_ip = str(deployer_config.get("VM_COMMON_IP") or "").strip()
        provider_ip = str(deployer_config.get("VM_PROVIDER_IP") or "").strip()
        consumer_ip = str(deployer_config.get("VM_CONSUMER_IP") or "").strip()
        nodeport = str(deployer_config.get("K3S_INGRESS_HTTP_NODEPORT") or "31667").strip()
        ds_domain = str(deployer_config.get("DS_DOMAIN_BASE") or "").strip()

        if not common_ip or not ds_domain:
            print("Warning: VM_COMMON_IP or DS_DOMAIN_BASE not set — skipping nginx HTTP proxy sync.")
            return

        try:
            ds_name = self.config_adapter.primary_dataspace_name()
        except Exception:
            ds_name = None
        if not ds_name:
            print("Warning: could not resolve dataspace name — skipping nginx HTTP proxy sync.")
            return

        provider_shorts = [n.strip() for n in str(deployer_config.get("VM_PROVIDER_CONNECTORS") or "").split(",") if n.strip()]
        consumer_shorts = [n.strip() for n in str(deployer_config.get("VM_CONSUMER_CONNECTORS") or "").split(",") if n.strip()]

        def _server_block(listen_ip, server_name, proxy_target, *, read_timeout=None, max_body=None):
            extras = ""
            if read_timeout:
                extras += f"        proxy_read_timeout {read_timeout};\n"
            if max_body:
                extras += f"        client_max_body_size {max_body};\n"
            else:
                extras += "        client_max_body_size 0;\n"
            return (
                f"server {{\n"
                f"    listen {listen_ip}:80;\n"
                f"    server_name {server_name};\n"
                f"    location / {{\n"
                f"        proxy_pass http://{proxy_target};\n"
                f"        proxy_set_header Host $host;\n"
                f"        proxy_set_header X-Real-IP $remote_addr;\n"
                f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                f"        proxy_set_header X-Forwarded-Proto $scheme;\n"
                f"        proxy_http_version 1.1;\n"
                f"{extras}"
                f"    }}\n"
                f"}}\n"
            )

        blocks = []
        rs_hostname = f"registration-service-{ds_name}.{ds_domain}"
        blocks.append(_server_block(common_ip, rs_hostname, f"{common_ip}:{nodeport}"))

        for short in provider_shorts:
            conn_name = f"conn-{short}-{ds_name}"
            conn_hostname = f"{conn_name}.{ds_domain}"
            target = f"{provider_ip}:{nodeport}" if provider_ip else f"{common_ip}:{nodeport}"
            blocks.append(_server_block(common_ip, conn_hostname, target))

        for short in consumer_shorts:
            conn_name = f"conn-{short}-{ds_name}"
            conn_hostname = f"{conn_name}.{ds_domain}"
            target = f"{consumer_ip}:{nodeport}" if consumer_ip else f"{common_ip}:{nodeport}"
            blocks.append(_server_block(common_ip, conn_hostname, target))

        conf_path = f"/etc/nginx/sites-enabled/pionera-vm-distributed-{ds_name}.conf"
        conf = "# Generated by framework — vm-distributed nginx HTTP proxy blocks\n" + "\n".join(blocks)

        try:
            proc = subprocess.run(
                ["sudo", "tee", conf_path],
                input=conf, text=True, capture_output=True,
            )
            if proc.returncode != 0:
                print(f"Warning: could not write {conf_path}: {proc.stderr.strip()}")
                return
            reload = subprocess.run(["sudo", "nginx", "-s", "reload"], capture_output=True, text=True)
            if reload.returncode == 0:
                print(f"nginx HTTP proxy conf updated ({conf_path}) and reloaded.")
            else:
                print(f"Warning: nginx reload failed after writing {conf_path}: {reload.stderr.strip()}")
        except Exception as exc:
            print(f"Warning: nginx HTTP proxy sync skipped: {exc}")
            return

        if provider_ip and provider_shorts:
            self._sync_remote_nginx_vm_distributed(
                provider_ip, provider_shorts, ds_name, ds_domain, nodeport, provider_ip,
            )
        if consumer_ip and consumer_shorts:
            self._sync_remote_nginx_vm_distributed(
                consumer_ip, consumer_shorts, ds_name, ds_domain, nodeport, consumer_ip,
            )

    def _sync_remote_nginx_vm_distributed(self, remote_ip, connector_shorts, ds_name, ds_domain, nodeport, listen_ip):
        """Write connector nginx server blocks on a remote VM via SSH and reload nginx."""
        blocks = []
        for short in connector_shorts:
            conn_name = f"conn-{short}-{ds_name}"
            conn_hostname = f"{conn_name}.{ds_domain}"
            block = (
                f"server {{\n"
                f"    listen {listen_ip}:80;\n"
                f"    server_name {conn_hostname};\n"
                f"    location / {{\n"
                f"        proxy_pass http://{listen_ip}:{nodeport};\n"
                f"        proxy_set_header Host $host;\n"
                f"        proxy_set_header X-Real-IP $remote_addr;\n"
                f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                f"        proxy_read_timeout 300s;\n"
                f"        client_max_body_size 800m;\n"
                f"    }}\n"
                f"}}\n"
            )
            blocks.append(block)
        if not blocks:
            return
        remote_conf = f"/etc/nginx/sites-enabled/pionera-vm-distributed-{ds_name}.conf"
        conf = f"# Generated by framework — vm-distributed connector nginx blocks\n" + "\n".join(blocks)
        try:
            proc = subprocess.run(
                ["ssh", f"pionera@{remote_ip}", f"sudo tee {remote_conf}"],
                input=conf, text=True, capture_output=True,
            )
            if proc.returncode != 0:
                print(f"Warning: could not write nginx conf on {remote_ip}: {proc.stderr.strip()}")
                return
            reload = subprocess.run(
                ["ssh", f"pionera@{remote_ip}", "sudo nginx -s reload"],
                capture_output=True, text=True,
            )
            if reload.returncode == 0:
                print(f"Remote nginx on {remote_ip} updated ({remote_conf}) and reloaded.")
            else:
                print(f"Warning: remote nginx reload failed on {remote_ip}: {reload.stderr.strip()}")
        except Exception as exc:
            print(f"Warning: remote nginx sync on {remote_ip} skipped: {exc}")

    def _sync_nginx_stream_proxy_vm_distributed(self):
        """Update /etc/nginx/pionera-stream.conf with current k8s ClusterIPs and reload nginx."""
        import shlex as _shlex

        NGINX_STREAM_CONF = "/etc/nginx/pionera-stream.conf"

        def _clusterip(namespace, service):
            try:
                out = subprocess.check_output(
                    ["kubectl", "get", "svc", service, "-n", namespace,
                     "-o", "jsonpath={.spec.clusterIP}"],
                    text=True, stderr=subprocess.DEVNULL,
                ).strip()
                return out if out and out != "None" else None
            except Exception:
                return None

        pg_ip = _clusterip("common-srvs", "common-srvs-postgresql")
        vault_ip = _clusterip("common-srvs", "common-srvs-vault")
        kc_ip = _clusterip("common-srvs", "common-srvs-keycloak")

        if not (pg_ip and vault_ip):
            print("Warning: could not resolve common-srvs ClusterIPs — skipping nginx stream sync.")
            return

        entries = []
        if pg_ip:
            entries.append(f"    server {{\n        listen 5432;\n        proxy_pass {pg_ip}:5432;\n        proxy_timeout 600s;\n        proxy_connect_timeout 10s;\n    }}")
        if vault_ip:
            entries.append(f"    server {{\n        listen 8200;\n        proxy_pass {vault_ip}:8200;\n        proxy_timeout 600s;\n        proxy_connect_timeout 10s;\n    }}")
        if kc_ip:
            entries.append(f"    server {{\n        listen 8080;\n        proxy_pass {kc_ip}:80;\n        proxy_timeout 600s;\n        proxy_connect_timeout 10s;\n    }}")

        conf = "stream {\n" + "\n".join(entries) + "\n}\n"

        try:
            proc = subprocess.run(
                ["sudo", "tee", NGINX_STREAM_CONF],
                input=conf, text=True,
                capture_output=True,
            )
            if proc.returncode != 0:
                print(f"Warning: could not write {NGINX_STREAM_CONF}: {proc.stderr.strip()}")
                return
            reload = subprocess.run(["sudo", "nginx", "-s", "reload"], capture_output=True, text=True)
            if reload.returncode == 0:
                print(f"nginx stream proxy updated (pg={pg_ip}, vault={vault_ip}) and reloaded.")
            else:
                print(f"Warning: nginx reload failed: {reload.stderr.strip()}")
        except Exception as exc:
            print(f"Warning: nginx stream sync skipped: {exc}")
