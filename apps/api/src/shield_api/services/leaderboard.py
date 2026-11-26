"""Derived Redis sorted-set leaderboard service with single-flight rebuild and store fallback."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from shield_api.schemas import (
    DifficultyLeaderboardEntry,
    LeaderboardRankResponse,
    ScoreRecord,
)
from shield_api.services import scores as scores_mod
from shield_api.services.scores import (
    ScoreChange,
    ScoreStore,
    _owner_key,
    aggregate_difficulty_leaderboard,
)
from shield_engine.game import (
    ALL_LEVEL_IDS,
    LEVEL_IDS_BY_DIFFICULTY,
    DifficultyCategory,
    get_level,
)

logger = logging.getLogger(__name__)

BoardName = DifficultyCategory | Literal["All"]
ALL_BOARDS: tuple[BoardName, ...] = ("Easy", "Medium", "Hard", "All")

_PRIMARY_SCALE = 32
_LOCK_TTL_MS = 30_000
_WAIT_FOR_REBUILD_SECONDS = 2.0
_WAIT_POLL_INTERVAL_SECONDS = 0.05
_FALLBACK_CACHE_TTL_SECONDS = 10.0
_MAX_TIE_GROUP_FETCH = 250
_MAX_RANK_TIE_SCAN = 1000

_LUA_UPSERT = """-- op:upsert
local z_key = KEYS[1]
local h_key = KEYS[2]
local ready_key = KEYS[3]
local lock_key = KEYS[4]
local dirty_key = KEYS[5]

if redis.call("EXISTS", lock_key) == 1 then
  redis.call("SET", dirty_key, "1")
  return 0
end
if redis.call("EXISTS", ready_key) == 0 then
  return 0
end

local member = ARGV[1]
local d_primary = tonumber(ARGV[2])
local d_total = tonumber(ARGV[3])
local d_mastered = tonumber(ARGV[4])
local d_solved = tonumber(ARGV[5])
local d_lat = tonumber(ARGV[6])
local d_cost = tonumber(ARGV[7])
local new_name = ARGV[8]
local new_name_at = tonumber(ARGV[9])
local has_new_win = ARGV[10]

local new_solved = redis.call("HINCRBY", h_key, member .. ":solved", d_solved)
if new_solved <= 0 then
  redis.call("ZREM", z_key, member)
  redis.call(
    "HDEL",
    h_key,
    member .. ":name",
    member .. ":name_at",
    member .. ":total",
    member .. ":mastered",
    member .. ":solved",
    member .. ":lat_milli",
    member .. ":cost_nano"
  )
  return 1
end

redis.call("ZINCRBY", z_key, d_primary, member)
redis.call("HINCRBY", h_key, member .. ":total", d_total)
redis.call("HINCRBY", h_key, member .. ":mastered", d_mastered)
redis.call("HINCRBY", h_key, member .. ":lat_milli", d_lat)
redis.call("HINCRBY", h_key, member .. ":cost_nano", d_cost)

if has_new_win == "1" then
  local cur_at = tonumber(redis.call("HGET", h_key, member .. ":name_at") or "-1")
  if new_name_at >= cur_at then
    redis.call("HSET", h_key, member .. ":name", new_name, member .. ":name_at", ARGV[9])
  end
end
return 1
"""

_LUA_DELETE_MEMBER = """-- op:delete_member
local z_key = KEYS[1]
local h_key = KEYS[2]
local ready_key = KEYS[3]
local lock_key = KEYS[4]
local dirty_key = KEYS[5]
local member = ARGV[1]

if redis.call("EXISTS", lock_key) == 1 then
  redis.call("SET", dirty_key, "1")
  return 0
end
if redis.call("EXISTS", ready_key) == 0 then
  return 0
end

redis.call("ZREM", z_key, member)
redis.call(
  "HDEL",
  h_key,
  member .. ":name",
  member .. ":name_at",
  member .. ":total",
  member .. ":mastered",
  member .. ":solved",
  member .. ":lat_milli",
  member .. ":cost_nano"
)
return 1
"""

_LUA_SET_NAME = """-- op:set_name
local z_key = KEYS[1]
local h_key = KEYS[2]
local ready_key = KEYS[3]
local lock_key = KEYS[4]
local dirty_key = KEYS[5]

if redis.call("EXISTS", lock_key) == 1 then
  redis.call("SET", dirty_key, "1")
  return 0
