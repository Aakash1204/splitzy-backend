from datetime import date, datetime
import uuid
from pydantic import BaseModel, ConfigDict
from src.statements.models import BankStatement, ProcessingStatus, StatementFileType


class BankStatementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    file_type: str
    pii_redacted: bool
    processing_status: str
    period_start: date | None
    period_end: date | None
    transaction_count: int
    uploaded_at: datetime

    @classmethod
    def from_model(cls, statement: BankStatement) -> "BankStatementResponse":
        return cls(
            id=statement.id,
            user_id=statement.user_id,
            original_filename=statement.original_filename,
            file_type=statement.file_type,
            pii_redacted=statement.pii_redacted,
            processing_status=statement.processing_status,
            period_start=statement.period_start,
            period_end=statement.period_end,
            transaction_count=statement.transaction_count,
            uploaded_at=statement.uploaded_at,
        )


class StatementUploadResponse(BaseModel):
    statement: BankStatementResponse
    redacted_preview: str | None = None
