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


def _provider_text(provider, prompt, instructions):
    """Reuse provider transports for task-oriented, backend-only calls."""
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key: raise AIServiceError("OpenAI is not configured on this server.")
        data = _post("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {"model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"), "instructions": instructions, "input": prompt})
        try: return data["output"][0]["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as error: raise AIServiceError("OpenAI returned an unexpected response.") from error
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key: raise AIServiceError("Gemini is not configured on this server.")
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            {"Content-Type": "application/json"}, {"contents": [{"parts": [{"text": f"{instructions}\n\n{prompt}"}]}]})
        try: return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error: raise AIServiceError("Gemini returned an unexpected response.") from error
    raise AIServiceError("Choose OpenAI or Gemini.")


def extract_application_from_posting(provider, posting_text, pathways, personas):
    choices = "Pathways: " + ", ".join(p.name for p in pathways) + "\nPersonas: " + ", ".join(p.name for p in personas)
    raw = _provider_text(provider, f"{choices}\n\nJOB POSTING:\n{posting_text}",
        "Return only a JSON object with keys company, role_title, location, job_url, status, pathway, persona, notes. "
        "Extract facts only; use empty strings when absent. Status must be Preparing. Pathway and persona are optional suggestions from the supplied names only.")
    try:
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip(); result = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as error: raise AIServiceError("The AI response could not be validated. No application was created.") from error
    if not isinstance(result, dict): raise AIServiceError("The AI response could not be validated. No application was created.")
    clean = {key: str(result.get(key) or "").strip() for key in ("company", "role_title", "location", "job_url", "notes")}
    clean["status"] = "Preparing"
    pathway_names = {p.name.casefold(): p.id for p in pathways}; persona_names = {p.name.casefold(): p.id for p in personas}
    clean["pathway_id"] = pathway_names.get(str(result.get("pathway") or "").strip().casefold())
    clean["persona_id"] = persona_names.get(str(result.get("persona") or "").strip().casefold())
    return clean


def generate_cover_letter(provider, application, job_posting, source_documents, instructions=None):
    sources = "\n\n".join(f"SOURCE: {d.title}\n{(d.text_content or '')[:20000]}" for d in source_documents) or "No source materials supplied."
    prompt = (f"Company: {application.company}\nRole: {application.role_title}\nLocation: {application.location}\n"
              f"JOB POSTING:\n{job_posting[:30000]}\n\n{sources[:50000]}\n\nUSER INSTRUCTIONS:\n{instructions or 'None'}")
    text = _provider_text(provider, prompt, "Write only the body of a concise, professional, tailored business cover letter with salutation and closing. "
        "Do not invent professional experience, employers, education, metrics, skills, publications, projects, credentials, or personal facts not supported by provided materials.")
    if not text.strip(): raise AIServiceError("The AI service returned an empty cover letter.")
    return text.strip()
