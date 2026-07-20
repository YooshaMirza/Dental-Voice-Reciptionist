from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    name: str = Field(..., max_length=200)
    phone: str = Field(..., max_length=15)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = "admin"

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Name is required.")
        return v

    @field_validator("phone")
    @classmethod
    def phone_not_blank(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Phone is required.")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v):
        if v not in ("admin", "other"):
            raise ValueError("Invalid role. Must be one of: admin, other")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenRefreshRequest(BaseModel):
    refresh: str


class OtpRequest(BaseModel):
    email: EmailStr
