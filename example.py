#!/usr/bin/env python3
"""
Example: Run periodic screenshot capture every 10 seconds.

Usage:
    python example.py

Screenshots are saved to ./screenshots/ by default.
Press Ctrl+C to stop.
"""

import signal
import time

from invoy_sdk import ScreenshotCapture


def main():
    capture = ScreenshotCapture(
        interval_seconds=10,
        output_dir="./screenshots",
    )
    capture.start()

    print("Screenshot capture running (every 10 seconds). Press Ctrl+C to stop.")
    print(f"Screenshots saved to: {capture.output_dir.absolute()}")

    def on_exit(*_):
        print("\nStopping...")
        capture.stop()

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    # Keep main thread alive until stopped
    while capture.is_running:
        time.sleep(1)


if __name__ == "__main__":
    main()
