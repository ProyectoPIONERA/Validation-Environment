"""Connector host synchronization helpers used by Level 6 validation."""

from __future__ import annotations

from typing import Any, Callable


def connector_hosts_resolve(
    connectors: list[str],
    *,
    domain: str | None,
    resolver: Callable[[str], str],
) -> list[str]:
    unresolved: list[str] = []
    if not domain:
        return unresolved

    for connector in connectors or []:
        host = f"{connector}.{domain}"
        try:
            resolver(host)
        except OSError:
            unresolved.append(host)

    return unresolved


def ensure_connector_hosts(
    connectors: list[str],
    *,
    config_adapter: Any,
    infrastructure_adapter: Any,
    domain: str | None,
    resolver: Callable[[str], str],
    header_comment: str = "# Dataspace Connector Hosts",
) -> None:
    infra_hosts = config_adapter.generate_hosts(infrastructure_adapter._dataspace_name())
    connector_hosts = config_adapter.generate_connector_hosts(connectors)
    all_hosts = list(dict.fromkeys(infra_hosts + connector_hosts))

    if all_hosts:
        infrastructure_adapter.manage_hosts_entries(
            all_hosts,
            header_comment=header_comment,
        )

    unresolved = connector_hosts_resolve(
        connectors,
        domain=domain,
        resolver=resolver,
    )
    if unresolved:
        joined = ", ".join(unresolved)
        raise RuntimeError(
            "Connector hostnames do not resolve locally. "
            f"Check /etc/hosts and minikube tunnel for: {joined}"
        )
