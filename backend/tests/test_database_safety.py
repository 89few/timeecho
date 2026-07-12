from __future__ import annotations

import pytest

from tests.database_safety import is_explicit_test_database_url


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:///:memory:",
        "sqlite+aiosqlite:///./timeecho_test.db",
        "postgresql+asyncpg://user:password@localhost/timeecho_test",
        "mysql+aiomysql://user:password@localhost/timeecho_test",
    ],
)
def test_accepts_unmistakable_test_databases(url: str):
    assert is_explicit_test_database_url(url)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "not-a-database-url",
        "sqlite+aiosqlite:///./timeecho.db",
        "postgresql+asyncpg://user:password@localhost/timeecho",
        "postgresql+asyncpg://user:password@localhost/timeecho_testing",
    ],
)
def test_rejects_development_or_ambiguous_databases(url: str | None):
    assert not is_explicit_test_database_url(url)
