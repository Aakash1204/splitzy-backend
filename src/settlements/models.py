from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.rooms.models import Room
    from src.users.models import User


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2, asdecimal=True),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    room: Mapped["Room"] = relationship("Room", foreign_keys=[room_id])
    payer: Mapped["User"] = relationship("User", foreign_keys=[payer_id])
    payee: Mapped["User"] = relationship("User", foreign_keys=[payee_id])
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlements_amount_positive"),
        CheckConstraint("payer_id != payee_id", name="ck_settlements_payer_ne_payee"),
        Index("idx_settlements_room_settled", "room_id", text("settled_at DESC")),
    )
