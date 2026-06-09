"""
Configuration package for shared app settings and neutral runtime helpers.
"""

from app.config.chat_instructions import build_chat_system_instruction
from app.config.settings import settings
from app.config.time import utc_now

__all__ = [
    "build_chat_system_instruction",
    "settings",
    "utc_now",
]
