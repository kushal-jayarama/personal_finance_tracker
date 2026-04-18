import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


BASE_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"


def _base(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return BASE_URL
    return f"{p.scheme}://{p.netloc}"


def get_tags(base_url: str) -> dict:
    req = Request(f"{base_url}/api/tags", method="GET")
    with urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat_ping(base_url: str, model: str) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": 'Return exactly this JSON: {"status":"ok"}'}],
        "options": {"temperature": 0},
    }
    req = Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    message = data.get("message", {}) if isinstance(data, dict) else {}
    content = message.get("content", "")
    return str(content).strip()


def main() -> int:
    base = _base(BASE_URL)
    model = MODEL
    if len(sys.argv) > 1:
        model = sys.argv[1]

    print(f"Testing Ollama at: {base}")
    print(f"Model: {model}")

    try:
        tags = get_tags(base)
        models = [m.get("name") for m in tags.get("models", []) if isinstance(m, dict)]
        print(f"Reachable: YES | Models found: {len(models)}")
        if model not in models:
            print(f"Model missing: {model}")
            print(f"Run this: ollama pull {model}")
            return 2
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"Ollama HTTP error {exc.code}: {detail}")
        return 3
    except URLError as exc:
        print(f"Ollama unreachable: {exc.reason}")
        print("Start it with: ollama serve")
        return 4
    except Exception as exc:
        print(f"Unexpected error checking tags: {exc}")
        return 5

    try:
        content = chat_ping(base, model)
        print("Chat response:")
        print(content)
        print("LLM chat test: PASS")
        return 0
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"Chat HTTP error {exc.code}: {detail}")
        return 6
    except Exception as exc:
        print(f"Chat failed: {exc}")
        return 7


if __name__ == "__main__":
    raise SystemExit(main())
