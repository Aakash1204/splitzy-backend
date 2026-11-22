from datetime import date, datetime
from decimal import Decimal
import uuid
from pydantic import BaseModel, ConfigDict, Field
from src.core.types import MoneyDecimal
from src.expenses.models import ExpenseShare, SplitExpense, SplitType
from src.users.schemas import UserProfileResponse


class ExpenseShareInput(BaseModel):
    user_id: uuid.UUID = Field(..., description="UUID of the participant")
    value: Decimal | None = Field(
        default=None,
        description="Split value (exact amount for EXACT, percentage for PERCENTAGE, shares count for SHARES, omitted for EQUAL)",
    )


class ExpenseShareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    expense_id: uuid.UUID
    user_id: uuid.UUID
    owed_amount: Decimal
    share_input: Decimal | None = None
    user: UserProfileResponse | None = None

    @classmethod
    def from_model(cls, share: ExpenseShare) -> "ExpenseShareResponse":
        return cls(
            id=share.id,
            expense_id=share.expense_id,
            user_id=share.user_id,
            owed_amount=share.owed_amount,
            share_input=share.share_input,
            user=UserProfileResponse.model_validate(share.user) if share.user else None,
        )


class SplitExpenseCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150, description="Title of the expense")
    total_amount: MoneyDecimal = Field(
        ...,
        gt=Decimal("0.00"),
        description="Total monetary amount (strictly NUMERIC(12, 2), greater than zero)",
    )
    paid_by: uuid.UUID = Field(..., description="UUID of the user who paid for this expense")
    split_type: SplitType = Field(default=SplitType.EQUAL, description="Split distribution strategy")
    expense_date: date | None = Field(default=None, description="Date of expense (defaults to today)")
    participants: list[ExpenseShareInput] | None = Field(
        default=None,
        description="Optional list of participants and split inputs. If split_type is EQUAL and omitted, defaults to all room members.",
    )


class SplitExpenseUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    total_amount: MoneyDecimal | None = Field(default=None, gt=Decimal("0.00"))
    paid_by: uuid.UUID | None = Field(default=None)
    split_type: SplitType | None = Field(default=None)
    expense_date: date | None = Field(default=None)
    participants: list[ExpenseShareInput] | None = Field(
        default=None,
        description="If provided, replaces existing participant shares",
    )


class SplitExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    title: str
    total_amount: Decimal
    paid_by: uuid.UUID
    created_by: uuid.UUID
    split_type: str
    expense_date: date
    created_at: datetime
    updated_at: datetime

    # Strictly computed dynamically at runtime (never stored in database)
    can_edit: bool = False
    can_delete: bool = False

    # Requesting user's personal owed/lent delta
    user_net_delta: Decimal = Decimal("0.00")
    user_owed_amount: Decimal = Decimal("0.00")
    is_payer: bool = False

    payer: UserProfileResponse | None = None
    creator: UserProfileResponse | None = None
    shares: list[ExpenseShareResponse] = []

    @classmethod
    def from_model(cls, expense: SplitExpense, current_user_id: uuid.UUID) -> "SplitExpenseResponse":
        is_creator = (expense.created_by == current_user_id)
        is_payer = (expense.paid_by == current_user_id)

        # Calculate requesting user's owed/lent delta
        my_share = next((s for s in expense.shares if s.user_id == current_user_id), None)
        user_owed_amount = my_share.owed_amount if my_share else Decimal("0.00")

        if is_payer:
            # Payer paid total_amount, and owes user_owed_amount, net effect = +(total_amount - user_owed_amount)
            user_net_delta = expense.total_amount - user_owed_amount
        else:
            # Non-payer: net effect = -user_owed_amount if involved, else 0.00
            user_net_delta = -user_owed_amount if my_share else Decimal("0.00")

        return cls(
            id=expense.id,
            room_id=expense.room_id,
            title=expense.title,
            total_amount=expense.total_amount,
            paid_by=expense.paid_by,
            created_by=expense.created_by,
            split_type=expense.split_type,
            expense_date=expense.expense_date,
            created_at=expense.created_at,
            updated_at=expense.updated_at,
            can_edit=is_creator,
            can_delete=is_creator,
            user_net_delta=user_net_delta,
            user_owed_amount=user_owed_amount,
            is_payer=is_payer,
            payer=UserProfileResponse.model_validate(expense.payer) if expense.payer else None,
            creator=UserProfileResponse.model_validate(expense.creator) if expense.creator else None,
            shares=[ExpenseShareResponse.from_model(s) for s in expense.shares],
        )


class MemberBalanceResponse(BaseModel):
    user: UserProfileResponse
    total_paid: Decimal
    total_owed: Decimal
    settlements_paid_out: Decimal = Decimal("0.00")
    settlements_received: Decimal = Decimal("0.00")
    net_balance: Decimal  # total_paid - total_share_owed + settlements_paid_out - settlements_received


class PairwiseDebtResponse(BaseModel):
    from_user: UserProfileResponse
    to_user: UserProfileResponse
    amount: Decimal


class RoomBalancesResponse(BaseModel):
    room_id: uuid.UUID
    balances: list[MemberBalanceResponse]
    debts: list[PairwiseDebtResponse]


class DeleteExpenseResponse(BaseModel):
    message: str = Field(..., description="Status message")
    expense_id: str = Field(..., description="UUID of the deleted expense")

