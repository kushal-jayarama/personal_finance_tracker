from datetime import date

from sqlalchemy.orm import Session

from ..models import Insight, Transaction
from .analytics import compute_dashboard, detect_unusual_transactions, month_key


def generate_insights(db: Session) -> list[dict]:
    today = date.today()
    current_month = today.strftime("%Y-%m")
    year = today.year
    month = today.month
    prev_month = f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"

    dashboard = compute_dashboard(db)
    current_total = next((x["expense"] for x in dashboard["monthly_trend"] if x["month"] == current_month), 0.0)
    prev_total = next((x["expense"] for x in dashboard["monthly_trend"] if x["month"] == prev_month), 0.0)
    insights: list[dict] = []

    if prev_total > 0 and current_total > prev_total * 1.2:
        pct = round((current_total - prev_total) / prev_total * 100, 1)
        insights.append({"type": "overspending", "severity": "high", "content": f"You are spending {pct}% more than last month."})

    for cat in dashboard["by_category"][:3]:
        if cat["amount"] > 0.35 * dashboard["totals"]["expense"] and dashboard["totals"]["expense"] > 0:
            insights.append({"type": "top_category", "severity": "medium", "content": f"{cat['category']} is one of your highest spending categories this period."})

    txns = db.query(Transaction).all()
    unusual = detect_unusual_transactions(txns)
    if unusual:
        insights.append({"type": "anomaly", "severity": "high", "content": f"{len(unusual)} unusual transactions detected."})

    existing = {(i.insight_type, i.content) for i in db.query(Insight).filter(Insight.month == current_month).all()}
    created = []
    for insight in insights:
        key = (insight["type"], insight["content"])
        if key in existing:
            continue
        record = Insight(month=current_month, insight_type=insight["type"], severity=insight["severity"], content=insight["content"])
        db.add(record)
        created.append(insight)
    db.commit()

    recurring = dashboard["recurring_payments"]
    if recurring:
        created.append({"type": "recurring", "severity": "info", "content": f"Detected {len(recurring)} recurring payment merchants."})
    return created


def list_insights(db: Session) -> list[dict]:
    all_insights = db.query(Insight).order_by(Insight.created_at.desc()).limit(100).all()
    return [{"id": i.id, "month": i.month, "type": i.insight_type, "severity": i.severity, "content": i.content} for i in all_insights]
