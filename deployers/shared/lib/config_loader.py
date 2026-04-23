from __future__ import annotations

import os
import re


_DATASPACE_SLOT_PATTERN = re.compile(r"^DS_(\d+)_([A-Z0-9_]+)$")


INFRASTRUCTURE_MANAGED_KEYS = frozenset(
    {
        "KC_URL",
        "KC_INTERNAL_URL",
        "KC_USER",
        "KC_PASSWORD",
        "PG_HOST",
        "PG_PORT",
        "PG_USER",
        "PG_PASSWORD",
        "VT_URL",
        "VT_TOKEN",
        "MINIO_ENDPOINT",
        "MINIO_USER",
        "MINIO_PASSWORD",
        "MINIO_ADMIN_USER",
        "MINIO_ADMIN_PASS",
    }
)


def load_deployer_config(path: str) -> dict[str, str]:
    """Load a deployer.config file using a simple KEY=VALUE format."""
    config: dict[str, str] = {}
    if not path or not os.path.isfile(path):
        return config

    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


def apply_pionera_environment_overrides(config: dict[str, str]) -> dict[str, str]:
    """Apply PIONERA_* environment variables as highest-priority overrides."""

    for env_key, env_value in os.environ.items():
        if not env_key.startswith("PIONERA_"):
            continue
        override_key = env_key[len("PIONERA_"):].strip()
        if not override_key or env_value in (None, ""):
            continue
        config[override_key] = env_value
    return config


def load_layered_deployer_config(
    paths: list[str] | tuple[str, ...],
    *,
    defaults: dict[str, str] | None = None,
    apply_environment: bool = True,
    protected_keys: set[str] | frozenset[str] | None = None,
) -> dict[str, str]:
    """Load deployer configuration as defaults < files in order < PIONERA_*."""

    config: dict[str, str] = dict(defaults or {})
    protected = set(protected_keys or [])
    for path in paths:
        layer = load_deployer_config(path)
        for key, value in layer.items():
            if key in protected and key in config:
                continue
            config[key] = value
    if apply_environment:
        apply_pionera_environment_overrides(config)
    return config


def iter_dataspace_slots(config: dict[str, str] | None) -> list[dict[str, str]]:
    """Group DS_<n>_* keys by slot while keeping the raw values untouched."""
    slots: dict[str, dict[str, str]] = {}
    for key, value in (config or {}).items():
        match = _DATASPACE_SLOT_PATTERN.match(key)
        if not match:
            continue
        slot_id, field_name = match.groups()
        slot = slots.setdefault(slot_id, {"slot": slot_id})
        slot[field_name] = value

    def _sort_key(item: dict[str, str]) -> int:
        try:
            return int(item["slot"])
        except (KeyError, TypeError, ValueError):
            return 0

    return [slots[key] for key in sorted(slots, key=lambda value: int(value))]
