from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal, close_resources
from app.models.security import AdminRole, AdminUser
from app.services.admin_service import create_admin_account


def _legacy_credentials() -> tuple[str, str] | None:
    path = Path(".env")
    if not path.is_file():
        return None
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw and not raw.lstrip().startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            if key.strip() in {"ADMIN_USERNAME", "ADMIN_PASSWORD"}:
                values[key.strip()] = value.strip()
    username, password = values.get("ADMIN_USERNAME"), values.get("ADMIN_PASSWORD")
    return (username, password) if username and password else None


async def main() -> None:
    async with AsyncSessionLocal() as db:
        if int(await db.scalar(select(func.count(AdminUser.id))) or 0):
            print("Administrator table already initialized")
            return
        credentials = _legacy_credentials()
        if not credentials:
            raise SystemExit("No legacy credentials found; run scripts/create_admin.py interactively")
        admin = await create_admin_account(db, credentials[0], credentials[1], AdminRole.SUPER_ADMIN)
        print(f"Migrated administrator: {admin.username}; remove legacy ADMIN_PASSWORD from .env")
    await close_resources()


if __name__ == "__main__":
    asyncio.run(main())
