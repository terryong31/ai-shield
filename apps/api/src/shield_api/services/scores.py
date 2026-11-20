"""Leaderboard score stores (``game.scores``). The gateway owns persistence; the web
client never touches the database directly.

Scores recorded for a signed-in player carry their email (spec 0025), so each
account keeps its own best score per level even when display names collide.
Scores recorded before that have no email and are keyed by display name.
The email is never part of a ``ScoreRecord``, so the leaderboard never shows it.
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

from shield_api.schemas import (
    BoardGraphSchema,
    DifficultyLeaderboardEntry,
    DifficultyProgressSummary,
    LevelProgressItem,
    PlayerProgressResponse,
    ScoreCreateRequest,
    ScoreRecord,
)
from shield_api.services.sqlite import connect_domains
from shield_engine.game import (
    ALL_LEVEL_IDS,
    LEVEL_IDS_BY_DIFFICULTY,
    DifficultyCategory,
    LevelId,
    get_levels,
)

logger = logging.getLogger(__name__)

Backend = Literal["sqlite", "supabase", "memory"]


# Leaderboard scoring scale; bump when scores stop being comparable (spec 0021, 0039).
SCORE_VERSION = 3

_EMPTY_BOARD = BoardGraphSchema(nodes=[], edges=[])
_LEGACY_SUMMARY_COLUMNS = (
    "id,created_at,email,player_name,level_id,total_score,medal,"
    "attacks_blocked,attacks_total,false_alarms,avg_latency_ms,total_cost_usd,"
    "score_version"
)
_SUMMARY_COLUMNS = f"{_LEGACY_SUMMARY_COLUMNS},won,mastered"
_ALL_SCORES_KEY = "__all__"
_OWNED_SCORES_KEY = "__owned__"


def _is_missing_column_error(exc: Exception) -> bool:
    if getattr(exc, "code", None) == "42703":
        return True
    msg = str(exc)
    return "does not exist" in msg and ("won" in msg or "mastered" in msg)


def _rank(total: int, latency: float, cost: float) -> tuple[int, float, float]:
    return (total, -latency, -cost)


class ScoreStore(Protocol):
    @property
    def backend(self) -> Backend: ...

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord: ...

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]: ...

    async def clear_scores(self) -> None: ...

    async def delete_scores_for(self, email: str) -> int:
        """Delete every score owned by this email; returns how many were removed."""
        ...

    async def rename_scores_email(self, old: str, new: str) -> None: ...

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]: ...

    async def list_scores_for_owner(self, email: str) -> list[ScoreRecord]: ...


@dataclass
class _OwnedScore:
    record: ScoreRecord
    email: str | None


class InMemoryScoreStore:
    """Test double. Bounded and lost on restart, so never wired in production."""

    backend: ClassVar[Backend] = "memory"

    def __init__(self) -> None:
        self._scores: list[_OwnedScore] = []

    def _same_owner(self, row: _OwnedScore, payload: ScoreCreateRequest, email: str | None) -> bool:
        if row.record.level_id != payload.level_id:
            return False
        if email is not None:
            return row.email == email
        return row.email is None and row.record.player_name == payload.player_name

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord:
        existing_idx = next(
            (idx for idx, row in enumerate(self._scores) if self._same_owner(row, payload, email)),
            None,
        )
        entry = ScoreRecord(
            id=self._scores[existing_idx].record.id
            if existing_idx is not None
            else str(uuid.uuid4()),
            created_at=datetime.now(UTC),
            **payload.model_dump(),
        )
        if existing_idx is not None:
            prev = self._scores[existing_idx].record
            sticky_won = prev.won or payload.won
            sticky_mastered = prev.mastered or payload.mastered
            if _rank(entry.total_score, entry.avg_latency_ms, entry.total_cost_usd) >= _rank(
                prev.total_score, prev.avg_latency_ms, prev.total_cost_usd
            ):
                merged = entry.model_copy(update={"won": sticky_won, "mastered": sticky_mastered})
                self._scores[existing_idx] = _OwnedScore(merged, email)
                return merged
            if sticky_won != prev.won or sticky_mastered != prev.mastered:
                updated = prev.model_copy(update={"won": sticky_won, "mastered": sticky_mastered})
                self._scores[existing_idx] = _OwnedScore(updated, email)
                return updated
            return prev
        self._scores.append(_OwnedScore(entry, email))
        return entry

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        items = [
            row.record
            for row in self._scores
            if level_id is None or row.record.level_id == level_id
        ]
        items.sort(key=lambda s: (-s.total_score, s.avg_latency_ms, s.total_cost_usd, s.created_at))
        return items[:limit]

    async def clear_scores(self) -> None:
        self._scores.clear()

    async def delete_scores_for(self, email: str) -> int:
        kept = [row for row in self._scores if row.email != email]
        removed = len(self._scores) - len(kept)
        self._scores = kept
        return removed

    async def rename_scores_email(self, old: str, new: str) -> None:
        for row in self._scores:
            if row.email == old:
                row.email = new

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        return [(row.email, row.record) for row in self._scores]

    async def list_scores_for_owner(self, email: str) -> list[ScoreRecord]:
        return [row.record for row in self._scores if row.email == email]


class SupabaseScoreStore:
    """Stores leaderboard scores in ``game.scores``.

    The supabase-py client is synchronous, so calls run in a worker thread to
    keep the event loop free.
    """

    backend: ClassVar[Backend] = "supabase"
    SCORES_SCHEMA = "game"
    SCORES_TABLE = "scores"

    def __init__(self, client: Any) -> None:
        self._client = client
        self._has_mastery_columns = True

    def _scores(self) -> Any:
        return self._client.schema(self.SCORES_SCHEMA).table(self.SCORES_TABLE)

    def _execute_summary_query(self, make_query: Callable[[str], Any]) -> list[dict[str, Any]]:
        cols = _SUMMARY_COLUMNS if self._has_mastery_columns else _LEGACY_SUMMARY_COLUMNS
        try:
            response = make_query(cols).execute()
        except Exception as exc:
            if not (self._has_mastery_columns and _is_missing_column_error(exc)):
                raise
            self._has_mastery_columns = False
            logger.warning(
                "game.scores.won/mastered columns missing until migration "
                "20261119104405_campaign_levels_and_mastery.sql is applied; "
                "falling back to legacy summary columns."
            )
            response = make_query(_LEGACY_SUMMARY_COLUMNS).execute()
        return list(response.data or [])

    @staticmethod
    def _score_from_row(row: dict[str, Any]) -> ScoreRecord:
        board = row.get("board_json")
        if board is None:
            parsed_board = _EMPTY_BOARD
        elif isinstance(board, str):
            parsed_board = BoardGraphSchema.model_validate_json(board)
        else:
            parsed_board = BoardGraphSchema.model_validate(board)
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
            board=parsed_board,
            score_version=int(row["score_version"]),
            won=bool(row.get("won", False)),
            mastered=bool(row.get("mastered", False)),
        )

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord:
        """Keep each owner's best current-version score per level."""

        def write() -> ScoreRecord:
            query = (
                self._scores()
                .select("*")
                .eq("level_id", payload.level_id)
                .eq("score_version", SCORE_VERSION)
            )
            if email is not None:
                query = query.eq("email", email)
            else:
                query = query.eq("player_name", payload.player_name)
            rows = query.order("total_score", desc=True).execute().data or []
            if email is None:
                rows = [row for row in rows if row.get("email") is None]
            sticky_won = payload.won
            sticky_mastered = payload.mastered
            if rows:
                prev = self._score_from_row(rows[0])
                sticky_won = prev.won or payload.won
                sticky_mastered = prev.mastered or payload.mastered
                prev_rank = _rank(prev.total_score, prev.avg_latency_ms, prev.total_cost_usd)
                new_rank = _rank(
                    payload.total_score, payload.avg_latency_ms, payload.total_cost_usd
                )
                if new_rank < prev_rank:
                    if sticky_won != prev.won or sticky_mastered != prev.mastered:
                        self._scores().update({"won": sticky_won, "mastered": sticky_mastered}).eq(
                            "id", prev.id
                        ).execute()
                        return prev.model_copy(
                            update={"won": sticky_won, "mastered": sticky_mastered}
                        )
                    return prev
                self._scores().delete().eq("id", prev.id).execute()
            row = {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
                "email": email,
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
                "won": sticky_won,
                "mastered": sticky_mastered,
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

    async def delete_scores_for(self, email: str) -> int:
        response = await asyncio.to_thread(
            lambda: self._scores().delete().eq("email", email).execute()
        )
        return len(response.data or [])

    async def rename_scores_email(self, old: str, new: str) -> None:
        await asyncio.to_thread(
            lambda: self._scores().update({"email": new}).eq("email", old).execute()
        )

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        def read() -> list[dict[str, Any]]:
            return self._execute_summary_query(
                lambda cols: self._scores().select(cols).eq("score_version", SCORE_VERSION)
            )

        rows = await asyncio.to_thread(read)
        return [
            (str(r["email"]) if r.get("email") is not None else None, self._score_from_row(r))
            for r in rows
            if r.get("level_id") in ALL_LEVEL_IDS
        ]

    async def list_scores_for_owner(self, email: str) -> list[ScoreRecord]:
        def read() -> list[dict[str, Any]]:
            return self._execute_summary_query(
                lambda cols: (
                    self._scores()
                    .select(cols)
                    .eq("email", email)
                    .eq("score_version", SCORE_VERSION)
                )
            )

        return [
            self._score_from_row(r)
            for r in await asyncio.to_thread(read)
            if r.get("level_id") in ALL_LEVEL_IDS
        ]


class SqliteScoreStore:
    """Zero-setup durable store, used whenever Supabase is not configured.

    Mirrors the columns of ``game.scores`` in ``supabase/migrations`` through the
    attached domain databases (API-SCHEMA-006). Each call
    opens its own connection in a worker thread, so the event loop never
    blocks and no connection is shared across threads.
    """

    backend: ClassVar[Backend] = "sqlite"

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("pragma game.journal_mode = wal")
            # Mirrors the drop_audit_requests migration for databases created before spec 0026.
            connection.execute("drop table if exists audit.requests")
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
                  score_version   integer not null default 1,
                  email           text,
                  won             integer not null default 0,
                  mastered        integer not null default 0
                );
                create index if not exists game.scores_rank_idx
                  on scores (level_id, total_score desc, avg_latency_ms asc, total_cost_usd asc);
                """
            )
            columns = {row[1] for row in connection.execute("pragma game.table_info(scores)")}
            # Databases created before spec 0021 lack the column; their rows are version 1.
            if "score_version" not in columns:
                connection.execute(
                    "alter table game.scores add column score_version integer not null default 1"
                )
            # Databases created before spec 0025 have no owner column.
            if "email" not in columns:
                connection.execute("alter table game.scores add column email text")
            if "won" not in columns:
                connection.execute(
                    "alter table game.scores add column won integer not null default 0"
                )
            if "mastered" not in columns:
                connection.execute(
                    "alter table game.scores add column mastered integer not null default 0"
                )
            # Mirrors the rename_agent_review_to_llm_review migration.
            connection.execute(
                "update game.scores set board_json = "
                "replace(board_json, '\"agent_review\"', '\"llm_review\"') "
                "where board_json like '%\"agent_review\"%'"
            )
            # Spec 0039 purge of pre-campaign (< v3 or legacy level_id) rows, mirroring Supabase.
            connection.execute(
                "delete from game.scores where score_version < ? "
                "or level_id in ('easy', 'medium', 'hard')",
                (SCORE_VERSION,),
            )
            connection.execute(
                "create index if not exists game.scores_owner_idx"
                " on scores (email, level_id, score_version)"
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

    def _count(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        connection = self._connect()
        try:
            with connection:
                return connection.execute(sql, params).rowcount
        finally:
            connection.close()

    @staticmethod
    def _record(row: sqlite3.Row) -> ScoreRecord:
        return ScoreRecord(
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
            won=bool(row["won"]),
            mastered=bool(row["mastered"]),
        )

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord:
        if email is not None:
            owner_sql, owner = "email = ?", email
        else:
            owner_sql, owner = "email is null and player_name = ?", payload.player_name
        existing_rows = await asyncio.to_thread(
            self._run,
            f"select * from game.scores where {owner_sql} and level_id = ? and score_version = ?"  # noqa: S608
            " order by total_score desc, avg_latency_ms asc, total_cost_usd asc limit 1",
            (owner, payload.level_id, SCORE_VERSION),
        )
        now = datetime.now(UTC)
        sticky_won = payload.won
        sticky_mastered = payload.mastered
        if existing_rows:
            prev = existing_rows[0]
            prev_won = bool(prev["won"])
            prev_mastered = bool(prev["mastered"])
            sticky_won = prev_won or payload.won
            sticky_mastered = prev_mastered or payload.mastered
            prev_rank = _rank(
                int(prev["total_score"]),
                float(prev["avg_latency_ms"]),
                float(prev["total_cost_usd"]),
            )
            new_rank = _rank(payload.total_score, payload.avg_latency_ms, payload.total_cost_usd)
            if new_rank < prev_rank:
                if sticky_won != prev_won or sticky_mastered != prev_mastered:
                    await asyncio.to_thread(
                        self._run,
                        "update game.scores set won = ?, mastered = ? where id = ?",
                        (int(sticky_won), int(sticky_mastered), prev["id"]),
                    )
                    return self._record(prev).model_copy(
                        update={"won": sticky_won, "mastered": sticky_mastered}
                    )
                return self._record(prev)
            await asyncio.to_thread(
                self._run,
                f"delete from game.scores where {owner_sql} and level_id = ?"  # noqa: S608
                " and score_version = ?",
                (owner, payload.level_id, SCORE_VERSION),
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
            email,
            int(sticky_won),
            int(sticky_mastered),
        )
        await asyncio.to_thread(
            self._run,
            "insert into game.scores (id, created_at, player_name, level_id, total_score, medal,"
            " attacks_blocked, attacks_total, false_alarms, avg_latency_ms,"
            " total_cost_usd, board_json, score_version, email, won, mastered)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        return ScoreRecord(
            id=score_id,
            created_at=now,
            score_version=SCORE_VERSION,
            **{**payload.model_dump(), "won": sticky_won, "mastered": sticky_mastered},
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
        return [self._record(row) for row in rows]

    async def clear_scores(self) -> None:
        await asyncio.to_thread(self._run, "delete from game.scores")

    async def delete_scores_for(self, email: str) -> int:
        return await asyncio.to_thread(
            self._count, "delete from game.scores where email = ?", (email,)
        )

    async def rename_scores_email(self, old: str, new: str) -> None:
        await asyncio.to_thread(
            self._run, "update game.scores set email = ? where email = ?", (new, old)
        )

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        rows = await asyncio.to_thread(
            self._run,
            "select * from game.scores where score_version = ?",
            (SCORE_VERSION,),
        )
        return [
            (row["email"], self._record(row)) for row in rows if row["level_id"] in ALL_LEVEL_IDS
        ]

    async def list_scores_for_owner(self, email: str) -> list[ScoreRecord]:
        rows = await asyncio.to_thread(
            self._run,
            "select * from game.scores where email = ? and score_version = ?",
            (email, SCORE_VERSION),
        )
        return [self._record(row) for row in rows if row["level_id"] in ALL_LEVEL_IDS]


_LEVEL_IDS: tuple[str, ...] = ALL_LEVEL_IDS
_LEADERBOARD_CHANNEL = "leaderboard:events"
_CACHE_TTL_SECONDS = 3600


class LeaderboardNotifier(Protocol):
    async def publish(self, *, level_id: str | None, reason: str) -> None: ...

    def subscribe(self) -> AsyncIterator[dict[str, str | None]]: ...


class InMemoryNotifier:
    """In-process fan-out notifier used when Redis is not configured."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, str | None]]] = set()

    async def publish(self, *, level_id: str | None, reason: str) -> None:
        payload: dict[str, str | None] = {"level_id": level_id, "reason": reason}
        for queue in list(self._subscribers):
            queue.put_nowait(payload)

    async def subscribe(self) -> AsyncIterator[dict[str, str | None]]:
        queue: asyncio.Queue[dict[str, str | None]] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


