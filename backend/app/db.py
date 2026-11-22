"""Database session management.

Default is SQLite so the platform runs on a laptop with zero configuration;
set DATABASE_URL to a PostgreSQL DSN in production. Nothing else changes.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    _default_path = os.environ.get(
        "COMPLIANCE_DB", os.path.join(os.path.expanduser("~"), "compliance-os.db")
    )
    DATABASE_URL = "sqlite:///" + _default_path

# pool_pre_ping keeps a long-lived worker honest after a DB restart.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args, future=True)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registers mappers)
    Base.metadata.create_all(bind=engine)
