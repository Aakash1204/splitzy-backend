import base64
import io
import json
import os
import re
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
import pypdf

load_dotenv()

# Ensure GOOGLE_API_KEY is available (supports GEMINI_API_KEY as an alias from .env)
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

# ============================================================================
# Pydantic Schemas for Structured Bank Statement Extraction
# ============================================================================

class StatementMeta(BaseModel):
    statement_id: str = Field(
        default="stmt_2024_10_01",
        description="Unique identifier for the statement, e.g. stmt_YYYY_MM_DD",
    )
    currency_code: str = Field(
        default="INR",
        description="3-letter currency code, e.g. INR, USD, EUR",
    )
    currency_symbol: str = Field(
        default="₹",
        description="Currency symbol, e.g. ₹, $, €",
    )
    period: str = Field(
        description="Period formatted as YYYY-MM, e.g. 2024-10",
    )
    period_label: str = Field(
        description="Human readable period label, e.g. October 2024",
    )


class MonthlyCashFlow(BaseModel):
    status: str = Field(
        description="Cashflow status: 'SURPLUS', 'DEFICIT', or 'BALANCED'",
    )
    income: float = Field(
        description="Total credited / income amount in the period",
    )
    expenses: float = Field(
        description="Total debited / expenditure amount in the period",
    )
    net_savings: float = Field(
        description="Net savings (income - expenses)",
    )
    net_savings_rate: float = Field(
        description="Savings rate percentage ((net_savings / income) * 100), rounded to 1 decimal",
    )


class CategoryItem(BaseModel):
    id: str = Field(
        description="Unique category ID in snake_case, e.g. food, rent_bills, travel, shopping, other_utilities_subscriptions",
    )
    name: str = Field(
        description="Display name of category, e.g. Food, Rent/Bills, Travel, Shopping",
    )
    amount: float = Field(
        description="Total spend amount allocated to this category",
    )
    percentage: float = Field(
        description="Percentage of total spending for this category, rounded to 1 decimal",
    )
    color_hex: str = Field(
        default="#8EC5FC",
        description="Hex color code for UI visualization, e.g. #B8A9FA, #8EC5FC, #6EE7B7, #FCA5A5, #FDE047",
    )


class CategoryBreakdown(BaseModel):
    active_buckets_count: int = Field(
        description="Total count of active spending categories",
    )
    total_spent: float = Field(
        description="Total expenditure amount across all categories",
    )
    budget_limit: Optional[float] = Field(
        default=None,
        description="Monthly budget limit or estimated budget capacity",
    )
    budget_status: str = Field(
        default="IN_BUDGET",
        description="'IN_BUDGET' or 'OVER_BUDGET'",
    )
    categories: List[CategoryItem] = Field(
        description="List of individual categorized expenses",
    )


class TrendDataPoint(BaseModel):
    period: str = Field(
        description="Period in YYYY-MM format, e.g. 2024-05",
    )
    label: str = Field(
        description="Short month label, e.g. May",
    )
    amount: float = Field(
        description="Total expenditure for that month",
    )
    is_current: bool = Field(
        default=False,
        description="True only if this data point represents the current statement period",
    )


class SpendingTrends(BaseModel):
    range: str = Field(
        default="6M",
        description="Selected range window, e.g. '6M'",
    )
    range_label: str = Field(
        default="Trailing 6 Months",
        description="Display label, e.g. 'Trailing 6 Months'",
    )
    available_ranges: List[str] = Field(
        default_factory=lambda: ["3M", "6M", "12M"],
        description="List of available range filters",
    )
    highlighted_amount: float = Field(
        description="Highlighted amount (typically the current period's total expenditure)",
    )
    data_points: List[TrendDataPoint] = Field(
        description="Chronological series of trend data points",
    )


class BankStatementAnalysisResponse(BaseModel):
    meta: StatementMeta
    monthly_cash_flow: MonthlyCashFlow
    category_breakdown: CategoryBreakdown
    spending_trends: SpendingTrends