class RedisPubSubNotifier:
    """Cross-worker leaderboard event broadcaster backed by Redis Pub/Sub."""

    def __init__(self, redis_client: Any, channel: str = _LEADERBOARD_CHANNEL) -> None:
        self._redis = redis_client
        self._channel = channel

    async def publish(self, *, level_id: str | None, reason: str) -> None:
        payload = json.dumps({"level_id": level_id, "reason": reason})
        try:
            await self._redis.publish(self._channel, payload)
        except Exception as exc:
            logger.warning("Redis publish failed; skipping notification: %s", exc)

    async def subscribe(self) -> AsyncIterator[dict[str, str | None]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel)
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    raw = message.get("data")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    if isinstance(raw, str):
                        data = json.loads(raw)
                        yield {
                            "level_id": data.get("level_id"),
                            "reason": str(data.get("reason", "updated")),
                        }
                else:
                    await asyncio.sleep(0.05)
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.aclose()


def _composite_score(record: ScoreRecord) -> float:
    # Pack total_score in the integer part and an inverted latency tie-breaker in the fraction.
    latency_tie = 1.0 - min(max(record.avg_latency_ms, 0.0), 999_999.0) / 1_000_000.0
    return float(record.total_score) + latency_tie


def _owner_key(player_name: str, email: str | None) -> str:
    return f"email:{email}" if email is not None else f"anon:{player_name}"


