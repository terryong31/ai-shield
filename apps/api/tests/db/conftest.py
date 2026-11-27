"""Fixtures for the database tests (spec 0056). They need the local Supabase stack.

`mise run test:db` starts it. The tests make rows with unique `dbtest+<uuid>` emails and
delete them again, so they never touch real data.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache

import psycopg
import pytest


@dataclass(frozen=True)
class LocalStack:
    db_url: str
    api_url: str
    service_key: str


@cache
def local_stack() -> LocalStack:
    """The local stack from the environment, else from `supabase status`."""
    db_url = os.environ.get("SHIELD_TEST_DB_URL")
    api_url = os.environ.get("SHIELD_TEST_API_URL")
    key = os.environ.get("SHIELD_TEST_SERVICE_KEY")
    if not (db_url and api_url and key):
        supabase = shutil.which("supabase")
        if supabase is None:
            raise RuntimeError("The Supabase CLI is not on PATH; run `mise run test:db`.")
        raw = subprocess.run(  # noqa: S603 - a fixed argv from the PATH lookup above
            [supabase, "status", "-o", "json"], capture_output=True, text=True, check=True
        ).stdout
        status = json.loads(raw[raw.index("{") :])
        db_url = db_url or status["DB_URL"]
        api_url = api_url or status["API_URL"]
        key = key or status.get("SERVICE_ROLE_KEY") or status["SECRET_KEY"]
    return LocalStack(db_url=db_url, api_url=api_url, service_key=key)


@pytest.fixture
def stack() -> LocalStack:
    return local_stack()


@pytest.fixture
def db(stack: LocalStack) -> Iterator[psycopg.Connection]:
    """A superuser connection whose work is rolled back at the end of the test."""
    with psycopg.connect(stack.db_url) as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def email() -> str:
    return f"dbtest+{uuid.uuid4().hex}@example.invalid"


def purge(stack: LocalStack, *emails: str) -> None:
    """Delete every row that the given test emails own."""
    with psycopg.connect(stack.db_url, autocommit=True) as conn:
        for address in emails:
            conn.execute("delete from players.purchases where email = %s", (address,))
            conn.execute("delete from players.daily_usage where email = %s", (address,))
            conn.execute("delete from players.sessions where email = %s", (address,))
            conn.execute("delete from game.saved_boards where email = %s", (address,))
            conn.execute("delete from game.scores where email = %s", (address,))
            conn.execute("delete from players.accounts where email = %s", (address,))
