"""
Seed script: creates the initial admin account.

Usage (from the backend/ directory):
    python seed.py

Reads SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD from .env.
Safe to run multiple times — skips creation if the admin already exists.
"""
import asyncio
import sys

from sqlalchemy import select

from backend.config import settings
from backend.database import AsyncSessionLocal, engine
from backend.models import User, UserRole
from backend.services.auth_service import hash_password


async def seed() -> None:
    if not settings.seed_admin_email or not settings.seed_admin_password:
        print(
            "ERROR: SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD must be set in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    email = settings.seed_admin_email.strip().lower()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            print(f"Admin '{email}' already exists — skipping.")
            return

        admin = User(
            email=email,
            password_hash=hash_password(settings.seed_admin_password),
            role=UserRole.admin,
        )
        session.add(admin)
        await session.commit()
        print(f"Admin account created: {email}")


if __name__ == "__main__":
    asyncio.run(seed())
