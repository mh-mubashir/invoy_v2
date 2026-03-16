"""
SQLite-based activity log for screen activity tracking.

Stores timestamped activity entries from MLLM analysis.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_entries (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    unix_time REAL NOT NULL,
    screenshot_path TEXT NOT NULL,
    activity TEXT,
    activity_extracted_text TEXT,
    change_summary TEXT,
    change_prev_extracted_text TEXT,
    change_cur_extracted_text TEXT,
    activity_inference_ms REAL,
    change_inference_ms REAL,
    model_name TEXT,
    prompt_version TEXT,
    activity_quality_score REAL,
    change_correct INTEGER,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_session ON activity_entries(session_id);
"""


class SQLiteActivityLog:
    """
    Logs screen activity to SQLite with timestamps.
    """

    def __init__(self, db_path: str | Path = "./activity_log.db", session_id: Optional[str] = None):
        """
        Initialize the activity log.

        Args:
            db_path: Path to SQLite database file.
            session_id: Optional session identifier. Auto-generated if not provided.
        """
        self.db_path = Path(db_path)
        self.session_id = session_id or str(uuid.uuid4())
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._conn.executescript(SCHEMA)
            self._conn.row_factory = sqlite3.Row
            # Migration: add columns if missing (existing DBs)
            for col, typ in [
                ("change_summary", "TEXT"),
                ("activity_extracted_text", "TEXT"),
                ("change_prev_extracted_text", "TEXT"),
                ("change_cur_extracted_text", "TEXT"),
                ("activity_inference_ms", "REAL"),
                ("change_inference_ms", "REAL"),
                ("model_name", "TEXT"),
                ("prompt_version", "TEXT"),
                ("activity_quality_score", "REAL"),
                ("change_correct", "INTEGER"),
            ]:
                try:
                    self._conn.execute(
                        f"ALTER TABLE activity_entries ADD COLUMN {col} {typ}"
                    )
                except sqlite3.OperationalError:
                    pass  # Column already exists
        return self._conn

    def log(
        self,
        screenshot_path: str,
        activity: Optional[str] = None,
        activity_extracted_text: Optional[str] = None,
        change_summary: Optional[str] = None,
        change_prev_extracted_text: Optional[str] = None,
        change_cur_extracted_text: Optional[str] = None,
        activity_inference_ms: Optional[float] = None,
        change_inference_ms: Optional[float] = None,
        model_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
        activity_quality_score: Optional[float] = None,
        change_correct: Optional[bool] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Log an activity entry.

        Args:
            screenshot_path: Path to the screenshot file.
            activity: MLLM-generated activity description.
            change_summary: MLLM-generated description of what changed from previous screenshot.
            activity_inference_ms: Time in ms for the activity MLLM call (edge inference).
            change_inference_ms: Time in ms for the change detection MLLM call.
            model_name: Name of the VLM model used for this inference.
            prompt_version: Identifier for the prompt configuration used.
            activity_quality_score: Optional human-provided quality rating (e.g. 1–5 scale).
            change_correct: Optional human label indicating if the change summary is correct.
            timestamp: When the screenshot was taken. Defaults to now.

        Returns:
            The generated entry ID.
        """
        ts = timestamp or datetime.now()
        entry_id = str(uuid.uuid4())

        conn = self._get_conn()
        change_correct_int: Optional[int] = None
        if change_correct is not None:
            change_correct_int = 1 if change_correct else 0
        conn.execute(
            """
            INSERT INTO activity_entries
            (id, timestamp, unix_time, screenshot_path, activity, activity_extracted_text,
             change_summary, change_prev_extracted_text, change_cur_extracted_text,
             activity_inference_ms, change_inference_ms, model_name, prompt_version,
             activity_quality_score, change_correct, session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                ts.isoformat(),
                ts.timestamp(),
                str(screenshot_path),
                activity or "",
                activity_extracted_text or "",
                change_summary or "",
                change_prev_extracted_text or "",
                change_cur_extracted_text or "",
                activity_inference_ms,
                change_inference_ms,
                model_name,
                prompt_version,
                activity_quality_score,
                change_correct_int,
                self.session_id,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        logger.debug("Logged activity: %s", entry_id)
        return entry_id

    def get_entries(
        self,
        limit: int = 100,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Retrieve recent activity entries.

        Args:
            limit: Maximum number of entries to return.
            session_id: Filter by session. Uses current session if None.

        Returns:
            List of entry dicts with id, timestamp, unix_time, screenshot_path, activity,
            change_summary, activity_inference_ms, change_inference_ms, model_name,
            prompt_version, activity_quality_score, change_correct, session_id.
        """
        conn = self._get_conn()
        sid = session_id or self.session_id
        cursor = conn.execute(
            """
            SELECT id, timestamp, unix_time, screenshot_path, activity, change_summary,
                   activity_extracted_text, change_prev_extracted_text, change_cur_extracted_text,
                   activity_inference_ms, change_inference_ms, model_name, prompt_version,
                   activity_quality_score, change_correct, session_id
            FROM activity_entries
            WHERE session_id = ?
            ORDER BY unix_time DESC
            LIMIT ?
            """,
            (sid, limit),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SQLiteActivityLog":
        return self

    def __exit__(self, *args) -> None:
        self.close()