def _encode_owned(email: str | None, record: ScoreRecord) -> str:
    stripped = record.model_copy(update={"board": _EMPTY_BOARD})
    return json.dumps({"email": email, "record": stripped.model_dump(mode="json")})


def _decode_owned(raw: str) -> tuple[str | None, ScoreRecord]:
    data = json.loads(raw)
    raw_email = data.get("email")
    email = str(raw_email) if raw_email is not None else None
    return (email, ScoreRecord.model_validate(data["record"]))


class RedisCachedScoreStore:
    """Cache-aside / write-through Redis ZSET + HASH decorator over any ScoreStore."""

    def __init__(
        self,
        inner: ScoreStore,
        redis_client: Any,
        notifier: LeaderboardNotifier | None = None,
        *,
        ttl_seconds: int = _CACHE_TTL_SECONDS,
    ) -> None:
        self._inner = inner
        self._redis = redis_client
        self._notifier = notifier
        self._ttl = ttl_seconds
        self._hydrate_owned_lock = asyncio.Lock()
        self._hydrate_all_lock = asyncio.Lock()
        self._level_locks: dict[str, asyncio.Lock] = {}

    def _lock_for_level(self, level_id: str) -> asyncio.Lock:
        lock = self._level_locks.get(level_id)
        if lock is None:
            lock = asyncio.Lock()
            self._level_locks[level_id] = lock
        return lock

    @property
    def backend(self) -> Backend:
        return self._inner.backend

    @staticmethod
    def _zkey(level_id: str) -> str:
        return f"leaderboard:v{SCORE_VERSION}:z:{level_id}"

    @staticmethod
    def _records_key() -> str:
        return f"leaderboard:v{SCORE_VERSION}:records"

    @staticmethod
    def _owners_key(level_id: str) -> str:
        return f"leaderboard:v{SCORE_VERSION}:owners:{level_id}"

    @staticmethod
    def _hydrated_key() -> str:
        return f"leaderboard:v{SCORE_VERSION}:hydrated"

    @staticmethod
    def _owned_key() -> str:
        return f"leaderboard:v{SCORE_VERSION}:owned"

    async def _notify(self, *, level_id: str | None, reason: str) -> None:
        if self._notifier is not None:
            await self._notifier.publish(level_id=level_id, reason=reason)

    async def _hydrate_level(self, level_id: str, limit: int) -> list[ScoreRecord]:
        async with self._lock_for_level(level_id):
            try:
                cached = await self._read_level_from_cache(level_id, limit)
                if cached is not None:
                    return cached
            except Exception as exc:
                logger.warning("Redis read failed for %s; falling back: %s", level_id, exc)
                return await self._inner.list_scores(level_id=level_id, limit=limit)
            records = await self._inner.list_scores(level_id=level_id, limit=max(limit, 200))
            try:
                pipe = self._redis.pipeline(transaction=False)
                zkey = self._zkey(level_id)
                pipe.delete(zkey)
                if records:
                    pipe.zadd(zkey, {r.id: _composite_score(r) for r in records})
                    pipe.hset(
                        self._records_key(),
                        mapping={r.id: r.model_dump_json() for r in records},
                    )
                    pipe.expire(zkey, self._ttl)
                    pipe.expire(self._records_key(), self._ttl)
                pipe.hset(self._hydrated_key(), level_id, "1")
                pipe.expire(self._hydrated_key(), self._ttl)
                await pipe.execute()
            except Exception as exc:
                logger.warning("Redis hydration failed for %s: %s", level_id, exc)
            return records[:limit]

    async def _hydrate_all_scores(self, limit: int) -> list[ScoreRecord]:
        async with self._hydrate_all_lock:
            try:
                cached = await self._read_level_from_cache(_ALL_SCORES_KEY, limit)
                if cached is not None:
                    return cached
            except Exception as exc:
                logger.warning("Redis read failed for all levels; falling back: %s", exc)
                return await self._inner.list_scores(level_id=None, limit=limit)
            records = await self._inner.list_scores(level_id=None, limit=max(limit, 200))
            try:
                pipe = self._redis.pipeline(transaction=False)
                zkey = self._zkey(_ALL_SCORES_KEY)
                pipe.delete(zkey)
                if records:
                    pipe.zadd(zkey, {r.id: _composite_score(r) for r in records})
                    pipe.hset(
                        self._records_key(),
                        mapping={r.id: r.model_dump_json() for r in records},
                    )
                    pipe.expire(zkey, self._ttl)
                    pipe.expire(self._records_key(), self._ttl)
                pipe.hset(self._hydrated_key(), _ALL_SCORES_KEY, "1")
                pipe.expire(self._hydrated_key(), self._ttl)
                await pipe.execute()
            except Exception as exc:
                logger.warning("Redis all-scores hydration failed: %s", exc)
            return records[:limit]

    async def _read_level_from_cache(self, level_id: str, limit: int) -> list[ScoreRecord] | None:
        hydrated = await self._redis.hget(self._hydrated_key(), level_id)
        if hydrated != "1":
            return None
        ids = await self._redis.zrevrange(self._zkey(level_id), 0, limit + 19)
        if not ids:
            return []
        raw_records = await self._redis.hmget(self._records_key(), *ids)
        records = [ScoreRecord.model_validate_json(raw) for raw in raw_records if raw is not None]
        if len(records) < len(ids):
            return None
        records.sort(
            key=lambda s: (-s.total_score, s.avg_latency_ms, s.total_cost_usd, s.created_at)
        )
        return records[:limit]

    async def _read_owned_from_cache(self) -> list[tuple[str | None, ScoreRecord]] | None:
        hydrated = await self._redis.hget(self._hydrated_key(), _OWNED_SCORES_KEY)
        if hydrated != "1":
            return None
        raw_map = await self._redis.hgetall(self._owned_key())
        return [_decode_owned(raw) for raw in raw_map.values()]

    async def _hydrate_owned(self) -> list[tuple[str | None, ScoreRecord]]:
        async with self._hydrate_owned_lock:
            try:
                cached = await self._read_owned_from_cache()
                if cached is not None:
                    return cached
            except Exception as exc:
                logger.warning("Redis owned-scores cache check failed: %s", exc)
                return await self._inner.list_all_current_scores()
            owned_scores = await self._inner.list_all_current_scores()
            deduped: dict[str, tuple[str | None, ScoreRecord]] = {}
            for email, rec in owned_scores:
                field = f"{_owner_key(rec.player_name, email)}|{rec.level_id}"
                prev = deduped.get(field)
                if prev is None or _rank(
                    rec.total_score, rec.avg_latency_ms, rec.total_cost_usd
                ) >= _rank(prev[1].total_score, prev[1].avg_latency_ms, prev[1].total_cost_usd):
                    deduped[field] = (email, rec)
            result = list(deduped.values())
            try:
                pipe = self._redis.pipeline(transaction=False)
                pipe.delete(self._owned_key())
                mapping = {
                    field: _encode_owned(email, rec) for field, (email, rec) in deduped.items()
                }
                if mapping:
                    pipe.hset(self._owned_key(), mapping=mapping)
                    pipe.expire(self._owned_key(), self._ttl)
                pipe.hset(self._hydrated_key(), _OWNED_SCORES_KEY, "1")
                pipe.expire(self._hydrated_key(), self._ttl)
                await pipe.execute()
            except Exception as exc:
                logger.warning("Redis owned-scores hydration failed: %s", exc)
            return result

    async def warm_cache(self) -> None:
        """Warm the Redis owned-scores cache at startup without crashing on errors."""
        try:
            await self.list_all_current_scores()
        except Exception as exc:
            logger.warning("Redis cache warmup failed: %s", exc)

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord:
        record = await self._inner.record_score(payload, email=email)
        owner = _owner_key(payload.player_name, email)
        try:
            level_hydrated, owned_hydrated, all_hydrated = await self._redis.hmget(
                self._hydrated_key(), payload.level_id, _OWNED_SCORES_KEY, _ALL_SCORES_KEY
            )
            if level_hydrated != "1":
                await self._hydrate_level(payload.level_id, 200)
                pipe = self._redis.pipeline(transaction=False)
                pipe.hset(self._owners_key(payload.level_id), owner, record.id)
                pipe.expire(self._owners_key(payload.level_id), self._ttl)
                prev_id: str | None = None
            else:
                prev_id = await self._redis.hget(self._owners_key(payload.level_id), owner)
                pipe = self._redis.pipeline(transaction=False)
                if prev_id and prev_id != record.id:
                    pipe.zrem(self._zkey(payload.level_id), prev_id)
                    pipe.hdel(self._records_key(), prev_id)
                pipe.zadd(self._zkey(payload.level_id), {record.id: _composite_score(record)})
                pipe.hset(self._records_key(), record.id, record.model_dump_json())
                pipe.hset(self._owners_key(payload.level_id), owner, record.id)
                pipe.hset(self._hydrated_key(), payload.level_id, "1")
                pipe.expire(self._zkey(payload.level_id), self._ttl)
                pipe.expire(self._records_key(), self._ttl)
                pipe.expire(self._owners_key(payload.level_id), self._ttl)
                pipe.expire(self._hydrated_key(), self._ttl)

            if owned_hydrated == "1":
                pipe.hset(
                    self._owned_key(),
                    f"{owner}|{payload.level_id}",
                    _encode_owned(email, record),
                )
                pipe.expire(self._owned_key(), self._ttl)

            if all_hydrated == "1":
                if prev_id is not None:
                    if prev_id != record.id:
                        pipe.zrem(self._zkey(_ALL_SCORES_KEY), prev_id)
                    pipe.zadd(self._zkey(_ALL_SCORES_KEY), {record.id: _composite_score(record)})
                    pipe.expire(self._zkey(_ALL_SCORES_KEY), self._ttl)
                else:
                    pipe.hdel(self._hydrated_key(), _ALL_SCORES_KEY)

            await pipe.execute()
        except Exception as exc:
            logger.warning("Redis write-through failed on record_score: %s", exc)
        await self._notify(level_id=payload.level_id, reason="recorded")
        return record

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        target_key = level_id if level_id is not None else _ALL_SCORES_KEY
        try:
            cached = await self._read_level_from_cache(target_key, limit)
            if cached is not None:
                return cached
        except Exception as exc:
            logger.warning("Redis read failed for %s; falling back: %s", target_key, exc)
            return await self._inner.list_scores(level_id=level_id, limit=limit)
        if level_id is not None:
            return await self._hydrate_level(level_id, limit)
        return await self._hydrate_all_scores(limit)

    async def clear_scores(self) -> None:
        await self._inner.clear_scores()
        try:
            keys = [
                self._hydrated_key(),
                self._records_key(),
                self._owned_key(),
                self._zkey(_ALL_SCORES_KEY),
                *[self._zkey(lvl) for lvl in _LEVEL_IDS],
                *[self._owners_key(lvl) for lvl in _LEVEL_IDS],
            ]
            await self._redis.delete(*keys)
        except Exception as exc:
            logger.warning("Redis invalidation failed on clear_scores: %s", exc)
        await self._notify(level_id=None, reason="cleared")

    async def delete_scores_for(self, email: str) -> int:
        removed = await self._inner.delete_scores_for(email)
        if removed > 0:
            owner = _owner_key("", email)
            try:
                pipe = self._redis.pipeline(transaction=False)
                for lvl in _LEVEL_IDS:
                    score_id = await self._redis.hget(self._owners_key(lvl), owner)
                    if score_id:
                        pipe.zrem(self._zkey(lvl), score_id)
                        pipe.hdel(self._records_key(), score_id)
                        pipe.hdel(self._owners_key(lvl), owner)
                    else:
                        # If owner mapping wasn't cached yet, force re-hydration for this level.
                        pipe.hdel(self._hydrated_key(), lvl)
                pipe.hdel(self._owned_key(), *(f"{owner}|{lvl}" for lvl in _LEVEL_IDS))
                pipe.hdel(self._hydrated_key(), _ALL_SCORES_KEY)
                await pipe.execute()
            except Exception as exc:
                logger.warning("Redis invalidation failed on delete_scores_for: %s", exc)
            await self._notify(level_id=None, reason="deleted")
        return removed

    async def rename_scores_email(self, old: str, new: str) -> None:
        await self._inner.rename_scores_email(old, new)
        old_owner = _owner_key("", old)
        new_owner = _owner_key("", new)
        try:
            pipe = self._redis.pipeline(transaction=False)
            for lvl in _LEVEL_IDS:
                score_id = await self._redis.hget(self._owners_key(lvl), old_owner)
                if score_id:
                    pipe.hdel(self._owners_key(lvl), old_owner)
                    pipe.hset(self._owners_key(lvl), new_owner, score_id)
            pipe.delete(self._owned_key())
            pipe.hdel(self._hydrated_key(), _OWNED_SCORES_KEY, _ALL_SCORES_KEY)
            await pipe.execute()
        except Exception as exc:
            logger.warning("Redis owner rename failed: %s", exc)

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        try:
            cached = await self._read_owned_from_cache()
            if cached is not None:
                return cached
        except Exception as exc:
            logger.warning("Redis owned-scores read failed; falling back: %s", exc)
            return await self._inner.list_all_current_scores()
        return await self._hydrate_owned()

    async def list_scores_for_owner(self, email: str) -> list[ScoreRecord]:
        return await self._inner.list_scores_for_owner(email)


