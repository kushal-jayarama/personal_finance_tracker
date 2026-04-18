import json
from collections.abc import Iterable

from sqlalchemy.orm import Session

from ..models import CategoryOverride
from .llm_client import configured_model, get_llm_client, is_ollama_provider, is_remote_llm_enabled, ollama_chat


DEFAULT_CATEGORY = "Others"
CATEGORY_KEYWORDS = {
    "Food": ["swiggy", "zomato", "restaurant", "cafe", "food", "dominos"],
    "Rent": ["rent", "landlord", "lease", "housing"],
    "Travel": ["uber", "ola", "flight", "rail", "fuel", "petrol", "diesel"],
    "Shopping": ["amazon", "flipkart", "myntra", "store", "shopping"],
    "Bills": ["electricity", "water", "internet", "recharge", "bill", "utility", "netflix", "spotify"],
    "Investment": ["sip", "mutual fund", "nse", "bse", "stock", "zerodha", "groww", "coin"],
    "Salary": ["salary", "payroll", "income", "bonus"],
}


def _normalize_text(text: str) -> str:
    return (text or "").lower().strip()


def categorize_description(description: str, merchant: str, db: Session) -> str:
    text = f"{_normalize_text(description)} {_normalize_text(merchant)}"
    overrides = db.query(CategoryOverride).all()
    for o in overrides:
        if o.keyword.lower() in text:
            return o.category
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return category
    return DEFAULT_CATEGORY


def learn_override(keyword: str, category: str, db: Session) -> None:
    key = keyword.lower().strip()
    if not key:
        return
    existing = db.query(CategoryOverride).filter(CategoryOverride.keyword == key).first()
    if existing:
        existing.category = category
    else:
        db.add(CategoryOverride(keyword=key, category=category))
    db.commit()


def llm_categorize_unresolved(items: Iterable[dict]) -> dict[int, str]:
    items = list(items)
    if not is_remote_llm_enabled() or not items:
        return {}
    payload = [{"id": i["id"], "description": i["description"], "merchant": i["merchant"]} for i in items]
    prompt = (
        "Categorize each transaction into one of exactly: Food, Rent, Travel, Shopping, Bills, "
        "Investment, Salary, Others. Return strict JSON list of objects with keys id and category.\n"
        f"Transactions: {json.dumps(payload)}"
    )
    messages = [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]
    if is_ollama_provider():
        text = ollama_chat(messages, temperature=0, timeout=20)
    else:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=configured_model(),
            temperature=0,
            messages=messages,
        )
        text = (response.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    out: dict[int, str] = {}
    for row in parsed:
        if isinstance(row, dict) and "id" in row and "category" in row:
            out[int(row["id"])] = str(row["category"])
    return out
