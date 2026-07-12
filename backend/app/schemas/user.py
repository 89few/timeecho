from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserMe(BaseModel):
    uid: str
    anonymous_name: str
    phone_masked: str | None
    email: str | None = None
    username: str | None = None
    email_verified: bool = False
    avatar_url: str | None = None
    bio: str | None = None
    emotion: str | None
    status: str
    muted_until: datetime | None
    created_at: datetime


class UpdateUserMe(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=20)
    emotion: str | None = Field(default=None, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=160)