end
if redis.call("EXISTS", ready_key) == 0 then
  return 0
end
if redis.call("ZSCORE", z_key, ARGV[1]) then
  redis.call("HSET", h_key, ARGV[1] .. ":name", ARGV[2])
end
return 1
"""

_LUA_RENAME_MEMBER = """-- op:rename_member
local z_key = KEYS[1]
local h_key = KEYS[2]
local ready_key = KEYS[3]
local lock_key = KEYS[4]
local dirty_key = KEYS[5]
local old_m = ARGV[1]
local new_m = ARGV[2]

if redis.call("EXISTS", lock_key) == 1 then
  redis.call("SET", dirty_key, "1")
  return 0
end
if redis.call("EXISTS", ready_key) == 0 then
  return 0
end

local score = redis.call("ZSCORE", z_key, old_m)
if not score then
  return 1
end
if redis.call("ZSCORE", z_key, new_m) then
  redis.call("DEL", ready_key)
  return 2
end

redis.call("ZADD", z_key, score, new_m)
redis.call("ZREM", z_key, old_m)
local suffixes = {"name", "name_at", "total", "mastered", "solved", "lat_milli", "cost_nano"}
for _, suf in ipairs(suffixes) do
  local val = redis.call("HGET", h_key, old_m .. ":" .. suf)
  if val then
    redis.call("HSET", h_key, new_m .. ":" .. suf, val)
    redis.call("HDEL", h_key, old_m .. ":" .. suf)
  end
