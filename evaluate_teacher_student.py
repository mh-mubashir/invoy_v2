#!/usr/bin/env python3
"""
Compare "student" (local VLM via Ollama) vs "teacher" (cloud VLM) labels.

This script:
- Reads student entries from `activity_entries` (in `SQLiteActivityLog`).
- Reads teacher entries from `teacher_activity_entries` (created by teacher_analyze_screenshots.py).
- Joins them on `screenshot_path`.
- Computes simple agreement stats on:
  - activity_label
  - category
  - same_activity (if teacher change JSON is available and student change_summary contains JSON).

Outputs a textual summary and optional CSV for deeper analysis.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


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


@dataclass
class PairRow:
    screenshot_path: str
    student_activity_json: Optional[dict[str, Any]]
    student_change_json: Optional[dict[str, Any]]
    teacher_activity_json: Optional[dict[str, Any]]
    teacher_change_json: Optional[dict[str, Any]]


def load_pairs(db_path: Path, session_id: Optional[str] = None) -> list[PairRow]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if session_id:
        student_rows = conn.execute(
            """
            SELECT screenshot_path, activity, change_summary
            FROM activity_entries
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchall()
    else:
        student_rows = conn.execute(
            """
            SELECT screenshot_path, activity, change_summary
            FROM activity_entries
            """
        ).fetchall()

    teacher_rows = conn.execute(
        """
        SELECT screenshot_path, activity_text, activity_json, change_text, change_json
        FROM teacher_activity_entries
        """
    ).fetchall()
    conn.close()

    teacher_by_path = {}
    for row in teacher_rows:
        teacher_by_path[row["screenshot_path"]] = row

    pairs: list[PairRow] = []
    for srow in student_rows:
        spath = srow["screenshot_path"]
        trow = teacher_by_path.get(spath)
        if not trow:
            continue
        student_activity_json = _extract_json_from_text(srow["activity"] or "")
        student_change_json = _extract_json_from_text(srow["change_summary"] or "")
        teacher_activity_json: Optional[dict[str, Any]] = None
        teacher_change_json: Optional[dict[str, Any]] = None
        if trow["activity_json"]:
            try:
                teacher_activity_json = json.loads(trow["activity_json"])
            except Exception:
                teacher_activity_json = None
        if trow["change_json"]:
            try:
                teacher_change_json = json.loads(trow["change_json"])
            except Exception:
                teacher_change_json = None

        pairs.append(
            PairRow(
                screenshot_path=spath,
                student_activity_json=student_activity_json,
                student_change_json=student_change_json,
                teacher_activity_json=teacher_activity_json,
                teacher_change_json=teacher_change_json,
            )
        )

    return pairs


def evaluate(pairs: list[PairRow]) -> dict[str, Any]:
    total = len(pairs)
    label_agree = 0
    category_agree = 0
    same_activity_total = 0
    same_activity_agree = 0

    for p in pairs:
        s_act = p.student_activity_json or {}
        t_act = p.teacher_activity_json or {}
        if s_act and t_act:
            if s_act.get("activity_label") and t_act.get("activity_label"):
                if s_act["activity_label"] == t_act["activity_label"]:
                    label_agree += 1
            if s_act.get("category") and t_act.get("category"):
                if s_act["category"] == t_act["category"]:
                    category_agree += 1

        s_change = p.student_change_json or {}
        t_change = p.teacher_change_json or {}
        if "same_activity" in s_change and "same_activity" in t_change:
            same_activity_total += 1
            if bool(s_change["same_activity"]) == bool(t_change["same_activity"]):
                same_activity_agree += 1

    return {
        "total_pairs": total,
        "label_agree": label_agree,
        "label_agree_rate": (label_agree / total) if total else 0.0,
        "category_agree": category_agree,
        "category_agree_rate": (category_agree / total) if total else 0.0,
        "same_activity_total": same_activity_total,
        "same_activity_agree": same_activity_agree,
        "same_activity_agree_rate": (same_activity_agree / same_activity_total)
        if same_activity_total
        else 0.0,
    }


def write_pairs_csv(pairs: list[PairRow], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "screenshot_path",
                "student_activity_label",
                "student_category",
                "teacher_activity_label",
                "teacher_category",
                "student_same_activity",
                "teacher_same_activity",
            ]
        )
        for p in pairs:
            s_act = p.student_activity_json or {}
            t_act = p.teacher_activity_json or {}
            s_ch = p.student_change_json or {}
            t_ch = p.teacher_change_json or {}
            writer.writerow(
                [
                    p.screenshot_path,
                    s_act.get("activity_label", ""),
                    s_act.get("category", ""),
                    t_act.get("activity_label", ""),
                    t_act.get("category", ""),
                    s_ch.get("same_activity", ""),
                    t_ch.get("same_activity", ""),
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate student vs teacher activity labeling agreement."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./activity_offline.db",
        help="SQLite database path.",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Optional session_id filter for student entries.",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help="Optional CSV output with per-pair labels.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    pairs = load_pairs(db_path=db_path, session_id=args.session_id)
    stats = evaluate(pairs)

    print("Teacher–student evaluation summary")
    print(f"  Total joined pairs:            {stats['total_pairs']}")
    print(
        f"  Activity label agreement:      {stats['label_agree']} "
        f"({stats['label_agree_rate']*100:.1f}%)"
    )
    print(
        f"  Category agreement:            {stats['category_agree']} "
        f"({stats['category_agree_rate']*100:.1f}%)"
    )
    print(
        f"  Same/different pairs covered:  {stats['same_activity_total']} "
        f"({stats['same_activity_total'] / stats['total_pairs']*100:.1f}%)"
        if stats["total_pairs"]
        else "  Same/different pairs covered:  0"
    )
    print(
        f"  Same/different agreement:      {stats['same_activity_agree']} "
        f"({stats['same_activity_agree_rate']*100:.1f}%)"
    )

    if args.output_csv:
        out_path = Path(args.output_csv)
        write_pairs_csv(pairs, out_path)
        print(f"\nWrote per-pair CSV to {out_path}")


if __name__ == "__main__":
    main()

