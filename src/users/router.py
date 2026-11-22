from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.users.models import User
from src.users.schemas import (
    AuthResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
)
from src.users.service import UserService

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users"])


@auth_router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Registers a user with lowercase username and email, hashes the password, and returns a JWT access token.",
)
async def register(
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    user, access_token = await UserService.register_user(db, body)
    return AuthResponse(access_token=access_token, user=UserProfileResponse.model_validate(user))


@auth_router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Login user",
    description="Authenticates via username or email and password, returning a JWT access token.",
)
async def login(
    body: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user, access_token = await UserService.authenticate_user(db, body)
    return AuthResponse(access_token=access_token, user=UserProfileResponse.model_validate(user))


@users_router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Returns the profile of the currently authenticated user.",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user


@users_router.get(
    "/search",
    response_model=list[UserProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Search users",
    description="Search registered users by username, full_name, or email with case-insensitive trigram matching, excluding self.",
)
async def search_users(
    q: Annotated[str, Query(min_length=1, max_length=100, description="Search query string")],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of users to return")] = 20,
    db: AsyncSession = Depends(get_db),
):
    users = await UserService.search_users(
        db=db,
        query=q,
        current_user_id=current_user.id,
        limit=limit,
    )
    return users
