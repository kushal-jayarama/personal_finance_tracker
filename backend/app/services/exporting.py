from io import BytesIO

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from ..models import Transaction
from ..security import decrypt_text
from .analytics import compute_dashboard


def export_transactions_excel(db: Session) -> bytes:
    txns = db.query(Transaction).order_by(Transaction.txn_date.asc()).all()
    rows = []
    for t in txns:
        rows.append(
            {
                "Date": t.txn_date.isoformat(),
                "Description": decrypt_text(t.description_encrypted),
                "Merchant": decrypt_text(t.merchant_encrypted),
                "Amount": t.amount,
                "Type": t.tx_type,
                "Category": t.category,
                "Balance": t.balance,
                "Bank": t.bank_name,
            }
        )
    df = pd.DataFrame(rows)
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Transactions")
    return stream.getvalue()


def export_summary_pdf(db: Session) -> bytes:
    dashboard = compute_dashboard(db)
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Personal Finance Tracker - Summary Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Income: {dashboard['totals']['income']}", styles["Normal"]),
        Paragraph(f"Expense: {dashboard['totals']['expense']}", styles["Normal"]),
        Paragraph(f"Savings: {dashboard['totals']['savings']}", styles["Normal"]),
        Paragraph(f"Savings Rate: {dashboard['totals']['savings_rate']}%", styles["Normal"]),
        Spacer(1, 12),
        Paragraph("Top Categories", styles["Heading2"]),
    ]
    for c in dashboard["by_category"][:8]:
        story.append(Paragraph(f"{c['category']}: {c['amount']}", styles["Normal"]))
    doc.build(story)
    return stream.getvalue()
