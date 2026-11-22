from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.dashboard.schemas import DashboardSummaryResponse
from src.dashboard.service import DashboardService
from src.users.models import User

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@dashboard_router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Unified Financial Dashboard Summary",
    description="Fast aggregated view (<500ms) across personal bank debits, room shares, net balances, and active rooms.",
)
async def get_dashboard_summary(
    month: str | None = Query(default=None, description="Month in YYYY-MM format (defaults to current calendar month)"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    return await DashboardService.get_summary(
        db=db,
        current_user=current_user,
        month_str=month,
    )
