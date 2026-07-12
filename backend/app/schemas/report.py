from __future__ import annotations

from pydantic import BaseModel, Field


class ReportCreateRequest(BaseModel):
    target_type: str = Field(
        pattern="^(LETTER|ROOM|MESSAGE|USER|letter|room|message|user)$"
    )
    target_id: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1000)


class ReportReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1000)
