from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def is_explicit_test_database_url(value: str | None) -> bool:
    """Return whether *value* is unmistakably safe for destructive tests.

    PostgreSQL/MySQL-style databases must have a database name ending in
    ``_test``.  SQLite files must have ``test`` in the filename; an in-memory
    SQLite database is also safe.  The function intentionally errs on the side
    of refusing a run because the test suite recreates every table.
    """

    if not value or not value.strip():
        return False

    try:
        url = make_url(value.strip())
    except ArgumentError:
        return False

    backend = url.get_backend_name().lower()
    database = (url.database or "").strip()

    if backend == "sqlite":
        if database in {"", ":memory:"}:
            return True
        return "test" in Path(database).name.lower()

    return bool(database) and database.lower().endswith("_test")
