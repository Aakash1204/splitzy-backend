from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db

# Password hashing with Argon2id (pwdlib recommended default is Argon2id)
password_hasher = PasswordHash.recommended()
http_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash password using Argon2id/bcrypt."""
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password."""
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(
    subject: str | int | dict[str, Any],
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    claims: dict[str, Any] = {
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    if isinstance(subject, dict):
        claims.update(subject)
    else:
        claims["sub"] = str(subject)

    if extra_claims:
        claims.update(extra_claims)

    return jwt.encode(
        claims,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> dict[str, Any]:
    """Extract and validate JWT token claims from Authorization header."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


async def get_current_user(
    payload: dict[str, Any] = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    """Async dependency returning the authenticated User model from database."""
    user_id_str = payload.get("sub") or payload.get("id")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(str(user_id_str))
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    from src.users.models import User

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
