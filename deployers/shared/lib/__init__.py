"""Common contracts and helpers for deployer-based orchestration."""

from .config_loader import (
    apply_pionera_environment_overrides,
    iter_dataspace_slots,
    load_deployer_config,
    load_layered_deployer_config,
)
from .contracts import DeploymentContext, NamespaceRoles, ValidationProfile
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
from .orchestrator import DeployerOrchestrator

__all__ = [
    "DeploymentContext",
    "DeployerOrchestrator",
    "HostBlock",
    "HostEntry",
    "NamespaceRoles",
    "ValidationProfile",
    "apply_managed_blocks",
    "blocks_as_dict",
    "build_context_host_blocks",
    "hostnames_by_level",
    "iter_dataspace_slots",
    "load_deployer_config",
    "apply_pionera_environment_overrides",
    "load_layered_deployer_config",
    "merge_missing_managed_blocks",
    "parse_hostnames",
    "remove_managed_blocks",
    "render_managed_block",
    "upsert_managed_block",
    "upsert_managed_blocks",
]
