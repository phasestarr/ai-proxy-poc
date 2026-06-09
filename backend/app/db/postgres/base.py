"""
Purpose:
- Define the shared SQLAlchemy declarative base for PostgreSQL ORM models.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
