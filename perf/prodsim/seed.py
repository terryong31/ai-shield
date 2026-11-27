"""Make or remove the lab's test players in local Supabase (lab only).

Usage: uv run python perf/prodsim/seed.py create N   |   uv run python perf/prodsim/seed.py clean

Players are `swarm+<n>@example.invalid` on the paid plan, so the daily wave limit (50) is not
what the swarm measures. Their passwords are generated per run and written to out/users.json.
"""

from __future__ import annotations

import json
import secrets
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api" / "tests" / "db"))
from conftest import local_stack

OUT = Path(__file__).resolve().parent / "out"
PATTERN = "swarm+%@example.invalid"


def _create_auth_user(api_url: str, key: str, email: str, password: str) -> None:
    body = json.dumps({"email": email, "password": password, "email_confirm": True}).encode()
    request = urllib.request.Request(  # noqa: S310 - the local Supabase URL
        f"{api_url}/auth/v1/admin/users",
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30):  # noqa: S310
        pass


def create(count: int) -> None:
    stack = local_stack()
    password = "Sw4rm" + secrets.token_urlsafe(12)
    users = [{"email": f"swarm+{n}@example.invalid", "password": password} for n in range(count)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(
            pool.map(
                lambda u: _create_auth_user(
                    stack.api_url, stack.service_key, u["email"], u["password"]
                ),
                users,
            )
        )
    with psycopg.connect(stack.db_url, autocommit=True) as conn:
        conn.cursor().executemany(
            "insert into players.accounts (email, player_name, tier, paid_until) "
            "values (%s, %s, 'paid', now() + interval '30 days') on conflict (email) do nothing",
            [(u["email"], f"Swarm {n}") for n, u in enumerate(users)],
        )
    OUT.mkdir(exist_ok=True)
    (OUT / "users.json").write_text(json.dumps(users))
    print(f"created {count} players")


def clean() -> None:
    stack = local_stack()
    with psycopg.connect(stack.db_url, autocommit=True) as conn:
        for table in (
            "players.purchases",
            "players.daily_usage",
            "players.sessions",
            "game.saved_boards",
            "game.scores",
            "players.accounts",
        ):
            conn.execute(f"delete from {table} where email like %s", (PATTERN,))  # noqa: S608
        conn.execute("delete from players.sessions where email is null")
        conn.execute("delete from game.anonymous_scores")
        conn.execute("delete from players.daily_usage where email like 'anon:%%'")
        conn.execute("delete from auth.users where email like %s", (PATTERN,))
    (OUT / "users.json").unlink(missing_ok=True)
    print("removed the lab players")


if __name__ == "__main__":
    if sys.argv[1:2] == ["create"]:
        create(int(sys.argv[2]))
    elif sys.argv[1:2] == ["clean"]:
        clean()
    else:
        raise SystemExit(__doc__)
