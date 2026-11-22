from datetime import date, datetime
from decimal import Decimal
import hashlib
import re
from typing import NamedTuple
import uuid

from src.analytics.models import TransactionCategory, TransactionType


class ParsedTransaction(NamedTuple):
    tx_date: date
    merchant_raw: str
    merchant_normalized: str
    amount: Decimal
    tx_type: str
    category: str
    dedup_hash: str


# Mapping of lowercase keyword patterns to (normalized_merchant, category)
MERCHANT_CATEGORY_RULES = [
    # Food
    (r"\bswiggy\b", "Swiggy", TransactionCategory.FOOD.value),
    (r"\bzomato\b", "Zomato", TransactionCategory.FOOD.value),
    (r"\bmcdonalds?\b|\bkfc\b|\bdominos?\b|\bpizza\b|\bstarbucks\b", "Dining", TransactionCategory.FOOD.value),
    # Groceries
    (r"\bblinkit\b", "Blinkit", TransactionCategory.GROCERIES.value),
    (r"\bzepto\b", "Zepto", TransactionCategory.GROCERIES.value),
    (r"\binstamart\b", "Instamart", TransactionCategory.GROCERIES.value),
    (r"\bbigbasket\b|\bgrocery\b|\bsupermarket\b", "Groceries", TransactionCategory.GROCERIES.value),
    # Travel
    (r"\buber\b", "Uber", TransactionCategory.TRAVEL.value),
    (r"\bola\b", "Ola", TransactionCategory.TRAVEL.value),
    (r"\brapido\b", "Rapido", TransactionCategory.TRAVEL.value),
    (r"\birctc\b|\bindigo\b|\bair\s*india\b|\bmakemytrip\b|\bflight\b|\brailway\b", "Travel", TransactionCategory.TRAVEL.value),
    # Shopping
    (r"\bamazon\b", "Amazon", TransactionCategory.SHOPPING.value),
    (r"\bflipkart\b", "Flipkart", TransactionCategory.SHOPPING.value),
    (r"\bmyntra\b|\bzara\b|\bh&m\b|\bajio\b", "Fashion", TransactionCategory.SHOPPING.value),
    # Subscriptions
    (r"\bnetflix\b", "Netflix", TransactionCategory.SUBSCRIPTIONS.value),
    (r"\bspotify\b", "Spotify", TransactionCategory.SUBSCRIPTIONS.value),
    (r"\bprime\b|\bamazon\s*prime\b", "Amazon Prime", TransactionCategory.SUBSCRIPTIONS.value),
    (r"\bhotstar\b|\byoutube\s*premium\b|\bapple\.com\b", "Subscriptions", TransactionCategory.SUBSCRIPTIONS.value),
    # Utilities
    (r"\bairtel\b|\bjio\b|\bvi\b|\bbillpay\b|\belectricity\b|\bbescom\b|\bgas\b|\bwater\b", "Utilities", TransactionCategory.UTILITIES.value),
    # Rent
    (r"\brent\b|\bnobroker\b|\bhouse\s*rent\b", "Rent", TransactionCategory.RENT.value),
    # Salary / Income
    (r"\bsalary\b|\bpayroll\b|\bwages\b", "Salary", TransactionCategory.SALARY.value),
]


class StatementParser:
    @staticmethod
    def normalize_merchant_and_category(narration: str) -> tuple[str, str]:
        narration_lower = narration.lower()
        for pattern, merchant_norm, cat in MERCHANT_CATEGORY_RULES:
            if re.search(pattern, narration_lower):
                return merchant_norm, cat

        # Generic fallback: extract clean leading alphanumeric tokens
        tokens = re.findall(r"[A-Za-z0-9]+", narration)
        # Filter out common transaction noise words
        noise = {"upi", "pos", "neft", "imps", "rtgs", "ach", "dr", "cr", "to", "by", "transfer", "inb"}
        clean_tokens = [t.capitalize() for t in tokens if t.lower() not in noise and not t.isdigit()]

        merchant = " ".join(clean_tokens[:2]) if clean_tokens else "Other"
        return merchant[:100], TransactionCategory.OTHER.value

    @classmethod
    def parse_statement_text(cls, text: str, user_id: uuid.UUID) -> list[ParsedTransaction]:
        """
        Parses PII-redacted statement text lines into structured transactions.
        """
        lines = text.strip().split("\n")
        transactions: list[ParsedTransaction] = []

        # Date pattern at line beginning: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD
        line_regex = re.compile(
            r"^\s*(\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4})\s+(.+?)\s+([\d,]+(?:\.\d{1,2})?)\s*(dr|cr|debit|credit)?\s*$",
            re.IGNORECASE,
        )

        seq_idx = 0
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            match = line_regex.match(line_str)
            if not match:
                # Try finding date + amount inside line
                date_match = re.search(r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}[/.-]\d{1,2}[/.-]\d{1,2})\b", line_str)
                amount_match = re.search(r"\b([\d,]+\.\d{2})\b", line_str)
                if not (date_match and amount_match):
                    continue

                raw_date = date_match.group(1)
                raw_amt = amount_match.group(1)
                # Remainder of line as narration
                narration = line_str.replace(raw_date, "").replace(raw_amt, "").strip()
                indicator = "cr" if re.search(r"\b(cr|credit|salary|refund)\b", line_str, re.I) else "dr"
            else:
                raw_date = match.group(1)
                narration = match.group(2).strip()
                raw_amt = match.group(3)
                indicator = (match.group(4) or "dr").lower()

            # Parse date
            parsed_date = None
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).date()
                    break
                except ValueError:
                    pass

            if not parsed_date:
                continue

            # Parse amount
            try:
                cleaned_amt = Decimal(raw_amt.replace(",", ""))
                if cleaned_amt <= Decimal("0.00"):
                    continue
            except Exception:
                continue

            # Determine tx_type
            tx_type = TransactionType.CREDIT.value if indicator in ("cr", "credit") else TransactionType.DEBIT.value

            # Normalize merchant & category
            merchant_norm, category = cls.normalize_merchant_and_category(narration)

            # Generate SHA-256 dedup_hash
            hash_input = f"{user_id}_{parsed_date}_{cleaned_amt}_{narration[:100]}_{seq_idx}"
            dedup_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            seq_idx += 1

            transactions.append(
                ParsedTransaction(
                    tx_date=parsed_date,
                    merchant_raw=narration[:255] if narration else "Transaction",
                    merchant_normalized=merchant_norm,
                    amount=cleaned_amt,
                    tx_type=tx_type,
                    category=category,
                    dedup_hash=dedup_hash,
                )
            )

        return transactions
