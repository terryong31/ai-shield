from typing import Any

import pytest

from shield_api.container import build_container
from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest, ScoreRecord
from shield_api.services.scores import (
    InMemoryNotifier,
    InMemoryScoreStore,
    RedisCachedScoreStore,
)
from shield_api.settings import Settings


def _board() -> BoardGraphSchema:
    return BoardGraphSchema(nodes=[], edges=[])


def _score_req(
    player_name: str,
    *,
    level_id: str = "easy-1",
    total_score: int = 1000,
    avg_latency_ms: float = 10.0,
    total_cost_usd: float = 0.01,
    won: bool = False,
    mastered: bool = False,
) -> ScoreCreateRequest:
    return ScoreCreateRequest(
        player_name=player_name,
        level_id=level_id,  # type: ignore[arg-type]
        total_score=total_score,
        medal="gold",
        attacks_blocked=10,
        attacks_total=10,
        false_alarms=0,
        avg_latency_ms=avg_latency_ms,
        total_cost_usd=total_cost_usd,
        board=_board(),
        won=won,
        mastered=mastered,
    )


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def zadd(self, key: str, mapping: dict[str, float]) -> "FakePipeline":
        self._ops.append(("zadd", (key, mapping)))
        return self

    def zrem(self, key: str, *members: str) -> "FakePipeline":
        self._ops.append(("zrem", (key, members)))
        return self

    def zrevrange(self, key: str, start: int, stop: int) -> "FakePipeline":
        self._ops.append(("zrevrange", (key, start, stop)))
        return self

    def hset(
        self,
        key: str,
        field: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> "FakePipeline":
        self._ops.append(("hset", (key, field, value, mapping)))
        return self

    def hdel(self, key: str, *fields: str) -> "FakePipeline":
        self._ops.append(("hdel", (key, fields)))
        return self

    def hmget(self, key: str, *fields: str) -> "FakePipeline":
        self._ops.append(("hmget", (key, fields)))
        return self

    def delete(self, *keys: str) -> "FakePipeline":
        self._ops.append(("delete", keys))
        return self

    def expire(self, key: str, seconds: int) -> "FakePipeline":
        self._ops.append(("expire", (key, seconds)))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, args in self._ops:
            if op == "zadd":
                key, mapping = args
                zset = self._redis.zsets.setdefault(key, {})
                zset.update(mapping)
                results.append(len(mapping))
            elif op == "zrem":
                key, members = args
                zset = self._redis.zsets.get(key, {})
                removed = sum(1 for m in members if zset.pop(m, None) is not None)
                results.append(removed)
            elif op == "zrevrange":
                key, start, stop = args
                zset = self._redis.zsets.get(key, {})
                ordered = sorted(zset.items(), key=lambda item: (-item[1], item[0]))
                end = None if stop == -1 else stop + 1
                results.append([member for member, _ in ordered[start:end]])
            elif op == "hset":
                key, field, value, mapping = args
                h = self._redis.hashes.setdefault(key, {})
                if mapping:
                    h.update(mapping)
                    results.append(len(mapping))
                elif field is not None and value is not None:
                    h[field] = value
                    results.append(1)
            elif op == "hdel":
                key, fields = args
                h = self._redis.hashes.get(key, {})
                results.append(sum(1 for f in fields if h.pop(f, None) is not None))
            elif op == "hmget":
                key, fields = args
                h = self._redis.hashes.get(key, {})
                results.append([h.get(f) for f in fields])
            elif op == "delete":
                removed = 0
                for k in args:
                    if k in self._redis.zsets:
                        del self._redis.zsets[k]
                        removed += 1
                    if k in self._redis.hashes:
                        del self._redis.hashes[k]
                        removed += 1
                results.append(removed)
            elif op == "expire":
                results.append(True)
        self._ops.clear()
        return results


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.zsets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.published: list[tuple[str, str]] = []
        self.fail = fail

    def pipeline(self, transaction: bool = False) -> FakePipeline:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        return FakePipeline(self)

    async def zrevrange(self, key: str, start: int, stop: int) -> list[str]:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        zset = self.zsets.get(key, {})
        ordered = sorted(zset.items(), key=lambda item: (-item[1], item[0]))
        end = None if stop == -1 else stop + 1
        return [member for member, _ in ordered[start:end]]

    async def hmget(self, key: str, *fields: str) -> list[str | None]:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        h = self.hashes.get(key, {})
        return [h.get(f) for f in fields]

    async def hget(self, key: str, field: str) -> str | None:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key: str) -> dict[str, str]:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        return dict(self.hashes.get(key, {}))

    async def delete(self, *keys: str) -> int:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        removed = 0
        for k in keys:
            if k in self.zsets:
                del self.zsets[k]
                removed += 1
            if k in self.hashes:
                del self.hashes[k]
                removed += 1
        return removed

    async def publish(self, channel: str, message: str) -> int:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        self.published.append((channel, message))
        return 1


