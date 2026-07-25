"""Vocis OmniGent Server Router."""

from fastapi import APIRouter, HTTPException, status
from vocis import VoiceGatewayApi, ConnectorRegistry, PlatformConnectionStore

def create_voice_gateway_router(
    api: VoiceGatewayApi
) -> APIRouter:
    """Create FastAPI router for Voice Gateway endpoints.
    
    Args:
        api: The VoiceGatewayApi instance
        
    Returns:
        Configured APIRouter with all Voice Gateway endpoints
    """
    router = APIRouter(prefix="/voice-gateway", tags=["voice-gateway"])
    
    @router.get("/connectors")
    async def list_connectors():
        """List available Platform Connectors."""
        return list(api.list_connectors())
    
    @router.get("/connections")
    async def list_connections():
        """List configured Platform Connections."""
        return list(api.list_connections())
    
    @router.post("/connections", status_code=status.HTTP_201_CREATED)
    async def create_connection(data: dict):
        """Create a new Platform Connection."""
        # TODO: Implement
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Connection creation not yet implemented"
        )
    
    @router.post("/sessions", status_code=status.HTTP_201_CREATED)
    async def start_session(data: dict):
        """Start a new Voice Session."""
        connection_id = data.get("connectionId")
        agent_session_id = data.get("agentSessionId")
        voice_profile_id = data.get("voiceProfileId")
        
        if not connection_id or not voice_profile_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="connectionId and voiceProfileId are required"
            )
        
        session = await api.start_voice_session(
            connection_id=connection_id,
            agent_session_id=agent_session_id,
            voice_profile_id=voice_profile_id
        )
        
        return {
            "connectionId": session.connection_id,
            "agentSessionId": session.agent_session_id,
            "voiceProfileId": session.voice_profile_id,
            "status": "active"
        }
    
    return router

__all__ = ["create_voice_gateway_router"]
