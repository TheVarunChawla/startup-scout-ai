"""CLI entrypoint.

    python main.py run                       # run the daily pipeline
    python main.py feedback <id> --like       # record positive feedback
    python main.py feedback <id> --reject     # record negative feedback
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from startup_scout.config import AppConfig
from startup_scout.db import Database
from startup_scout.logging_config import configure_logging
from startup_scout.memory import MemoryStore
from startup_scout.pipeline import DailyPipeline


def cmd_run(args: argparse.Namespace) -> None:
    config = AppConfig.load()
    pipeline = DailyPipeline(config)
    result = pipeline.run()
    print(f"Scored {len(result.scored)} startups. Report: {result.report_path}")


def cmd_feedback(args: argparse.Namespace) -> None:
    config = AppConfig.load()
    db = Database(config.db_path)
    memory = MemoryStore(db)
    action = "liked" if args.like else "rejected"
    memory.record_feedback(args.startup_id, action, note=args.note or "")
    print(f"Recorded '{action}' feedback for {args.startup_id}")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(prog="startup-scout", description="Startup Scout AI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the daily collection/scoring/report pipeline")
    run_parser.set_defaults(func=cmd_run)

    feedback_parser = subparsers.add_parser("feedback", help="Record like/reject feedback on a startup")
    feedback_parser.add_argument("startup_id", help="Startup id, shown in the daily report / DB")
    group = feedback_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--like", action="store_true")
    group.add_argument("--reject", action="store_true")
    feedback_parser.add_argument("--note", default="", help="Optional note explaining the feedback")
    feedback_parser.set_defaults(func=cmd_feedback)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
