from __future__ import annotations

from pydantic import BaseModel, field_validator

PURPOSES = {"VENT", "LISTEN", "CASUAL"}
TOPICS = {"LIFE", "STUDY", "WORK", "RELATIONSHIP", "INTEREST", "LATE_NIGHT"}


class MatchJoinRequest(BaseModel):
    purpose: str
    topic: str

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in PURPOSES:
            raise ValueError("不支持的聊天目的")
        return value

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in TOPICS:
            raise ValueError("不支持的聊天话题")
        return value


class MatchEndRequest(BaseModel):
    action: str = "END"

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"END", "NO_REMATCH", "BLOCK"}:
            raise ValueError("不支持的结束方式")
        return value