class CountingScoreStore(InMemoryScoreStore):
    def __init__(self) -> None:
        super().__init__()
        self.list_calls = 0
        self.list_all_calls = 0

    async def list_scores(
        self, *, level_id: str | None = None, limit: int = 50
    ) -> list[ScoreRecord]:
        self.list_calls += 1
        return await super().list_scores(level_id=level_id, limit=limit)

    async def list_all_current_scores(self) -> list[tuple[str | None, ScoreRecord]]:
        self.list_all_calls += 1
        return await super().list_all_current_scores()


@pytest.mark.spec("API-SCORE-001")
async def test_warm_redis_cache_returns_exact_ranked_order_without_hitting_inner_store() -> None:
    inner = CountingScoreStore()
    redis = FakeRedis()
    store = RedisCachedScoreStore(inner, redis)

    # Record tied scores with different latency, cost, and timestamps
    await store.record_score(
        _score_req("Slow", total_score=2000, avg_latency_ms=40.0, total_cost_usd=0.01),
        email="slow@example.com",
    )
    await store.record_score(
        _score_req("FastExpensive", total_score=2000, avg_latency_ms=10.0, total_cost_usd=0.05),
        email="fastexp@example.com",
    )
    await store.record_score(
        _score_req("FastCheap", total_score=2000, avg_latency_ms=10.0, total_cost_usd=0.01),
        email="fastcheap@example.com",
    )
    await store.record_score(
        _score_req("Top", total_score=3000, avg_latency_ms=50.0, total_cost_usd=0.10),
        email="top@example.com",
    )

    inner.list_calls = 0
    results = await store.list_scores(level_id="easy-1", limit=10)

    assert [r.player_name for r in results] == ["Top", "FastCheap", "FastExpensive", "Slow"]
    assert inner.list_calls == 0


@pytest.mark.spec("API-SCORE-002")
async def test_cold_redis_cache_hydrates_from_inner_store_on_first_read() -> None:
    inner = CountingScoreStore()
    await inner.record_score(_score_req("Ada", total_score=2500), email="ada@example.com")
    await inner.record_score(_score_req("Bob", total_score=1800), email="bob@example.com")

    redis = FakeRedis()
    store = RedisCachedScoreStore(inner, redis)

    first = await store.list_scores(level_id="easy-1", limit=10)
    assert [r.player_name for r in first] == ["Ada", "Bob"]
    assert inner.list_calls == 1

    # Second read must come from Redis without calling inner.list_scores again
    second = await store.list_scores(level_id="easy-1", limit=10)
    assert [r.player_name for r in second] == ["Ada", "Bob"]
    assert inner.list_calls == 1


@pytest.mark.spec("API-SCORE-002")
async def test_record_score_on_cold_redis_does_not_mask_existing_inner_scores() -> None:
    inner = CountingScoreStore()
    await inner.record_score(_score_req("Existing", total_score=2500), email="existing@example.com")

    redis = FakeRedis()
    store = RedisCachedScoreStore(inner, redis)

    await store.record_score(_score_req("NewPlayer", total_score=1800), email="new@example.com")
    results = await store.list_scores(level_id="easy-1", limit=10)

    assert [r.player_name for r in results] == ["Existing", "NewPlayer"]


