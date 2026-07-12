from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.crypto import encrypt_text
from app.core.security import utcnow
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.chat import AnonymousIdentity
from app.models.letter import Letter, LetterStatus, RiskLevel
from app.services.salvage_service import add_to_available_pools
from tests.conftest import register


def headers(data: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {data['access_token']}"}


def ws_ticket(client, user: dict) -> str:
    return client.post("/api/auth/ws-ticket", headers=headers(user)).json()["data"]["ticket"]


async def available_letter(fake_redis, author_id: int, content: str = "只属于这架纸飞机的匿名问候") -> int:
    async with AsyncSessionLocal() as db:
        letter = Letter(
            author_id=author_id,
            content_ciphertext=encrypt_text(content),
            emotion="平静",
            city="杭州",
            status=LetterStatus.AVAILABLE,
            seal_days=1,
            release_at=utcnow() - timedelta(minutes=1),
            risk_level=RiskLevel.NONE,
        )
        db.add(letter)
        await db.commit()
        await db.refresh(letter)
        await add_to_available_pools(fake_redis, letter)
        return letter.id


@pytest.mark.asyncio
async def test_paper_plane_identity_is_relationship_scoped_and_never_leaks_real_profile(
    client, setup_db_and_overrides
):
    author = await register(client, "13821000001")
    salvager = await register(client, "13821000002")
    letter_id = await available_letter(setup_db_and_overrides, author["user_id"])

    salvaged = await client.post(
        "/api/salvage",
        json={"emotion": "平静", "city": "杭州"},
        headers=headers(salvager),
    )
    assert salvaged.status_code == 200, salvaged.text
    data = salvaged.json()["data"]
    assert data["letter_id"] == letter_id
    assert "author_id" not in data and "author_username" not in data
    assert data["author_anonymous_name"].count("的") == 1
    assert data["author_anonymous_avatar_url"].startswith("/static/assets/avatars/")

    room_response = await client.post(
        f"/api/salvage/{letter_id}/reply", headers=headers(salvager)
    )
    room_id = room_response.json()["data"]["room_id"]
    room = await client.get(f"/api/chat/rooms/{room_id}", headers=headers(salvager))
    room_data = room.json()["data"]
    assert "peer_user_id" not in room_data
    assert "can_view_profile" not in room_data
    assert room_data["peer_display_name"] == data["author_anonymous_name"]

    detail = await client.get(f"/api/letters/{letter_id}", headers=headers(salvager))
    detail_data = detail.json()["data"]
    assert detail_data["author_anonymous_name"] == data["author_anonymous_name"]
    assert "author_id" not in detail_data and "profile_url" not in detail_data

    async with AsyncSessionLocal() as db:
        identities = list(
            (
                await db.execute(
                    __import__("sqlalchemy").select(AnonymousIdentity).where(
                        AnonymousIdentity.scope_type == "LETTER",
                        AnonymousIdentity.scope_id == letter_id,
                    )
                )
            ).scalars().all()
        )
        assert len(identities) == 2


@pytest.mark.asyncio
async def test_card_exchange_requires_both_consents_and_switches_atomically(
    client, setup_db_and_overrides
):
    author = await register(client, "13821000003")
    salvager = await register(client, "13821000004")
    outsider = await register(client, "13821000005")
    await client.put("/api/users/me", json={"username": "纸上青禾"}, headers=headers(author))
    await client.put("/api/users/me", json={"username": "半格月光"}, headers=headers(salvager))
    letter_id = await available_letter(setup_db_and_overrides, author["user_id"], "交换名片仍要双方同意")
    await client.post("/api/salvage", json={"emotion": "平静", "city": "杭州"}, headers=headers(salvager))
    reply = await client.post(f"/api/salvage/{letter_id}/reply", headers=headers(salvager))
    room_id = reply.json()["data"]["room_id"]

    forbidden = await client.post(f"/api/chat/rooms/{room_id}/card-exchange", headers=headers(outsider))
    assert forbidden.status_code == 403

    first = await client.post(f"/api/chat/rooms/{room_id}/card-exchange", headers=headers(salvager))
    assert first.status_code == 200
    assert first.json()["data"]["identity_revealed"] is False
    assert "peer_user_id" not in first.json()["data"]
    invitation = await client.get("/api/notifications", headers=headers(author))
    card_notice = next(
        item for item in invitation.json()["data"]["items"]
        if item["type"] == "CARD_EXCHANGE"
    )
    assert card_notice["actor"] is None
    assert card_notice["data"] == {"room_id": room_id}

    invited = await client.get(f"/api/chat/rooms/{room_id}", headers=headers(author))
    assert invited.json()["data"]["card_exchange_status"] == "INVITED"
    assert "peer_user_id" not in invited.json()["data"]

    second = await client.post(f"/api/chat/rooms/{room_id}/card-exchange", headers=headers(author))
    assert second.status_code == 200
    assert second.json()["data"]["identity_revealed"] is True
    assert second.json()["data"]["peer_user_id"] == salvager["user_id"]
    other_side = await client.get(f"/api/chat/rooms/{room_id}", headers=headers(salvager))
    assert other_side.json()["data"]["identity_revealed"] is True
    assert other_side.json()["data"]["peer_user_id"] == author["user_id"]


@pytest.mark.asyncio
async def test_matching_queue_single_active_room_cancel_and_no_rematch(client):
    alice = await register(client, "13821000006")
    bob = await register(client, "13821000007")
    carol = await register(client, "13821000008")
    payload_a = {"purpose": "VENT", "topic": "LIFE"}
    payload_b = {"purpose": "LISTEN", "topic": "LIFE"}

    waiting = await client.post("/api/matching/join", json=payload_a, headers=headers(alice))
    assert waiting.json()["data"]["status"] == "WAITING"
    matched = await client.post("/api/matching/join", json=payload_b, headers=headers(bob))
    assert matched.status_code == 200, matched.text
    assert matched.json()["data"]["status"] == "ACTIVE"
    room = matched.json()["data"]["room"]
    assert room["room_kind"] == "MATCH"
    assert "peer_user_id" not in room
    room_id = room["room_id"]

    alice_status = await client.get("/api/matching/status", headers=headers(alice))
    assert alice_status.json()["data"]["room"]["room_id"] == room_id
    duplicate = await client.post("/api/matching/join", json=payload_a, headers=headers(alice))
    assert duplicate.json()["data"]["room"]["room_id"] == room_id

    ended = await client.post(
        f"/api/matching/rooms/{room_id}/end",
        json={"action": "NO_REMATCH"},
        headers=headers(alice),
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["data"]["status"] == "IDLE"

    await client.post("/api/matching/join", json=payload_a, headers=headers(alice))
    bob_waiting = await client.post("/api/matching/join", json=payload_b, headers=headers(bob))
    assert bob_waiting.json()["data"]["status"] == "WAITING"
    carol_match = await client.post(
        "/api/matching/join",
        json={"purpose": "CASUAL", "topic": "STUDY"},
        headers=headers(carol),
    )
    assert carol_match.json()["data"]["status"] == "ACTIVE"
    assert carol_match.json()["data"]["room"]["room_id"] != room_id


@pytest.mark.asyncio
async def test_matching_wait_can_cancel_and_nonmember_cannot_read(client):
    alice = await register(client, "13821000009")
    bob = await register(client, "13821000010")
    await client.post(
        "/api/matching/join",
        json={"purpose": "CASUAL", "topic": "WORK"},
        headers=headers(alice),
    )
    cancelled = await client.post("/api/matching/cancel", headers=headers(alice))
    assert cancelled.json()["data"]["status"] == "IDLE"
    status = await client.get("/api/matching/status", headers=headers(alice))
    assert status.json()["data"]["status"] == "IDLE"
    missing = await client.get("/api/chat/rooms/99999/messages", headers=headers(bob))
    assert missing.status_code == 404


def test_match_websocket_uses_room_alias_and_blocks_media(setup_db_and_overrides):
    with TestClient(app) as client:
        def sync_user(phone: str) -> dict:
            client.post("/api/auth/send-code", json={"phone": phone})
            response = client.post("/api/auth/login", json={"phone": phone, "code": "123456", "city": "杭州"})
            return response.json()["data"]

        alice = sync_user("13821000011")
        bob = sync_user("13821000012")
        ha, hb = headers(alice), headers(bob)
        client.post("/api/matching/join", json={"purpose": "VENT", "topic": "LATE_NIGHT"}, headers=ha)
        matched = client.post("/api/matching/join", json={"purpose": "LISTEN", "topic": "LATE_NIGHT"}, headers=hb)
        room_id = matched.json()["data"]["room"]["room_id"]
        with client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(client, alice)}") as first:
            with client.websocket_connect(f"/ws/chat/{room_id}?ticket={ws_ticket(client, bob)}") as second:
                second.send_json({"type": "message", "kind": "text", "content": "今晚想聊一会儿"})
                message = first.receive_json()
                assert message["sender_name"].count("的") == 1
                assert "sender_id" not in message
                second.receive_json()
                second.send_json({"type": "message", "kind": "image", "media_url": "/static/uploads/a.png", "content": "[图片]"})
                error = second.receive_json()
                assert error["type"] == "error"
                assert "文字和表情" in error["message"]
