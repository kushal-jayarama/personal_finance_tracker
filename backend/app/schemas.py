from datetime import date, datetime

from pydantic import BaseModel, Field


class TransactionOut(BaseModel):
    id: int
    txn_date: date
    description: str
    merchant: str
    amount: float
    tx_type: str
    category: str
    balance: float | None
    bank_name: str | None

    class Config:
        from_attributes = True


class BudgetIn(BaseModel):
    category: str
    amount: float = Field(gt=0)
    month: str = Field(pattern=r"^\d{4}-\d{2}$")


class BudgetOut(BudgetIn):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class CategoryOverrideIn(BaseModel):
    keyword: str
    category: str


class DashboardResponse(BaseModel):
    totals: dict
    by_category: list[dict]
    monthly_trend: list[dict]
    top_merchants: list[dict]
    recurring_payments: list[dict]
    budget_status: list[dict]


class ForecastResponse(BaseModel):
    monthly_expense_forecast: float
    monthly_savings_forecast: float
    next_balance_forecast: float
    model_name: str


class GoalIn(BaseModel):
    title: str
    target_amount: float = Field(gt=0)
    current_amount: float = Field(ge=0, default=0)
    target_date: date | None = None


class GoalProgressIn(BaseModel):
    current_amount: float = Field(ge=0)


class GoalOut(GoalIn):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class MerchantMappingOut(BaseModel):
    merchant: str
    category: str
    count: int


class MerchantMappingBulkItem(BaseModel):
    merchant: str
    category: str


class MerchantMappingBulkIn(BaseModel):
    mappings: list[MerchantMappingBulkItem]
