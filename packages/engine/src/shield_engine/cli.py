"""``shield-engine`` command line: retrain the baseline classifier."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from shield_engine import __version__
from shield_engine.dataset import load_jsonl
from shield_engine.models import BASELINE_DIR


def _cmd_train(args: argparse.Namespace) -> int:
    from shield_engine.training import train_baseline

    metadata = train_baseline(
        load_jsonl(args.data), args.out, dataset_path=args.data, random_state=args.seed
    )
    print(json.dumps(metadata["files"], indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shield-engine", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    tr = sub.add_parser("train", help="retrain the baseline classifier")
    tr.add_argument("--data", type=Path, required=True)
    tr.add_argument("--out", type=Path, default=BASELINE_DIR)
    tr.add_argument("--seed", type=int, default=42)
    tr.set_defaults(func=_cmd_train)

    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
