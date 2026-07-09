"""Classify a spoken user turn as chit-chat or an actionable coding task.

A cheap local Ollama call. Returns whether the turn should be dispatched to
Claude Code and, if so, a distilled one-line instruction. On a client/network
error it RAISES so the caller can degrade (send the raw transcript instead of
losing the task); on merely malformed model output it defaults to chit-chat."""
import json
import re

from summarizer import OLLAMA_BASE_URL, OLLAMA_API_KEY, DEFAULT_MODEL
from dataclasses import dataclass

SYSTEM_PROMPT = (
    "You classify a single spoken turn from a user talking to a coding "
    "assistant. Decide if the turn is an ACTIONABLE coding task the assistant "
    "should carry out (write code, run commands, commit, investigate, fix, "
    "explain the codebase) versus chit-chat, greetings, acknowledgements, or "
    "vague musing. Reply with ONLY a JSON object, no prose, of the form "
    '{"is_task": true|false, "instruction": "..."}. When is_task is true, '
    "instruction is a concise imperative restatement of what to do. When false, "
    "instruction is an empty string."
)


@dataclass
class Classification:
    is_task: bool
    instruction: str = ""


def _default_client():
    from openai import OpenAI

    return OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)


def _extract_json(text):
    """Pull the first {...} JSON object out of the model output, or None."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except (ValueError, TypeError):
        return None


def classify(user_text, context="", *, client=None, model=DEFAULT_MODEL):
    if client is None:
        client = _default_client()
    user_content = user_text
    if context:
        user_content = f"RECENT CONTEXT:\n{context}\n\nCURRENT TURN:\n{user_text}"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = _extract_json(raw)
    if not isinstance(data, dict):
        return Classification(is_task=False)
    return Classification(
        is_task=bool(data.get("is_task")),
        instruction=(data.get("instruction") or "").strip(),
    )
