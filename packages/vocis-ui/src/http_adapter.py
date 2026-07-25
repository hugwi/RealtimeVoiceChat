"""Voice Gateway UI - FastAPI HTTP adapter for VoiceGatewayApi."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from vocis.settings_api import VoiceGatewayApi, VoiceSession


def create_app(api: VoiceGatewayApi) -> FastAPI:
    """Create FastAPI app that exposes VoiceGatewayApi over HTTP."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="Voice Gateway API",
        description="HTTP interface for Voice Gateway settings and sessions",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/api/connectors")
    async def list_connectors() -> list[dict[str, Any]]:
        """List available Platform Connectors."""
        return list(api.list_connectors())

    @app.get("/api/connections")
    async def list_connections() -> list[dict[str, Any]]:
        """List configured Platform Connections."""
        return list(api.list_connections())

    @app.post("/api/connections", status_code=status.HTTP_201_CREATED)
    async def create_connection(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new Platform Connection."""
        # TODO: Implement connection creation via PlatformConnectionStore
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Connection creation not yet implemented",
        )

    @app.patch("/api/connections/{connection_id}")
    async def update_connection(
        connection_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing Platform Connection."""
        # TODO: Implement connection update via PlatformConnectionStore
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Connection update not yet implemented",
        )

    @app.delete("/api/connections/{connection_id}")
    async def delete_connection(connection_id: str) -> None:
        """Delete a Platform Connection."""
        # TODO: Implement connection deletion via PlatformConnectionStore
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Connection deletion not yet implemented",
        )

    @app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
    async def start_voice_session(data: dict[str, Any]) -> dict[str, Any]:
        """Start a new Voice Session."""
        connection_id = data.get("connectionId")
        agent_session_id = data.get("agentSessionId")
        voice_profile_id = data.get("voiceProfileId")

        if not connection_id or not voice_profile_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="connectionId and voiceProfileId are required",
            )

        # Start the session
        session = await api.start_voice_session(
            connection_id=connection_id,
            agent_session_id=agent_session_id,
            voice_profile_id=voice_profile_id,
        )

        # For now, return session info without the agent_session object
        return {
            "connectionId": session.connection_id,
            "agentSessionId": session.agent_session_id,
            "voiceProfileId": session.voice_profile_id,
            "status": "active",
        }

    @app.delete("/api/sessions/{session_id}")
    async def end_voice_session(session_id: str) -> None:
        """End a Voice Session."""
        # TODO: Implement session termination
        # For now, just acknowledge the request
        pass

    return app
