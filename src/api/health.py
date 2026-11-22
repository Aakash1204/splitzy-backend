from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    timestamp: datetime
    database: str


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description="Returns the service health status along with database connectivity state.",
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint checking application and async PostgreSQL database connectivity."""
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"disconnected: {e.__class__.__name__}"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        app=settings.APP_NAME,
        environment=settings.APP_ENV,
        timestamp=datetime.now(timezone.utc),
        database=db_status,
    )
