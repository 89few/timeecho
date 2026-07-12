from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, or_, select

from app.core.crypto import encrypt_text
from app.core.security import utcnow
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.chat import (
    AnonymousIdentity,
    ChatMessage,
    ChatRoom,
    ChatRoomKind,
    ChatRoomStatus,
    MatchParticipant,
    UserBlock,
)
from app.models.letter import Letter, LetterStatus, RiskLevel
from app.models.social import Friendship
from app.services.salvage_service import add_to_available_pools
from tests.conftest import register


def headers(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['access_token']}"}


def ws_ticket(client, user: dict) -> str:
    return client.post("/api/auth/ws-ticket", headers=headers(user)).json()["data"]["ticket"]


async def available_letter(redis, author_id: int, text: str = "一封不带身份线索的信") -> int:
    async with AsyncSessionLocal() as db:
        letter = Letter(
            author_id=author_id,
            content_ciphertext=encrypt_text(text),
            emotion="平静",
            city="不应返回的城市",
            status=LetterStatus.AVAILABLE,
            seal_days=1,
            release_at=utcnow() - timedelta(minutes=1),
            risk_level=RiskLevel.NONE,
        )
        db.add(letter)
        await db.commit()
        await db.refresh(letter)
        await add_to_available_pools(redis, letter)
        return letter.id


def assert_no_identity_leak(value) -> None:
    forbidden = {
        "city",
        "author_id",
        "sender_id",
        "user_id",
        "peer_user_id",
        "username",
        "real_name",
        "profile_url",
        "can_view_profile",
    }
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value.keys()), value
        for child in value.values():
            assert_no_identity_leak(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_identity_leak(child)


@pytest.mark.asyncio
async def test_anonymous_endpoints_remove_city_and_all_real_identity_fields(
    client, setup_db_and_overrides
):
    author = await register(client, "13831000001", city="北京")
    salvager = await register(client, "13831000002", city="上海")
    await client.put(
        "/api/users/me",
        json={"username": "真实作者", "avatar_url": "/static/assets/avatars/avatar-1.png"},
        headers=headers(author),
    )
    letter_id = await available_letter(setup_db_and_overrides, author["user_id"])
    salvage = await client.post(
        "/api/salvage", json={"emotion": "平静"}, headers=headers(salvager)
    )
    assert salvage.status_code == 200
    assert_no_identity_leak(salvage.json()["data"])
    reply = await client.post(
        f"/api/salvage/{letter_id}/reply", headers=headers(salvager)
    )
    room_id = reply.json()["data"]["room_id"]
    room = await client.get(f"/api/chat/rooms/{room_id}", headers=headers(salvager))
    assert_no_identity_leak(room.json()["data"])
    detail = await client.get(f"/api/letters/{letter_id}", headers=headers(salvager))
    assert_no_identity_leak(detail.json()["data"])
    one_sided = await client.post(
        f"/api/chat/rooms/{room_id}/card-exchange", headers=headers(salvager)
    )
    assert one_sided.json()["data"]["identity_revealed"] is False
    assert_no_identity_leak(one_sided.json()["data"])


@pytest.mark.asyncio
async def test_matching_join_is_atomic_under_real_concurrent_requests(client):
    users = [await register(client, f"1383100001{i}") for i in range(4)]
    gate = asyncio.Event()

    async def join(index: int):
        await gate.wait()
        return await client.post(
            "/api/matching/join",
            json={"purpose": "CASUAL", "topic": "LIFE"},
            headers=headers(users[index]),
        )

    tasks = [asyncio.create_task(join(index)) for index in range(4)]
    gate.set()
    responses = await asyncio.gather(*tasks)
    assert all(response.status_code == 200 for response in responses)

    async with AsyncSessionLocal() as db:
        rooms = list(
            (
                await db.execute(
                    select(ChatRoom).where(
                        ChatRoom.room_kind == ChatRoomKind.MATCH,
                        ChatRoom.status == ChatRoomStatus.ACTIVE,
                    )
                )
            ).scalars().all()
        )
        assert len(rooms) == 2
        participants = list(
            (await db.execute(select(MatchParticipant))).scalars().all()
        )
        counts: dict[int, int] = {}
        for participant in participants:
            counts[participant.user_id] = counts.get(participant.user_id, 0) + 1
        assert counts == {user["user_id"]: 1 for user in users}

    duplicate_gate = asyncio.Event()

    async def duplicate_join():
        await duplicate_gate.wait()
        return await client.post(
            "/api/matching/join",
            json={"purpose": "CASUAL", "topic": "LIFE"},
            headers=headers(users[0]),
        )

    duplicates = [asyncio.create_task(duplicate_join()) for _ in range(3)]
    duplicate_gate.set()
    duplicate_responses = await asyncio.gather(*duplicates)
    room_ids = {
        response.json()["data"]["room"]["room_id"]
        for response in duplicate_responses
    }
    assert len(room_ids) == 1


@pytest.mark.asyncio
async def test_global_block_stops_salvage_friend_social_and_profile_interactions(
    client, setup_db_and_overrides
):
    author = await register(client, "13831000021")
    other = await register(client, "13831000022")
    async with AsyncSessionLocal() as db:
        low, high = sorted((author["user_id"], other["user_id"]))
        db.add(Friendship(user_low_id=low, user_high_id=high, created_at=utcnow()))
        await db.commit()
    first_letter = await available_letter(setup_db_and_overrides, author["user_id"])
    await client.post("/api/salvage", json={"emotion": "平静"}, headers=headers(other))
    reply = await client.post(
        f"/api/salvage/{first_letter}/reply", headers=headers(other)
    )
    room_id = reply.json()["data"]["room_id"]
    blocked = await client.post(
        f"/api/chat/rooms/{room_id}/block", headers=headers(other)
    )
    assert blocked.status_code == 200
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count(UserBlock.id))) == 1
        assert await db.scalar(select(func.count(Friendship.id))) == 0

    second_letter = await available_letter(
        setup_db_and_overrides, author["user_id"], "这一封也不能再被对方打捞"
    )
    second_salvage = await client.post(
        "/api/salvage", json={"emotion": "平静"}, headers=headers(other)
    )
    assert second_salvage.json()["data"].get("letter_id") != second_letter

    for source, target in ((other, author), (author, other)):
        friend = await client.post(
            "/api/social/friends/requests",
            json={"target_user_id": target["user_id"]},
            headers=headers(source),
        )
        assert friend.status_code == 403
    profile = await client.get(
        f"/api/users/{author['user_id']}", headers=headers(other)
    )
    assert profile.status_code == 403

    post = await client.post(
        "/api/social/posts",
        json={"text": "公开动态", "visibility": "PUBLIC", "media": []},
        headers=headers(author),
    )
    post_id = post.json()["data"]["id"]
    like = await client.post(
        f"/api/social/posts/{post_id}/likes", headers=headers(other)
    )
    comment = await client.post(
        f"/api/social/posts/{post_id}/comments",
        json={"text": "不能互动"},
        headers=headers(other),
    )
    assert like.status_code == comment.status_code == 403


