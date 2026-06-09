"""
Purpose:
- Configure and expose PostgreSQL engine and session creation.

Responsibilities:
- Create the SQLAlchemy engine and session factory
- Provide the shared engine used by ORM sessions and migrations
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings

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
