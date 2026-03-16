"""
Pipeline: Screenshot capture + MLLM analysis + SQLite activity logging.

Runs continuously: capture every N seconds, analyze with vision model, log to SQLite.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from invoy_sdk.analyzer import MoondreamAnalyzer
from invoy_sdk.activity_log import SQLiteActivityLog
from invoy_sdk.capture import ScreenshotCapture

logger = logging.getLogger(__name__)


class ActivityTrackingPipeline:
    """
    Captures screenshots periodically, analyzes them with a local MLLM,
    and logs activity to SQLite.

    Example:
        pipeline = ActivityTrackingPipeline(
            interval_seconds=10,
            output_dir="./screenshots",
            db_path="./activity_log.db",
        )
        pipeline.start()
        # ...
        pipeline.stop()
    """

    def __init__(
        self,
        interval_seconds: float = 10.0,
        output_dir: str | Path = "./screenshots",
        db_path: str | Path = "./activity_log.db",
        model: str = "llava",  # Use model="moondream" if <5GB RAM
        ollama_host: str = "http://localhost:11434",
        session_id: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ):
        """
        Initialize the pipeline.

        Args:
            interval_seconds: Seconds between screenshots. Default 10.
            output_dir: Directory for screenshots.
            db_path: Path to SQLite activity log.
            model: Ollama model name (default: llava).
            ollama_host: Ollama API host URL.
            session_id: Optional session identifier for grouping entries in SQLite.
            prompt_version: Identifier for the prompt configuration used for this run.
        """
        self.interval_seconds = interval_seconds
        self.output_dir = Path(output_dir)
        self.db_path = Path(db_path)
        self.prompt_version = prompt_version

        self.analyzer = MoondreamAnalyzer(
            model=model,
            host=ollama_host,
            fallback_model="moondream",
        )
        self.activity_log = SQLiteActivityLog(db_path=self.db_path, session_id=session_id)
        self.capture = ScreenshotCapture(
            interval_seconds=interval_seconds,
            output_dir=output_dir,
            on_capture=self._on_capture,
        )
        # Path of the immediately previous screenshot only (for change comparison)
        self._previous_path: Optional[str] = None

    def _on_capture(self, path: str, raw_bytes: bytes) -> None:
        """Called after each screenshot: analyze (activity + change) and log. Separate MLLM calls for each."""
        # Resolve to absolute path so we always analyze the correct file
        abs_path = str(Path(path).resolve())
        screenshot_name = Path(path).name
        logger.info("Analyzing new screenshot: %s", screenshot_name)
        try:
            # Activity detection: always run (single image)
            activity, activity_extracted_text, activity_ms = self.analyzer.analyze_with_extracted(abs_path)

            # Change detection: only when we have a previous screenshot (two images)
            change_summary = None
            change_prev_extracted_text = None
            change_cur_extracted_text = None
            change_ms = None
            if self._previous_path is not None:
                (
                    change_summary,
                    change_prev_extracted_text,
                    change_cur_extracted_text,
                    change_ms,
                ) = self.analyzer.analyze_change_with_extracted(abs_path, self._previous_path)

            self.activity_log.log(
                screenshot_path=abs_path,
                activity=activity,
                activity_extracted_text=activity_extracted_text,
                change_summary=change_summary,
                change_prev_extracted_text=change_prev_extracted_text,
                change_cur_extracted_text=change_cur_extracted_text,
                activity_inference_ms=activity_ms,
                change_inference_ms=change_ms,
                model_name=self.analyzer.model,
                prompt_version=self.prompt_version,
            )
            msg = f"[{screenshot_name}] " + ((activity or "")[:80] + ("..." if activity and len(activity) > 80 else ""))
            if change_summary:
                msg += f" | Change: {(change_summary or '')[:60]}..."
            if activity_ms is not None:
                msg += f" (activity: {activity_ms:.0f}ms"
                if change_ms is not None:
                    msg += f", change: {change_ms:.0f}ms"
                msg += ")"
            logger.info("Activity logged: %s", msg)
            self._previous_path = abs_path
        except Exception as e:
            logger.exception("Pipeline step failed: %s", e)
            self.activity_log.log(
                screenshot_path=abs_path,
                activity=None,
                change_summary=None,
                activity_inference_ms=None,
                change_inference_ms=None,
                model_name=self.analyzer.model,
                prompt_version=self.prompt_version,
            )
            self._previous_path = abs_path

    def start(self) -> None:
        """Start the pipeline (capture + analyze + log)."""
        self.capture.start()

    def stop(self) -> None:
        """Stop the pipeline."""
        self.capture.stop()
        self.activity_log.close()

    def get_entries(self, limit: int = 100) -> list[dict]:
        """Get recent activity entries from the log."""
        return self.activity_log.get_entries(limit=limit)

    @property
    def is_running(self) -> bool:
        """Whether the pipeline is running."""
        return self.capture.is_running
