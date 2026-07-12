from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SendCodeRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=32)


class LoginRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=32)
    code: str = Field(min_length=4, max_length=8)
    city: str | None = Field(default=None, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str


class EmailCodeRequest(BaseModel):
    email: EmailStr
    purpose: Literal["register", "reset"] = "register"


class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    code: str | None = Field(default=None, min_length=6, max_length=6)
    username: str | None = Field(
        default=None,
        min_length=2,
        max_length=20,
    )
    city: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=500)


class PasswordLoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=72)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=72)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class AdminLoginRequest(BaseModel):
    username: str
    password: str
