import os
import uuid
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.anomaly_detector import AnomalyDetector
from src.analytics.models import BankTransaction
from src.analytics.parser import StatementParser
from src.statements.models import BankStatement, ProcessingStatus, StatementFileType
from src.statements.pii_redactor import PIIRedactor
from src.statements.schemas import BankStatementResponse, StatementUploadResponse
from src.users.models import User

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


class StatementService:
    @staticmethod
    def detect_file_type(filename: str, content_type: str | None) -> StatementFileType:
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf" or (content_type and "pdf" in content_type):
            return StatementFileType.PDF
        elif ext in [".png", ".jpg", ".jpeg"] or (
            content_type and any(img in content_type for img in ["image/png", "image/jpeg", "image/jpg"])
        ):
            return StatementFileType.IMAGE
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Please upload a PDF, PNG, or JPG bank statement.",
            )

    @classmethod
    async def process_and_create_statement(
        cls,
        db: AsyncSession,
        current_user: User,
        file: UploadFile,
    ) -> StatementUploadResponse:
        filename = os.path.basename(file.filename or "statement.pdf")
        file_type = cls.detect_file_type(filename, file.content_type)

        # Read file bytes in memory
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB.",
            )

        # Ephemeral extraction + deterministic PII redaction
        parsed_txs = []
        try:
            redacted_text, metadata = await PIIRedactor.process_ephemeral(
                file_bytes=file_bytes,
                file_type=file_type,
                filename=filename,
            )
            # Parse structured transactions from the redacted text
            parsed_txs = StatementParser.parse_statement_text(redacted_text, current_user.id)
            status_val = ProcessingStatus.COMPLETED.value
        except Exception:
            redacted_text = ""
            metadata = {"period_start": None, "period_end": None, "transaction_count": 0}
            status_val = ProcessingStatus.FAILED.value

        tx_count = len(parsed_txs) if parsed_txs else metadata.get("transaction_count", 0)
        p_start = min((t.tx_date for t in parsed_txs), default=None) or metadata.get("period_start")
        p_end = max((t.tx_date for t in parsed_txs), default=None) or metadata.get("period_end")

        statement = BankStatement(
            user_id=current_user.id,
            original_filename=filename,
            file_type=file_type.value,
            pii_redacted=True,
            processing_status=status_val,
            period_start=p_start,
            period_end=p_end,
            transaction_count=tx_count,
        )
        db.add(statement)
        await db.flush()

        # Insert transactions with upsert ON CONFLICT DO NOTHING for safe re-uploads
        if parsed_txs:
            tx_dicts = [
                {
                    "user_id": current_user.id,
                    "statement_id": statement.id,
                    "tx_date": pt.tx_date,
                    "merchant_raw": pt.merchant_raw,
                    "merchant_normalized": pt.merchant_normalized,
                    "amount": pt.amount,
                    "tx_type": pt.tx_type,
                    "category": pt.category,
                    "dedup_hash": pt.dedup_hash,
                }
                for pt in parsed_txs
            ]
            insert_stmt = (
                pg_insert(BankTransaction)
                .values(tx_dicts)
                .on_conflict_do_nothing(index_elements=["user_id", "dedup_hash"])
            )
            await db.execute(insert_stmt)
            await db.commit()

            # Run automated anomaly detection after insert
            await AnomalyDetector.run_detection_for_user(db, current_user.id)
        else:
            await db.commit()

        await db.refresh(statement)

        preview = (redacted_text[:300] + "...") if len(redacted_text) > 300 else redacted_text
        return StatementUploadResponse(
            statement=BankStatementResponse.from_model(statement),
            redacted_preview=preview if preview else None,
        )

    @staticmethod
    async def list_user_statements(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[BankStatementResponse]:
        stmt = (
            select(BankStatement)
            .where(BankStatement.user_id == user_id)
            .order_by(BankStatement.uploaded_at.desc())
        )
        res = await db.execute(stmt)
        statements = res.scalars().all()
        return [BankStatementResponse.from_model(s) for s in statements]

    @staticmethod
    async def get_statement_by_id(
        db: AsyncSession,
        statement_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BankStatementResponse:
        stmt = select(BankStatement).where(BankStatement.id == statement_id)
        res = await db.execute(stmt)
        statement = res.scalar_one_or_none()

        if not statement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bank statement not found",
            )

        if statement.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have access to this bank statement",
            )

        return BankStatementResponse.from_model(statement)
