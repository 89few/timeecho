from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.security import utcnow
from app.core.crypto import encrypt_text
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatMessage, ChatRoom, ChatRoomStatus
from app.models.complaint import Complaint
from app.models.letter import Letter, LetterStatus
from app.models.user import User, UserStatus
from app.models.system_config import SystemConfig
from app.services.chat_service import consecutive_unread_count, mark_messages_read, save_chat_message
from app.services.salvage_service import add_to_available_pools, rebuild_available_letter_pools, salvage_letter
from app.workers.cleanup_worker import cleanup_once
from app.workers.dormant_user_worker import dormant_user_once
from app.workers.release_letter_worker import process_due_letters_once
from tests.conftest import register


async def _make_available_letter(client, redis, token: str, content: str = "一个人也想被理解", emotion: str = "孤独", city: str = "东京") -> int:
    resp = await client.post(
        "/api/letters",
        json={"content": content, "emotion": emotion, "seal_minutes": 1, "city": city},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    letter_id = resp.json()["data"]["id"]
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        letter.status = LetterStatus.AVAILABLE
        await db.commit()
        await db.refresh(letter)
        await add_to_available_pools(redis, letter)
    return letter_id


@pytest.mark.asyncio
async def test_letters_mine_and_detail(client, setup_db_and_overrides):
    user = await register(client, "13900000001")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, user["access_token"])

    mine = await client.get("/api/letters/mine?status=AVAILABLE", headers={"Authorization": f"Bearer {user['access_token']}"})
    assert mine.status_code == 200, mine.text
    items = mine.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == letter_id
    assert items[0]["content_destroyed"] is False

    detail = await client.get(f"/api/letters/{letter_id}", headers={"Authorization": f"Bearer {user['access_token']}"})
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["content"]


@pytest.mark.asyncio
async def test_author_cannot_salvage_and_same_letter_only_once(client, setup_db_and_overrides):
    author = await register(client, "13900000002")
    b = await register(client, "13900000003")
    c = await register(client, "13900000004")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, author["access_token"])

    own = await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {author['access_token']}"})
    assert own.status_code == 200
    assert "暂时没有" in own.json()["message"]

    ok = await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["letter_id"] == letter_id

    again = await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {c['access_token']}"})
    assert again.status_code == 200
    assert "暂时没有" in again.json()["message"]


@pytest.mark.asyncio
async def test_concurrent_salvage_single_winner(client, setup_db_and_overrides):
    author = await register(client, "13900000005")
    b = await register(client, "13900000006")
    c = await register(client, "13900000007")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, author["access_token"])

    async def try_salvage(user_id: int):
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            return await salvage_letter(db, setup_db_and_overrides, user, "孤独", "东京")

    results = await asyncio.gather(try_salvage(b["user_id"]), try_salvage(c["user_id"]), return_exceptions=True)
    successes = [r for r in results if isinstance(r, dict)]
    assert len(successes) == 1
    assert successes[0]["letter_id"] == letter_id


@pytest.mark.asyncio
async def test_release_worker_due_not_due_risk_and_idempotent(client, setup_db_and_overrides, monkeypatch):
    import app.workers.release_letter_worker as worker
    monkeypatch.setattr(worker, "redis_client", setup_db_and_overrides)

    author = await register(client, "13900000008")
    due_id = await _make_available_letter(client, setup_db_and_overrides, author["access_token"], content="需要等到未来")
    async with AsyncSessionLocal() as db:
        due = await db.get(Letter, due_id)
        due.status = LetterStatus.SEALED
        due.release_at = utcnow() - timedelta(seconds=1)
        not_due = Letter(author_id=due.author_id, content_ciphertext=encrypt_text("未到期"), emotion="平静", city="东京", status=LetterStatus.SEALED, release_at=utcnow() + timedelta(days=1))
        risk = Letter(author_id=due.author_id, content_ciphertext=encrypt_text("审核"), emotion="焦虑", city="东京", status=LetterStatus.RISK_REVIEW, release_at=utcnow() - timedelta(seconds=1))
        db.add_all([not_due, risk])
        await db.commit()
        await db.refresh(not_due); await db.refresh(risk)
        not_due_id, risk_id = not_due.id, risk.id
        await setup_db_and_overrides.zadd("letter:sealed:zset", {str(due.id): due.release_at.timestamp(), str(not_due.id): not_due.release_at.timestamp(), str(risk.id): risk.release_at.timestamp()})

    assert await process_due_letters_once() == 1
    assert await process_due_letters_once() == 0
    async with AsyncSessionLocal() as db:
        due = await db.get(Letter, due_id)
        not_due = await db.get(Letter, not_due_id)
        risk = await db.get(Letter, risk_id)
        assert due.status == LetterStatus.AVAILABLE
        assert not_due.status == LetterStatus.SEALED
        assert risk.status == LetterStatus.RISK_REVIEW


