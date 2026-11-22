from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.rooms.dependencies import verify_room_member
from src.rooms.models import Room
from src.settlements.schemas import SettlementCreateRequest, SettlementResponse
from src.settlements.service import SettlementService
from src.users.models import User

# Router for room-nested settlements: /rooms/{room_id}/settlements
settlements_router = APIRouter(prefix="/rooms", tags=["Settlements"])


@settlements_router.post(
    "/{room_id}/settlements",
    response_model=SettlementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a settlement payment",
    description="Records a payment (payer_id, payee_id, amount) in an ACTIVE room without modifying or deleting any split_expenses rows.",
)
async def create_settlement(
    room_id: uuid.UUID,
    body: SettlementCreateRequest,
    room: Annotated[Room, Depends(verify_room_member)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await SettlementService.create_settlement(
        db=db,
        room=room,
        current_user=current_user,
        payload=body,
    )


@settlements_router.get(
    "/{room_id}/settlements",
    response_model=list[SettlementResponse],
    status_code=status.HTTP_200_OK,
    summary="List chronological room settlements",
    description="Lists all settlement records chronologically so the Room page can display them alongside expenses.",
)
async def list_room_settlements(
    room_id: uuid.UUID,
    room: Annotated[Room, Depends(verify_room_member)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await SettlementService.list_room_settlements(
        db=db,
        room_id=room_id,
    )
