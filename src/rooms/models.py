import enum
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class RoomCategory(str, enum.Enum):
    TRIP = "TRIP"
    HOME = "HOME"
    DINING = "DINING"
    EVENT = "EVENT"
    OFFICE = "OFFICE"
    OTHER = "OTHER"


class RoomStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=RoomCategory.OTHER.value,
        server_default=text("'OTHER'"),
    )
    icon: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RoomStatus.ACTIVE.value,
        server_default=text("'ACTIVE'"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    members: Mapped[list["RoomMember"]] = relationship(
        "RoomMember",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="RoomMember.joined_at.asc()",
    )


class RoomMember(Base):
    __tablename__ = "room_members"

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    room: Mapped["Room"] = relationship("Room", back_populates="members")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
