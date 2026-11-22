from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.statements.schemas import BankStatementResponse, StatementUploadResponse
from src.statements.service import StatementService
from src.users.models import User

# Router for bank statements: /statements
statements_router = APIRouter(prefix="/statements", tags=["Bank Statements"])


@statements_router.post(
    "/upload",
    response_model=StatementUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a bank statement",
    description="Privacy-first ingestion: runs CPU-offloaded extraction and deterministic pre-LLM PII scrubbing in ephemeral storage.",
)
async def upload_statement(
    file: UploadFile = File(..., description="Bank statement file (PDF, PNG, JPG)"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    return await StatementService.process_and_create_statement(
        db=db,
        current_user=current_user,
        file=file,
    )


@statements_router.get(
    "",
    response_model=list[BankStatementResponse],
    status_code=status.HTTP_200_OK,
    summary="List uploaded bank statements",
    description="Lists the authenticated user's uploaded statement history.",
)
async def list_statements(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await StatementService.list_user_statements(
        db=db,
        user_id=current_user.id,
    )


@statements_router.get(
    "/{statement_id}",
    response_model=BankStatementResponse,
    status_code=status.HTTP_200_OK,
    summary="Get statement details",
    description="Returns details for a specific statement owned by the current user.",
)
async def get_statement(
    statement_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await StatementService.get_statement_by_id(
        db=db,
        statement_id=statement_id,
        user_id=current_user.id,
    )
