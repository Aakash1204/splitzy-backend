from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_chat.schemas import AIChatMessageResponse, ChatQueryRequest
from src.ai_chat.service import AIChatService
from src.core.database import get_db
from src.core.security import get_current_user
from src.users.models import User

ai_router = APIRouter(prefix="/ai", tags=["AI Financial Assistant"])


@ai_router.post(
    "/query",
    response_model=AIChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ask financial question to Splitzy AI",
    description="Accurate tool-calling engine: evaluates deterministic read-only SQL queries scoped to current user and returns answer + UI structured payload.",
)
async def query_ai(
    body: ChatQueryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await AIChatService.process_user_query(
        db=db,
        current_user=current_user,
        payload=body,
    )


@ai_router.get(
    "/history",
    response_model=list[AIChatMessageResponse],
    status_code=status.HTTP_200_OK,
    summary="Get chat message history",
    description="Returns chronological chat history for the authenticated user.",
)
async def get_history(
    limit: int = Query(default=50, ge=1, le=200, description="Max messages to return"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    return await AIChatService.get_chat_history(
        db=db,
        user_id=current_user.id,
        limit=limit,
    )
