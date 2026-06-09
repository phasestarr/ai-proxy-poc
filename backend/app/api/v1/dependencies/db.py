"""
Purpose:
- Provide FastAPI dependency helpers related to database access.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.postgres.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
