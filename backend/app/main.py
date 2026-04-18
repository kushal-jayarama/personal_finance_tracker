from datetime import date

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .models import Budget, Goal, Transaction
from .schemas import (
    BudgetIn,
    BudgetOut,
    CategoryOverrideIn,
    DashboardResponse,
    ForecastResponse,
    GoalIn,
    GoalOut,
    GoalProgressIn,
    MerchantMappingBulkIn,
    MerchantMappingOut,
    TransactionOut,
)
from .security import decrypt_text, encrypt_text
from .services.analytics import compute_dashboard, transaction_dict
from .services.ai_advice import ai_connection_diagnostics, generate_ai_advice
from .services.categorization import categorize_description, learn_override, llm_categorize_unresolved
from .services.exporting import export_summary_pdf, export_transactions_excel
from .services.forecasting import run_forecast
from .services.insights import generate_insights, list_insights
from .services.merchant_mappings import apply_merchant_mappings_bulk, list_unique_merchant_mappings
from .services.parsing import parse_statement_file, transactions_to_records
from .services.premium import close_goal_if_reached, premium_snapshot

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _norm_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _canonical_signature(txn_date: date, description: str | None, amount: float, balance: float | None) -> tuple:
    rounded_balance = None if balance is None else round(float(balance), 2)
    return (
        txn_date.isoformat(),
        _norm_text(description),
        round(float(amount), 2),
        rounded_balance,
    )


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/upload-statement")
async def upload_statement(
    file: UploadFile = File(...),
    bank_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        content = await file.read()
        df = parse_statement_file(content, file.filename or "statement")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse statement: {exc}") from exc

    rows = transactions_to_records(df, file.filename or "statement", bank_name)
    if not rows:
        return {"inserted": 0, "duplicates_skipped": 0}

    min_date = min(r["txn_date"] for r in rows)
    max_date = max(r["txn_date"] for r in rows)
    existing_candidates = (
        db.query(Transaction)
        .filter(Transaction.txn_date >= min_date, Transaction.txn_date <= max_date)
        .all()
    )
    existing_signatures = {
        _canonical_signature(
            t.txn_date,
            decrypt_text(t.description_encrypted),
            t.amount,
            t.balance,
        )
        for t in existing_candidates
    }

    created_ids = []
    duplicates_skipped = 0
    for row in rows:
        signature = _canonical_signature(
            row["txn_date"],
            row.get("description"),
            float(row["amount"]),
            float(row["balance"]) if row["balance"] is not None else None,
        )
        if signature in existing_signatures:
            duplicates_skipped += 1
            continue

        tx = Transaction(
            txn_date=row["txn_date"],
            description_encrypted=encrypt_text(row["description"]),
            merchant_encrypted=encrypt_text(row["merchant"]),
            amount=float(row["amount"]),
            tx_type=row["tx_type"],
            category=categorize_description(row["description"], row["merchant"], db),
            balance=float(row["balance"]) if row["balance"] is not None else None,
            bank_name=row["bank_name"],
            source_file=row["source_file"],
        )
        db.add(tx)
        db.flush()
        created_ids.append(tx.id)
        existing_signatures.add(signature)

    unresolved = []
    if created_ids:
        inserted = db.query(Transaction).filter(Transaction.id.in_(created_ids)).all()
        for t in inserted:
            if t.category == "Others":
                unresolved.append({"id": t.id, "description": decrypt_text(t.description_encrypted), "merchant": decrypt_text(t.merchant_encrypted)})
        llm_labels = llm_categorize_unresolved(unresolved)
        for t in inserted:
            if t.id in llm_labels:
                t.category = llm_labels[t.id]

    db.commit()
    return {"inserted": len(created_ids), "duplicates_skipped": duplicates_skipped}


@app.get("/api/transactions", response_model=list[TransactionOut])
def list_transactions(
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Transaction)
    if start:
        q = q.filter(Transaction.txn_date >= start)
    if end:
        q = q.filter(Transaction.txn_date <= end)
    if category:
        q = q.filter(Transaction.category == category)
    txns = q.order_by(Transaction.txn_date.desc()).limit(5000).all()
    return [transaction_dict(t) for t in txns]


@app.patch("/api/transactions/{transaction_id}/category")
def update_transaction_category(transaction_id: int, payload: CategoryOverrideIn, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    tx.category = payload.category
    db.commit()
    learn_override(payload.keyword, payload.category, db)
    return {"ok": True}


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
):
    return compute_dashboard(db, start=start, end=end, category=category)


@app.post("/api/insights/generate")
def create_insights(db: Session = Depends(get_db)):
    generated = generate_insights(db)
    return {"generated": generated}


@app.get("/api/insights")
def get_insights(db: Session = Depends(get_db)):
    return list_insights(db)


@app.post("/api/forecast", response_model=ForecastResponse)
def forecast(db: Session = Depends(get_db)):
    return run_forecast(db)


@app.post("/api/budgets", response_model=BudgetOut)
def upsert_budget(payload: BudgetIn, db: Session = Depends(get_db)):
    existing = db.query(Budget).filter(Budget.category == payload.category, Budget.month == payload.month).first()
    if existing:
        existing.amount = payload.amount
        db.commit()
        db.refresh(existing)
        return existing
    b = Budget(category=payload.category, amount=payload.amount, month=payload.month)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@app.get("/api/budgets", response_model=list[BudgetOut])
def list_budgets(month: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Budget)
    if month:
        q = q.filter(Budget.month == month)
    return q.order_by(Budget.created_at.desc()).all()


@app.get("/api/export/transactions.xlsx")
def export_xlsx(db: Session = Depends(get_db)):
    content = export_transactions_excel(db)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions_export.xlsx"},
    )


@app.get("/api/export/summary.pdf")
def export_pdf(db: Session = Depends(get_db)):
    content = export_summary_pdf(db)
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=monthly_summary.pdf"})


@app.get("/api/premium/overview")
def get_premium_overview(db: Session = Depends(get_db)):
    return premium_snapshot(db)


@app.post("/api/goals", response_model=GoalOut)
def create_goal(payload: GoalIn, db: Session = Depends(get_db)):
    g = Goal(
        title=payload.title.strip(),
        target_amount=payload.target_amount,
        current_amount=payload.current_amount,
        target_date=payload.target_date,
    )
    close_goal_if_reached(g)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@app.get("/api/goals", response_model=list[GoalOut])
def list_goals(db: Session = Depends(get_db)):
    return db.query(Goal).order_by(Goal.created_at.desc()).all()


@app.patch("/api/goals/{goal_id}/progress", response_model=GoalOut)
def update_goal_progress(goal_id: int, payload: GoalProgressIn, db: Session = Depends(get_db)):
    g = db.query(Goal).filter(Goal.id == goal_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found.")
    g.current_amount = payload.current_amount
    close_goal_if_reached(g)
    db.commit()
    db.refresh(g)
    return g


@app.get("/api/merchant-mappings", response_model=list[MerchantMappingOut])
def get_merchant_mappings(db: Session = Depends(get_db)):
    return list_unique_merchant_mappings(db)


@app.put("/api/merchant-mappings/bulk")
def put_merchant_mappings(payload: MerchantMappingBulkIn, db: Session = Depends(get_db)):
    return apply_merchant_mappings_bulk(db, [m.model_dump() for m in payload.mappings])


@app.get("/api/ai/advice")
def get_ai_advice(db: Session = Depends(get_db)):
    return generate_ai_advice(db)


@app.get("/api/ai/diagnostics")
def get_ai_diagnostics():
    return ai_connection_diagnostics()
