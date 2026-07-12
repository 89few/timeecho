from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class SalvageRequest(BaseModel):
    emotion: str | None = Field(default=None, max_length=32)


class SalvageResponse(BaseModel):
    letter_id: int
    content: str
    emotion: str
    author_anonymous_name: str
    salvaged_at: datetime
    destroy_at: datetime


class ReplyResponse(BaseModel):
    room_id: int
    websocket_url: str
