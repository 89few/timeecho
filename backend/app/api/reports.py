from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_redis
from app.core.exceptions import ok
from app.models.user import User
from app.schemas.report import ReportCreateRequest, ReportReasonRequest
from app.services.report_service import create_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("")
async def report(payload: ReportCreateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    complaint = await create_report(db, redis, user, payload.target_type, payload.target_id, payload.reason, payload.description)
    return ok({"id": complaint.id, "status": complaint.status.value, "created_at": complaint.created_at}, "举报已提交")


@router.post("/letter/{letter_id}")
async def report_letter(letter_id: int, payload: ReportReasonRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    complaint = await create_report(db, redis, user, "LETTER", letter_id, payload.reason, payload.description)
    return ok({"id": complaint.id, "status": complaint.status.value, "created_at": complaint.created_at}, "举报已提交")


@router.post("/room/{room_id}")
async def report_room(room_id: int, payload: ReportReasonRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    complaint = await create_report(db, redis, user, "ROOM", room_id, payload.reason, payload.description)
    return ok({"id": complaint.id, "status": complaint.status.value, "created_at": complaint.created_at}, "举报已提交")


@router.post("/message/{message_id}")
async def report_message(message_id: int, payload: ReportReasonRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    complaint = await create_report(db, redis, user, "MESSAGE", message_id, payload.reason, payload.description)
    return ok({"id": complaint.id, "status": complaint.status.value, "created_at": complaint.created_at}, "举报已提交")
