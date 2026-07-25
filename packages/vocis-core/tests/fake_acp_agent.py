from __future__ import annotations

from typing import Any


class EchoAgent:
    def __init__(self) -> None:
        self._conn: Any = None

    def on_connect(self, conn: Any) -> None:
        self._conn = conn

    async def initialize(self, protocol_version: int, **kwargs: Any) -> Any:
        from acp import PROTOCOL_VERSION, InitializeResponse
        from acp.schema import AgentCapabilities, Implementation

        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(load_session=True),
            agent_info=Implementation(
                name="voice-gateway-test-echo",
                title="Voice Gateway Test Echo",
                version="0.1.0",
            ),
        )

    async def load_session(self, cwd: str, session_id: str, **kwargs: Any) -> Any:
        from acp import LoadSessionResponse

        return LoadSessionResponse()

    async def prompt(
        self, session_id: str, prompt: list[Any], **kwargs: Any
    ) -> Any:
        from acp import PromptResponse, update_agent_message_text

        text = "".join(
            block.text
            for block in prompt
            if getattr(block, "type", None) == "text"
        )
        await self._conn.session_update(
            session_id,
            update_agent_message_text(f"echo:{text}"),
        )
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        return None

    async def authenticate(self, method_id: str, **kwargs: Any) -> Any:
        return None

    async def new_session(self, cwd: str, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def set_session_mode(
        self, session_id: str, mode_id: str, **kwargs: Any
    ) -> Any:
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None


if __name__ == "__main__":
    from acp import run_agent
    import asyncio

    asyncio.run(run_agent(EchoAgent()))
