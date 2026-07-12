from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import ensure_user_can_post, get_current_user, get_db, get_redis
from app.core.exceptions import ok
from app.models.user import User
from app.schemas.salvage import SalvageRequest
from app.services.chat_service import create_chat_room_for_letter
from app.services.salvage_service import salvage_letter

router = APIRouter(prefix="/salvage", tags=["salvage"])


@router.post("")
async def salvage(payload: SalvageRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    ensure_user_can_post(user)
    data = await salvage_letter(db, redis, user, payload.emotion, None)
    if not data:
        return ok({"message": "暂时没有可以打捞的纸飞机"}, "暂时没有可以打捞的纸飞机")
    return ok(data, "打捞成功")


@router.post("/{letter_id}/reply")
async def reply(letter_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    ensure_user_can_post(user)
    room = await create_chat_room_for_letter(db, letter_id, user, redis)
    return ok({"room_id": room.id}, "临时会话已创建")