def aggregate_difficulty_leaderboard(
    owned_scores: list[tuple[str | None, ScoreRecord]],
    *,
    difficulty: DifficultyCategory | None = None,
    limit: int = 25,
) -> list[DifficultyLeaderboardEntry]:
    """Aggregate each player's best scores across all levels in ``difficulty`` (spec 0039)."""
    allowed_ids = (
        frozenset(LEVEL_IDS_BY_DIFFICULTY[difficulty])
        if difficulty is not None
        else frozenset(ALL_LEVEL_IDS)
    )
    levels_total = len(allowed_ids)
    diff_label: DifficultyCategory | Literal["All"] = (
        difficulty if difficulty is not None else "All"
    )
    by_owner: dict[str, dict[LevelId, ScoreRecord]] = {}
    for email, rec in owned_scores:
        if rec.level_id not in allowed_ids:
            continue
        owner = _owner_key(rec.player_name, email)
        per_level = by_owner.setdefault(owner, {})
        prev = per_level.get(rec.level_id)
        if prev is None or _rank(rec.total_score, rec.avg_latency_ms, rec.total_cost_usd) > _rank(
            prev.total_score, prev.avg_latency_ms, prev.total_cost_usd
        ):
            per_level[rec.level_id] = rec

    entries: list[DifficultyLeaderboardEntry] = []
    for per_level in by_owner.values():
        records = list(per_level.values())
        latest = max(records, key=lambda r: r.created_at)
        count = len(records)
        entries.append(
            DifficultyLeaderboardEntry(
                player_name=latest.player_name,
                difficulty=diff_label,
                total_score=sum(r.total_score for r in records),
                max_possible_score=levels_total * 10_000,
                levels_solved=sum(1 for r in records if r.won),
                levels_mastered=sum(1 for r in records if r.mastered),
                levels_total=levels_total,
                avg_latency_ms=round(sum(r.avg_latency_ms for r in records) / count, 2),
                total_cost_usd=round(sum(r.total_cost_usd for r in records), 6),
            )
        )
    entries.sort(
        key=lambda e: (
            -e.total_score,
            -e.levels_mastered,
            e.avg_latency_ms,
            e.total_cost_usd,
            e.player_name,
        )
    )
    return entries[:limit]


