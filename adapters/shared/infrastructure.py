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
        self._ensure_ingress_nginx_forwarded_headers_vm_distributed(deployer_config)
        self._ensure_remote_nginx_server_names_hash_bucket_vm_distributed(deployer_config)

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

    def _ensure_remote_nginx_server_names_hash_bucket_vm_distributed(self, deployer_config=None):
        """Ensure server_names_hash_bucket_size 128 in /etc/nginx/nginx.conf on provider/consumer VMs.

        Long dataspace hostnames (e.g. conn-citycounciledc-pionera-edc.pionera.oeg.fi.upm.es) exceed
        nginx's default 64-byte hash bucket size, causing nginx to reject server_name directives on
        the remote VMs. This sets the value to 128 idempotently via SSH.
        """
        config = deployer_config or {}
        provider_ip = str(config.get("VM_PROVIDER_IP") or "").strip()
        consumer_ip = str(config.get("VM_CONSUMER_IP") or "").strip()

        for ip in filter(None, [provider_ip, consumer_ip]):
            try:
                # Idempotent: replace commented-out default OR already-present 64 value with 128.
                # Noop if 128 is already set.
                sed_cmd = (
                    "grep -q 'server_names_hash_bucket_size 128' /etc/nginx/nginx.conf && exit 0; "
                    "sudo sed -i "
                    "'s/# server_names_hash_bucket_size 64;/server_names_hash_bucket_size 128;/g; "
                    "s/server_names_hash_bucket_size 64;/server_names_hash_bucket_size 128;/g' "
                    "/etc/nginx/nginx.conf && sudo nginx -s reload"
                )
                proc = subprocess.run(
                    ["ssh", f"pionera@{ip}", sed_cmd],
                    capture_output=True, text=True,
                )
                if proc.returncode == 0:
                    print(f"[OK]   nginx server_names_hash_bucket_size 128 set on {ip}")
                else:
                    print(f"[WARN] nginx hash bucket patch failed on {ip}: {proc.stderr.strip()}")
            except Exception as exc:
                print(f"[WARN] nginx hash bucket patch skipped on {ip}: {exc}")

    def _ensure_ingress_nginx_forwarded_headers_vm_distributed(self, deployer_config=None):
        """Patch ingress-nginx configmap on provider and consumer clusters to trust X-Forwarded-Proto.

        Without use-forwarded-headers=true, ingress-nginx ignores X-Forwarded-Proto: https sent by
        the common VM's nginx reverse proxy, sees plain HTTP on the NodePort, and force-redirects to
        https://<connector-hostname> — which resolves directly to the remote VM from LAN clients,
        creating an ssl-redirect loop (ERR_TOO_MANY_REDIRECTS).
        """
        config = deployer_config or {}
        kubeconfigs = []
        for key in ("K3S_KUBECONFIG_PROVIDER", "K3S_KUBECONFIG_CONSUMER"):
            kc = str(config.get(key) or "").strip()
            if kc:
                kubeconfigs.append(kc)

        cm_patch = '{"data":{"use-forwarded-headers":"true","compute-full-forwarded-for":"true"}}'
        for kc in kubeconfigs:
            try:
                proc = subprocess.run(
                    ["kubectl", "--kubeconfig", kc, "patch", "configmap",
                     "ingress-nginx-controller", "-n", "ingress-nginx",
                     "--type=merge", "-p", cm_patch],
                    capture_output=True, text=True,
                )
                if proc.returncode == 0:
                    print(f"[OK]   ingress-nginx configmap patched ({kc})")
                else:
                    print(f"[WARN] ingress-nginx configmap patch failed ({kc}): {proc.stderr.strip()}")
            except Exception as exc:
                print(f"[WARN] ingress-nginx configmap patch skipped ({kc}): {exc}")

    def _ensure_ingress_ssl_redirect_disabled_vm_distributed(self, deployer_config, ds_name):
        """Disable ssl-redirect on connector and common-service ingresses for vm-distributed.

        ingress-nginx default ssl_redirect=true redirects HTTP → https://<hostname>. For vm-distributed
        all traffic arrives via the pioneer40 nginx proxy over the LAN using plain HTTP — there is no
        HTTPS listener on the internal hostname, so the redirect creates a dead-end (SSL cert missing or
        self-signed). Disabled on:
          - connector ingresses on provider/consumer clusters (prevent loop when LAN clients hit NodePort)
          - Keycloak/MinIO ingresses on common cluster (prevent 301 redirect that causes SSL verify failure
            when the framework calls KC_INTERNAL_URL from pioneer40)
        """
        config = deployer_config or {}
        annotation_patch = '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/ssl-redirect":"false"}}}'

        # Connector ingresses on remote clusters
        entries = [
            (config.get("K3S_KUBECONFIG_PROVIDER") or "", "provider",
             [n.strip() for n in str(config.get("VM_PROVIDER_CONNECTORS") or "").split(",") if n.strip()]),
            (config.get("K3S_KUBECONFIG_CONSUMER") or "", "consumer",
             [n.strip() for n in str(config.get("VM_CONSUMER_CONNECTORS") or "").split(",") if n.strip()]),
        ]
        for kc, namespace, shorts in entries:
            if not kc:
                continue
            for short in shorts:
                ingress_name = f"conn-{short}-{ds_name}-ingress"
                try:
                    proc = subprocess.run(
                        ["kubectl", "--kubeconfig", kc, "patch", "ingress", ingress_name,
                         "-n", namespace, "--type=merge", "-p", annotation_patch],
                        capture_output=True, text=True,
                    )
                    if proc.returncode == 0:
                        print(f"[OK]   ssl-redirect disabled on {ingress_name} ({namespace})")
                    else:
                        print(f"[WARN] ssl-redirect patch failed on {ingress_name}: {proc.stderr.strip()}")
                except Exception as exc:
                    print(f"[WARN] ssl-redirect patch skipped ({ingress_name}): {exc}")

        # Common-service ingresses on the common cluster (Keycloak, MinIO)
        common_ingresses = [
            ("common-srvs", "common-srvs-keycloak"),
            ("common-srvs", "common-srvs-keycloak-admin"),
            ("common-srvs", "common-srvs-minio"),
            ("common-srvs", "common-srvs-minio-console"),
        ]
        for namespace, ingress_name in common_ingresses:
            try:
                proc = subprocess.run(
                    ["kubectl", "patch", "ingress", ingress_name,
                     "-n", namespace, "--type=merge", "-p", annotation_patch],
                    capture_output=True, text=True,
                )
                if proc.returncode == 0:
                    print(f"[OK]   ssl-redirect disabled on {ingress_name} ({namespace})")
                else:
                    print(f"[WARN] ssl-redirect patch failed on {ingress_name}: {proc.stderr.strip()}")
            except Exception as exc:
                print(f"[WARN] ssl-redirect patch skipped ({ingress_name}): {exc}")

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
        provider_port = str(deployer_config.get("VM_PROVIDER_INGRESS_HTTP_PORT") or nodeport).strip()
        consumer_port = str(deployer_config.get("VM_CONSUMER_INGRESS_HTTP_PORT") or nodeport).strip()
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
            target = f"{provider_ip}:{provider_port}" if provider_ip else f"{common_ip}:{nodeport}"
            blocks.append(_server_block(common_ip, conn_hostname, target))

        for short in consumer_shorts:
            conn_name = f"conn-{short}-{ds_name}"
            conn_hostname = f"{conn_name}.{ds_domain}"
            target = f"{consumer_ip}:{consumer_port}" if consumer_ip else f"{common_ip}:{nodeport}"
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
                provider_ip, provider_shorts, ds_name, ds_domain, provider_port, provider_ip,
            )
        if consumer_ip and consumer_shorts:
            self._sync_remote_nginx_vm_distributed(
                consumer_ip, consumer_shorts, ds_name, ds_domain, consumer_port, consumer_ip,
            )

        self._patch_dataspace_nginx_for_vm_distributed(deployer_config, ds_name, ds_domain)
        self._ensure_ingress_ssl_redirect_disabled_vm_distributed(deployer_config, ds_name)
        self._sync_connector_routing_conf_vm_distributed(deployer_config, ds_name, ds_domain)
        self._patch_keycloak_admin_console_vm_distributed(deployer_config, ds_domain)

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

    def _patch_dataspace_nginx_for_vm_distributed(self, deployer_config, ds_name, ds_domain):
        """Generate complete /etc/nginx/sites-enabled/pionera-dataspace.conf for vm-distributed.

        Writes the full server blocks with SSL termination, Keycloak sub_filter rewrites,
        MinIO WebSocket proxy, and correct proxy_pass targets per provider/consumer VM.
        Also patches app.config realm references on the common VM.
        Idempotent — safe to re-run at any level.
        """
        DATASPACE_CONF = "/etc/nginx/sites-enabled/pionera-dataspace.conf"
        CERT_PATH = "/etc/nginx/pionera-selfsigned.crt"
        KEY_PATH  = "/etc/nginx/pionera-selfsigned.key"

        nodeport_default = str(deployer_config.get("K3S_INGRESS_HTTP_NODEPORT") or "31667").strip()
        common_ip        = str(deployer_config.get("VM_COMMON_IP") or "").strip()
        minikube_ip      = str(deployer_config.get("MINIKUBE_IP") or "192.168.49.2").strip()
        provider_ip      = str(deployer_config.get("VM_PROVIDER_IP") or "").strip()
        consumer_ip      = str(deployer_config.get("VM_CONSUMER_IP") or "").strip()
        provider_nodeport = str(deployer_config.get("VM_PROVIDER_INGRESS_NODEPORT") or nodeport_default).strip()
        consumer_nodeport = str(deployer_config.get("VM_CONSUMER_INGRESS_NODEPORT") or nodeport_default).strip()
        provider_shorts  = [n.strip() for n in str(deployer_config.get("VM_PROVIDER_CONNECTORS") or "").split(",") if n.strip()]
        consumer_shorts  = [n.strip() for n in str(deployer_config.get("VM_CONSUMER_CONNECTORS") or "").split(",") if n.strip()]

        if not common_ip or not provider_ip or not consumer_ip:
            return

        # Ensure self-signed TLS cert exists for nginx SSL block
        cert_missing = subprocess.run(["sudo", "test", "-f", CERT_PATH], capture_output=True).returncode != 0
        if cert_missing:
            print("Generating self-signed TLS certificate for nginx...")
            subprocess.run([
                "sudo", "openssl", "req", "-x509", "-nodes", "-days", "3650",
                "-newkey", "rsa:2048", "-keyout", KEY_PATH, "-out", CERT_PATH,
                "-subj", f"/CN=org1.{ds_domain}/O=Pionera",
                "-addext", f"subjectAltName=DNS:org1.{ds_domain},DNS:*.{ds_domain}",
            ], capture_output=True)
            subprocess.run(["sudo", "chmod", "600", KEY_PATH], capture_output=True)

        all_shorts = provider_shorts + consumer_shorts
        org1       = f"org1.{ds_domain}"
        auth_host  = f"auth.{ds_domain}"
        admin_host = f"admin.auth.{ds_domain}"
        nodeport   = nodeport_default  # local common-VM k3s NodePort for shared services

        # --- App config locations ---
        app_cfg = (
            "    location = /inesdata-connector-interface/assets/config/app.config.json {\n"
            "        rewrite ^ /internal-connector-config/$connector_config_name last;\n"
            "    }\n"
        )
        for short in all_shorts:
            app_cfg += (
                f"    location = /internal-connector-config/{short} {{\n"
                f"        internal;\n"
                f"        alias /var/www/connector-configs/app.config.{short}.https.json;\n"
                f"        default_type application/json;\n"
                f'        add_header Cache-Control "no-store, no-cache, must-revalidate" always;\n'
                f"    }}\n"
                f"    location = /c/{short}/inesdata-connector-interface/assets/config/app.config.json {{\n"
                f"        alias /var/www/connector-configs/app.config.{short}.https.json;\n"
                f"        default_type application/json;\n"
                f'        add_header Cache-Control "no-store, no-cache, must-revalidate";\n'
                f"    }}\n"
            )

        # --- Connector locations ---
        conn_links = "".join(
            f'<li><a href=\\\"/c/{s}/inesdata-connector-interface/\\\">{s.capitalize()} Connector</a></li>'
            for s in all_shorts
        )

        def _connector_locations(shorts, backend_ip, backend_port):
            out = ""
            for short in shorts:
                conn_host = f"conn-{short}-{ds_name}.{ds_domain}"
                out += (
                    f"    location ~* ^/c/{short}/inesdata-connector-interface(.*)$ {{\n"
                    f'        add_header Set-Cookie "inesdata_connector={short}; Path=/; SameSite=Lax" always;\n'
                    f"        return 301 /inesdata-connector-interface$1$is_args$args;\n"
                    f"    }}\n"
                    f"    location /c/{short}/management/ {{\n"
                    f"        rewrite ^/c/{short}/management/(.*) /management/$1 break;\n"
                    f"        proxy_pass http://{backend_ip}:{backend_port};\n"
                    f"        proxy_set_header Host {conn_host};\n"
                    f"        proxy_set_header X-Real-IP $remote_addr;\n"
                    f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                    f"        proxy_set_header X-Forwarded-Proto $scheme;\n"
                    f"        client_max_body_size 0;\n"
                    f"    }}\n"
                    f"    location /c/{short}/shared/ {{\n"
                    f"        rewrite ^/c/{short}/shared/(.*) /shared/$1 break;\n"
                    f"        proxy_pass http://{backend_ip}:{backend_port};\n"
                    f"        proxy_set_header Host {conn_host};\n"
                    f"        proxy_set_header X-Real-IP $remote_addr;\n"
                    f"    }}\n"
                    f"    location /c/{short}/federatedcatalog/ {{\n"
                    f"        rewrite ^/c/{short}/federatedcatalog/(.*) /management/federatedcatalog/$1 break;\n"
                    f"        proxy_pass http://{backend_ip}:{backend_port};\n"
                    f"        proxy_set_header Host {conn_host};\n"
                    f"        proxy_set_header X-Real-IP $remote_addr;\n"
                    f"    }}\n"
                    f"    location /c/{short}/ {{\n"
                    f'        add_header Set-Cookie "inesdata_connector={short}; Path=/; SameSite=Lax" always;\n'
                    f"        rewrite ^/c/{short}/(.*) /$1 break;\n"
                    f"        proxy_pass http://{backend_ip}:{backend_port};\n"
                    f"        proxy_set_header Host {conn_host};\n"
                    f"        proxy_set_header X-Real-IP $remote_addr;\n"
                    f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
                    f"        proxy_set_header X-Forwarded-Proto $scheme;\n"
                    f"    }}\n"
                )
            return out

        connector_locs  = _connector_locations(provider_shorts, provider_ip, provider_nodeport)
        connector_locs += _connector_locations(consumer_shorts, consumer_ip, consumer_nodeport)

        conf = (
            "# Generated by framework — vm-distributed full nginx proxy\n"
            "server {\n"
            f"    listen {common_ip}:80;\n"
            f"    listen {minikube_ip}:80;\n"
            f"    listen {common_ip}:443 ssl;\n"
            f"    ssl_certificate     {CERT_PATH};\n"
            f"    ssl_certificate_key {KEY_PATH};\n"
            "    ssl_protocols       TLSv1.2 TLSv1.3;\n"
            "    ssl_ciphers         HIGH:!aNULL:!MD5;\n"
            f"    server_name {org1};\n\n"
            + app_cfg + "\n"
            "    location = / {\n"
            "        default_type text/html;\n"
            f'        return 200 "<html><body><h1>INESData Environment</h1><ul>{conn_links}'
            '<li><a href=\\\"/auth/\\\">Keycloak</a></li>'
            '<li><a href=\\\"/s3-console/\\\">MinIO Console</a></li>'
            '</ul></body></html>";\n'
            "    }\n\n"
            # Keycloak — full sub_filter set to survive behind nginx SSL termination
            "    location /auth/ {\n"
            "        rewrite ^/auth/(.*) /$1 break;\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            f"        proxy_set_header Host {auth_host};\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto https;\n"
            "        proxy_set_header X-Forwarded-Port 443;\n"
            "        proxy_set_header Accept-Encoding \"\";\n"
            f"        proxy_redirect http://{admin_host}/admin/ https://{org1}/auth/admin/;\n"
            f"        proxy_redirect http://{auth_host}/ https://{org1}/auth/;\n"
            "        proxy_cookie_path /realms/ /auth/realms/;\n"
            "        sub_filter_types application/json;\n"
            "        sub_filter_once off;\n"
            f'        sub_filter "http://{auth_host}/realms/"    "https://{org1}/auth/realms/";\n'
            f'        sub_filter "https://{auth_host}/realms/"  "https://{org1}/auth/realms/";\n'
            f'        sub_filter "https://{auth_host}/"         "https://{org1}/auth/";\n'
            f'        sub_filter "http://{auth_host}/resources/" "https://{org1}/auth/resources/";\n'
            f'        sub_filter "http://{auth_host}/js/"        "https://{org1}/auth/js/";\n'
            f'        sub_filter "http://{org1}/auth/"           "https://{org1}/auth/";\n'
            f'        sub_filter \'"auth-server-url":"http://{admin_host}"\' \'"auth-server-url":"https://{org1}/auth"\';\n'
            f'        sub_filter \'"auth-server-url": "http://{admin_host}"\' \'"auth-server-url": "https://{org1}/auth"\';\n'
            f"        sub_filter 'http://{admin_host}' 'https://{org1}/auth';\n"
            "    }\n\n"
            "    location /s3/ {\n"
            "        rewrite ^/s3/(.*) /$1 break;\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            f"        proxy_set_header Host minio.{ds_domain};\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "    }\n\n"
            "    location /resources/ {\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            f"        proxy_set_header Host {auth_host};\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"
            "    }\n\n"
            # MinIO WebSocket — browser uses absolute /ws/ path (ignores <base href>)
            "    location /ws/ {\n"
            f"        proxy_pass http://{common_ip}:{nodeport}/ws/;\n"
            f"        proxy_set_header Host console.minio-s3.{ds_domain};\n"
            f"        proxy_set_header Origin https://console.minio-s3.{ds_domain};\n"
            "        proxy_set_header Upgrade $http_upgrade;\n"
            '        proxy_set_header Connection "upgrade";\n'
            "        proxy_http_version 1.1;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto https;\n"
            "        proxy_set_header X-Forwarded-Port 443;\n"
            "        proxy_read_timeout 3600s;\n"
            "    }\n"
            "    location /s3-console/ws/ {\n"
            f"        proxy_pass http://{common_ip}:{nodeport}/ws/;\n"
            f"        proxy_set_header Host console.minio-s3.{ds_domain};\n"
            f"        proxy_set_header Origin https://console.minio-s3.{ds_domain};\n"
            "        proxy_set_header Upgrade $http_upgrade;\n"
            '        proxy_set_header Connection "upgrade";\n'
            "        proxy_http_version 1.1;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto https;\n"
            "        proxy_set_header X-Forwarded-Port 443;\n"
            "        proxy_read_timeout 3600s;\n"
            "    }\n"
            "    location /s3-console/ {\n"
            "        rewrite ^/s3-console/(.*) /$1 break;\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            f"        proxy_set_header Host console.minio-s3.{ds_domain};\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto https;\n"
            "        proxy_set_header X-Forwarded-Port 443;\n"
            "        proxy_http_version 1.1;\n"
            '        proxy_set_header Accept-Encoding "";\n'
            "        proxy_cookie_path / /s3-console/;\n"
            "        gunzip on;\n"
            "        sub_filter '<base href=\"/\"/>' '<base href=\"/s3-console/\"/>';\n"
            "        sub_filter_once on;\n"
            "    }\n\n"
            "    location /rs-demo/ {\n"
            "        rewrite ^/rs-demo/(.*) /$1 break;\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            f"        proxy_set_header Host registration-service-demo.{ds_domain};\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "    }\n\n"
            + connector_locs
            + "\n"
            "    location /inesdata-connector-interface/ {\n"
            "        proxy_pass http://$connector_backend;\n"
            "        proxy_set_header Host $connector_host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"
            "    }\n"
            "}\n\n"
            "server {\n"
            f"    listen {common_ip}:80;\n"
            f"    listen {minikube_ip}:80;\n"
            f"    listen {common_ip}:443 ssl;\n"
            f"    ssl_certificate     {CERT_PATH};\n"
            f"    ssl_certificate_key {KEY_PATH};\n"
            "    ssl_protocols       TLSv1.2 TLSv1.3;\n"
            "    ssl_ciphers         HIGH:!aNULL:!MD5;\n"
            f"    server_name *.{org1};\n\n"
            "    location / {\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"
            "        proxy_http_version 1.1;\n"
            "        proxy_set_header Upgrade $http_upgrade;\n"
            '        proxy_set_header Connection "upgrade";\n'
            "        client_max_body_size 0;\n"
            "    }\n"
            "}\n\n"
            "# Direct passthrough server blocks for internal service hostnames\n"
            "server {\n"
            f"    listen {common_ip}:80;\n"
            f"    server_name {auth_host} {admin_host};\n"
            "    location / {\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"
            "        proxy_connect_timeout 10s;\n"
            "        client_max_body_size 0;\n"
            "    }\n"
            "}\n\n"
            "# MinIO S3 API — direct hostname access (used by EDC data-plane AWS SDK)\n"
            "server {\n"
            f"    listen {common_ip}:80;\n"
            f"    server_name minio.{ds_domain} console.minio-s3.{ds_domain};\n"
            "    client_max_body_size 0;\n"
            "    location / {\n"
            f"        proxy_pass http://{common_ip}:{nodeport};\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            "        proxy_set_header X-Forwarded-Proto $scheme;\n"
            "        proxy_http_version 1.1;\n"
            "        proxy_read_timeout 300s;\n"
            "    }\n"
            "}\n"
        )

        # Patch app.config files on the common VM: substitute unresolved template vars
        import json as _json
        app_config_dir = "/var/www/connector-configs"
        ontology_url = f"https://ontology-hub-{ds_name}.{ds_domain}"
        for short in all_shorts:
            for suffix in (".https.json", ".json"):
                cfg_path = f"{app_config_dir}/app.config.{short}{suffix}"
                try:
                    r = subprocess.run(["sudo", "cat", cfg_path], capture_output=True, text=True)
                    if r.returncode != 0:
                        continue
                    try:
                        cfg = _json.loads(r.stdout)
                    except _json.JSONDecodeError:
                        continue
                    changed = False
                    # Substitute unresolved $VAR placeholders and stale realm references
                    for key, replacement in [
                        ("ontologyUrl", ontology_url),
                        ("ontologyAdminUser", ""),
                        ("ontologyAdminPassword", ""),
                        ("participantId", f"conn-{short}-{ds_name}"),
                        ("storageAccount", ""),
                        ("storageExplorerLinkTemplate", ""),
                    ]:
                        if isinstance(cfg.get(key), str) and cfg[key].startswith("$"):
                            cfg[key] = replacement
                            changed = True
                    oauth2 = cfg.get("oauth2") or {}
                    if isinstance(oauth2.get("issuer"), str) and "/realms/demo" in oauth2["issuer"]:
                        oauth2["issuer"] = oauth2["issuer"].replace("/realms/demo", f"/realms/{ds_name}")
                        changed = True
                    if changed:
                        patched = _json.dumps(cfg, indent=2)
                        subprocess.run(["sudo", "tee", cfg_path], input=patched, text=True, capture_output=True)
                        print(f"Patched app.config {cfg_path}")
                except Exception as exc:
                    print(f"Warning: could not patch {cfg_path}: {exc}")

        try:
            proc = subprocess.run(
                ["sudo", "tee", DATASPACE_CONF],
                input=conf, text=True, capture_output=True,
            )
            if proc.returncode != 0:
                print(f"Warning: could not write {DATASPACE_CONF}: {proc.stderr.strip()}")
                return
            reload = subprocess.run(["sudo", "nginx", "-s", "reload"], capture_output=True, text=True)
            if reload.returncode == 0:
                print(f"pionera-dataspace.conf generated and nginx reloaded.")
            else:
                print(f"Warning: nginx reload failed after writing {DATASPACE_CONF}: {reload.stderr.strip()}")
        except Exception as exc:
            print(f"Warning: dataspace conf write failed: {exc}")

    def _sync_connector_routing_conf_vm_distributed(self, deployer_config, ds_name, ds_domain):
        """Write /etc/nginx/conf.d/connector-routing.conf with cookie-based connector routing maps."""
        nodeport_default = str(deployer_config.get("K3S_INGRESS_HTTP_NODEPORT") or "31667").strip()
        provider_ip = str(deployer_config.get("VM_PROVIDER_IP") or "").strip()
        consumer_ip = str(deployer_config.get("VM_CONSUMER_IP") or "").strip()
        provider_nodeport = str(deployer_config.get("VM_PROVIDER_INGRESS_NODEPORT") or nodeport_default).strip()
        consumer_nodeport = str(deployer_config.get("VM_CONSUMER_INGRESS_NODEPORT") or nodeport_default).strip()
        provider_shorts = [n.strip() for n in str(deployer_config.get("VM_PROVIDER_CONNECTORS") or "").split(",") if n.strip()]
        consumer_shorts = [n.strip() for n in str(deployer_config.get("VM_CONSUMER_CONNECTORS") or "").split(",") if n.strip()]

        if not provider_shorts or not consumer_shorts:
            return

        provider_short = provider_shorts[0]
        consumer_short = consumer_shorts[0]
        provider_host = f"conn-{provider_short}-{ds_name}.{ds_domain}"
        consumer_host = f"conn-{consumer_short}-{ds_name}.{ds_domain}"

        conf = (
            f"# Generated by framework — vm-distributed connector cookie routing maps\n"
            f"map $cookie_inesdata_connector $connector_host {{\n"
            f'    "{consumer_short}"    {consumer_host};\n'
            f"    default      {provider_host};\n"
            f"}}\n"
            f"map $cookie_inesdata_connector $connector_config_name {{\n"
            f'    "{consumer_short}"    {consumer_short};\n'
            f"    default      {provider_short};\n"
            f"}}\n"
            f"map $cookie_inesdata_connector $connector_backend {{\n"
            f'    "{consumer_short}"    {consumer_ip}:{consumer_nodeport};\n'
            f"    default      {provider_ip}:{provider_nodeport};\n"
            f"}}\n"
        )

        conf_path = "/etc/nginx/conf.d/connector-routing.conf"
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
                print(f"connector-routing.conf updated ({conf_path}) and nginx reloaded.")
            else:
                print(f"Warning: nginx reload failed after writing {conf_path}: {reload.stderr.strip()}")
        except Exception as exc:
            print(f"Warning: connector-routing.conf sync skipped: {exc}")

    def _patch_keycloak_admin_console_vm_distributed(self, deployer_config, ds_domain):
        """Register org1 HTTPS redirect URI on security-admin-console client in master realm.

        Keycloak's built-in security-admin-console client only lists relative redirect URIs by
        default.  When Keycloak is accessed via the org1 HTTPS proxy the absolute URI must also
        be registered or the admin console login flow fails with 'invalid_redirect_uri'.
        Also sets ssl-required=none on master realm so that Keycloak (which receives plain HTTP
        from nginx) does not reject admin console requests with "HTTPS required".
        """
        import json as _json
        try:
            import requests as _requests
        except ImportError:
            print("Warning: requests not available — skipping Keycloak admin console patch")
            return

        kc_url  = str(deployer_config.get("KC_URL") or "").rstrip("/")
        kc_user = str(deployer_config.get("KC_USER") or "admin").strip()
        kc_pass = str(deployer_config.get("KC_PASSWORD") or "").strip()
        if not kc_url or not kc_pass:
            print("Keycloak admin console patch skipped: KC_URL/KC_PASSWORD not set")
            return

        org1_redirect = f"https://org1.{ds_domain}/auth/admin/master/console/*"

        try:
            token_resp = _requests.post(
                f"{kc_url}/realms/master/protocol/openid-connect/token",
                data={"grant_type": "password", "client_id": "admin-cli",
                      "username": kc_user, "password": kc_pass},
                timeout=10,
            )
            if token_resp.status_code != 200:
                print(f"Warning: Keycloak token fetch failed ({token_resp.status_code}) — skipping admin console patch")
                return
            token = token_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            # ssl-required=none so Keycloak does not reject HTTP requests from nginx
            realm_resp = _requests.get(f"{kc_url}/admin/realms/master", headers=headers, timeout=10)
            if realm_resp.status_code == 200:
                realm = realm_resp.json()
                if realm.get("sslRequired") != "none":
                    realm["sslRequired"] = "none"
                    _requests.put(f"{kc_url}/admin/realms/master", headers=headers,
                                  data=_json.dumps(realm), timeout=10)
                    print("Keycloak master realm: ssl-required set to none")

            # Add org1 redirect URI to security-admin-console client
            clients_resp = _requests.get(
                f"{kc_url}/admin/realms/master/clients?clientId=security-admin-console",
                headers=headers, timeout=10,
            )
            if clients_resp.status_code == 200 and clients_resp.json():
                client = clients_resp.json()[0]
                redirect_uris = client.get("redirectUris") or []
                if org1_redirect not in redirect_uris:
                    redirect_uris.append(org1_redirect)
                    client["redirectUris"] = redirect_uris
                    r = _requests.put(
                        f"{kc_url}/admin/realms/master/clients/{client['id']}",
                        headers=headers, data=_json.dumps(client), timeout=10,
                    )
                    if r.status_code in (200, 204):
                        print(f"Keycloak security-admin-console: added redirect URI {org1_redirect}")
                    else:
                        print(f"Warning: could not update security-admin-console redirectUris: {r.status_code}")
        except Exception as exc:
            print(f"Warning: Keycloak admin console patch failed: {exc}")

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
