"""Stable generic EDC adapter facade import path."""

import json

from adapters.inesdata.adapter import InesdataAdapter
from adapters.inesdata.infrastructure import INESDataInfrastructureAdapter

from .config import EDCConfigAdapter, EdcConfig
from .connectors import EDCConnectorsAdapter
from .deployment import EDCDeploymentAdapter


class EdcAdapter(InesdataAdapter):
    """Facade for generic EDC deployment and validation integration."""

    def __init__(self, run=None, run_silent=None, auto_mode_getter=lambda: False, config_cls=None, dry_run=False, topology="local"):
        resolved_config = config_cls or EdcConfig
        super().__init__(
            run=run,
            run_silent=run_silent,
            auto_mode_getter=auto_mode_getter,
            config_cls=resolved_config,
            dry_run=dry_run,
        )

        self.topology = topology or resolved_config.DEFAULT_TOPOLOGY
        self.config = resolved_config
        self.config_adapter = EDCConfigAdapter(self.config, topology=self.topology)
        self.infrastructure = INESDataInfrastructureAdapter(
            run=self.run,
            run_silent=self.run_silent,
            auto_mode_getter=self.auto_mode_getter,
            config_adapter=self.config_adapter,
            config_cls=self.config,
        )
        self.deployment = EDCDeploymentAdapter(
            run=self.run,
            run_silent=self.run_silent,
            auto_mode_getter=self.auto_mode_getter,
            infrastructure_adapter=self.infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
            topology=self.topology,
        )
        self.connectors = EDCConnectorsAdapter(
            run=self.run,
            run_silent=self.run_silent,
            auto_mode_getter=self.auto_mode_getter,
            infrastructure_adapter=self.infrastructure,
            config_adapter=self.config_adapter,
            config_cls=self.config,
            topology=self.topology,
        )
        self.deployment.connectors_adapter = self.connectors
        self.connectors.deployment_adapter = self.deployment

    def deploy_infrastructure(self):
        common_ready, _ = self.infrastructure.verify_common_services_ready_for_level3()
        if common_ready:
            self.infrastructure.announce_level(2, "DEPLOY COMMON SERVICES")
            print("Existing shared common services are already ready for Level 3. Reusing them for EDC mode.")
            self.infrastructure.complete_level(2)
            return True
        return self.infrastructure.deploy_infrastructure()

    def _preview_common_services(self):
        namespace = self.config.NS_COMMON
        pod_output = self.run_silent(f"kubectl get pods -n {namespace} --no-headers") or ""
        ignored_hook_pod = getattr(self.infrastructure, "_is_ignored_transient_hook_pod", None)
        services = {
            "keycloak": {"pod": None, "status": "missing", "ready": False},
            "minio": {"pod": None, "status": "missing", "ready": False},
            "postgresql": {"pod": None, "status": "missing", "ready": False},
            "vault": {"pod": None, "status": "missing", "ready": False},
        }
        prefixes = {
            "keycloak": "common-srvs-keycloak-",
            "minio": "common-srvs-minio-",
            "postgresql": "common-srvs-postgresql-",
            "vault": "common-srvs-vault-",
        }

        for line in pod_output.splitlines():
            columns = line.split()
            if len(columns) < 3:
                continue

            pod_name = columns[0]
            ready = columns[1]
            status = columns[2]

            if callable(ignored_hook_pod) and ignored_hook_pod(namespace, pod_name):
                continue

            for service_name, prefix in prefixes.items():
                if not pod_name.startswith(prefix):
                    continue
                ready_flag = False
                if "/" in ready:
                    ready_current, ready_total = ready.split("/", 1)
                    ready_flag = status == "Running" and ready_current == ready_total

                candidate = {
                    "pod": pod_name,
                    "status": status,
                    "ready": ready_flag,
                }
                current = services[service_name]
                if current["pod"] is None or candidate["ready"] or (
                    not current["ready"]
                    and candidate["status"] == "Running"
                    and current["status"] != "Running"
                ):
                    services[service_name] = candidate
                break

        vault_state = {
            "pod": services["vault"]["pod"],
            "initialized": None,
            "sealed": None,
            "ready": False,
        }
        if services["vault"]["pod"]:
            raw_status = self.run_silent(
                f"kubectl exec {services['vault']['pod']} -n {namespace} -- vault status -format=json"
            )
            if raw_status:
                try:
                    payload = json.loads(raw_status)
                except json.JSONDecodeError:
                    payload = None
                if payload:
                    vault_state["initialized"] = bool(payload.get("initialized"))
                    vault_state["sealed"] = bool(payload.get("sealed"))
                    vault_state["ready"] = vault_state["initialized"] and not vault_state["sealed"]

        issues = []
        for service_name, state in services.items():
            if not state["pod"]:
                issues.append(f"{service_name} pod not found in namespace {namespace}")
            elif not state["ready"] and service_name != "vault":
                issues.append(f"{service_name} pod is not ready (status={state['status']})")

        if services["vault"]["pod"] and not vault_state["ready"]:
            issues.append("Vault is present but not initialized/unsealed")

        ready = (
            services["keycloak"]["ready"]
            and services["minio"]["ready"]
            and services["postgresql"]["ready"]
            and services["vault"]["pod"] is not None
            and vault_state["ready"]
        )

        return {
            "status": "ready" if ready else "missing",
            "action": "reuse" if ready else "deploy_infrastructure",
            "namespace": namespace,
            "services": services,
            "vault": vault_state,
            "issues": issues,
        }

    def _preview_dataspace(self):
        namespace = self.config.namespace_demo()
        ds_name = self.config.dataspace_name()
        pod_output = self.run_silent(f"kubectl get pods -n {namespace} --no-headers") or ""
        pod_names = []
        for line in pod_output.splitlines():
            columns = line.split()
            if columns:
                pod_names.append(columns[0])

        registration_pod = self.infrastructure.get_pod_by_name(namespace, "registration-service")
        schema_ready = False
        if registration_pod:
            schema_ready = bool(
                self.infrastructure.wait_for_registration_service_schema(
                    timeout=1,
                    poll_interval=1,
                    quiet=True,
                )
            )

        issues = []
        if not pod_names:
            issues.append(f"No pods detected in namespace {namespace}")
        if not registration_pod:
            issues.append("registration-service pod not found")
        elif not schema_ready:
            issues.append("registration-service schema is not ready yet")

        ready = bool(pod_names) and bool(registration_pod) and schema_ready
        return {
            "status": "ready" if ready else "missing",
            "action": "reuse" if ready else "deploy_dataspace",
            "dataspace": ds_name,
            "namespace": namespace,
            "registration_service_pod": registration_pod,
            "schema_ready": schema_ready,
            "pod_count": len(pod_names),
            "issues": issues,
        }

    def preview_deploy(self):
        common_services = self._preview_common_services()
        dataspace = self._preview_dataspace()
        connectors = self.connectors.preview_deploy_connectors()

        if connectors.get("status") == "blocked":
            status = "blocked"
            next_step = "Use an isolated dataspace configuration or remove the conflicting runtime resources before deploying EDC."
        elif common_services["status"] != "ready":
            status = "shared-services-required"
            next_step = "Deploy or repair the shared common services before running the EDC connector deployment."
        elif dataspace["status"] != "ready":
            status = "dataspace-required"
            next_step = "Deploy or repair the shared dataspace services before running the EDC connector deployment."
        elif connectors.get("status") == "bootstrap-required":
            status = "bootstrap-required"
            next_step = "Create the connector bootstrap artifacts first so the final EDC values files can be rendered."
        else:
            status = "ready"
            next_step = "The local shared foundation is reusable and the EDC connector chart is ready to deploy."

        return {
            "status": status,
            "topology": self.topology,
            "shared_common_services": common_services,
            "shared_dataspace": dataspace,
            "connectors": connectors,
            "next_step": next_step,
        }
