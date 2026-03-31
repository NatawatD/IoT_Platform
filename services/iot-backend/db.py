import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/iot.db")


def _ensure_sqlite_dir() -> None:
    if DATABASE_URL.startswith("sqlite+aiosqlite:///"):
        db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    _ensure_sqlite_dir()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
