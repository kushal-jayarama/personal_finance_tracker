import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from .llm_client import configured_model, get_llm_client, is_ollama_provider, is_remote_llm_enabled, ollama_chat, ollama_healthcheck
from .premium import premium_snapshot

AI_ADVICE_TIMEOUT_SECONDS = 5 * 60


def _fallback_advice(snapshot: dict) -> dict:
    do_items: list[dict] = []
    avoid_items: list[dict] = []

    for alert in snapshot.get("overspending_alerts", [])[:3]:
        do_items.append(
            {
                "title": "Take action on overspending",
                "reason": alert.get("message", ""),
                "priority": "high" if alert.get("severity") == "high" else "medium",
            }
        )

    for anomaly in snapshot.get("category_anomalies", [])[:2]:
        do_items.append(
            {
                "title": f"Set a cap for {anomaly.get('category', 'spending')}",
                "reason": anomaly.get("message", ""),
                "priority": "medium",
            }
        )

    for pattern in snapshot.get("spending_patterns", [])[:2]:
        avoid_items.append(
            {
                "title": "Avoid repeating high-cost pattern",
                "reason": pattern.get("message", ""),
                "priority": "medium",
            }
        )

    if not do_items:
        do_items.append(
            {
                "title": "Create category budgets",
                "reason": "Budget targets make spending drift visible early.",
                "priority": "medium",
            }
        )
    if not avoid_items:
        avoid_items.append(
            {
                "title": "Avoid unplanned discretionary spend",
                "reason": "Untracked impulse spends reduce savings velocity.",
                "priority": "medium",
            }
        )

    return {
        "summary": "AI advisor is running in local fallback mode. Add API key + enable_remote_llm for richer suggestions.",
        "what_to_do": do_items[:5],
        "what_to_avoid": avoid_items[:5],
        "source": "fallback",
        "generated_at": datetime.utcnow().isoformat(),
    }


def _parse_json_content(text: str) -> dict:
    payload = (text or "").strip()
    if payload.startswith("```"):
        payload = payload.strip("`")
        if payload.lower().startswith("json"):
            payload = payload[4:].strip()
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("LLM output is not a JSON object.")
    return parsed


def _normalize_item(item: dict, fallback_title: str) -> dict:
    if not isinstance(item, dict):
        item = {}
    return {
        "title": str(item.get("title") or fallback_title),
        "reason": str(item.get("reason") or "No reason provided."),
        "priority": str(item.get("priority") or "medium"),
    }


def _normalize_advice(payload: dict) -> dict:
    if not isinstance(payload, dict):
        payload = {}
    do_raw = payload.get("what_to_do")
    avoid_raw = payload.get("what_to_avoid")
    do_list = do_raw if isinstance(do_raw, list) else []
    avoid_list = avoid_raw if isinstance(avoid_raw, list) else []
    return {
        "summary": str(payload.get("summary") or "No AI summary available."),
        "what_to_do": [_normalize_item(x, "Take a corrective action") for x in do_list[:5]],
        "what_to_avoid": [_normalize_item(x, "Avoid risky spending behavior") for x in avoid_list[:5]],
        "source": str(payload.get("source") or "llm"),
        "generated_at": str(payload.get("generated_at") or datetime.utcnow().isoformat()),
    }


def _llm_advice(snapshot: dict, timeout_seconds: int = AI_ADVICE_TIMEOUT_SECONDS) -> dict:
    if not is_remote_llm_enabled():
        raise ValueError("Remote LLM is disabled. Set ENABLE_REMOTE_LLM=true.")
    if is_ollama_provider():
        hc = ollama_healthcheck()
        if not hc.get("ok"):
            raise ValueError(hc.get("message", "Ollama is offline."))
        model = configured_model()
        if hc.get("models") and model not in hc.get("models", []):
            raise ValueError(f"Ollama model '{model}' is not pulled. Run: ollama pull {model}")
    payload = {
        "totals": snapshot.get("health_breakdown", {}),
        "weekly_recap": snapshot.get("weekly_recap", {}),
        "overspending_alerts": snapshot.get("overspending_alerts", [])[:5],
        "spending_patterns": snapshot.get("spending_patterns", [])[:5],
        "category_anomalies": snapshot.get("category_anomalies", [])[:5],
    }
    prompt = (
        "You are a personal finance advisor. Based on this JSON, provide actionable guidance.\n"
        "Return strict JSON object with keys: summary (string), what_to_do (array), what_to_avoid (array).\n"
        "Each item in arrays must have: title, reason, priority (high|medium|low). Maximum 5 items per list.\n"
        f"DATA: {json.dumps(payload)}"
    )
    messages = [
        {"role": "system", "content": "You are a precise financial assistant. Always return valid JSON."},
        {"role": "user", "content": prompt},
    ]
    if is_ollama_provider():
        text = ollama_chat(messages, temperature=0.2, timeout=timeout_seconds)
    else:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=configured_model(),
            temperature=0.2,
            messages=messages,
            timeout=timeout_seconds,
        )
        text = (resp.choices[0].message.content or "").strip()
    parsed = _parse_json_content(text)
    parsed["source"] = "llm"
    parsed["generated_at"] = datetime.utcnow().isoformat()
    return _normalize_advice(parsed)


def generate_ai_advice(db: Session) -> dict:
    snapshot = premium_snapshot(db)
    try:
        return _llm_advice(snapshot, timeout_seconds=AI_ADVICE_TIMEOUT_SECONDS)
    except Exception as exc:
        fallback = _normalize_advice(_fallback_advice(snapshot))
        fallback["llm_error"] = str(exc)
        return fallback


def ai_connection_diagnostics() -> dict:
    checks = {
        "enable_remote_llm": bool(settings.enable_remote_llm),
        "provider": settings.llm_provider,
        "base_url": settings.llm_base_url,
        "model": configured_model(),
        "has_api_key": bool(settings.effective_llm_api_key and settings.effective_llm_api_key != "ollama"),
    }
    if not checks["enable_remote_llm"]:
        return {"ok": False, "mode": "disabled", "checks": checks, "message": "ENABLE_REMOTE_LLM is false."}

    try:
        if is_ollama_provider():
            hc = ollama_healthcheck()
            if not hc.get("ok"):
                return {"ok": False, "mode": "ollama_unreachable", "checks": checks, "message": hc.get("message", "Ollama unavailable")}
            model = configured_model()
            models = hc.get("models", [])
            if models and model not in models:
                return {
                    "ok": False,
                    "mode": "model_missing",
                    "checks": {**checks, "available_models": models[:20]},
                    "message": f"Model '{model}' not found in Ollama. Run: ollama pull {model}",
                }
        ping_messages = [{"role": "user", "content": 'Return exactly this JSON object: {"status":"ok"}'}]
        if is_ollama_provider():
            text = ollama_chat(ping_messages, temperature=0)
        else:
            client = get_llm_client()
            resp = client.chat.completions.create(
                model=configured_model(),
                temperature=0,
                messages=ping_messages,
            )
            text = resp.choices[0].message.content or "{}"
        parsed = _parse_json_content(text)
        return {
            "ok": parsed.get("status") == "ok",
            "mode": "llm",
            "checks": checks,
            "message": "Connected to configured LLM successfully." if parsed.get("status") == "ok" else f"LLM responded but payload was unexpected: {text[:120]}",
        }
    except Exception as exc:
        return {"ok": False, "mode": "llm_error", "checks": checks, "message": str(exc)}
