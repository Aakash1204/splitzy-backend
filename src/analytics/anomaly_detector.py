from datetime import date, timedelta
from decimal import Decimal
import math
import uuid
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.models import AnomalyType, BankTransaction, TransactionType


class AnomalyDetector:
    @classmethod
    async def run_detection_for_user(cls, db: AsyncSession, user_id: uuid.UUID) -> int:
        """
        Runs the 3 anomaly detection checks across the user's transactions:
        1. DOUBLE_CHARGE: same merchant_normalized + same amount within 48 hours
        2. LARGE_TRANSACTION: debit > 2.5 standard deviations above category historical mean
        3. CATEGORY_SPIKE: current month category total >= 40% above 3-month rolling average
        Returns the number of newly detected anomalies.
        """
        # Fetch user's non-dismissed debit transactions
        stmt = (
            select(BankTransaction)
            .where(
                BankTransaction.user_id == user_id,
                BankTransaction.tx_type == TransactionType.DEBIT.value,
            )
            .order_by(BankTransaction.tx_date.asc(), BankTransaction.created_at.asc())
        )
        res = await db.execute(stmt)
        txs = list(res.scalars().all())

        if not txs:
            return 0

        flagged_count = 0

        # --- Rule 1: DOUBLE_CHARGE ---
        # Look for identical merchant_normalized + same amount within 48 hours (2 days)
        # Group by (merchant_normalized, amount)
        merchant_amt_map: dict[tuple[str, Decimal], list[BankTransaction]] = {}
        for tx in txs:
            key = (tx.merchant_normalized.lower(), tx.amount)
            merchant_amt_map.setdefault(key, []).append(tx)

        for (merchant_name, amt), group in merchant_amt_map.items():
            if len(group) >= 2:
                for i in range(len(group) - 1):
                    t1 = group[i]
                    t2 = group[i + 1]
                    diff_days = abs((t2.tx_date - t1.tx_date).days)
                    if diff_days <= 2:
                        # Flag the duplicate (t2) if not already flagged
                        if not t2.is_anomaly:
                            t2.is_anomaly = True
                            t2.anomaly_type = AnomalyType.DOUBLE_CHARGE.value
                            t2.anomaly_reason = (
                                f"Potential double charge: Identical amount {amt} at {t2.merchant_normalized} "
                                f"within {diff_days} day(s) of previous charge on {t1.tx_date}"
                            )
                            flagged_count += 1

        # --- Rule 2: LARGE_TRANSACTION (> 2.5 stddev above category mean) ---
        category_txs: dict[str, list[BankTransaction]] = {}
        for tx in txs:
            category_txs.setdefault(tx.category, []).append(tx)

        for cat, cat_list in category_txs.items():
            if len(cat_list) >= 3:
                amounts = [float(t.amount) for t in cat_list]
                mean_amt = sum(amounts) / len(amounts)
                variance = sum((x - mean_amt) ** 2 for x in amounts) / len(amounts)
                stddev = math.sqrt(variance)

                if stddev > 0:
                    threshold = mean_amt + (2.5 * stddev)
                    for t in cat_list:
                        if not t.is_anomaly and float(t.amount) > threshold:
                            t.is_anomaly = True
                            t.anomaly_type = AnomalyType.LARGE_TRANSACTION.value
                            t.anomaly_reason = (
                                f"Large transaction: Amount {t.amount} is > 2.5 standard deviations "
                                f"above category '{cat}' mean ({Decimal(str(round(mean_amt, 2)))})"
                            )
                            flagged_count += 1

        # --- Rule 3: CATEGORY_SPIKE (current month >= 40% above 3-month rolling average) ---
        # Group spend by (category, year, month)
        monthly_cat_spend: dict[tuple[str, int, int], Decimal] = {}
        for tx in txs:
            ym = (tx.category, tx.tx_date.year, tx.tx_date.month)
            monthly_cat_spend[ym] = monthly_cat_spend.get(ym, Decimal("0.00")) + tx.amount

        # For each (cat, y, m), calculate average of previous 3 months
        for (cat, y, m), current_spend in monthly_cat_spend.items():
            prev_spends = []
            cur_date = date(y, m, 1)
            for months_back in (1, 2, 3):
                # Approximate 1 month back
                p_date = (cur_date - timedelta(days=months_back * 30)).replace(day=1)
                prev_key = (cat, p_date.year, p_date.month)
                if prev_key in monthly_cat_spend:
                    prev_spends.append(monthly_cat_spend[prev_key])

            if prev_spends:
                avg_prev = sum(prev_spends) / Decimal(str(len(prev_spends)))
                if avg_prev > Decimal("0.00") and current_spend >= (avg_prev * Decimal("1.40")):
                    # Find candidate transaction in that category and month to attach spike alert
                    month_txs = [
                        t for t in txs
                        if t.category == cat and t.tx_date.year == y and t.tx_date.month == m and not t.is_anomaly
                    ]
                    if month_txs:
                        # Flag the largest transaction of that month with category spike
                        largest_tx = max(month_txs, key=lambda t: t.amount)
                        largest_tx.is_anomaly = True
                        largest_tx.anomaly_type = AnomalyType.CATEGORY_SPIKE.value
                        largest_tx.anomaly_reason = (
                            f"Category spend spike: '{cat}' total for {y}-{m:02d} ({current_spend}) "
                            f"is >= 40% higher than the 3-month average ({avg_prev.quantize(Decimal('0.01'))})"
                        )
                        flagged_count += 1

        if flagged_count > 0:
            await db.commit()

        return flagged_count
