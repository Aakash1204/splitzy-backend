from datetime import date, datetime
from decimal import Decimal
import enum
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.rooms.models import Room
    from src.users.models import User


class SplitType(str, enum.Enum):
    EQUAL = "EQUAL"
    EXACT = "EXACT"
    PERCENTAGE = "PERCENTAGE"
    SHARES = "SHARES"


class SplitExpense(Base):
    __tablename__ = "split_expenses"

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
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2, asdecimal=True),
        nullable=False,
    )
    paid_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    split_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SplitType.EQUAL.value,
        server_default=text("'EQUAL'"),
    )
    expense_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        server_default=func.current_date(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    room: Mapped["Room"] = relationship("Room", foreign_keys=[room_id])
    payer: Mapped["User"] = relationship("User", foreign_keys=[paid_by])
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    shares: Mapped[list["ExpenseShare"]] = relationship(
        "ExpenseShare",
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseShare.owed_amount.desc()",
    )

    __table_args__ = (
        CheckConstraint("total_amount > 0", name="ck_split_expenses_total_amount_positive"),
        Index("idx_expenses_room_date", "room_id", text("expense_date DESC")),
    )


class ExpenseShare(Base):
    __tablename__ = "expense_shares"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("split_expenses.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owed_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2, asdecimal=True),
        nullable=False,
    )
    share_input: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4, asdecimal=True),
        nullable=True,
    )

    expense: Mapped["SplitExpense"] = relationship("SplitExpense", back_populates="shares")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint("owed_amount >= 0", name="ck_expense_shares_owed_amount_non_negative"),
        UniqueConstraint("expense_id", "user_id", name="uq_expense_shares_expense_user"),
        Index("idx_shares_user", "user_id", "expense_id"),
    )
