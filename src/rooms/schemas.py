from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field
from src.rooms.models import RoomCategory, RoomStatus
from src.users.schemas import UserProfileResponse


class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Room name")
    category: RoomCategory = Field(default=RoomCategory.OTHER, description="Room category")
    icon: str = Field(
        default="sparkles",
        min_length=1,
        max_length=50,
        description="Vector icon key (e.g. plane, home, utensils, ticket, briefcase, sparkles)",
    )
    member_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Optional initial user UUIDs to add to the room",
    )


class AddRoomMembersRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="List of user UUIDs to add to the room",
    )


class RoomMemberDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    username: str
    joined_at: datetime


class RoomMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    room_id: uuid.UUID
    user_id: uuid.UUID
    joined_at: datetime
    user: UserProfileResponse | None = None


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    icon: str
    status: str
    created_by: uuid.UUID
    archived_at: datetime | None = None
    created_at: datetime


class RoomDetailResponse(RoomResponse):
    creator: UserProfileResponse | None = None
    members: list[RoomMemberDetailResponse] = []


class RemoveMemberResponse(BaseModel):
    message: str = Field(..., description="Status message")
    room_id: str = Field(..., description="UUID of the room")
    user_id: str = Field(..., description="UUID of the removed member")

