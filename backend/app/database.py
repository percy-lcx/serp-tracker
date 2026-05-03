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
                ("aio_citations", [
                    ("citation_type", "VARCHAR(20) DEFAULT 'inline'"),
                    ("is_same_domain", "BOOLEAN DEFAULT 0"),
                ]),
                ("organic_results", [("is_same_domain", "BOOLEAN DEFAULT 0")]),
                ("tracking_jobs", [("target_domain", "VARCHAR(253)")]),
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

    # Drop NOT NULL on tracking_jobs.target_url (SQLite needs a table rebuild).
    async with engine.begin() as conn:
        from sqlalchemy import text, inspect as sa_inspect

        def _relax_target_url_nullable(connection):
            inspector = sa_inspect(connection)
            if not inspector.has_table("tracking_jobs"):
                return
            cols = {c["name"]: c for c in inspector.get_columns("tracking_jobs")}
            target_col = cols.get("target_url")
            if target_col is None or target_col.get("nullable", True):
                return
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(text("""
                CREATE TABLE tracking_jobs__new (
                    id VARCHAR(36) PRIMARY KEY,
                    target_url TEXT,
                    target_domain VARCHAR(253),
                    query TEXT NOT NULL,
                    gl VARCHAR(10) NOT NULL DEFAULT 'us',
                    hl VARCHAR(10) NOT NULL DEFAULT 'en',
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            connection.execute(text("""
                INSERT INTO tracking_jobs__new
                    (id, target_url, target_domain, query, gl, hl, is_active, created_at, updated_at)
                SELECT id, target_url, target_domain, query, gl, hl, is_active, created_at, updated_at
                FROM tracking_jobs
            """))
            connection.execute(text("DROP TABLE tracking_jobs"))
            connection.execute(text("ALTER TABLE tracking_jobs__new RENAME TO tracking_jobs"))
            connection.execute(text("PRAGMA foreign_keys=ON"))

        await conn.run_sync(_relax_target_url_nullable)
