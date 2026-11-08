import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from shield_api.container import Container
from shield_api.demo.assistant import AssistantReply, DemoAssistant
from shield_api.main import create_app
from shield_api.services.audit import InMemoryAuditLog
from shield_api.settings import Settings
from shield_engine import Shield, ToolPolicy, Verdict
from shield_engine.testing import ScriptedAdjudicator, StaticClassifier

if TYPE_CHECKING:
    from shield_api.services.sessions import SessionStore

PASSPHRASE = "correct horse battery staple"


@dataclass
class RecordingAssistant:
    """Wraps the real demo assistant (offline) and records what it was allowed."""

    calls: list[tuple[str, list[str]]] = field(default_factory=list)
    inner: DemoAssistant = field(default_factory=DemoAssistant)

    async def respond(self, prompt: str, allowed_tools: list[str]) -> AssistantReply:
        self.calls.append((prompt, allowed_tools))
        return await self.inner.respond(prompt, allowed_tools)


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
    adjudicator: ScriptedAdjudicator
    assistant: RecordingAssistant
    audit_log: InMemoryAuditLog
    sessions: "SessionStore"
    clock: FakeClock

    def chat(self, **body) -> list[dict]:
        with self.client.stream("POST", "/api/v1/chat", json=body) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("application/x-ndjson")
            return [json.loads(line) for line in response.iter_lines() if line]

    def grant(self, passphrase: str):  # -> httpx.Response
        return self.client.post("/api/v1/clearance", json={"passphrase": passphrase})


@pytest.fixture
def make_harness() -> Iterator[Callable[..., Harness]]:
    clients: list[TestClient] = []

    def build(
        verdict: Verdict = Verdict.SAFE,
        probability: float = 0.05,
        adjudicator: ScriptedAdjudicator | None = None,
        sessions: "SessionStore | None" = None,
        secret: str | None = PASSPHRASE,
    ) -> Harness:
        from shield_api.services.sessions import AttemptLimiter, InMemorySessionStore

        classifier = StaticClassifier(verdict, probability)
        adjudicator = adjudicator or ScriptedAdjudicator(
            verdict=Verdict.SAFE, policy=ToolPolicy.RESTRICTED
        )
        assistant = RecordingAssistant()
        audit_log = InMemoryAuditLog()
        sessions = sessions or InMemorySessionStore()
        clock = FakeClock()
        settings = Settings(
            _env_file=None,
            SECURE_PASSPHRASE=SecretStr(secret) if secret else None,
            # TestClient speaks plain http://testserver, which drops Secure cookies.
            SESSION_COOKIE_SECURE=False,
        )
        container = Container(
            settings=settings,
            classifier=classifier,
            shield=Shield(classifier, adjudicator=adjudicator),
            audit_log=audit_log,
            assistant=assistant,
            sessions=sessions,
            attempts=AttemptLimiter(
                max_attempts=settings.CLEARANCE_MAX_ATTEMPTS,
                window=timedelta(minutes=settings.CLEARANCE_WINDOW_MINUTES),
                clock=clock,
            ),
        )
        client = TestClient(create_app(container))
        client.__enter__()
        clients.append(client)
        return Harness(
            client, container, classifier, adjudicator, assistant, audit_log, sessions, clock
        )

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def valid_passphrase() -> str:
    return PASSPHRASE


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