# ============================================================================
# LLM Initialization
# ============================================================================

model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.1)

try:
    structured_extractor = llm.with_structured_output(BankStatementAnalysisResponse)
except Exception:
    structured_extractor = None

SYSTEM_PROMPT = """You are a senior financial analyst and document parsing expert.
Analyze the provided bank statement (text, PDF, or image) thoroughly and extract structured financial intelligence.

You MUST produce output following these specifications:
1. meta:
   - statement_id: e.g. stmt_YYYY_MM_DD
   - currency_code: 3-letter code (e.g. "INR", "USD")
   - currency_symbol: currency symbol (e.g. "₹", "$")
   - period: "YYYY-MM"
   - period_label: "Month YYYY" (e.g. "October 2024")

2. monthly_cash_flow:
   - status: "SURPLUS" if income > expenses else "DEFICIT" (or "BALANCED" if equal)
   - income: total credits / deposits
   - expenses: total debits / withdrawals
   - net_savings: income - expenses
   - net_savings_rate: (net_savings / income) * 100 if income > 0 else 0.0

3. category_breakdown:
   - active_buckets_count: count of active categories
   - total_spent: total expense sum
   - budget_limit: realistic target budget (e.g., 10-20% above total_spent)
   - budget_status: "IN_BUDGET" if total_spent <= budget_limit else "OVER_BUDGET"
   - categories: list of categories with:
     * id: snake_case (e.g., "food", "rent_bills", "travel", "shopping", "other_utilities_subscriptions", "healthcare", "entertainment")
     * name: Title Case (e.g., "Food", "Rent/Bills", "Travel", "Shopping", "Other Utilities & Subscriptions")
     * amount: total spent in that category
     * percentage: (amount / total_spent) * 100
     * color_hex: modern vibrant hex colors like "#B8A9FA", "#8EC5FC", "#6EE7B7", "#FCA5A5", "#FDE047", "#FDA4AF", "#C084FC"

4. spending_trends:
   - range: "6M"
   - range_label: "Trailing 6 Months"
   - available_ranges: ["3M", "6M", "12M"]
   - highlighted_amount: current month total expense
   - data_points: a 6-month trailing sequence culminating in the current statement period.
     If the statement only covers the current month, realistically project/interpolate the preceding 5 months matching typical seasonal spending so the UI trend graph displays 6 continuous data points. Mark the current month with is_current: true, and all previous with is_current: false.
"""

MAX_FILE_SIZE_MB = 20
MAX_FILE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(tags=["Bank Statement Extraction"])


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extracts plain text from PDF pages using pypdf."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        extracted_pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                extracted_pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
        return "\n\n".join(extracted_pages)
    except Exception:
        return ""


def _parse_json_fallback(raw_text: str) -> BankStatementAnalysisResponse:
    """Fallback parser to extract JSON block when structured output format isn't directly bound."""
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_text)
    json_str = match.group(1) if match else raw_text.strip()
    data = json.loads(json_str)
    return BankStatementAnalysisResponse.model_validate(data)


async def _run_llm_extraction(messages: list) -> BankStatementAnalysisResponse:
    """Invokes LLM with structured output or fallback JSON parsing."""
    if structured_extractor:
        try:
            result = await structured_extractor.ainvoke(messages)
            if isinstance(result, BankStatementAnalysisResponse):
                return result
            if isinstance(result, dict):
                return BankStatementAnalysisResponse.model_validate(result)
        except Exception:
            pass  # Fall back to standard invocation

    # Fallback standard invocation
    response = await llm.ainvoke(messages)
    content = response.content if hasattr(response, "content") else str(response)
    return _parse_json_fallback(content)


