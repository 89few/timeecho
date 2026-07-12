from __future__ import annotations

from pathlib import Path

import pytest

from app.db.session import AsyncSessionLocal
from app.models.user import User
from tests.conftest import register


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def social_users(client) -> tuple[dict, dict, dict]:
    users = [
        await register(client, "15800000101"),
        await register(client, "15800000102"),
        await register(client, "15800000103"),
    ]
    async with AsyncSessionLocal() as db:
        for data, username in zip(users, ["alice_echo", "bob_echo", "carol_echo"]):
            user = await db.get(User, data["user_id"])
            user.username = username
            user.avatar_url = f"/static/assets/avatars/avatar-{user.id}.png"
        await db.commit()
    return users[0], users[1], users[2]


async def become_friends(client, requester: dict, addressee: dict) -> int:
    sent = await client.post(
        "/api/social/friends/requests",
        json={"target_user_id": addressee["user_id"], "message": "一起听见时间的回声"},
        headers=auth(requester["access_token"]),
    )
    assert sent.status_code == 200, sent.text
    request_id = sent.json()["data"]["id"]
    accepted = await client.post(
        f"/api/social/friends/requests/{request_id}/accept",
        headers=auth(addressee["access_token"]),
    )
    assert accepted.status_code == 200, accepted.text
    return request_id


