"""
Purpose:
- Configure and expose PostgreSQL engine and session creation.

Responsibilities:
- Create the SQLAlchemy engine and session factory
- Initialize ORM tables for the current PoC runtime
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.postgres.base import Base

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_database() -> None:
    import app.db.postgres.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
