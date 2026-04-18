from collections import defaultdict
from datetime import date

import numpy as np
from sqlalchemy.orm import Session

from ..models import Budget, Transaction
from ..security import decrypt_text


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def transaction_dict(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "txn_date": tx.txn_date,
        "description": decrypt_text(tx.description_encrypted),
        "merchant": decrypt_text(tx.merchant_encrypted),
        "amount": tx.amount,
        "tx_type": tx.tx_type,
        "category": tx.category,
        "balance": tx.balance,
        "bank_name": tx.bank_name,
    }


def compute_dashboard(db: Session, start: date | None = None, end: date | None = None, category: str | None = None):
    q = db.query(Transaction)
    if start:
        q = q.filter(Transaction.txn_date >= start)
    if end:
        q = q.filter(Transaction.txn_date <= end)
    if category:
        q = q.filter(Transaction.category == category)
    txns = q.order_by(Transaction.txn_date.asc()).all()

    income = sum(t.amount for t in txns if t.amount > 0)
    expenses = abs(sum(t.amount for t in txns if t.amount < 0))
    savings = income - expenses
    savings_rate = (savings / income * 100.0) if income else 0.0
    burn_rate = (expenses / len(txns)) if txns else 0.0

    by_category_raw: dict[str, float] = defaultdict(float)
    monthly: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    merchant_spend: dict[str, float] = defaultdict(float)
    recurring_counter: dict[tuple[str, str], int] = defaultdict(int)

    for t in txns:
        m = month_key(t.txn_date)
        merchant = decrypt_text(t.merchant_encrypted)
        if t.amount < 0:
            by_category_raw[t.category] += abs(t.amount)
            monthly[m]["expense"] += abs(t.amount)
            merchant_spend[merchant] += abs(t.amount)
            recurring_counter[(merchant, m)] += 1
        else:
            monthly[m]["income"] += t.amount

    by_category = [{"category": c, "amount": round(v, 2)} for c, v in sorted(by_category_raw.items(), key=lambda x: x[1], reverse=True)]
    monthly_trend = [{"month": m, "income": round(v["income"], 2), "expense": round(v["expense"], 2), "savings": round(v["income"] - v["expense"], 2)} for m, v in sorted(monthly.items())]
    top_merchants = [{"merchant": k, "spend": round(v, 2)} for k, v in sorted(merchant_spend.items(), key=lambda x: x[1], reverse=True)[:10]]

    recurring = []
    merchant_month_counts: dict[str, int] = defaultdict(int)
    for (merchant, _), count in recurring_counter.items():
        if count >= 1:
            merchant_month_counts[merchant] += 1
    for merchant, months in merchant_month_counts.items():
        if months >= 3:
            recurring.append({"merchant": merchant, "months_seen": months, "avg_monthly_obligation": round(merchant_spend[merchant] / max(months, 1), 2)})

    current_month = date.today().strftime("%Y-%m")
    budgets = db.query(Budget).filter(Budget.month == current_month).all()
    spent_by_cat = {x["category"]: x["amount"] for x in by_category}
    budget_status = []
    for b in budgets:
        spent = spent_by_cat.get(b.category, 0.0)
        usage = (spent / b.amount * 100) if b.amount else 0.0
        budget_status.append({"category": b.category, "budget": b.amount, "spent": round(spent, 2), "usage_pct": round(usage, 2), "status": "over" if usage > 100 else "near" if usage >= 85 else "ok"})

    return {
        "totals": {
            "income": round(income, 2),
            "expense": round(expenses, 2),
            "savings": round(savings, 2),
            "savings_rate": round(savings_rate, 2),
            "burn_rate": round(float(burn_rate), 2),
            "tx_count": len(txns),
        },
        "by_category": by_category,
        "monthly_trend": monthly_trend,
        "top_merchants": top_merchants,
        "recurring_payments": recurring,
        "budget_status": budget_status,
    }


def detect_unusual_transactions(txns: list[Transaction]) -> list[dict]:
    expenses = [abs(t.amount) for t in txns if t.amount < 0]
    if len(expenses) < 4:
        return []
    mean = float(np.mean(expenses))
    std = float(np.std(expenses))
    threshold = mean + 2 * std
    unusual = []
    for t in txns:
        if t.amount < 0 and abs(t.amount) > threshold:
            unusual.append({
                "id": t.id,
                "txn_date": t.txn_date.isoformat(),
                "merchant": decrypt_text(t.merchant_encrypted),
                "amount": round(abs(t.amount), 2),
                "reason": "Amount significantly above normal spending pattern",
            })
    return unusual[:15]
