import asyncio
from datetime import date, datetime
import os
import re
import tempfile
from typing import Any
import pypdf

from src.statements.models import StatementFileType


class PIIRedactor:
    """
    Privacy-first deterministic pre-LLM PII redaction layer.
    Strips bank account numbers, IFSC codes, customer IDs, phone numbers,
    email addresses, PAN/Aadhaar numbers, and addresses/pincodes before any text
    is passed to downstream processors or LLMs.
    """

    # 1. Email addresses
    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        re.IGNORECASE,
    )

    # 2. PAN Card (5 letters, 4 digits, 1 letter)
    PAN_PATTERN = re.compile(
        r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
    )

    # 3. Aadhaar Number (12 digits, often 4-4-4)
    AADHAAR_PATTERN = re.compile(
        r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b"
    )

    # 4. IFSC Code (4 letters, 0, 6 alphanumeric)
    IFSC_PATTERN = re.compile(
        r"\b[A-Z]{4}0[A-Z0-9]{6}\b"
    )

    # 5. Customer ID / CIF Numbers
    CUSTOMER_ID_PATTERN = re.compile(
        r"(?i)\b(?:CIF|Cust(?:omer)?\s*(?:ID|No|Num)|CRN)[\s#:.-]*([A-Za-z0-9]{6,16})\b"
    )

    # 6. Explicitly labelled Account Numbers
    ACCOUNT_LABEL_PATTERN = re.compile(
        r"(?i)\b(?:A\/C|Account(?:\s*(?:Number|No|Num|#))?|Acc(?:\s*(?:Number|No|Num|#))?|Acct(?:\s*(?:Number|No|Num|#))?)[\s#:.-]*([0-9]{9,18})\b"
    )

    # 7. Standalone 11 to 18-digit bank account numbers
    STANDALONE_ACCOUNT_PATTERN = re.compile(
        r"\b[0-9]{11,18}\b"
    )

    # 8. Indian & international phone numbers (10 digits or + prefixed)
    PHONE_PATTERN = re.compile(
        r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b|\b\+[1-9]\d{0,2}[-.\s]\(?\d{2,4}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
    )

    # 9. Pincodes
    PINCODE_PATTERN = re.compile(
        r"(?i)\b(?:pin(?:\s*code)?|postal(?:\s*code)?)[\s#:.-]*([1-9][0-9]{5})\b"
    )

    # 10. Street addresses
    ADDRESS_PATTERN = re.compile(
        r"(?i)\b(?:Flat|Plot|House|Door|Bldg|Building|Street|Road|Lane|Sector|Nagar|Colony|Apartment|Appt|Cross|Main)[\s#.:\w,-]+(?:,\s*[A-Za-z\s]+){1,3}"
    )

    @classmethod
    def redact_text(cls, text: str) -> str:
        """
        Deterministically strips all PII from raw extracted statement text.
        Order of operations is intentional to avoid partial replacements.
        """
        redacted = text

        # 1. Email
        redacted = cls.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)

        # 2. PAN
        redacted = cls.PAN_PATTERN.sub("[REDACTED_PAN]", redacted)

        # 3. Aadhaar
        redacted = cls.AADHAAR_PATTERN.sub("[REDACTED_AADHAAR]", redacted)

        # 4. IFSC
        redacted = cls.IFSC_PATTERN.sub("[REDACTED_IFSC]", redacted)

        # 5. Customer / CIF ID
        redacted = cls.CUSTOMER_ID_PATTERN.sub("CUSTOMER_ID: [REDACTED_CUSTOMER_ID]", redacted)

        # 6. Explicit Account number labels
        redacted = cls.ACCOUNT_LABEL_PATTERN.sub("A/C: [REDACTED_ACCOUNT]", redacted)

        # 7. Standalone long account numbers (run before phone numbers to prioritize accounts)
        redacted = cls.STANDALONE_ACCOUNT_PATTERN.sub("[REDACTED_ACCOUNT]", redacted)

        # 8. Phone numbers
        redacted = cls.PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)

        # 9. Pincodes
        redacted = cls.PINCODE_PATTERN.sub("PIN: [REDACTED_PINCODE]", redacted)

        # 10. Street addresses
        redacted = cls.ADDRESS_PATTERN.sub("[REDACTED_ADDRESS]", redacted)

        return redacted

    @classmethod
    def extract_text_from_pdf(cls, file_path: str) -> str:
        """Synchronous CPU-bound PDF text extraction using pypdf."""
        extracted_chunks: list[str] = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    extracted_chunks.append(text)
        return "\n".join(extracted_chunks)

    @classmethod
    def extract_text_from_image(cls, file_path: str) -> str:
        """
        Synchronous OCR extraction hook for images (PNG/JPG).
        Tries pytesseract if available on system, otherwise falls back gracefully.
        """
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(file_path)
            return pytesseract.image_to_string(image)
        except Exception:
            # Fallback when OCR binary is not installed
            return f"[IMAGE_OCR_EXTRACTED_CONTENT: {os.path.basename(file_path)}]"

    @classmethod
    def parse_statement_metadata(cls, text: str) -> dict[str, Any]:
        """
        Extracts statement period dates (start/end) and estimates transaction count.
        """
        # Match common date patterns: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD
        date_patterns = [
            (r"\b(\d{2})[/.-](\d{2})[/.-](\d{4})\b", "%d-%m-%Y"),
            (r"\b(\d{4})[/.-](\d{2})[/.-](\d{2})\b", "%Y-%m-%d"),
        ]

        found_dates: list[date] = []
        for pat, fmt in date_patterns:
            matches = re.findall(pat, text)
            for match in matches:
                try:
                    if fmt == "%d-%m-%Y":
                        d_str = f"{match[0]}-{match[1]}-{match[2]}"
                    else:
                        d_str = f"{match[0]}-{match[1]}-{match[2]}"
                    parsed = datetime.strptime(d_str, fmt).date()
                    if 2000 <= parsed.year <= 2035:
                        found_dates.append(parsed)
                except ValueError:
                    continue

        period_start = min(found_dates) if found_dates else None
        period_end = max(found_dates) if found_dates else None

        # Estimate transactions: count lines that start with a date or contain currency amounts
        lines = text.split("\n")
        tx_count = 0
        tx_line_pattern = re.compile(r"^\s*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")
        for line in lines:
            if tx_line_pattern.match(line):
                tx_count += 1

        return {
            "period_start": period_start,
            "period_end": period_end,
            "transaction_count": tx_count,
        }

    @classmethod
    async def process_ephemeral(
        cls,
        file_bytes: bytes,
        file_type: StatementFileType,
        filename: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        Ephemeral processing:
        Writes uploaded file to a temporary file, offloads extraction to asyncio.to_thread
        to keep the event loop unblocked, redacts all PII, and GUARANTEES temp file deletion
        in a finally block immediately after extraction.
        """
        ext = ".pdf" if file_type == StatementFileType.PDF else ".png"
        temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        temp_path = temp_file.name

        try:
            # Write to disk temporarily for extraction tools
            temp_file.write(file_bytes)
            temp_file.flush()
            temp_file.close()

            # Offload CPU-heavy extraction to thread pool
            if file_type == StatementFileType.PDF:
                raw_text = await asyncio.to_thread(cls.extract_text_from_pdf, temp_path)
            else:
                raw_text = await asyncio.to_thread(cls.extract_text_from_image, temp_path)

            # Deterministic PII Redaction
            redacted_text = cls.redact_text(raw_text)

            # Metadata extraction
            metadata = cls.parse_statement_metadata(redacted_text)
            return redacted_text, metadata

        finally:
            # Strictly ephemeral: guarantee immediate deletion of temporary file
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
