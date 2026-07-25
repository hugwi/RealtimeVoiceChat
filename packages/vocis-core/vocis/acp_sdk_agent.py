from __future__ import annotations

from typing import Any

from .acp_agent import OmnigentAcpAgent


class OfficialSdkOmnigentAgent:
    """Official ACP Python SDK wrapper around the tested core agent.

    Imports stay inside methods/module construction so the core protocol and
    LiveKit tests do not require the optional ACP dependency.
    """

    def __init__(self, core: OmnigentAcpAgent, default_session_id: str) -> None:
        self._core = core
        self._default_session_id = default_session_id
        self._conn: Any = None

    def on_connect(self, conn: Any) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any = None,
        client_info: Any = None,
        **kwargs: Any,
    ) -> Any:
        from acp import PROTOCOL_VERSION, InitializeResponse
        from acp.schema import AgentCapabilities, Implementation

        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(load_session=True),
            agent_info=Implementation(
                name="omnigent-acp-voice-bridge",
                title="OmniGent Voice Bridge",
                version="0.1.0",
            ),
        )

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        from acp import NewSessionResponse

        # Baseline ACP has no portable "choose OmniGent harness/session" field.
        # Bind to the operator-configured target instead of inventing a private
        # required extension that generic ACP clients cannot provide.
        await self._core.load_session(
            self._default_session_id, self._default_session_id
        )
        return NewSessionResponse(session_id=self._default_session_id, modes=None)

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        additional_directories: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        from acp import LoadSessionResponse

        await self._core.load_session(session_id, session_id)
        return LoadSessionResponse()

    async def prompt(
        self, session_id: str, prompt: list[Any], **kwargs: Any
    ) -> Any:
        from acp import PromptResponse, update_agent_message_text
        from acp.schema import PermissionOption, ToolCallUpdate

        raw_prompt = [
            {"type": "text", "text": block.text}
            for block in prompt
            if getattr(block, "type", None) == "text"
        ]

        async def notify(params: dict[str, Any]) -> None:
            update = params.get("update", {})
            content = update.get("content", {})
            text = content.get("text", "")
            if text:
                await self._conn.session_update(
                    session_id, update_agent_message_text(text)
                )

        async def request_permission(params: dict[str, Any]) -> str:
            tool_call = params["toolCall"]
            response = await self._conn.request_permission(
                session_id=session_id,
                tool_call=ToolCallUpdate(
                    tool_call_id=tool_call["toolCallId"],
                    title=tool_call.get("title"),
                    kind=tool_call.get("kind"),
                    status=tool_call.get("status"),
                ),
                options=[PermissionOption(**option) for option in params["options"]],
            )
            outcome = response.outcome
            if getattr(outcome, "outcome", None) == "cancelled":
                return "cancel"
            return str(getattr(outcome, "option_id", "deny"))

        result = await self._core.prompt(
            {"sessionId": session_id, "prompt": raw_prompt},
            notify,
            request_permission,
        )
        return PromptResponse(stop_reason=result["stopReason"])

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        await self._core.cancel(session_id)

    async def authenticate(self, method_id: str, **kwargs: Any) -> Any:
        return None

    async def set_session_mode(
        self, session_id: str, mode_id: str, **kwargs: Any
    ) -> Any:
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None


class OfficialSdkAttachedSessionAgent:
    """Expose an already-attached platform-neutral Agent Session over ACP."""

    def __init__(self, session: Any, session_id: str) -> None:
        self._session = session
        self._session_id = session_id
        self._conn: Any = None

    def on_connect(self, conn: Any) -> None:
        self._conn = conn
        self._session.set_permission_handler(self._request_permission)

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any = None,
        client_info: Any = None,
        **kwargs: Any,
    ) -> Any:
        from acp import PROTOCOL_VERSION, InitializeResponse
        from acp.schema import AgentCapabilities, Implementation

        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(load_session=True),
            agent_info=Implementation(
                name="voice-gateway-acp-bridge",
                title="Voice Gateway ACP Bridge",
                version="0.1.0",
            ),
        )

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        from acp import NewSessionResponse

        return NewSessionResponse(session_id=self._session_id, modes=None)

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        additional_directories: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        from acp import LoadSessionResponse

        self._require_session(session_id)
        return LoadSessionResponse()

    async def prompt(
        self, session_id: str, prompt: list[Any], **kwargs: Any
    ) -> Any:
        from acp import PromptResponse, update_agent_message_text

        self._require_session(session_id)
        text = "\n".join(
            block.text
            for block in prompt
            if getattr(block, "type", None) == "text"
            and isinstance(getattr(block, "text", None), str)
        ).strip()
        if not text:
            raise ValueError("prompt must contain non-empty text")

        stop_reason = "end_turn"
        async for event in self._session.prompt(session_id, text):
            if event.kind == "text_delta" and event.text:
                await self._conn.session_update(
                    session_id, update_agent_message_text(event.text)
                )
            elif event.kind == "cancelled":
                stop_reason = "cancelled"
            elif event.kind == "failed":
                raise RuntimeError(event.text or "Agent Session request failed")
        return PromptResponse(stop_reason=stop_reason)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        self._require_session(session_id)
        await self._session.cancel(session_id)

    async def authenticate(self, method_id: str, **kwargs: Any) -> Any:
        return None

    async def set_session_mode(
        self, session_id: str, mode_id: str, **kwargs: Any
    ) -> Any:
        self._require_session(session_id)
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None

    async def _request_permission(self, params: dict[str, Any]) -> str:
        from acp.schema import PermissionOption, ToolCallUpdate

        tool_call = params["toolCall"]
        response = await self._conn.request_permission(
            session_id=self._session_id,
            tool_call=ToolCallUpdate(
                tool_call_id=tool_call["toolCallId"],
                title=tool_call.get("title"),
                kind=tool_call.get("kind"),
                status=tool_call.get("status"),
            ),
            options=[PermissionOption(**option) for option in params["options"]],
        )
        outcome = response.outcome
        if getattr(outcome, "outcome", None) == "cancelled":
            return "cancel"
        return str(getattr(outcome, "option_id", "deny"))

    def _require_session(self, session_id: str) -> None:
        if session_id != self._session_id:
            raise ValueError(
                f"configured Agent Session is {self._session_id!r}, "
                f"not {session_id!r}"
            )
