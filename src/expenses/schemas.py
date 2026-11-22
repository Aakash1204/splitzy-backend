from decimal import Decimal
import uuid
from pydantic import BaseModel, ConfigDict
from src.core.types import MoneyDecimal


class ExpenseSplitCreate(BaseModel):
    user_id: uuid.UUID
    split_amount: MoneyDecimal


class ExpenseSplitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: uuid.UUID
    split_amount: Decimal
    is_settled: bool


class ExpenseCreate(BaseModel):
    title: str
    description: str | None = None
    total_amount: MoneyDecimal
    currency: str = "USD"
    payer_id: uuid.UUID
    splits: list[ExpenseSplitCreate] = []


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    total_amount: Decimal
    currency: str
    payer_id: uuid.UUID
    splits: list[ExpenseSplitResponse] = []
