"""Audit log of screened requests. The gateway owns persistence; the web client never
touches the database directly."""

import asyncio
import json
import logging
import sqlite3
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

from shield_api.schemas import (
    AuditRecord,
    BoardGraphSchema,
    ScoreCreateRequest,
    ScoreRecord,
    StatsResponse,
)

logger = logging.getLogger(__name__)

Action = Literal["ALLOWED", "BLOCKED"]
Backend = Literal["sqlite", "supabase", "memory"]


def _stats(total: int, blocked: int) -> StatsResponse:
    return StatsResponse(
        total=total,
        blocked=blocked,
        allowed=total - blocked,
        block_rate=round(blocked / total * 100, 1) if total else 0.0,
    )


class AuditLog(Protocol):
    backend: ClassVar[Backend]

    async def record(
        self, *, query: str, action: Action, reason: str, layer: str, metadata: dict[str, Any]
    ) -> None: ...

    async def recent(self, limit: int) -> list[AuditRecord]: ...

    async def stats(self) -> StatsResponse: ...

    async def review(self, request_id: str, human_label: int) -> None: ...

    async def record_score(self, payload: ScoreCreateRequest) -> ScoreRecord: ...

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]: ...

    async def clear_scores(self) -> None: ...


class InMemoryAuditLog:
    """Test double. Bounded and lost on restart, so never wired in production."""

    backend: ClassVar[Backend] = "memory"

    def __init__(self, capacity: int = 1000) -> None:
        self._records: deque[AuditRecord] = deque(maxlen=capacity)
        self._scores: list[ScoreRecord] = []

    async def record(
        self, *, query: str, action: Action, reason: str, layer: str, metadata: dict[str, Any]
    ) -> None:
        self._records.appendleft(
            AuditRecord(
                id=str(uuid.uuid4()),
                created_at=datetime.now(UTC),
                query=query,
                action=action,
                reason=reason,
                layer=layer,
                metadata=metadata,
            )
        )

    async def recent(self, limit: int) -> list[AuditRecord]:
        return list(self._records)[:limit]

    async def stats(self) -> StatsResponse:
        blocked = sum(1 for r in self._records if r.action == "BLOCKED")
        return _stats(len(self._records), blocked)

    async def review(self, request_id: str, human_label: int) -> None:
        for index, record in enumerate(self._records):
            if record.id == request_id:
                self._records[index] = record.model_copy(
                    update={
                        "reviewed": True,
                        "human_label": human_label,
                        "action": "BLOCKED" if human_label == 1 else "ALLOWED",
                    }
                )
                return

    async def record_score(self, payload: ScoreCreateRequest) -> ScoreRecord:
        entry = ScoreRecord(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            **payload.model_dump(),
        )
        self._scores.append(entry)
        return entry

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        items = [s for s in self._scores if level_id is None or s.level_id == level_id]
        items.sort(key=lambda s: (-s.total_score, s.avg_latency_ms, s.total_cost_usd, s.created_at))
        return items[:limit]

    async def clear_scores(self) -> None:
        self._scores.clear()


