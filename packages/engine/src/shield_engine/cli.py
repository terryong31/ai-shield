"""``shield-engine`` command line: train the baseline and run evaluations."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from shield_engine import __version__
from shield_engine.evaluation import evaluate, load_jsonl
from shield_engine.models import BASELINE_DIR, load_baseline, sha256_file
from shield_engine.pipeline import Shield


def _build_shield(pipeline: str) -> Shield:
    classifier = load_baseline()
    if pipeline == "classifier":
        return Shield(classifier)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("--pipeline full needs GROQ_API_KEY in the environment")
    from shield_engine.adapters.groq import GroqChatModel
    from shield_engine.adjudication import DebateAdjudicator
    from shield_engine.detectors import LlamaGuardModerator

    return Shield(
        classifier,
        moderator=LlamaGuardModerator(
            GroqChatModel(api_key, os.environ.get("GROQ_GUARD_MODEL", "llama-guard-3-8b"))
        ),
        adjudicator=DebateAdjudicator(
            GroqChatModel(api_key, os.environ.get("GROQ_DEBATE_MODEL", "llama-3.3-70b-versatile"))
        ),
    )


def _cmd_eval(args: argparse.Namespace) -> int:
    examples = load_jsonl(args.data)
    report = asyncio.run(evaluate(_build_shield(args.pipeline), examples))
    payload = {
        "engine_version": __version__,
        "pipeline": args.pipeline,
        "dataset": {"path": str(args.data), "sha256": sha256_file(args.data)},
        **report.as_dict(),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    m = report.metrics
    print(
        f"n={report.examples}  precision={m.precision:.3f}  recall={m.recall:.3f}  "
        f"f1={m.f1:.3f}  fpr={m.false_positive_rate:.3f}  "
        f"abstain={report.abstention_rate:.3f}  p50={report.latency_ms_p50:.2f}ms"
    )
    return 0


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

    ev = sub.add_parser("eval", help="evaluate the pipeline on a labelled JSONL dataset")
    ev.add_argument("--data", type=Path, required=True)
    ev.add_argument("--report", type=Path, help="write a JSON report here")
    ev.add_argument("--pipeline", choices=["classifier", "full"], default="classifier")
    ev.set_defaults(func=_cmd_eval)

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
