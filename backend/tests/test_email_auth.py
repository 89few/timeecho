from __future__ import annotations

import re
import time

import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_email_registration_and_login_by_email_or_generated_username(client):
    response = await client.post(
        "/api/auth/email/register",
        json={"email": "First.User@Example.com", "password": "echoPass123", "city": "上海"},
    )
    assert response.status_code == 200, response.text
    account = response.json()["data"]
    assert account["email"] == "first.user@example.com"
    assert re.fullmatch(r"echo_[0-9a-f]{8}", account["username"])
    assert account["email_verified"] is False
    assert account["avatar_url"].startswith("/static/assets/avatars/avatar-")
    assert account["access_token"]
    assert account["refresh_token"]

    by_email = await client.post(
        "/api/auth/email/login",
        json={"identifier": "FIRST.USER@EXAMPLE.COM", "password": "echoPass123"},
    )
    assert by_email.status_code == 200, by_email.text
    assert by_email.json()["data"]["user_id"] == account["user_id"]

    by_username = await client.post(
        "/api/auth/email/login",
        json={"identifier": account["username"].upper(), "password": "echoPass123"},
    )
    assert by_username.status_code == 200, by_username.text
    token = by_username.json()["data"]["access_token"]
    me = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["phone_masked"] is None
    assert me.json()["data"]["email"] == "first.user@example.com"


