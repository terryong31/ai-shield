from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from shield_api.container import Container
from shield_api.main import create_app
from shield_api.services.admins import NoAdminAuthenticator, SupabaseAdminAuthenticator
from shield_api.services.players import InMemoryPlayerStore
from shield_api.services.scores import InMemoryScoreStore
from shield_api.settings import Settings
from shield_engine import Verdict
from shield_engine.testing import StaticClassifier

if TYPE_CHECKING:
    from shield_api.services.players import PlayerStore
    from shield_api.services.scores import ScoreStore
    from shield_api.services.sessions import SessionStore

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"


# --- in-process fake of supabase-py's auth client ----------------------------


@dataclass
class FakeAuthUser:
    id: str
    email: str
    app_metadata: dict[str, Any] = field(default_factory=dict)
    user_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeAuthSession:
    access_token: str = "fake-access-token"


@dataclass
class FakeUserResponse:
    user: FakeAuthUser | None
    session: FakeAuthSession | None = None


class FakeAuthError(Exception):
    """Mirrors supabase_auth's AuthApiError: a message plus a machine-readable ``code``."""

    def __init__(self, message: str, code: str | None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class FakeAuthDirectory:
    """The Supabase Auth users of one project, shared by every throwaway client."""

    users: dict[str, FakeAuthUser] = field(default_factory=dict)
    passwords: dict[str, str] = field(default_factory=dict)
    email_confirmed: dict[str, bool] = field(default_factory=dict)
    sign_ins: list[str] = field(default_factory=list)
    sign_ups: list[dict[str, Any]] = field(default_factory=list)
    resends: list[dict[str, Any]] = field(default_factory=list)
    open_sessions: int = 0
    fail: bool = False
    writes: int = 0
    # Mirrors the project's "Confirm email" setting.
    confirm_email: bool = True
    # Admin API (update/delete user) failures, separate from sign-in failures.
    fail_admin: bool = False
    # Every Supabase Auth call, in order, by method name.
    calls: list[str] = field(default_factory=list)

    def confirm(self, email: str) -> None:
        user = self.by_email(email)
        assert user is not None
        self.email_confirmed[user.id] = True

    def add(
        self,
        email: str,
        password: str,
        app_metadata: dict[str, Any] | None = None,
        user_metadata: dict[str, Any] | None = None,
    ) -> FakeAuthUser:
        user = FakeAuthUser(
            id=f"user-{len(self.users) + 1}",
            email=email,
            app_metadata=dict(app_metadata or {}),
            user_metadata=dict(user_metadata or {}),
        )
        self.users[user.id] = user
        self.passwords[user.id] = password
        return user

    def by_email(self, email: str) -> FakeAuthUser | None:
        return next((u for u in self.users.values() if u.email.lower() == email.lower()), None)

    def client(self) -> "FakeAuthClient":
        return FakeAuthClient(FakeAuth(self))


@dataclass
class FakeAuthAdmin:
    directory: FakeAuthDirectory

    def list_users(
        self, page: int | None = None, per_page: int | None = None
    ) -> list[FakeAuthUser]:
        users = list(self.directory.users.values())
        size = per_page or 50
        start = ((page or 1) - 1) * size
        return users[start : start + size]

    def create_user(self, attributes: dict[str, Any]) -> FakeUserResponse:
        self.directory.writes += 1
        user = self.directory.add(
            attributes["email"], attributes["password"], attributes.get("app_metadata")
        )
        self.directory.email_confirmed[user.id] = bool(attributes.get("email_confirm"))
        return FakeUserResponse(user)

    def update_user_by_id(self, uid: str, attributes: dict[str, Any]) -> FakeUserResponse:
        self.directory.calls.append("admin.update_user_by_id")
        if self.directory.fail_admin:
            raise RuntimeError("auth admin down")
        self.directory.writes += 1
        user = self.directory.users[uid]
        if "email" in attributes:
            taken = self.directory.by_email(attributes["email"])
            if taken is not None and taken.id != uid:
                raise FakeAuthError("Email address already registered", "email_exists")
            user.email = attributes["email"]
        if "password" in attributes:
            self.directory.passwords[uid] = attributes["password"]
        if "app_metadata" in attributes:
            user.app_metadata = dict(attributes["app_metadata"])
        if "email_confirm" in attributes:
            self.directory.email_confirmed[uid] = bool(attributes["email_confirm"])
        return FakeUserResponse(user)

    def delete_user(self, uid: str, should_soft_delete: bool = False) -> None:
        self.directory.calls.append("admin.delete_user")
        if self.directory.fail_admin:
            raise RuntimeError("auth admin down")
        self.directory.writes += 1
        self.directory.users.pop(uid)
        self.directory.passwords.pop(uid, None)


@dataclass
class FakeAuth:
    directory: FakeAuthDirectory
    signed_in: bool = False

    @property
    def admin(self) -> FakeAuthAdmin:
        return FakeAuthAdmin(self.directory)

    def _open_session(self) -> FakeAuthSession:
        self.signed_in = True
        self.directory.open_sessions += 1
        return FakeAuthSession()

    def sign_in_with_password(self, credentials: dict[str, str]) -> FakeUserResponse:
        directory = self.directory
        directory.calls.append("sign_in_with_password")
        directory.sign_ins.append(credentials["email"])
        if directory.fail:
            raise RuntimeError("auth service down")
        user = directory.by_email(credentials["email"])
        if user is None or directory.passwords[user.id] != credentials["password"]:
            raise FakeAuthError("Invalid login credentials", "invalid_credentials")
        if directory.email_confirmed.get(user.id, True) is False:
            raise FakeAuthError("Email not confirmed", "email_not_confirmed")
        return FakeUserResponse(user, self._open_session())

    def sign_up(self, credentials: dict[str, Any]) -> FakeUserResponse:
        directory = self.directory
        directory.calls.append("sign_up")
        directory.sign_ups.append(credentials)
        if directory.fail:
            raise RuntimeError("auth service down")
        options = credentials.get("options") or {}
        if directory.by_email(credentials["email"]) is not None:
            if directory.confirm_email:
                # Supabase answers an existing email with an obfuscated user, no error.
                return FakeUserResponse(FakeAuthUser(id="obfuscated", email=credentials["email"]))
            raise FakeAuthError("User already registered", "user_already_exists")
        user = directory.add(
            credentials["email"], credentials["password"], user_metadata=options.get("data")
        )
        directory.email_confirmed[user.id] = not directory.confirm_email
        if directory.confirm_email:
            return FakeUserResponse(user)
        return FakeUserResponse(user, self._open_session())

    def resend(self, credentials: dict[str, Any]) -> object:
        directory = self.directory
        directory.calls.append("resend")
        directory.resends.append(credentials)
        if directory.fail:
            raise RuntimeError("auth service down")
        return object()

    def sign_in_anonymously(self, *_: Any) -> object:
        self.directory.calls.append("sign_in_anonymously")
        return object()

    def sign_out(self) -> None:
        self.directory.calls.append("sign_out")
        if self.signed_in:
            self.signed_in = False
            self.directory.open_sessions -= 1


@dataclass
class FakeAuthClient:
    auth: FakeAuth


@dataclass
class FakeClock:
    """Monotonic seconds, advanced by hand."""

    now: float = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class Harness:
    client: TestClient
    container: Container
    classifier: StaticClassifier
    scores: "ScoreStore"
    sessions: "SessionStore"
    clock: FakeClock
    auth: FakeAuthDirectory

    def grant(self, password: str, email: str = ADMIN_EMAIL):  # -> httpx.Response
        return self.client.post("/api/v1/clearance", json={"email": email, "password": password})


@pytest.fixture
def make_harness() -> Iterator[Callable[..., Harness]]:
    clients: list[TestClient] = []

    def build(
        verdict: Verdict = Verdict.SAFE,
        probability: float = 0.05,
        sessions: "SessionStore | None" = None,
        supabase_auth: bool = True,
        supabase_players: bool = False,
        players: "PlayerStore | None" = None,
        scores: "ScoreStore | None" = None,
    ) -> Harness:
        from shield_api.services.sessions import AttemptLimiter, InMemorySessionStore

        classifier = StaticClassifier(verdict, probability)
        scores = scores or InMemoryScoreStore()
        sessions = sessions or InMemorySessionStore()
        clock = FakeClock()
        auth = FakeAuthDirectory()
        auth.add(ADMIN_EMAIL, ADMIN_PASSWORD, app_metadata={"provider": "email", "role": "admin"})
        settings = Settings(
            _env_file=None,
            # TestClient speaks plain http://testserver, which drops Secure cookies.
            SESSION_COOKIE_SECURE=False,
        )
        container = Container(
            settings=settings,
            classifier=classifier,
            scores=scores,
            sessions=sessions,
            attempts=AttemptLimiter(
                max_attempts=settings.CLEARANCE_MAX_ATTEMPTS,
                window=timedelta(minutes=settings.CLEARANCE_WINDOW_MINUTES),
                clock=clock,
            ),
            admins=(
                SupabaseAdminAuthenticator(auth.client) if supabase_auth else NoAdminAuthenticator()
            ),
            players=players or InMemoryPlayerStore(),
        )
        if supabase_players:
            from shield_api.services.identity import SupabasePlayerIdentity

            container.identity = SupabasePlayerIdentity(
                auth.client, redirect_to=f"{settings.WEB_BASE_URL}/auth/confirmed"
            )
        client = TestClient(create_app(container))
        client.__enter__()
        clients.append(client)
        return Harness(client, container, classifier, scores, sessions, clock, auth)

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def admin_password() -> str:
    return ADMIN_PASSWORD


@pytest.fixture
def harness(make_harness: Callable[..., Harness]) -> Harness:
    return make_harness()


# --- in-process fake of the supabase-py query builder ------------------------


@dataclass
class Result:
    data: list[dict[str, Any]] | None = None
    count: int | None = None


def _matches(row: dict[str, Any], tests: list[tuple[str, str, Any]]) -> bool:
    for op, column, value in tests:
        cell = row.get(column)
        if op == "eq" and cell != value:
            return False
        if op == "neq" and cell == value:
            return False
        if op == "lte" and not (cell is not None and cell <= value):
            return False
        if op == "lt" and not (cell is not None and cell < value):
            return False
        if op == "gte" and not (cell is not None and cell >= value):
            return False
    return True


@dataclass
class FakeQuery:
    table: "FakeTable"
    op: str
    payload: Any = None
    tests: list[tuple[str, str, Any]] = field(default_factory=list)
    orders: list[tuple[str, bool]] = field(default_factory=list)
    count_mode: str | None = None
    limit_n: int | None = None
    on_conflict: str | None = None

    @property
    def filters(self) -> dict[str, Any]:
        return {column: value for op, column, value in self.tests if op == "eq"}

    def select(self, *_: str, count: str | None = None, head: bool = False) -> "FakeQuery":
        self.count_mode = count
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.tests.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> "FakeQuery":
        self.tests.append(("neq", column, value))
        return self

    def lte(self, column: str, value: Any) -> "FakeQuery":
        self.tests.append(("lte", column, value))
        return self

    def lt(self, column: str, value: Any) -> "FakeQuery":
        self.tests.append(("lt", column, value))
        return self

    def gte(self, column: str, value: Any) -> "FakeQuery":
        self.tests.append(("gte", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.orders.append((column, desc))
        return self

    def limit(self, n: int) -> "FakeQuery":
        self.limit_n = n
        return self

    def execute(self) -> Result:
        table = self.table
        if table.fail:
            raise RuntimeError("network down")
        rows = table.rows
        if self.op == "insert":
            table.counter += 1
            row = {
                "id": str(len(rows)),
                "created_at": f"2026-09-23T00:00:{table.counter:02d}+00:00",
                **self.payload,
            }
            rows.append(row)
            return Result(data=[dict(row)])
        if self.op == "upsert":
            keys = [k.strip() for k in (self.on_conflict or "id").split(",")]
            for row in rows:
                if all(row.get(k) == self.payload.get(k) for k in keys):
                    row.update(self.payload)
                    return Result(data=[dict(row)])
            rows.append(dict(self.payload))
            return Result(data=[dict(self.payload)])
        matching = [r for r in rows if _matches(r, self.tests)]
        if self.op == "update":
            for row in matching:
                row.update(self.payload)
            return Result(data=[dict(r) for r in matching])
        if self.op == "delete":
            table.rows = [r for r in rows if r not in matching]
            return Result(data=matching)
        if self.count_mode:
            return Result(count=len(matching))
        ordered = list(matching)
        for column, desc in reversed(self.orders):
            ordered.sort(key=lambda r, c=column: r.get(c), reverse=desc)
        return Result(data=[dict(r) for r in ordered[: self.limit_n]])


@dataclass
class FakeTable:
    rows: list[dict[str, Any]] = field(default_factory=list)
    fail: bool = False
    counter: int = 0

    def insert(self, row: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, "insert", row)

    def upsert(self, row: dict[str, Any], on_conflict: str | None = None) -> FakeQuery:
        return FakeQuery(self, "upsert", row, on_conflict=on_conflict)

    def update(self, values: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, "update", values)

    def delete(self) -> FakeQuery:
        return FakeQuery(self, "delete")

    def select(self, *columns: str, **kwargs: Any) -> FakeQuery:
        return FakeQuery(self, "select").select(*columns, **kwargs)


@dataclass
class FakeSchema:
    client: "FakeClient"
    name: str

    def table(self, name: str) -> FakeTable:
        self.client.accessed.append((self.name, name))
        return self.client.tables.setdefault((self.name, name), FakeTable(fail=self.client.fail))


@dataclass
class FakeClient:
    """Tables are keyed by ``(schema, table)``; nothing lives in ``public`` (spec 0024)."""

    fail: bool = False
    tables: dict[tuple[str, str], FakeTable] = field(default_factory=dict)
    accessed: list[tuple[str, str]] = field(default_factory=list)

    def schema(self, name: str) -> FakeSchema:
        return FakeSchema(self, name)

    def table(self, name: str) -> FakeTable:
        raise AssertionError(f"query {name!r} through client.schema(...), not public")

    @property
    def requests(self) -> FakeTable:
        return self.schema("audit").table("requests")


@pytest.fixture
def fake_supabase() -> Callable[..., FakeClient]:
    def build(fail: bool = False) -> FakeClient:
        return FakeClient(fail=fail)

    return build
