from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.expenses.schemas import (
    DeleteExpenseResponse,
    RoomBalancesResponse,
    SplitExpenseCreateRequest,
    SplitExpenseResponse,
    SplitExpenseUpdateRequest,
)
from src.expenses.service import ExpenseService
from src.rooms.dependencies import verify_room_member
from src.rooms.models import Room
from src.users.models import User

# Router for room-nested expense endpoints: /rooms/{room_id}/expenses
room_expenses_router = APIRouter(prefix="/rooms", tags=["Expenses"])

# Router for direct expense operations: /expenses/{expense_id}
expenses_router = APIRouter(prefix="/expenses", tags=["Expenses"])


@room_expenses_router.post(
    "/{room_id}/expenses",
    response_model=SplitExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an expense to a room",
    description="Adds an expense to an ACTIVE room. Rejects if room is ARCHIVED. Verifies paid_by is a room member. Sets created_by to current user.",
)
async def create_expense(
    room_id: uuid.UUID,
    body: SplitExpenseCreateRequest,
    room: Annotated[Room, Depends(verify_room_member)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await ExpenseService.create_expense(
        db=db,
        room=room,
        current_user=current_user,
        payload=body,
    )


@room_expenses_router.get(
    "/{room_id}/expenses",
    response_model=list[SplitExpenseResponse],
    status_code=status.HTTP_200_OK,
    summary="Get chronological feed of room expenses",
    description="Returns chronological feed of room expenses with dynamically computed can_edit and can_delete flags for requesting user.",
)
async def get_room_expenses(
    room_id: uuid.UUID,
    room: Annotated[Room, Depends(verify_room_member)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await ExpenseService.get_room_expenses(
        db=db,
        room_id=room_id,
        current_user_id=current_user.id,
    )


@room_expenses_router.get(
    "/{room_id}/balances",
    response_model=RoomBalancesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get room member balances and pairwise debts",
    description="Calculates each member's net balance (total_paid - total_owed) and simplified pairwise debts using SQL aggregation.",
)
async def get_room_balances(
    room_id: uuid.UUID,
    room: Annotated[Room, Depends(verify_room_member)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await ExpenseService.get_room_balances(
        db=db,
        room_id=room_id,
    )


@expenses_router.patch(
    "/{expense_id}",
    response_model=SplitExpenseResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an expense",
    description="Creator-only edit. Rejects with 403 if requester != created_by, or 400 if room is ARCHIVED.",
)
async def update_expense(
    expense_id: uuid.UUID,
    body: SplitExpenseUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await ExpenseService.update_expense(
        db=db,
        expense_id=expense_id,
        current_user=current_user,
        payload=body,
    )


@expenses_router.delete(
    "/{expense_id}",
    response_model=DeleteExpenseResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete an expense",
    description="Creator-only delete. Rejects with 403 if requester != created_by, or 400 if room is ARCHIVED.",
)
async def delete_expense(
    expense_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    return await ExpenseService.delete_expense(
        db=db,
        expense_id=expense_id,
        current_user=current_user,
    )
