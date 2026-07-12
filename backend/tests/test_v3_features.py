from __future__ import annotations

import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select

from app.core.crypto import encrypt_text
from app.core.security import decode_token, utcnow
from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.chat import ChatMessage, ChatRoom, ChatRoomStatus
from app.models.complaint import Complaint
from app.models.letter import Letter, LetterStatus, RiskLevel
from app.models.user import User
from app.services.salvage_service import add_to_available_pools
from tests.conftest import register


def ws_ticket(client, user: dict) -> str:
    response = client.post(
        "/api/auth/ws-ticket",
        headers={"Authorization": f"Bearer {user['access_token']}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["ticket"]


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


async def _make_room(client, redis):
    a = await register(client, "15000000001")
    b = await register(client, "15000000002")
    letter_id = await _make_available_letter(client, redis, a["access_token"], content="想被某个人听见")
    salvaged = await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    assert salvaged.status_code == 200, salvaged.text
    reply = await client.post(f"/api/salvage/{letter_id}/reply", headers={"Authorization": f"Bearer {b['access_token']}"})
    assert reply.status_code == 200, reply.text
    return a, b, letter_id, reply.json()["data"]["room_id"]


@pytest.mark.asyncio
async def test_user_letter_detail_does_not_expose_internal_user_ids(client, setup_db_and_overrides):
    a = await register(client, "15000000003")
    b = await register(client, "15000000004")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"])
    await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})

    for token in [a["access_token"], b["access_token"]]:
        resp = await client.get(f"/api/letters/{letter_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "author_id" not in data
        assert "salvaged_by" not in data
        assert "sender_id" not in data
        assert "user_a_id" not in data
        assert "user_b_id" not in data
        assert "anonymous_name" in data
        assert "is_author" in data
        assert "is_salvager" in data

    reply = await client.post(f"/api/salvage/{letter_id}/reply", headers={"Authorization": f"Bearer {b['access_token']}"})
    room_id = reply.json()["data"]["room_id"]
    room = await client.get(f"/api/chat/rooms/{room_id}", headers={"Authorization": f"Bearer {a['access_token']}"})
    assert room.status_code == 200
    room_data = room.json()["data"]
    assert "user_a_id" not in room_data
    assert "user_b_id" not in room_data
    assert "peer_anonymous_name" in room_data


@pytest.mark.asyncio
async def test_cannot_report_unseen_letter(client, setup_db_and_overrides):
    a = await register(client, "15000000005")
    c = await register(client, "15000000006")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"])
    resp = await client.post("/api/reports", json={"target_type": "LETTER", "target_id": letter_id, "reason": "广告引流"}, headers={"Authorization": f"Bearer {c['access_token']}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_author_can_report_own_letter(client, setup_db_and_overrides):
    a = await register(client, "15000000007")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"])
    resp = await client.post("/api/reports", json={"target_type": "LETTER", "target_id": letter_id, "reason": "误投递"}, headers={"Authorization": f"Bearer {a['access_token']}"})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_salvager_can_report_letter(client, setup_db_and_overrides):
    a = await register(client, "15000000008")
    b = await register(client, "15000000009")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"])
    await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    resp = await client.post("/api/reports", json={"target_type": "LETTER", "target_id": letter_id, "reason": "广告引流"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_non_room_member_cannot_report_room(client, setup_db_and_overrides):
    a, b, letter_id, room_id = await _make_room(client, setup_db_and_overrides)
    c = await register(client, "15000000010")
    resp = await client.post("/api/reports", json={"target_type": "ROOM", "target_id": room_id, "reason": "骚扰"}, headers={"Authorization": f"Bearer {c['access_token']}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_room_member_cannot_report_message(client, setup_db_and_overrides):
    a, b, letter_id, room_id = await _make_room(client, setup_db_and_overrides)
    c = await register(client, "15000000011")
    async with AsyncSessionLocal() as db:
        msg = ChatMessage(room_id=room_id, sender_id=b["user_id"], content_ciphertext=encrypt_text("你好"), is_read=False, created_at=utcnow())
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        message_id = msg.id
    resp = await client.post("/api/reports", json={"target_type": "MESSAGE", "target_id": message_id, "reason": "骚扰"}, headers={"Authorization": f"Bearer {c['access_token']}"})
    assert resp.status_code == 403
    missing = await client.post("/api/reports", json={"target_type": "MESSAGE", "target_id": 999999, "reason": "骚扰"}, headers={"Authorization": f"Bearer {a['access_token']}"})
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_admin_review_can_decrypt_letter_content_when_plain_dev_field_empty(client):
    user = await register(client, "15000000012")
    resp = await client.post(
        "/api/letters",
        json={"content": "我不想活，只想先被安全审核", "emotion": "焦虑", "seal_minutes": 1, "city": "东京"},
        headers={"Authorization": f"Bearer {user['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    letter_id = resp.json()["data"]["id"]
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        assert letter.status == LetterStatus.RISK_REVIEW
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    reviews = await client.get("/api/admin/reviews/letters", headers={"Authorization": f"Bearer {token}"})
    assert reviews.status_code == 200, reviews.text
    item = reviews.json()["data"][0]
    assert item["id"] == letter_id
    assert "不想活" in item["content"]
    assert item["content_destroyed"] is False


@pytest.mark.asyncio
async def test_admin_complaints_include_target_content(client, setup_db_and_overrides):
    a = await register(client, "15000000013")
    b = await register(client, "15000000014")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"], content="这是一封可审核的纸飞机")
    await client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    report = await client.post("/api/reports", json={"target_type": "LETTER", "target_id": letter_id, "reason": "广告引流"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    assert report.status_code == 200, report.text
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    complaints = await client.get("/api/admin/complaints", headers={"Authorization": f"Bearer {token}"})
    assert complaints.status_code == 200
    item = complaints.json()["data"][0]
    assert item["target_type"] == "LETTER"
    assert "可审核" in item["target_content"]


@pytest.mark.asyncio
async def test_validation_error_response_format(client):
    user = await register(client, "15000000015")
    resp = await client.post("/api/letters", json={"emotion": "平静", "seal_minutes": 1}, headers={"Authorization": f"Bearer {user['access_token']}"})
    assert resp.status_code == 422
    data = resp.json()
    assert data["success"] is False
    assert data["error_code"] == "VALIDATION_ERROR"
    assert data["message"] == "请求参数不正确"
    assert isinstance(data["details"], list)


@pytest.mark.asyncio
async def test_admin_process_due_letters_once(client):
    user = await register(client, "15000000016")
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    letter = await client.post("/api/letters", json={"content": "很累但还好", "emotion": "疲惫", "seal_seconds": 1, "city": "东京"}, headers={"Authorization": f"Bearer {user['access_token']}"})
    assert letter.status_code == 200, letter.text
    time.sleep(1.1)
    released = await client.post("/api/admin/maintenance/process-due-letters-once", headers={"Authorization": f"Bearer {token}"})
    assert released.status_code == 200, released.text
    assert released.json()["data"]["released"] == 1


@pytest.mark.asyncio
async def test_admin_cleanup_once(client, setup_db_and_overrides):
    a = await register(client, "15000000017")
    b = await register(client, "15000000018")
    letter_id = await _make_available_letter(client, setup_db_and_overrides, a["access_token"], content="将被清理")
    async with AsyncSessionLocal() as db:
        letter = await db.get(Letter, letter_id)
        letter.status = LetterStatus.SALVAGED
        letter.salvaged_by = b["user_id"]
        letter.salvaged_at = utcnow() - timedelta(days=2)
        letter.destroy_at = utcnow() - timedelta(seconds=1)
        room = ChatRoom(letter_id=letter_id, user_a_id=a["user_id"], user_b_id=b["user_id"], status=ChatRoomStatus.ACTIVE, created_at=utcnow() - timedelta(days=2), expired_at=utcnow() - timedelta(seconds=1))
        db.add(room)
        await db.commit()
    admin = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = admin.json()["data"]["access_token"]
    resp = await client.post("/api/admin/maintenance/cleanup-once", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"rooms": 1, "letters": 1}


def _sync_register(client: TestClient, phone: str, city: str = "东京") -> dict:
    assert client.post("/api/auth/send-code", json={"phone": phone}).status_code == 200
    resp = client.post("/api/auth/login", json={"phone": phone, "code": "123456", "city": city})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return {**data, "user_id": int(decode_token(data["access_token"])["sub"])}


def _sync_make_room(client: TestClient, suffix: str = "") -> tuple[dict, dict, int, int]:
    admin = client.post("/api/admin/login", json={"username": "admin", "password": "admin123"}).json()["data"]
    a = _sync_register(client, f"151{suffix}0000001"[-11:])
    b = _sync_register(client, f"151{suffix}0000002"[-11:])
    create = client.post("/api/letters", json={"content": "想被某个人听见", "emotion": "孤独", "seal_seconds": 1, "city": "东京"}, headers={"Authorization": f"Bearer {a['access_token']}"})
    assert create.status_code == 200, create.text
    letter_id = create.json()["data"]["id"]
    time.sleep(1.1)
    released = client.post("/api/admin/maintenance/process-due-letters-once", headers={"Authorization": f"Bearer {admin['access_token']}"})
    assert released.status_code == 200, released.text
    salvaged = client.post("/api/salvage", json={"emotion": "孤独", "city": "东京"}, headers={"Authorization": f"Bearer {b['access_token']}"})
    assert salvaged.status_code == 200, salvaged.text
    reply = client.post(f"/api/salvage/{letter_id}/reply", headers={"Authorization": f"Bearer {b['access_token']}"})
    assert reply.status_code == 200, reply.text
    return a, b, letter_id, reply.json()["data"]["room_id"]


def test_websocket_two_users_can_send_and_receive_message(setup_db_and_overrides):
    with TestClient(app) as sync_client:
        a, b, _, room_id = _sync_make_room(sync_client, "001")
        with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, a)}") as ws_a:
            with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, b)}") as ws_b:
                ws_b.send_json({"type": "message", "content": "看到你的信，我也有过类似的时候。"})
                received = ws_a.receive_json()
                ack = ws_b.receive_json()
                assert received["type"] == "message"
                assert received["content"] == "看到你的信，我也有过类似的时候。"
                assert "sender_id" not in received
                assert received["sender_name"]
                assert received["sender_role"] == "peer"
                assert ack["type"] == "ack"


def test_two_users_can_upload_and_receive_media_in_realtime(setup_db_and_overrides):
    with TestClient(app) as sync_client:
        a, b, _, room_id = _sync_make_room(sync_client, "011")
        events = sync_client.get(
            "/api/users/me/events", headers={"Authorization": f"Bearer {a['access_token']}"}
        )
        assert events.status_code == 200
        assert events.json()["data"][0]["type"] == "LETTER_SALVAGED"
        assert events.json()["data"][0]["room_id"] == room_id
        uploaded = sync_client.post(
            f"/api/chat/rooms/{room_id}/media",
            files={"file": ("tiny.png", b"\x89PNG\r\n\x1a\n" + b"demo-image", "image/png")},
            headers={"Authorization": f"Bearer {b['access_token']}"},
        )
        assert uploaded.status_code == 200, uploaded.text
        media = uploaded.json()["data"]
        assert media["kind"] == "image"
        assert media["url"].startswith("/api/media/")
        inferred = sync_client.post(
            f"/api/chat/rooms/{room_id}/media",
            files={"file": ("camera.jpg", b"\xff\xd8\xff" + b"camera-image", "application/octet-stream")},
            headers={"Authorization": f"Bearer {b['access_token']}"},
        )
        assert inferred.status_code == 200, inferred.text
        assert inferred.json()["data"]["kind"] == "image"

        with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, a)}") as ws_a:
            with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, b)}") as ws_b:
                for kind, content, media_url in [
                    ("emoji", "😊", None),
                    ("image", "", media["url"]),
                ]:
                    ws_b.send_json(
                        {"type": "message", "kind": kind, "content": content, "media_url": media_url}
                    )
                    received = ws_a.receive_json()
                    ack = ws_b.receive_json()
                    assert received["kind"] == kind
                    assert (received["media_url"] or "").split("?", 1)[0] == (media_url or "").split("?", 1)[0]
                    assert received["sender_name"]
                    assert received["created_at"]
                    assert ack["type"] == "ack"
        history = sync_client.get(
            f"/api/chat/rooms/{room_id}/messages",
            headers={"Authorization": f"Bearer {a['access_token']}"},
        )
        assert history.status_code == 200
        assert [item["kind"] for item in history.json()["data"][-2:]] == ["emoji", "image"]


def test_websocket_payload_does_not_expose_sender_id(setup_db_and_overrides):
    with TestClient(app) as sync_client:
        a, b, _, room_id = _sync_make_room(sync_client, "002")
        with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, a)}") as ws_a:
            with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, b)}") as ws_b:
                ws_b.send_json({"type": "message", "content": "匿名字段检查"})
                payload = ws_a.receive_json()
                assert "sender_id" not in payload
                assert "sender_name" in payload
                assert "sender_role" in payload


