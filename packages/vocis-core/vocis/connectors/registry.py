from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping


_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_CAPABILITIES = frozenset(
    {
        "sessionDiscovery",
        "sessionHistory",
        "streamingText",
        "cancellation",
        "permissions",
        "backgroundTasks",
    }
)
_AUTH_METHODS = frozenset({"oauth-device", "bearer-token", "none"})


class ConnectorManifestError(ValueError):
    """A connector manifest is invalid or conflicts with another manifest."""


@dataclass(frozen=True)
class ConnectorManifest:
    id: str
    display_name: str
    version: str
    runtime_type: str
    command: str | None
    arguments: tuple[str, ...]
    entrypoint: str | None
    protocol: str
    protocol_version: int
    capabilities: frozenset[str]
    authentication_methods: tuple[str, ...]
    preferred_authentication: str
    configuration: Mapping[str, Any]
    source: str

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


class ConnectorRegistry:
    """Validated catalog of trusted, operator-installed Platform Connectors."""

    def __init__(self, manifests: Iterable[ConnectorManifest]) -> None:
        indexed: dict[str, ConnectorManifest] = {}
        for manifest in manifests:
            if manifest.id in indexed:
                raise ConnectorManifestError(
                    f"duplicate connector id {manifest.id!r}: "
                    f"{indexed[manifest.id].source} and {manifest.source}"
                )
            indexed[manifest.id] = manifest
        self._manifests = MappingProxyType(indexed)

    @classmethod
    def discover(
        cls, extra_directories: Iterable[str | Path] = ()
    ) -> ConnectorRegistry:
        manifests = [
            _load_builtin("omnigent.connector.json"),
            _load_builtin("generic-acp.connector.json"),
        ]
        for directory in extra_directories:
            path = Path(directory).expanduser()
            if not path.is_dir():
                raise ConnectorManifestError(
                    f"connector directory does not exist: {path}"
                )
            manifests.extend(
                _load_path(candidate)
                for candidate in sorted(path.glob("*.connector.json"))
            )
        return cls(manifests)

    def list(self) -> tuple[ConnectorManifest, ...]:
        return tuple(sorted(self._manifests.values(), key=lambda item: item.id))

    def require(self, connector_id: str) -> ConnectorManifest:
        try:
            return self._manifests[connector_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._manifests)) or "(none)"
            raise ConnectorManifestError(
                f"unknown connector {connector_id!r}; available: {available}"
            ) from exc


def _load_builtin(name: str) -> ConnectorManifest:
    resource = files("vocis.connectors").joinpath("builtin", name)
    try:
        raw = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectorManifestError(f"cannot load built-in manifest {name}: {exc}") from exc
    return _parse(raw, f"builtin:{name}")


def _load_path(path: Path) -> ConnectorManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectorManifestError(f"cannot load manifest {path}: {exc}") from exc
    return _parse(raw, str(path))


def _parse(raw: Any, source: str) -> ConnectorManifest:
    root = _mapping(raw, source)
    _exact_keys(
        root,
        {"apiVersion", "kind", "metadata", "runtime", "capabilities", "authentication", "configuration"},
        source,
    )
    if root["apiVersion"] != "voice-gateway/v1alpha1":
        raise ConnectorManifestError(f"{source}: unsupported apiVersion")
    if root["kind"] != "AgentPlatformConnector":
        raise ConnectorManifestError(f"{source}: kind must be AgentPlatformConnector")

    metadata = _mapping(root["metadata"], f"{source}.metadata")
    _exact_keys(metadata, {"id", "displayName", "version"}, f"{source}.metadata")
    connector_id = _string(metadata["id"], f"{source}.metadata.id")
    if not _ID_PATTERN.fullmatch(connector_id):
        raise ConnectorManifestError(f"{source}: invalid connector id {connector_id!r}")
    version = _string(metadata["version"], f"{source}.metadata.version")
    if not _VERSION_PATTERN.fullmatch(version):
        raise ConnectorManifestError(f"{source}: version must be semantic")

    runtime = _mapping(root["runtime"], f"{source}.runtime")
    runtime_type = runtime.get("type")
    if runtime_type == "executable":
        _exact_keys(
            runtime,
            {"type", "command", "arguments", "protocol", "protocolVersion"},
            f"{source}.runtime",
        )
        command = _string(runtime["command"], f"{source}.runtime.command")
        arguments_raw = runtime["arguments"]
        if not isinstance(arguments_raw, list) or not all(
            isinstance(item, str) for item in arguments_raw
        ):
            raise ConnectorManifestError(
                f"{source}.runtime.arguments: expected string array"
            )
        arguments = tuple(arguments_raw)
        entrypoint = None
    elif runtime_type == "builtin":
        _exact_keys(
            runtime,
            {"type", "entrypoint", "protocol", "protocolVersion"},
            f"{source}.runtime",
        )
        command = None
        arguments = ()
        entrypoint = _string(
            runtime["entrypoint"], f"{source}.runtime.entrypoint"
        )
    else:
        raise ConnectorManifestError(
            f"{source}: runtime type must be executable or builtin"
        )
    if runtime["protocol"] != "acp":
        raise ConnectorManifestError(f"{source}: only ACP connectors are supported")
    protocol_version = runtime["protocolVersion"]
    if not isinstance(protocol_version, int) or isinstance(protocol_version, bool):
        raise ConnectorManifestError(f"{source}.runtime.protocolVersion: expected integer")

    capabilities_raw = _mapping(root["capabilities"], f"{source}.capabilities")
    unknown_capabilities = set(capabilities_raw) - _CAPABILITIES
    if unknown_capabilities:
        raise ConnectorManifestError(
            f"{source}: unknown capabilities: {', '.join(sorted(unknown_capabilities))}"
        )
    if not all(isinstance(value, bool) for value in capabilities_raw.values()):
        raise ConnectorManifestError(f"{source}.capabilities: expected boolean values")

    authentication = _mapping(root["authentication"], f"{source}.authentication")
    _exact_keys(authentication, {"methods", "preferred"}, f"{source}.authentication")
    methods_raw = authentication["methods"]
    if not isinstance(methods_raw, list) or not methods_raw:
        raise ConnectorManifestError(f"{source}.authentication.methods: expected non-empty array")
    methods = tuple(_string(item, f"{source}.authentication.methods") for item in methods_raw)
    if set(methods) - _AUTH_METHODS:
        raise ConnectorManifestError(f"{source}: unsupported authentication method")
    preferred = _string(authentication["preferred"], f"{source}.authentication.preferred")
    if preferred not in methods:
        raise ConnectorManifestError(f"{source}: preferred authentication must be in methods")

    configuration = _mapping(root["configuration"], f"{source}.configuration")
    return ConnectorManifest(
        id=connector_id,
        display_name=_string(metadata["displayName"], f"{source}.metadata.displayName"),
        version=version,
        runtime_type=runtime_type,
        command=command,
        arguments=arguments,
        entrypoint=entrypoint,
        protocol="acp",
        protocol_version=protocol_version,
        capabilities=frozenset(
            key for key, enabled in capabilities_raw.items() if enabled
        ),
        authentication_methods=methods,
        preferred_authentication=preferred,
        configuration=MappingProxyType(dict(configuration)),
        source=source,
    )


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConnectorManifestError(f"{location}: expected object")
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectorManifestError(f"{location}: expected non-empty string")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], location: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            details.append(f"unknown {', '.join(sorted(unknown))}")
        raise ConnectorManifestError(f"{location}: {'; '.join(details)}")
