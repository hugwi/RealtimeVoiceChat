"""Summarize a Claude reply into a spoken-friendly, near-extractive summary.
The full reply is always visible in the Happy chat, so this is a lossy preview
by design — but it must never fabricate facts."""
import re

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"
DEFAULT_MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = (
    "You turn a coding agent's reply into a short spoken summary. "
    "Summarize ONLY what is stated. Never add facts, numbers, or names that "
    "are not present. If the reply is unclear, say 'Check the chat for details.' "
    "Keep it to two or three sentences, plain spoken English, no markdown."
)

_PLACEHOLDER = "Nothing to report. Check the chat for details."


def _default_client():
    from openai import OpenAI

    return OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)


def _truncate(text, max_sentences=3):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:max_sentences]).strip()


def summarize(reply, *, client=None, model=DEFAULT_MODEL):
    if not reply or not reply.strip():
        return _PLACEHOLDER
    if client is None:
        client = _default_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": reply},
            ],
            temperature=0.2,
        )
        out = (resp.choices[0].message.content or "").strip()
    except Exception:
        out = ""
    if not out:
        return _truncate(reply)
    return out
