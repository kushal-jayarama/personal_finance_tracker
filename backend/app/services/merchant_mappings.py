from collections import defaultdict

from sqlalchemy.orm import Session

from ..models import CategoryOverride, Transaction
from ..security import decrypt_text


def normalize_merchant(text: str) -> str:
    return " ".join((text or "").lower().strip().split())[:120]


def list_unique_merchant_mappings(db: Session) -> list[dict]:
    txns = db.query(Transaction).all()
    grouped: dict[str, dict] = {}

    for t in txns:
        merchant = decrypt_text(t.merchant_encrypted).strip()
        key = normalize_merchant(merchant)
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "merchant": merchant,
                "count": 0,
                "category_counts": defaultdict(int),
            }
        grouped[key]["count"] += 1
        grouped[key]["category_counts"][t.category] += 1

    out = []
    for _, payload in grouped.items():
        category = max(payload["category_counts"].items(), key=lambda x: x[1])[0]
        out.append(
            {
                "merchant": payload["merchant"],
                "category": category,
                "count": payload["count"],
            }
        )

    out.sort(key=lambda x: (-x["count"], x["merchant"]))
    return out


def apply_merchant_mappings_bulk(db: Session, mappings: list[dict]) -> dict:
    cleaned = {}
    for m in mappings:
        merchant = normalize_merchant(m.get("merchant", ""))
        category = (m.get("category") or "").strip()
        if merchant and category:
            cleaned[merchant] = category

    if not cleaned:
        return {"updated_transactions": 0, "updated_overrides": 0}

    txns = db.query(Transaction).all()
    updated_transactions = 0
    for t in txns:
        merchant = normalize_merchant(decrypt_text(t.merchant_encrypted))
        if merchant in cleaned:
            target = cleaned[merchant]
            if t.category != target:
                t.category = target
                updated_transactions += 1

    updated_overrides = 0
    for merchant, category in cleaned.items():
        ov = db.query(CategoryOverride).filter(CategoryOverride.keyword == merchant).first()
        if ov:
            if ov.category != category:
                ov.category = category
                updated_overrides += 1
        else:
            db.add(CategoryOverride(keyword=merchant, category=category))
            updated_overrides += 1

    db.commit()
    return {"updated_transactions": updated_transactions, "updated_overrides": updated_overrides}
