from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.rate_limit import enforce_rate_limit
from app.models.chat import ChatMessage, ChatRoom
from app.models.complaint import Complaint
from app.models.letter import Letter
from app.models.user import User
from app.services.config_service import get_int_config

VALID_TARGET_TYPES = {"LETTER", "ROOM", "MESSAGE", "USER"}


async def create_report(db: AsyncSession, redis: Redis, user: User, target_type: str, target_id: int, reason: str, description: str | None = None) -> Complaint:
    target_type = target_type.upper()
    if target_type not in VALID_TARGET_TYPES:
        raise AppException("INVALID_REPORT_TARGET", "举报对象类型不正确", 400)

    complaint = Complaint(reporter_id=user.id, reason=reason, description=description)
    if target_type == "USER":
        target = await db.get(User, target_id)
        if not target or target.id == user.id:
            raise AppException("USER_NOT_FOUND", "举报的用户不存在", 404)
        complaint.target_user_id = target.id
    elif target_type == "LETTER":
        letter = await db.get(Letter, target_id)
        if not letter:
            raise AppException("LETTER_NOT_FOUND", "举报的纸飞机不存在", 404)
        if user.id not in {letter.author_id, letter.salvaged_by}:
            raise AppException("FORBIDDEN", "无权举报未查看过的纸飞机", 403)
        complaint.letter_id = letter.id
        complaint.target_user_id = letter.author_id if letter.author_id != user.id else letter.salvaged_by
    elif target_type == "ROOM":
        room = await db.get(ChatRoom, target_id)
        if not room:
            raise AppException("ROOM_NOT_FOUND", "举报的房间不存在", 404)
        if user.id not in {room.user_a_id, room.user_b_id}:
            raise AppException("FORBIDDEN", "无权举报该房间", 403)
        complaint.room_id = room.id
        complaint.target_user_id = room.user_b_id if user.id == room.user_a_id else room.user_a_id
    else:
        msg = await db.get(ChatMessage, target_id)
        if not msg:
            raise AppException("MESSAGE_NOT_FOUND", "举报的消息不存在", 404)
        room = await db.get(ChatRoom, msg.room_id)
        if not room or user.id not in {room.user_a_id, room.user_b_id}:
            raise AppException("FORBIDDEN", "无权举报该消息", 403)
        complaint.message_id = msg.id
        complaint.room_id = msg.room_id
        complaint.target_user_id = msg.sender_id

    limit = await get_int_config(db, redis, "daily_complaint_limit", settings.daily_complaint_limit)
    await enforce_rate_limit(redis, f"limit:complaint:day:{user.id}", limit, 86400, "今日举报次数已达上限")

    db.add(complaint)
    await db.commit()
    await db.refresh(complaint)
    return complaint
