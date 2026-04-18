from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, pstdev

from sqlalchemy.orm import Session

from ..models import Budget, Goal, Transaction
from ..security import decrypt_text


def _safe_pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return max(0.0, min(100.0, (num / den) * 100.0))


def _latest_balance(txns: list[Transaction]) -> float:
    latest = [t.balance for t in txns if t.balance is not None]
    return float(latest[-1]) if latest else 0.0


def _upcoming_bills(txns: list[Transaction]) -> list[dict]:
    recurring: dict[str, list[Transaction]] = defaultdict(list)
    for t in txns:
        if t.amount < 0:
            recurring[decrypt_text(t.merchant_encrypted)].append(t)

    upcoming = []
    today = date.today()
    for merchant, rows in recurring.items():
        if len(rows) < 3:
            continue
        by_month = defaultdict(int)
        for r in rows:
            by_month[r.txn_date.strftime("%Y-%m")] += 1
        if len(by_month) < 2:
            continue
        avg_amt = round(sum(abs(r.amount) for r in rows[-6:]) / min(len(rows), 6), 2)
        avg_day = int(round(sum(r.txn_date.day for r in rows[-6:]) / min(len(rows), 6)))
        try:
            due = date(today.year, today.month, max(1, min(avg_day, 28)))
        except ValueError:
            due = today + timedelta(days=7)
        if due < today:
            next_month = today.replace(day=28) + timedelta(days=4)
            due = date(next_month.year, next_month.month, max(1, min(avg_day, 28)))
        upcoming.append(
            {
                "merchant": merchant,
                "expected_amount": avg_amt,
                "due_date": due.isoformat(),
                "days_left": (due - today).days,
            }
        )
    upcoming.sort(key=lambda x: (x["days_left"], -x["expected_amount"]))
    return upcoming[:8]


def _monthly_expense_by_category(txns: list[Transaction]) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    monthly_total: dict[str, float] = defaultdict(float)
    cat_monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in txns:
        if t.amount < 0:
            month = t.txn_date.strftime("%Y-%m")
            amt = abs(t.amount)
            monthly_total[month] += amt
            cat_monthly[t.category][month] += amt
    return dict(monthly_total), {k: dict(v) for k, v in cat_monthly.items()}


def _overspending_alerts(
    budgets: list[Budget], current_month: str, month_total: dict[str, float], spent_by_category: dict[str, float]
) -> list[dict]:
    alerts: list[dict] = []
    months_sorted = sorted(month_total.keys())
    current_expense = month_total.get(current_month, 0.0)

    if current_month in months_sorted:
        idx = months_sorted.index(current_month)
    else:
        idx = len(months_sorted) - 1

    prev_expense = month_total.get(months_sorted[idx - 1], 0.0) if idx > 0 else 0.0
    if prev_expense > 0 and current_expense > prev_expense * 1.15:
        pct = round((current_expense - prev_expense) / prev_expense * 100, 1)
        alerts.append(
            {
                "severity": "high",
                "title": "Month-over-month overspending",
                "message": f"Spending is up by {pct}% vs previous month.",
            }
        )

    last3 = [month_total[m] for m in months_sorted[max(0, idx - 3) : idx]]
    if len(last3) >= 2:
        avg_last3 = mean(last3)
        if avg_last3 > 0 and current_expense > avg_last3 * 1.25:
            pct = round((current_expense - avg_last3) / avg_last3 * 100, 1)
            alerts.append(
                {
                    "severity": "high",
                    "title": "Spending spike vs recent trend",
                    "message": f"Current month spend is {pct}% above your recent 3-month average.",
                }
            )

    for b in budgets:
        spent = spent_by_category.get(b.category, 0.0)
        if spent > b.amount:
            alerts.append(
                {
                    "severity": "high",
                    "title": f"Budget exceeded: {b.category}",
                    "message": f"Spent {round(spent,2)} against budget {round(b.amount,2)}.",
                }
            )
        elif b.amount > 0 and spent >= b.amount * 0.85:
            alerts.append(
                {
                    "severity": "medium",
                    "title": f"Budget nearing limit: {b.category}",
                    "message": f"Used {round(spent / b.amount * 100,1)}% of category budget.",
                }
            )

    return alerts[:8]


def _spending_pattern_detection(txns: list[Transaction], current_month: str) -> list[dict]:
    patterns: list[dict] = []
    month_rows = [t for t in txns if t.amount < 0 and t.txn_date.strftime("%Y-%m") == current_month]
    if not month_rows:
        return patterns

    weekday_spend: dict[int, float] = defaultdict(float)
    merchant_spend: dict[str, float] = defaultdict(float)
    weekend_spend = 0.0
    total = 0.0
    for t in month_rows:
        amt = abs(t.amount)
        total += amt
        wd = t.txn_date.weekday()
        weekday_spend[wd] += amt
        if wd >= 5:
            weekend_spend += amt
        merchant_spend[decrypt_text(t.merchant_encrypted)] += amt

    if weekday_spend:
        top_day = max(weekday_spend.items(), key=lambda x: x[1])[0]
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        patterns.append(
            {
                "pattern": "peak_spending_day",
                "message": f"You spend the most on {day_names[top_day]} this month.",
            }
        )

    weekend_pct = (weekend_spend / total * 100) if total > 0 else 0
    if weekend_pct >= 45:
        patterns.append(
            {
                "pattern": "weekend_heavy",
                "message": f"{round(weekend_pct,1)}% of spend happens on weekends.",
            }
        )

    if merchant_spend and total > 0:
        merchant, val = max(merchant_spend.items(), key=lambda x: x[1])
        share = val / total * 100
        if share >= 18:
            patterns.append(
                {
                    "pattern": "merchant_concentration",
                    "message": f"{merchant} accounts for {round(share,1)}% of this month's spend.",
                }
            )

    return patterns[:6]


