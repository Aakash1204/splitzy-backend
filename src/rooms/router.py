from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.rooms.dependencies import verify_room_member
from src.rooms.models import Room, RoomStatus
from src.rooms.schemas import (
    AddRoomMembersRequest,
    RemoveMemberResponse,
    RoomCreateRequest,
    RoomDetailResponse,
    RoomMemberDetailResponse,
    RoomResponse,
)
from src.rooms.service import RoomService
from src.users.models import User

rooms_router = APIRouter(prefix="/rooms", tags=["Rooms"])


@rooms_router.post(
    "",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new room",
    description="Creates a room and atomically inserts the creator and all initial member_ids into room_members.",
)
async def create_room(
    body: RoomCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    room = await RoomService.create_room(db=db, creator=current_user, payload=body)
    return room


@rooms_router.get(
    "",
    response_model=list[RoomResponse],
    status_code=status.HTTP_200_OK,
    summary="List user's rooms",
    description="Lists all rooms where the current user is a member, filterable by status.",
)
async def list_rooms(
    current_user: Annotated[User, Depends(get_current_user)],
    room_status: Annotated[RoomStatus | None, Query(alias="status")] = None,
    db: AsyncSession = Depends(get_db),
):
    rooms = await RoomService.list_user_rooms(db=db, user_id=current_user.id, status_filter=room_status)
    return rooms


@rooms_router.get(
    "/{room_id}",
    response_model=RoomDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get room details",
    description="Returns room details if the current user is a member, otherwise returns 403 Forbidden.",
)
async def get_room(
    room_id: uuid.UUID,
    room: Annotated[Room, Depends(verify_room_member)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    details = await RoomService.get_room_details(db=db, room_id=room_id, current_user_id=current_user.id)
    return details


@rooms_router.patch(
    "/{room_id}/archive",
    response_model=RoomResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive room",
    description="Archives an active room once all balances are zero. Archived rooms reject future mutations.",
)
async def archive_room(
    room_id: uuid.UUID,
    room: Annotated[Room, Depends(verify_room_member)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    archived_room = await RoomService.archive_room(db=db, room_id=room_id, current_user_id=current_user.id)
    return archived_room


# ==========================================
# Room Members Management Endpoints
# ==========================================

@rooms_router.get(
    "/{room_id}/members",
    response_model=list[RoomMemberDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="List room members",
    description="Lists all members (id, full_name, username, joined_at) in the room. Requires room membership.",
)
async def list_members(
    room_id: uuid.UUID,
    room: Annotated[Room, Depends(verify_room_member)],
    db: AsyncSession = Depends(get_db),
):
    return await RoomService.list_room_members(db=db, room_id=room_id)


@rooms_router.post(
    "/{room_id}/members",
    response_model=list[RoomMemberDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Add members to room",
    description="Adds one or more user_ids to an ACTIVE room. Rejects if room is ARCHIVED. Cleanly handles already-present members.",
)
async def add_members(
    room_id: uuid.UUID,
    body: AddRoomMembersRequest,
    room: Annotated[Room, Depends(verify_room_member)],
    db: AsyncSession = Depends(get_db),
):
    return await RoomService.add_room_members(db=db, room=room, user_ids=body.user_ids)


@rooms_router.delete(
    "/{room_id}/members/{user_id}",
    response_model=RemoveMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove member from room",
    description="Removes a member from an ACTIVE room only if their net balance in the room is 0.00.",
)
async def remove_member(
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    room: Annotated[Room, Depends(verify_room_member)],
    db: AsyncSession = Depends(get_db),
):
    return await RoomService.remove_room_member(db=db, room=room, target_user_id=user_id)
