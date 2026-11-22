from datetime import datetime
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field
from src.ai_chat.models import AIChatMessage


class ChatQueryRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User financial query or question")


class AIChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    content: str
    structured_payload: dict[str, Any] | None = None
    created_at: datetime

    @classmethod
    def from_model(cls, msg: AIChatMessage) -> "AIChatMessageResponse":
        return cls(
            id=msg.id,
            user_id=msg.user_id,
            role=msg.role,
            content=msg.content,
            structured_payload=msg.structured_payload,
            created_at=msg.created_at,
        )
