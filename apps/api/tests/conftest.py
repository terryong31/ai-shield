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


@dataclass
class FakeQuery:
    table: "FakeTable"
    op: str
    payload: Any = None
    filters: dict[str, Any] = field(default_factory=dict)
    count_mode: str | None = None
    limit_n: int | None = None

    def select(self, *_: str, count: str | None = None, head: bool = False) -> "FakeQuery":
        self.count_mode = count
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters[column] = value
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        return self

    def limit(self, n: int) -> "FakeQuery":
        self.limit_n = n
        return self

    def execute(self) -> Result:
        if self.table.fail:
            raise RuntimeError("network down")
        rows = self.table.rows
        if self.op == "insert":
            rows.append(
                {"id": str(len(rows)), "created_at": "2026-09-23T00:00:00Z", **self.payload}
            )
            return Result()
        matching = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
        if self.op == "update":
            for row in matching:
                row.update(self.payload)
            return Result()
        if self.count_mode:
            return Result(count=len(matching))
        return Result(data=list(reversed(matching))[: self.limit_n])


@dataclass
class FakeTable:
    rows: list[dict[str, Any]] = field(default_factory=list)
    fail: bool = False

    def insert(self, row: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, "insert", row)

    def update(self, values: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, "update", values)

    def select(self, *columns: str, **kwargs: Any) -> FakeQuery:
        return FakeQuery(self, "select").select(*columns, **kwargs)


@dataclass
class FakeClient:
    requests: FakeTable = field(default_factory=FakeTable)

    def table(self, name: str) -> FakeTable:
        assert name == "requests"
        return self.requests


@pytest.fixture
def fake_supabase() -> Callable[..., FakeClient]:
    def build(fail: bool = False) -> FakeClient:
        return FakeClient(FakeTable(fail=fail))

    return build
