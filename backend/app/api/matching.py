from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_redis
from app.core.exceptions import ok
from app.models.user import User
from app.schemas.matching import MatchEndRequest, MatchJoinRequest
from app.services.matching_service import cancel_matching, end_match_room, heartbeat, join_matching, matching_status

router = APIRouter(prefix="/matching", tags=["matching"])


@router.get("/status")
async def status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    return ok(await matching_status(db, redis, user))


@router.post("/join")
async def join(payload: MatchJoinRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    return ok(await join_matching(db, redis, user, payload.purpose, payload.topic))


@router.post("/heartbeat")
async def keep_alive(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    return ok(await heartbeat(db, redis, user))


@router.post("/cancel")
async def cancel(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    return ok(await cancel_matching(db, redis, user))


@router.post("/rooms/{room_id}/end")
async def end_room(room_id: int, payload: MatchEndRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    return ok(await end_match_room(db, redis, user, room_id, payload.action))
