from datetime import datetime, timezone
import uuid
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.rooms.models import Room, RoomMember
from src.rooms.service import RoomService
from src.settlements.models import Settlement
from src.settlements.schemas import SettlementCreateRequest, SettlementResponse
from src.users.models import User


class SettlementService:
    @staticmethod
    async def create_settlement(
        db: AsyncSession,
        room: Room,
        current_user: User,
        payload: SettlementCreateRequest,
    ) -> SettlementResponse:
        # 1. Reject if room is ARCHIVED
        RoomService.assert_room_active(room)

        # 2. Reject if payer_id == payee_id
        if payload.payer_id == payload.payee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payer and payee cannot be the same user",
            )

        # 3. Verify both payer and payee are members of the room
        stmt = select(RoomMember.user_id).where(
            RoomMember.room_id == room.id,
            RoomMember.user_id.in_([payload.payer_id, payload.payee_id]),
        )
        res = await db.execute(stmt)
        found_member_ids = set(res.scalars().all())

        if payload.payer_id not in found_member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payer ({payload.payer_id}) is not a member of this room",
            )
        if payload.payee_id not in found_member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payee ({payload.payee_id}) is not a member of this room",
            )

        # 4. Insert settlement without modifying or deleting split_expenses
        new_settlement = Settlement(
            room_id=room.id,
            payer_id=payload.payer_id,
            payee_id=payload.payee_id,
            amount=payload.amount,
            created_by=current_user.id,
            settled_at=payload.settled_at or datetime.now(timezone.utc),
        )
        db.add(new_settlement)
        await db.commit()

        # 5. Reload with relationships for response
        return await SettlementService.get_settlement_response(db, new_settlement.id)

    @staticmethod
    async def get_settlement_response(
        db: AsyncSession,
        settlement_id: uuid.UUID,
    ) -> SettlementResponse:
        stmt = (
            select(Settlement)
            .options(
                selectinload(Settlement.payer),
                selectinload(Settlement.payee),
                selectinload(Settlement.creator),
            )
            .where(Settlement.id == settlement_id)
        )
        res = await db.execute(stmt)
        settlement = res.scalar_one_or_none()
        if not settlement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Settlement not found",
            )
        return SettlementResponse.from_model(settlement)

    @staticmethod
    async def list_room_settlements(
        db: AsyncSession,
        room_id: uuid.UUID,
    ) -> list[SettlementResponse]:
        stmt = (
            select(Settlement)
            .options(
                selectinload(Settlement.payer),
                selectinload(Settlement.payee),
                selectinload(Settlement.creator),
            )
            .where(Settlement.room_id == room_id)
            .order_by(Settlement.settled_at.desc(), Settlement.id.desc())
        )
        res = await db.execute(stmt)
        settlements = res.scalars().all()
        return [SettlementResponse.from_model(s) for s in settlements]
