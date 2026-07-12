from __future__ import annotations

import json
import re
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.letter import RiskLevel
from app.models.sensitive_word import SensitiveWord

SENSITIVE_WORD_CACHE_KEY = "risk:sensitive_words:cache"
SENSITIVE_WORD_CACHE_TTL = 300


@dataclass(slots=True)
class RiskResult:
    allowed: bool
    level: RiskLevel
    category: str | None = None
    reason: str | None = None
    high_risk: bool = False


STATIC_RULES = [
    (re.compile(r"https?://|www\.|\.com|\.cn|\.net", re.I), "网址", RiskLevel.MEDIUM, "禁止发送网址或引流链接"),
    (re.compile(r"(?:\+?\d{1,3}[- ]?)?1[3-9]\d{9}"), "手机号", RiskLevel.MEDIUM, "禁止发送手机号等联系方式"),
    (re.compile(r"(?:微信|vx|v信|wechat)[:： ]?[a-zA-Z0-9_\-]{5,}", re.I), "微信号", RiskLevel.MEDIUM, "禁止发送微信号等联系方式"),
    (re.compile(r"(?:QQ|qq)[:： ]?\d{5,12}"), "QQ号", RiskLevel.MEDIUM, "禁止发送 QQ 号等联系方式"),
]

STATIC_KEYWORDS: list[tuple[str, str, RiskLevel, str]] = [
    ("加微信", "引流", RiskLevel.MEDIUM, "禁止引流到站外联系方式"),
    ("私聊赚钱", "广告", RiskLevel.MEDIUM, "疑似广告引流内容"),
    ("兼职刷单", "广告", RiskLevel.MEDIUM, "疑似广告内容"),
    ("傻逼", "辱骂", RiskLevel.LOW, "请避免辱骂性表达"),
    ("去死", "辱骂", RiskLevel.MEDIUM, "请避免攻击性表达"),
]

HIGH_RISK_KEYWORDS = ["轻生", "自杀", "不想活", "结束生命", "跳楼", "割腕"]


def _level_from_string(value: str | RiskLevel | None) -> RiskLevel:
    if isinstance(value, RiskLevel):
        return value
    if not value:
        return RiskLevel.MEDIUM
    normalized = str(value).upper()
    if normalized in RiskLevel.__members__:
        return RiskLevel[normalized]
    for level in RiskLevel:
        if level.value == normalized:
            return level
    return RiskLevel.MEDIUM


async def load_sensitive_words(db: AsyncSession, redis: Redis | None) -> list[dict[str, str]]:
    if redis is not None:
        cached = await redis.get(SENSITIVE_WORD_CACHE_KEY)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                await redis.delete(SENSITIVE_WORD_CACHE_KEY)

    rows = (await db.execute(select(SensitiveWord).where(SensitiveWord.enabled.is_(True)))).scalars().all()
    data = [{"word": r.word, "category": r.category, "level": r.level} for r in rows]
    if redis is not None:
        await redis.set(SENSITIVE_WORD_CACHE_KEY, json.dumps(data, ensure_ascii=False), ex=SENSITIVE_WORD_CACHE_TTL)
    return data


async def clear_sensitive_word_cache(redis: Redis) -> None:
    await redis.delete(SENSITIVE_WORD_CACHE_KEY)


async def check_content(db: AsyncSession, redis: Redis | None, content: str) -> RiskResult:
    text = content or ""
    lowered = text.lower()

    if any(word in text for word in HIGH_RISK_KEYWORDS):
        return RiskResult(False, RiskLevel.HIGH, "极端消极", "内容包含高危消极表达，需要进入审核", True)

    for pattern, category, level, reason in STATIC_RULES:
        if pattern.search(text):
            return RiskResult(False, level, category, reason, False)

    for word, category, level, reason in STATIC_KEYWORDS:
        if word in text or word.lower() in lowered:
            return RiskResult(False, level, category, reason, level in {RiskLevel.HIGH, RiskLevel.CRITICAL})

    for row in await load_sensitive_words(db, redis):
        word = row.get("word", "")
        if not word:
            continue
        if word in text or word.lower() in lowered:
            level = _level_from_string(row.get("level"))
            high = level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
            return RiskResult(False, level, row.get("category") or "敏感词", f"命中后台敏感词：{word}", high)

    return RiskResult(True, RiskLevel.NONE)
