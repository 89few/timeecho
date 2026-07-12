from __future__ import annotations

import re

import pytest

from tests.conftest import register


async def _admin_headers(client):
    response = await client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_uid_is_eight_digits_unique_immutable_and_admin_searchable(client):
    first = await register(client, "13800009001")
    second = await register(client, "13800009002")
    assert re.fullmatch(r"\d{8}", first["uid"])
    assert re.fullmatch(r"\d{8}", second["uid"])
    assert first["uid"] != second["uid"]

    headers = {"Authorization": f"Bearer {first['access_token']}"}
    me = await client.get("/api/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["uid"] == first["uid"]

    # UID is deliberately absent from the editable profile schema.
    update = await client.put(
        "/api/users/me",
        headers=headers,
        json={"uid": "11111111", "bio": "UID 不可编辑"},
    )
    assert update.status_code == 200
    after = await client.get("/api/users/me", headers=headers)
    assert after.json()["data"]["uid"] == first["uid"]

    admin = await _admin_headers(client)
    found = await client.get(f"/api/admin/users?q={first['uid']}", headers=admin)
    assert found.status_code == 200
    assert [item["uid"] for item in found.json()["data"]] == [first["uid"]]


@pytest.mark.asyncio
async def test_messages_overview_combines_three_message_tab_resources(client):
    account = await register(client, "13800009003")
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    response = await client.get("/api/overview/messages", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data) == {"rooms", "notifications", "friend_requests"}
    assert all(isinstance(data[key], list) for key in data)


@pytest.mark.asyncio
async def test_admin_can_apply_and_reverse_user_moderation(client):
    account = await register(client, "13800009004")
    admin = await _admin_headers(client)

    muted = await client.post(
        f"/api/admin/users/{account['user_id']}/mute",
        headers=admin,
        json={"minutes": 30, "reason": "后台权限回归"},
    )
    assert muted.status_code == 200
    assert muted.json()["data"]["status"] == "MUTED"

    restored = await client.post(
        f"/api/admin/users/{account['user_id']}/unmute", headers=admin
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "ACTIVE"

    banned = await client.post(
        f"/api/admin/users/{account['user_id']}/ban",
        headers=admin,
        json={"reason": "后台权限回归"},
    )
    assert banned.status_code == 200
    assert banned.json()["data"]["status"] == "BANNED"

    final_restore = await client.post(
        f"/api/admin/users/{account['user_id']}/unban", headers=admin
    )
    assert final_restore.json()["data"]["status"] == "ACTIVE"
