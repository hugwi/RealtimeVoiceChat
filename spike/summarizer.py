"""Summarize a Claude reply into a spoken-friendly, near-extractive summary.
The full reply is always visible in the Happy chat, so this is a lossy preview
by design — but it must never fabricate facts."""
import re

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"
DEFAULT_MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = (
    "You are the spoken voice of a coding agent, reading its reply aloud to the "
    "user. You are given the USER'S REQUEST and the agent's full reply. Produce "
    "what should be spoken back.\n"
    "Default to a concise two or three sentence summary of what the agent did or "
    "found. BUT adapt to the user's request: if they asked to go deeper, explain "
    "the code, walk through the reasoning, or hear more detail, give that detail "
    "and be as long as needed — describe code in plain spoken English, never read "
    "symbols or markdown aloud. "
    "Summarize ONLY what the reply states; never add facts, numbers, or names that "
    "are not present. If the reply is unclear, say 'Check the chat for details.' "
    "Plain spoken English, no markdown, no code fences."
)

_PLACEHOLDER = "Nothing to report. Check the chat for details."


def _default_client():
    from openai import OpenAI

    return OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)


def _truncate(text, max_sentences=3):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:max_sentences]).strip()


def summarize(reply, user_request=None, *, client=None, model=DEFAULT_MODEL):
    if not reply or not reply.strip():
        return _PLACEHOLDER
    if client is None:
        client = _default_client()
    request = (user_request or "").strip() or "(no specific request)"
    user_content = f"USER'S REQUEST:\n{request}\n\nAGENT'S REPLY:\n{reply}"
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
        out = (resp.choices[0].message.content or "").strip()
    except Exception:
        out = ""
    if not out:
        return _truncate(reply)
    return out
