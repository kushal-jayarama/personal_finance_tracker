from io import BytesIO
from typing import Any

import pandas as pd


COLUMN_ALIASES = {
    "date": {"date", "txn date", "transaction date", "value date", "value dt"},
    "description": {"description", "narration", "remarks", "particulars", "details"},
    "debit": {"debit", "withdrawal", "withdrawal amt", "dr"},
    "credit": {"credit", "deposit", "deposit amt", "cr"},
    "amount": {"amount", "txn amount", "transaction amount"},
    "balance": {"balance", "closing balance", "available balance"},
}


def _normalize_col(col: str) -> str:
    cleaned = (
        col.strip()
        .lower()
        .replace("_", " ")
        .replace(".", " ")
        .replace("/", " ")
        .replace("-", " ")
    )
    return " ".join(cleaned.split())


def _find_column(cols: list[str], target: str) -> str | None:
    aliases = COLUMN_ALIASES[target]
    for col in cols:
        if col in aliases:
            return col
    for col in cols:
        for alias in aliases:
            if alias in col:
                return col
    return None


def _coerce_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", ""), errors="coerce").fillna(0.0)


def parse_statement_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        try:
            df = pd.read_csv(BytesIO(file_bytes), encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(BytesIO(file_bytes), encoding="latin-1")
    else:
        df = pd.read_excel(BytesIO(file_bytes))

    if df.empty:
        raise ValueError("Uploaded statement is empty.")

    raw_cols = list(df.columns)
    norm_cols = [_normalize_col(str(c)) for c in raw_cols]
    col_map = dict(zip(norm_cols, raw_cols))

    date_col = _find_column(norm_cols, "date")
    desc_col = _find_column(norm_cols, "description")
    debit_col = _find_column(norm_cols, "debit")
    credit_col = _find_column(norm_cols, "credit")
    amount_col = _find_column(norm_cols, "amount")
    balance_col = _find_column(norm_cols, "balance")

    if not date_col or not desc_col:
        raise ValueError("Could not detect required Date and Description columns.")

    d = pd.DataFrame()
    d["txn_date"] = pd.to_datetime(df[col_map[date_col]], errors="coerce", dayfirst=True).dt.date
    d["description"] = df[col_map[desc_col]].fillna("").astype(str).str.strip()
    d["description"] = d["description"].replace({"nan": "", "None": ""})

    if debit_col or credit_col:
        debit = _coerce_number(df[col_map[debit_col]]) if debit_col else 0.0
        credit = _coerce_number(df[col_map[credit_col]]) if credit_col else 0.0
        d["amount"] = credit - debit
    elif amount_col:
        amount = _coerce_number(df[col_map[amount_col]])
        desc_l = d["description"].str.lower()
        debit_mask = desc_l.str.contains("debit|dr|withdraw|payment")
        d["amount"] = amount.where(~debit_mask, -amount)
    else:
        raise ValueError("Could not detect amount fields (Debit/Credit or Amount).")

    d["balance"] = _coerce_number(df[col_map[balance_col]]) if balance_col else None

    d = d.dropna(subset=["txn_date"])
    d = d[d["description"] != ""]
    d = d.drop_duplicates(subset=["txn_date", "description", "amount"])
    d["merchant"] = (
        d["description"]
        .str.replace(r"[^a-zA-Z0-9 ]", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.split(" ")
        .str[:3]
        .str.join(" ")
    )
    d["tx_type"] = d["amount"].apply(lambda x: "income" if x >= 0 else "expense")
    return d


def transactions_to_records(df: pd.DataFrame, source_file: str, bank_name: str | None) -> list[dict[str, Any]]:
    records = df.to_dict(orient="records")
    for r in records:
        if pd.isna(r.get("balance")):
            r["balance"] = None
        r["source_file"] = source_file
        r["bank_name"] = bank_name
    return records
