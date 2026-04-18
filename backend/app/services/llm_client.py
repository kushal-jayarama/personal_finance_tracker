import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from openai import OpenAI

from ..config import settings


def is_remote_llm_enabled() -> bool:
    return bool(settings.enable_remote_llm)


def configured_model() -> str:
    return settings.effective_llm_model


def is_ollama_provider() -> bool:
    return (settings.llm_provider or "ollama").lower() == "ollama"


def _base_without_path(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "http://localhost:11434"
    return f"{parsed.scheme}://{parsed.netloc}"


def _ollama_chat_url() -> str:
    # Ollama native endpoint. Works regardless of whether llm_base_url has /v1.
    return f"{_base_without_path(settings.llm_base_url or 'http://localhost:11434')}/api/chat"


def _ollama_tags_url() -> str:
    return f"{_base_without_path(settings.llm_base_url or 'http://localhost:11434')}/api/tags"


def ollama_healthcheck(timeout: int = 5) -> dict:
    req = Request(_ollama_tags_url(), headers={"Content-Type": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return {"ok": False, "message": f"Ollama HTTP {exc.code}: {detail}", "models": []}
    except URLError as exc:
        return {"ok": False, "message": f"Ollama unreachable at {_ollama_tags_url()}: {exc.reason}", "models": []}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "models": []}

    models = []
    for m in data.get("models", []) if isinstance(data, dict) else []:
        if isinstance(m, dict):
            name = m.get("name")
            if isinstance(name, str):
                models.append(name)
    return {"ok": True, "message": "Ollama reachable.", "models": models}


def ollama_chat(messages: list[dict], *, temperature: float = 0.2, timeout: int = 90) -> str:
    payload = {
        "model": configured_model(),
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(_ollama_chat_url(), data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Ollama unreachable at {_ollama_chat_url()}: {exc.reason}") from exc

    # Native response usually has {"message":{"content":"..."}}
    message = data.get("message", {}) if isinstance(data, dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if content is None and isinstance(data, dict):
        content = data.get("response")
    return (content or "").strip()


def get_llm_client() -> OpenAI:
    provider = (settings.llm_provider or "ollama").lower()
    if provider == "ollama":
        return OpenAI(
            base_url=settings.llm_base_url or "http://localhost:11434/v1",
            api_key=settings.effective_llm_api_key,
            timeout=60,
        )
    if provider in {"openai", "openai_compatible"}:
        if settings.llm_base_url:
            return OpenAI(base_url=settings.llm_base_url, api_key=settings.effective_llm_api_key, timeout=60)
        return OpenAI(api_key=settings.effective_llm_api_key, timeout=60)
    return OpenAI(base_url=settings.llm_base_url or "http://localhost:11434/v1", api_key=settings.effective_llm_api_key, timeout=60)