def _category_anomalies(cat_monthly: dict[str, dict[str, float]], current_month: str) -> list[dict]:
    anomalies: list[dict] = []
    for category, monthly in cat_monthly.items():
        if current_month not in monthly:
            continue
        current_val = monthly[current_month]
        history = [v for m, v in monthly.items() if m != current_month]
        if len(history) < 3:
            continue
        base = mean(history)
        std = pstdev(history) if len(history) > 1 else 0.0
        threshold = base + 2 * std
        if current_val > max(threshold, base * 1.3, 500):
            pct = round(((current_val - base) / base * 100), 1) if base > 0 else 999.0
            anomalies.append(
                {
                    "category": category,
                    "current": round(current_val, 2),
                    "baseline": round(base, 2),
                    "change_pct": pct,
                    "message": f"{category} spend is unusually high this month.",
                }
            )
    anomalies.sort(key=lambda x: x["change_pct"], reverse=True)
    return anomalies[:8]


def premium_snapshot(db: Session) -> dict:
    txns = db.query(Transaction).order_by(Transaction.txn_date.asc()).all()
    if not txns:
        return {
            "net_worth_estimate": 0.0,
            "financial_health_score": 0,
            "health_breakdown": {"savings_discipline": 0, "budget_control": 0, "cash_buffer": 0},
            "weekly_recap": {"income": 0.0, "expense": 0.0, "top_category": "N/A", "top_merchant": "N/A"},
            "upcoming_bills": [],
            "overspending_alerts": [],
            "spending_patterns": [],
            "category_anomalies": [],
        }

    income = sum(t.amount for t in txns if t.amount > 0)
    expense = abs(sum(t.amount for t in txns if t.amount < 0))
    savings_rate = (income - expense) / income if income else 0.0

    current_month = txns[-1].txn_date.strftime("%Y-%m")
    budgets = db.query(Budget).filter(Budget.month == current_month).all()
    spent_by_category: dict[str, float] = defaultdict(float)
    for t in txns:
        if t.amount < 0:
            spent_by_category[t.category] += abs(t.amount)
    if budgets:
        on_budget = 0
        for b in budgets:
            if spent_by_category.get(b.category, 0) <= b.amount:
                on_budget += 1
        budget_control = _safe_pct(on_budget, len(budgets))
    else:
        budget_control = 60.0

    monthly_expense_avg = expense / max(len({t.txn_date.strftime("%Y-%m") for t in txns}), 1)
    cash_buffer_months = (_latest_balance(txns) / monthly_expense_avg) if monthly_expense_avg > 0 else 0.0
    cash_buffer_score = min(100.0, cash_buffer_months * 30.0)
    savings_score = min(100.0, max(0.0, savings_rate * 250.0))
    final_score = round(0.45 * savings_score + 0.30 * budget_control + 0.25 * cash_buffer_score)

    cutoff = date.today() - timedelta(days=7)
    recent = [t for t in txns if t.txn_date >= cutoff]
    weekly_income = sum(t.amount for t in recent if t.amount > 0)
    weekly_expense = abs(sum(t.amount for t in recent if t.amount < 0))
    by_cat: dict[str, float] = defaultdict(float)
    by_merchant: dict[str, float] = defaultdict(float)
    for t in recent:
        if t.amount < 0:
            by_cat[t.category] += abs(t.amount)
            by_merchant[decrypt_text(t.merchant_encrypted)] += abs(t.amount)
    top_category = max(by_cat.items(), key=lambda x: x[1])[0] if by_cat else "N/A"
    top_merchant = max(by_merchant.items(), key=lambda x: x[1])[0] if by_merchant else "N/A"
    month_total, cat_monthly = _monthly_expense_by_category(txns)

    return {
        "net_worth_estimate": round(_latest_balance(txns), 2),
        "financial_health_score": int(final_score),
        "health_breakdown": {
            "savings_discipline": round(savings_score, 1),
            "budget_control": round(budget_control, 1),
            "cash_buffer": round(cash_buffer_score, 1),
        },
        "weekly_recap": {
            "income": round(weekly_income, 2),
            "expense": round(weekly_expense, 2),
            "top_category": top_category,
            "top_merchant": top_merchant,
        },
        "upcoming_bills": _upcoming_bills(txns),
        "overspending_alerts": _overspending_alerts(budgets, current_month, month_total, spent_by_category),
        "spending_patterns": _spending_pattern_detection(txns, current_month),
        "category_anomalies": _category_anomalies(cat_monthly, current_month),
    }


def close_goal_if_reached(goal: Goal) -> None:
    if goal.current_amount >= goal.target_amount:
        goal.status = "completed"