def test_http_and_websocket_message_retries_are_idempotent(setup_db_and_overrides):
    with TestClient(app) as client:
        def user(phone: str):
            client.post("/api/auth/send-code", json={"phone": phone})
            return client.post(
                "/api/auth/login", json={"phone": phone, "code": "123456"}
            ).json()["data"]

        first, second = user("13831000031"), user("13831000032")
        client.post(
            "/api/matching/join",
            json={"purpose": "VENT", "topic": "WORK"},
            headers=headers(first),
        )
        matched = client.post(
            "/api/matching/join",
            json={"purpose": "LISTEN", "topic": "WORK"},
            headers=headers(second),
        )
        room_id = matched.json()["data"]["room"]["room_id"]
        payload = {
            "client_message_id": "same-client-message",
            "kind": "text",
            "content": "只保存一次",
        }
        one = client.post(
            f"/api/chat/rooms/{room_id}/messages",
            json=payload,
            headers=headers(first),
        ).json()["data"]
        two = client.post(
            f"/api/chat/rooms/{room_id}/messages",
            json=payload,
            headers=headers(first),
        ).json()["data"]
        assert one["created"] is True and two["created"] is False
        assert one["message_id"] == two["message_id"]

        with client.websocket_connect(
            f"/ws/chat/{room_id}?ticket={ws_ticket(client, first)}"
        ) as ws:
            ws.send_json({"type": "message", **payload})
            ack = ws.receive_json()
            assert ack["type"] == "ack"
            assert ack["duplicate"] is True
            assert ack["message_id"] == one["message_id"]

        async def count_messages():
            async with AsyncSessionLocal() as db:
                return await db.scalar(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.room_id == room_id,
                        ChatMessage.client_message_id == "same-client-message",
                    )
                )

        assert asyncio.run(count_messages()) == 1


def test_room_end_notifies_peer_and_resets_both_match_states(setup_db_and_overrides):
    with TestClient(app) as client:
        def user(phone: str):
            client.post("/api/auth/send-code", json={"phone": phone})
            return client.post(
                "/api/auth/login", json={"phone": phone, "code": "123456"}
            ).json()["data"]

        first, second = user("13831000041"), user("13831000042")
        client.post(
            "/api/matching/join",
            json={"purpose": "VENT", "topic": "STUDY"},
            headers=headers(first),
        )
        matched = client.post(
            "/api/matching/join",
            json={"purpose": "LISTEN", "topic": "STUDY"},
            headers=headers(second),
        )
        room_id = matched.json()["data"]["room"]["room_id"]
        with client.websocket_connect(
            f"/ws/chat/{room_id}?ticket={ws_ticket(client, second)}"
        ) as peer:
            ended = client.post(
                f"/api/matching/rooms/{room_id}/end",
                json={"action": "END"},
                headers=headers(first),
            )
            assert ended.status_code == 200
            event = peer.receive_json()
            assert event["type"] == "room_ended"
            assert event["room_id"] == room_id
        for account in (first, second):
            status = client.get(
                "/api/matching/status", headers=headers(account)
            ).json()["data"]
            assert status["status"] == "IDLE"
            assert status["room"] is None


@pytest.mark.asyncio
async def test_anonymous_room_appearances_are_distinct(client):
    first = await register(client, "13831000051")
    second = await register(client, "13831000052")
    await client.post(
        "/api/matching/join",
        json={"purpose": "CASUAL", "topic": "INTEREST"},
        headers=headers(first),
    )
    matched = await client.post(
        "/api/matching/join",
        json={"purpose": "CASUAL", "topic": "INTEREST"},
        headers=headers(second),
    )
    room_id = matched.json()["data"]["room"]["room_id"]
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(AnonymousIdentity).where(
                        AnonymousIdentity.scope_type == "ROOM",
                        AnonymousIdentity.scope_id == room_id,
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 2
        assert len({(row.anonymous_name, row.avatar_url) for row in rows}) == 2
