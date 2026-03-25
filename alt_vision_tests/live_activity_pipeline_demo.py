#!/usr/bin/env python3
"""
Demo: live screenshot capture + local Qwen VL analysis + SQLite activity logging.

Requires:
    pip install -e ".[vlm-native]"

Usage:
    python alt_vision_tests/live_activity_pipeline_demo.py

Press Ctrl+C to stop. Activity log saved to ./activity_log.db
"""

import logging
import signal
import time

from invoy_sdk import ActivityTrackingPipeline

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    pipeline = ActivityTrackingPipeline(
        interval_seconds=10,
        output_dir="./screenshots",
        db_path="./activity_log.db",
    )
    pipeline.start()

    print("Activity tracking running (screenshot every 10s -> MLLM -> SQLite)")
    print("Screenshots: ./screenshots/")
    print("Activity log: ./activity_log.db")
    print("Press Ctrl+C to stop.")

    def on_exit(*_):
        print("\nStopping...")
        pipeline.stop()

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    while pipeline.is_running:
        time.sleep(1)


if __name__ == "__main__":
    main()

