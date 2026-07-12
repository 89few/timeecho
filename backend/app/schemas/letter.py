from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.constants import ALLOWED_EMOTIONS, ALLOWED_SEAL_DAYS


class LetterCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    emotion: str = Field(max_length=32)
    seal_days: int | None = None
    seal_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 30)
    seal_seconds: int | None = Field(default=None, ge=1, le=3600)
    city: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_release_window(self):
        if self.emotion not in ALLOWED_EMOTIONS:
            raise ValueError(f"emotion 只能是：{', '.join(ALLOWED_EMOTIONS)}")
        if self.seal_seconds is not None:
            return self
        if self.seal_minutes is None:
            if self.seal_days not in ALLOWED_SEAL_DAYS:
                raise ValueError("seal_days 只能是 1、7、30；开发测试可以传 seal_minutes；开发演示可传 seal_seconds")
        return self


class LetterResponse(BaseModel):
    id: int
    emotion: str
    status: str
    risk_level: str
    release_at: datetime | None
    created_at: datetime
