#!/usr/bin/env python3
"""
Experiment runner: configure and launch the ActivityTrackingPipeline with
explicit model / interval / DB path / session tagging for reproducible experiments.

Usage examples:

    python run_experiment.py --model moondream:1.8b-v2-q8_0 --interval 10 \\
        --db-path ./activity_moondream_coding.db \\
        --session-tag moondream_q8_coding_10s \\
        --prompt-version activity_dense_v1_change_v1

Press Ctrl+C to stop. The session_id in SQLite will match --session-tag (if provided).
"""

import argparse
import logging
import signal
import time
from datetime import datetime
from pathlib import Path

from invoy_sdk import ActivityTrackingPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Invoy activity tracking experiment.")
    parser.add_argument(
        "--model",
        type=str,
        default="moondream:1.8b-v2-q8_0",
        help="Ollama vision model to use (e.g. moondream, moondream:1.8b-v2-q8_0, llava).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Seconds between screenshots.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./activity_log.db",
        help="Path to SQLite database file for this experiment.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./screenshots",
        help="Directory where screenshots will be stored.",
    )
    parser.add_argument(
        "--session-tag",
        type=str,
        default="",
        help="Optional human-readable tag for this experiment session (used as session_id).",
    )
    parser.add_argument(
        "--prompt-version",
        type=str,
        default="activity_dense_v1_change_v1",
        help="Identifier for the prompt configuration used (stored in SQLite).",
    )
    parser.add_argument(
        "--ollama-host",
        type=str,
        default="http://localhost:11434",
        help="Ollama host URL.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    session_id = args.session_tag or f"{Path(args.db_path).stem}_{datetime.now().isoformat(timespec='seconds')}"

    pipeline = ActivityTrackingPipeline(
        interval_seconds=args.interval,
        output_dir=args.output_dir,
        db_path=args.db_path,
        model=args.model,
        ollama_host=args.ollama_host,
        session_id=session_id,
        prompt_version=args.prompt_version,
    )
    pipeline.start()

    print("Activity tracking experiment running.")
    print(f"  Model:         {args.model}")
    print(f"  Interval:      {args.interval}s")
    print(f"  DB path:       {args.db_path}")
    print(f"  Screenshots:   {args.output_dir}")
    print(f"  Session ID:    {session_id}")
    print(f"  Prompt config: {args.prompt_version}")
    print("Press Ctrl+C to stop.")

    def on_exit(*_: object) -> None:
        print("\nStopping experiment...")
        pipeline.stop()

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    while pipeline.is_running:
        time.sleep(1)


if __name__ == "__main__":
    main()