@pytest.mark.spec("API-SCORE-003")
async def test_mutations_invalidate_redis_and_publish_sse_notifications() -> None:
    inner = CountingScoreStore()
    redis = FakeRedis()
    notifier = InMemoryNotifier()
    store = RedisCachedScoreStore(inner, redis, notifier=notifier)

    events: list[dict[str, Any]] = []

    async def collect() -> None:
        async for event in notifier.subscribe():
            events.append(event)
            if len(events) >= 3:
                break

    import asyncio

    listener = asyncio.create_task(collect())
    await asyncio.sleep(0)

    await store.record_score(_score_req("Ada", total_score=1000), email="ada@example.com")
    await store.record_score(_score_req("Ada", total_score=2000), email="ada@example.com")
    await store.delete_scores_for("ada@example.com")

    await asyncio.wait_for(listener, timeout=1.0)
    assert [e["reason"] for e in events] == ["recorded", "recorded", "deleted"]
    assert await store.list_scores(level_id="easy-1", limit=10) == []


@pytest.mark.spec("API-SCORE-003")
async def test_sse_stream_survives_keepalive_timeout_without_stop_async_iteration(
    monkeypatch, tmp_path
) -> None:
    import asyncio

    from shield_api.routers import game as game_router

    monkeypatch.setattr(game_router, "_STREAM_KEEPALIVE_SECONDS", 0.02)

    container = build_container(Settings(_env_file=None, SQLITE_PATH=tmp_path / "shield.db"))

    class DummyRequest:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 4

    response = await game_router.stream_game_scores(DummyRequest(), container)  # type: ignore[arg-type]
    chunks: list[str] = []

    async def publish_later() -> None:
        await asyncio.sleep(0.05)
        await container.leaderboard_notifier.publish(level_id="easy-1", reason="recorded")

    pub_task = asyncio.create_task(publish_later())
    async for chunk in response.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
        chunks.append(text)
    await pub_task

    assert any(c == ": keepalive\n\n" for c in chunks)
    assert any("event: leaderboard" in c for c in chunks)


@pytest.mark.spec("API-SCORE-004")
def test_gateway_falls_back_to_inner_score_store_when_redis_is_unset_or_unreachable(
    tmp_path,
) -> None:
    # Unset REDIS_URL: standard SqliteScoreStore without error
    container = build_container(Settings(_env_file=None, SQLITE_PATH=tmp_path / "shield.db"))
    assert container.scores.backend == "sqlite"

    # Unreachable Redis: RedisCachedScoreStore degrades to inner store without raising
    import asyncio

    inner = InMemoryScoreStore()
    failing_redis = FakeRedis(fail=True)
    cached = RedisCachedScoreStore(inner, failing_redis)

    recorded = asyncio.run(cached.record_score(_score_req("Ada", total_score=1500), email="a@b.c"))
    assert recorded.player_name == "Ada"
    listed = asyncio.run(cached.list_scores(level_id="easy-1", limit=10))
    assert [r.player_name for r in listed] == ["Ada"]
    listed_all = asyncio.run(cached.list_scores(level_id=None, limit=10))
    assert [r.player_name for r in listed_all] == ["Ada"]
    owned_all = asyncio.run(cached.list_all_current_scores())
    assert [(email, rec.player_name) for email, rec in owned_all] == [("a@b.c", "Ada")]


@pytest.mark.spec("API-SCORE-001")
@pytest.mark.spec("API-SCORE-002")
async def test_list_scores_all_levels_hydrates_in_single_inner_query() -> None:
    inner = CountingScoreStore()
    await inner.record_score(
        _score_req("Ada", level_id="easy-1", total_score=9100), email="ada@example.com"
    )
    await inner.record_score(
        _score_req("Bob", level_id="medium-1", total_score=8400), email="bob@example.com"
    )
    await inner.record_score(
        _score_req("Cara", level_id="hard-1", total_score=7900), email="cara@example.com"
    )

    store = RedisCachedScoreStore(inner, FakeRedis())

    first = await store.list_scores(level_id=None, limit=50)
    assert [r.player_name for r in first] == ["Ada", "Bob", "Cara"]
    assert inner.list_calls == 1

    second = await store.list_scores(level_id=None, limit=50)
    assert [r.player_name for r in second] == ["Ada", "Bob", "Cara"]
    assert inner.list_calls == 1


