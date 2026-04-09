from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import DATABASE_URL

# Ensure the directory for the SQLite database file exists
_db_path = DATABASE_URL.split("///")[-1] if "///" in DATABASE_URL else None
if _db_path:
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add columns that may be missing from older databases
    async with engine.begin() as conn:
        from sqlalchemy import text, inspect as sa_inspect

        def _add_missing_columns(connection):
            inspector = sa_inspect(connection)
            for table_name, columns_to_add in [
                ("tracking_results", [("debug_log", "TEXT"), ("aio_citation_url", "TEXT")]),
            ]:
                if not inspector.has_table(table_name):
                    continue
                existing = {c["name"] for c in inspector.get_columns(table_name)}
                for col_name, col_type in columns_to_add:
                    if col_name not in existing:
                        connection.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                        ))

        await conn.run_sync(_add_missing_columns)
