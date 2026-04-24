"""Common contracts and helpers for deployer-based orchestration."""

from .config_loader import (
    apply_pionera_environment_overrides,
    iter_dataspace_slots,
    load_deployer_config,
    load_layered_deployer_config,
)
from .contracts import DeploymentContext, NamespaceRoles, TopologyProfile, ValidationProfile
from .hosts_manager import (
    HostBlock,
    HostEntry,
    apply_managed_blocks,
    blocks_as_dict,
    build_context_host_blocks,
    hostnames_by_level,
    merge_missing_managed_blocks,
    parse_hostnames,
    remove_managed_blocks,
    render_managed_block,
    upsert_managed_block,
    upsert_managed_blocks,
)
from .namespaces import (
    COMPACT_NAMESPACE_PROFILE,
    ROLE_ALIGNED_NAMESPACE_PROFILE,
    SUPPORTED_NAMESPACE_PROFILES,
    normalize_namespace_profile,
    resolve_namespace_profile_plan,
)
from .orchestrator import DeployerOrchestrator
from .topology import SUPPORTED_TOPOLOGIES, build_topology_profile, normalize_topology

__all__ = [
    "DeploymentContext",
    "DeployerOrchestrator",
    "HostBlock",
    "HostEntry",
    "NamespaceRoles",
    "COMPACT_NAMESPACE_PROFILE",
    "ROLE_ALIGNED_NAMESPACE_PROFILE",
    "SUPPORTED_NAMESPACE_PROFILES",
    "SUPPORTED_TOPOLOGIES",
    "TopologyProfile",
    "ValidationProfile",
    "apply_managed_blocks",
    "blocks_as_dict",
    "build_context_host_blocks",
    "build_topology_profile",
    "hostnames_by_level",
    "iter_dataspace_slots",
    "load_deployer_config",
    "apply_pionera_environment_overrides",
    "load_layered_deployer_config",
    "merge_missing_managed_blocks",
    "normalize_namespace_profile",
    "normalize_topology",
    "parse_hostnames",
    "remove_managed_blocks",
    "render_managed_block",
    "resolve_namespace_profile_plan",
    "upsert_managed_block",
    "upsert_managed_blocks",
]
