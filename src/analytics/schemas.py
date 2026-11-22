from datetime import date, datetime
from decimal import Decimal
import uuid
from pydantic import BaseModel, ConfigDict, Field
from src.analytics.models import BankTransaction, TransactionCategory


class BankTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    statement_id: uuid.UUID | None
    tx_date: date
    merchant_raw: str
    merchant_normalized: str
    amount: Decimal
    tx_type: str
    category: str
    is_anomaly: bool
    anomaly_type: str | None
    anomaly_reason: str | None
    is_anomaly_dismissed: bool
    created_at: datetime

    @classmethod
    def from_model(cls, tx: BankTransaction) -> "BankTransactionResponse":
        return cls(
            id=tx.id,
            user_id=tx.user_id,
            statement_id=tx.statement_id,
            tx_date=tx.tx_date,
            merchant_raw=tx.merchant_raw,
            merchant_normalized=tx.merchant_normalized,
            amount=tx.amount,
            tx_type=tx.tx_type,
            category=tx.category,
            is_anomaly=tx.is_anomaly,
            anomaly_type=tx.anomaly_type,
            anomaly_reason=tx.anomaly_reason,
            is_anomaly_dismissed=tx.is_anomaly_dismissed,
            created_at=tx.created_at,
        )


class CategorySpendItem(BaseModel):
    category: str
    amount: Decimal
    percentage: Decimal


class CategoryBreakdownResponse(BaseModel):
    month: str
    total_spend: Decimal
    breakdown: list[CategorySpendItem]


class MonthlyTrendItem(BaseModel):
    month: str
    total_spend: Decimal
    total_income: Decimal


class TrendsResponse(BaseModel):
    months_requested: int
    trends: list[MonthlyTrendItem]


class CashflowResponse(BaseModel):
    month: str
    inflows: Decimal
    outflows: Decimal
    net_savings: Decimal
    savings_rate: Decimal


class TopMerchantItem(BaseModel):
    merchant: str
    total_spend: Decimal
    visit_count: int


class TopMerchantsResponse(BaseModel):
    month: str
    sort_by: str
    merchants: list[TopMerchantItem]


class CategoryOverrideRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=50, description="New category name")
