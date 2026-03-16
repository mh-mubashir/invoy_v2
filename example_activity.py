#!/usr/bin/env python3
"""
Example: Screenshot capture + MLLM analysis + SQLite activity logging.

Requires:
    1. Ollama installed: https://ollama.com/download
    2. Vision model: ollama pull llava (needs ~5GB RAM)
       Or: ollama pull moondream (for <5GB RAM, pass model="moondream")

Usage:
    python example_activity.py

Press Ctrl+C to stop. Activity log saved to ./activity_log.db
"""

import logging
import signal
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")

from invoy_sdk import ActivityTrackingPipeline


def main():
    # Use llava for better quality (needs ~5GB RAM). Use moondream for <5GB RAM.
    pipeline = ActivityTrackingPipeline(
        interval_seconds=10,
        output_dir="./screenshots",
        db_path="./activity_log.db",
        model="moondream:1.8b-v2-q8_0",  # Q8 - best quality, ~2.4GB, fits in ~4GB RAM
    )
    pipeline.start()

    print("Activity tracking running (screenshot every 10s -> MLLM -> SQLite)")
    print(f"Screenshots: ./screenshots/")
    print(f"Activity log: ./activity_log.db")
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