def build_player_progress(owned_scores: list[ScoreRecord]) -> PlayerProgressResponse:
    """Summarize the authenticated player's best score, win, and mastery across all 23 levels."""
    best_by_level: dict[LevelId, ScoreRecord] = {}
    for row in owned_scores:
        prev = best_by_level.get(row.level_id)
        if prev is None or _rank(row.total_score, row.avg_latency_ms, row.total_cost_usd) > _rank(
            prev.total_score, prev.avg_latency_ms, prev.total_cost_usd
        ):
            best_by_level[row.level_id] = row

    level_items: list[LevelProgressItem] = []
    for lvl in get_levels():
        best = best_by_level.get(lvl.id)
        level_items.append(
            LevelProgressItem(
                level_id=lvl.id,
                difficulty=lvl.difficulty,
                best_score=best.total_score if best else 0,
                medal=best.medal if best else "none",
                won=best.won if best else False,
                mastered=best.mastered if best else False,
            )
        )

    diff_order: tuple[DifficultyCategory, ...] = ("Easy", "Medium", "Hard")
    summaries: list[DifficultyProgressSummary] = []
    for diff in diff_order:
        cat_items = [item for item in level_items if item.difficulty == diff]
        total = len(cat_items)
        summaries.append(
            DifficultyProgressSummary(
                difficulty=diff,
                total_score=sum(item.best_score for item in cat_items),
                max_possible_score=total * 10_000,
                levels_solved=sum(1 for item in cat_items if item.won),
                levels_mastered=sum(1 for item in cat_items if item.mastered),
                levels_total=total,
            )
        )
    return PlayerProgressResponse(levels=level_items, difficulties=summaries)
