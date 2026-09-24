from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

import asyncio
import logging
import uuid

engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


_db_initialized = False
_init_lock = asyncio.Lock()
SEED_ADMIN_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def init_db():
    global _db_initialized
    if _db_initialized:
        return
    async with _init_lock:
        if _db_initialized:
            return
        try:
            from sqlalchemy import select
            import backend.models  # Ensure all models are registered on Base.metadata
            from backend.models.user import User, UserRole
            from backend.services.auth_service import hash_password, verify_password

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Ensure default admin account exists and password is in sync
            if settings.seed_admin_email and settings.seed_admin_password:
                admin_email = settings.seed_admin_email.strip().lower()
                async with AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(User).where(User.email == admin_email)
                    )
                    admin_user = res.scalar_one_or_none()
                    if admin_user is None:
                        new_admin = User(
                            id=SEED_ADMIN_UUID,
                            email=admin_email,
                            password_hash=hash_password(settings.seed_admin_password),
                            role=UserRole.admin,
                        )
                        session.add(new_admin)
                        await session.commit()
                        logging.info(f"Default admin account initialized: {admin_email}")
                    else:
                        # Synchronize password if it differs from current seed configuration
                        if not verify_password(settings.seed_admin_password, admin_user.password_hash):
                            admin_user.password_hash = hash_password(settings.seed_admin_password)
                            await session.commit()
                            logging.info(f"Default admin account password synced: {admin_email}")
            _db_initialized = True
        except Exception as e:
            logging.warning(f"Database table/admin initialization skipped or failed: {e}")



async def get_db() -> AsyncSession:  # type: ignore[return]
    if not _db_initialized:
        await init_db()
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

