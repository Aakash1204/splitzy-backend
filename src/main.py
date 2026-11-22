from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.health import router as health_router
from src.core.config import settings
from src.core.database import engine
from src.users.router import auth_router, users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and graceful shutdown."""
    yield
    # Graceful shutdown: close async database connection pool
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-ready backend for Splitzy - expense-splitting and personal finance app",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware configured for React Native (iOS, Android, Web, Expo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register health check and API routers with /api/v1 prefix and root aliases
app.include_router(health_router)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)

# Also expose without prefix for convenience
app.include_router(auth_router)
app.include_router(users_router)
