"""Discovery and validation for Agent Platform connector manifests."""

from .registry import (
    ConnectorManifest,
    ConnectorManifestError,
    ConnectorRegistry,
)

__all__ = [
    "ConnectorManifest",
    "ConnectorManifestError",
    "ConnectorRegistry",
]
