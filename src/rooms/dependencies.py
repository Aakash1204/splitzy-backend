from typing import Annotated
import uuid
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.rooms.models import Room
from src.rooms.service import RoomService
from src.users.models import User


async def verify_room_member(
    room_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> Room:
    """
    Reusable FastAPI dependency that verifies the room exists and the current_user is a member.
    Raises 404 Not Found if room does not exist.
    Raises 403 Forbidden if the user is not in room_members.
    Returns the verified Room object.
    """
    return await RoomService.get_room_and_verify_member(
        db=db,
        room_id=room_id,
        user_id=current_user.id,
    )
