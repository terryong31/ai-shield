"""The baseline retraining path, the dataset loader, the Groq adapter and the test doubles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from shield_engine import ChatCompletion, ChatMessage, Verdict
from shield_engine.cli import main
from shield_engine.dataset import DatasetError, Example, load_jsonl
from shield_engine.models import load_baseline
from shield_engine.testing import ScriptedChatModel, ScriptedUsageChatModel, StaticClassifier

SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "train.jsonl"


def write_jsonl(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "bad_line",
    ["{not json", '{"label": 1}', '{"text": "x", "label": 2}', '{"text": 5, "label": 0}', "[1]"],
)
def test_malformed_rows_name_their_line(tmp_path: Path, bad_line: str) -> None:
    path = write_jsonl(tmp_path / "d.jsonl", ['{"text": "ok", "label": 0}', bad_line])

    with pytest.raises(DatasetError, match="line 2"):
        load_jsonl(path)


def test_valid_rows_load_with_optional_fields(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "d.jsonl",
        ['{"text": "a", "label": 1, "category": "jailbreak"}', "", '{"text": "b", "label": 0}'],
    )

    assert load_jsonl(path) == [
        Example(text="a", label=1, category="jailbreak"),
        Example(text="b", label=0),
    ]


def test_cli_train_writes_verified_artifacts(tmp_path: Path, capsys) -> None:
    out = tmp_path / "candidate"

    assert main(["train", "--data", str(SEED), "--out", str(out), "--seed", "7"]) == 0

    digests = json.loads(capsys.readouterr().out)
    assert set(digests) == {"model.joblib", "vectorizer.joblib"}
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["training_data"]["examples"] == len(load_jsonl(SEED))
    assert metadata["hyperparameters"]["random_state"] == 7
    detector = load_baseline(directory=out)
    assert detector.score("drop table employees").verdict is Verdict.MALICIOUS


@dataclass
class FakeCompletions:
    usage: Any
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        message = type("Message", (), {"content": "hello"})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice], "usage": self.usage})()


async def test_groq_adapter_sends_messages_and_reports_usage() -> None:
    from shield_engine.adapters.groq import GroqChatModel

    model = GroqChatModel("test-key", "llama-3.1-8b-instant")
    usage = type("Usage", (), {"prompt_tokens": 12, "completion_tokens": 3})()
    completions = FakeCompletions(usage)
    model._client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()

    messages = [ChatMessage("system", "rules"), ChatMessage("user", "hi")]
    result = await model.complete_with_usage(messages, max_tokens=50)

    assert result == ChatCompletion(text="hello", input_tokens=12, output_tokens=3)
    assert completions.calls[0]["model"] == "llama-3.1-8b-instant"
    assert completions.calls[0]["messages"] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "hi"},
    ]

    completions.usage = None
    assert await model.complete(messages) == "hello"


async def test_test_doubles_replay_their_scripts() -> None:
    classifier = StaticClassifier(Verdict.MALICIOUS, 0.9)
    assert classifier.score("x").verdict is Verdict.MALICIOUS
    assert classifier.calls == ["x"]

    chat = ScriptedChatModel(["one", RuntimeError("down")])
    assert await chat.complete([ChatMessage("user", "a")]) == "one"
    with pytest.raises(RuntimeError):
        await chat.complete([ChatMessage("user", "b")])
    with pytest.raises(AssertionError):
        await chat.complete([ChatMessage("user", "c")])

    usage = ScriptedUsageChatModel(["plain", ValueError("bad")], default=ChatCompletion("d"))
    assert (await usage.complete_with_usage([])).text == "plain"
    with pytest.raises(ValueError, match="bad"):
        await usage.complete_with_usage([])
    assert (await usage.complete_with_usage([])).text == "d"
    with pytest.raises(AssertionError):
        await ScriptedUsageChatModel([]).complete_with_usage([])