end
return 1
"""

_LUA_UNLOCK = """-- op:unlock
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
"""


def owner_member_hash(player_name: str, email: str | None) -> str:
    return hashlib.sha256(_owner_key(player_name, email).encode("utf-8")).hexdigest()


def _board_name(difficulty: DifficultyCategory | None) -> BoardName:
    return difficulty if difficulty is not None else "All"


def _board_levels_total(board: BoardName) -> int:
    if board == "All":
        return len(ALL_LEVEL_IDS)
    return len(LEVEL_IDS_BY_DIFFICULTY[board])


def _entry_sort_key(entry: DifficultyLeaderboardEntry) -> tuple[int, int, float, str]:
    return scores_mod.leaderboard_sort_key(entry)


def _decode_member_entry(
    board: BoardName, levels_total: int, raw: list[str | None]
) -> DifficultyLeaderboardEntry | None:
    name, name_at, total_s, mastered_s, solved_s, lat_s, cost_s = raw
    if (
        name is None
        or total_s is None
        or mastered_s is None
        or solved_s is None
        or lat_s is None
        or cost_s is None
    ):
        return None
    solved = int(solved_s)
    total = int(total_s)
    if solved <= 0 or total <= 0:
        return None
    return DifficultyLeaderboardEntry(
        player_name=name,
        difficulty=board,
        total_score=total,
        max_possible_score=levels_total * 10_000,
        levels_solved=solved,
        levels_mastered=int(mastered_s),
        levels_total=levels_total,
        avg_latency_ms=round(int(lat_s) / 1000 / solved, 2),
        total_cost_usd=round(int(cost_s) / 1_000_000_000, 6),
        reached_at=datetime.fromtimestamp(float(name_at), UTC) if name_at else None,
    )


def _record_contribution(rec: ScoreRecord | None) -> tuple[int, int, int, int, int]:
    if rec is None or not rec.won:
        return (0, 0, 0, 0, 0)
    return (
        rec.total_score,
        1 if rec.mastered else 0,
        1,
        round(rec.avg_latency_ms * 1000),
        round(rec.total_cost_usd * 1_000_000_000),
    )


class LeaderboardService:
    """Derived Redis ZSET+HASH leaderboard index with single-flight rebuild and store fallback."""

    def __init__(
        self,
        store: ScoreStore,
        redis_client: Any = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._redis = redis_client
        self._clock: Callable[[], float] = clock or time.monotonic
        self._script_shas: dict[str, str] = {}
        self._fallback_rows: list[tuple[str | None, ScoreRecord]] | None = None
        self._fallback_fetched_at: float | None = None
        self._fallback_lock = asyncio.Lock()

    @staticmethod
    def _prefix() -> str:
        return f"lb:v{scores_mod.SCORE_VERSION}:"

    @classmethod
    def _keys(cls, board: BoardName) -> tuple[str, str, str, str, str]:
        prefix = cls._prefix()
        return (
            f"{prefix}z:{board}",
            f"{prefix}d:{board}",
            f"{prefix}ready:{board}",
            f"{prefix}lock:{board}",
            f"{prefix}dirty:{board}",
        )

    def _invalidate_fallback_cache(self) -> None:
        self._fallback_rows = None
        self._fallback_fetched_at = None

    async def _fallback_owned_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        now = self._clock()
        if (
            self._fallback_rows is not None
            and self._fallback_fetched_at is not None
            and now - self._fallback_fetched_at < _FALLBACK_CACHE_TTL_SECONDS
        ):
            return self._fallback_rows
        async with self._fallback_lock:
            now = self._clock()
            if (
                self._fallback_rows is not None
                and self._fallback_fetched_at is not None
                and now - self._fallback_fetched_at < _FALLBACK_CACHE_TTL_SECONDS
            ):
                return self._fallback_rows
            rows = await self._store.list_all_current_scores()
            self._fallback_rows = rows
            self._fallback_fetched_at = self._clock()
            return rows

    async def _eval_script(self, script: str, numkeys: int, *keys_and_args: str) -> Any:
        sha = self._script_shas.get(script)
        if sha is None:
            sha = await self._redis.script_load(script)
            self._script_shas[script] = sha
        try:
            return await self._redis.evalsha(sha, numkeys, *keys_and_args)
        except Exception as exc:
            if "NOSCRIPT" not in str(exc):
                raise
            sha = await self._redis.script_load(script)
            self._script_shas[script] = sha
            return await self._redis.evalsha(sha, numkeys, *keys_and_args)

    async def _ensure_board_ready(self, board: BoardName) -> bool:
        """Ensure ``ready:<board>`` exists, rebuilding single-flight if missing.

        Returns False if another instance holds the rebuild and we timed out waiting.
        """
        z_key, d_key, ready_key, lock_key, dirty_key = self._keys(board)
        if await self._redis.get(ready_key) == "1":
            return True

        token = str(uuid.uuid4())
        acquired = await self._redis.set(lock_key, token, nx=True, px=_LOCK_TTL_MS)
        if not acquired:
            deadline = self._clock() + _WAIT_FOR_REBUILD_SECONDS
            while self._clock() < deadline:
                if await self._redis.get(ready_key) == "1":
                    return True
                await asyncio.sleep(_WAIT_POLL_INTERVAL_SECONDS)
            return False

        try:
            if await self._redis.get(ready_key) == "1":
                return True
            await self._rebuild_board(board, z_key, d_key, ready_key, dirty_key)
            return True
        finally:
            try:
                await self._eval_script(_LUA_UNLOCK, 1, lock_key, token)
            except Exception as exc:
                logger.warning("Failed to release rebuild lock for %s: %s", board, exc)

    async def _rebuild_board(
        self, board: BoardName, z_key: str, d_key: str, ready_key: str, dirty_key: str
    ) -> None:
        owned_scores = await self._store.list_all_current_scores()
        allowed = (
            frozenset(ALL_LEVEL_IDS)
            if board == "All"
            else frozenset(LEVEL_IDS_BY_DIFFICULTY[board])
        )
        per_member: dict[str, dict[str, ScoreRecord]] = {}
        for email, rec in owned_scores:
            if rec.level_id not in allowed or not rec.won:
                continue
            member = owner_member_hash(rec.player_name, email)
            levels = per_member.setdefault(member, {})
            prev = levels.get(rec.level_id)
            if prev is None or scores_mod._rank(
                rec.total_score, rec.avg_latency_ms, rec.total_cost_usd
            ) > scores_mod._rank(prev.total_score, prev.avg_latency_ms, prev.total_cost_usd):
                levels[rec.level_id] = rec

        z_mapping: dict[str, float] = {}
        h_mapping: dict[str, str] = {}
        for member, levels in per_member.items():
            recs = list(levels.values())
            latest = max(recs, key=lambda r: r.created_at)
            total = sum(r.total_score for r in recs)
            mastered = sum(1 for r in recs if r.mastered)
            solved = len(recs)
            lat_milli = sum(round(r.avg_latency_ms * 1000) for r in recs)
            cost_nano = sum(round(r.total_cost_usd * 1_000_000_000) for r in recs)
            z_mapping[member] = float(total * _PRIMARY_SCALE + mastered)
            h_mapping[f"{member}:name"] = latest.player_name
            h_mapping[f"{member}:name_at"] = f"{latest.created_at.timestamp():.6f}"
            h_mapping[f"{member}:total"] = str(total)
            h_mapping[f"{member}:mastered"] = str(mastered)
            h_mapping[f"{member}:solved"] = str(solved)
            h_mapping[f"{member}:lat_milli"] = str(lat_milli)
            h_mapping[f"{member}:cost_nano"] = str(cost_nano)

        suffix = uuid.uuid4().hex[:12]
        tmp_z = f"{self._prefix()}tmp:z:{board}:{suffix}"
        tmp_h = f"{self._prefix()}tmp:d:{board}:{suffix}"

        pipe = self._redis.pipeline(transaction=True)
        pipe.delete(z_key, d_key)
        if z_mapping:
            pipe.zadd(tmp_z, z_mapping)
            pipe.rename(tmp_z, z_key)
        if h_mapping:
            pipe.hset(tmp_h, mapping=h_mapping)
            pipe.rename(tmp_h, d_key)
        pipe.set(ready_key, "1")
        await pipe.execute()

        if await self._redis.get(dirty_key) is not None:
            await self._redis.delete(dirty_key, ready_key)

    async def _fetch_member_entries(
        self, board: BoardName, d_key: str, members: list[str]
    ) -> list[tuple[str, DifficultyLeaderboardEntry]]:
        if not members:
            return []
        fields: list[str] = []
        for m in members:
            fields.extend(
                (
                    f"{m}:name",
                    f"{m}:name_at",
                    f"{m}:total",
                    f"{m}:mastered",
                    f"{m}:solved",
                    f"{m}:lat_milli",
                    f"{m}:cost_nano",
                )
            )
        raw_values = await self._redis.hmget(d_key, *fields)
        levels_total = _board_levels_total(board)
        paired: list[tuple[str, DifficultyLeaderboardEntry]] = []
        for idx, m in enumerate(members):
            chunk = raw_values[idx * 7 : (idx + 1) * 7]
            entry = _decode_member_entry(board, levels_total, chunk)
            if entry is not None:
                paired.append((m, entry))
        return paired

    async def _fetch_entries_for_members(
        self, board: BoardName, d_key: str, members: list[str]
    ) -> list[DifficultyLeaderboardEntry]:
        return [entry for _, entry in await self._fetch_member_entries(board, d_key, members)]

    async def get_leaderboard(
        self,
        *,
        difficulty: DifficultyCategory | None = None,
        limit: int = 25,
    ) -> list[DifficultyLeaderboardEntry]:
        if self._redis is None:
            owned = await self._fallback_owned_scores()
            return aggregate_difficulty_leaderboard(owned, difficulty=difficulty, limit=limit)

        board = _board_name(difficulty)
        z_key, d_key, _, _, _ = self._keys(board)
        try:
            if not await self._ensure_board_ready(board):
                owned = await self._fallback_owned_scores()
                return aggregate_difficulty_leaderboard(owned, difficulty=difficulty, limit=limit)

            top = await self._redis.zrevrangebyscore(
                z_key, "+inf", _PRIMARY_SCALE, start=0, num=limit, withscores=True
            )
            if not top:
                return []

            members = [str(m) for m, _ in top]
            if len(top) == limit:
                boundary = int(top[-1][1])
                ties = await self._redis.zrangebyscore(
                    z_key, boundary, boundary, start=0, num=_MAX_TIE_GROUP_FETCH
                )
                seen = set(members)
                for m in ties:
                    ms = str(m)
                    if ms not in seen:
                        members.append(ms)
                        seen.add(ms)

            entries = await self._fetch_entries_for_members(board, d_key, members)
            entries.sort(key=_entry_sort_key)
            return entries[:limit]
        except Exception as exc:
            logger.warning("Redis leaderboard read failed for %s; falling back: %s", board, exc)
            owned = await self._fallback_owned_scores()
            return aggregate_difficulty_leaderboard(owned, difficulty=difficulty, limit=limit)

    async def get_player_rank(
        self,
        email: str,
        *,
        difficulty: DifficultyCategory = "Easy",
    ) -> LeaderboardRankResponse:
        member = owner_member_hash("", email)
        if self._redis is not None:
            board = _board_name(difficulty)
            z_key, d_key, ready_key, _, _ = self._keys(board)
            try:
                if await self._ensure_board_ready(board):
                    score = await self._redis.zscore(z_key, member)
                    if score is None or int(score) < _PRIMARY_SCALE:
                        return LeaderboardRankResponse(
                            difficulty=difficulty, rank=None, total_score=None
                        )
                    primary = int(score)
                    higher = int(await self._redis.zcount(z_key, f"({primary}", "+inf"))
                    page = [
                        str(m)
                        for m in await self._redis.zrangebyscore(
                            z_key, primary, primary, start=0, num=_MAX_TIE_GROUP_FETCH
                        )
                    ]
                    paired0 = await self._fetch_member_entries(board, d_key, page)
                    caller_entry = next((entry for m, entry in paired0 if m == member), None)
                    if caller_entry is None:
                        own_paired = await self._fetch_member_entries(board, d_key, [member])
                        if own_paired:
                            caller_entry = own_paired[0][1]
                    if caller_entry is None:
                        await self._redis.delete(ready_key)
                    else:
                        caller_key = _entry_sort_key(caller_entry)
                        better = sum(
                            1
                            for m, entry in paired0
                            if m != member and _entry_sort_key(entry) < caller_key
                        )
                        sampled_others = sum(1 for m, _ in paired0 if m != member)
                        offset = _MAX_TIE_GROUP_FETCH
                        while len(page) == _MAX_TIE_GROUP_FETCH and offset < _MAX_RANK_TIE_SCAN:
                            page = [
                                str(m)
                                for m in await self._redis.zrangebyscore(
                                    z_key,
                                    primary,
                                    primary,
                                    start=offset,
                                    num=_MAX_TIE_GROUP_FETCH,
                                )
                            ]
                            if not page:
                                break
                            paired_page = await self._fetch_member_entries(board, d_key, page)
                            better += sum(
                                1
                                for m, entry in paired_page
                                if m != member and _entry_sort_key(entry) < caller_key
                            )
                            sampled_others += sum(1 for m, _ in paired_page if m != member)
                            offset += _MAX_TIE_GROUP_FETCH
                        if len(page) == _MAX_TIE_GROUP_FETCH and sampled_others > 0:
                            total_tied = int(await self._redis.zcount(z_key, primary, primary))
                            other_ties = max(sampled_others, total_tied - 1)
                            better = round(better * other_ties / sampled_others)
                        return LeaderboardRankResponse(
                            difficulty=difficulty,
                            rank=1 + higher + better,
                            total_score=caller_entry.total_score,
                        )
            except Exception as exc:
                logger.warning("Redis rank lookup failed for %s; falling back: %s", board, exc)

        owned = await self._fallback_owned_scores()
        all_entries = aggregate_difficulty_leaderboard(
            owned, difficulty=difficulty, limit=max(len(owned), 1)
        )
        # Re-resolve member's player_name from current store rows for exact match
        owner_recs = [
            rec
            for row_email, rec in owned
            if row_email == email
            and rec.won
            and rec.level_id in LEVEL_IDS_BY_DIFFICULTY[difficulty]
        ]
        if not owner_recs:
            return LeaderboardRankResponse(difficulty=difficulty, rank=None, total_score=None)
        best_total = sum(r.total_score for r in owner_recs)
        if best_total <= 0:
            return LeaderboardRankResponse(difficulty=difficulty, rank=None, total_score=None)
        latest_name = max(owner_recs, key=lambda r: r.created_at).player_name
        for idx, entry in enumerate(all_entries, start=1):
            if entry.player_name == latest_name and entry.total_score == best_total:
                return LeaderboardRankResponse(
                    difficulty=difficulty, rank=idx, total_score=entry.total_score
                )
        return LeaderboardRankResponse(difficulty=difficulty, rank=None, total_score=None)

    async def on_score_recorded(self, email: str | None, change: ScoreChange) -> None:
        if not change.changed:
            return
        self._invalidate_fallback_cache()
        if self._redis is None:
            return
        ref = change.current or change.previous
        if ref is None:
            return
        prev_c = _record_contribution(change.previous)
        curr_c = _record_contribution(change.current)
        if prev_c == (0, 0, 0, 0, 0) and curr_c == (0, 0, 0, 0, 0):
            return

        d_total = curr_c[0] - prev_c[0]
        d_mastered = curr_c[1] - prev_c[1]
        d_solved = curr_c[2] - prev_c[2]
        d_lat = curr_c[3] - prev_c[3]
        d_cost = curr_c[4] - prev_c[4]
        d_primary = d_total * _PRIMARY_SCALE + d_mastered

        has_new_win = change.current is not None and change.current.won
        if (d_primary, d_total, d_mastered, d_solved, d_lat, d_cost) == (
            0,
            0,
            0,
            0,
            0,
            0,
        ) and not has_new_win:
            return

        member = owner_member_hash(ref.player_name, email)
        new_name = change.current.player_name if change.current is not None else ref.player_name
        new_name_at = (
            f"{change.current.created_at.timestamp():.6f}"
            if change.current is not None
            else f"{ref.created_at.timestamp():.6f}"
        )
        level_diff: DifficultyCategory = get_level(ref.level_id).difficulty
        boards: tuple[BoardName, ...] = (level_diff, "All")

        for board in boards:
            z_key, d_key, ready_key, lock_key, dirty_key = self._keys(board)
            try:
                await self._eval_script(
                    _LUA_UPSERT,
                    5,
                    z_key,
                    d_key,
                    ready_key,
                    lock_key,
                    dirty_key,
                    member,
                    str(d_primary),
                    str(d_total),
                    str(d_mastered),
                    str(d_solved),
                    str(d_lat),
                    str(d_cost),
                    new_name,
                    new_name_at,
                    "1" if has_new_win else "0",
                )
            except Exception as exc:
                logger.warning("Redis leaderboard upsert failed for %s: %s", board, exc)
                try:
                    await self._redis.delete(ready_key)
                except Exception as del_exc:
                    logger.warning("Failed to clear ready key for %s: %s", board, del_exc)

    async def on_scores_cleared(self) -> None:
        self._invalidate_fallback_cache()
        if self._redis is None:
            return
        keys_to_delete: list[str] = []
        ready_keys: list[str] = []
        for board in ALL_BOARDS:
            z_key, d_key, ready_key, lock_key, dirty_key = self._keys(board)
            keys_to_delete.extend((z_key, d_key, lock_key, dirty_key))
            ready_keys.append(ready_key)
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.delete(*keys_to_delete)
            for rk in ready_keys:
                pipe.set(rk, "1")
            await pipe.execute()
        except Exception as exc:
            logger.warning("Redis leaderboard clear failed: %s", exc)
            for rk in ready_keys:
                with contextlib.suppress(Exception):
                    await self._redis.delete(rk)

    async def on_owner_deleted(self, email: str) -> None:
        self._invalidate_fallback_cache()
        if self._redis is None:
            return
        member = owner_member_hash("", email)
        for board in ALL_BOARDS:
            z_key, d_key, ready_key, lock_key, dirty_key = self._keys(board)
            try:
                await self._eval_script(
                    _LUA_DELETE_MEMBER,
                    5,
                    z_key,
                    d_key,
                    ready_key,
                    lock_key,
                    dirty_key,
                    member,
                )
            except Exception as exc:
                logger.warning("Redis leaderboard delete failed for %s: %s", board, exc)
                with contextlib.suppress(Exception):
                    await self._redis.delete(ready_key)

    async def on_display_name_changed(self, email: str, player_name: str) -> None:
        """Show the new name on every board without changing rank (spec 0048)."""
        self._invalidate_fallback_cache()
        if self._redis is None:
            return
        member = owner_member_hash("", email)
        for board in ALL_BOARDS:
            z_key, d_key, ready_key, lock_key, dirty_key = self._keys(board)
            try:
                await self._eval_script(
                    _LUA_SET_NAME,
                    5,
                    z_key,
                    d_key,
                    ready_key,
                    lock_key,
                    dirty_key,
                    member,
                    player_name,
                )
            except Exception as exc:
                logger.warning("Redis display name update failed for %s: %s", board, exc)
                with contextlib.suppress(Exception):
                    await self._redis.delete(ready_key)

    async def on_owner_renamed(self, old_email: str, new_email: str) -> None:
        self._invalidate_fallback_cache()
        if self._redis is None:
            return
        old_m = owner_member_hash("", old_email)
        new_m = owner_member_hash("", new_email)
        for board in ALL_BOARDS:
            z_key, d_key, ready_key, lock_key, dirty_key = self._keys(board)
            try:
                await self._eval_script(
                    _LUA_RENAME_MEMBER,
                    5,
                    z_key,
                    d_key,
                    ready_key,
                    lock_key,
                    dirty_key,
                    old_m,
                    new_m,
                )
            except Exception as exc:
                logger.warning("Redis leaderboard rename failed for %s: %s", board, exc)
                with contextlib.suppress(Exception):
                    await self._redis.delete(ready_key)