@pytest.mark.asyncio
async def test_cleanup_worker_letters_rooms_idempotent(client, setup_db_and_overrides, monkeypatch):
    import app.workers.cleanup_worker as worker
    monkeypatch.setattr(worker, "redis_client", setup_db_and_overrides)

    a = await register(client, "13900000009")
    b = await register(client, "13900000010")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"], content="过期信")
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        letter.status = LetterStatus.SALVAGED
        letter.salvaged_by = b["user_id"]
        letter.salvaged_at = utcnow() - timedelta(days=2)
        letter.destroy_at = utcnow() - timedelta(seconds=1)
        room = ChatRoom(letter_id=letter_id, user_a_id=a["user_id"], user_b_id=b["user_id"], status=ChatRoomStatus.ACTIVE, created_at=utcnow() - timedelta(days=2), expired_at=utcnow() - timedelta(seconds=1))
        db.add(room)
        await db.flush()
        db.add(ChatMessage(room_id=room.id, sender_id=a["user_id"], content_ciphertext=encrypt_text("hello"), is_read=False, created_at=utcnow() - timedelta(days=2)))
        await db.commit()
        room_id = room.id

    result = await cleanup_once()
    assert result == {"rooms": 1, "letters": 1}
    assert await cleanup_once() == {"rooms": 0, "letters": 0}
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        room = await db.get(ChatRoom, room_id)
        msg = (await db.execute(select(ChatMessage).where(ChatMessage.room_id == room_id))).scalar_one()
        assert letter.status == LetterStatus.DESTROYED
        assert letter.content_ciphertext == ""
        assert room.status == ChatRoomStatus.EXPIRED
        assert msg.content_ciphertext == ""
        assert msg.deleted_at is not None


@pytest.mark.asyncio
async def test_admin_sensitive_word_affects_letter_creation(client):
    user = await register(client, "13900000011")
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    add = await client.post("/api/admin/sensitive-words", json={"word": "火星暗号", "category": "广告", "level": "MEDIUM"}, headers={"Authorization": f"Bearer {token}"})
    assert add.status_code == 200, add.text
    blocked = await client.post(
        "/api/letters",
        json={"content": "这里有火星暗号", "emotion": "平静", "seal_minutes": 1, "city": "东京"},
        headers={"Authorization": f"Bearer {user['access_token']}"},
    )
    assert blocked.status_code == 400
    assert blocked.json()["error_code"] == "CONTENT_BLOCKED"


