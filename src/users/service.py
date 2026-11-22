import uuid
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password, verify_password
from src.users.models import User
from src.users.schemas import UserLoginRequest, UserRegisterRequest


class UserService:
    @staticmethod
    async def register_user(db: AsyncSession, payload: UserRegisterRequest) -> tuple[User, str]:
        # Validate username uniqueness
        stmt_username = select(User).where(User.username == payload.username)
        res_username = await db.execute(stmt_username)
        if res_username.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this username already exists",
            )

        # Validate email uniqueness
        stmt_email = select(User).where(User.email == payload.email)
        res_email = await db.execute(stmt_email)
        if res_email.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists",
            )

        # Create user with hashed password
        new_user = User(
            full_name=payload.full_name,
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # Issue JWT access token
        access_token = create_access_token(
            subject=str(new_user.id),
            extra_claims={"username": new_user.username, "email": new_user.email},
        )
        return new_user, access_token

    @staticmethod
    async def authenticate_user(db: AsyncSession, payload: UserLoginRequest) -> tuple[User, str]:
        # Query by lowercase username or email
        stmt = select(User).where(
            or_(
                User.username == payload.identifier,
                User.email == payload.identifier,
            )
        )
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username/email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"username": user.username, "email": user.email},
        )
        return user, access_token

    @staticmethod
    async def search_users(
        db: AsyncSession,
        query: str,
        current_user_id: uuid.UUID,
        limit: int = 20,
    ) -> list[User]:
        clean_query = query.strip()
        if not clean_query:
            return []

        pattern = f"%{clean_query.lower()}%"
        # Trigram-accelerated ILIKE search on username, full_name, or email
        stmt = (
            select(User)
            .where(
                User.id != current_user_id,
                or_(
                    User.username.ilike(pattern),
                    User.full_name.ilike(f"%{clean_query}%"),
                    User.email.ilike(pattern),
                ),
            )
            .order_by(User.username.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
