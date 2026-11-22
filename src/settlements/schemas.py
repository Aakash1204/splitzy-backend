from datetime import datetime
from decimal import Decimal
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator
from src.core.types import MoneyDecimal
from src.settlements.models import Settlement
from src.users.schemas import UserProfileResponse


class SettlementCreateRequest(BaseModel):
    payer_id: uuid.UUID = Field(..., description="UUID of the user paying the settlement")
    payee_id: uuid.UUID = Field(..., description="UUID of the user receiving the settlement")
    amount: MoneyDecimal = Field(
        ...,
        gt=Decimal("0.00"),
        description="Settlement amount (strictly NUMERIC(12, 2), greater than zero)",
    )
    settled_at: datetime | None = Field(default=None, description="Timestamp of payment (defaults to NOW)")

    @model_validator(mode="after")
    def validate_payer_not_payee(self) -> "SettlementCreateRequest":
        if self.payer_id == self.payee_id:
            raise ValueError("Payer and payee cannot be the same user")
        return self


class SettlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    payer_id: uuid.UUID
    payee_id: uuid.UUID
    amount: Decimal
    created_by: uuid.UUID
    settled_at: datetime

    payer: UserProfileResponse | None = None
    payee: UserProfileResponse | None = None
    creator: UserProfileResponse | None = None

    @classmethod
    def from_model(cls, settlement: Settlement) -> "SettlementResponse":
        return cls(
            id=settlement.id,
            room_id=settlement.room_id,
            payer_id=settlement.payer_id,
            payee_id=settlement.payee_id,
            amount=settlement.amount,
            created_by=settlement.created_by,
            settled_at=settlement.settled_at,
            payer=UserProfileResponse.model_validate(settlement.payer) if settlement.payer else None,
            payee=UserProfileResponse.model_validate(settlement.payee) if settlement.payee else None,
            creator=UserProfileResponse.model_validate(settlement.creator) if settlement.creator else None,
        )
