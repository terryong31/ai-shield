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
from shield_api.services.sqlite import connect_domains

logger = logging.getLogger(__name__)

Action = Literal["ALLOWED", "BLOCKED"]
Backend = Literal["sqlite", "supabase", "memory"]


# Leaderboard scoring scale; bump when scores stop being comparable (spec 0021).
SCORE_VERSION = 2


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
        existing_idx = next(
            (
                idx
                for idx, s in enumerate(self._scores)
                if s.player_name == payload.player_name and s.level_id == payload.level_id
            ),
            None,
        )
        entry = ScoreRecord(
            id=self._scores[existing_idx].id if existing_idx is not None else str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            **payload.model_dump(),
        )
        if existing_idx is not None:
            prev = self._scores[existing_idx]
            if (
                entry.total_score,
                -entry.avg_latency_ms,
                -entry.total_cost_usd,
            ) >= (
                prev.total_score,
                -prev.avg_latency_ms,
                -prev.total_cost_usd,
            ):
                self._scores[existing_idx] = entry
                return entry
            return prev
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
    """Stores audit records in ``audit.requests`` and leaderboard scores in ``game.scores``.

    The supabase-py client is synchronous, so calls run in a worker thread to
    keep the event loop free. Audit write failures are logged, not raised: losing
    an audit row must not break the user's request.
    """

    backend: ClassVar[Backend] = "supabase"
    SCHEMA = "audit"
    TABLE = "requests"
    SCORES_SCHEMA = "game"
    SCORES_TABLE = "scores"

    def __init__(self, client: Any) -> None:
        self._client = client

    def _requests(self) -> Any:
        return self._client.schema(self.SCHEMA).table(self.TABLE)

    def _scores(self) -> Any:
        return self._client.schema(self.SCORES_SCHEMA).table(self.SCORES_TABLE)

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
            await asyncio.to_thread(lambda: self._requests().insert(row).execute())
        except Exception:
            logger.exception("failed to write audit record")

    async def recent(self, limit: int) -> list[AuditRecord]:
        response = await asyncio.to_thread(
            lambda: (
                self._requests().select("*").order("created_at", desc=True).limit(limit).execute()
            )
        )
        return [AuditRecord.model_validate(row) for row in response.data or []]

    async def stats(self) -> StatsResponse:
        def count(action: str | None) -> int:
            query = self._requests().select("id", count="exact", head=True)
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
                lambda: self._requests().update(update).eq("id", request_id).execute()
            )
        except Exception:
            logger.exception("failed to update audit review")

    @staticmethod
    def _score_from_row(row: dict[str, Any]) -> ScoreRecord:
        board = row["board_json"]
        return ScoreRecord(
            id=str(row["id"]),
            created_at=row["created_at"],
            player_name=row["player_name"],
            level_id=row["level_id"],
            total_score=int(row["total_score"]),
            medal=row["medal"],
            attacks_blocked=int(row["attacks_blocked"]),
            attacks_total=int(row["attacks_total"]),
            false_alarms=int(row["false_alarms"]),
            avg_latency_ms=float(row["avg_latency_ms"]),
            total_cost_usd=float(row["total_cost_usd"]),
            board=(
                BoardGraphSchema.model_validate_json(board)
                if isinstance(board, str)
                else BoardGraphSchema.model_validate(board)
            ),
            score_version=int(row["score_version"]),
        )

    async def record_score(self, payload: ScoreCreateRequest) -> ScoreRecord:
        """Keep each player's best current-version score per level."""

        def write() -> ScoreRecord:
            existing = (
                self._scores()
                .select("*")
                .eq("player_name", payload.player_name)
                .eq("level_id", payload.level_id)
                .eq("score_version", SCORE_VERSION)
                .order("total_score", desc=True)
                .limit(1)
                .execute()
                .data
            )
            if existing:
                prev = self._score_from_row(existing[0])
                prev_rank = (prev.total_score, -prev.avg_latency_ms, -prev.total_cost_usd)
                new_rank = (payload.total_score, -payload.avg_latency_ms, -payload.total_cost_usd)
                if new_rank < prev_rank:
                    return prev
                self._scores().delete().eq("id", prev.id).execute()
            row = {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
                "player_name": payload.player_name,
                "level_id": payload.level_id,
                "total_score": payload.total_score,
                "medal": payload.medal,
                "attacks_blocked": payload.attacks_blocked,
                "attacks_total": payload.attacks_total,
                "false_alarms": payload.false_alarms,
                "avg_latency_ms": payload.avg_latency_ms,
                "total_cost_usd": payload.total_cost_usd,
                "board_json": payload.board.model_dump(mode="json"),
                "score_version": SCORE_VERSION,
            }
            self._scores().insert(row).execute()
            return self._score_from_row(row)

        return await asyncio.to_thread(write)

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        def read() -> list[dict[str, Any]]:
            query = self._scores().select("*").eq("score_version", SCORE_VERSION)
            if level_id:
                query = query.eq("level_id", level_id)
            response = (
                query.order("total_score", desc=True)
                .order("avg_latency_ms")
                .order("total_cost_usd")
                .order("created_at")
                .limit(limit)
                .execute()
            )
            return list(response.data or [])

        return [self._score_from_row(row) for row in await asyncio.to_thread(read)]

    async def clear_scores(self) -> None:
        # PostgREST refuses an unfiltered delete; every row has a total_score.
        await asyncio.to_thread(
            lambda: self._scores().delete().gte("total_score", -(2**31)).execute()
        )


