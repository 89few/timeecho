from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import register


def ws_ticket(client, user: dict) -> str:
    response = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {user['access_token']}"})
    return response.json()["data"]["ticket"]


def _headers(data: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.mark.asyncio
async def test_new_post_is_public_and_user_profile_is_openable(client):
    alice = await register(client, "13910000001")
    bob = await register(client, "13910000002")
    await client.put(
        "/api/users/me",
        json={"username": "alice"},
        headers=_headers(alice),
    )
    created = await client.post(
        "/api/social/posts",
        json={"text": "所有人都应该看到这条动态", "media": []},
        headers=_headers(alice),
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["visibility"] == "PUBLIC"

    feed = await client.get("/api/social/posts", headers=_headers(bob))
    assert feed.status_code == 200
    assert any(
        item["text"] == "所有人都应该看到这条动态"
        for item in feed.json()["data"]["items"]
    )

    profile = await client.get(
        f"/api/users/{alice['user_id']}", headers=_headers(bob)
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["data"]["display_name"] == "alice"
    assert profile.json()["data"]["post_count"] == 1
    assert profile.json()["data"]["relationship"] == "NONE"


@pytest.mark.asyncio
async def test_friend_request_notifications_pending_filter_and_direct_room(client):
    alice = await register(client, "13910000003")
    bob = await register(client, "13910000004")
    await client.put(
        "/api/users/me", json={"username": "alice2"}, headers=_headers(alice)
    )
    await client.put(
        "/api/users/me", json={"username": "bob2"}, headers=_headers(bob)
    )

    request = await client.post(
        "/api/social/friends/requests",
        json={"target_user_id": bob["user_id"], "message": "你好"},
        headers=_headers(alice),
    )
    assert request.status_code == 200, request.text
    request_id = request.json()["data"]["id"]

    incoming = await client.get(
        "/api/social/friends/requests", headers=_headers(bob)
    )
    assert [item["id"] for item in incoming.json()["data"]["items"]] == [
        request_id
    ]
    unread = await client.get(
        "/api/notifications/unread-count", headers=_headers(bob)
    )
    assert unread.json()["data"]["count"] == 1

    accepted = await client.post(
        f"/api/social/friends/requests/{request_id}/accept",
        headers=_headers(bob),
    )
    assert accepted.status_code == 200, accepted.text

    # 默认接口只返回 PENDING，已经通过的记录不会再残留在“新的朋友”。
    incoming_after = await client.get(
        "/api/social/friends/requests", headers=_headers(bob)
    )
    assert incoming_after.json()["data"]["items"] == []
    bob_unread_after = await client.get(
        "/api/notifications/unread-count", headers=_headers(bob)
    )
    assert bob_unread_after.json()["data"]["count"] == 0

    alice_notifications = await client.get(
        "/api/notifications", headers=_headers(alice)
    )
    assert any(
        item["type"] == "FRIEND_ACCEPTED"
        for item in alice_notifications.json()["data"]["items"]
    )

    room = await client.post(
        f"/api/chat/friends/{bob['user_id']}/room", headers=_headers(alice)
    )
    assert room.status_code == 200, room.text
    room_data = room.json()["data"]
    assert room_data["room_kind"] == "FRIEND"
    assert room_data["letter_id"] is None
    assert room_data["expired_at"] is None

    same_room = await client.post(
        f"/api/chat/friends/{alice['user_id']}/room", headers=_headers(bob)
    )
    assert same_room.json()["data"]["room_id"] == room_data["room_id"]


@pytest.mark.asyncio
async def test_custom_avatar_upload(client):
    user = await register(client, "13910000005")
    upload = await client.post(
        "/api/users/me/avatar",
        files={
            "file": (
                "avatar.png",
                b"\x89PNG\r\n\x1a\n" + b"timeecho-avatar",
                "image/png",
            )
        },
        headers=_headers(user),
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["data"]["avatar_url"].startswith(
        "/static/uploads/avatar-"
    )


def _sync_register(client: TestClient, phone: str, username: str) -> dict:
    client.post("/api/auth/send-code", json={"phone": phone})
    response = client.post(
        "/api/auth/login",
        json={"phone": phone, "code": "123456", "city": "东京"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    update = client.put(
        "/api/users/me",
        json={"username": username},
        headers=_headers(data),
    )
    assert update.status_code == 200, update.text
    # Search supplies the internal public user ID without changing /users/me privacy.
    return data


def test_friend_direct_message_websocket(setup_db_and_overrides):
    with TestClient(app) as client:
        alice = _sync_register(client, "13910000006", "alicews")
        bob = _sync_register(client, "13910000007", "bobws")
        bob_search = client.get(
            "/api/social/friends/search",
            params={"q": "bobws"},
            headers=_headers(alice),
        )
        bob_id = bob_search.json()["data"]["items"][0]["id"]
        alice_search = client.get(
            "/api/social/friends/search",
            params={"q": "alicews"},
            headers=_headers(bob),
        )
        alice_id = alice_search.json()["data"]["items"][0]["id"]

        friend_request = client.post(
            "/api/social/friends/requests",
            json={"target_user_id": bob_id},
            headers=_headers(alice),
        )
        request_id = friend_request.json()["data"]["id"]
        accepted = client.post(
            f"/api/social/friends/requests/{request_id}/accept",
            headers=_headers(bob),
        )
        assert accepted.status_code == 200, accepted.text

        room = client.post(
            f"/api/chat/friends/{bob_id}/room", headers=_headers(alice)
        )
        assert room.status_code == 200, room.text
        room_id = room.json()["data"]["room_id"]

        with client.websocket_connect(
            f"/ws/chat/{room_id}?ticket={ws_ticket(client, alice)}"
        ) as ws_alice:
            with client.websocket_connect(
                f"/ws/chat/{room_id}?ticket={ws_ticket(client, bob)}"
            ) as ws_bob:
                ws_bob.send_json({"type": "message", "content": "好友私信已打通"})
                received = ws_alice.receive_json()
                ack = ws_bob.receive_json()
                assert received["content"] == "好友私信已打通"
                assert received["sender_name"] == "bobws"
                assert "sender_id" not in received
                assert ack["type"] == "ack"

        profile = client.get(
            f"/api/users/{alice_id}", headers=_headers(bob)
        )
        assert profile.json()["data"]["can_message"] is True
