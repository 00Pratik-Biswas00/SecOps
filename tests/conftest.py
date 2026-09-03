import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings

settings = get_settings()
TEST_DATABASE_URL = settings.database_url


@pytest_asyncio.fixture
async def db_session():
    """Each test gets its own connection, rolled back on teardown."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await trans.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def user_viewer(db_session):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.user import User

    result = await db_session.execute(
        select(User).where(User.username == "alice_viewer").options(selectinload(User.role))
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def user_engineer(db_session):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.user import User

    result = await db_session.execute(
        select(User).where(User.username == "bob_engineer").options(selectinload(User.role))
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def user_admin(db_session):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.user import User

    result = await db_session.execute(
        select(User).where(User.username == "carol_admin").options(selectinload(User.role))
    )
    return result.scalar_one()
