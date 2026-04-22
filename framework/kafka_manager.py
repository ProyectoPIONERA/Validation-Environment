import os
import socket
import subprocess
import time
from textwrap import dedent

from .kafka_container_factory import KafkaContainerFactory
from .kafka_testcontainer import FrameworkKafkaContainer


class KafkaManager:
    """Ensures a Kafka broker is available for optional benchmarks."""

    def __init__(
        self,
        bootstrap_servers=None,
        runtime_config=None,
        adapter_config_loader=None,
        container_class=None,
        container_factory=None,
        command_runner=None,
        image="confluentinc/cp-kafka:latest",
        wait_timeout_seconds=60,
        poll_interval_seconds=1,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.runtime_config = runtime_config or {}
        self.adapter_config_loader = adapter_config_loader
        self.container_class = container_class
        self.container_factory = container_factory or KafkaContainerFactory()
        self.command_runner = command_runner or self._default_command_runner
        self.image = image
        self.wait_timeout_seconds = wait_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.container = None
        self.port_forward_process = None
        self.started_by_framework = False
        self.last_error = None
        self.cluster_bootstrap_servers = None
        self.provisioning_mode = None

    @staticmethod
    def _default_command_runner(args, input_text=None):
        return subprocess.run(
            args,
            text=True,
            input=input_text,
            capture_output=True,
            check=False,
        )

    def _load_adapter_config(self):
        if callable(self.adapter_config_loader):
            config = self.adapter_config_loader()
            return config if isinstance(config, dict) else {}
        if isinstance(self.adapter_config_loader, dict):
            return self.adapter_config_loader
        return {}

    def _candidate_bootstrap_servers(self):
        candidates = []
        env_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
        adapter_bootstrap = self._load_adapter_config().get("bootstrap_servers")
        runtime_bootstrap = self.runtime_config.get("bootstrap_servers")

        for candidate in (env_bootstrap, runtime_bootstrap, adapter_bootstrap, self.bootstrap_servers):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    def _load_manager_config(self):
        config = {}
        config.update(self._load_adapter_config())
        config.update(self.runtime_config)
        config.setdefault("provisioner", config.get("provisioner") or "kubernetes")
        config.setdefault("cluster_advertised_host", config.get("cluster_advertised_host") or "host.minikube.internal")
        config.setdefault("k8s_namespace", config.get("k8s_namespace") or "demo")
        config.setdefault("k8s_service_name", config.get("k8s_service_name") or "framework-kafka")
        config.setdefault("k8s_nodeport", config.get("k8s_nodeport") or "32092")
        config.setdefault("k8s_local_port", config.get("k8s_local_port") or config.get("k8s_nodeport") or "39092")
        config.setdefault("minikube_profile", config.get("minikube_profile") or "minikube")
        return config

    def _provisioner(self):
        return str(self._load_manager_config().get("provisioner") or "kubernetes").strip().lower()

    @staticmethod
    def _normalize_bootstrap_servers(bootstrap_servers):
        if bootstrap_servers is None:
            return []
        if isinstance(bootstrap_servers, (list, tuple, set)):
            values = bootstrap_servers
        else:
            values = str(bootstrap_servers).split(",")
        return [value.strip() for value in values if str(value).strip()]

    @staticmethod
    def _parse_host_port(address):
        address = str(address).strip()
        if "://" in address:
            address = address.split("://", 1)[1]
        if address.count(":") > 1 and address.startswith("["):
            host, _, port = address.rpartition(":")
            return host.strip("[]"), int(port or 9092)
        if ":" in address:
            host, port = address.rsplit(":", 1)
            return host, int(port or 9092)
        return address, 9092

    @classmethod
    def is_kafka_available(cls, bootstrap_servers):
        """Attempt a basic TCP connection to determine broker availability."""
        for address in cls._normalize_bootstrap_servers(bootstrap_servers):
            try:
                host, port = cls._parse_host_port(address)
                with socket.create_connection((host, port), timeout=2):
                    return True
            except Exception:
                continue
        return False

    def _load_container_class(self):
        if self.container_class is not None:
            return self.container_class

        try:
            return FrameworkKafkaContainer
        except Exception as exc:
            raise RuntimeError(
                f"testcontainers Kafka support is not available: {exc}"
            ) from exc

    def _run_command(self, args, input_text=None):
        result = self.command_runner(args, input_text=input_text)
        if getattr(result, "returncode", 1) != 0:
            stdout = (getattr(result, "stdout", "") or "").strip()
            stderr = (getattr(result, "stderr", "") or "").strip()
            combined = "\n".join(part for part in (stdout, stderr) if part).strip()
            raise RuntimeError(combined or f"Command failed: {' '.join(args)}")
        return result

    def _resolve_minikube_ip(self, config):
        configured_ip = str(config.get("minikube_ip") or "").strip()
        if configured_ip:
            return configured_ip
        profile = str(config.get("minikube_profile") or "minikube").strip() or "minikube"
        try:
            result = self._run_command(["minikube", "-p", profile, "ip"])
            resolved_ip = (getattr(result, "stdout", "") or "").strip()
            if resolved_ip:
                return resolved_ip
        except Exception:
            pass
        return "192.168.49.2"

    def _kubernetes_identifiers(self, config):
        namespace = str(config.get("k8s_namespace") or "demo").strip() or "demo"
        service_name = str(config.get("k8s_service_name") or "framework-kafka").strip() or "framework-kafka"
        local_port = int(str(config.get("k8s_local_port") or "39092").strip() or "39092")
        internal_bootstrap = f"{service_name}.{namespace}.svc.cluster.local:9092"
        external_bootstrap = f"127.0.0.1:{local_port}"
        return {
            "namespace": namespace,
            "service_name": service_name,
            "external_service_name": f"{service_name}-external",
            "deployment_name": service_name,
            "local_port": local_port,
            "internal_bootstrap": internal_bootstrap,
            "external_bootstrap": external_bootstrap,
        }

    @staticmethod
    def _kubernetes_cluster_id():
        return "MkU3OEVBNTcwNTJENDM2Qk"

    def _build_kubernetes_manifest(self, config):
        ids = self._kubernetes_identifiers(config)
        image = str(config.get("container_image") or self.image)
        service_name = ids["service_name"]
        deployment_name = ids["deployment_name"]
        namespace = ids["namespace"]
        external_service_name = ids["external_service_name"]
        external_bootstrap = ids["external_bootstrap"]
        internal_bootstrap = ids["internal_bootstrap"]
        cluster_id = self._kubernetes_cluster_id()
        return dedent(
            f"""
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: {deployment_name}
              namespace: {namespace}
              labels:
                app: {service_name}
                managed-by: inesdata-framework
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app: {service_name}
              template:
                metadata:
                  labels:
                    app: {service_name}
                    managed-by: inesdata-framework
                spec:
                  containers:
                  - name: kafka
                    image: {image}
                    imagePullPolicy: IfNotPresent
                    ports:
                    - containerPort: 9092
                      name: internal
                    - containerPort: 9093
                      name: controller
                    - containerPort: 9094
                      name: external
                    env:
                    - name: CLUSTER_ID
                      value: "{cluster_id}"
                    - name: KAFKA_NODE_ID
                      value: "1"
                    - name: KAFKA_PROCESS_ROLES
                      value: "broker,controller"
                    - name: KAFKA_LISTENERS
                      value: "INTERNAL://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,EXTERNAL://0.0.0.0:9094"
                    - name: KAFKA_ADVERTISED_LISTENERS
                      value: "INTERNAL://{internal_bootstrap},EXTERNAL://{external_bootstrap}"
                    - name: KAFKA_LISTENER_SECURITY_PROTOCOL_MAP
                      value: "INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT,EXTERNAL:PLAINTEXT"
                    - name: KAFKA_INTER_BROKER_LISTENER_NAME
                      value: "INTERNAL"
                    - name: KAFKA_CONTROLLER_LISTENER_NAMES
                      value: "CONTROLLER"
                    - name: KAFKA_CONTROLLER_QUORUM_VOTERS
                      value: "1@localhost:9093"
                    - name: KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR
                      value: "1"
                    - name: KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR
                      value: "1"
                    - name: KAFKA_TRANSACTION_STATE_LOG_MIN_ISR
                      value: "1"
                    - name: KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS
                      value: "0"
                    - name: KAFKA_AUTO_CREATE_TOPICS_ENABLE
                      value: "true"
                    - name: KAFKA_LOG_DIRS
                      value: "/var/lib/kafka/data/kraft-combined-logs"
                    readinessProbe:
                      tcpSocket:
                        port: 9092
                      initialDelaySeconds: 10
                      periodSeconds: 5
                    livenessProbe:
                      tcpSocket:
                        port: 9092
                      initialDelaySeconds: 20
                      periodSeconds: 10
                    volumeMounts:
                    - name: kafka-data
                      mountPath: /var/lib/kafka/data
                  volumes:
                  - name: kafka-data
                    emptyDir: {{}}
            ---
            apiVersion: v1
            kind: Service
            metadata:
              name: {service_name}
              namespace: {namespace}
              labels:
                app: {service_name}
                managed-by: inesdata-framework
            spec:
              selector:
                app: {service_name}
              ports:
              - name: internal
                port: 9092
                targetPort: 9092
              type: ClusterIP
            ---
            apiVersion: v1
            kind: Service
            metadata:
              name: {external_service_name}
              namespace: {namespace}
              labels:
                app: {service_name}
                managed-by: inesdata-framework
            spec:
              selector:
                app: {service_name}
              ports:
              - name: external
                port: 9094
                targetPort: 9094
              type: ClusterIP
            """
        ).strip()

    def _start_kubernetes_port_forward(self, ids):
        if self.port_forward_process is not None and self.port_forward_process.poll() is None:
            return self.port_forward_process

        command = [
            "kubectl",
            "port-forward",
            "-n",
            ids["namespace"],
            f"service/{ids['external_service_name']}",
            f"{ids['local_port']}:9094",
        ]
        self.port_forward_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            # kubectl port-forward writes connection traces to stderr; if that
            # stream is piped but never drained, the forward can block mid-run.
            stderr=subprocess.DEVNULL,
            text=True,
        )

        deadline = time.time() + self.wait_timeout_seconds
        while time.time() < deadline:
            if self.port_forward_process.poll() is not None:
                raise RuntimeError("Kafka port-forward process exited unexpectedly")
            if self.is_kafka_available(ids["external_bootstrap"]):
                return self.port_forward_process
            time.sleep(self.poll_interval_seconds)

        raise RuntimeError("Kafka port-forward did not expose the external bootstrap server in time")

    def _list_kubernetes_probe_pods(self, namespace, excluded_prefixes=None):
        excluded_prefixes = tuple(excluded_prefixes or ())
        result = self._run_command(["kubectl", "get", "pods", "-n", namespace, "--no-headers"])
        pods = []
        for line in (getattr(result, "stdout", "") or "").splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            name, ready, status = parts[0], parts[1], parts[2]
            if excluded_prefixes and any(name.startswith(prefix) for prefix in excluded_prefixes):
                continue
            if status != "Running":
                continue
            if "/" in ready:
                try:
                    ready_count, total_count = ready.split("/", 1)
                    if int(ready_count) < int(total_count):
                        continue
                except Exception:
                    pass
            pods.append(name)
        return pods

    def _wait_for_kubernetes_internal_bootstrap(self, ids):
        host, port = self._parse_host_port(ids["internal_bootstrap"])
        deadline = time.time() + self.wait_timeout_seconds
        excluded_prefixes = (ids["deployment_name"],)

        while time.time() < deadline:
            try:
                pods = self._list_kubernetes_probe_pods(ids["namespace"], excluded_prefixes=excluded_prefixes)
            except Exception:
                pods = []

            preferred_pods = [pod for pod in pods if pod.startswith("conn-")]
            candidate_pods = preferred_pods or pods

            for pod_name in candidate_pods:
                probe_command = (
                    f"timeout 3 bash -lc '</dev/tcp/{host}/{port}'"
                )
                result = self.command_runner(
                    [
                        "kubectl",
                        "exec",
                        "-n",
                        ids["namespace"],
                        pod_name,
                        "--",
                        "bash",
                        "-lc",
                        probe_command,
                    ]
                )
                if getattr(result, "returncode", 1) == 0:
                    return {
                        "pod": pod_name,
                        "host": host,
                        "port": port,
                    }
            time.sleep(self.poll_interval_seconds)

        raise RuntimeError("Kafka internal bootstrap server did not become reachable from namespace pods in time")

    def _start_kafka_kubernetes(self):
        config = self._load_manager_config()
        manifest = self._build_kubernetes_manifest(config)
        ids = self._kubernetes_identifiers(config)

        self._run_command(["kubectl", "apply", "-f", "-"], input_text=manifest)
        self._run_command(
            [
                "kubectl",
                "rollout",
                "status",
                f"deployment/{ids['deployment_name']}",
                "-n",
                ids["namespace"],
                f"--timeout={self.wait_timeout_seconds}s",
            ]
        )
        self._start_kubernetes_port_forward(ids)
        self._wait_for_kubernetes_internal_bootstrap(ids)

        deadline = time.time() + self.wait_timeout_seconds
        while time.time() < deadline:
            if self.is_kafka_available(ids["external_bootstrap"]):
                self.container = None
                self.started_by_framework = True
                self.bootstrap_servers = ids["external_bootstrap"]
                self.cluster_bootstrap_servers = ids["internal_bootstrap"]
                self.provisioning_mode = "kubernetes"
                self.last_error = None
                return ids["external_bootstrap"]
            time.sleep(self.poll_interval_seconds)

        raise RuntimeError("Kafka Kubernetes broker was deployed but the external bootstrap server did not become reachable in time")

    def _start_kafka_container(self):
        """Start a Kafka container and wait until the broker becomes available."""
        container_class = self._load_container_class()
        container = self.container_factory.create_container(
            container_class,
            self.image,
            config=self._load_manager_config(),
        )
        container.start()

        bootstrap_servers = None
        get_bootstrap_server = getattr(container, "get_bootstrap_server", None)
        get_cluster_bootstrap_server = getattr(container, "get_cluster_bootstrap_server", None)
        if callable(get_bootstrap_server):
            bootstrap_servers = get_bootstrap_server()
        else:
            bootstrap_servers = getattr(container, "bootstrap_servers", None)
        cluster_bootstrap_servers = None
        if callable(get_cluster_bootstrap_server):
            cluster_bootstrap_servers = get_cluster_bootstrap_server()

        deadline = time.time() + self.wait_timeout_seconds
        while time.time() < deadline:
            if bootstrap_servers and self.is_kafka_available(bootstrap_servers):
                self.container = container
                self.started_by_framework = True
                self.bootstrap_servers = bootstrap_servers
                self.cluster_bootstrap_servers = cluster_bootstrap_servers
                self.provisioning_mode = "docker"
                self.last_error = None
                return bootstrap_servers
            time.sleep(self.poll_interval_seconds)

        stop_method = getattr(container, "stop", None)
        if callable(stop_method):
            stop_method()
        raise RuntimeError("Kafka container started but broker did not become available in time")

    def start_kafka(self):
        if self._provisioner() == "kubernetes":
            return self._start_kafka_kubernetes()
        return self._start_kafka_container()

    def ensure_kafka_running(self):
        """Return reachable bootstrap servers or try to auto-start Kafka."""
        previous_bootstrap_servers = self.bootstrap_servers
        previous_cluster_bootstrap_servers = self.cluster_bootstrap_servers
        previous_started_by_framework = self.started_by_framework
        previous_provisioning_mode = self.provisioning_mode
        for candidate in self._candidate_bootstrap_servers():
            if self.is_kafka_available(candidate):
                self.bootstrap_servers = candidate
                explicit_cluster_bootstrap_servers = self._load_manager_config().get("cluster_bootstrap_servers")
                if explicit_cluster_bootstrap_servers:
                    self.cluster_bootstrap_servers = explicit_cluster_bootstrap_servers
                elif candidate == previous_bootstrap_servers and previous_cluster_bootstrap_servers:
                    self.cluster_bootstrap_servers = previous_cluster_bootstrap_servers
                else:
                    self.cluster_bootstrap_servers = None
                framework_managed_kubernetes = (
                    previous_provisioning_mode == "kubernetes"
                    and self.port_forward_process is not None
                    and self.port_forward_process.poll() is None
                )
                self.started_by_framework = (
                    previous_started_by_framework
                    and candidate == previous_bootstrap_servers
                    and (self.container is not None or framework_managed_kubernetes)
                )
                self.last_error = None
                return candidate

        try:
            return self.start_kafka()
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[WARNING] Kafka auto-provisioning failed: {exc}")
            return None

    def stop_kafka(self):
        """Stop the Kafka container only if it was started by the framework."""
        if not self.started_by_framework or self.container is None:
            if self.started_by_framework and self.provisioning_mode == "kubernetes":
                config = self._load_manager_config()
                ids = self._kubernetes_identifiers(config)
                try:
                    if self.port_forward_process is not None:
                        self.port_forward_process.terminate()
                        try:
                            self.port_forward_process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            self.port_forward_process.kill()
                    self._run_command(
                        [
                            "kubectl",
                            "delete",
                            f"deployment/{ids['deployment_name']}",
                            f"service/{ids['service_name']}",
                            f"service/{ids['external_service_name']}",
                            "-n",
                            ids["namespace"],
                            "--ignore-not-found=true",
                        ]
                    )
                except Exception as exc:
                    print(f"[WARNING] Failed to stop Kafka Kubernetes broker cleanly: {exc}")
                finally:
                    self.port_forward_process = None
                    self.started_by_framework = False
                    self.cluster_bootstrap_servers = None
                    self.provisioning_mode = None
            return

        try:
            stop_method = getattr(self.container, "stop", None)
            if callable(stop_method):
                stop_method()
        except Exception as exc:
            print(f"[WARNING] Failed to stop Kafka container cleanly: {exc}")
        finally:
            self.container = None
            self.port_forward_process = None
            self.started_by_framework = False
            self.cluster_bootstrap_servers = None
            self.provisioning_mode = None

    def describe(self) -> str:
        return "KafkaManager ensures a Kafka broker is available for benchmarks."

