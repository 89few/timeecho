from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=72)
    role: str = "MODERATOR"


class AdminPasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=10, max_length=72)


class AdminEnabledUpdate(BaseModel):
    enabled: bool


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MuteRequest(BaseModel):
    minutes: int = Field(default=60, ge=1, le=60 * 24 * 365)
    reason: str | None = None


class BanRequest(BaseModel):
    reason: str | None = None


class ReviewActionRequest(BaseModel):
    release_now: bool = False


class SensitiveWordCreate(BaseModel):
    word: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    level: str = Field(default="MEDIUM", max_length=32)
    enabled: bool = True


class ConfigUpdate(BaseModel):
    config_value: str
    description: str | None = None


class ComplaintHandleRequest(BaseModel):
    status: str = "HANDLED"


class ComplaintResolutionRequest(BaseModel):
    decision: str = Field(pattern=r"^(VIOLATION|REJECTED)$")
    action: str = Field(default="NONE", pattern=r"^(NONE|REMOVE_CONTENT|MUTE|BAN)$")
    duration_minutes: int | None = Field(default=None, ge=1, le=525600)
    review_note: str = Field(min_length=2, max_length=1000)


class AdminUserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=8, max_length=72)
    city: str | None = Field(default=None, max_length=64)


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=2, max_length=20)
    city: str | None = Field(default=None, max_length=64)
    emotion: str | None = Field(default=None, max_length=32)
    bio: str | None = Field(default=None, max_length=160)
    avatar_url: str | None = Field(default=None, max_length=500)
