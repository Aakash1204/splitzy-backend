from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.health import router as health_router
from src.core.config import settings
from src.core.database import engine
from src.core.docs import (
    API_DESCRIPTION,
    API_SUMMARY,
    API_TITLE,
    API_VERSION,
    SWAGGER_UI_PARAMETERS,
    TAGS_METADATA,
    custom_openapi_schema,
)
from src.users.router import auth_router, users_router
from src.rooms.router import rooms_router
from src.expenses.router import room_expenses_router, expenses_router
from src.settlements.router import settlements_router
from src.statements.router import statements_router
from src.analytics.router import analytics_router, transactions_router
from src.ai_chat.router import ai_router
from src.dashboard.router import dashboard_router
from src.image_to_text.image import router as extract_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and graceful shutdown."""
    yield
    # Graceful shutdown: close async database connection pool
    await engine.dispose()


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    summary=API_SUMMARY,
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
    lifespan=lifespan,
)

# Custom OpenAPI schema generator with detailed security schemes and metadata
app.openapi = lambda: custom_openapi_schema(app)

# CORS middleware configured for React Native (iOS, Android, Web, Expo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Canonical API endpoints (documented in Swagger UI / ReDoc)
app.include_router(health_router)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(rooms_router, prefix=settings.API_V1_PREFIX)
app.include_router(room_expenses_router, prefix=settings.API_V1_PREFIX)
app.include_router(expenses_router, prefix=settings.API_V1_PREFIX)
app.include_router(settlements_router, prefix=settings.API_V1_PREFIX)
app.include_router(statements_router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics_router, prefix=settings.API_V1_PREFIX)
app.include_router(transactions_router, prefix=settings.API_V1_PREFIX)
app.include_router(ai_router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard_router, prefix=settings.API_V1_PREFIX)
app.include_router(extract_router)

# Root aliases without prefix (functional for backwards-compatibility, hidden from Swagger to avoid duplicates)
app.include_router(auth_router, include_in_schema=False)
app.include_router(users_router, include_in_schema=False)
app.include_router(rooms_router, include_in_schema=False)
app.include_router(room_expenses_router, include_in_schema=False)
app.include_router(expenses_router, include_in_schema=False)
app.include_router(settlements_router, include_in_schema=False)
app.include_router(statements_router, include_in_schema=False)
app.include_router(analytics_router, include_in_schema=False)
app.include_router(transactions_router, include_in_schema=False)
app.include_router(ai_router, include_in_schema=False)
app.include_router(dashboard_router, include_in_schema=False)
