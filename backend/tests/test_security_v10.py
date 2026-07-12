from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.security import AdminAuditLog, AdminRole, AdminUser, UserSession
from app.services.auth_service import verify_password
from tests.conftest import register


def auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['access_token']}"}


@pytest.mark.asyncio
async def test_admin_password_is_hashed_cookie_session_revokes_and_audits(client):
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(AdminUser).where(AdminUser.username == "admin"))
        assert admin.password_hash != "admin123"
        assert verify_password("admin123", admin.password_hash)

    login = await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    assert client.cookies.get("te_admin_session")
    assert (await client.get("/api/admin/me")).status_code == 200

    user = await register(client, "13800101001")
    muted = await client.post(f"/api/admin/users/{user['user_id']}/mute", json={"minutes": 5, "reason": "审计测试"})
    assert muted.status_code == 200
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(AdminAuditLog.id).where(AdminAuditLog.action.like("POST%/mute")))

    assert (await client.post("/api/admin/logout")).status_code == 200
    assert (await client.get("/api/admin/me")).status_code == 401


@pytest.mark.asyncio
async def test_admin_lockout_and_rbac(client):
    for _ in range(5):
        response = await client.post("/api/admin/login", json={"username": "admin", "password": "wrong-password"})
        assert response.status_code == 401
    assert (await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})).status_code == 401


@pytest.mark.asyncio
async def test_auditor_can_read_but_cannot_mutate(client):
    assert (await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})).status_code == 200
    created = await client.post(
        "/api/admin/admins",
        json={"username": "audit_only", "password": "AuditOnly123", "role": "AUDITOR"},
    )
    assert created.status_code == 200
    assert (await client.post("/api/admin/logout")).status_code == 200
    assert (await client.post(
        "/api/admin/login", json={"username": "audit_only", "password": "AuditOnly123"}
    )).status_code == 200
    assert (await client.get("/api/admin/users")).status_code == 200
    assert (await client.post(
        "/api/admin/sensitive-words",
        json={"word": "audit-forbidden", "category": "test", "level": "LOW"},
    )).status_code == 403


@pytest.mark.asyncio
async def test_user_status_transitions_do_not_overwrite_ban(client):
    user = await register(client, "13800101009")
    assert (await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})).status_code == 200
    assert (await client.post(
        f"/api/admin/users/{user['user_id']}/ban", json={"reason": "transition-test"}
    )).status_code == 200
    assert (await client.post(
        f"/api/admin/users/{user['user_id']}/mute", json={"minutes": 5, "reason": "must-fail"}
    )).status_code == 409
    assert (await client.post(f"/api/admin/users/{user['user_id']}/activate")).status_code == 409
    assert (await client.post(f"/api/admin/users/{user['user_id']}/unban")).status_code == 200


@pytest.mark.asyncio
async def test_refresh_rotation_logout_and_ban_revoke_user_sessions(client):
    user = await register(client, "13800101002")
    first_refresh = user["refresh_token"]
    rotated = await client.post("/api/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    assert (await client.post("/api/auth/refresh", json={"refresh_token": first_refresh})).status_code == 401
    new_tokens = rotated.json()["data"]
    assert (await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})).status_code == 200
    assert (await client.get("/api/users/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})).status_code == 401

    again = await register(client, "13800101003")
    await client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    assert (await client.post(f"/api/admin/users/{again['user_id']}/ban", json={"reason": "安全测试"})).status_code == 200
    assert (await client.get("/api/users/me", headers=auth(again))).status_code == 401


@pytest.mark.asyncio
async def test_private_media_requires_valid_short_lived_signature(client):
    user = await register(client, "13800101004")
    upload = await client.post(
        "/api/social/media",
        files={"file": ("tiny.png", b"\x89PNG\r\n\x1a\nprivate", "image/png")},
        headers=auth(user),
    )
    assert upload.status_code == 200
    signed_url = upload.json()["data"]["url"]
    raw_url = signed_url.split("?", 1)[0]
    assert (await client.get(raw_url)).status_code == 404
    assert (await client.get(signed_url)).status_code == 200
    assert (await client.get(signed_url.replace("sig=", "sig=x"))).status_code == 404


def test_websocket_rejects_jwt_query_and_ticket_is_one_time(setup_db_and_overrides):
    with TestClient(app) as client:
        user = client.post("/api/auth/send-code", json={"phone": "13800101005"})
        assert user.status_code == 200
        login = client.post("/api/auth/login", json={"phone": "13800101005", "code": "123456"}).json()["data"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/matching?token={login['access_token']}"):
                pass
        ticket = client.post("/api/auth/ws-ticket", headers=auth(login)).json()["data"]["ticket"]
        with client.websocket_connect(f"/ws/matching?ticket={ticket}") as websocket:
            assert websocket.receive_json()["type"] == "ready"
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/matching?ticket={ticket}"):
                pass


def test_insecure_production_configuration_refuses_startup():
    with pytest.raises(ValueError):
        Settings(app_env="prod")
