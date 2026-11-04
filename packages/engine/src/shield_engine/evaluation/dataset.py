from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class DatasetError(ValueError):
    """A dataset row is malformed. The message names the 1-based line."""


@dataclass(frozen=True, slots=True)
class Example:
    text: str
    label: int  # 1 = malicious, 0 = benign
    source: str | None = None
    category: str | None = None


def load_jsonl(path: Path) -> list[Example]:
    examples: list[Example] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{path}: line {number}: invalid JSON ({exc.msg})") from exc
            if not isinstance(row, dict):
                raise DatasetError(f"{path}: line {number}: expected an object")
            text, label = row.get("text"), row.get("label")
            if not isinstance(text, str):
                raise DatasetError(f"{path}: line {number}: 'text' must be a string")
            if label not in (0, 1) or isinstance(label, bool):
                raise DatasetError(f"{path}: line {number}: 'label' must be 0 or 1")
            examples.append(
                Example(
                    text=text, label=label, source=row.get("source"), category=row.get("category")
                )
            )
    return examples
