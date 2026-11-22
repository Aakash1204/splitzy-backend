from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100, description="User full name")
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(..., description="Unique email address")
    password: str = Field(..., min_length=6, max_length=128, description="User password")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Username cannot be empty")
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Full name cannot be empty")
        return cleaned


class UserLoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1, description="Username or email address")
    password: str = Field(..., min_length=1, description="Password")

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, v: str) -> str:
        return v.strip().lower()


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    username: str
    email: str
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileResponse
