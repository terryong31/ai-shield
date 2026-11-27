"""Scores of anonymous players, kept on the server until they sign in (spec 0052).

Rows are keyed by the SHA-256 hash of the ``HttpOnly`` session token, so the browser
cannot forge them. They never reach the public leaderboard: sign-in moves them into
``game.scores`` and deletes them.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from shield_api.schemas import ScoreCreateRequest, ScoreRecord
from shield_api.services.scores import SCORE_VERSION, best_of

ANONYMOUS_SCORE_TTL = timedelta(days=7)


def pending_score_record(payload: ScoreCreateRequest) -> ScoreRecord:
    """A pending anonymous score shaped for ``build_player_progress``."""
    return ScoreRecord(id="pending", created_at=datetime.now(UTC), **payload.model_dump())


class AnonymousScoreStore(Protocol):
    async def record(
        self, session_hash: str, payload: ScoreCreateRequest, *, ttl: timedelta
    ) -> None: ...

    async def list_for(self, session_hash: str) -> list[ScoreCreateRequest]: ...

    async def delete_for(self, session_hash: str) -> None: ...


@dataclass
class _Row:
    payload: ScoreCreateRequest
    expires_at: datetime


@dataclass
class InMemoryAnonymousScoreStore:
    """Test double and local fallback."""

    _rows: dict[tuple[str, str, int], _Row] = field(default_factory=dict)

    async def record(
        self, session_hash: str, payload: ScoreCreateRequest, *, ttl: timedelta
    ) -> None:
        key = (session_hash, payload.level_id, SCORE_VERSION)
        now = datetime.now(UTC)
        previous = self._rows.get(key)
        kept = previous.payload if previous and previous.expires_at > now else None
        self._rows[key] = _Row(best_of(kept, payload), now + ttl)

    async def list_for(self, session_hash: str) -> list[ScoreCreateRequest]:
        now = datetime.now(UTC)
        return [
            row.payload
            for (owner, _, version), row in self._rows.items()
            if owner == session_hash and version == SCORE_VERSION and row.expires_at > now
        ]

    async def delete_for(self, session_hash: str) -> None:
        for key in [key for key in self._rows if key[0] == session_hash]:
            del self._rows[key]


_COLUMNS = (
    "level_id,total_score,medal,attacks_blocked,attacks_total,false_alarms,"
    "avg_latency_ms,total_cost_usd,board_json,won,mastered,player_name"
)


class SupabaseAnonymousScoreStore:
    """``game.anonymous_scores``: service role only, RLS deny-all for every other role."""

    SCHEMA = "game"
    TABLE = "anonymous_scores"

    def __init__(self, client: Any) -> None:
        self._client = client

    def _table(self) -> Any:
        return self._client.schema(self.SCHEMA).table(self.TABLE)

    @staticmethod
    def _payload(row: dict[str, Any]) -> ScoreCreateRequest:
        fields = {key: value for key, value in row.items() if key != "board_json"}
        fields["board"] = row["board_json"]
        fields["player_name"] = row.get("player_name") or "Player"
        return ScoreCreateRequest.model_validate(fields)

    def _read(self, session_hash: str, level_id: str | None = None) -> list[dict[str, Any]]:
        query = (
            self._table()
            .select(_COLUMNS)
            .eq("session_token_hash", session_hash)
            .eq("score_version", SCORE_VERSION)
            .gte("expires_at", datetime.now(UTC).isoformat())
        )
        if level_id is not None:
            query = query.eq("level_id", level_id)
        return list(query.execute().data or [])

    async def record(
        self, session_hash: str, payload: ScoreCreateRequest, *, ttl: timedelta
    ) -> None:
        def write() -> None:
            rows = self._read(session_hash, payload.level_id)
            kept = best_of(self._payload(rows[0]) if rows else None, payload)
            now = datetime.now(UTC)
            self._table().upsert(
                {
                    **kept.model_dump(mode="json", exclude={"board"}),
                    "board_json": kept.board.model_dump(mode="json"),
                    "session_token_hash": session_hash,
                    "score_version": SCORE_VERSION,
                    "created_at": now.isoformat(),
                    "expires_at": (now + ttl).isoformat(),
                },
                on_conflict="session_token_hash,level_id,score_version",
            ).execute()

        await asyncio.to_thread(write)

    async def list_for(self, session_hash: str) -> list[ScoreCreateRequest]:
        rows = await asyncio.to_thread(self._read, session_hash)
        return [self._payload(row) for row in rows]

    async def delete_for(self, session_hash: str) -> None:
        await asyncio.to_thread(
            lambda: self._table().delete().eq("session_token_hash", session_hash).execute()
        )
