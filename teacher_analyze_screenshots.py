#!/usr/bin/env python3
"""
Teacher analysis over screenshots using a strong cloud VLM (e.g. OpenAI).

This script:
- Iterates over a directory of PNG screenshots.
- Calls a "teacher" model with the same billing-focused prompts used in `MoondreamAnalyzer`,
  but via a cloud API (e.g. OpenAI's /chat/completions with vision).
- Stores the teacher outputs in a separate SQLite table, keyed by screenshot path.

Environment:
- Set OPENAI_API_KEY to use the OpenAI API.

Usage example:
    python teacher_analyze_screenshots.py \\
        --screenshots-dir ./screenshots_monitor1_10s \\
        --db-path ./activity_offline.db \\
        --teacher-model gpt-4.1-mini
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import sqlite3


TEACHER_ACTIVITY_PROMPT = """You are an expert time-tracking assistant. Your job is to generate very precise, billing-grade descriptions
of what work a person is doing based on a single desktop screenshot.

GOAL: Produce a description that could appear on an invoice, and a structured label that makes it easy
to group similar screenshots into the same work activity.

Given this screenshot, do ALL of the following:

1. Write a dense, 3–6 sentence description of the EXACT work being done, focusing on:
   - The main application(s) visible and their role (e.g. "VS Code editing payment_service.py",
     "Chrome showing GitHub PR #123", "Outlook composing an email").
   - The specific artifact(s): filenames, URLs, document titles, issue IDs, PR numbers, JIRA tickets, etc.
   - The concrete task: e.g. "implementing a new endpoint", "fixing a failing unit test",
     "writing product requirements", "answering a customer support email".
   - Any visible project or client names (if present on screen).

2. Infer a single most likely BILLING ACTIVITY label with this JSON structure:
   {
     "activity_label": "<short label suitable for an invoice line item>",
     "category": "<one of: coding, code_review, debugging, documentation, reading_docs, email_comms,
                   messaging_comms, planning/notes, admin/other>",
     "primary_tool": "<e.g. VS Code, Cursor, Chrome, Firefox, Outlook, Slack, Notion, Terminal>",
     "artifact": "<main file/doc/page, e.g. payment_service.py, PR #123, design_spec.md, customer_email>",
     "client_or_project": "<if inferable, else null>"
   }

3. Make sure your activity_label is specific enough that if many screenshots with the same label are grouped
   together, they represent a coherent block of work that could be billed as a unit.

Return your answer as:
- First, the free-form description.
- Then a line starting with 'JSON:' followed by ONLY the JSON object."""


TEACHER_CHANGE_PROMPT = """You are comparing TWO desktop screenshots: image A (previous) and image B (current).

Goal: Decide if the person is doing the SAME BILLING ACTIVITY or a DIFFERENT one between A and B.

1. In 2–4 sentences, explain:
   - What the person is doing in A vs B.
   - Whether this is the same underlying task (e.g. continuing the same implementation, same PR review,
     same email thread) or a different task (e.g. switching to a new feature, new PR, different document).

2. Output a JSON object:
   {
     "same_activity": true/false,
     "reason": "<short explanation>",
     "new_activity_label": "<if different, proposed label for the NEW activity; else null>"
   }

Return the explanation first, then a line starting with 'JSON:' and the JSON object."""


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


@dataclass
class TeacherResult:
    activity_text: str
    activity_json: Optional[dict[str, Any]]
    change_text: Optional[str]
    change_json: Optional[dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run teacher VLM analysis over screenshots and store in SQLite."
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
        help="SQLite database path (same DB as student entries).",
    )
    parser.add_argument(
        "--teacher-model",
        type=str,
        default="gpt-4.1-mini",
        help="Teacher model name (e.g. OpenAI vision-capable model).",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default="https://api.openai.com/v1",
        help="Base URL for the teacher model API (OpenAI-compatible).",
    )
    parser.add_argument(
        "--skip-change",
        action="store_true",
        help="If set, only run single-image activity analysis (no change comparison).",
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


def _get_openai_client(api_base: str, api_key: str):
    try:
        from openai import OpenAI
    except ImportError as e:  # pragma: no cover - import guard
        raise SystemExit("openai package required. Install with: pip install openai") from e
    return OpenAI(base_url=api_base, api_key=api_key)


def run_teacher_on_pair(
    client,
    model: str,
    current_image: Path,
    previous_image: Optional[Path],
    skip_change: bool,
) -> TeacherResult:
    # Activity (single image)
    activity_resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": TEACHER_ACTIVITY_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": current_image.resolve().as_uri(),
                        },
                    },
                ],
            }
        ],
    )
    activity_text = activity_resp.choices[0].message.content or ""
    activity_json = _extract_json_from_text(activity_text)

    change_text: Optional[str] = None
    change_json: Optional[dict[str, Any]] = None
    if not skip_change and previous_image is not None:
        change_resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": TEACHER_CHANGE_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": previous_image.resolve().as_uri(),
                            },
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": current_image.resolve().as_uri(),
                            },
                        },
                    ],
                }
            ],
        )
        change_text = change_resp.choices[0].message.content or ""
        change_json = _extract_json_from_text(change_text)

    return TeacherResult(
        activity_text=activity_text,
        activity_json=activity_json,
        change_text=change_text,
        change_json=change_json,
    )


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("teacher_analyze_screenshots")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable is not set.")
        sys.exit(1)

    screenshots_dir = Path(args.screenshots_dir)
    if not screenshots_dir.exists() or not screenshots_dir.is_dir():
        logger.error("Screenshots directory does not exist or is not a directory: %s", screenshots_dir)
        sys.exit(1)

    screenshots = _list_screenshots(screenshots_dir)
    if not screenshots:
        logger.error("No PNG screenshots found in %s", screenshots_dir)
        sys.exit(1)

    logger.info("Found %d screenshots in %s", len(screenshots), screenshots_dir)
    logger.info("Teacher model: %s", args.teacher_model)
    logger.info("DB path: %s", args.db_path)

    client = _get_openai_client(api_base=args.api_base, api_key=api_key)

    # Connect to SQLite and ensure teacher table exists
    conn = sqlite3.connect(str(Path(args.db_path)))
    conn.executescript(SCHEMA_TEACHER)
    conn.row_factory = sqlite3.Row

    previous_path: Optional[Path] = None

    for idx, img_path in enumerate(screenshots, start=1):
        logger.info("Teacher analyzing screenshot %d/%d: %s", idx, len(screenshots), img_path.name)
        result = run_teacher_on_pair(
            client=client,
            model=args.teacher_model,
            current_image=img_path,
            previous_image=previous_path,
            skip_change=args.skip_change,
        )

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
                result.activity_text,
                json.dumps(result.activity_json) if result.activity_json is not None else None,
                result.change_text,
                json.dumps(result.change_json) if result.change_json is not None else None,
                args.teacher_model,
            ),
        )
        conn.commit()
        previous_path = img_path

    conn.close()
    logger.info("Teacher analysis complete. Results saved to %s", args.db_path)


if __name__ == "__main__":
    main()

