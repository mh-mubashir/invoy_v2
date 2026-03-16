"""
Invoy SDK - Periodic screenshot capture and screen activity analysis.

Usage:
    from invoy_sdk import ScreenshotCapture

    capture = ScreenshotCapture(interval_seconds=10, output_dir="./screenshots")
    capture.start()
    # ... let it run ...
    capture.stop()

    # With MLLM analysis and SQLite logging:
    from invoy_sdk import ActivityTrackingPipeline

    pipeline = ActivityTrackingPipeline(interval_seconds=10)
    pipeline.start()
"""

from invoy_sdk.capture import ScreenshotCapture
from invoy_sdk.analyzer import MoondreamAnalyzer
from invoy_sdk.activity_log import SQLiteActivityLog
from invoy_sdk.pipeline import ActivityTrackingPipeline

__all__ = [
    "ScreenshotCapture",
    "MoondreamAnalyzer",
    "SQLiteActivityLog",
    "ActivityTrackingPipeline",
]
__version__ = "0.1.0"
