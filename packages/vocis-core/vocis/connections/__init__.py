"""Durable configuration for connections to Agent Platform instances."""

from .store import (
    PlatformConnection,
    PlatformConnectionError,
    PlatformConnectionNotFound,
    PlatformConnectionStore,
)

__all__ = [
    "PlatformConnection",
    "PlatformConnectionError",
    "PlatformConnectionNotFound",
    "PlatformConnectionStore",
]
