from datetime import datetime, timezone
from decimal import Decimal
import uuid
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.rooms.models import Room, RoomMember, RoomStatus
from src.rooms.schemas import RoomCreateRequest, RoomMemberDetailResponse
from src.users.models import User


class RoomService:
    @staticmethod
    async def create_room(
        db: AsyncSession,
        creator: User,
        payload: RoomCreateRequest,
    ) -> Room:
        """
        Creates a room and atomically inserts the creator and all provided member_ids
        into room_members within the same transaction. Supports any number of users.
        """
        new_room = Room(
            name=payload.name.strip(),
            category=payload.category.value if hasattr(payload.category, "value") else str(payload.category),
            icon=payload.icon.strip(),
            status=RoomStatus.ACTIVE.value,
            created_by=creator.id,
        )
        db.add(new_room)
        await db.flush()

        # Atomically add creator
        creator_member = RoomMember(
            room_id=new_room.id,
            user_id=creator.id,
        )
        db.add(creator_member)

        # Atomically add provided member_ids with no artificial cap
        if payload.member_ids:
            distinct_member_ids = {mid for mid in payload.member_ids if mid != creator.id}
            if distinct_member_ids:
                stmt = select(User.id).where(User.id.in_(distinct_member_ids))
                res = await db.execute(stmt)
                existing_ids = set(res.scalars().all())

                missing_ids = distinct_member_ids - existing_ids
                if missing_ids:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cannot add member(s): user ID(s) do not exist: {list(missing_ids)}",
                    )

                for mid in distinct_member_ids:
                    db.add(RoomMember(room_id=new_room.id, user_id=mid))

        await db.commit()
        await db.refresh(new_room)
        return new_room

    @staticmethod
    async def list_user_rooms(
        db: AsyncSession,
        user_id: uuid.UUID,
        status_filter: RoomStatus | None = None,
    ) -> list[Room]:
        stmt = (
            select(Room)
            .join(RoomMember, Room.id == RoomMember.room_id)
            .where(RoomMember.user_id == user_id)
        )
        if status_filter:
            status_val = status_filter.value if hasattr(status_filter, "value") else str(status_filter)
            stmt = stmt.where(Room.status == status_val)

        stmt = stmt.order_by(Room.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_room_and_verify_member(
        db: AsyncSession,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Room:
        stmt = select(Room).where(Room.id == room_id)
        res = await db.execute(stmt)
        room = res.scalar_one_or_none()

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Room not found",
            )

        member_stmt = select(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user_id,
        )
        member_res = await db.execute(member_stmt)
        if not member_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not a member of this room",
            )

        return room

    @staticmethod
    async def get_room_details(
        db: AsyncSession,
        room_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> dict:
        room = await RoomService.get_room_and_verify_member(db, room_id, current_user_id)
        creator = await db.get(User, room.created_by)
        members = await RoomService.list_room_members(db, room_id)

        return {
            "id": room.id,
            "name": room.name,
            "category": room.category,
            "icon": room.icon,
            "status": room.status,
            "created_by": room.created_by,
            "archived_at": room.archived_at,
            "created_at": room.created_at,
            "creator": creator,
            "members": members,
        }

    @staticmethod
    async def list_room_members(
        db: AsyncSession,
        room_id: uuid.UUID,
    ) -> list[RoomMemberDetailResponse]:
        """Lists all members (id, full_name, username, joined_at) in the room."""
        stmt = (
            select(User.id, User.full_name, User.username, RoomMember.joined_at)
            .join(RoomMember, User.id == RoomMember.user_id)
            .where(RoomMember.room_id == room_id)
            .order_by(RoomMember.joined_at.asc())
        )
        res = await db.execute(stmt)
        return [
            RoomMemberDetailResponse(
                id=row.id,
                full_name=row.full_name,
                username=row.username,
                joined_at=row.joined_at,
            )
            for row in res.all()
        ]

    @staticmethod
    async def add_room_members(
        db: AsyncSession,
        room: Room,
        user_ids: list[uuid.UUID],
    ) -> list[RoomMemberDetailResponse]:
        """Adds one or more user_ids to an ACTIVE room. Rejects if room is ARCHIVED."""
        RoomService.assert_room_active(room)

        distinct_ids = set(user_ids)
        if not distinct_ids:
            return await RoomService.list_room_members(db, room.id)

        # Validate that all requested users exist
        stmt = select(User.id).where(User.id.in_(distinct_ids))
        res = await db.execute(stmt)
        existing_user_ids = set(res.scalars().all())

        missing = distinct_ids - existing_user_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add member(s): user ID(s) do not exist: {list(missing)}",
            )

        # Check existing members to ignore duplicates cleanly
        existing_members_stmt = select(RoomMember.user_id).where(
            RoomMember.room_id == room.id,
            RoomMember.user_id.in_(distinct_ids),
        )
        existing_members_res = await db.execute(existing_members_stmt)
        already_members = set(existing_members_res.scalars().all())

        to_add = distinct_ids - already_members
        for uid in to_add:
            db.add(RoomMember(room_id=room.id, user_id=uid))

        await db.commit()
        return await RoomService.list_room_members(db, room.id)

    @staticmethod
    async def verify_member_balance_zero(
        db: AsyncSession,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """
        Verifies that the specified member's net balance in the room is 0.00.
        Raises 400 Bad Request if balance != 0.00.
        """
        from src.expenses.service import ExpenseService

        balances_res = await ExpenseService.get_room_balances(db, room_id)
        for b in balances_res.balances:
            if b.user.id == user_id and b.net_balance != Decimal("0.00"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot remove member: member has an unsettled balance of {b.net_balance}",
                )

    @staticmethod
    async def remove_room_member(
        db: AsyncSession,
        room: Room,
        target_user_id: uuid.UUID,
    ) -> dict:
        """Removes a member from an ACTIVE room only if their net balance is 0.00."""
        RoomService.assert_room_active(room)

        # Check if target is a member of the room
        stmt = select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.user_id == target_user_id,
        )
        res = await db.execute(stmt)
        member = res.scalar_one_or_none()

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not a member of this room",
            )

        # Verify net balance is 0.00 before removal
        await RoomService.verify_member_balance_zero(db, room.id, target_user_id)

        await db.delete(member)
        await db.commit()

        return {
            "message": "Member removed successfully",
            "room_id": str(room.id),
            "user_id": str(target_user_id),
        }

    @staticmethod
    async def verify_all_balances_zero(db: AsyncSession, room_id: uuid.UUID) -> None:
        """
        Service hook to verify that all member balances in the room are 0.00.
        Raises 400 Bad Request if any member's balance is not 0.00.
        """
        from src.expenses.service import ExpenseService

        balances_res = await ExpenseService.get_room_balances(db, room_id)
        unsettled = [b for b in balances_res.balances if b.net_balance != Decimal("0.00")]
        if unsettled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot archive room: all member balances must be 0.00 before archiving ({len(unsettled)} members have unsettled balances)",
            )

    @staticmethod
    def assert_room_active(room: Room) -> None:
        """Archived rooms must reject any future expense/member mutations."""
        if room.status == RoomStatus.ARCHIVED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot perform operation: this room is archived",
            )

    @staticmethod
    async def archive_room(
        db: AsyncSession,
        room_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> Room:
        room = await RoomService.get_room_and_verify_member(db, room_id, current_user_id)

        if room.status == RoomStatus.ARCHIVED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Room is already archived",
            )

        await RoomService.verify_all_balances_zero(db, room_id)

        room.status = RoomStatus.ARCHIVED.value
        room.archived_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(room)
        return room
