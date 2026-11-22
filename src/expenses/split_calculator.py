from decimal import Decimal, ROUND_DOWN
from typing import NamedTuple
import uuid
from fastapi import HTTPException, status

from src.expenses.models import SplitType

CENT = Decimal("0.01")


class CalculatedShare(NamedTuple):
    user_id: uuid.UUID
    owed_amount: Decimal
    share_input: Decimal | None


class SplitCalculator:
    @staticmethod
    def calculate_equal(
        total_amount: Decimal,
        participant_ids: list[uuid.UUID],
    ) -> list[CalculatedShare]:
        if not participant_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one participant is required for EQUAL split",
            )

        unique_ids = sorted(list(set(participant_ids)), key=lambda u: str(u))
        n = len(unique_ids)

        total_cents = int((total_amount * 100).to_integral_value())
        base_cents = total_cents // n
        remainder_cents = total_cents % n

        result: list[CalculatedShare] = []
        for idx, uid in enumerate(unique_ids):
            cents = base_cents + (1 if idx < remainder_cents else 0)
            owed = Decimal(cents) / Decimal(100)
            result.append(CalculatedShare(user_id=uid, owed_amount=owed, share_input=None))

        # Verification
        assert sum(r.owed_amount for r in result) == total_amount, "EQUAL split rounding error"
        return result

    @staticmethod
    def calculate_exact(
        total_amount: Decimal,
        participants: list[tuple[uuid.UUID, Decimal | None]],
    ) -> list[CalculatedShare]:
        if not participants:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Participants list cannot be empty for EXACT split",
            )

        result: list[CalculatedShare] = []
        running_total = Decimal("0.00")

        seen_users = set()
        for uid, val in participants:
            if uid in seen_users:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Duplicate participant user_id: {uid}",
                )
            seen_users.add(uid)

            if val is None or val < Decimal("0.00"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Exact owed amount for user {uid} must be non-negative",
                )

            quantized_val = val.quantize(CENT)
            running_total += quantized_val
            result.append(CalculatedShare(user_id=uid, owed_amount=quantized_val, share_input=quantized_val))

        if running_total != total_amount.quantize(CENT):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Sum of exact amounts ({running_total}) does not equal total amount ({total_amount})"
                ),
            )

        return result

    @staticmethod
    def calculate_percentage(
        total_amount: Decimal,
        participants: list[tuple[uuid.UUID, Decimal | None]],
    ) -> list[CalculatedShare]:
        if not participants:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Participants list cannot be empty for PERCENTAGE split",
            )

        seen_users = set()
        cleaned_items: list[tuple[uuid.UUID, Decimal]] = []
        total_pct = Decimal("0.00")

        for uid, val in participants:
            if uid in seen_users:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Duplicate participant user_id: {uid}",
                )
            seen_users.add(uid)

            if val is None or val < Decimal("0.00"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Percentage for user {uid} must be non-negative",
                )
            total_pct += val
            cleaned_items.append((uid, val))

        # Validate sum of percentages equals 100.00 (within 0.01 tolerance for precision representation)
        if total_pct.quantize(CENT) != Decimal("100.00"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Sum of percentages ({total_pct}%) must equal 100.00%",
            )

        target_cents = int((total_amount * 100).to_integral_value())

        # Largest Remainder Method
        temp = []
        allocated_cents = 0
        for uid, pct in cleaned_items:
            exact_cents = (total_amount * pct * 100) / Decimal("100")
            floor_cents = int(exact_cents.to_integral_value(rounding=ROUND_DOWN))
            rem = exact_cents - Decimal(floor_cents)
            allocated_cents += floor_cents
            temp.append({"user_id": uid, "pct": pct, "floor_cents": floor_cents, "rem": rem})

        diff_cents = target_cents - allocated_cents
        # Deterministically sort by remainder descending, tie-break with user_id
        temp.sort(key=lambda x: (-x["rem"], str(x["user_id"])))

        for i in range(diff_cents):
            temp[i]["floor_cents"] += 1

        result: list[CalculatedShare] = []
        for item in temp:
            owed = Decimal(item["floor_cents"]) / Decimal(100)
            result.append(
                CalculatedShare(
                    user_id=item["user_id"],
                    owed_amount=owed,
                    share_input=item["pct"],
                )
            )

        assert sum(r.owed_amount for r in result) == total_amount, "PERCENTAGE split rounding error"
        return result

    @staticmethod
    def calculate_shares(
        total_amount: Decimal,
        participants: list[tuple[uuid.UUID, Decimal | None]],
    ) -> list[CalculatedShare]:
        if not participants:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Participants list cannot be empty for SHARES split",
            )

        seen_users = set()
        cleaned_items: list[tuple[uuid.UUID, Decimal]] = []
        total_shares = Decimal("0")

        for uid, val in participants:
            if uid in seen_users:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Duplicate participant user_id: {uid}",
                )
            seen_users.add(uid)

            if val is None or val <= Decimal("0"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Share unit for user {uid} must be strictly greater than zero",
                )
            total_shares += val
            cleaned_items.append((uid, val))

        if total_shares <= Decimal("0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Total shares must be greater than zero",
            )

        target_cents = int((total_amount * 100).to_integral_value())

        # Largest Remainder Method
        temp = []
        allocated_cents = 0
        for uid, sh in cleaned_items:
            exact_cents = (total_amount * sh * 100) / total_shares
            floor_cents = int(exact_cents.to_integral_value(rounding=ROUND_DOWN))
            rem = exact_cents - Decimal(floor_cents)
            allocated_cents += floor_cents
            temp.append({"user_id": uid, "shares": sh, "floor_cents": floor_cents, "rem": rem})

        diff_cents = target_cents - allocated_cents
        temp.sort(key=lambda x: (-x["rem"], str(x["user_id"])))

        for i in range(diff_cents):
            temp[i]["floor_cents"] += 1

        result: list[CalculatedShare] = []
        for item in temp:
            owed = Decimal(item["floor_cents"]) / Decimal(100)
            result.append(
                CalculatedShare(
                    user_id=item["user_id"],
                    owed_amount=owed,
                    share_input=item["shares"],
                )
            )

        assert sum(r.owed_amount for r in result) == total_amount, "SHARES split rounding error"
        return result

    @classmethod
    def calculate(
        cls,
        split_type: SplitType | str,
        total_amount: Decimal,
        participants: list[tuple[uuid.UUID, Decimal | None]],
    ) -> list[CalculatedShare]:
        type_str = split_type.value if hasattr(split_type, "value") else str(split_type)

        if type_str == SplitType.EQUAL.value:
            participant_ids = [uid for uid, _ in participants]
            return cls.calculate_equal(total_amount, participant_ids)
        elif type_str == SplitType.EXACT.value:
            return cls.calculate_exact(total_amount, participants)
        elif type_str == SplitType.PERCENTAGE.value:
            return cls.calculate_percentage(total_amount, participants)
        elif type_str == SplitType.SHARES.value:
            return cls.calculate_shares(total_amount, participants)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported split type: {split_type}",
            )
