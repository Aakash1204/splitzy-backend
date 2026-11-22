from datetime import date, datetime, timezone
from decimal import Decimal
import uuid
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.expenses.models import ExpenseShare, SplitExpense, SplitType
from src.expenses.schemas import (
    MemberBalanceResponse,
    PairwiseDebtResponse,
    RoomBalancesResponse,
    SplitExpenseCreateRequest,
    SplitExpenseResponse,
    SplitExpenseUpdateRequest,
)
from src.expenses.split_calculator import SplitCalculator
from src.rooms.models import Room, RoomMember
from src.rooms.service import RoomService
from src.settlements.models import Settlement
from src.users.models import User
from src.users.schemas import UserProfileResponse


class ExpenseService:
    @staticmethod
    async def create_expense(
        db: AsyncSession,
        room: Room,
        current_user: User,
        payload: SplitExpenseCreateRequest,
    ) -> SplitExpenseResponse:
        # 1. Reject if room is ARCHIVED
        RoomService.assert_room_active(room)

        # 2. Verify paid_by is a room member
        payer_stmt = select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.user_id == payload.paid_by,
        )
        payer_res = await db.execute(payer_stmt)
        if not payer_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payer (paid_by) must be a member of this room",
            )

        # 3. Determine participants and split values
        split_type_val = (
            payload.split_type.value if hasattr(payload.split_type, "value") else str(payload.split_type)
        )

        if not payload.participants:
            if split_type_val == SplitType.EQUAL.value:
                # Default EQUAL split: all current members of the room
                members_stmt = select(RoomMember.user_id).where(RoomMember.room_id == room.id)
                members_res = await db.execute(members_stmt)
                all_member_ids = list(members_res.scalars().all())
                participant_inputs = [(uid, None) for uid in all_member_ids]
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Participants list is required for {split_type_val} split",
                )
        else:
            # Validate all participants are room members
            participant_ids = {p.user_id for p in payload.participants}
            member_check_stmt = select(RoomMember.user_id).where(
                RoomMember.room_id == room.id,
                RoomMember.user_id.in_(participant_ids),
            )
            member_check_res = await db.execute(member_check_stmt)
            valid_ids = set(member_check_res.scalars().all())

            missing = participant_ids - valid_ids
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Participant(s) are not members of this room: {list(missing)}",
                )

            participant_inputs = [(p.user_id, p.value) for p in payload.participants]

        # 4. Compute shares using flexible calculation engine
        calculated_shares = SplitCalculator.calculate(
            split_type=split_type_val,
            total_amount=payload.total_amount,
            participants=participant_inputs,
        )

        # 5. Atomically insert SplitExpense and ExpenseShares
        new_expense = SplitExpense(
            room_id=room.id,
            title=payload.title.strip(),
            total_amount=payload.total_amount,
            paid_by=payload.paid_by,
            created_by=current_user.id,
            split_type=split_type_val,
            expense_date=payload.expense_date or date.today(),
        )
        db.add(new_expense)
        await db.flush()

        for cs in calculated_shares:
            share = ExpenseShare(
                expense_id=new_expense.id,
                user_id=cs.user_id,
                owed_amount=cs.owed_amount,
                share_input=cs.share_input,
            )
            db.add(share)

        await db.commit()

        # Reload with relationships
        return await ExpenseService.get_expense_response(db, new_expense.id, current_user.id)

    @staticmethod
    async def get_expense_response(
        db: AsyncSession,
        expense_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> SplitExpenseResponse:
        stmt = (
            select(SplitExpense)
            .options(
                selectinload(SplitExpense.payer),
                selectinload(SplitExpense.creator),
                selectinload(SplitExpense.shares).selectinload(ExpenseShare.user),
            )
            .where(SplitExpense.id == expense_id)
            .execution_options(populate_existing=True)
        )
        res = await db.execute(stmt)
        expense = res.scalar_one_or_none()
        if not expense:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expense not found",
            )
        return SplitExpenseResponse.from_model(expense, current_user_id)

    @staticmethod
    async def get_room_expenses(
        db: AsyncSession,
        room_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> list[SplitExpenseResponse]:
        stmt = (
            select(SplitExpense)
            .options(
                selectinload(SplitExpense.payer),
                selectinload(SplitExpense.creator),
                selectinload(SplitExpense.shares).selectinload(ExpenseShare.user),
            )
            .where(SplitExpense.room_id == room_id)
            .order_by(SplitExpense.expense_date.desc(), SplitExpense.created_at.desc())
        )
        result = await db.execute(stmt)
        expenses = result.scalars().all()
        return [SplitExpenseResponse.from_model(exp, current_user_id) for exp in expenses]

    @staticmethod
    async def get_expense_by_id(
        db: AsyncSession,
        expense_id: uuid.UUID,
    ) -> SplitExpense:
        stmt = (
            select(SplitExpense)
            .options(
                selectinload(SplitExpense.room),
                selectinload(SplitExpense.payer),
                selectinload(SplitExpense.creator),
                selectinload(SplitExpense.shares).selectinload(ExpenseShare.user),
            )
            .where(SplitExpense.id == expense_id)
        )
        res = await db.execute(stmt)
        expense = res.scalar_one_or_none()
        if not expense:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expense not found",
            )
        return expense

    @staticmethod
    async def update_expense(
        db: AsyncSession,
        expense_id: uuid.UUID,
        current_user: User,
        payload: SplitExpenseUpdateRequest,
    ) -> SplitExpenseResponse:
        expense = await ExpenseService.get_expense_by_id(db, expense_id)

        # 1. Enforce creator-only authorization
        if expense.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Only the creator of this expense can edit it",
            )

        # 2. Reject if room is ARCHIVED
        RoomService.assert_room_active(expense.room)

        # 3. If paid_by changed, verify new paid_by is a room member
        if payload.paid_by and payload.paid_by != expense.paid_by:
            payer_stmt = select(RoomMember).where(
                RoomMember.room_id == expense.room_id,
                RoomMember.user_id == payload.paid_by,
            )
            payer_res = await db.execute(payer_stmt)
            if not payer_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Payer (paid_by) must be a member of this room",
                )
            expense.paid_by = payload.paid_by

        if payload.title is not None:
            expense.title = payload.title.strip()
        if payload.expense_date is not None:
            expense.expense_date = payload.expense_date

        target_total = payload.total_amount if payload.total_amount is not None else expense.total_amount
        target_split_type = (
            payload.split_type.value
            if (payload.split_type and hasattr(payload.split_type, "value"))
            else (str(payload.split_type) if payload.split_type else expense.split_type)
        )

        should_recalc_shares = (
            payload.participants is not None
            or payload.total_amount is not None
            or (payload.split_type is not None and target_split_type != expense.split_type)
        )

        if should_recalc_shares:
            if payload.participants is not None:
                # Validate participants are room members
                participant_ids = {p.user_id for p in payload.participants}
                member_check_stmt = select(RoomMember.user_id).where(
                    RoomMember.room_id == expense.room_id,
                    RoomMember.user_id.in_(participant_ids),
                )
                member_check_res = await db.execute(member_check_stmt)
                valid_ids = set(member_check_res.scalars().all())

                missing = participant_ids - valid_ids
                if missing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Participant(s) are not members of this room: {list(missing)}",
                    )
                participant_inputs = [(p.user_id, p.value) for p in payload.participants]
            else:
                # Reuse existing participants
                if target_split_type == SplitType.EQUAL.value:
                    participant_inputs = [(s.user_id, None) for s in expense.shares]
                elif target_split_type == SplitType.PERCENTAGE.value:
                    participant_inputs = [(s.user_id, s.share_input) for s in expense.shares]
                elif target_split_type == SplitType.SHARES.value:
                    participant_inputs = [(s.user_id, s.share_input) for s in expense.shares]
                else:  # EXACT
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Participants list must be provided when updating total_amount for an EXACT split",
                    )

            calculated_shares = SplitCalculator.calculate(
                split_type=target_split_type,
                total_amount=target_total,
                participants=participant_inputs,
            )

            expense.total_amount = target_total
            expense.split_type = target_split_type

            # Atomically replace expense_shares: clear and flush deletes first to avoid uq_expense_shares_expense_user conflict
            expense.shares.clear()
            await db.flush()

            for cs in calculated_shares:
                expense.shares.append(
                    ExpenseShare(
                        expense_id=expense.id,
                        user_id=cs.user_id,
                        owed_amount=cs.owed_amount,
                        share_input=cs.share_input,
                    )
                )

        expense.updated_at = datetime.now(timezone.utc)
        await db.commit()

        return await ExpenseService.get_expense_response(db, expense.id, current_user.id)

    @staticmethod
    async def delete_expense(
        db: AsyncSession,
        expense_id: uuid.UUID,
        current_user: User,
    ) -> dict:
        expense = await ExpenseService.get_expense_by_id(db, expense_id)

        # 1. Enforce creator-only authorization
        if expense.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Only the creator of this expense can delete it",
            )

        # 2. Reject if room is ARCHIVED
        RoomService.assert_room_active(expense.room)

        await db.delete(expense)
        await db.commit()

        return {
            "message": "Expense deleted successfully",
            "expense_id": str(expense_id),
        }

    @staticmethod
    async def get_room_balances(
        db: AsyncSession,
        room_id: uuid.UUID,
    ) -> RoomBalancesResponse:
        # 1. Fetch all room members
        members_stmt = (
            select(User)
            .join(RoomMember, RoomMember.user_id == User.id)
            .where(RoomMember.room_id == room_id)
            .order_by(RoomMember.joined_at.asc())
        )
        members_res = await db.execute(members_stmt)
        members = list(members_res.scalars().all())

        # 2. Aggregate total_paid per user for this room
        paid_stmt = (
            select(
                SplitExpense.paid_by,
                func.coalesce(func.sum(SplitExpense.total_amount), 0).label("total_paid"),
            )
            .where(SplitExpense.room_id == room_id)
            .group_by(SplitExpense.paid_by)
        )
        paid_res = await db.execute(paid_stmt)
        paid_map = {row.paid_by: Decimal(str(row.total_paid)) for row in paid_res.all()}

        # 3. Aggregate total_share_owed per user for this room
        owed_stmt = (
            select(
                ExpenseShare.user_id,
                func.coalesce(func.sum(ExpenseShare.owed_amount), 0).label("total_owed"),
            )
            .join(SplitExpense, SplitExpense.id == ExpenseShare.expense_id)
            .where(SplitExpense.room_id == room_id)
            .group_by(ExpenseShare.user_id)
        )
        owed_res = await db.execute(owed_stmt)
        owed_map = {row.user_id: Decimal(str(row.total_owed)) for row in owed_res.all()}

        # 4. Aggregate settlements_paid_out per user for this room
        settle_paid_stmt = (
            select(
                Settlement.payer_id,
                func.coalesce(func.sum(Settlement.amount), 0).label("settlements_paid_out"),
            )
            .where(Settlement.room_id == room_id)
            .group_by(Settlement.payer_id)
        )
        settle_paid_res = await db.execute(settle_paid_stmt)
        settle_paid_map = {row.payer_id: Decimal(str(row.settlements_paid_out)) for row in settle_paid_res.all()}

        # 5. Aggregate settlements_received per user for this room
        settle_recv_stmt = (
            select(
                Settlement.payee_id,
                func.coalesce(func.sum(Settlement.amount), 0).label("settlements_received"),
            )
            .where(Settlement.room_id == room_id)
            .group_by(Settlement.payee_id)
        )
        settle_recv_res = await db.execute(settle_recv_stmt)
        settle_recv_map = {row.payee_id: Decimal(str(row.settlements_received)) for row in settle_recv_res.all()}

        # 6. Compute each member's net balance:
        # net_balance = total_paid - total_share_owed + settlements_paid_out - settlements_received
        balances: list[MemberBalanceResponse] = []
        user_profiles: dict[uuid.UUID, UserProfileResponse] = {}

        for m in members:
            profile = UserProfileResponse.model_validate(m)
            user_profiles[m.id] = profile
            total_paid = paid_map.get(m.id, Decimal("0.00"))
            total_share_owed = owed_map.get(m.id, Decimal("0.00"))
            settlements_paid_out = settle_paid_map.get(m.id, Decimal("0.00"))
            settlements_received = settle_recv_map.get(m.id, Decimal("0.00"))

            net = total_paid - total_share_owed + settlements_paid_out - settlements_received
            balances.append(
                MemberBalanceResponse(
                    user=profile,
                    total_paid=total_paid,
                    total_owed=total_share_owed,
                    settlements_paid_out=settlements_paid_out,
                    settlements_received=settlements_received,
                    net_balance=net,
                )
            )

        # 5. Calculate pairwise simplified debts
        # Debtors (net < 0) owe Creditors (net > 0)
        debtors = []
        creditors = []
        for b in balances:
            if b.net_balance < Decimal("0.00"):
                debtors.append({"user_id": b.user.id, "amount": -b.net_balance})
            elif b.net_balance > Decimal("0.00"):
                creditors.append({"user_id": b.user.id, "amount": b.net_balance})

        debtors.sort(key=lambda x: x["amount"], reverse=True)
        creditors.sort(key=lambda x: x["amount"], reverse=True)

        debts: list[PairwiseDebtResponse] = []
        d_idx, c_idx = 0, 0
        while d_idx < len(debtors) and c_idx < len(creditors):
            debtor = debtors[d_idx]
            creditor = creditors[c_idx]

            settle = min(debtor["amount"], creditor["amount"])
            if settle > Decimal("0.00"):
                debts.append(
                    PairwiseDebtResponse(
                        from_user=user_profiles[debtor["user_id"]],
                        to_user=user_profiles[creditor["user_id"]],
                        amount=settle.quantize(Decimal("0.01")),
                    )
                )

            debtor["amount"] -= settle
            creditor["amount"] -= settle

            if debtor["amount"] == Decimal("0.00"):
                d_idx += 1
            if creditor["amount"] == Decimal("0.00"):
                c_idx += 1

        return RoomBalancesResponse(
            room_id=room_id,
            balances=balances,
            debts=debts,
        )
