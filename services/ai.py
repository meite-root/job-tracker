"""Small, provider-neutral AI gateway. API keys never leave the server."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AIServiceError(RuntimeError):
    """A safe, user-facing provider error."""


def _post(url, headers, payload):
    request = Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise AIServiceError("The AI service is temporarily unavailable.") from error


def ask_openai(message, context):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise AIServiceError("OpenAI is not configured on this server.")
    data = _post("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                 {"model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"), "instructions": "Answer using the read-only job tracker context. Be concise and do not claim to modify data.", "input": f"{context}\n\nQuestion: {message}"})
    try:
        return data["output"][0]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIServiceError("OpenAI returned an unexpected response.") from error


def ask_gemini(message, context):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise AIServiceError("Gemini is not configured on this server.")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                 {"Content-Type": "application/json"}, {"contents": [{"parts": [{"text": f"Use this read-only job tracker context. Be concise.\n{context}\n\nQuestion: {message}"}]}]})
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIServiceError("Gemini returned an unexpected response.") from error


def ask_ai(provider, message, context):
    if provider == "openai":
        return ask_openai(message, context)
    if provider == "gemini":
        return ask_gemini(message, context)
    raise AIServiceError("Choose OpenAI or Gemini.")
