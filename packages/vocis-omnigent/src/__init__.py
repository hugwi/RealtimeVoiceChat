"""Vocis OmniGent Adapter."""

# Server
from vocis_omnigent.server.router import create_voice_gateway_router

# UI
# from vocis_omnigent.ui import VoiceGatewaySection

__all__ = [
    "create_voice_gateway_router",
]
