"""Tests for Redis sorted-set leaderboard read scaling & my-rank (spec 0044)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from shield_api.openapi import render as render_openapi
from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest, ScoreRecord
from shield_api.services import leaderboard as leaderboard_mod
from shield_api.services import scores as scores_mod
from shield_api.services.leaderboard import LeaderboardService
from shield_api.services.scores import (
    InMemoryScoreStore,
    SupabaseScoreStore,
    aggregate_difficulty_leaderboard,
)
from shield_engine.game import LEVEL_IDS_BY_DIFFICULTY

from .conftest import FakeClock, Harness


def _empty_board() -> BoardGraphSchema:
    return BoardGraphSchema(nodes=[], edges=[])


def _req(
    player_name: str,
    *,
    level_id: str = "easy-1",
    total_score: int = 5000,
    avg_latency_ms: float = 10.0,
    total_cost_usd: float = 0.01,
    won: bool = True,
    mastered: bool = False,
) -> ScoreCreateRequest:
    return ScoreCreateRequest(
        player_name=player_name,
        level_id=level_id,  # type: ignore[arg-type]
        total_score=total_score,
        medal="gold" if won else "none",
        attacks_blocked=5 if won else 1,
        attacks_total=5,
        false_alarms=0,
        avg_latency_ms=avg_latency_ms,
        total_cost_usd=total_cost_usd,
        board=_empty_board(),
        won=won,
        mastered=mastered,
    )


class NoScriptError(Exception):
    pass


def _parse_bound(raw: str | float | int) -> tuple[float, bool]:
    if isinstance(raw, int | float):
        return (float(raw), False)
    s = str(raw).strip()
    exclusive = s.startswith("(")
    if exclusive:
        s = s[1:]
    if s == "+inf":
        return (float("inf"), exclusive)
    if s == "-inf":
        return (float("-inf"), exclusive)
    return (float(s), exclusive)


def _in_range(score: float, min_spec: str | float | int, max_spec: str | float | int) -> bool:
    lo, lo_ex = _parse_bound(min_spec)
    hi, hi_ex = _parse_bound(max_spec)
    if lo_ex and not (score > lo):
        return False
    if not lo_ex and not (score >= lo):
        return False
    if hi_ex and not (score < hi):
        return False
    return not (not hi_ex and not score <= hi)


class FakePipeline:
    def __init__(self, redis: FakeLeaderboardRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def delete(self, *keys: str) -> FakePipeline:
        self._ops.append(("delete", keys))
        return self

    def set(self, key: str, value: str, *, nx: bool = False, px: int | None = None) -> FakePipeline:
        self._ops.append(("set", (key, value, nx, px)))
        return self

    def zadd(self, key: str, mapping: dict[str, float | int]) -> FakePipeline:
        self._ops.append(("zadd", (key, dict(mapping))))
        return self

    def hset(
        self,
        key: str,
        field: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> FakePipeline:
        self._ops.append(("hset", (key, field, value, dict(mapping) if mapping else None)))
        return self

    def rename(self, src: str, dst: str) -> FakePipeline:
        self._ops.append(("rename", (src, dst)))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, args in self._ops:
            if op == "delete":
                results.append(await self._redis.delete(*args))
            elif op == "set":
                key, value, nx, px = args
                results.append(await self._redis.set(key, value, nx=nx, px=px))
            elif op == "zadd":
                key, mapping = args
                results.append(await self._redis.zadd(key, mapping))
            elif op == "hset":
                key, field, value, mapping = args
                results.append(
                    await self._redis.hset(key, field=field, value=value, mapping=mapping)
                )
            elif op == "rename":
                src, dst = args
                results.append(await self._redis.rename(src, dst))
        self._ops.clear()
        return results


class FakeLeaderboardRedis:
    """In-memory async Redis stand-in supporting ZSET bounds, HASH, MULTI, and Lua EVALSHA."""

    def __init__(self, *, fail_all: bool = False) -> None:
        self.strings: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.scripts: dict[str, str] = {}
        self.commands: list[str] = []
        self.zrangebyscore_slices: list[tuple[int | None, int | None]] = []
        self.hmget_field_counts: list[int] = []
        self.fail_all = fail_all
        self.fail_mid_script = False

    def _check(self, cmd: str) -> None:
        self.commands.append(cmd)
        if self.fail_all:
            raise ConnectionError("Redis unavailable")

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        del transaction
        return FakePipeline(self)

    async def get(self, key: str) -> str | None:
        self._check("GET")
        return self.strings.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        *,
        nx: bool = False,
        px: int | None = None,
        ex: int | None = None,
    ) -> bool:
        del px, ex
        self._check("SET")
        if nx and key in self.strings:
            return False
        self.strings[key] = str(value)
        return True

    async def delete(self, *keys: str) -> int:
        self._check("DEL")
        removed = 0
        for key in keys:
            if key in self.strings:
                del self.strings[key]
                removed += 1
            if key in self.zsets:
                del self.zsets[key]
                removed += 1
            if key in self.hashes:
                del self.hashes[key]
                removed += 1
        return removed

    async def rename(self, src: str, dst: str) -> bool:
        self._check("RENAME")
        if src in self.zsets:
            self.zsets[dst] = self.zsets.pop(src)
        elif src in self.hashes:
            self.hashes[dst] = self.hashes.pop(src)
        elif src in self.strings:
            self.strings[dst] = self.strings.pop(src)
        return True

    async def zadd(self, key: str, mapping: dict[str, float | int]) -> int:
        self._check("ZADD")
        z = self.zsets.setdefault(key, {})
        added = sum(1 for k in mapping if k not in z)
        for k, v in mapping.items():
            z[k] = float(v)
        return added

    async def zrevrangebyscore(
        self,
        key: str,
        max: str | float | int,
        min: str | float | int,
        start: int = 0,
        num: int = -1,
        withscores: bool = False,
    ) -> list[Any]:
        self._check("ZREVRANGEBYSCORE")
        z = self.zsets.get(key, {})
        items = [(m, s) for m, s in z.items() if _in_range(s, min, max)]
        items.sort(key=lambda pair: (-pair[1], pair[0]))
        sliced = items[start:] if num < 0 else items[start : start + num]
        if withscores:
            return sliced
        return [m for m, _ in sliced]

    async def zrangebyscore(
        self,
        key: str,
        min: str | float | int,
        max: str | float | int,
        start: int | None = None,
        num: int | None = None,
    ) -> list[str]:
        self._check("ZRANGEBYSCORE")
        self.zrangebyscore_slices.append((start, num))
        z = self.zsets.get(key, {})
        items = [(m, s) for m, s in z.items() if _in_range(s, min, max)]
        items.sort(key=lambda pair: (pair[1], pair[0]))
        if start is not None and num is not None:
            items = items[start:] if num < 0 else items[start : start + num]
        return [m for m, _ in items]

    async def zscore(self, key: str, member: str) -> float | None:
        self._check("ZSCORE")
        return self.zsets.get(key, {}).get(member)

    async def zcount(self, key: str, min: str | float | int, max: str | float | int) -> int:
        self._check("ZCOUNT")
        z = self.zsets.get(key, {})
        return sum(1 for s in z.values() if _in_range(s, min, max))

    async def hset(
        self,
        key: str,
        field: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int:
        self._check("HSET")
        h = self.hashes.setdefault(key, {})
        added = 0
        if mapping:
            for k, v in mapping.items():
                if k not in h:
                    added += 1
                h[k] = str(v)
        elif field is not None and value is not None:
            if field not in h:
                added = 1
            h[field] = str(value)
        return added

    async def hmget(self, key: str, *fields: str) -> list[str | None]:
        self._check("HMGET")
        self.hmget_field_counts.append(len(fields))
        h = self.hashes.get(key, {})
        return [h.get(f) for f in fields]

    async def script_load(self, script: str) -> str:
        self._check("SCRIPT LOAD")
        sha = hashlib.sha1(script.encode("utf-8"), usedforsecurity=False).hexdigest()
        self.scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> Any:
        self._check("EVALSHA")
        script = self.scripts.get(sha)
        if script is None:
            raise NoScriptError("NOSCRIPT No matching script")
        keys = [str(x) for x in keys_and_args[:numkeys]]
        args = [str(x) for x in keys_and_args[numkeys:]]
        # Snapshot for atomic rollback when fail_mid_script is enabled (API-LBOARD-019)
        snap_strings = deepcopy(self.strings)
        snap_zsets = deepcopy(self.zsets)
        snap_hashes = deepcopy(self.hashes)
        try:
            return self._exec_lua(script, keys, args)
        except Exception:
            self.strings = snap_strings
            self.zsets = snap_zsets
            self.hashes = snap_hashes
            raise

    def _exec_lua(self, script: str, keys: list[str], args: list[str]) -> Any:
        if "-- op:upsert" in script:
            z_key, h_key, ready_key, lock_key, dirty_key = keys
            if lock_key in self.strings:
                self.strings[dirty_key] = "1"
                return 0
            if ready_key not in self.strings:
                return 0
            (
                member,
                d_primary_s,
                d_total_s,
                d_mastered_s,
                d_solved_s,
                d_lat_s,
                d_cost_s,
                new_name,
                new_name_at,
                has_new_win,
            ) = args
            z = self.zsets.setdefault(z_key, {})
            z[member] = z.get(member, 0.0) + float(d_primary_s)
            if self.fail_mid_script:
                raise RuntimeError("Simulated mid-script failure")
            h = self.hashes.setdefault(h_key, {})
            solved = int(h.get(f"{member}:solved", "0")) + int(d_solved_s)
            if solved <= 0:
                z.pop(member, None)
                for suf in (
                    "name",
                    "name_at",
                    "total",
                    "mastered",
                    "solved",
                    "lat_milli",
                    "cost_nano",
                ):
                    h.pop(f"{member}:{suf}", None)
                return 1
            for suf, delta in (
                ("total", int(d_total_s)),
                ("mastered", int(d_mastered_s)),
                ("solved", int(d_solved_s)),
                ("lat_milli", int(d_lat_s)),
                ("cost_nano", int(d_cost_s)),
            ):
                h[f"{member}:{suf}"] = str(int(h.get(f"{member}:{suf}", "0")) + delta)
            if has_new_win == "1":
                cur_at = float(h.get(f"{member}:name_at", "-1"))
                if float(new_name_at) >= cur_at:
                    h[f"{member}:name"] = new_name
                    h[f"{member}:name_at"] = new_name_at
            return 1

        if "-- op:delete_member" in script:
            z_key, h_key, ready_key, lock_key, dirty_key = keys
            (member,) = args
            if lock_key in self.strings:
                self.strings[dirty_key] = "1"
                return 0
            if ready_key not in self.strings:
                return 0
            self.zsets.get(z_key, {}).pop(member, None)
            h = self.hashes.get(h_key, {})
            for suf in ("name", "name_at", "total", "mastered", "solved", "lat_milli", "cost_nano"):
                h.pop(f"{member}:{suf}", None)
            return 1

        if "-- op:rename_member" in script:
            z_key, h_key, ready_key, lock_key, dirty_key = keys
            old_m, new_m = args
            if lock_key in self.strings:
                self.strings[dirty_key] = "1"
                return 0
            if ready_key not in self.strings:
                return 0
            z = self.zsets.get(z_key, {})
            score = z.get(old_m)
            if score is None:
                return 1
            if new_m in z:
                self.strings.pop(ready_key, None)
                return 2
            z[new_m] = score
            del z[old_m]
            h = self.hashes.setdefault(h_key, {})
            for suf in ("name", "name_at", "total", "mastered", "solved", "lat_milli", "cost_nano"):
                val = h.pop(f"{old_m}:{suf}", None)
                if val is not None:
                    h[f"{new_m}:{suf}"] = val
            return 1

        if "-- op:unlock" in script:
            (lock_key,) = keys
            (token,) = args
            if self.strings.get(lock_key) == token:
                del self.strings[lock_key]
                return 1
            return 0

        raise AssertionError(f"Unknown Lua script: {script[:80]}")


class CountingInMemoryStore(InMemoryScoreStore):
    def __init__(self) -> None:
        super().__init__()
        self.list_all_calls = 0

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        self.list_all_calls += 1
        return await super().list_all_current_scores()


@pytest.mark.spec("API-LBOARD-009")
async def test_supabase_list_all_current_scores_paginates_all_rows_with_range() -> None:
    total_rows = 2500
    all_db_rows = [
        {
            "id": f"id-{i:04d}",
            "created_at": datetime(2026, 11, 20, tzinfo=UTC).isoformat(),
            "email": f"p{i}@example.com",
            "player_name": f"Player{i}",
            "level_id": "easy-1",
            "total_score": 5000 + (i % 500),
            "medal": "gold",
            "attacks_blocked": 5,
            "attacks_total": 5,
            "false_alarms": 0,
            "avg_latency_ms": 10.0,
            "total_cost_usd": 0.01,
            "score_version": 3,
            "won": True,
            "mastered": False,
        }
        for i in range(total_rows)
    ]
    ranges_requested: list[tuple[int, int]] = []

    class PaginatedQuery:
        def __init__(self) -> None:
            self._start = 0
            self._end = 999

        def eq(self, _col: str, _val: Any) -> PaginatedQuery:
            return self

        def order(self, _col: str, desc: bool = False) -> PaginatedQuery:
            del desc
            return self

        def range(self, start: int, end: int) -> PaginatedQuery:
            self._start = start
            self._end = end
            ranges_requested.append((start, end))
            return self

        def execute(self) -> Any:
            cap = min(1000, self._end - self._start + 1)
            return type("Resp", (), {"data": all_db_rows[self._start : self._start + cap]})()

    class PaginatedClient:
        def schema(self, _name: str) -> PaginatedClient:
            return self

        def table(self, _name: str) -> PaginatedClient:
            return self

        def select(self, _cols: str) -> PaginatedQuery:
            return PaginatedQuery()

    store = SupabaseScoreStore(PaginatedClient())
    rows = await store.list_all_current_scores()

    assert len(rows) == 2500
    assert ranges_requested == [(0, 999), (1000, 1999), (2000, 2999)]


@pytest.mark.spec("API-LBOARD-011")
async def test_redis_leaderboard_matches_python_aggregation_on_1000_seeded_owners() -> None:
    rng = random.Random(42)  # noqa: S311
    store = CountingInMemoryStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)
    levels = (
        list(LEVEL_IDS_BY_DIFFICULTY["Easy"][:2])
        + list(LEVEL_IDS_BY_DIFFICULTY["Medium"][:2])
        + list(LEVEL_IDS_BY_DIFFICULTY["Hard"][:2])
    )
    base_time = datetime(2026, 11, 20, tzinfo=UTC)

    # First ensure all boards are built/ready so every record goes incrementally through Lua.
    for board in ("Easy", "Medium", "Hard", None):
        assert await service.get_leaderboard(difficulty=board, limit=10) == []

    for i in range(1050):
        email = f"player{i:04d}@example.com" if i % 5 != 0 else None
        name = f"Player_{i:04d}"
        for lvl in rng.sample(levels, rng.randint(1, 3)):
            score = rng.choice([3000, 5000, 7500, 9000])
            req = _req(
                name,
                level_id=lvl,
                total_score=score,
                avg_latency_ms=round(rng.uniform(1.0, 200.0), 3),
                total_cost_usd=round(rng.uniform(0.0001, 0.05), 6),
                won=True,
                mastered=rng.random() < 0.35,
            )
            change = await store.record_score_change(req, email=email)
            if change.current is not None and change.previous is None:
                # Ensure deterministic distinct timestamps via store record mutation if needed
                _ = base_time + timedelta(seconds=i)
            await service.on_score_recorded(email, change)

    all_owned = await store.list_all_current_scores()
    store.list_all_calls = 0
    for board in ("Easy", "Medium", "Hard", None):
        for lim in (1, 10, 25, 100):
            expected = aggregate_difficulty_leaderboard(all_owned, difficulty=board, limit=lim)
            actual = await service.get_leaderboard(difficulty=board, limit=lim)
            assert actual == expected
    assert store.list_all_calls == 0


@pytest.mark.spec("API-LBOARD-012")
async def test_read_5000_owners_uses_bounded_redis_commands_and_zero_store_reads() -> None:
    store = CountingInMemoryStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)
    z_key = "lb:v3:z:Easy"
    d_key = "lb:v3:d:Easy"
    redis.strings["lb:v3:ready:Easy"] = "1"
    z_map: dict[str, float] = {}
    d_map: dict[str, str] = {}
    for i in range(5000):
        member = hashlib.sha256(f"email:u{i}@example.com".encode()).hexdigest()
        total = 1000 + (i % 50) * 100
        mastered = i % 3
        z_map[member] = float(total * 32 + mastered)
        d_map[f"{member}:name"] = f"User{i:04d}"
        d_map[f"{member}:name_at"] = "1700000000.0"
        d_map[f"{member}:total"] = str(total)
        d_map[f"{member}:mastered"] = str(mastered)
        d_map[f"{member}:solved"] = "1"
        d_map[f"{member}:lat_milli"] = str(10_000 + i)
        d_map[f"{member}:cost_nano"] = "1000000"
    redis.zsets[z_key] = z_map
    redis.hashes[d_key] = d_map

    redis.commands.clear()
    store.list_all_calls = 0
    rows = await service.get_leaderboard(difficulty="Easy", limit=25)

    assert len(rows) == 25
    assert store.list_all_calls == 0
    assert redis.commands.count("ZREVRANGEBYSCORE") == 1
    assert redis.commands.count("ZRANGEBYSCORE") <= 1
    assert redis.commands.count("HMGET") == 1


@pytest.mark.spec("API-LBOARD-013")
async def test_boundary_tie_group_is_ordered_by_latency_cost_and_name() -> None:
    store = InMemoryScoreStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)
    await service.get_leaderboard(difficulty="Easy", limit=10)

    candidates = [
        ("Zed", 20.0, 0.01),
        ("Amy", 10.0, 0.05),
        ("Bob", 10.0, 0.01),
        ("Ada", 10.0, 0.01),
    ]
    for name, lat, cost in candidates:
        c = await store.record_score_change(
            _req(name, total_score=5000, avg_latency_ms=lat, total_cost_usd=cost, won=True),
            email=f"{name.lower()}@example.com",
        )
        await service.on_score_recorded(f"{name.lower()}@example.com", c)

    # Top-2 cut splits a 4-way primary tie: Ada & Bob must win the tie-break.
    top2 = await service.get_leaderboard(difficulty="Easy", limit=2)
    assert [e.player_name for e in top2] == ["Ada", "Bob"]


@pytest.mark.spec("API-LBOARD-014")
@pytest.mark.spec("API-LBOARD-015")
async def test_no_emails_in_redis_and_lost_or_zero_rows_excluded() -> None:
    store = InMemoryScoreStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)
    await service.get_leaderboard(difficulty="Easy", limit=10)

    secret_email = "secret-player@example.com"
    lost = await store.record_score_change(
        _req("Loser", total_score=5000, won=False), email=secret_email
    )
    await service.on_score_recorded(secret_email, lost)
    zero = await store.record_score_change(
        _req("ZeroWin", total_score=0, won=True), email="zero@example.com"
    )
    await service.on_score_recorded("zero@example.com", zero)
    won = await store.record_score_change(
        _req("Winner", total_score=6000, won=True), email=secret_email
    )
    await service.on_score_recorded(secret_email, won)

    rows = await service.get_leaderboard(difficulty="Easy", limit=10)
    assert [r.player_name for r in rows] == ["Winner"]

    serialized = repr(redis.strings) + repr(redis.zsets) + repr(redis.hashes)
    assert secret_email not in serialized
    assert "zero@example.com" not in serialized


@pytest.mark.spec("API-LBOARD-016")
@pytest.mark.spec("API-LBOARD-017")
@pytest.mark.spec("API-LBOARD-018")
async def test_incremental_writes_mastery_flip_and_ignored_non_replacing_runs() -> None:
    store = CountingInMemoryStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)
    await service.get_leaderboard(difficulty="Easy", limit=10)
    await service.get_leaderboard(difficulty=None, limit=10)

    c1 = await store.record_score_change(
        _req("Ada", level_id="easy-1", total_score=6000, won=True, mastered=False),
        email="ada@example.com",
    )
    await service.on_score_recorded("ada@example.com", c1)

    redis.commands.clear()
    c2 = await store.record_score_change(
        _req("Ada", level_id="easy-1", total_score=7000, won=True, mastered=False),
        email="ada@example.com",
    )
    await service.on_score_recorded("ada@example.com", c2)
    assert redis.commands.count("EVALSHA") == 2  # Easy and All

    store.list_all_calls = 0
    easy_rows = await service.get_leaderboard(difficulty="Easy", limit=10)
    assert store.list_all_calls == 0
    assert (easy_rows[0].total_score, easy_rows[0].levels_solved, easy_rows[0].levels_mastered) == (
        7000,
        1,
        0,
    )

    # Lower/lost run: ScoreChange.changed is False -> zero Redis commands.
    redis.commands.clear()
    c3 = await store.record_score_change(
        _req("Ada", level_id="easy-1", total_score=5000, won=False, mastered=False),
        email="ada@example.com",
    )
    assert not c3.changed
    await service.on_score_recorded("ada@example.com", c3)
    assert redis.commands == []

    # Sticky mastery flip on same rank -> mastered rises by 1 and primary score rises by 1.
    c4 = await store.record_score_change(
        _req("Ada", level_id="easy-1", total_score=7000, won=True, mastered=True),
        email="ada@example.com",
    )
    assert c4.changed
    await service.on_score_recorded("ada@example.com", c4)
    easy_after = await service.get_leaderboard(difficulty="Easy", limit=10)
    assert easy_after[0].levels_mastered == 1
    member = hashlib.sha256(b"email:ada@example.com").hexdigest()
    assert redis.zsets["lb:v3:z:Easy"][member] == 7000 * 32 + 1
    assert redis.zsets["lb:v3:z:All"][member] == 7000 * 32 + 1


@pytest.mark.spec("API-LBOARD-019")
async def test_mid_script_failure_leaves_redis_atomic_logs_warning_and_marks_rebuild(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryScoreStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)
    await service.get_leaderboard(difficulty="Easy", limit=10)
    c1 = await store.record_score_change(
        _req("Ada", total_score=4000, won=True), email="ada@example.com"
    )
    await service.on_score_recorded("ada@example.com", c1)

    z_before = dict(redis.zsets["lb:v3:z:Easy"])
    h_before = dict(redis.hashes["lb:v3:d:Easy"])

    redis.fail_mid_script = True
    with caplog.at_level(logging.WARNING):
        c2 = await store.record_score_change(
            _req("Ada", total_score=8000, won=True), email="ada@example.com"
        )
        await service.on_score_recorded("ada@example.com", c2)
    assert redis.zsets["lb:v3:z:Easy"] == z_before
    assert redis.hashes["lb:v3:d:Easy"] == h_before
    assert "ready" not in "|".join(k for k in redis.strings if "lb:v3:ready:Easy" in k)
    assert any(r.levelno >= logging.WARNING for r in caplog.records)

    redis.fail_mid_script = False
    rebuilt = await service.get_leaderboard(difficulty="Easy", limit=10)
    assert [(e.player_name, e.total_score) for e in rebuilt] == [("Ada", 8000)]


@pytest.mark.spec("API-LBOARD-020")
@pytest.mark.spec("API-LBOARD-021")
@pytest.mark.spec("API-LBOARD-022")
async def test_clear_delete_and_email_rename_mutations() -> None:
    store = CountingInMemoryStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)
    for board in ("Easy", "Medium", "Hard", None):
        await service.get_leaderboard(difficulty=board, limit=10)

    for email, name, lvl, pts in (
        ("ada@example.com", "Ada", "easy-1", 6000),
        ("ada@example.com", "Ada", "medium-1", 7000),
        ("bob@example.com", "Bob", "easy-1", 5000),
    ):
        c = await store.record_score_change(_req(name, level_id=lvl, total_score=pts), email=email)
        await service.on_score_recorded(email, c)

    # Rename bob -> robert
    await store.rename_scores_email("bob@example.com", "robert@example.com")
    await service.on_owner_renamed("bob@example.com", "robert@example.com")
    easy_names = [e.player_name for e in await service.get_leaderboard(difficulty="Easy", limit=10)]
    assert easy_names == ["Ada", "Bob"]
    old_member = hashlib.sha256(b"email:bob@example.com").hexdigest()
    assert old_member not in redis.zsets.get("lb:v3:z:Easy", {})

    # Delete ada (two boards)
    await store.delete_scores_for("ada@example.com")
    await service.on_owner_deleted("ada@example.com")
    assert [e.player_name for e in await service.get_leaderboard(difficulty="Easy", limit=10)] == [
        "Bob"
    ]
    assert await service.get_leaderboard(difficulty="Medium", limit=10) == []

    # Admin clear marks all four boards empty and ready (no store rebuild on next read)
    await store.clear_scores()
    await service.on_scores_cleared()
    store.list_all_calls = 0
    for board in ("Easy", "Medium", "Hard", None):
        assert await service.get_leaderboard(difficulty=board, limit=10) == []
    assert store.list_all_calls == 0


@pytest.mark.spec("API-LBOARD-023")
@pytest.mark.spec("API-LBOARD-024")
@pytest.mark.spec("API-LBOARD-025")
@pytest.mark.spec("API-LBOARD-026")
async def test_rebuild_singleflight_dirty_flag_and_version_bump(monkeypatch) -> None:
    store = CountingInMemoryStore()
    c1 = await store.record_score_change(
        _req("Ada", level_id="easy-1", total_score=5000), email="ada@example.com"
    )
    assert c1.changed

    redis = FakeLeaderboardRedis()
    svc_a = LeaderboardService(store, redis)
    svc_b = LeaderboardService(store, redis)

    # Concurrent reads when ready missing: only one scans the store.
    res_a, res_b = await asyncio.gather(
        svc_a.get_leaderboard(difficulty="Easy", limit=10),
        svc_b.get_leaderboard(difficulty="Easy", limit=10),
    )
    assert [(e.player_name, e.total_score) for e in res_a] == [("Ada", 5000)]
    assert res_b == res_a
    assert store.list_all_calls == 1
    assert redis.strings.get("lb:v3:ready:Easy") == "1"

    # Simulate lock held while a write arrives -> dirty flag -> next read rebuilds again.
    redis.strings["lb:v3:lock:Easy"] = "other-holder"
    c2 = await store.record_score_change(
        _req("Bob", level_id="easy-1", total_score=9000), email="bob@example.com"
    )
    await svc_a.on_score_recorded("bob@example.com", c2)
    assert "lb:v3:dirty:Easy" in redis.strings

    # Simulate finishing the earlier rebuild: clear lock and apply dirty clearing check
    del redis.strings["lb:v3:lock:Easy"]
    if "lb:v3:dirty:Easy" in redis.strings:
        redis.strings.pop("lb:v3:dirty:Easy", None)
        redis.strings.pop("lb:v3:ready:Easy", None)
    rebuilt = await svc_a.get_leaderboard(difficulty="Easy", limit=10)
    assert [(e.player_name, e.total_score) for e in rebuilt] == [("Bob", 9000), ("Ada", 5000)]

    # Version bump switches prefix and triggers rebuild ignoring old-prefix keys.
    monkeypatch.setattr(scores_mod, "SCORE_VERSION", 99)
    monkeypatch.setattr(leaderboard_mod, "SCORE_VERSION", 99, raising=False)
    v99 = await svc_a.get_leaderboard(difficulty="Easy", limit=10)
    assert [(e.player_name, e.total_score) for e in v99] == [("Bob", 9000), ("Ada", 5000)]
    assert redis.strings.get("lb:v99:ready:Easy") == "1"


@pytest.mark.spec("API-LBOARD-027")
@pytest.mark.spec("API-LBOARD-028")
async def test_redis_error_and_unset_use_paginated_store_with_10s_cache(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = CountingInMemoryStore()
    c = await store.record_score_change(
        _req("Ada", level_id="easy-1", total_score=5000), email="ada@example.com"
    )
    assert c.changed
    clock = FakeClock(now=100.0)

    failing = LeaderboardService(store, FakeLeaderboardRedis(fail_all=True), clock=clock)
    with caplog.at_level(logging.WARNING):
        first = await failing.get_leaderboard(difficulty="Easy", limit=10)
        clock.advance(5.0)
        second = await failing.get_leaderboard(difficulty="Easy", limit=10)
    assert [(e.player_name, e.total_score) for e in first] == [("Ada", 5000)]
    assert second == first
    assert store.list_all_calls == 1
    assert any(r.levelno >= logging.WARNING for r in caplog.records)

    clock.advance(6.0)  # >10s since first read
    await failing.get_leaderboard(difficulty="Easy", limit=10)
    assert store.list_all_calls == 2

    # Unset Redis in development also uses 10s cached store path
    store.list_all_calls = 0
    dev_only = LeaderboardService(store, None, clock=clock)
    await dev_only.get_leaderboard(difficulty="Easy", limit=10)
    await dev_only.get_leaderboard(difficulty="Easy", limit=10)
    assert store.list_all_calls == 1


@pytest.mark.spec("API-LBOARD-010")
@pytest.mark.spec("API-LBOARD-029")
@pytest.mark.spec("API-LBOARD-030")
@pytest.mark.spec("API-LBOARD-031")
async def test_http_caching_my_rank_removed_stream_and_admin_scores(
    harness: Harness,
) -> None:
    import shield_api.services.scores as s_mod

    for removed in (
        "LeaderboardNotifier",
        "InMemoryNotifier",
        "RedisPubSubNotifier",
        "RedisCachedScoreStore",
        "warm_cache",
    ):
        assert not hasattr(s_mod, removed), removed

    spec = render_openapi()
    assert "/api/v1/game/scores/stream" not in spec
    assert harness.client.get("/api/v1/game/scores/stream").status_code == 404

    # Replace leaderboard service on harness container with Redis-backed one so we test HTTP + Redis
    redis = FakeLeaderboardRedis()
    harness.container.leaderboard = LeaderboardService(harness.scores, redis)
    for email, name, lat in (
        ("p1@example.com", "First", 5.0),
        ("p2@example.com", "Second", 10.0),
        ("p3@example.com", "Third", 20.0),
    ):
        c = await harness.scores.record_score_change(
            _req(name, level_id="easy-1", total_score=7000, avg_latency_ms=lat), email=email
        )
        await harness.container.leaderboard.on_score_recorded(email, c)

    lb_res = harness.client.get("/api/v1/game/leaderboard?difficulty=Easy&limit=25")
    assert lb_res.status_code == 200
    assert lb_res.headers.get("cache-control") == "public, s-maxage=10, stale-while-revalidate=30"

    scores_res = harness.client.get("/api/v1/game/scores?limit=100")
    assert scores_res.status_code == 200
    assert "public" not in (scores_res.headers.get("cache-control") or "")
    assert len(scores_res.json()) == 3

    prog_res = harness.client.get("/api/v1/game/progress")
    assert "public" not in (prog_res.headers.get("cache-control") or "")

    # Anonymous / unauthenticated -> 403 on /me
    assert harness.client.get("/api/v1/game/leaderboard/me?difficulty=Easy").status_code == 403
    assert harness.client.post("/api/v1/auth/anonymous").status_code == 200
    assert harness.client.get("/api/v1/game/leaderboard/me?difficulty=Easy").status_code == 403

    # Sign in as p3@example.com (ranked 3rd on primary score tie broken by latency)
    harness.client.post(
        "/api/v1/auth/register",
        json={"email": "p3@example.com", "password": "Password1", "player_name": "Third"},
    )
    me_easy = harness.client.get("/api/v1/game/leaderboard/me?difficulty=Easy")
    assert me_easy.status_code == 200
    assert me_easy.headers.get("cache-control") == "private, no-store"
    assert me_easy.json() == {"difficulty": "Easy", "rank": 3, "total_score": 7000}

    me_medium = harness.client.get("/api/v1/game/leaderboard/me?difficulty=Medium")
    assert me_medium.status_code == 200
    assert me_medium.json() == {"difficulty": "Medium", "rank": None, "total_score": None}


@pytest.mark.spec("API-LBOARD-032")
@pytest.mark.spec("API-LBOARD-034")
async def test_massive_tie_at_cutoff_caps_zrangebyscore_and_hmget_reads() -> None:
    store = InMemoryScoreStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)

    for i in range(400):
        email = f"tied-{i:03d}@example.com"
        req = _req(f"P{i:03d}", level_id="easy-1", total_score=1500, avg_latency_ms=10.0 + i)
        change = await store.record_score_change(req, email=email)
        await service.on_score_recorded(email, change)

    redis.zrangebyscore_slices.clear()
    redis.hmget_field_counts.clear()
    top = await service.get_leaderboard(difficulty="Easy", limit=25)
    assert len(top) == 25
    assert redis.zrangebyscore_slices == [(0, 250)]
    assert all(count <= (25 + 250) * 7 for count in redis.hmget_field_counts)

    redis.zrangebyscore_slices.clear()
    redis.hmget_field_counts.clear()
    rank = await service.get_player_rank("tied-399@example.com", difficulty="Easy")
    assert rank.total_score == 1500
    assert rank.rank == 400
    assert redis.zrangebyscore_slices == [(0, 250), (250, 250)]
    assert all(count <= 250 * 7 for count in redis.hmget_field_counts)


@pytest.mark.spec("API-LBOARD-033")
async def test_get_player_rank_pairs_members_accurately_when_hash_record_incomplete() -> None:
    from shield_api.services.leaderboard import owner_member_hash

    store = InMemoryScoreStore()
    redis = FakeLeaderboardRedis()
    service = LeaderboardService(store, redis)

    players = [
        ("tie-a@example.com", "Alpha", 5.0),
        ("tie-b@example.com", "Bravo", 10.0),
        ("tie-c@example.com", "Charlie", 20.0),
    ]
    for email, name, lat in players:
        change = await store.record_score_change(
            _req(name, level_id="easy-1", total_score=5000, avg_latency_ms=lat),
            email=email,
        )
        await service.on_score_recorded(email, change)

    assert len(await service.get_leaderboard(difficulty="Easy", limit=10)) == 3
    z_key, d_key, ready_key, _, _ = service._keys("Easy")
    # Pick the lexicographically earliest member in the ZSET so zrangebyscore visits it first,
    # and corrupt its hash record by deleting its total field.
    ordered_members = sorted(redis.zsets[z_key].keys())
    member_by_hash = {owner_member_hash("", email): (email, lat) for email, _, lat in players}
    corrupt_hash = ordered_members[0]
    del redis.hashes[d_key][f"{corrupt_hash}:total"]

    # Pick another tied player whose record is intact; pairing must match each member to its
    # own record (if index shifted by zip(ties, entries), rank/membership would mismatch).
    intact_hashes = ordered_members[1:]
    slowest_intact_hash = max(intact_hashes, key=lambda h: member_by_hash[h][1])
    slowest_email = member_by_hash[slowest_intact_hash][0]
    rank = await service.get_player_rank(slowest_email, difficulty="Easy")
    assert rank.total_score == 5000
    assert rank.rank == len(intact_hashes)

    # Also test the lexicographically last intact member when it previously fell off zip().
    last_email = member_by_hash[ordered_members[-1]][0]
    last_rank = await service.get_player_rank(last_email, difficulty="Easy")
    assert last_rank.total_score == 5000
    expected_last_pos = 1 + sum(
        1 for h in intact_hashes if member_by_hash[h][1] < member_by_hash[ordered_members[-1]][1]
    )
    assert last_rank.rank == expected_last_pos

    # Now corrupt the caller's own hash record while its ZSET entry still exists:
    # ready:<board> must be cleared and the store fallback must return the exact rank.
    caller_hash = owner_member_hash("", "tie-c@example.com")
    if caller_hash != corrupt_hash:
        del redis.hashes[d_key][f"{caller_hash}:total"]
    repaired = await service.get_player_rank("tie-c@example.com", difficulty="Easy")
    assert repaired.total_score == 5000
    assert repaired.rank == 3
    assert ready_key not in redis.strings