@pytest.mark.asyncio
async def test_friend_remark_drives_friend_list_profile_and_chat_title(client):
    alice, bob, _ = await social_users(client)
    await become_friends(client, alice, bob)
    headers = auth(alice["access_token"])

    updated = await client.put(
        f"/api/social/friends/{bob['user_id']}/remark",
        json={"remark": "小林"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    friends = await client.get("/api/social/friends", headers=headers)
    friend = friends.json()["data"]["items"][0]
    assert friend["display_name"] == "小林"
    assert friend["remark"] == "小林"

    profile = await client.get(f"/api/users/{bob['user_id']}", headers=headers)
    assert profile.json()["data"]["display_name"] == "小林"
    room = await client.post(
        f"/api/chat/friends/{bob['user_id']}/room", headers=headers
    )
    room_id = room.json()["data"]["room_id"]
    status = await client.get(f"/api/chat/rooms/{room_id}", headers=headers)
    assert status.json()["data"]["peer_display_name"] == "小林"

    cleared = await client.put(
        f"/api/social/friends/{bob['user_id']}/remark",
        json={"remark": ""},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["remark"] is None


@pytest.mark.asyncio
async def test_profile_user_report_and_block(client):
    alice, bob, _ = await social_users(client)
    reported = await client.post(
        "/api/reports",
        json={
            "target_type": "USER",
            "target_id": bob["user_id"],
            "reason": "垃圾广告",
        },
        headers=auth(alice["access_token"]),
    )
    assert reported.status_code == 200, reported.text
    blocked = await client.post(
        f"/api/users/{bob['user_id']}/block",
        headers=auth(alice["access_token"]),
    )
    assert blocked.status_code == 200, blocked.text
    assert (
        await client.get(
            f"/api/users/{bob['user_id']}",
            headers=auth(alice["access_token"]),
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_social_endpoints_require_login(client):
    for path in ["/api/social/friends", "/api/social/friends/search?q=echo", "/api/social/posts"]:
        response = await client.get(path)
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_friend_request_accept_list_delete_and_request_again(client):
    alice, bob, _ = await social_users(client)
    found = await client.get(
        "/api/social/friends/search?q=bob",
        headers=auth(alice["access_token"]),
    )
    assert found.status_code == 200, found.text
    card = found.json()["data"]["items"][0]
    assert card["id"] == bob["user_id"]
    assert card["display_name"] == "bob_echo"
    assert card["relationship"] == "NONE"
    assert "email" not in card

    sent = await client.post(
        "/api/social/friends/requests",
        json={"target_user_id": bob["user_id"], "message": "你好"},
        headers=auth(alice["access_token"]),
    )
    assert sent.status_code == 200, sent.text
    request_id = sent.json()["data"]["id"]
    duplicate = await client.post(
        "/api/social/friends/requests",
        json={"target_user_id": bob["user_id"]},
        headers=auth(alice["access_token"]),
    )
    assert duplicate.status_code == 409
    reverse = await client.post(
        "/api/social/friends/requests",
        json={"target_user_id": alice["user_id"]},
        headers=auth(bob["access_token"]),
    )
    assert reverse.status_code == 409
    assert reverse.json()["error_code"] == "INCOMING_REQUEST_EXISTS"

    incoming = await client.get(
        "/api/social/friends/requests?box=incoming&status=PENDING",
        headers=auth(bob["access_token"]),
    )
    assert incoming.status_code == 200
    assert incoming.json()["data"]["items"][0]["user"]["id"] == alice["user_id"]
    forbidden = await client.post(
        f"/api/social/friends/requests/{request_id}/accept",
        headers=auth(alice["access_token"]),
    )
    assert forbidden.status_code == 404

    accepted = await client.post(
        f"/api/social/friends/requests/{request_id}/accept",
        headers=auth(bob["access_token"]),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "ACCEPTED"
    for user, peer_id in [(alice, bob["user_id"]), (bob, alice["user_id"])]:
        friends = await client.get("/api/social/friends", headers=auth(user["access_token"]))
        assert friends.status_code == 200
        assert friends.json()["data"]["items"][0]["id"] == peer_id
        assert friends.json()["data"]["items"][0]["is_friend"] is True

    removed = await client.delete(
        f"/api/social/friends/{bob['user_id']}", headers=auth(alice["access_token"])
    )
    assert removed.status_code == 200
    empty = await client.get("/api/social/friends", headers=auth(alice["access_token"]))
    assert empty.json()["data"]["items"] == []
    sent_again = await client.post(
        "/api/social/friends/requests",
        json={"target_user_id": alice["user_id"]},
        headers=auth(bob["access_token"]),
    )
    assert sent_again.status_code == 200, sent_again.text
    assert sent_again.json()["data"]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_reject_friend_request_cannot_be_reprocessed(client):
    alice, bob, _ = await social_users(client)
    sent = await client.post(
        "/api/social/friends/requests",
        json={"target_user_id": bob["user_id"]},
        headers=auth(alice["access_token"]),
    )
    request_id = sent.json()["data"]["id"]
    rejected = await client.post(
        f"/api/social/friends/requests/{request_id}/reject",
        headers=auth(bob["access_token"]),
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "REJECTED"
    repeated = await client.post(
        f"/api/social/friends/requests/{request_id}/accept",
        headers=auth(bob["access_token"]),
    )
    assert repeated.status_code == 409


@pytest.mark.asyncio
async def test_post_privacy_feed_likes_comments_and_soft_delete(client):
    alice, bob, carol = await social_users(client)

    friend_post = await client.post(
        "/api/social/posts",
        json={"text": "只给朋友看的雨声", "visibility": "FRIENDS"},
        headers=auth(bob["access_token"]),
    )
    public_post = await client.post(
        "/api/social/posts",
        json={"text": "所有人都能看见的晚霞", "visibility": "PUBLIC"},
        headers=auth(bob["access_token"]),
    )
    private_post = await client.post(
        "/api/social/posts",
        json={"text": "只留给自己的句子", "visibility": "PRIVATE"},
        headers=auth(bob["access_token"]),
    )
    assert friend_post.status_code == public_post.status_code == private_post.status_code == 200
    friend_id = friend_post.json()["data"]["id"]
    public_id = public_post.json()["data"]["id"]
    private_id = private_post.json()["data"]["id"]

    before = await client.get("/api/social/posts", headers=auth(alice["access_token"]))
    before_ids = {item["id"] for item in before.json()["data"]["items"]}
    assert public_id in before_ids
    assert friend_id not in before_ids
    assert private_id not in before_ids
    hidden_detail = await client.get(
        f"/api/social/posts/{private_id}", headers=auth(alice["access_token"])
    )
    assert hidden_detail.status_code == 404

    await become_friends(client, alice, bob)
    after = await client.get("/api/social/posts", headers=auth(alice["access_token"]))
    after_ids = {item["id"] for item in after.json()["data"]["items"]}
    assert friend_id in after_ids
    assert private_id not in after_ids

    liked = await client.post(
        f"/api/social/posts/{friend_id}/likes", headers=auth(alice["access_token"])
    )
    assert liked.status_code == 200
    assert liked.json()["data"] == {"post_id": friend_id, "liked": True, "like_count": 1}
    unliked = await client.post(
        f"/api/social/posts/{friend_id}/likes", headers=auth(alice["access_token"])
    )
    assert unliked.json()["data"]["liked"] is False
    assert unliked.json()["data"]["like_count"] == 0

    commented = await client.post(
        f"/api/social/posts/{friend_id}/comments",
        json={"text": "我也喜欢雨声"},
        headers=auth(alice["access_token"]),
    )
    assert commented.status_code == 200, commented.text
    comment_id = commented.json()["data"]["id"]
    comments = await client.get(
        f"/api/social/posts/{friend_id}/comments", headers=auth(bob["access_token"])
    )
    assert comments.status_code == 200
    assert comments.json()["data"]["items"][0]["text"] == "我也喜欢雨声"
    cannot_delete = await client.delete(
        f"/api/social/comments/{comment_id}", headers=auth(carol["access_token"])
    )
    assert cannot_delete.status_code == 403
    owner_delete_comment = await client.delete(
        f"/api/social/comments/{comment_id}", headers=auth(bob["access_token"])
    )
    assert owner_delete_comment.status_code == 200

    cannot_delete_post = await client.delete(
        f"/api/social/posts/{friend_id}", headers=auth(alice["access_token"])
    )
    assert cannot_delete_post.status_code == 403
    deleted = await client.delete(
        f"/api/social/posts/{friend_id}", headers=auth(bob["access_token"])
    )
    assert deleted.status_code == 200
    missing = await client.get(
        f"/api/social/posts/{friend_id}", headers=auth(bob["access_token"])
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_social_media_upload_and_multimedia_post(client):
    alice, _, _ = await social_users(client)
    bad = await client.post(
        "/api/social/media",
        files={"file": ("fake.png", b"this is not a png", "image/png")},
        headers=auth(alice["access_token"]),
    )
    assert bad.status_code == 422
    uploaded = await client.post(
        "/api/social/media",
        files={"file": ("tiny.png", b"\x89PNG\r\n\x1a\n" + b"test-payload", "image/png")},
        headers=auth(alice["access_token"]),
    )
    assert uploaded.status_code == 200, uploaded.text
    media = uploaded.json()["data"]
    assert media["kind"] == "image"
    assert media["url"].startswith("/api/media/")
    try:
        served = await client.get(media["url"])
        assert served.status_code == 200
        assert served.content.startswith(b"\x89PNG")
        assert "private" in served.headers["cache-control"]
        post = await client.post(
            "/api/social/posts",
            json={
                "text": "一张测试图片",
                "visibility": "PUBLIC",
                "media": [{"kind": "image", "url": media["url"], "width": 16, "height": 16}],
            },
            headers=auth(alice["access_token"]),
        )
        assert post.status_code == 200, post.text
        assert post.json()["data"]["media"][0]["url"].split("?", 1)[0] == media["url"].split("?", 1)[0]
        empty = await client.post(
            "/api/social/posts", json={}, headers=auth(alice["access_token"])
        )
        assert empty.status_code == 422
        external = await client.post(
            "/api/social/posts",
            json={"media": [{"kind": "image", "url": "https://example.com/tracker.png"}]},
            headers=auth(alice["access_token"]),
        )
        assert external.status_code == 422
    finally:
        pass
