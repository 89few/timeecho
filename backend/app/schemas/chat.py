from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRoomResponse(BaseModel):
    room_id: int
    room_kind: str = "TEMPORARY"
    letter_id: int | None = None
    status: str
    created_at: datetime
    expired_at: datetime | None = None
    destroyed_at: datetime | None = None
    peer_user_id: int | None = None
    peer_anonymous_name: str | None = None
    peer_display_name: str | None = None
    peer_avatar_url: str | None = None
    is_temporary: bool = True


class ExitRoomResponse(BaseModel):
    room_id: int
    status: str


class ChatMessageCreate(BaseModel):
    client_message_id: str = Field(min_length=1, max_length=64)
    content: str = Field(default="", max_length=4000)
    kind: str = Field(default="text", max_length=16)
    media_url: str | None = Field(default=None, max_length=512)