def test_websocket_non_member_cannot_connect(setup_db_and_overrides):
    with TestClient(app) as sync_client:
        a, b, _, room_id = _sync_make_room(sync_client, "003")
        c = _sync_register(sync_client, "15100000003")
        with pytest.raises(WebSocketDisconnect):
            with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, c)}"):
                pass


def test_websocket_muted_user_blocked(setup_db_and_overrides):
    with TestClient(app) as sync_client:
        a, b, _, room_id = _sync_make_room(sync_client, "004")
        admin = sync_client.post("/api/admin/login", json={"username": "admin", "password": "admin123"}).json()["data"]
        muted = sync_client.post(f"/api/admin/users/{b['user_id']}/mute", json={"minutes": 10, "reason": "测试"}, headers={"Authorization": f"Bearer {admin['access_token']}"})
        assert muted.status_code == 200
        with pytest.raises(WebSocketDisconnect):
            with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, b)}"):
                pass


def test_websocket_sensitive_message_blocked(setup_db_and_overrides):
    with TestClient(app) as sync_client:
        a, b, _, room_id = _sync_make_room(sync_client, "005")
        with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, b)}") as ws_b:
            ws_b.send_json({"type": "message", "content": "加微信 vx:abcdefg 详聊"})
            blocked = ws_b.receive_json()
            assert blocked["type"] == "blocked"
            assert blocked["error_code"] == "MESSAGE_BLOCKED"


def test_websocket_cannot_connect_after_room_destroyed(setup_db_and_overrides):
    with TestClient(app) as sync_client:
        a, b, _, room_id = _sync_make_room(sync_client, "006")
        exit_resp = sync_client.post(f"/api/chat/rooms/{room_id}/exit", headers={"Authorization": f"Bearer {b['access_token']}"})
        assert exit_resp.status_code == 200
        with pytest.raises(WebSocketDisconnect):
            with sync_client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(sync_client, a)}"):
                pass
