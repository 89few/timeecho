from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.constants import SEALED_ZSET_KEY
from app.db.session import AsyncSessionLocal, redis_client
from app.models.letter import Letter, LetterStatus
from app.services.salvage_service import add_to_available_pools
from tests.conftest import register


@pytest.mark.asyncio
async def test_send_code_login_and_me(client):
    data = await register(client, "13812345678")
    assert data["access_token"]
    me = await client.get("/api/users/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["phone_masked"] == "138****5678"


@pytest.mark.asyncio
async def test_login_response_does_not_expose_user_id(client):
    phone = "13812345679"
    await client.post("/api/auth/send-code", json={"phone": phone})
    response = await client.post(
        "/api/auth/login",
        json={"phone": phone, "code": "123456", "city": "Tokyo"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "user_id" not in data
    assert "id" not in data


@pytest.mark.asyncio
async def test_me_response_does_not_expose_user_id(client):
    data = await register(client, "13812345680")
    response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert response.status_code == 200
    profile = response.json()["data"]
    assert "id" not in profile
    assert "user_id" not in profile


@pytest.mark.asyncio
async def test_create_letter_and_release_logic(client, setup_db_and_overrides):
    user = await register(client, "13800000001")
    resp = await client.post(
        "/api/letters",
        json={"content": "今天很累，但还是想慢慢来", "emotion": "疲惫", "seal_minutes": 1, "city": "东京"},
        headers={"Authorization": f"Bearer {user['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    letter_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "SEALED"

    # 手动模拟到期并释放，避免测试等待 1 分钟。
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        letter.status = LetterStatus.AVAILABLE
        await db.commit()
        await db.refresh(letter)
        redis = setup_db_and_overrides
        await add_to_available_pools(redis, letter)
        assert await redis.sismember("letter:available:all", str(letter_id))


@pytest.mark.asyncio
async def test_salvage_excludes_self_and_prevents_duplicate(client, setup_db_and_overrides):
    author = await register(client, "13800000002")
    salvager = await register(client, "13800000003")
    create = await client.post(
        "/api/letters",
        json={"content": "一个人也想被理解", "emotion": "孤独", "seal_minutes": 1, "city": "东京"},
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    letter_id = create.json()["data"]["id"]
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        letter.status = LetterStatus.AVAILABLE
        await db.commit()
        await db.refresh(letter)
        redis = setup_db_and_overrides
        await add_to_available_pools(redis, letter)

    self_try = await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {author['access_token']}"})
    assert self_try.status_code == 200
    assert "暂时没有" in self_try.json()["message"]

    ok_resp = await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {salvager['access_token']}"})
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["data"]["letter_id"] == letter_id

    again = await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {salvager['access_token']}"})
    assert "暂时没有" in again.json()["message"]


@pytest.mark.asyncio
async def test_empty_salvage_attempts_do_not_consume_daily_quota(client, setup_db_and_overrides):
    user = await register(client, "13800000031")
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    for _ in range(8):
        response = await client.post(
            "/api/salvage",
            json={"emotion": "平静", "city": "上海"},
            headers=headers,
        )
        assert response.status_code == 200
        assert "暂时没有" in response.json()["message"]
    assert await setup_db_and_overrides.get(f"limit:salvage:day:{user['user_id']}") is None


@pytest.mark.asyncio
async def test_create_chat_room_after_salvage(client, setup_db_and_overrides):
    author = await register(client, "13800000004")
    salvager = await register(client, "13800000005")
    create = await client.post(
        "/api/letters",
        json={"content": "压力很大，想找个人共鸣", "emotion": "焦虑", "seal_minutes": 1, "city": "东京"},
        headers={"Authorization": f"Bearer {author['access_token']}"},
    )
    letter_id = create.json()["data"]["id"]
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        letter.status = LetterStatus.AVAILABLE
        await db.commit()
        await db.refresh(letter)
        redis = setup_db_and_overrides
        await add_to_available_pools(redis, letter)
    await client.post("/api/salvage", json={"emotion": "焦虑", "city": "东京"}, headers={"Authorization": f"Bearer {salvager['access_token']}"})
    reply = await client.post(f"/api/salvage/{letter_id}/reply", headers={"Authorization": f"Bearer {salvager['access_token']}"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["data"]["room_id"]


@pytest.mark.asyncio
async def test_sensitive_word_intercept(client):
    user = await register(client, "13800000006")
    resp = await client.post(
        "/api/letters",
        json={"content": "加微信 vx:abcdefg 详聊", "emotion": "平静", "seal_minutes": 1, "city": "东京"},
        headers={"Authorization": f"Bearer {user['access_token']}"},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "CONTENT_BLOCKED"


@pytest.mark.asyncio
async def test_admin_ban_user(client):
    user = await register(client, "13800000007")
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    ban = await client.post(f"/api/admin/users/{user['user_id']}/ban", json={"reason": "测试封禁"}, headers={"Authorization": f"Bearer {token}"})
    assert ban.status_code == 200
    assert ban.json()["data"]["status"] == "BANNED"
