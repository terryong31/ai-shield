"""Row level security and role privileges on the real database (spec 0056)."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import errors, sql

pytestmark = pytest.mark.db

SCHEMAS = ("audit", "game", "players")
CLIENT_ROLES = ("anon", "authenticated")


def _tables(db: psycopg.Connection) -> list[tuple[str, str]]:
    return db.execute(
        "select schemaname, tablename from pg_tables where schemaname = any(%s) order by 1, 2",
        (list(SCHEMAS),),
    ).fetchall()


@pytest.mark.spec("API-DB-001")
def test_client_roles_are_denied_every_table_and_function(db: psycopg.Connection) -> None:
    tables = _tables(db)
    assert tables, "no application tables found"
    for role in CLIENT_ROLES:
        for schema, table in tables:
            target = sql.Identifier(schema, table)
            # psycopg.sql quotes the identifiers, so these are not string-built SQL.
            for statement in (
                sql.SQL("select 1 from {} limit 1").format(target),
                sql.SQL("delete from {} where false").format(target),
            ):
                db.execute("savepoint probe")
                db.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
                with pytest.raises(errors.InsufficientPrivilege):
                    db.execute(statement)
                db.execute("rollback to savepoint probe")

        functions = db.execute(
            "select p.oid::regprocedure::text from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'players'"
        ).fetchall()
        assert functions
        for (signature,) in functions:
            privileged = db.execute(
                "select has_function_privilege(%s, %s, 'execute')", (role, signature)
            ).fetchone()
            assert privileged == (False,), (role, signature)

    public = db.execute("select tablename from pg_tables where schemaname = 'public'").fetchall()
    assert public == []


@pytest.mark.spec("API-DB-002")
def test_every_table_has_rls_and_no_client_grants(db: psycopg.Connection) -> None:
    rows = db.execute(
        "select n.nspname, c.relname, c.relrowsecurity from pg_class c "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where c.relkind = 'r' and n.nspname = any(%s)",
        (list(SCHEMAS),),
    ).fetchall()
    assert rows
    assert [(s, t) for s, t, rls in rows if not rls] == []

    grants = db.execute(
        "select table_schema, table_name, grantee, privilege_type "
        "from information_schema.role_table_grants "
        "where table_schema = any(%s) and grantee in ('PUBLIC', 'anon', 'authenticated')",
        (list(SCHEMAS),),
    ).fetchall()
    assert grants == []
    for schema, table, _ in rows:
        for role in CLIENT_ROLES:
            allowed = db.execute(
                "select has_table_privilege(%s, %s, 'select, insert, update, delete')",
                (role, f'"{schema}"."{table}"'),
            ).fetchone()
            assert allowed == (False,), (role, schema, table)
