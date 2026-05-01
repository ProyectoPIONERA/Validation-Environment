from __future__ import annotations

from typing import Any

from .topology import LOCAL_TOPOLOGY, VM_DISTRIBUTED_TOPOLOGY, VM_SINGLE_TOPOLOGY, normalize_topology


MINIKUBE_CLUSTER_TYPE = "minikube"
K3S_CLUSTER_TYPE = "k3s"
SUPPORTED_CLUSTER_TYPES = (MINIKUBE_CLUSTER_TYPE, K3S_CLUSTER_TYPE)

DEFAULT_CLUSTER_TYPE_BY_TOPOLOGY = {
    LOCAL_TOPOLOGY: MINIKUBE_CLUSTER_TYPE,
    VM_SINGLE_TOPOLOGY: MINIKUBE_CLUSTER_TYPE,
    VM_DISTRIBUTED_TOPOLOGY: K3S_CLUSTER_TYPE,
}

DEFAULT_K3S_KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"


def normalize_cluster_type(value: Any = None, topology: str = LOCAL_TOPOLOGY) -> str:
    """Return a supported cluster runtime, preserving current Minikube defaults."""

    normalized_topology = normalize_topology(topology)
    fallback = DEFAULT_CLUSTER_TYPE_BY_TOPOLOGY.get(normalized_topology, MINIKUBE_CLUSTER_TYPE)
    cluster_type = str(value or fallback).strip().lower() or fallback
    if cluster_type not in SUPPORTED_CLUSTER_TYPES:
        supported = ", ".join(SUPPORTED_CLUSTER_TYPES)
        raise ValueError(f"Unsupported cluster runtime '{cluster_type}'. Supported runtimes: {supported}")
    return cluster_type


def build_cluster_runtime(config: dict[str, Any] | None = None, topology: str = LOCAL_TOPOLOGY) -> dict[str, str]:
    """Resolve cluster runtime settings from layered deployer configuration."""

    values = dict(config or {})
    cluster_type = normalize_cluster_type(values.get("CLUSTER_TYPE"), topology=topology)
    k3s_kubeconfig = str(values.get("K3S_KUBECONFIG") or DEFAULT_K3S_KUBECONFIG).strip()
    return {
        "cluster_type": cluster_type,
        "k3s_kubeconfig": k3s_kubeconfig or DEFAULT_K3S_KUBECONFIG,
    }
