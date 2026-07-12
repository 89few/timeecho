from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal, close_resources
from app.models.security import AdminRole
from app.services.admin_service import create_admin_account


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create a hashed TimeEcho administrator")
    parser.add_argument("username")
    parser.add_argument("--role", choices=[item.value for item in AdminRole], default="SUPER_ADMIN")
    args = parser.parse_args()
    password = getpass.getpass("New administrator password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    async with AsyncSessionLocal() as db:
        admin = await create_admin_account(db, args.username, password, AdminRole(args.role))
        print(f"Created administrator: {admin.username} ({admin.role.value})")
    await close_resources()


if __name__ == "__main__":
    asyncio.run(main())