@pytest.mark.asyncio
async def test_admin_system_config_limit_effective(client):
    user = await register(client, "13900000012")
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    cfg = await client.put("/api/admin/configs/daily_letter_limit", json={"config_value": "1"}, headers={"Authorization": f"Bearer {token}"})
    assert cfg.status_code == 200
    first = await client.post("/api/letters", json={"content": "第一封", "emotion": "平静", "seal_minutes": 1, "city": "东京"}, headers={"Authorization": f"Bearer {user['access_token']}"})
    assert first.status_code == 200, first.text
    second = await client.post("/api/letters", json={"content": "第二封", "emotion": "平静", "seal_minutes": 1, "city": "东京"}, headers={"Authorization": f"Bearer {user['access_token']}"})
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_report_api_and_admin_handle(client, setup_db_and_overrides):
    a = await register(client, "13900000013")
    b = await register(client, "13900000014")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"])
    await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    resp = await client.post("/api/reports", json={"target_type": "LETTER", "target_id": letter_id, "reason": "广告引流", "description": "测试"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    assert resp.status_code == 200, resp.text
    complaint_id = resp.json()["data"]["id"]
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    handled = await client.post(f"/api/admin/complaints/{complaint_id}/handle", json={"status": "HANDLED"}, headers={"Authorization": f"Bearer {token}"})
    assert handled.status_code == 200
    assert handled.json()["data"]["handled_at"] is not None
    async with AsyncSessionLocal() as db:
        c = await db.get(Complaint, complaint_id)
        assert c.handled_at is not None


@pytest.mark.asyncio
async def test_chat_room_status_unread_read_and_reminder(client, setup_db_and_overrides):
    a = await register(client, "13900000015")
    b = await register(client, "13900000016")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"], content="想聊聊")
    await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    reply = await client.post(f"/api/salvage/{letter_id}/reply", headers={"Authorization": f"Bearer {b['access_token']}"})
    room_id = reply.json()["data"]["room_id"]

    status = await client.get(f"/api/chat/rooms/{room_id}", headers={"Authorization": f"Bearer {b['access_token']}"})
    assert status.status_code == 200
    assert status.json()["data"]["peer_anonymous_name"]

    async with AsyncSessionLocal() as db:
        db.add(SystemConfig(config_key="chat_message_limit_per_minute", config_value="10"))
        await db.commit()
        await setup_db_and_overrides.delete("risk:system_config:chat_message_limit_per_minute")
        room = await db.get(ChatRoom, room_id)
        sender = await db.get(User, b["user_id"])
        for i in range(5):
            msg, count, _ = await save_chat_message(db, setup_db_and_overrides, room, sender, f"第{i}条")
        assert count == 5
        assert await consecutive_unread_count(db, room_id, b["user_id"]) == 5
        marked = await mark_messages_read(db, room_id, a["user_id"])
        assert marked == 5
        assert await consecutive_unread_count(db, room_id, b["user_id"]) == 0


@pytest.mark.asyncio
async def test_websocket_offline_payload_is_json(client, setup_db_and_overrides):
    payload = {"type": "message", "content": "你好", "message_id": 1}
    await setup_db_and_overrides.rpush("chat:offline:1:2", json.dumps(payload, ensure_ascii=False))
    item = (await setup_db_and_overrides.lrange("chat:offline:1:2", 0, -1))[0]
    assert json.loads(item) == payload


@pytest.mark.asyncio
async def test_admin_rebuild_available_pools(client, setup_db_and_overrides):
    a = await register(client, "13900000017")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"])
    await setup_db_and_overrides.delete("letter:available:all", "letter:available:emotion:孤独", "letter:available:city:东京", "letter:available:emotion_city:孤独:东京")
    assert not await setup_db_and_overrides.sismember("letter:available:all", str(letter_id))
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    resp = await client.post("/api/admin/maintenance/rebuild-available-pools", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["rebuilt"] == 1
    assert await setup_db_and_overrides.sismember("letter:available:all", str(letter_id))


@pytest.mark.asyncio
async def test_dormant_user_worker(client, setup_db_and_overrides, monkeypatch):
    import app.workers.dormant_user_worker as worker
    monkeypatch.setattr(worker, "redis_client", setup_db_and_overrides)

    user = await register(client, "13900000018")
    async with AsyncSessionLocal() as db:
        db_user = await db.get(User, user["user_id"])
        db_user.created_at = utcnow() - timedelta(days=8)
        db_user.last_login_at = utcnow() - timedelta(days=8)
        await db.commit()
    changed = await dormant_user_once(days=7)
    assert changed == 1
    async with AsyncSessionLocal() as db:
        db_user = await db.get(User, user["user_id"])
        assert db_user.status == UserStatus.DORMANT
