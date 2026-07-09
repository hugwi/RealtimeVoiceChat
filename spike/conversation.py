"""Fast local conversational reply for the voice bridge front-end.

Produces a short, spoken-friendly reply to a chit-chat turn via Ollama. It must
NOT claim to have done coding work — actual tasks are dispatched to Claude Code
elsewhere. Returns '' on any error; the caller substitutes a neutral fallback."""
from summarizer import OLLAMA_BASE_URL, OLLAMA_API_KEY, DEFAULT_MODEL

SYSTEM_PROMPT = (
    "You are the friendly voice of a coding assistant, talking with the user in "
    "real time. Reply in one or two short spoken sentences, plain English, no "
    "markdown. You are ONLY making conversation — do not claim to have written "
    "code, run commands, or completed any task; those are handled separately. If "
    "the user seems to want work done, briefly acknowledge and invite them to say "
    "what they need."
)


def _default_client():
    from openai import OpenAI

    return OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)


def converse(user_text, context="", *, client=None, model=DEFAULT_MODEL):
    if client is None:
        client = _default_client()
    user_content = user_text
    if context:
        user_content = f"CONVERSATION SO FAR:\n{context}\n\nUSER JUST SAID:\n{user_text}"
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.6,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""
