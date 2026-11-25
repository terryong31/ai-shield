from typing import Any

import pytest

from shield_api.container import build_container
from shield_api.services.scores import InMemoryScoreStore, SupabaseScoreStore
from shield_api.settings import Settings


@pytest.mark.spec("API-SCORE-004")
async def test_gateway_falls_back_to_inner_score_store_when_redis_is_unset_or_unreachable(
    monkeypatch,
) -> None:
    from pydantic import SecretStr

    from shield_api.schemas import BoardGraphSchema, ScoreCreateRequest
    from shield_api.services.leaderboard import LeaderboardService

    from .conftest import FakeClient

    monkeypatch.setattr("supabase.create_client", lambda url, key: FakeClient())
    container = build_container(
        Settings(
            _env_file=None,
            APP_ENV="development",
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_KEY=SecretStr("service-key"),
        )
    )
    assert container.scores.backend == "supabase"
    assert isinstance(container.leaderboard, LeaderboardService)

    class FailingRedis:
        async def get(self, _key: str) -> Any:
            raise ConnectionError("Redis unavailable")

        async def script_load(self, _script: str) -> str:
            raise ConnectionError("Redis unavailable")

        async def evalsha(self, *_args: Any) -> Any:
            raise ConnectionError("Redis unavailable")

        async def delete(self, *_keys: str) -> int:
            raise ConnectionError("Redis unavailable")

    inner = InMemoryScoreStore()
    service = LeaderboardService(inner, FailingRedis())
    req = ScoreCreateRequest(
        player_name="Ada",
        level_id="easy-1",
        total_score=1500,
        medal="gold",
        attacks_blocked=10,
        attacks_total=10,
        false_alarms=0,
        avg_latency_ms=10.0,
        total_cost_usd=0.01,
        board=BoardGraphSchema(nodes=[], edges=[]),
        won=True,
        mastered=False,
    )
    change = await inner.record_score_change(req, email="a@b.c")
    await service.on_score_recorded("a@b.c", change)

    entries = await service.get_leaderboard(difficulty="Easy", limit=10)
    assert [(e.player_name, e.total_score) for e in entries] == [("Ada", 1500)]


@pytest.mark.spec("API-CAMP-003")
async def test_supabase_summary_queries_fall_back_when_mastery_columns_missing() -> None:
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

        def order(self, _col: str, desc: bool = False) -> "LegacySupabaseQuery":
            return self

        def range(self, _start: int, _end: int) -> "LegacySupabaseQuery":
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
