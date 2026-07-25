from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit

from ..connectors import (
    ConnectorManifest,
    ConnectorManifestError,
    ConnectorRegistry,
)


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SECRET_KEYS = frozenset(
    {
        "apikey",
        "authorization",
        "bearertoken",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
    }
)
_MISSING = object()


class PlatformConnectionError(ValueError):
    """A Platform Connection is invalid or its store cannot be read."""


class PlatformConnectionNotFound(PlatformConnectionError):
    """The requested Platform Connection does not exist."""


@dataclass(frozen=True)
class PlatformConnection:
    id: str
    connector_id: str
    display_name: str
    configuration: Mapping[str, Any]
    credential_grant_id: str | None
    created_at: str
    updated_at: str


class PlatformConnectionStore:
    """Atomic JSON persistence for non-secret Platform Connection metadata."""

    def __init__(self, path: str | Path, connectors: ConnectorRegistry) -> None:
        self._path = Path(path).expanduser()
        self._connectors = connectors

    def list(self) -> tuple[PlatformConnection, ...]:
        connections = self._read()
        return tuple(connections[key] for key in sorted(connections))

    def get(self, connection_id: str) -> PlatformConnection:
        self._validate_id(connection_id, "connection id")
        try:
            return self._read()[connection_id]
        except KeyError as exc:
            raise PlatformConnectionNotFound(
                f"unknown Platform Connection {connection_id!r}"
            ) from exc

    def create(
        self,
        *,
        connector_id: str,
        display_name: str,
        configuration: Mapping[str, Any],
        credential_grant_id: str | None = None,
        connection_id: str | None = None,
    ) -> PlatformConnection:
        connection_id = connection_id or str(uuid.uuid4())
        self._validate_id(connection_id, "connection id")
        manifest = self._resolve_connector(connector_id)
        self._validate_grant(manifest, credential_grant_id)
        clean_configuration = self._validate_configuration(manifest, configuration)
        if not isinstance(display_name, str) or not display_name.strip():
            raise PlatformConnectionError("display name must be a non-empty string")

        connections = self._read()
        if connection_id in connections:
            raise PlatformConnectionError(
                f"Platform Connection {connection_id!r} already exists"
            )
        now = _timestamp()
        connection = PlatformConnection(
            id=connection_id,
            connector_id=connector_id,
            display_name=display_name.strip(),
            configuration=_freeze(clean_configuration),
            credential_grant_id=credential_grant_id,
            created_at=now,
            updated_at=now,
        )
        connections[connection_id] = connection
        self._write(connections)
        return connection

    def update(
        self,
        connection_id: str,
        *,
        display_name: str | object = _MISSING,
        configuration: Mapping[str, Any] | object = _MISSING,
        credential_grant_id: str | None | object = _MISSING,
    ) -> PlatformConnection:
        connections = self._read()
        try:
            current = connections[connection_id]
        except KeyError as exc:
            raise PlatformConnectionNotFound(
                f"unknown Platform Connection {connection_id!r}"
            ) from exc

        next_name = current.display_name if display_name is _MISSING else display_name
        if not isinstance(next_name, str) or not next_name.strip():
            raise PlatformConnectionError("display name must be a non-empty string")
        next_grant = (
            current.credential_grant_id
            if credential_grant_id is _MISSING
            else credential_grant_id
        )
        next_configuration = (
            _thaw(current.configuration)
            if configuration is _MISSING
            else configuration
        )
        if not isinstance(next_configuration, Mapping):
            raise PlatformConnectionError("configuration must be an object")
        manifest = self._resolve_connector(current.connector_id)
        self._validate_grant(manifest, next_grant)
        clean_configuration = self._validate_configuration(
            manifest, next_configuration
        )
        updated = PlatformConnection(
            id=current.id,
            connector_id=current.connector_id,
            display_name=next_name.strip(),
            configuration=_freeze(clean_configuration),
            credential_grant_id=next_grant,
            created_at=current.created_at,
            updated_at=_timestamp(),
        )
        connections[connection_id] = updated
        self._write(connections)
        return updated

    def delete(self, connection_id: str) -> None:
        connections = self._read()
        if connection_id not in connections:
            raise PlatformConnectionNotFound(
                f"unknown Platform Connection {connection_id!r}"
            )
        del connections[connection_id]
        self._write(connections)

    def _resolve_connector(self, connector_id: str) -> ConnectorManifest:
        try:
            return self._connectors.require(connector_id)
        except ConnectorManifestError as exc:
            raise PlatformConnectionError(str(exc)) from exc

    def _validate_grant(
        self, manifest: ConnectorManifest, grant_id: str | None
    ) -> None:
        if manifest.authentication_methods == ("none",):
            if grant_id is not None:
                raise PlatformConnectionError(
                    f"connector {manifest.id!r} does not use a Credential Grant"
                )
            return
        if grant_id is None:
            raise PlatformConnectionError(
                f"connector {manifest.id!r} requires a Credential Grant"
            )
        self._validate_id(grant_id, "Credential Grant id")

    def _validate_configuration(
        self, manifest: ConnectorManifest, configuration: Mapping[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(configuration, Mapping):
            raise PlatformConnectionError("configuration must be an object")
        candidate = deepcopy(_thaw(configuration))
        _reject_secrets(candidate, "configuration")
        _validate_schema(candidate, manifest.configuration, "configuration")
        return candidate

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
            raise PlatformConnectionError(
                f"{label} must contain only letters, numbers, '.', '_' or '-'"
            )

    def _read(self) -> dict[str, PlatformConnection]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PlatformConnectionError(
                f"cannot read Platform Connection store {self._path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise PlatformConnectionError(
                f"unsupported Platform Connection store format: {self._path}"
            )
        records = raw.get("connections")
        if not isinstance(records, list):
            raise PlatformConnectionError(
                f"invalid Platform Connection store: {self._path}"
            )
        result: dict[str, PlatformConnection] = {}
        try:
            for record in records:
                connection = _decode(record)
                if connection.id in result:
                    raise PlatformConnectionError(
                        f"duplicate Platform Connection id {connection.id!r}"
                    )
                self._validate_id(connection.id, "connection id")
                if not connection.display_name.strip():
                    raise PlatformConnectionError(
                        "display name must be a non-empty string"
                    )
                manifest = self._resolve_connector(connection.connector_id)
                self._validate_grant(manifest, connection.credential_grant_id)
                self._validate_configuration(manifest, connection.configuration)
                result[connection.id] = connection
        except (KeyError, TypeError) as exc:
            raise PlatformConnectionError(
                f"invalid Platform Connection store: {self._path}"
            ) from exc
        return result

    def _write(self, connections: Mapping[str, PlatformConnection]) -> None:
        payload = {
            "version": 1,
            "connections": [
                _encode(connections[key]) for key in sorted(connections)
            ],
        }
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(self._path.parent, 0o700)
        except OSError:
            pass
        temporary_name: str | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self._path.name}.",
                dir=self._path.parent,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self._path)
            try:
                directory_descriptor = os.open(self._path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            except OSError:
                pass
        except OSError as exc:
            raise PlatformConnectionError(
                f"cannot write Platform Connection store {self._path}: {exc}"
            ) from exc
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass


def _validate_schema(value: Any, schema: Mapping[str, Any], location: str) -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            raise PlatformConnectionError(f"{location}: expected object")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = set(required) - set(value)
        unknown = set(value) - set(properties)
        if missing:
            raise PlatformConnectionError(
                f"{location}: missing {', '.join(sorted(missing))}"
            )
        if unknown:
            raise PlatformConnectionError(
                f"{location}: unknown {', '.join(sorted(unknown))}"
            )
        for key, child in value.items():
            _validate_schema(child, properties[key], f"{location}.{key}")
    elif expected_type == "string":
        if not isinstance(value, str):
            raise PlatformConnectionError(f"{location}: expected string")
        if schema.get("format") == "uri":
            parsed = urlsplit(value)
            if not parsed.scheme or (parsed.scheme in {"http", "https"} and not parsed.netloc):
                raise PlatformConnectionError(f"{location}: expected absolute URI")
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            raise PlatformConnectionError(f"{location}: expected boolean")
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise PlatformConnectionError(f"{location}: expected integer")
    elif expected_type == "array":
        if not isinstance(value, list):
            raise PlatformConnectionError(f"{location}: expected array")
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            _validate_schema(item, item_schema, f"{location}[{index}]")
    elif expected_type is not None:
        raise PlatformConnectionError(
            f"{location}: unsupported schema type {expected_type!r}"
        )


def _reject_secrets(value: Any, location: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in _SECRET_KEYS:
                raise PlatformConnectionError(
                    f"{location}.{key}: secrets belong in a Credential Grant"
                )
            _reject_secrets(child, f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{location}[{index}]")


def _decode(raw: Any) -> PlatformConnection:
    if not isinstance(raw, dict):
        raise TypeError("record must be an object")
    expected = {
        "id",
        "connectorId",
        "displayName",
        "configuration",
        "credentialGrantId",
        "createdAt",
        "updatedAt",
    }
    if set(raw) != expected:
        raise TypeError("record fields do not match")
    configuration = raw["configuration"]
    if not isinstance(configuration, dict):
        raise TypeError("configuration must be an object")
    for field in expected - {"configuration", "credentialGrantId"}:
        if not isinstance(raw[field], str):
            raise TypeError(f"{field} must be a string")
    credential_grant_id = raw["credentialGrantId"]
    if credential_grant_id is not None and not isinstance(
        credential_grant_id, str
    ):
        raise TypeError("credentialGrantId must be a string or null")
    return PlatformConnection(
        id=raw["id"],
        connector_id=raw["connectorId"],
        display_name=raw["displayName"],
        configuration=_freeze(configuration),
        credential_grant_id=credential_grant_id,
        created_at=raw["createdAt"],
        updated_at=raw["updatedAt"],
    )


def _encode(connection: PlatformConnection) -> dict[str, Any]:
    return {
        "id": connection.id,
        "connectorId": connection.connector_id,
        "displayName": connection.display_name,
        "configuration": _thaw(connection.configuration),
        "credentialGrantId": connection.credential_grant_id,
        "createdAt": connection.created_at,
        "updatedAt": connection.updated_at,
    }


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
