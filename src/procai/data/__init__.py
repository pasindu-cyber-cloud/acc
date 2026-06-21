"""Local persistence layer (SQLite). All data remains on the user's machine."""

from .database import Database

__all__ = ["Database"]
