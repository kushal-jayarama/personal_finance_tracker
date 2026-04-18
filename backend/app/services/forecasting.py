from datetime import date

import numpy as np
from sqlalchemy.orm import Session

from ..models import Forecast, Transaction


def _month_index(ym: str) -> int:
    year, month = ym.split("-")
    return int(year) * 12 + int(month)


def _fit_next_value(series: list[tuple[str, float]]) -> float:
    if not series:
        return 0.0
    if len(series) == 1:
        return float(series[0][1])
    x = np.array([_month_index(m) for m, _ in series], dtype=float)
    y = np.array([v for _, v in series], dtype=float)
    coeff = np.polyfit(x, y, 1)
    next_x = x.max() + 1
    pred = coeff[0] * next_x + coeff[1]
    return max(float(pred), 0.0)


def run_forecast(db: Session) -> dict:
    txns = db.query(Transaction).order_by(Transaction.txn_date.asc()).all()
    monthly_income: dict[str, float] = {}
    monthly_expense: dict[str, float] = {}
    latest_balance = 0.0
    for t in txns:
        m = t.txn_date.strftime("%Y-%m")
        if t.amount >= 0:
            monthly_income[m] = monthly_income.get(m, 0.0) + t.amount
        else:
            monthly_expense[m] = monthly_expense.get(m, 0.0) + abs(t.amount)
        if t.balance is not None:
            latest_balance = t.balance

    income_series = sorted(monthly_income.items())
    expense_series = sorted(monthly_expense.items())
    next_expense = _fit_next_value(expense_series)
    next_income = _fit_next_value(income_series)
    next_savings = next_income - next_expense
    next_balance = latest_balance + next_savings

    if income_series:
        latest_month = income_series[-1][0]
    elif expense_series:
        latest_month = expense_series[-1][0]
    else:
        latest_month = date.today().strftime("%Y-%m")

    y, m = latest_month.split("-")
    y_i, m_i = int(y), int(m)
    next_month = f"{y_i + 1}-01" if m_i == 12 else f"{y_i}-{m_i + 1:02d}"

    db.query(Forecast).filter(Forecast.forecast_month == next_month, Forecast.metric.in_(["monthly_expense", "monthly_savings", "account_balance"])).delete(synchronize_session=False)
    db.add(Forecast(forecast_month=next_month, metric="monthly_expense", value=next_expense, model_name="linear_regression"))
    db.add(Forecast(forecast_month=next_month, metric="monthly_savings", value=next_savings, model_name="linear_regression"))
    db.add(Forecast(forecast_month=next_month, metric="account_balance", value=next_balance, model_name="linear_regression"))
    db.commit()

    return {
        "monthly_expense_forecast": round(next_expense, 2),
        "monthly_savings_forecast": round(next_savings, 2),
        "next_balance_forecast": round(next_balance, 2),
        "model_name": "linear_regression",
    }
