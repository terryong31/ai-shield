"""Leaderboard score stores (``game.scores``). The gateway owns persistence; the web
client never touches the database directly.

Scores recorded for a signed-in player carry their email (spec 0025), so each
account keeps its own best score per level even when display names collide.
Scores recorded before that have no email and are keyed by display name.
The email is never part of a ``ScoreRecord``, so the leaderboard never shows it.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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
from shield_engine.game import (
    ALL_LEVEL_IDS,
    LEVEL_IDS_BY_DIFFICULTY,
    DifficultyCategory,
    LevelId,
    get_levels,
)

logger = logging.getLogger(__name__)

Backend = Literal["supabase", "memory"]


# Leaderboard scoring scale; bump when scores stop being comparable (spec 0021, 0039).
SCORE_VERSION = 3

_EMPTY_BOARD = BoardGraphSchema(nodes=[], edges=[])
_LEGACY_SUMMARY_COLUMNS = (
    "id,created_at,email,player_name,level_id,total_score,medal,"
    "attacks_blocked,attacks_total,false_alarms,avg_latency_ms,total_cost_usd,"
    "score_version"
)
_SUMMARY_COLUMNS = f"{_LEGACY_SUMMARY_COLUMNS},won,mastered"
_PAGE_SIZE = 1000


def _is_missing_column_error(exc: Exception) -> bool:
    if getattr(exc, "code", None) == "42703":
        return True
    msg = str(exc)
    return "does not exist" in msg and ("won" in msg or "mastered" in msg)


def _rank(total: int, latency: float, cost: float) -> tuple[int, float, float]:
    return (total, -latency, -cost)


def _replaces(
    prev_won: bool,
    prev_rank: tuple[int, float, float],
    new_won: bool,
    new_rank: tuple[int, float, float],
) -> bool:
    # A won run always outranks a lost one, so lost rounds never displace a win (spec 0039).
    if prev_won != new_won:
        return new_won
    return new_rank >= prev_rank


@dataclass(frozen=True)
class ScoreChange:
    """Stored best score before and after a write (spec 0044)."""

    previous: ScoreRecord | None
    current: ScoreRecord | None
    changed: bool


class ScoreStore(Protocol):
    @property
    def backend(self) -> Backend: ...

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord: ...

    async def record_score_change(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreChange: ...

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]: ...

    async def clear_scores(self) -> None: ...

    async def delete_scores_for(self, email: str) -> int:
        """Delete every score owned by this email; returns how many were removed."""
        ...

    async def rename_scores_email(self, old: str, new: str) -> None: ...

    async def rename_scores_player(self, email: str, player_name: str) -> None: ...

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

    async def record_score_change(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreChange:
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
            if _replaces(
                prev.won,
                _rank(prev.total_score, prev.avg_latency_ms, prev.total_cost_usd),
                payload.won,
                _rank(entry.total_score, entry.avg_latency_ms, entry.total_cost_usd),
            ):
                merged = entry.model_copy(update={"won": sticky_won, "mastered": sticky_mastered})
                self._scores[existing_idx] = _OwnedScore(merged, email)
                return ScoreChange(previous=prev, current=merged, changed=True)
            if sticky_won != prev.won or sticky_mastered != prev.mastered:
                updated = prev.model_copy(update={"won": sticky_won, "mastered": sticky_mastered})
                self._scores[existing_idx] = _OwnedScore(updated, email)
                return ScoreChange(previous=prev, current=updated, changed=True)
            return ScoreChange(previous=prev, current=prev, changed=False)
        self._scores.append(_OwnedScore(entry, email))
        return ScoreChange(previous=None, current=entry, changed=True)

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord:
        change = await self.record_score_change(payload, email=email)
        assert change.current is not None
        return change.current

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

    async def rename_scores_player(self, email: str, player_name: str) -> None:
        for row in self._scores:
            if row.email == email:
                row.record = row.record.model_copy(update={"player_name": player_name})

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

    async def record_score_change(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreChange:
        """Keep each owner's best current-version score per level and return what changed."""

        def write() -> ScoreChange:
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
            prev: ScoreRecord | None = None
            if rows:
                prev = self._score_from_row(rows[0])
                sticky_won = prev.won or payload.won
                sticky_mastered = prev.mastered or payload.mastered
                prev_rank = _rank(prev.total_score, prev.avg_latency_ms, prev.total_cost_usd)
                new_rank = _rank(
                    payload.total_score, payload.avg_latency_ms, payload.total_cost_usd
                )
                if not _replaces(prev.won, prev_rank, payload.won, new_rank):
                    if sticky_won != prev.won or sticky_mastered != prev.mastered:
                        self._scores().update({"won": sticky_won, "mastered": sticky_mastered}).eq(
                            "id", prev.id
                        ).execute()
                        updated = prev.model_copy(
                            update={"won": sticky_won, "mastered": sticky_mastered}
                        )
                        return ScoreChange(previous=prev, current=updated, changed=True)
                    return ScoreChange(previous=prev, current=prev, changed=False)
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
            return ScoreChange(previous=prev, current=self._score_from_row(row), changed=True)

        return await asyncio.to_thread(write)

    async def record_score(
        self, payload: ScoreCreateRequest, *, email: str | None = None
    ) -> ScoreRecord:
        change = await self.record_score_change(payload, email=email)
        assert change.current is not None
        return change.current

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

    async def rename_scores_player(self, email: str, player_name: str) -> None:
        await asyncio.to_thread(
            lambda: self._scores().update({"player_name": player_name}).eq("email", email).execute()
        )

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        def read() -> list[dict[str, Any]]:
            all_rows: list[dict[str, Any]] = []
            offset = 0
            while True:

                def page_query(cols: str, *, start: int = offset) -> Any:
                    return (
                        self._scores()
                        .select(cols)
                        .eq("score_version", SCORE_VERSION)
                        .order("id")
                        .range(start, start + _PAGE_SIZE - 1)
                    )

                page = self._execute_summary_query(page_query)
                all_rows.extend(page)
                if len(page) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE
            return all_rows

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


def _owner_key(player_name: str, email: str | None) -> str:
    return f"email:{email}" if email is not None else f"anon:{player_name}"


def aggregate_difficulty_leaderboard(
    owned_scores: list[tuple[str | None, ScoreRecord]],
    *,
    difficulty: DifficultyCategory | None = None,
    limit: int = 25,
) -> list[DifficultyLeaderboardEntry]:
    """Aggregate each player's best scores across all levels in ``difficulty`` (spec 0039, 0044)."""
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
        if rec.level_id not in allowed_ids or not rec.won:
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
        lat_milli = sum(round(r.avg_latency_ms * 1000) for r in records)
        cost_nano = sum(round(r.total_cost_usd * 1_000_000_000) for r in records)
        entries.append(
            DifficultyLeaderboardEntry(
                player_name=latest.player_name,
                difficulty=diff_label,
                total_score=sum(r.total_score for r in records),
                max_possible_score=levels_total * 10_000,
                levels_solved=sum(1 for r in records if r.won),
                levels_mastered=sum(1 for r in records if r.mastered),
                levels_total=levels_total,
                avg_latency_ms=round(lat_milli / 1000 / count, 2),
                total_cost_usd=round(cost_nano / 1_000_000_000, 6),
            )
        )
    entries = [e for e in entries if e.total_score > 0]
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
