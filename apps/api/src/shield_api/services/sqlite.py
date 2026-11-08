"""SQLite connections laid out like the Postgres domain schemas (spec 0024).

Each domain (``audit``, ``game``, ``players``) is its own database file attached
under the schema's name, so SQL reads ``audit.requests`` or ``players.accounts``
exactly as it does in Postgres, and the main database stays empty.
"""

import sqlite3
from pathlib import Path

DOMAINS: tuple[str, ...] = ("audit", "game", "players")


def domain_path(path: Path, schema: str) -> Path:
    """``var/shield.db`` holds ``audit`` in ``var/shield.audit.db``, and so on."""
    return path.with_name(f"{path.stem}.{schema}{path.suffix or '.db'}")


def connect_domains(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    for schema in DOMAINS:
        # Schema names come from the fixed DOMAINS tuple, never from input.
        connection.execute(f"attach database ? as {schema}", (str(domain_path(path, schema)),))
    return connection
