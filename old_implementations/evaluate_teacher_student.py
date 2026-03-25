#!/usr/bin/env python3
"""
Compare baseline (small local Qwen) vs strong (larger local Qwen) labeling.

- Baseline rows: ``activity_entries`` from ``offline_analyze_screenshots.py`` (e.g. Qwen2-VL-2B).
- Strong rows: ``teacher_activity_entries`` from ``teacher_analyze_screenshots.py`` (e.g. Qwen2.5-VL-3B).

Joins on ``screenshot_path``. Agreement stats use ``JSON:`` footers when present.
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


def load_pairs(
    db_path: Path,
    *,
    baseline_session_id: Optional[str] = None,
    baseline_model_substr: Optional[str] = None,
    strong_teacher_model: Optional[str] = None,
) -> list[PairRow]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    student_sql = """
        SELECT screenshot_path, activity, change_summary
        FROM activity_entries
        WHERE (?1 IS NULL OR session_id = ?1)
          AND (?2 IS NULL OR model_name LIKE '%' || ?2 || '%')
    """
    student_rows = conn.execute(
        student_sql,
        (baseline_session_id, baseline_model_substr),
    ).fetchall()

    teacher_sql = """
        SELECT id, screenshot_path, activity_text, activity_json, change_text, change_json, teacher_model
        FROM teacher_activity_entries
        WHERE (? IS NULL OR teacher_model = ?)
        ORDER BY id ASC
    """
    teacher_rows = conn.execute(
        teacher_sql,
        (strong_teacher_model, strong_teacher_model),
    ).fetchall()
    conn.close()

    teacher_by_path: dict[str, sqlite3.Row] = {}
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
                "baseline_activity_label",
                "baseline_category",
                "strong_activity_label",
                "strong_category",
                "baseline_same_activity",
                "strong_same_activity",
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
        description="Evaluate agreement between baseline (small) and strong (large) local Qwen runs."
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
        help="Optional session_id filter for baseline rows in activity_entries.",
    )
    parser.add_argument(
        "--baseline-model-substr",
        type=str,
        default=None,
        help="Optional substring filter on activity_entries.model_name (e.g. 2B-Instruct).",
    )
    parser.add_argument(
        "--teacher-model",
        type=str,
        default=None,
        help="Optional exact teacher_model value for strong rows (e.g. Qwen/Qwen2.5-VL-3B-Instruct).",
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
    pairs = load_pairs(
        db_path=db_path,
        baseline_session_id=args.session_id,
        baseline_model_substr=args.baseline_model_substr,
        strong_teacher_model=args.teacher_model,
    )
    stats = evaluate(pairs)

    print("Baseline vs strong Qwen evaluation summary")
    if args.session_id:
        print(f"  Baseline session_id:          {args.session_id}")
    if args.baseline_model_substr:
        print(f"  Baseline model_name contains:  {args.baseline_model_substr!r}")
    if args.teacher_model:
        print(f"  Strong teacher_model:          {args.teacher_model}")
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

