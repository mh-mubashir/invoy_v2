#!/usr/bin/env python3
"""
Periodic screenshot data collection for Invoy experiments (capture-only).

This script captures periodic screenshots from a selected monitor and saves
them to disk without running any VLM or writing to SQLite. Use it to collect
raw visual data first; you can run offline analysis later.

Examples:

    # Capture from monitor 1 every 10s for ~30 minutes
    python collect_periodic_screenshots.py --monitor 1 --interval 10 --duration-minutes 30 ^
        --output-dir ./screenshots_monitor1_10s

    # Capture until you press Ctrl+C (no fixed duration)
    python collect_periodic_screenshots.py --monitor 1 --interval 10 --output-dir ./screenshots_freeform
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from invoy_sdk.capture import ScreenshotCapture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect periodic screenshots from a selected monitor for offline analysis."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Seconds between screenshots (default: 10).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./screenshots",
        help="Directory where screenshots will be stored.",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=0,
        help="Monitor index: 0 = all monitors, 1 = primary, 2 = secondary, etc.",
    )
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=0.0,
        help="Optional duration in minutes. 0 = run until Ctrl+C.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    output_dir = Path(args.output_dir)
    duration = timedelta(minutes=args.duration_minutes) if args.duration_minutes > 0 else None
    end_time = datetime.now() + duration if duration is not None else None

    print("Starting screenshot-only collection.")
    print(f"  Output directory: {output_dir}")
    print(f"  Interval:        {args.interval}s")
    print(f"  Monitor index:   {args.monitor} (0=all, 1=first, 2=second, ...)")
    if duration is not None:
        print(f"  Duration:        ~{args.duration_minutes} minutes (auto-stop)")
    else:
        print("  Duration:        until Ctrl+C")

    capture = ScreenshotCapture(
        interval_seconds=args.interval,
        output_dir=output_dir,
        monitor=args.monitor,
        on_capture=None,  # no analysis or logging here; just saving PNGs
    )

    capture.start()

    def on_exit(*_: object) -> None:
        print("\nStopping screenshot collection...")
        capture.stop()

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    try:
        while capture.is_running:
            if end_time is not None and datetime.now() >= end_time:
                print("\nReached target duration; stopping...")
                capture.stop()
                break
            time.sleep(1)
    except KeyboardInterrupt:
        # Extra safety; though SIGINT handler should handle it.
        on_exit()

    print("Screenshot collection finished.")


if __name__ == "__main__":
    # On non-Linux platforms, capture may behave differently; warn but still run.
    if sys.platform.startswith("win"):
        print("Note: ScreenshotCapture is primarily tested on Linux; behavior on Windows may vary.")
    main()

