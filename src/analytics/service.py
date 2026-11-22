from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
import uuid
from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.models import BankTransaction, TransactionType
from src.analytics.schemas import (
    BankTransactionResponse,
    CategoryBreakdownResponse,
    CategorySpendItem,
    CashflowResponse,
    MonthlyTrendItem,
    TopMerchantItem,
    TopMerchantsResponse,
    TrendsResponse,
)


class AnalyticsService:
    @staticmethod
    def parse_month_bounds(month_str: str | None) -> tuple[str, date, date]:
        """
        Parses 'YYYY-MM' into (month_str, start_date, end_date) covering the full month.
        Defaults to current month if None.
        """
        if not month_str:
            today = date.today()
            year = today.year
            month = today.month
            formatted = f"{year}-{month:02d}"
        else:
            try:
                parts = month_str.strip().split("-")
                year = int(parts[0])
                month = int(parts[1])
                if not (1 <= month <= 12):
                    raise ValueError
                formatted = f"{year}-{month:02d}"
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid month format. Expected 'YYYY-MM' (e.g. '2026-11').",
                )

        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        return formatted, start_date, end_date

    @classmethod
    async def get_category_breakdown(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        month_str: str | None,
    ) -> CategoryBreakdownResponse:
        formatted_month, start_date, end_date = cls.parse_month_bounds(month_str)

        stmt = (
            select(
                BankTransaction.category,
                func.coalesce(func.sum(BankTransaction.amount), Decimal("0.00")).label("cat_total"),
            )
            .where(
                BankTransaction.user_id == user_id,
                BankTransaction.tx_type == TransactionType.DEBIT.value,
                BankTransaction.tx_date >= start_date,
                BankTransaction.tx_date <= end_date,
            )
            .group_by(BankTransaction.category)
            .order_by(func.sum(BankTransaction.amount).desc())
        )
        res = await db.execute(stmt)
        rows = res.all()

        total_spend = sum((Decimal(str(r.cat_total)) for r in rows), Decimal("0.00"))

        breakdown: list[CategorySpendItem] = []
        for r in rows:
            amt = Decimal(str(r.cat_total))
            pct = (amt / total_spend * Decimal("100")).quantize(Decimal("0.01")) if total_spend > Decimal("0.00") else Decimal("0.00")
            breakdown.append(
                CategorySpendItem(
                    category=r.category,
                    amount=amt,
                    percentage=pct,
                )
            )

        return CategoryBreakdownResponse(
            month=formatted_month,
            total_spend=total_spend,
            breakdown=breakdown,
        )

    @classmethod
    async def get_trends(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        months: int,
    ) -> TrendsResponse:
        if months not in (3, 6, 12):
            months = 6

        today = date.today()
        # Compute start month by going back 'months' months
        year = today.year
        month = today.month

        month_list: list[tuple[int, int]] = []
        for i in range(months - 1, -1, -1):
            m = month - i
            y = year
            while m <= 0:
                m += 12
                y -= 1
            month_list.append((y, m))

        earliest_y, earliest_m = month_list[0]
        start_date = date(earliest_y, earliest_m, 1)

        stmt = (
            select(
                func.extract("year", BankTransaction.tx_date).label("tx_year"),
                func.extract("month", BankTransaction.tx_date).label("tx_month"),
                func.coalesce(
                    func.sum(case((BankTransaction.tx_type == TransactionType.DEBIT.value, BankTransaction.amount), else_=0)),
                    0,
                ).label("debit_total"),
                func.coalesce(
                    func.sum(case((BankTransaction.tx_type == TransactionType.CREDIT.value, BankTransaction.amount), else_=0)),
                    0,
                ).label("credit_total"),
            )
            .where(
                BankTransaction.user_id == user_id,
                BankTransaction.tx_date >= start_date,
            )
            .group_by(
                func.extract("year", BankTransaction.tx_date),
                func.extract("month", BankTransaction.tx_date),
            )
        )
        res = await db.execute(stmt)
        data_map = {
            (int(r.tx_year), int(r.tx_month)): (Decimal(str(r.debit_total)), Decimal(str(r.credit_total)))
            for r in res.all()
        }

        trends: list[MonthlyTrendItem] = []
        for y, m in month_list:
            debit, credit = data_map.get((y, m), (Decimal("0.00"), Decimal("0.00")))
            trends.append(
                MonthlyTrendItem(
                    month=f"{y}-{m:02d}",
                    total_spend=debit,
                    total_income=credit,
                )
            )

        return TrendsResponse(months_requested=months, trends=trends)

    @classmethod
    async def get_cashflow(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        month_str: str | None,
    ) -> CashflowResponse:
        formatted_month, start_date, end_date = cls.parse_month_bounds(month_str)

        stmt = (
            select(
                func.coalesce(
                    func.sum(case((BankTransaction.tx_type == TransactionType.CREDIT.value, BankTransaction.amount), else_=0)),
                    0,
                ).label("inflows"),
                func.coalesce(
                    func.sum(case((BankTransaction.tx_type == TransactionType.DEBIT.value, BankTransaction.amount), else_=0)),
                    0,
                ).label("outflows"),
            )
            .where(
                BankTransaction.user_id == user_id,
                BankTransaction.tx_date >= start_date,
                BankTransaction.tx_date <= end_date,
            )
        )
        res = await db.execute(stmt)
        row = res.one()

        inflows = Decimal(str(row.inflows))
        outflows = Decimal(str(row.outflows))
        net_savings = inflows - outflows

        if inflows > Decimal("0.00"):
            savings_rate = (net_savings / inflows * Decimal("100")).quantize(Decimal("0.01"))
        else:
            savings_rate = Decimal("0.00")

        return CashflowResponse(
            month=formatted_month,
            inflows=inflows,
            outflows=outflows,
            net_savings=net_savings,
            savings_rate=savings_rate,
        )

    @classmethod
    async def get_top_merchants(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        month_str: str | None,
        sort_by: str = "spend",
    ) -> TopMerchantsResponse:
        formatted_month, start_date, end_date = cls.parse_month_bounds(month_str)

        order_col = (
            func.sum(BankTransaction.amount).desc()
            if sort_by.lower() != "visits"
            else func.count(BankTransaction.id).desc()
        )

        stmt = (
            select(
                BankTransaction.merchant_normalized,
                func.coalesce(func.sum(BankTransaction.amount), Decimal("0.00")).label("total_spend"),
                func.count(BankTransaction.id).label("visit_count"),
            )
            .where(
                BankTransaction.user_id == user_id,
                BankTransaction.tx_type == TransactionType.DEBIT.value,
                BankTransaction.tx_date >= start_date,
                BankTransaction.tx_date <= end_date,
            )
            .group_by(BankTransaction.merchant_normalized)
            .order_by(order_col)
            .limit(5)
        )
        res = await db.execute(stmt)
        rows = res.all()

        merchants = [
            TopMerchantItem(
                merchant=r.merchant_normalized,
                total_spend=Decimal(str(r.total_spend)),
                visit_count=r.visit_count,
            )
            for r in rows
        ]

        return TopMerchantsResponse(
            month=formatted_month,
            sort_by="visits" if sort_by.lower() == "visits" else "spend",
            merchants=merchants,
        )

    @staticmethod
    async def list_active_anomalies(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[BankTransactionResponse]:
        stmt = (
            select(BankTransaction)
            .where(
                BankTransaction.user_id == user_id,
                BankTransaction.is_anomaly == True,
                BankTransaction.is_anomaly_dismissed == False,
            )
            .order_by(BankTransaction.tx_date.desc(), BankTransaction.created_at.desc())
        )
        res = await db.execute(stmt)
        txs = res.scalars().all()
        return [BankTransactionResponse.from_model(t) for t in txs]

    @staticmethod
    async def dismiss_anomaly(
        db: AsyncSession,
        user_id: uuid.UUID,
        tx_id: uuid.UUID,
    ) -> BankTransactionResponse:
        stmt = select(BankTransaction).where(BankTransaction.id == tx_id)
        res = await db.execute(stmt)
        tx = res.scalar_one_or_none()

        if not tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found",
            )

        if tx.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not own this transaction",
            )

        tx.is_anomaly_dismissed = True
        await db.commit()
        await db.refresh(tx)
        return BankTransactionResponse.from_model(tx)

    @staticmethod
    async def override_category(
        db: AsyncSession,
        user_id: uuid.UUID,
        tx_id: uuid.UUID,
        new_category: str,
    ) -> BankTransactionResponse:
        stmt = select(BankTransaction).where(BankTransaction.id == tx_id)
        res = await db.execute(stmt)
        tx = res.scalar_one_or_none()

        if not tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found",
            )

        if tx.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not own this transaction",
            )

        tx.category = new_category.strip().upper()
        await db.commit()
        await db.refresh(tx)
        return BankTransactionResponse.from_model(tx)
