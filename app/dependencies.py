from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        async with session.begin():
            yield session
