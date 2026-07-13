from pathlib import Path

import pytest

from app.core.config import Settings


@pytest.mark.asyncio
async def test_root_redirects_to_admin_without_legacy_landing_page(client):
    response = await client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/admin"


@pytest.mark.asyncio
async def test_admin_login_shell_is_available(client):
    response = await client.get("/admin")

    assert response.status_code == 200
    assert 'class="login-shell"' in response.text
    assert "管理员登录" in response.text
    assert "webapp.css?v=20260713-2" in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_admin_script_does_not_reload_on_unauthenticated_probe():
    script = Path("app/static/admin.js").read_text(encoding="utf-8")

    assert "location.reload()" not in script
    assert "showLogin(path === '/me'" in script


def test_production_can_explicitly_enable_community_automation():
    config = Settings(
        app_env="prod",
        debug=False,
        jwt_secret_key="a-production-jwt-secret-with-more-than-32-characters",
        server_salt="a-production-server-salt-with-more-than-32-characters",
        encryption_secret="a-production-encryption-key-with-more-than-32-characters",
        email_dev_code_enabled=False,
        phone_auto_registration_enabled=False,
        community_simulation_enabled=True,
    )

    assert config.community_simulation_enabled is True
