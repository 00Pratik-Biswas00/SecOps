import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def _build_database_url() -> str:
    cloud_sql = os.environ.get("CLOUD_SQL_CONNECTION_NAME", "")
    db_pass = os.environ.get("DB_PASSWORD", "")
    if cloud_sql and db_pass:
        # Cloud Run — connect via Unix socket, no public DB port
        socket = f"/cloudsql/{cloud_sql}"
        return f"postgresql+asyncpg://connector:{db_pass}@/secops_db?host={socket}"
    return settings.database_url


engine = create_async_engine(
    _build_database_url(),
    echo=settings.app_env == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
