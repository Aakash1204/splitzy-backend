from datetime import date
from decimal import Decimal
from typing import Any
import uuid
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.models import BankTransaction, TransactionType


class FinancialTools:
    """
    Deterministic read-only database tools scoped strictly to the current user.
    Never relies on LLMs for calculations or raw transaction summing.
    """

    @staticmethod
    async def get_spend_by_category(
        db: AsyncSession,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            BankTransaction.category,
            func.coalesce(func.sum(BankTransaction.amount), Decimal("0.00")).label("total"),
        ).where(
            BankTransaction.user_id == user_id,
            BankTransaction.tx_type == TransactionType.DEBIT.value,
        )

        if start_date:
            stmt = stmt.where(BankTransaction.tx_date >= start_date)
        if end_date:
            stmt = stmt.where(BankTransaction.tx_date <= end_date)
        if category:
            stmt = stmt.where(func.upper(BankTransaction.category) == category.strip().upper())

        stmt = stmt.group_by(BankTransaction.category).order_by(func.sum(BankTransaction.amount).desc())
        res = await db.execute(stmt)
        rows = res.all()

        breakdown = [
            {"category": r.category, "amount": float(r.total)}
            for r in rows
        ]
        total = sum(item["amount"] for item in breakdown)
        return {
            "tool": "get_spend_by_category",
            "category_filtered": category,
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None,
            "total_spend": round(total, 2),
            "breakdown": breakdown,
        }

    @staticmethod
    async def get_spend_by_merchant(
        db: AsyncSession,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        merchant_query: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            BankTransaction.merchant_normalized,
            func.coalesce(func.sum(BankTransaction.amount), Decimal("0.00")).label("total"),
            func.count(BankTransaction.id).label("count"),
        ).where(
            BankTransaction.user_id == user_id,
            BankTransaction.tx_type == TransactionType.DEBIT.value,
        )

        if start_date:
            stmt = stmt.where(BankTransaction.tx_date >= start_date)
        if end_date:
            stmt = stmt.where(BankTransaction.tx_date <= end_date)
        if merchant_query:
            clean_q = f"%{merchant_query.strip().lower()}%"
            stmt = stmt.where(
                func.lower(BankTransaction.merchant_normalized).like(clean_q)
                | func.lower(BankTransaction.merchant_raw).like(clean_q)
            )

        stmt = stmt.group_by(BankTransaction.merchant_normalized).order_by(func.sum(BankTransaction.amount).desc())
        res = await db.execute(stmt)
        rows = res.all()

        merchants = [
            {"merchant": r.merchant_normalized, "total_spend": float(r.total), "transactions_count": r.count}
            for r in rows
        ]
        total = sum(m["total_spend"] for m in merchants)
        return {
            "tool": "get_spend_by_merchant",
            "merchant_query": merchant_query,
            "total_spend": round(total, 2),
            "merchants": merchants,
        }

    @staticmethod
    async def compare_periods(
        db: AsyncSession,
        user_id: uuid.UUID,
        period1_start: date,
        period1_end: date,
        period2_start: date,
        period2_end: date,
        category: str | None = None,
    ) -> dict[str, Any]:
        async def fetch_period_spend(s_date: date, e_date: date) -> float:
            stmt = select(
                func.coalesce(func.sum(BankTransaction.amount), Decimal("0.00")),
            ).where(
                BankTransaction.user_id == user_id,
                BankTransaction.tx_type == TransactionType.DEBIT.value,
                BankTransaction.tx_date >= s_date,
                BankTransaction.tx_date <= e_date,
            )
            if category:
                stmt = stmt.where(func.upper(BankTransaction.category) == category.strip().upper())
            res = await db.execute(stmt)
            return float(res.scalar_one_or_none() or 0.0)

        spend1 = await fetch_period_spend(period1_start, period1_end)
        spend2 = await fetch_period_spend(period2_start, period2_end)

        diff = spend2 - spend1
        pct_change = round((diff / spend1 * 100), 2) if spend1 > 0 else (100.0 if spend2 > 0 else 0.0)

        return {
            "tool": "compare_periods",
            "category": category,
            "period1": {
                "start": str(period1_start),
                "end": str(period1_end),
                "spend": round(spend1, 2),
            },
            "period2": {
                "start": str(period2_start),
                "end": str(period2_end),
                "spend": round(spend2, 2),
            },
            "difference": round(diff, 2),
            "percentage_change": pct_change,
        }

    @staticmethod
    async def get_top_merchants(
        db: AsyncSession,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        sort_by: str = "spend",
    ) -> dict[str, Any]:
        order_col = (
            func.sum(BankTransaction.amount).desc()
            if sort_by.lower() != "visits"
            else func.count(BankTransaction.id).desc()
        )

        stmt = select(
            BankTransaction.merchant_normalized,
            func.coalesce(func.sum(BankTransaction.amount), Decimal("0.00")).label("total"),
            func.count(BankTransaction.id).label("count"),
        ).where(
            BankTransaction.user_id == user_id,
            BankTransaction.tx_type == TransactionType.DEBIT.value,
        )

        if start_date:
            stmt = stmt.where(BankTransaction.tx_date >= start_date)
        if end_date:
            stmt = stmt.where(BankTransaction.tx_date <= end_date)

        stmt = stmt.group_by(BankTransaction.merchant_normalized).order_by(order_col).limit(5)
        res = await db.execute(stmt)
        rows = res.all()

        merchants = [
            {"merchant": r.merchant_normalized, "total_spend": float(r.total), "visits": r.count}
            for r in rows
        ]
        return {
            "tool": "get_top_merchants",
            "sort_by": sort_by,
            "top_merchants": merchants,
        }

    @staticmethod
    async def get_cashflow_summary(
        db: AsyncSession,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            func.coalesce(
                func.sum(case((BankTransaction.tx_type == TransactionType.CREDIT.value, BankTransaction.amount), else_=0)),
                0,
            ).label("inflows"),
            func.coalesce(
                func.sum(case((BankTransaction.tx_type == TransactionType.DEBIT.value, BankTransaction.amount), else_=0)),
                0,
            ).label("outflows"),
        ).where(
            BankTransaction.user_id == user_id,
        )

        if start_date:
            stmt = stmt.where(BankTransaction.tx_date >= start_date)
        if end_date:
            stmt = stmt.where(BankTransaction.tx_date <= end_date)

        res = await db.execute(stmt)
        row = res.one()

        inflows = float(row.inflows)
        outflows = float(row.outflows)
        net_savings = inflows - outflows
        savings_rate = round((net_savings / inflows * 100), 2) if inflows > 0 else 0.0

        return {
            "tool": "get_cashflow_summary",
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None,
            "inflows": round(inflows, 2),
            "outflows": round(outflows, 2),
            "net_savings": round(net_savings, 2),
            "savings_rate": savings_rate,
        }

    @staticmethod
    async def get_active_anomalies(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        stmt = select(
            BankTransaction.id,
            BankTransaction.tx_date,
            BankTransaction.merchant_normalized,
            BankTransaction.amount,
            BankTransaction.anomaly_type,
            BankTransaction.anomaly_reason,
        ).where(
            BankTransaction.user_id == user_id,
            BankTransaction.is_anomaly == True,
            BankTransaction.is_anomaly_dismissed == False,
        ).order_by(BankTransaction.tx_date.desc())

        res = await db.execute(stmt)
        rows = res.all()

        anomalies = [
            {
                "id": str(r.id),
                "date": str(r.tx_date),
                "merchant": r.merchant_normalized,
                "amount": float(r.amount),
                "type": r.anomaly_type,
                "reason": r.anomaly_reason,
            }
            for r in rows
        ]
        return {
            "tool": "get_active_anomalies",
            "total_anomalies": len(anomalies),
            "anomalies": anomalies,
        }