@pytest.mark.spec("API-SCORE-001")
@pytest.mark.spec("API-SCORE-002")
@pytest.mark.spec("API-SCORE-003")
async def test_list_all_current_scores_caches_in_redis_with_singleflight_and_write_through() -> (
    None
):
    import asyncio

    empty_inner = CountingScoreStore()
    empty_store = RedisCachedScoreStore(empty_inner, FakeRedis())
    assert await empty_store.list_all_current_scores() == []
    assert await empty_store.list_all_current_scores() == []
    assert empty_inner.list_all_calls == 1

    inner = CountingScoreStore()
    await inner.record_score(
        _score_req("Ada", level_id="easy-1", total_score=9000, won=True, mastered=False),
        email="ada@example.com",
    )
    await inner.record_score(
        _score_req("Bob", level_id="medium-1", total_score=8000, won=True, mastered=False),
        email="bob@example.com",
    )
    store = RedisCachedScoreStore(inner, FakeRedis())

    results = await asyncio.gather(
        store.list_all_current_scores(),
        store.list_all_current_scores(),
        store.list_all_current_scores(),
    )
    assert [len(batch) for batch in results] == [2, 2, 2]
    assert inner.list_all_calls == 1

    # Write-through on record_score updates owned cache (sticky won/mastered, zero reads)
    await store.record_score(
        _score_req("Ada", level_id="easy-1", total_score=8500, won=True, mastered=True),
        email="ada@example.com",
    )
    after_update = await store.list_all_current_scores()
    assert inner.list_all_calls == 1
    ada_entry = next(rec for email, rec in after_update if email == "ada@example.com")
    assert (ada_entry.total_score, ada_entry.won, ada_entry.mastered) == (9000, True, True)

    # Rename email invalidates & reloads updated owner email cleanly
    await store.rename_scores_email("bob@example.com", "robert@example.com")
    after_rename = await store.list_all_current_scores()
    assert {email for email, _ in after_rename} == {"ada@example.com", "robert@example.com"}

    # Delete removes Bob's entry cleanly
    await store.delete_scores_for("robert@example.com")
    after_delete = await store.list_all_current_scores()
    assert [email for email, _ in after_delete] == ["ada@example.com"]

    # Clear removes everything cleanly
    await store.clear_scores()
    assert await store.list_all_current_scores() == []


@pytest.mark.spec("API-CAMP-003")
async def test_supabase_summary_queries_fall_back_when_mastery_columns_missing() -> None:
    from shield_api.services.scores import SupabaseScoreStore

    class MissingColumnError(Exception):
        def __init__(self) -> None:
            super().__init__("column scores.won does not exist")
            self.code = "42703"

    selected_columns: list[str] = []

    class LegacySupabaseQuery:
        def __init__(self, cols: str) -> None:
            self._cols = cols

        def eq(self, _col: str, _val: Any) -> "LegacySupabaseQuery":
            return self

        def execute(self) -> Any:
            if "won" in self._cols or "mastered" in self._cols:
                raise MissingColumnError()
            return type(
                "Resp",
                (),
                {
                    "data": [
                        {
                            "id": "row-1",
                            "created_at": "2026-11-19T00:00:00+00:00",
                            "email": "ada@example.com",
                            "player_name": "Ada",
                            "level_id": "easy-1",
                            "total_score": 9200,
                            "medal": "gold",
                            "attacks_blocked": 5,
                            "attacks_total": 5,
                            "false_alarms": 0,
                            "avg_latency_ms": 1.2,
                            "total_cost_usd": 0.0,
                            "score_version": 3,
                        }
                    ]
                },
            )()

    class LegacySupabaseClient:
        def schema(self, _name: str) -> "LegacySupabaseClient":
            return self

        def table(self, _name: str) -> "LegacySupabaseClient":
            return self

        def select(self, cols: str) -> LegacySupabaseQuery:
            selected_columns.append(cols)
            return LegacySupabaseQuery(cols)

    store = SupabaseScoreStore(LegacySupabaseClient())

    all_rows = await store.list_all_current_scores()
    assert len(all_rows) == 1
    assert all_rows[0][0] == "ada@example.com"
    assert (all_rows[0][1].total_score, all_rows[0][1].won, all_rows[0][1].mastered) == (
        9200,
        False,
        False,
    )
    assert len(selected_columns) == 2
    assert "won" in selected_columns[0]
    assert "won" not in selected_columns[1]
    assert "board_json" not in selected_columns[1]

    # Cached _has_mastery_columns=False skips the failing select on subsequent owner/all queries.
    owner_rows = await store.list_scores_for_owner("ada@example.com")
    assert [r.total_score for r in owner_rows] == [9200]
    assert len(selected_columns) == 3
    assert "won" not in selected_columns[2]
    assert "board_json" not in selected_columns[2]
