"""Shared foundation infrastructure helpers reused by multiple adapters."""

from adapters.inesdata.infrastructure import INESDataInfrastructureAdapter


class SharedFoundationInfrastructureAdapter(INESDataInfrastructureAdapter):
    """Neutral facade for the shared Level 1-2 local foundation logic."""
