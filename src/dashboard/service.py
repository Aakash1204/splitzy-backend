from datetime import date
from decimal import Decimal
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.models import BankTransaction, TransactionType
from src.analytics.service import AnalyticsService
from src.dashboard.schemas import ActiveRoomSummary, DashboardSummaryResponse
from src.expenses.models import ExpenseShare, SplitExpense
from src.rooms.models import Room, RoomMember, RoomStatus
from src.settlements.models import Settlement
from src.users.models import User


class DashboardService:
    @classmethod
    async def get_summary(
        cls,
        db: AsyncSession,
        current_user: User,
        month_str: str | None = None,
    ) -> DashboardSummaryResponse:
        user_id = current_user.id
        formatted_month, start_date, end_date = AnalyticsService.parse_month_bounds(month_str)

        # 1 & 2. Personal Bank Debits and Room Shares Owed in Month (Single Query)
        bank_subq = (
            select(func.coalesce(func.sum(BankTransaction.amount), Decimal("0.00")))
            .where(
                BankTransaction.user_id == user_id,
                BankTransaction.tx_type == TransactionType.DEBIT.value,
                BankTransaction.tx_date >= start_date,
                BankTransaction.tx_date <= end_date,
            )
            .scalar_subquery()
        )

        shares_subq = (
            select(func.coalesce(func.sum(ExpenseShare.owed_amount), Decimal("0.00")))
            .select_from(ExpenseShare)
            .join(SplitExpense, SplitExpense.id == ExpenseShare.expense_id)
            .where(
                ExpenseShare.user_id == user_id,
                SplitExpense.expense_date >= start_date,
                SplitExpense.expense_date <= end_date,
            )
            .scalar_subquery()
        )

        monthly_totals_stmt = select(
            bank_subq.label("bank_expense"),
            shares_subq.label("shares_owed"),
        )
        monthly_res = await db.execute(monthly_totals_stmt)
        monthly_row = monthly_res.one()

        personal_bank_expense = Decimal(str(monthly_row.bank_expense or 0.00))
        room_shares_owed = Decimal(str(monthly_row.shares_owed or 0.00))
        current_month_expense = personal_bank_expense + room_shares_owed

        # 3. Active Rooms Summary & Net Balances via SQL Subqueries
        paid_subq = (
            select(func.coalesce(func.sum(SplitExpense.total_amount), Decimal("0.00")))
            .where(
                SplitExpense.room_id == Room.id,
                SplitExpense.paid_by == user_id,
            )
            .correlate(Room)
            .scalar_subquery()
        )

        owed_subq = (
            select(func.coalesce(func.sum(ExpenseShare.owed_amount), Decimal("0.00")))
            .select_from(ExpenseShare)
            .join(SplitExpense, SplitExpense.id == ExpenseShare.expense_id)
            .where(
                SplitExpense.room_id == Room.id,
                ExpenseShare.user_id == user_id,
            )
            .correlate(Room)
            .scalar_subquery()
        )

        settle_paid_subq = (
            select(func.coalesce(func.sum(Settlement.amount), Decimal("0.00")))
            .where(
                Settlement.room_id == Room.id,
                Settlement.payer_id == user_id,
            )
            .correlate(Room)
            .scalar_subquery()
        )

        settle_recv_subq = (
            select(func.coalesce(func.sum(Settlement.amount), Decimal("0.00")))
            .where(
                Settlement.room_id == Room.id,
                Settlement.payee_id == user_id,
            )
            .correlate(Room)
            .scalar_subquery()
        )

        member_count_subq = (
            select(func.count(RoomMember.user_id))
            .where(RoomMember.room_id == Room.id)
            .correlate(Room)
            .scalar_subquery()
        )

        latest_expense_subq = (
            select(func.max(SplitExpense.created_at))
            .where(SplitExpense.room_id == Room.id)
            .correlate(Room)
            .scalar_subquery()
        )

        latest_settlement_subq = (
            select(func.max(Settlement.settled_at))
            .where(Settlement.room_id == Room.id)
            .correlate(Room)
            .scalar_subquery()
        )

        last_activity_expr = func.coalesce(
            func.greatest(
                Room.created_at,
                func.coalesce(latest_expense_subq, Room.created_at),
                func.coalesce(latest_settlement_subq, Room.created_at),
            ),
            Room.created_at,
        )

        rooms_stmt = (
            select(
                Room.id,
                Room.name,
                Room.category,
                Room.icon,
                member_count_subq.label("member_count"),
                paid_subq.label("total_paid"),
                owed_subq.label("total_owed"),
                settle_paid_subq.label("settle_paid"),
                settle_recv_subq.label("settle_recv"),
                last_activity_expr.label("last_activity"),
            )
            .join(RoomMember, RoomMember.room_id == Room.id)
            .where(
                RoomMember.user_id == user_id,
                Room.status == RoomStatus.ACTIVE.value,
            )
            .order_by(last_activity_expr.desc())
        )

        rooms_res = await db.execute(rooms_stmt)
        rooms_rows = rooms_res.all()

        active_rooms: list[ActiveRoomSummary] = []
        you_owe = Decimal("0.00")
        owe_room_count = 0
        you_are_owed = Decimal("0.00")
        owed_room_count = 0

        for r in rooms_rows:
            tp = Decimal(str(r.total_paid))
            to = Decimal(str(r.total_owed))
            sp = Decimal(str(r.settle_paid))
            sr = Decimal(str(r.settle_recv))

            net_bal = tp - to + sp - sr

            if net_bal < Decimal("0.00"):
                you_owe += abs(net_bal)
                owe_room_count += 1
            elif net_bal > Decimal("0.00"):
                you_are_owed += net_bal
                owed_room_count += 1

            active_rooms.append(
                ActiveRoomSummary(
                    room_id=r.id,
                    name=r.name,
                    category=r.category,
                    icon=r.icon,
                    member_count=r.member_count,
                    user_net_balance=net_bal,
                )
            )

        return DashboardSummaryResponse(
            month=formatted_month,
            current_month_expense=current_month_expense,
            personal_bank_expense=personal_bank_expense,
            room_shares_owed=room_shares_owed,
            you_owe=you_owe,
            owe_room_count=owe_room_count,
            you_are_owed=you_are_owed,
            owed_room_count=owed_room_count,
            active_rooms_summary=active_rooms,
        )