class SqliteAuditLog:
    """Zero-setup durable store, used whenever Supabase is not configured.

    Mirrors the columns of ``audit.requests`` and ``game.scores`` in
    ``supabase/migrations`` through attached domain databases (API-SCHEMA-006). Each call
    opens its own connection in a worker thread, so the event loop never
    blocks and no connection is shared across threads.
    """

    backend: ClassVar[Backend] = "sqlite"
    _SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("pragma audit.journal_mode = wal")
            connection.execute("pragma game.journal_mode = wal")
            version = connection.execute("pragma audit.user_version").fetchone()[0]
            if version < self._SCHEMA_VERSION:
                connection.executescript(
                    """
                    create table if not exists audit.requests (
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
                    create index if not exists audit.requests_created_at_idx
                      on requests (created_at desc);
                    create index if not exists audit.requests_action_idx on requests (action);
                    pragma audit.user_version = 1;
                    """
                )
            connection.executescript(
                """
                create table if not exists game.scores (
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
                  board_json      text    not null,
                  score_version   integer not null default 1
                );
                create index if not exists game.scores_rank_idx
                  on scores (level_id, total_score desc, avg_latency_ms asc, total_cost_usd asc);
                """
            )
            # Databases created before spec 0021 lack the column; their rows are version 1.
            columns = {row[1] for row in connection.execute("pragma game.table_info(scores)")}
            if "score_version" not in columns:
                connection.execute(
                    "alter table game.scores add column score_version integer not null default 1"
                )

    def _connect(self) -> sqlite3.Connection:
        connection = connect_domains(self._path)
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
                "insert into audit.requests"
                " (id, created_at, query, action, reason, layer, metadata)"
                " values (?, ?, ?, ?, ?, ?, ?)",
                row,
            )
        except sqlite3.Error:
            logger.exception("failed to write audit record")

    async def recent(self, limit: int) -> list[AuditRecord]:
        rows = await asyncio.to_thread(
            self._run,
            "select * from audit.requests order by created_at desc, rowid desc limit ?",
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
            "select count(*), coalesce(sum(action = 'BLOCKED'), 0) from audit.requests",
        )
        return _stats(int(row[0]), int(row[1]))

    async def review(self, request_id: str, human_label: int) -> None:
        await asyncio.to_thread(
            self._run,
            "update audit.requests set reviewed = 1, human_label = ?, action = ? where id = ?",
            (human_label, "BLOCKED" if human_label == 1 else "ALLOWED", request_id),
        )

    async def record_score(self, payload: ScoreCreateRequest) -> ScoreRecord:
        existing_rows = await asyncio.to_thread(
            self._run,
            "select * from game.scores where player_name = ? and level_id = ? and score_version = ?"
            " order by total_score desc, avg_latency_ms asc, total_cost_usd asc limit 1",
            (payload.player_name, payload.level_id, SCORE_VERSION),
        )
        now = datetime.now(UTC)
        if existing_rows:
            prev = existing_rows[0]
            prev_rank = (
                int(prev["total_score"]),
                -float(prev["avg_latency_ms"]),
                -float(prev["total_cost_usd"]),
            )
            new_rank = (
                payload.total_score,
                -payload.avg_latency_ms,
                -payload.total_cost_usd,
            )
            if new_rank < prev_rank:
                return ScoreRecord(
                    id=prev["id"],
                    created_at=datetime.fromisoformat(prev["created_at"]),
                    player_name=prev["player_name"],
                    level_id=prev["level_id"],
                    total_score=int(prev["total_score"]),
                    medal=prev["medal"],
                    attacks_blocked=int(prev["attacks_blocked"]),
                    attacks_total=int(prev["attacks_total"]),
                    false_alarms=int(prev["false_alarms"]),
                    avg_latency_ms=float(prev["avg_latency_ms"]),
                    total_cost_usd=float(prev["total_cost_usd"]),
                    board=BoardGraphSchema.model_validate_json(prev["board_json"]),
                    score_version=int(prev["score_version"]),
                )
            await asyncio.to_thread(
                self._run,
                "delete from game.scores"
                " where player_name = ? and level_id = ? and score_version = ?",
                (payload.player_name, payload.level_id, SCORE_VERSION),
            )
        score_id = str(uuid.uuid4())
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
            SCORE_VERSION,
        )
        await asyncio.to_thread(
            self._run,
            "insert into game.scores (id, created_at, player_name, level_id, total_score, medal,"
            " attacks_blocked, attacks_total, false_alarms, avg_latency_ms,"
            " total_cost_usd, board_json, score_version)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        return ScoreRecord(
            id=score_id, created_at=now, score_version=SCORE_VERSION, **payload.model_dump()
        )

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        if level_id:
            rows = await asyncio.to_thread(
                self._run,
                "select * from game.scores where level_id = ? and score_version = ?"
                " order by total_score desc, avg_latency_ms asc, total_cost_usd asc, created_at asc"
                " limit ?",
                (level_id, SCORE_VERSION, limit),
            )
        else:
            rows = await asyncio.to_thread(
                self._run,
                "select * from game.scores where score_version = ?"
                " order by total_score desc, avg_latency_ms asc, total_cost_usd asc, created_at asc"
                " limit ?",
                (SCORE_VERSION, limit),
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
                score_version=int(row["score_version"]),
            )
            for row in rows
        ]

    async def clear_scores(self) -> None:
        await asyncio.to_thread(self._run, "delete from game.scores")
