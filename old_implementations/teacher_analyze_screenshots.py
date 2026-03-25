#!/usr/bin/env python3
"""
Strong / teacher Qwen run over screenshots (local Hugging Face).

Uses the same extract → describe pipeline as offline_analyze_screenshots.py (ScreenActivityAnalyzer),
with a typically larger model (default Qwen2.5-VL-3B-Instruct). Results go to ``teacher_activity_entries``
for comparison with baseline (small Qwen) rows in ``activity_entries`` — see evaluate_teacher_student.py.

Usage:
    python teacher_analyze_screenshots.py \\
        --screenshots-dir ./screenshots_test \\
        --db-path ./activity_offline.db \\
        --teacher-model Qwen/Qwen2.5-VL-3B-Instruct
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, List, Optional

import sqlite3

from invoy_sdk.analyzer import ScreenActivityAnalyzer

SCHEMA_TEACHER = """
CREATE TABLE IF NOT EXISTS teacher_activity_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screenshot_path TEXT NOT NULL,
    timestamp TEXT,
    unix_time REAL,
    activity_text TEXT,
    activity_json TEXT,
    change_text TEXT,
    change_json TEXT,
    teacher_model TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_teacher_screenshot_path ON teacher_activity_entries(screenshot_path);
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run strong (teacher) Qwen VL analysis over screenshots and store in SQLite."
    )
    parser.add_argument(
        "--screenshots-dir",
        type=str,
        required=True,
        help="Directory containing PNG screenshots.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./activity_offline.db",
        help="SQLite database path (same DB as baseline student entries).",
    )
    parser.add_argument(
        "--teacher-model",
        type=str,
        default="Qwen/Qwen2.5-VL-3B-Instruct",
        help="Hugging Face Qwen VL model id for the strong run.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device: auto, cpu, cuda, mps.",
    )
    vlm_speed = parser.add_mutually_exclusive_group()
    vlm_speed.add_argument(
        "--fast-vlm",
        action="store_true",
        help="Single extraction view; shorter generations.",
    )
    vlm_speed.add_argument(
        "--full-vlm-views",
        action="store_true",
        help="Multi-view extraction (slower on CPU).",
    )
    parser.add_argument(
        "--skip-change",
        action="store_true",
        help="Only run single-image activity analysis (no change comparison).",
    )
    return parser.parse_args()


def _list_screenshots(dir_path: Path) -> List[Path]:
    return sorted(p for p in dir_path.glob("*.png") if p.is_file())


def _extract_json_from_text(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    try:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("JSON:"):
                json_str = line[len("JSON:") :].strip()
                if not json_str:
                    continue
                return json.loads(json_str)
    except Exception:
        return None
    return None


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("teacher_analyze_screenshots")

    screenshots_dir = Path(args.screenshots_dir)
    if not screenshots_dir.exists() or not screenshots_dir.is_dir():
        logger.error("Screenshots directory does not exist or is not a directory: %s", screenshots_dir)
        sys.exit(1)

    screenshots = _list_screenshots(screenshots_dir)
    if not screenshots:
        logger.error("No PNG screenshots found in %s", screenshots_dir)
        sys.exit(1)

    logger.info("Found %d screenshots in %s", len(screenshots), screenshots_dir)
    logger.info("Strong model: %s", args.teacher_model)
    logger.info("DB path: %s", args.db_path)

    fast_vlm_kw: bool | None = None
    if args.fast_vlm:
        fast_vlm_kw = True
    elif args.full_vlm_views:
        fast_vlm_kw = False

    analyzer = ScreenActivityAnalyzer(
        model=args.teacher_model,
        device=args.device,
        fast_vlm=fast_vlm_kw,
    )

    conn = sqlite3.connect(str(Path(args.db_path)))
    conn.executescript(SCHEMA_TEACHER)

    previous_path: Optional[Path] = None

    for idx, img_path in enumerate(screenshots, start=1):
        logger.info("Strong Qwen analyzing screenshot %d/%d: %s", idx, len(screenshots), img_path.name)
        activity, _extracted, _ms = analyzer.analyze_with_extracted(img_path)
        activity_json = _extract_json_from_text(activity or "")

        change_text: Optional[str] = None
        change_json: Optional[dict[str, Any]] = None
        if not args.skip_change and previous_path is not None:
            change_text, _p, _c, _cms = analyzer.analyze_change_with_extracted(
                current_path=img_path,
                previous_path=previous_path,
            )
            change_json = _extract_json_from_text(change_text or "")

        conn.execute(
            """
            INSERT INTO teacher_activity_entries
            (screenshot_path, timestamp, unix_time,
             activity_text, activity_json,
             change_text, change_json,
             teacher_model, created_at)
            VALUES (?, NULL, NULL, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                str(img_path.resolve()),
                activity,
                json.dumps(activity_json) if activity_json is not None else None,
                change_text,
                json.dumps(change_json) if change_json is not None else None,
                args.teacher_model,
            ),
        )
        conn.commit()
        previous_path = img_path

    conn.close()
    logger.info("Strong Qwen analysis complete. Results saved to %s", args.db_path)


if __name__ == "__main__":
    main()

