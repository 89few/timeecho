from __future__ import annotations

from datetime import datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import SEALED_ZSET_KEY
from app.core.crypto import decrypt_text, encrypt_text
from app.core.exceptions import AppException
from app.core.rate_limit import enforce_rate_limit
from app.core.security import utcnow
from app.models.letter import Letter, LetterStatus, RiskLevel
from app.models.user import User
from app.services.ai_service import classify_emotion
from app.services.config_service import get_int_config
from app.services.risk_service import check_content
from app.services.anonymous_identity_service import ensure_letter_identities


async def create_letter(db: AsyncSession, redis: Redis, user: User, content: str, emotion: str, city: str | None, seal_days: int | None, seal_minutes: int | None, seal_seconds: int | None = None) -> Letter:
    daily_limit = await get_int_config(db, redis, "daily_letter_limit", settings.daily_letter_limit)
    await enforce_rate_limit(redis, f"limit:letter:day:{user.id}", daily_limit, 86400, "今日投递次数已达上限")

    risk = await check_content(db, redis, content)
    ai = classify_emotion(content, emotion)
    final_emotion = ai.final_emotion
    final_risk_level = risk.level if risk.level != RiskLevel.NONE else ai.risk_level

    if risk.high_risk or ai.is_high_risk:
        status = LetterStatus.RISK_REVIEW
    elif not risk.allowed:
        raise AppException("CONTENT_BLOCKED", risk.reason or "内容未通过风控，请修改后再提交", 400)
    else:
        status = LetterStatus.SEALED

    now = utcnow()
    if seal_seconds is not None:
        if settings.app_env not in {"dev", "test"}:
            raise AppException("SEAL_SECONDS_DEV_ONLY", "seal_seconds 仅允许开发环境演示使用", 400)
        release_at = now + timedelta(seconds=seal_seconds)
    elif seal_minutes is not None:
        release_at = now + timedelta(minutes=seal_minutes)
    else:
        release_at = now + timedelta(days=seal_days or 1)

    letter = Letter(
        author_id=user.id,
        content_ciphertext=encrypt_text(content),
        content_key_version=settings.encryption_key_version,
        emotion=final_emotion,
        city=city or user.city,
        status=status,
        seal_days=seal_days,
        release_at=release_at,
        risk_level=final_risk_level,
    )
    db.add(letter)
    await db.flush()

    user.emotion = final_emotion
    if city:
        user.city = city

    if status == LetterStatus.SEALED:
        await redis.zadd(SEALED_ZSET_KEY, {str(letter.id): release_at.timestamp()})

    await db.commit()
    await db.refresh(letter)
    return letter


def letter_payload(letter: Letter) -> dict:
    return {
        "id": letter.id,
        "emotion": letter.emotion,
        "status": letter.status.value,
        "risk_level": letter.risk_level.value,
        "release_at": letter.release_at,
        "created_at": letter.created_at,
    }


def letter_summary_payload(letter: Letter) -> dict:
    destroyed = letter.status == LetterStatus.DESTROYED or not bool(letter.content_ciphertext)
    return {
        "id": letter.id,
        "emotion": letter.emotion,
        "status": letter.status.value,
        "risk_level": letter.risk_level.value,
        "release_at": letter.release_at,
        "salvaged_at": letter.salvaged_at,
        "destroy_at": letter.destroy_at,
        "created_at": letter.created_at,
        "content_destroyed": destroyed,
    }


async def letter_detail_payload(db: AsyncSession, letter: Letter, current_user: User, include_content: bool = True) -> dict:
    data = letter_summary_payload(letter)
    is_author = letter.author_id == current_user.id
    is_salvager = letter.salvaged_by == current_user.id
    if include_content and letter.status != LetterStatus.DESTROYED and letter.content_ciphertext:
        data["content"] = decrypt_text(letter.content_ciphertext)
    else:
        data["content"] = None
    if letter.salvaged_by:
        # City is a relationship clue and is deliberately removed from every
        # anonymous paper-plane detail until real identities are exchanged in
        # the room endpoint.
        data.pop("city", None)
        author_identity, salvager_identity = await ensure_letter_identities(
            db, letter.id, letter.author_id, letter.salvaged_by
        )
        mine = author_identity if is_author else salvager_identity
        peer_identity = salvager_identity if is_author else author_identity
        data["anonymous_name"] = mine.anonymous_name
        data["anonymous_avatar_url"] = mine.avatar_url
        data["peer_anonymous_name"] = peer_identity.anonymous_name
        data["peer_anonymous_avatar_url"] = peer_identity.avatar_url
    else:
        data["anonymous_name"] = None
        data["anonymous_avatar_url"] = None
        data["peer_anonymous_name"] = None
        data["peer_anonymous_avatar_url"] = None
    data["is_author"] = is_author
    data["is_salvager"] = is_salvager
    if is_salvager and letter.salvaged_by:
        data["author_anonymous_name"] = data["peer_anonymous_name"]
        data["author_anonymous_avatar_url"] = data["peer_anonymous_avatar_url"]
    return data


async def list_user_letters(db: AsyncSession, user: User, status: str | None, page: int, page_size: int) -> dict:
    stmt = select(Letter).where(Letter.author_id == user.id)
    if status:
        try:
            stmt = stmt.where(Letter.status == LetterStatus(status))
        except ValueError as exc:
            raise AppException("INVALID_STATUS", "不支持的纸飞机状态", 400) from exc
    stmt = stmt.order_by(Letter.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [letter_summary_payload(x) for x in rows], "page": page, "page_size": page_size}


async def get_letter_for_user(db: AsyncSession, user: User, letter_id: int) -> dict:
    letter = await db.get(Letter, letter_id)
    if not letter:
        raise AppException("LETTER_NOT_FOUND", "纸飞机不存在", 404)
    if letter.author_id != user.id and letter.salvaged_by != user.id:
        raise AppException("FORBIDDEN", "无权查看该纸飞机", 403)
    if letter.status == LetterStatus.SEALED and letter.author_id != user.id:
        raise AppException("FORBIDDEN", "封存中的纸飞机不可查看", 403)
    return await letter_detail_payload(db, letter, user, include_content=letter.status != LetterStatus.DESTROYED)


async def emotion_summary(db: AsyncSession, user: User, days: int = 7) -> dict:
    since = utcnow() - timedelta(days=days)
    rows = (await db.execute(select(Letter).where(Letter.author_id == user.id, Letter.created_at >= since))).scalars().all()
    counts: dict[str, int] = {}
    for letter in rows:
        counts[letter.emotion] = counts.get(letter.emotion, 0) + 1
    if not counts:
        summary = "最近 7 天还没有新的纸飞机记录，可以从一次简单记录开始。"
    else:
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:2]
        names = "和".join([x[0] for x in top])
        if any(x[0] in {"疲惫", "焦虑", "孤独"} for x in top):
            summary = f"最近 {days} 天你的情绪主要集中在{names}，建议适当休息，也可以把心情慢慢写下来。"
        else:
            summary = f"最近 {days} 天你的情绪主要集中在{names}，整体状态相对稳定。"
    return {"days": days, "total_letters": len(rows), "emotion_counts": counts, "summary": summary}