class SupabaseAuditLog:
    """Stores records in the Supabase ``requests`` table.

    The supabase-py client is synchronous, so calls run in a worker thread to
    keep the event loop free. Write failures are logged, not raised: losing an
    audit row must not break the user's request.
    """

    backend: ClassVar[Backend] = "supabase"
    TABLE = "requests"

    def __init__(self, client: Any) -> None:
        self._client = client
        self._scores: list[ScoreRecord] = []

    async def record(
        self, *, query: str, action: Action, reason: str, layer: str, metadata: dict[str, Any]
    ) -> None:
        row = {
            "query": query,
            "action": action,
            "reason": reason,
            "layer": layer,
            "metadata": metadata,
            "reviewed": False,
        }
        try:
            await asyncio.to_thread(lambda: self._client.table(self.TABLE).insert(row).execute())
        except Exception:
            logger.exception("failed to write audit record")

    async def recent(self, limit: int) -> list[AuditRecord]:
        response = await asyncio.to_thread(
            lambda: (
                self._client.table(self.TABLE)
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        )
        return [AuditRecord.model_validate(row) for row in response.data or []]

    async def stats(self) -> StatsResponse:
        def count(action: str | None) -> int:
            query = self._client.table(self.TABLE).select("id", count="exact", head=True)
            if action:
                query = query.eq("action", action)
            return int(query.execute().count or 0)

        total, blocked = await asyncio.gather(
            asyncio.to_thread(count, None), asyncio.to_thread(count, "BLOCKED")
        )
        return _stats(total, blocked)

    async def review(self, request_id: str, human_label: int) -> None:
        update = {
            "human_label": human_label,
            "reviewed": True,
            "action": "BLOCKED" if human_label == 1 else "ALLOWED",
        }
        try:
            await asyncio.to_thread(
                lambda: self._client.table(self.TABLE).update(update).eq("id", request_id).execute()
            )
        except Exception:
            logger.exception("failed to update audit review")

    async def record_score(self, payload: ScoreCreateRequest) -> ScoreRecord:
        entry = ScoreRecord(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            **payload.model_dump(),
        )
        self._scores.append(entry)
        return entry

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        items = [s for s in self._scores if level_id is None or s.level_id == level_id]
        items.sort(key=lambda s: (-s.total_score, s.avg_latency_ms, s.total_cost_usd, s.created_at))
        return items[:limit]

    async def clear_scores(self) -> None:
        self._scores.clear()


class SqliteAuditLog:
    """Zero-setup durable store, used whenever Supabase is not configured.

    Mirrors the columns of ``supabase/migrations`` (API-STORE-006). Each call
    opens its own connection in a worker thread, so the event loop never
    blocks and no connection is shared across threads.
    """

    backend: ClassVar[Backend] = "sqlite"
    _SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("pragma journal_mode = wal")
            if connection.execute("pragma user_version").fetchone()[0] < self._SCHEMA_VERSION:
                connection.executescript(
                    """
                    create table if not exists requests (
                      id          text    primary key,
                      created_at  text    not null,
                      query       text    not null,
                      action      text    not null check (action in ('ALLOWED', 'BLOCKED')),
                      reason      text    not null default '',
                      layer       text    not null,
                      metadata    text    not null default '{}',
                      reviewed    integer not null default 0,
                      human_label integer check (human_label in (0, 1))
                    );
                    create index if not exists requests_created_at_idx
                      on requests (created_at desc);
                    create index if not exists requests_action_idx on requests (action);
                    pragma user_version = 1;
                    """
                )
            connection.executescript(
                """
                create table if not exists scores (
                  id              text    primary key,
                  created_at      text    not null,
                  player_name     text    not null,
                  level_id        text    not null,
                  total_score     integer not null,
                  medal           text    not null,
                  attacks_blocked integer not null,
                  attacks_total   integer not null,
                  false_alarms    integer not null,
                  avg_latency_ms  real    not null,
                  total_cost_usd  real    not null,
                  board_json      text    not null
                );
                create index if not exists scores_rank_idx
                  on scores (level_id, total_score desc, avg_latency_ms asc, total_cost_usd asc);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        connection = self._connect()
        try:
            with connection:
                return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    async def record(
        self, *, query: str, action: Action, reason: str, layer: str, metadata: dict[str, Any]
    ) -> None:
        row = (
            str(uuid.uuid4()),
            datetime.now(UTC).isoformat(),
            query,
            action,
            reason,
            layer,
            json.dumps(metadata),
        )
        try:
            await asyncio.to_thread(
                self._run,
                "insert into requests (id, created_at, query, action, reason, layer, metadata)"
                " values (?, ?, ?, ?, ?, ?, ?)",
                row,
            )
        except sqlite3.Error:
            logger.exception("failed to write audit record")

    async def recent(self, limit: int) -> list[AuditRecord]:
        rows = await asyncio.to_thread(
            self._run,
            "select * from requests order by created_at desc, rowid desc limit ?",
            (limit,),
        )
        return [
            AuditRecord.model_validate(
                {
                    **dict(row),
                    "metadata": json.loads(row["metadata"]),
                    "reviewed": bool(row["reviewed"]),
                }
            )
            for row in rows
        ]

    async def stats(self) -> StatsResponse:
        (row,) = await asyncio.to_thread(
            self._run,
            "select count(*), coalesce(sum(action = 'BLOCKED'), 0) from requests",
        )
        return _stats(int(row[0]), int(row[1]))

    async def review(self, request_id: str, human_label: int) -> None:
        await asyncio.to_thread(
            self._run,
            "update requests set reviewed = 1, human_label = ?, action = ? where id = ?",
            (human_label, "BLOCKED" if human_label == 1 else "ALLOWED", request_id),
        )

    async def record_score(self, payload: ScoreCreateRequest) -> ScoreRecord:
        score_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        row = (
            score_id,
            now.isoformat(),
            payload.player_name,
            payload.level_id,
            payload.total_score,
            payload.medal,
            payload.attacks_blocked,
            payload.attacks_total,
            payload.false_alarms,
            payload.avg_latency_ms,
            payload.total_cost_usd,
            payload.board.model_dump_json(),
        )
        await asyncio.to_thread(
            self._run,
            "insert into scores (id, created_at, player_name, level_id, total_score, medal,"
            " attacks_blocked, attacks_total, false_alarms, avg_latency_ms,"
            " total_cost_usd, board_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        return ScoreRecord(id=score_id, created_at=now, **payload.model_dump())

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        if level_id:
            rows = await asyncio.to_thread(
                self._run,
                "select * from scores where level_id = ?"
                " order by total_score desc, avg_latency_ms asc, total_cost_usd asc, created_at asc"
                " limit ?",
                (level_id, limit),
            )
        else:
            rows = await asyncio.to_thread(
                self._run,
                "select * from scores"
                " order by total_score desc, avg_latency_ms asc, total_cost_usd asc, created_at asc"
                " limit ?",
                (limit,),
            )
        return [
            ScoreRecord(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                player_name=row["player_name"],
                level_id=row["level_id"],
                total_score=int(row["total_score"]),
                medal=row["medal"],
                attacks_blocked=int(row["attacks_blocked"]),
                attacks_total=int(row["attacks_total"]),
                false_alarms=int(row["false_alarms"]),
                avg_latency_ms=float(row["avg_latency_ms"]),
                total_cost_usd=float(row["total_cost_usd"]),
                board=BoardGraphSchema.model_validate_json(row["board_json"]),
            )
            for row in rows
        ]

    async def clear_scores(self) -> None:
        await asyncio.to_thread(self._run, "delete from scores")
