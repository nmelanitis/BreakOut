"""Small persistent local state; never stores Spotify access credentials."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def default_state_path() -> Path:
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "BreakOut"
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BreakOut"
    else:
        root = Path.home() / ".local" / "share" / "breakout"
    return root / "state.sqlite3"


class LocalState:
    """SQLite-backed settings that are safe to keep between local app launches."""

    SPOTIFY_CLIENT_ID = "spotify_client_id"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def spotify_client_id(self) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (self.SPOTIFY_CLIENT_ID,)
            ).fetchone()
        return row[0] if row else None

    def set_spotify_client_id(self, client_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (self.SPOTIFY_CLIENT_ID, client_id),
            )

    def clear_spotify_setup(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM settings WHERE key = ?", (self.SPOTIFY_CLIENT_ID,))
