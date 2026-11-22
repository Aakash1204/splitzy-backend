from datetime import datetime, timezone
import uuid
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.core.types import Money


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Enforce strict financial precision: NUMERIC(12, 2) mapped to Decimal
    total_amount: Mapped[Money]
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    splits: Mapped[list["ExpenseSplit"]] = relationship(
        "ExpenseSplit", back_populates="expense", cascade="all, delete-orphan"
    )


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Enforce strict financial precision: NUMERIC(12, 2) mapped to Decimal
    split_amount: Mapped[Money]
    is_settled: Mapped[bool] = mapped_column(default=False, nullable=False)

    expense: Mapped["Expense"] = relationship("Expense", back_populates="splits")
