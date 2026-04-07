"""
Configuration package for shared app settings and neutral runtime helpers.
"""

from app.config.settings import settings
from app.config.time import utc_now

__all__ = [
    "settings",
    "utc_now",
]
