from datetime import date, datetime
from decimal import Decimal
import enum
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.statements.models import BankStatement
    from src.users.models import User


class TransactionType(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class TransactionCategory(str, enum.Enum):
    FOOD = "FOOD"
    TRAVEL = "TRAVEL"
    UTILITIES = "UTILITIES"
    SHOPPING = "SHOPPING"
    GROCERIES = "GROCERIES"
    SUBSCRIPTIONS = "SUBSCRIPTIONS"
    RENT = "RENT"
    SALARY = "SALARY"
    OTHER = "OTHER"


class AnomalyType(str, enum.Enum):
    DOUBLE_CHARGE = "DOUBLE_CHARGE"
    LARGE_TRANSACTION = "LARGE_TRANSACTION"
    CATEGORY_SPIKE = "CATEGORY_SPIKE"


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_statements.id", ondelete="SET NULL"),
        nullable=True,
    )
    tx_date: Mapped[date] = mapped_column(Date, nullable=False)
    merchant_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_normalized: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2, asdecimal=True),
        nullable=False,
    )
    tx_type: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    anomaly_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    anomaly_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_anomaly_dismissed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    statement: Mapped["BankStatement"] = relationship("BankStatement", foreign_keys=[statement_id])

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_bank_transactions_amount_positive"),
        UniqueConstraint("user_id", "dedup_hash", name="uq_bank_transactions_user_dedup"),
        Index("idx_bank_tx_user_date_type", "user_id", text("tx_date DESC"), "tx_type"),
        Index("idx_bank_tx_user_merchant", "user_id", "merchant_normalized"),
        Index("idx_bank_tx_user_category", "user_id", "category"),
        Index(
            "idx_bank_tx_active_anomalies",
            "user_id",
            postgresql_where=text("is_anomaly = TRUE AND is_anomaly_dismissed = FALSE"),
        ),
    )
