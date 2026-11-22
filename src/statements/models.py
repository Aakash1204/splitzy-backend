from datetime import date, datetime
import enum
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.users.models import User


class StatementFileType(str, enum.Enum):
    PDF = "PDF"
    IMAGE = "IMAGE"


class ProcessingStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BankStatement(Base):
    __tablename__ = "bank_statements"

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
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    pii_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    processing_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ProcessingStatus.PROCESSING.value,
        server_default=text("'PROCESSING'"),
    )
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_bank_statements_user_uploaded", "user_id", text("uploaded_at DESC")),
    )
