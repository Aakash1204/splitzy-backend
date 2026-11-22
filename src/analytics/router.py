from typing import Annotated, Literal
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.schemas import (
    BankTransactionResponse,
    CategoryBreakdownResponse,
    CategoryOverrideRequest,
    CashflowResponse,
    TopMerchantsResponse,
    TrendsResponse,
)
from src.analytics.service import AnalyticsService
from src.core.database import get_db
from src.core.security import get_current_user
from src.users.models import User

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])
transactions_router = APIRouter(prefix="/transactions", tags=["Transactions"])


@analytics_router.get(
    "/category-breakdown",
    response_model=CategoryBreakdownResponse,
    status_code=status.HTTP_200_OK,
    summary="Category spending breakdown",
    description="Returns total debit spend and breakdown by category with amounts and percentages for pie charts.",
)
async def get_category_breakdown(
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    return await AnalyticsService.get_category_breakdown(
        db=db,
        user_id=current_user.id,
        month_str=month,
    )


@analytics_router.get(
    "/trends",
    response_model=TrendsResponse,
    status_code=status.HTTP_200_OK,
    summary="Month-over-month trend lines",
    description="Returns monthly spending and income trend lines for the last 3, 6, or 12 months.",
)
async def get_trends(
    months: int = Query(default=6, description="Number of months to analyze: 3, 6, or 12"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    return await AnalyticsService.get_trends(
        db=db,
        user_id=current_user.id,
        months=months,
    )


@analytics_router.get(
    "/cashflow",
    response_model=CashflowResponse,
    status_code=status.HTTP_200_OK,
    summary="Monthly cashflow analysis",
    description="Returns total inflows, total outflows, net savings, and net savings rate percentage.",
)
async def get_cashflow(
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    return await AnalyticsService.get_cashflow(
        db=db,
        user_id=current_user.id,
        month_str=month,
    )


@analytics_router.get(
    "/top-merchants",
    response_model=TopMerchantsResponse,
    status_code=status.HTTP_200_OK,
    summary="Top 5 merchants",
    description="Returns top 5 merchants ranked by total spend or visit frequency.",
)
async def get_top_merchants(
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    sort_by: Literal["spend", "visits"] = Query(default="spend", description="Rank by 'spend' or 'visits'"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: AsyncSession = Depends(get_db),
):
    return await AnalyticsService.get_top_merchants(
        db=db,
        user_id=current_user.id,
        month_str=month,
        sort_by=sort_by,
    )


@analytics_router.get(
    "/anomalies",
    response_model=list[BankTransactionResponse],
    status_code=status.HTTP_200_OK,
    summary="List active anomaly alerts",
    description="Returns active, un-dismissed transaction anomaly alerts (double charges, large transactions, category spikes).",
)
async def list_anomalies(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await AnalyticsService.list_active_anomalies(
        db=db,
        user_id=current_user.id,
    )


@analytics_router.patch(
    "/anomalies/{tx_id}/dismiss",
    response_model=BankTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Dismiss an anomaly alert",
    description="Marks a flagged transaction anomaly as reviewed and dismissed.",
)
async def dismiss_anomaly(
    tx_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await AnalyticsService.dismiss_anomaly(
        db=db,
        user_id=current_user.id,
        tx_id=tx_id,
    )


@transactions_router.patch(
    "/{tx_id}/category",
    response_model=BankTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Override transaction category",
    description="Allows manual category override by the transaction owner.",
)
async def override_category(
    tx_id: uuid.UUID,
    body: CategoryOverrideRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await AnalyticsService.override_category(
        db=db,
        user_id=current_user.id,
        tx_id=tx_id,
        new_category=body.category,
    )
