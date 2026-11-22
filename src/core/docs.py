"""Swagger and OpenAPI documentation configuration for Splitzy API."""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

API_TITLE = "Splitzy API"
API_VERSION = "1.0.0"
API_SUMMARY = "Smart Expense-Splitting & Personal Financial Intelligence Platform"

API_DESCRIPTION = """
# Splitzy Backend API Documentation

Welcome to the **Splitzy** REST API documentation. Splitzy is a high-performance, privacy-first personal finance and expense-splitting backend engineered with **FastAPI**, **PostgreSQL** (with Async SQLAlchemy & asyncpg), and **Gemini AI**.

---

## 🚀 Quick Start & Authentication

Splitzy uses stateless **JWT Bearer Authentication** with **Argon2id** password hashing.

1. **Register** a new account via `POST /api/v1/auth/register` or **Login** via `POST /api/v1/auth/login`.
2. Both endpoints return an `access_token` and the user profile.
3. Click the **Authorize 🔓** button at the top right of this page.
4. Paste your token (e.g. `Bearer <access_token>` or just `<access_token>`).
5. All subsequent requests in Swagger UI will automatically include the `Authorization` header.

---

## 📦 Core Domain Modules

| Module | Prefix | Description |
| :--- | :--- | :--- |
| **Health** | `/health` | System health status and PostgreSQL database connectivity check |
| **Authentication** | `/api/v1/auth` | User registration, credential login, and JWT access token issuance |
| **Users** | `/api/v1/users` | Authenticated profile retrieval and GIN trigram-accelerated user search |
| **Rooms** | `/api/v1/rooms` | Shared expense spaces, vector icon/category customization, member management, and zero-balance archiving guardrails |
| **Expenses** | `/api/v1/rooms/{room_id}/expenses` & `/api/v1/expenses` | Flexible bill splitting (Equal, Exact, Percentage, Shares), activity feeds, dynamic ownership permissions (`can_edit`, `can_delete`), and SQL-aggregated debt simplification |
| **Settlements** | `/api/v1/rooms/{room_id}/settlements` | Direct peer-to-peer settlement recording ("Settle Up") without mutating historical expense records |
| **Bank Statements** | `/api/v1/statements` | Privacy-first bank statement upload (PDF, PNG, JPG) with CPU-offloaded async extraction and deterministic PII regex redaction |
| **Analytics** | `/api/v1/analytics` | Category breakdowns, 3/6/12-month trends, cashflow rates, top merchants, and automated anomaly detection (double charges, spikes, large amounts) |
| **Transactions** | `/api/v1/transactions` | Personal transaction management and manual category overrides |
| **AI Financial Assistant** | `/api/v1/ai` | Conversational financial query engine powered by Gemini with deterministic, read-only SQL tool calling |
| **Dashboard** | `/api/v1/dashboard` | Unified executive financial summary combining personal bank spending, individual room share obligations, owe/owed totals, and active rooms (<500ms) |

---

## 🔒 Security & Privacy Guarantees
- **Strict User Isolation**: All personal statements, transactions, and AI queries are strictly scoped to `current_user.id`.
- **Pre-LLM PII Redaction**: Bank statements have sensitive identifiers (account numbers, UPI IDs, Aadhaar, PAN) deterministically redacted before storage or AI processing.
- **Financial Precision**: All monetary calculations utilize strict `Decimal` arithmetic with deterministic remainder distribution. Full split bills are never incorrectly counted as personal expenses.
"""

TAGS_METADATA = [
    {
        "name": "Health",
        "description": "System health and database connectivity diagnostics.",
    },
    {
        "name": "Authentication",
        "description": "User registration, credential login, and JWT access token issuance.",
    },
    {
        "name": "Users",
        "description": "User profile retrieval and trigram-powered user search for room invites.",
    },
    {
        "name": "Rooms",
        "description": "Room lifecycle, category/icon customization, member management, and zero-balance archiving safety checks.",
    },
    {
        "name": "Expenses",
        "description": "Split bill creation across 4 split types (Equal, Exact, Percentage, Shares), activity feeds, pairwise debt calculations, and dynamic edit/delete permissions.",
    },
    {
        "name": "Settlements",
        "description": "Direct peer-to-peer settlement recording ('Settle Up') without mutating expense history.",
    },
    {
        "name": "Bank Statements",
        "description": "Privacy-first bank statement ingestion (PDF, PNG, JPG) with asynchronous OCR and deterministic PII redaction.",
    },
    {
        "name": "Analytics",
        "description": "Personal spending breakdown, category distribution, month-over-month trend lines, cashflow metrics, top merchants, and anomaly detection.",
    },
    {
        "name": "Transactions",
        "description": "Personal transaction management and manual category override.",
    },
    {
        "name": "AI Financial Assistant",
        "description": "Natural language conversational agent powered by Gemini with deterministic, read-only SQL tool calling.",
    },
    {
        "name": "Dashboard",
        "description": "Unified financial executive summary combining personal bank spending, room share burdens, owe/owed balances, and active room summaries (<500ms).",
    },
]

SWAGGER_UI_PARAMETERS = {
    "defaultModelsExpandDepth": 1,
    "defaultModelExpandDepth": 1,
    "deepLinking": True,
    "displayRequestDuration": True,
    "docExpansion": "list",
    "filter": True,
    "showExtensions": True,
    "showCommonExtensions": True,
    "syntaxHighlight.theme": "monokai",
    "persistAuthorization": True,
    "tryItOutEnabled": True,
}


def custom_openapi_schema(app: FastAPI) -> dict:
    """Generate and cache custom OpenAPI schema with Bearer auth description and server metadata."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=API_TITLE,
        version=API_VERSION,
        summary=API_SUMMARY,
        description=API_DESCRIPTION,
        routes=app.routes,
        tags=TAGS_METADATA,
    )

    # Ensure security schemes are cleanly documented
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Enter your JWT access token obtained from `POST /api/v1/auth/login` or "
            "`POST /api/v1/auth/register`. Swagger automatically prepends `Bearer `."
        ),
    }

    # Add contact and license info
    openapi_schema["info"]["contact"] = {
        "name": "Splitzy Engineering Team",
        "url": "https://github.com/splitzy/splitzy-backend",
    }
    openapi_schema["info"]["license"] = {
        "name": "Proprietary",
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema
