import os
import shlex
import tempfile
import time
import ipaddress

import yaml

from deployers.infrastructure.lib.paths import shared_artifact_roots
from .config import INESDataConfigAdapter, InesdataConfig


class INESDataComponentsAdapter:
    """Deploy optional platform components via Helm charts (Level 5).

    This adapter is intentionally isolated from Level 3/4 logic so introducing
    components does not change the stability of Levels 1-4.
    """

    _LEVEL6_EXCLUDED_KEYS = {
        # Components that are part of the base dataspace lifecycle.
        "registration-service",
        "public-portal",
    }
    _ONTOLOGY_HUB_REPO_URL = "https://github.com/ProyectoPIONERA/Ontology-Hub.git"
    _ONTOLOGY_HUB_REPO_DIRNAME = "Ontology-Hub"
    _AI_MODEL_HUB_REPO_URL = "https://github.com/ProyectoPIONERA/AIModelHub.git"
    _AI_MODEL_HUB_REPO_DIRNAME = "AIModelHub"

    def __init__(
        self,
        run,
        run_silent,
        auto_mode_getter,
        infrastructure_adapter,
        config_adapter=None,
        config_cls=None,
    ):
        self.run = run
        self.run_silent = run_silent
        self.auto_mode_getter = auto_mode_getter
        self.infrastructure = infrastructure_adapter
        self.config = config_cls or InesdataConfig
        self.config_adapter = config_adapter or INESDataConfigAdapter(self.config)
        self._attempted_platform_repo_refresh = False

    def _auto_mode(self) -> bool:
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

    @staticmethod
    def _normalize_component_key(component: str) -> str:
        return (component or "").strip().lower().replace("_", "-")

    @staticmethod
    def _to_http_url(host_or_url: str) -> str:
        value = (host_or_url or "").strip()
        if not value:
            return ""
        if value.startswith("http://"):
            return value
        if value.startswith("https://"):
            return "http://" + value[len("https://"):]
        return f"http://{value}"

    def _component_chart_roots(self):
        return shared_artifact_roots("components")

    def _refresh_platform_repo_once(self):
        if self._attempted_platform_repo_refresh:
            return
        self._attempted_platform_repo_refresh = True

        repo_dir = self.config.repo_dir()
        git_dir = os.path.join(repo_dir, ".git")
        if not os.path.isdir(git_dir):
            return

        repo_q = shlex.quote(repo_dir)
        print("Refreshing INESData deployer artifacts repository (git pull) to discover component charts...")
        self.run(f"git -C {repo_q} fetch --all --prune", check=False)
        self.run(f"git -C {repo_q} pull --ff-only", check=False)

    def _discover_component_charts(self) -> dict:
        """Discover deployable Helm charts.

        Convention:
        - Each component chart is a directory containing a Chart.yaml.
        - Root: <repo_dir>/components/*
        """
        charts = {}
        for root in self._component_chart_roots():
            if not os.path.isdir(root):
                continue
            for entry in os.listdir(root):
                chart_dir = os.path.join(root, entry)
                if not os.path.isdir(chart_dir):
                    continue
                if os.path.isfile(os.path.join(chart_dir, "Chart.yaml")):
                    charts[self._normalize_component_key(entry)] = chart_dir
        if charts:
            return charts

        # If the repo exists but charts are missing, attempt a single refresh.
        self._refresh_platform_repo_once()

        charts = {}
        for root in self._component_chart_roots():
            if not os.path.isdir(root):
                continue
            for entry in os.listdir(root):
                chart_dir = os.path.join(root, entry)
                if not os.path.isdir(chart_dir):
                    continue
                if os.path.isfile(os.path.join(chart_dir, "Chart.yaml")):
                    charts[self._normalize_component_key(entry)] = chart_dir
        return charts

    def list_deployable_components(self):
        return sorted(self._discover_component_charts().keys())

    def _resolve_component_chart_dir(self, component_key: str) -> str:
        normalized = self._normalize_component_key(component_key)
        charts = self._discover_component_charts()
        chart_dir = charts.get(normalized)
        if chart_dir:
            return chart_dir

        if not charts:
            self._fail(
                "No deployable component charts discovered in deployer artifacts",
                root_cause=(
                    "Expected Helm charts under deployers/shared/components or deployers/inesdata/components. "
                    "Verify that the deployer artifacts are present in this repository checkout."
                ),
            )

        available = ", ".join(sorted(charts)) or "(none)"
        self._fail(
            f"Unknown component '{component_key}'. "
            f"Deployable components discovered in deployer artifacts: {available}"
        )

    def _resolve_component_values_file(self, chart_dir: str, ds_name: str, namespace: str) -> str:
        candidates = [
            os.path.join(chart_dir, f"values-{ds_name}.yaml"),
            os.path.join(chart_dir, f"values-{namespace}.yaml"),
            os.path.join(chart_dir, "values.yaml"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate

        self._fail(
            "No values file found for component chart. "
            f"Tried: {', '.join(os.path.basename(p) for p in candidates)} in {chart_dir}"
        )

    def _resolve_component_release_name(self, normalized_component: str) -> str:
        ds_name = self._dataspace_name()
        if normalized_component == "registration-service":
            return self.config.helm_release_rs()
        if normalized_component == "public-portal":
            return f"{ds_name}-dataspace-pp"
        return f"{ds_name}-{normalized_component}"

    @staticmethod
    def _parse_bool(value, default=False) -> bool:
        if value is None:
            return default
        raw = str(value).strip().lower()
        if raw == "":
            return default
        if raw in ("1", "true", "yes", "y", "on"):
            return True
        if raw in ("0", "false", "no", "n", "off"):
            return False
        return default

    @staticmethod
    def _strip_url_scheme(host_or_url: str) -> str:
        value = (host_or_url or "").strip().rstrip("/")
        if value.startswith("http://"):
            return value[len("http://"):]
        if value.startswith("https://"):
            return value[len("https://"):]
        return value

    def _cleanup_components(self, components, namespace: str):
        namespace = (namespace or "").strip()
        if not namespace:
            return

        ns_q = shlex.quote(namespace)
        print("\nCleaning previous component deployments (Level 5)...")

        for component in components:
            normalized = self._normalize_component_key(component)
            if normalized in self._LEVEL6_EXCLUDED_KEYS:
                continue

            release_name = self._resolve_component_release_name(normalized)
            rel_q = shlex.quote(release_name)

            status = self.run_silent(f"helm status {rel_q} -n {ns_q}")
            if status is None:
                continue

            print(f"- Removing {normalized} (release {release_name})")

            pvc_pvs = []
            pv_list = self.run_silent(
                f"kubectl get pvc -n {ns_q} -l app.kubernetes.io/instance={rel_q} "
                f"-o jsonpath='{{range .items[*]}}{{.spec.volumeName}}{{\"\\n\"}}{{end}}'"
            )
            if pv_list:
                pvc_pvs = [line.strip() for line in pv_list.splitlines() if line.strip()]

            self.run(f"helm uninstall {rel_q} -n {ns_q}", check=False)
            self.run(
                f"kubectl delete pvc -n {ns_q} -l app.kubernetes.io/instance={rel_q} --ignore-not-found",
                check=False,
            )
            self.run(
                f"kubectl wait --for=delete pod -n {ns_q} -l app.kubernetes.io/instance={rel_q} --timeout=5m",
                check=False,
            )

            for pv_name in pvc_pvs:
                pv_q = shlex.quote(pv_name)
                reclaim = self.run_silent(
                    f"kubectl get pv {pv_q} -o jsonpath='{{.spec.persistentVolumeReclaimPolicy}}'"
                )
                if reclaim and reclaim.strip().upper() == "RETAIN":
                    self.run(f"kubectl delete pv {pv_q}", check=False)

    @staticmethod
    def _safe_load_yaml_file(path: str) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except Exception as exc:
            raise RuntimeError(f"Could not load YAML file: {path}. {exc}")

    @staticmethod
    def _extract_primary_image_ref(values: dict):
        image = (values or {}).get("image") or {}
        repository = (image.get("repository") or "").strip()
        tag_raw = image.get("tag")
        tag = str(tag_raw).strip() if tag_raw is not None else ""
        if not repository or not tag:
            return None
        return f"{repository}:{tag}"

    def _minikube_is_available(self, profile: str) -> bool:
        profile_q = shlex.quote(profile)
        return self.run_silent(f"minikube -p {profile_q} status") is not None

    def _minikube_has_image(self, profile: str, image_ref: str) -> bool:
        profile_q = shlex.quote(profile)
        output = self.run_silent(f"minikube -p {profile_q} image ls")
        if not output:
            return False

        suffix = image_ref.strip()
        for line in output.splitlines():
            candidate = (line or "").strip()
            if candidate.endswith(suffix):
                return True
        return False

    def _resolve_ontology_hub_source_dir(self, deployer_config: dict) -> str:
        sources_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources")
        ontology_hub_dir = os.path.join(sources_dir, self._ONTOLOGY_HUB_REPO_DIRNAME)
        dockerfile_path = os.path.join(ontology_hub_dir, "Dockerfile")
        if os.path.isfile(dockerfile_path):
            return ontology_hub_dir

        should_clone = not os.path.isdir(ontology_hub_dir)
        if not should_clone:
            try:
                remaining_entries = os.listdir(ontology_hub_dir)
            except OSError:
                remaining_entries = []
            should_clone = len(remaining_entries) == 0

        if should_clone:
            os.makedirs(sources_dir, exist_ok=True)
            if os.path.isdir(ontology_hub_dir):
                try:
                    os.rmdir(ontology_hub_dir)
                except OSError:
                    pass
            print(f"Cloning Ontology-Hub into {ontology_hub_dir} ...")
            import subprocess
            try:
                subprocess.run(["git", "clone", self._ONTOLOGY_HUB_REPO_URL, ontology_hub_dir], check=True)
            except Exception as exc:
                self._fail(
                    "Could not clone Ontology-Hub repository",
                    root_cause=str(exc),
                )

        if os.path.isfile(dockerfile_path):
            return ontology_hub_dir

        self._fail(
            "Ontology-Hub source directory is not usable",
            root_cause=(
                f"Expected Dockerfile at: {dockerfile_path}. "
                "Level 5 expects the canonical checkout at "
                "adapters/inesdata/sources/Ontology-Hub."
            ),
        )

    def _resolve_ai_model_hub_source_dir(self, deployer_config: dict) -> str:
        sources_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources")
        ai_model_hub_dir = os.path.join(sources_dir, self._AI_MODEL_HUB_REPO_DIRNAME)
        dashboard_dir = os.path.join(ai_model_hub_dir, "DataDashboard")
        dockerfile_path = os.path.join(dashboard_dir, "Dockerfile")
        if os.path.isfile(dockerfile_path):
            return dashboard_dir

        should_clone = not os.path.isdir(ai_model_hub_dir)
        if not should_clone:
            try:
                remaining_entries = os.listdir(ai_model_hub_dir)
            except OSError:
                remaining_entries = []
            should_clone = len(remaining_entries) == 0

        if should_clone:
            os.makedirs(sources_dir, exist_ok=True)
            if os.path.isdir(ai_model_hub_dir):
                try:
                    os.rmdir(ai_model_hub_dir)
                except OSError:
                    pass
            print(f"Cloning AI Model Hub into {ai_model_hub_dir} ...")
            import subprocess
            try:
                subprocess.run(["git", "clone", self._AI_MODEL_HUB_REPO_URL, ai_model_hub_dir], check=True)
            except Exception as exc:
                self._fail(
                    "Could not clone AI Model Hub repository",
                    root_cause=str(exc),
                )

        if os.path.isfile(dockerfile_path):
            return dashboard_dir

        self._fail(
            "AI Model Hub source directory is not usable",
            root_cause=(
                f"Expected Dockerfile at: {dockerfile_path}. "
                "Level 5 expects the canonical checkout at "
                "adapters/inesdata/sources/AIModelHub."
            ),
        )

    def _ontology_hub_build_args(self, ontology_hub_dir: str) -> dict:
        compose_path = os.path.join(ontology_hub_dir, "docker-compose.yml")
        if os.path.isfile(compose_path):
            compose = self._safe_load_yaml_file(compose_path)
            lov_server = ((compose.get("services") or {}).get("lov_server") or {})
            build = lov_server.get("build") or {}
            args = build.get("args") or {}
            if isinstance(args, dict) and args:
                return {str(k): str(v) for k, v in args.items() if v is not None}

        return {
            "REPO_URL": "https://github.com/ProyectoPIONERA/Ontology-Hub-Scripts.git",
            "BRANCH_NAME": "dev",
            "REPO_NAME": "Ontology-Hub-Scripts",
            "REPO_PATRONES": "https://github.com/oeg-upm/GrOwEr.git",
        }

    def _host_has_image(self, image_ref: str) -> bool:
        image_q = shlex.quote(image_ref)
        return self.run_silent(f"docker image inspect {image_q}") is not None

    def _load_image_into_minikube(self, profile: str, image_ref: str):
        profile_q = shlex.quote(profile)
        image_q = shlex.quote(image_ref)
        print(f"\nLoading image into minikube: {image_ref}")
        if self.run(f"minikube -p {profile_q} image load {image_q}", check=False) is None:
            self._fail("Failed to load image into minikube", root_cause=image_ref)

    def _build_ontology_hub_image_on_host(self, image_ref: str, deployer_config: dict):
        ontology_hub_dir = self._resolve_ontology_hub_source_dir(deployer_config)
        dockerfile_path = os.path.join(ontology_hub_dir, "Dockerfile")
        if not os.path.isfile(dockerfile_path):
            self._fail(
                "Ontology-Hub source directory not found",
                root_cause=(
                    f"Expected Dockerfile at: {dockerfile_path}. "
                    "The canonical checkout in adapters/inesdata/sources/Ontology-Hub is missing or incomplete."
                ),
            )

        build_args = self._ontology_hub_build_args(ontology_hub_dir)
        required = ("REPO_URL", "BRANCH_NAME", "REPO_NAME", "REPO_PATRONES")
        missing = [k for k in required if not (build_args.get(k) or "").strip()]
        if missing:
            self._fail(
                "Ontology-Hub build args are missing",
                root_cause=f"Missing keys: {', '.join(missing)} (see {os.path.join(ontology_hub_dir, 'docker-compose.yml')})",
            )

        image_q = shlex.quote(image_ref)
        arg_flags = " ".join(
            f"--build-arg {shlex.quote(f'{k}={v}')}"
            for k, v in build_args.items()
            if (v is not None and str(v).strip() != "")
        )

        print(f"\nBuilding local image on host for minikube: {image_ref}")
        cmd = f"docker build -t {image_q}"
        if arg_flags:
            cmd += f" {arg_flags}"
        cmd += " -f Dockerfile ."
        if self.run(cmd, check=False, cwd=ontology_hub_dir) is None:
            self._fail("Failed to build ontology-hub image on host", root_cause=image_ref)

    def _build_ai_model_hub_image_on_host(self, image_ref: str, deployer_config: dict):
        dashboard_dir = self._resolve_ai_model_hub_source_dir(deployer_config)
        dockerfile_path = os.path.join(dashboard_dir, "Dockerfile")
        if not os.path.isfile(dockerfile_path):
            self._fail(
                "AI Model Hub source directory not found",
                root_cause=(
                    f"Expected Dockerfile at: {dockerfile_path}. "
                    "The canonical checkout in adapters/inesdata/sources/AIModelHub is missing or incomplete."
                ),
            )

        image_q = shlex.quote(image_ref)
        print(f"\nBuilding local image on host for minikube: {image_ref}")
        cmd = f"docker build -t {image_q} ."
        if self.run(cmd, check=False, cwd=dashboard_dir) is None:
            self._fail("Failed to build AI Model Hub image on host", root_cause=image_ref)

    def _effective_component_values(self, normalized_component: str, values_file: str, deployer_config: dict) -> dict:
        values = dict(self._safe_load_yaml_file(values_file) or {})
        overrides = self._component_values_override_payload(normalized_component, deployer_config)

        image_overrides = overrides.get("image") or {}
        if image_overrides:
            image_values = dict(values.get("image") or {})
            image_values.update(image_overrides)
            values["image"] = image_values

        return values

    def _maybe_prepare_level6_local_image(self, normalized_component: str, values_file: str, deployer_config: dict) -> bool:
        """Ensure local images referenced by a Level 5 component exist in minikube.

        Returns True when the minikube image cache was updated.
        """
        values = self._effective_component_values(normalized_component, values_file, deployer_config)
        image_ref = self._extract_primary_image_ref(values)

        profile = (
            deployer_config.get("MINIKUBE_PROFILE")
            or getattr(self.config, "MINIKUBE_PROFILE", "minikube")
            or "minikube"
        ).strip() or "minikube"

        if normalized_component == "ontology-hub":
            if not image_ref:
                self._fail(
                    "Ontology-Hub chart image is not declared",
                    root_cause=f"Values file: {values_file}",
                )
            if not image_ref.lower().endswith(":local"):
                self._fail(
                    "Ontology-Hub must use a local image in Level 5/6",
                    root_cause=f"Configured image: {image_ref}",
                )
            if not self._minikube_is_available(profile):
                self._fail(
                    "Minikube profile is not available for Ontology-Hub local image deployment",
                    root_cause=profile,
                )
            self._build_ontology_hub_image_on_host(image_ref, deployer_config)
            self._load_image_into_minikube(profile, image_ref)
            return True

        auto_build_flag = deployer_config.get("LEVEL5_AUTO_BUILD_LOCAL_IMAGES")
        if auto_build_flag is None:
            auto_build_flag = deployer_config.get("LEVEL6_AUTO_BUILD_LOCAL_IMAGES")

        if not self._parse_bool(auto_build_flag, default=True):
            return False

        if not image_ref:
            return False

        if not image_ref.lower().endswith(":local"):
            return False

        if not self._minikube_is_available(profile):
            print(
                f"Local image '{image_ref}' referenced, but minikube profile '{profile}' is not available. "
                "Skipping auto-build."
            )
            return False

        if normalized_component == "ai-model-hub":
            self._build_ai_model_hub_image_on_host(image_ref, deployer_config)
            self._load_image_into_minikube(profile, image_ref)
            return True

        if self._minikube_has_image(profile, image_ref):
            return False

        print(f"Local image '{image_ref}' is missing in minikube, but no auto-build recipe exists for '{normalized_component}'.")
        return False

    def _infer_component_hostname(self, normalized_component: str, values_file: str, deployer_config: dict):
        """Infer component hostname (ingress host) from Helm values."""
        configured_host = self._configured_component_host(normalized_component, deployer_config)
        if configured_host:
            return configured_host

        try:
            values = self._safe_load_yaml_file(values_file)
        except Exception:
            return None

        ingress = (values or {}).get("ingress") or {}
        enabled = bool(ingress.get("enabled"))
        if not enabled:
            return None

        host = (ingress.get("host") or "").strip()
        if host:
            return host

        ds_name = (getattr(self.config, "DS_NAME", "") or "").strip()
        ds_domain = (deployer_config.get("DS_DOMAIN_BASE") or "").strip()
        if ds_name and ds_domain:
            return f"{normalized_component}-{ds_name}.{ds_domain}"

        return None

    def _configured_component_host(self, normalized_component: str, deployer_config: dict) -> str:
        normalized = self._normalize_component_key(normalized_component)

        env_key = normalized.upper().replace("-", "_")
        explicit = (
            deployer_config.get(f"{env_key}_HOST")
            or deployer_config.get(f"{env_key}_HOSTNAME")
            or deployer_config.get(f"{env_key}_URL")
        )
        explicit_host = self._strip_url_scheme(explicit)
        if explicit_host:
            return explicit_host

        if normalized == "ontology-hub":
            ds_domain = (deployer_config.get("DS_DOMAIN_BASE") or "").strip()
            ds_name = (getattr(self.config, "DS_NAME", "") or "").strip()
            if ds_domain and ds_name:
                return f"ontology-hub-{ds_name}.{ds_domain}"

        return ""

    def _component_values_override_payload(self, normalized_component: str, deployer_config: dict) -> dict:
        normalized = self._normalize_component_key(normalized_component)
        overrides = {}

        if normalized == "ontology-hub":
            host = self._configured_component_host(normalized, deployer_config)
            if host:
                base_url = self._to_http_url(host)
                overrides["ingress"] = {
                    "enabled": True,
                    "host": host,
                }
                overrides["env"] = {
                    "SELF_HOST_URL": base_url,
                    "BASE_URL": base_url,
                }
                host_alias_ip = self._resolve_ontology_hub_self_host_alias_ip(deployer_config)
                if host_alias_ip:
                    overrides["hostAliases"] = [
                        {
                            "ip": host_alias_ip,
                            "hostnames": [host],
                        }
                    ]

            if "ONTOLOGY_HUB_SAMPLE_DATA_ENABLED" in deployer_config:
                overrides.setdefault("sampleData", {})["enabled"] = self._parse_bool(
                    deployer_config.get("ONTOLOGY_HUB_SAMPLE_DATA_ENABLED"),
                    default=True,
                )

        return overrides

    def _resolve_ontology_hub_self_host_alias_ip(self, deployer_config: dict) -> str:
        explicit_ip = (deployer_config.get("ONTOLOGY_HUB_SELF_HOST_ALIAS_IP") or "").strip()
        if explicit_ip:
            return explicit_ip if self._is_ip_address(explicit_ip) else ""

        namespace = (
            deployer_config.get("ONTOLOGY_HUB_SELF_HOST_ALIAS_SERVICE_NAMESPACE")
            or "ingress-nginx"
        ).strip()
        service_name = (
            deployer_config.get("ONTOLOGY_HUB_SELF_HOST_ALIAS_SERVICE_NAME")
            or "ingress-nginx-controller"
        ).strip()
        if not namespace or not service_name:
            return ""

        svc_q = shlex.quote(service_name)
        ns_q = shlex.quote(namespace)
        ip = (
            self.run_silent(
                f"kubectl get svc {svc_q} -n {ns_q} -o jsonpath='{{.spec.clusterIP}}'"
            )
            or ""
        ).strip()
        return ip if self._is_ip_address(ip) else ""

    @staticmethod
    def _is_ip_address(value: str) -> bool:
        try:
            ipaddress.ip_address((value or "").strip())
            return True
        except ValueError:
            return False

    def _write_component_values_override_file(self, chart_dir: str, normalized_component: str, deployer_config: dict):
        payload = self._component_values_override_payload(normalized_component, deployer_config)
        if not payload:
            return None

        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f"{self._normalize_component_key(normalized_component)}-override-",
            suffix=".yaml",
            dir=chart_dir,
            delete=False,
        )
        try:
            yaml.safe_dump(payload, handle, sort_keys=False)
        finally:
            handle.close()
        return handle.name

    def _wait_for_pods_ready_by_selector(self, namespace: str, selector: str, timeout_seconds: int, label: str = "component") -> bool:
        namespace = (namespace or "").strip()
        selector = (selector or "").strip()
        if not namespace or not selector:
            return False

        ns_q = shlex.quote(namespace)
        sel_q = shlex.quote(selector)
        print(f"Waiting for {label} pods to be Running and Ready...")

        start = time.time()
        error_markers = (
            "ImagePullBackOff",
            "ErrImagePull",
            "CrashLoopBackOff",
            "CreateContainerConfigError",
            "RunContainerError",
        )

        while True:
            result = self.run_silent(f"kubectl get pods -n {ns_q} -l {sel_q} --no-headers")

            if result:
                all_ready = True
                for line in result.splitlines():
                    columns = line.split()
                    if len(columns) < 3:
                        continue

                    pod_name = columns[0]
                    ready = columns[1] if len(columns) > 1 else ""
                    status = columns[2]

                    if any(marker in status for marker in error_markers) or "BackOff" in status:
                        print(f"\nPod in error state: {pod_name} ({status})")
                        self.run(f"kubectl get pods -n {ns_q} -l {sel_q}", check=False)
                        self.run(f"kubectl describe pod -n {ns_q} {shlex.quote(pod_name)}", check=False)
                        return False

                    if status == "Completed":
                        continue

                    if status != "Running":
                        all_ready = False
                        break

                    if "/" in ready:
                        ready_current, ready_total = ready.split("/", 1)
                        if ready_current != ready_total:
                            all_ready = False
                            break
                    else:
                        all_ready = False
                        break

                if all_ready:
                    print(f"\n{label} pods are Running and Ready\n")
                    self.run(f"kubectl get pods -n {ns_q} -l {sel_q}", check=False)
                    return True

            if time.time() - start > timeout_seconds:
                print(f"\nTimeout waiting for {label} pods to be ready\n")
                self.run(f"kubectl get pods -n {ns_q} -l {sel_q}", check=False)
                return False

            time.sleep(2)

    def _wait_for_component_rollout(self, namespace: str, deployment_name: str, timeout_seconds: int, label: str) -> bool:
        rollout_waiter = getattr(self.infrastructure, "wait_for_deployment_rollout", None)
        if callable(rollout_waiter):
            return bool(
                rollout_waiter(
                    namespace,
                    deployment_name,
                    timeout_seconds=timeout_seconds,
                    label=label,
                )
            )

        selector = f"app.kubernetes.io/instance={deployment_name}"
        return self._wait_for_pods_ready_by_selector(
            namespace,
            selector,
            timeout_seconds=timeout_seconds,
            label=label,
        )

    def deploy_components(self, components):
        return self.COMPONENTS(components)

    def infer_component_urls(self, components):
        if not components:
            return {}

        ds_name = self._dataspace_name()
        namespace = self.config.namespace_demo()
        deployer_config = self.config_adapter.load_deployer_config() or {}

        inferred_hosts = {}
        for component in components:
            normalized = self._normalize_component_key(component)
            if normalized in self._LEVEL6_EXCLUDED_KEYS:
                continue
            try:
                chart_dir = self._resolve_component_chart_dir(normalized)
                values_file = self._resolve_component_values_file(chart_dir, ds_name=ds_name, namespace=namespace)
                host = self._infer_component_hostname(normalized, values_file, deployer_config)
            except Exception:
                host = None

            if host:
                inferred_hosts[normalized] = host

        return {k: self._to_http_url(v) for k, v in inferred_hosts.items() if v}

    def COMPONENTS(self, components):
        if not components:
            print("No components selected for deployment")
            return {"deployed": [], "urls": {}}

        repo_dir = self.config.repo_dir()
        if not os.path.exists(repo_dir):
            self._fail("Repository not found. Run Level 2 first")

        if not self.infrastructure.ensure_local_infra_access():
            self._fail("Local access to PostgreSQL/Vault is not available")

        if not self.infrastructure.ensure_vault_unsealed():
            self._fail("Vault is not initialized or unsealed")

        reconcile_vault_state = getattr(self.infrastructure, "reconcile_vault_state_for_local_runtime", None)
        if callable(reconcile_vault_state) and not reconcile_vault_state():
            self._fail("Vault token could not be synchronized with the shared local runtime")

        ds_name = self._dataspace_name()
        namespace = self.config.namespace_demo()

        deployer_config = self.config_adapter.load_deployer_config() or {}
        self._cleanup_components(components, namespace)

        inferred_hosts = {}
        for component in components:
            normalized = self._normalize_component_key(component)
            if normalized in self._LEVEL6_EXCLUDED_KEYS:
                continue

            try:
                chart_dir = self._resolve_component_chart_dir(normalized)
                values_file = self._resolve_component_values_file(chart_dir, ds_name=ds_name, namespace=namespace)
                host = self._infer_component_hostname(normalized, values_file, deployer_config)
            except Exception:
                host = None

            if host:
                inferred_hosts[normalized] = host

        if inferred_hosts:
            print("\nComponent hostnames inferred from values:")
            for host in sorted(set(inferred_hosts.values())):
                print(f"- {host}")

            desired_entries = [f"127.0.0.1 {h}" for h in sorted(set(inferred_hosts.values()))]
            self.infrastructure.manage_hosts_entries(
                desired_entries,
                header_comment="# Components",
                auto_confirm=True,
            )

        deployed = []
        for component in components:
            normalized = self._normalize_component_key(component)

            if normalized in self._LEVEL6_EXCLUDED_KEYS:
                self._fail(
                    f"'{normalized}' is part of the base dataspace and must not be deployed via Level 5. "
                    "Deploy it via Level 3 (dataspace) and remove it from COMPONENTS."
                )

            chart_dir = self._resolve_component_chart_dir(normalized)
            values_file = self._resolve_component_values_file(chart_dir, ds_name=ds_name, namespace=namespace)
            release_name = self._resolve_component_release_name(normalized)
            override_values_file = None

            built_local_image = False
            try:
                built_local_image = self._maybe_prepare_level6_local_image(normalized, values_file, deployer_config)
            except Exception as exc:
                self._fail(
                    f"Error preparing local images for component '{normalized}'",
                    root_cause=str(exc),
                )

            print(f"\nDeploying component: {normalized}")
            print(f"  Chart: {chart_dir}")
            print(f"  Values: {os.path.basename(values_file)}")
            print(f"  Release: {release_name}")
            print(f"  Namespace: {namespace}")
            try:
                override_values_file = self._write_component_values_override_file(
                    chart_dir,
                    normalized,
                    deployer_config,
                )
                values_files = [os.path.basename(values_file)]
                if override_values_file:
                    values_files.append(override_values_file)
                    print(f"  Override values: {os.path.basename(override_values_file)}")

                if not self.infrastructure.deploy_helm_release(
                    release_name,
                    namespace,
                    values_files,
                    cwd=chart_dir,
                ):
                    self._fail(f"Error deploying component '{normalized}'")
            finally:
                if override_values_file and os.path.exists(override_values_file):
                    os.unlink(override_values_file)

            if built_local_image:
                print(f"Restarting deployment/{release_name} to pick up local image...\n")
                self.run(
                    f"kubectl rollout restart deployment/{release_name} -n {namespace}",
                    check=False,
                )

            if normalized == "ontology-hub":
                timeout_seconds = 1800
                if not self._wait_for_component_rollout(
                    namespace,
                    release_name,
                    timeout_seconds=timeout_seconds,
                    label=normalized,
                ):
                    self._fail(f"Timeout waiting for component '{normalized}' deployment rollout")

            deployed.append(normalized)

        urls = {k: self._to_http_url(v) for k, v in inferred_hosts.items() if v}
        return {"deployed": deployed, "urls": urls}

    def describe(self) -> str:
        return "INESDataComponentsAdapter deploys optional components via Helm charts."