@router.post(
    "/api/extract",
    response_model=BankStatementAnalysisResponse,
    summary="Extract structured bank statement analysis from PDF or Image",
    description="Upload a bank statement PDF or Image. Returns full financial metadata, monthly cash flow, category breakdown, and 6M trends matching the Pydantic schema.",
)
@router.post(
    "/extract",
    response_model=BankStatementAnalysisResponse,
    include_in_schema=False,
)
async def extract_bank_statement(
    file: UploadFile = File(..., description="Uploaded bank statement PDF or Image file"),
    fileType: Optional[str] = Form(default=None, description="Optional indicator: 'pdf' or 'image'"),
    file_type: Optional[str] = Form(default=None, description="Alias for fileType"),
    user_id: Optional[str] = Form(default=None, description="Optional user ID"),
):
    """
    Handles PDF or Image bank statement uploads from the frontend:
    - Reads file bytes asynchronously in memory.
    - If PDF: extracts text via pypdf (or passes inline media if image-scanned).
    - If Image (JPEG, PNG, WEBP): base64 encodes and sends to Gemini Vision.
    - Returns structured Pydantic response with cash flow, categories, and trends.
    """
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB}MB.",
        )

    filename = (file.filename or "").lower()
    raw_content_type = (file.content_type or "").lower()
    type_hint = ((fileType or file_type) or "").lower()

    # Determine whether file is PDF or Image
    is_pdf = (
        type_hint == "pdf"
        or filename.endswith(".pdf")
        or "pdf" in raw_content_type
    )

    is_image = (
        type_hint in ["image", "img", "photo"]
        or raw_content_type.startswith("image/")
        or any(filename.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"])
    )

    if not is_pdf and not is_image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file format '{file.content_type}'. "
                "Please upload a PDF document or an image (PNG, JPG, WEBP)."
            ),
        )

    try:
        if is_pdf:
            # 1. Try extracting text from PDF
            extracted_text = _extract_text_from_pdf(file_bytes)

            if len(extracted_text.strip()) > 50:
                # Text-based PDF: feed text directly to LLM
                messages = [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=(
                            f"Analyze this bank statement document:\nFilename: {file.filename}\n\n"
                            f"{extracted_text}\n\n"
                            "Extract all financial figures according to the schema."
                        )
                    ),
                ]
            else:
                # Scanned/Image PDF: feed as inline base64 document
                b64_pdf = base64.b64encode(file_bytes).decode("utf-8")
                messages = [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": f"Analyze this scanned bank statement PDF (Filename: {file.filename}). Extract all figures according to the schema.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:application/pdf;base64,{b64_pdf}"},
                            },
                        ]
                    ),
                ]
        else:
            # Image file (PNG, JPG, WEBP, etc.)
            image_mime = raw_content_type if raw_content_type.startswith("image/") else "image/jpeg"
            b64_img = base64.b64encode(file_bytes).decode("utf-8")

            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": f"Analyze this bank statement image (Filename: {file.filename}). Extract all figures according to the schema.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{image_mime};base64,{b64_img}"},
                        },
                    ]
                ),
            ]

        result = await _run_llm_extraction(messages)
        return result

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze bank statement: {str(exc)}",
        )
    finally:
        await file.close()


# Optional standalone endpoint for simple image descriptions
@router.post("/describe", summary="Simple image description")
async def describe_simple_image(
    file: UploadFile = File(...),
    prompt_text: str = Form(default="Describe this image in detail."),
):
    contents = await file.read()
    mime = file.content_type or "image/jpeg"
    b64 = base64.b64encode(contents).decode("utf-8")
    resp = await llm.ainvoke([
        HumanMessage(content=[
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ])
    ])
    return {"description": resp.content}


# ============================================================================
# FastAPI Standalone Application
# ============================================================================

app = FastAPI(
    title="Splitzy Statement & Image Extraction API",
    description="Extracts structured bank statements from uploaded PDF or Image files using Gemini.",
)

# Enable CORS for React Native, Web, Expo, and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