@pytest.mark.asyncio
async def test_verified_registration_and_duplicate_constraints(client, monkeypatch):
    monkeypatch.setattr(settings, "email_verification_required", True)
    monkeypatch.setattr(settings, "email_allow_unverified_registration", False)

    missing = await client.post(
        "/api/auth/email/register",
        json={"email": "verified@example.com", "password": "Secure123"},
    )
    assert missing.status_code == 400
    assert missing.json()["error_code"] == "EMAIL_CODE_REQUIRED"

    sent = await client.post(
        "/api/auth/email/send-code",
        json={"email": "verified@example.com", "purpose": "register"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["data"]["dev_code"] == "123456"

    registered = await client.post(
        "/api/auth/email/register",
        json={
            "email": "verified@example.com",
            "password": "Secure123",
            "code": "123456",
            "username": "TimeEcho_User",
        },
    )
    assert registered.status_code == 200, registered.text
    assert registered.json()["data"]["email_verified"] is True
    assert registered.json()["data"]["username"] == "timeecho_user"

    duplicate_email = await client.post(
        "/api/auth/email/register",
        json={
            "email": "VERIFIED@example.com",
            "password": "Secure123",
            "code": "123456",
        },
    )
    assert duplicate_email.status_code == 409
    assert duplicate_email.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"

    duplicate_code = await client.post(
        "/api/auth/email/send-code",
        json={"email": "verified@example.com", "purpose": "register"},
    )
    assert duplicate_code.status_code == 409
    assert duplicate_code.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_password_policy_and_unique_username(client):
    no_number = await client.post(
        "/api/auth/email/register",
        json={"email": "weak1@example.com", "password": "onlyletters"},
    )
    assert no_number.status_code == 400
    assert no_number.json()["error_code"] == "WEAK_PASSWORD"

    no_letter = await client.post(
        "/api/auth/email/register",
        json={"email": "weak2@example.com", "password": "12345678"},
    )
    assert no_letter.status_code == 400
    assert no_letter.json()["error_code"] == "WEAK_PASSWORD"

    created = await client.post(
        "/api/auth/email/register",
        json={"email": "one@example.com", "password": "Strong123", "username": "shared_name"},
    )
    assert created.status_code == 200, created.text
    taken = await client.post(
        "/api/auth/email/register",
        json={"email": "two@example.com", "password": "Strong123", "username": "SHARED_NAME"},
    )
    assert taken.status_code == 409
    assert taken.json()["error_code"] == "USERNAME_TAKEN"


@pytest.mark.asyncio
async def test_forgot_and_reset_password(client):
    created = await client.post(
        "/api/auth/email/register",
        json={"email": "reset@example.com", "password": "Before123"},
    )
    assert created.status_code == 200, created.text

    forgot = await client.post("/api/auth/password/forgot", json={"email": "reset@example.com"})
    assert forgot.status_code == 200, forgot.text
    assert forgot.json()["data"]["dev_code"] == "123456"

    invalid = await client.post(
        "/api/auth/password/reset",
        json={"email": "reset@example.com", "code": "000000", "new_password": "After456"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error_code"] == "INVALID_CODE"

    reset = await client.post(
        "/api/auth/password/reset",
        json={"email": "reset@example.com", "code": "123456", "new_password": "After456"},
    )
    assert reset.status_code == 200, reset.text

    old_login = await client.post(
        "/api/auth/email/login",
        json={"identifier": "reset@example.com", "password": "Before123"},
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/auth/email/login",
        json={"identifier": "reset@example.com", "password": "After456"},
    )
    assert new_login.status_code == 200, new_login.text

    unknown_forgot = await client.post(
        "/api/auth/password/forgot",
        json={"email": "not-registered@example.com"},
    )
    assert unknown_forgot.status_code == 404
    assert unknown_forgot.json()["error_code"] == "ACCOUNT_NOT_FOUND"

    unknown_reset_code = await client.post(
        "/api/auth/email/send-code",
        json={"email": "not-registered@example.com", "purpose": "reset"},
    )
    assert unknown_reset_code.status_code == 404
    assert unknown_reset_code.json()["error_code"] == "ACCOUNT_NOT_FOUND"


@pytest.mark.asyncio
async def test_email_delivery_requires_smtp_outside_development(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "email_dev_code_enabled", False)
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from_email", None)

    created = await client.post(
        "/api/auth/email/register",
        json={"email": "someone@example.com", "password": "Secure123"},
    )
    assert created.status_code == 200, created.text
    response = await client.post(
        "/api/auth/email/send-code",
        json={"email": "someone@example.com", "purpose": "reset"},
    )
    assert response.status_code == 503
    assert response.json()["error_code"] == "EMAIL_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_update_profile_username_and_avatar_validation(client):
    created = await client.post(
        "/api/auth/email/register",
        json={"email": "profile@example.com", "password": "Profile123", "username": "profile_old"},
    )
    assert created.status_code == 200, created.text
    token = created.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    updated = await client.put(
        "/api/users/me",
        headers=headers,
        json={
            "username": "回声_01",
            "emotion": "平静",
            "avatar_url": "/static/assets/avatars/avatar-6.png",
        },
    )
    assert updated.status_code == 200, updated.text
    profile = updated.json()["data"]
    assert profile["username"] == "回声_01"
    assert "city" not in profile
    assert profile["avatar_url"] == "/static/assets/avatars/avatar-6.png"

    invalid_avatar = await client.put(
        "/api/users/me",
        headers=headers,
        json={"avatar_url": "https://untrusted.example/avatar.png"},
    )
    assert invalid_avatar.status_code == 400
    assert invalid_avatar.json()["error_code"] == "INVALID_AVATAR"


@pytest.mark.asyncio
async def test_production_smtp_uses_random_expiring_one_time_code(client, setup_db_and_overrides, monkeypatch):
    import app.services.auth_service as auth_service

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "email_dev_code_enabled", False)
    monkeypatch.setattr(settings, "email_verification_required", True)
    monkeypatch.setattr(settings, "email_allow_unverified_registration", False)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from_email", "official@example.com")

    delivered: list[tuple] = []

    async def fake_to_thread(function, *args):
        delivered.append(args)

    monkeypatch.setattr(auth_service.asyncio, "to_thread", fake_to_thread)
    sent = await client.post(
        "/api/auth/email/send-code",
        json={"email": "new-user@example.com", "purpose": "register"},
    )
    assert sent.status_code == 200, sent.text
    assert "dev_code" not in sent.json()["data"]
    assert delivered and delivered[0][0] == "new-user@example.com"
    code = delivered[0][1]
    assert re.fullmatch(r"\d{6}", code)

    code_keys = await setup_db_and_overrides.keys("auth:email_code:register:*")
    assert len(code_keys) == 1
    remaining = setup_db_and_overrides.expires[code_keys[0]] - time.time()
    assert 590 <= remaining <= 600

    registered = await client.post(
        "/api/auth/email/register",
        json={
            "email": "new-user@example.com",
            "username": "new_user",
            "password": "Secure123",
            "code": code,
        },
    )
    assert registered.status_code == 200, registered.text
    assert registered.json()["data"]["email_verified"] is True
    assert await setup_db_and_overrides.get(code_keys[0]) is None
