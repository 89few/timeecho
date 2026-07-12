from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.models.social import PostVisibility


class FriendRequestCreate(BaseModel):
    target_user_id: int = Field(gt=0)
    message: str | None = Field(default=None, max_length=120)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class FriendRemarkUpdate(BaseModel):
    remark: str | None = Field(default=None, max_length=40)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class PostMediaInput(BaseModel):
    kind: str
    url: str = Field(min_length=1, max_length=2048)
    thumbnail_url: str | None = Field(default=None, max_length=2048)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    width: int | None = Field(default=None, ge=1, le=20_000)
    height: int | None = Field(default=None, ge=1, le=20_000)

    @field_validator("kind")
    @classmethod
    def valid_kind(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"image", "video", "audio"}:
            raise ValueError("媒体类型仅支持 image、video 或 audio")
        return value


class PostCreate(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    media: list[PostMediaInput] = Field(default_factory=list, max_length=9)
    visibility: PostVisibility = PostVisibility.PUBLIC

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    parent_comment_id: int | None = Field(default=None, gt=0)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("评论不能为空")
        return value
