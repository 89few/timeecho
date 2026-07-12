from __future__ import annotations

import pytest


async def _admin_headers(client):
    response = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


async def _create_admin_user(client, headers, suffix: str):
    response = await client.post(
        "/api/admin/users",
        headers=headers,
        json={
            "email": f"admin-created-{suffix}@example.com",
            "username": f"managed_{suffix}",
            "password": "Managed123",
            "city": "上海",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_admin_user_social_and_friend_crud(client):
    admin = await _admin_headers(client)
    first = await _create_admin_user(client, admin, "one")
    second = await _create_admin_user(client, admin, "two")

    updated = await client.put(
        f"/api/admin/users/{first['id']}",
        headers=admin,
        json={"bio": "由管理员维护的简介", "city": "杭州", "status": "ACTIVE"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["bio"] == "由管理员维护的简介"

    login_a = await client.post(
        "/api/auth/email/login",
        json={"identifier": first["email"], "password": "Managed123"},
    )
    login_b = await client.post(
        "/api/auth/email/login",
        json={"identifier": second["email"], "password": "Managed123"},
    )
    assert login_a.status_code == login_b.status_code == 200
    headers_a = {"Authorization": f"Bearer {login_a.json()['data']['access_token']}"}
    headers_b = {"Authorization": f"Bearer {login_b.json()['data']['access_token']}"}
    assert (await client.post("/api/auth/password/change", headers=headers_a, json={"current_password": "Managed123", "new_password": "Changed123"})).status_code == 200
    assert (await client.post("/api/auth/password/change", headers=headers_b, json={"current_password": "Managed123", "new_password": "Changed123"})).status_code == 200
    login_a = await client.post("/api/auth/email/login", json={"identifier": first["email"], "password": "Changed123"})
    login_b = await client.post("/api/auth/email/login", json={"identifier": second["email"], "password": "Changed123"})
    headers_a = {"Authorization": f"Bearer {login_a.json()['data']['access_token']}"}
    headers_b = {"Authorization": f"Bearer {login_b.json()['data']['access_token']}"}

    request = await client.post(
        "/api/social/friends/requests",
        headers=headers_a,
        json={"target_user_id": second["id"], "message": "一起听回声"},
    )
    assert request.status_code == 200, request.text
    accepted = await client.post(
        f"/api/social/friends/requests/{request.json()['data']['id']}/accept",
        headers=headers_b,
    )
    assert accepted.status_code == 200, accepted.text

    post = await client.post(
        "/api/social/posts",
        headers=headers_a,
        json={"text": "管理员端到端动态测试", "visibility": "PUBLIC", "media": []},
    )
    assert post.status_code == 200, post.text
    post_id = post.json()["data"]["id"]
    comment = await client.post(
        f"/api/social/posts/{post_id}/comments",
        headers=headers_b,
        json={"text": "评论管理测试"},
    )
    assert comment.status_code == 200, comment.text
    comment_id = comment.json()["data"]["id"]

    posts = await client.get("/api/admin/social/posts", headers=admin)
    comments = await client.get("/api/admin/social/comments", headers=admin)
    friends = await client.get("/api/admin/social/friends", headers=admin)
    assert any(item["id"] == post_id for item in posts.json()["data"])
    assert any(item["id"] == comment_id for item in comments.json()["data"])
    friendship_id = friends.json()["data"]["friendships"][0]["id"]

    assert (await client.delete(f"/api/admin/social/comments/{comment_id}", headers=admin)).status_code == 200
    assert (await client.delete(f"/api/admin/social/posts/{post_id}", headers=admin)).status_code == 200
    assert (await client.delete(f"/api/admin/social/friends/{friendship_id}", headers=admin)).status_code == 200
    deactivated = await client.delete(f"/api/admin/users/{first['id']}", headers=admin)
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["status"] == "DEACTIVATED"
