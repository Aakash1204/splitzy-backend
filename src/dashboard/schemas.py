from decimal import Decimal
import uuid
from pydantic import BaseModel


class ActiveRoomSummary(BaseModel):
    room_id: uuid.UUID
    name: str
    category: str
    icon: str
    member_count: int
    user_net_balance: Decimal


class DashboardSummaryResponse(BaseModel):
    month: str
    current_month_expense: Decimal
    personal_bank_expense: Decimal
    room_shares_owed: Decimal
    you_owe: Decimal
    owe_room_count: int
    you_are_owed: Decimal
    owed_room_count: int
    active_rooms_summary: list[ActiveRoomSummary]
