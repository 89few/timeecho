from __future__ import annotations

import os
import tempfile
import uuid
import shutil
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.database_safety import is_explicit_test_database_url


# This guard must run before importing anything from ``app``.  In particular,
# Docker Compose injects the development DATABASE_URL into the API container;
# allowing Settings to inherit it would make the destructive reset fixture
# below drop the development tables.
_inherited_database_url = os.environ.get("DATABASE_URL")
if _inherited_database_url and not is_explicit_test_database_url(_inherited_database_url):
    raise pytest.UsageError(
        "Refusing to run destructive tests: DATABASE_URL is not an isolated "
        "SQLite database or a database whose name ends with '_test'."
    )

_explicit_test_database_url = os.environ.get("TEST_DATABASE_URL")
if _explicit_test_database_url and not is_explicit_test_database_url(_explicit_test_database_url):
    raise pytest.UsageError(
        "Refusing to run destructive tests: TEST_DATABASE_URL is not an "
        "isolated SQLite database or a database whose name ends with '_test'."
    )

_test_db_path: Path | None = None
if _explicit_test_database_url:
    _test_database_url = _explicit_test_database_url
elif _inherited_database_url:
    _test_database_url = _inherited_database_url
else:
    _test_db_path = Path(tempfile.gettempdir()) / f"timeecho_pytest_{uuid.uuid4().hex}.db"
    _test_database_url = f"sqlite+aiosqlite:///{_test_db_path.as_posix()}"

# Never use setdefault here.  Test settings are authoritative and must win over
# values loaded from backend/.env or inherited from a developer shell.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = _test_database_url
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/15"
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["SERVER_SALT"] = "test-salt"
os.environ["ENCRYPTION_SECRET"] = "test-encryption-secret"
os.environ["TIMEECHO_DEBUG"] = "false"
os.environ["DEV_SMS_CODE"] = "123456"
os.environ["PHONE_AUTO_REGISTRATION_ENABLED"] = "true"
os.environ["EMAIL_VERIFICATION_REQUIRED"] = "false"
os.environ["EMAIL_ALLOW_UNVERIFIED_REGISTRATION"] = "true"
os.environ["EMAIL_DEV_CODE_ENABLED"] = "true"
os.environ["DEV_EMAIL_CODE"] = "123456"
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["SMTP_FROM_EMAIL"] = ""
os.environ["RATE_LIMITS_ENABLED"] = "true"

from app.main import app
from app.core.dependencies import get_db, get_redis
from app.db.session import AsyncSessionLocal, engine
from app.models import Base
from app.models.user import User
from app.models.security import AdminRole, AdminUser
from app.services.auth_service import hash_password
from app.core.security import utcnow
from app.core.crypto import phone_hash
from sqlalchemy import select
from tests.fake_redis import FakeAsyncRedis


@pytest_asyncio.fixture(autouse=True)
async def setup_db_and_overrides(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    shutil.rmtree(Path("private_uploads"), ignore_errors=True)
    async with AsyncSessionLocal() as session:
        now = utcnow()
        session.add(
            AdminUser(
                username="admin",
                password_hash=hash_password("admin123"),
                role=AdminRole.SUPER_ADMIN,
                enabled=True,
                failed_attempts=0,
                password_changed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    fake_redis = FakeAsyncRedis(decode_responses=True)
    import app.db.session as session_module
    import app.main as main_module
    monkeypatch.setattr(session_module, "redis_client", fake_redis)
    monkeypatch.setattr(main_module, "redis_client", fake_redis)

    async def override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    yield fake_redis
    await fake_redis.flushall()
    await fake_redis.aclose()
    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    shutil.rmtree(Path("private_uploads"), ignore_errors=True)


def pytest_sessionfinish(session, exitstatus):
    """Remove the process-private SQLite file after the test session."""

    if _test_db_path is None:
        return
    try:
        _test_db_path.unlink(missing_ok=True)
    except PermissionError:
        # On Windows a late aiosqlite finalizer can briefly retain the handle.
        # The uniquely named file lives in the OS temp directory, never in the
        # project or development database.
        pass


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register(client: AsyncClient, phone: str, city: str = "东京") -> dict:
    await client.post("/api/auth/send-code", json={"phone": phone})
    resp = await client.post("/api/auth/login", json={"phone": phone, "code": "123456", "city": city})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # Internal IDs are test-fixture data, not part of the public login API.
    async with AsyncSessionLocal() as session:
        user_id = (
            await session.execute(select(User.id).where(User.phone_hash == phone_hash(phone)))
        ).scalar_one()
    return {**data, "user_id": user_id}
