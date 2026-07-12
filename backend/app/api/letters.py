from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import ensure_user_can_post, get_current_user, get_db, get_redis
from app.core.exceptions import ok
from app.models.user import User
from app.schemas.letter import LetterCreateRequest
from app.services.letter_service import create_letter, get_letter_for_user, letter_payload, list_user_letters

router = APIRouter(prefix="/letters", tags=["letters"])


@router.post("")
async def create(payload: LetterCreateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    ensure_user_can_post(user)
    letter = await create_letter(db, redis, user, payload.content, payload.emotion, payload.city, payload.seal_days, payload.seal_minutes, payload.seal_seconds)
    return ok(letter_payload(letter), "纸飞机已投递")


@router.get("/mine")
async def mine(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(await list_user_letters(db, user, status, page, page_size))


@router.get("/{letter_id}")
async def detail(letter_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return ok(await get_letter_for_user(db, user, letter_id))
