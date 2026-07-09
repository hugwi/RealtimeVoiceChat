"""Shared mutable state between the data-channel handler and HappyBridgeLLM.

All access is on the asyncio event loop — no locks needed. One instance lives
for the life of the agent job.
"""


class VoiceState:
    def __init__(self):
        self.focused_session_id = None
        self.summary_cache = {}  # {session_id: summary_text}
        self.transcript = []     # rolling list of user utterances since last dispatch

    def set_focus(self, session_id):
        self.focused_session_id = session_id

    def set_summary(self, session_id, text):
        if session_id:
            self.summary_cache[session_id] = text

    def get_summary(self, session_id):
        return self.summary_cache.get(session_id)

    def append_transcript(self, text, *, max_turns=20):
        if text and text.strip():
            self.transcript.append(text.strip())
            if len(self.transcript) > max_turns:
                self.transcript = self.transcript[-max_turns:]

    def transcript_context(self):
        return "\n".join(self.transcript)

    def drain_transcript(self):
        text = "\n".join(self.transcript)
        self.transcript = []
        return text