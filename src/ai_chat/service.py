import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_chat.models import AIChatMessage, ChatRole
from src.ai_chat.query_engine import QueryEngine
from src.ai_chat.schemas import AIChatMessageResponse, ChatQueryRequest
from src.users.models import User


class AIChatService:
    @staticmethod
    async def process_user_query(
        db: AsyncSession,
        current_user: User,
        payload: ChatQueryRequest,
    ) -> AIChatMessageResponse:
        # 1. Persist the USER message
        user_msg = AIChatMessage(
            user_id=current_user.id,
            role=ChatRole.USER.value,
            content=payload.message.strip(),
        )
        db.add(user_msg)
        await db.flush()

        # 2. Execute accurate tool-calling query engine
        content, structured_payload = await QueryEngine.query(
            db=db,
            user_id=current_user.id,
            message=payload.message.strip(),
        )

        # 3. Persist the ASSISTANT message with structured payload
        assistant_msg = AIChatMessage(
            user_id=current_user.id,
            role=ChatRole.ASSISTANT.value,
            content=content,
            structured_payload=structured_payload,
        )
        db.add(assistant_msg)
        await db.commit()
        await db.refresh(assistant_msg)

        return AIChatMessageResponse.from_model(assistant_msg)

    @staticmethod
    async def get_chat_history(
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[AIChatMessageResponse]:
        # Return chronological chat history
        stmt = (
            select(AIChatMessage)
            .where(AIChatMessage.user_id == user_id)
            .order_by(AIChatMessage.created_at.asc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        messages = res.scalars().all()
        return [AIChatMessageResponse.from_model(m) for m in messages]
