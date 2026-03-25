#!/usr/bin/env python3
"""
Summarize activity entries from SQLite into contiguous billable activity segments.

Assumes that the `activity` column contains:
- A free-form description, followed by
- A line starting with `JSON:` and a JSON object with:
  {
    "activity_label": "...",
    "category": "...",
    "primary_tool": "...",
    "artifact": "...",
    "client_or_project": "..." | null
  }

This matches the billing-focused prompt used by `ScreenActivityAnalyzer`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class FrameLabel:
    entry_id: str
    timestamp: datetime
    unix_time: float
    activity_raw: str
    activity_label: Optional[str]
    category: Optional[str]
    primary_tool: Optional[str]
    artifact: Optional[str]
    client_or_project: Optional[str]


@dataclass
class ActivitySegment:
    activity_label: str
    category: Optional[str]
    primary_tool: Optional[str]
    artifact: Optional[str]
    client_or_project: Optional[str]
    start_timestamp: datetime
    end_timestamp: datetime
    frame_count: int

    @property
    def duration_minutes(self) -> float:
        delta = self.end_timestamp - self.start_timestamp
        return delta.total_seconds() / 60.0


def _parse_activity_json(activity: str) -> dict[str, Any]:
    """
    Extract the JSON object from an activity string.

    Supports multiple formats:
    - Pure JSON object: '{"activity_label": "...", ...}'
    - JSON array with first element as stringified JSON:
      '["{ \\"activity_label\\": \\"...\\", ...}", "..."]'
    - Legacy format: free text, then a line starting with 'JSON:' followed by JSON.

    Returns {} on failure.
    """
    if not activity:
        return {}
    text = activity.strip()

    # 1) Try direct JSON parse (object or array)
    try:
        parsed = json.loads(text)
        # If it's already a dict, we're done.
        if isinstance(parsed, dict):
            return parsed
        # If it's a list where the first element is a JSON string, try to parse that.
        if isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, str):
                try:
                    inner = json.loads(first)
                    if isinstance(inner, dict):
                        return inner
                except Exception:
                    pass
    except Exception:
        pass

    # 2) Legacy: search for 'JSON:' footer line.
    try:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("JSON:"):
                json_str = line[len("JSON:") :].strip()
                if not json_str:
                    continue
                return json.loads(json_str)
    except Exception:
        # Be robust to malformed JSON; treat as unlabeled.
        return {}

    return {}


def _labels_equal(a: FrameLabel, b: FrameLabel) -> bool:
    """
    Decide whether two frame labels belong to the same underlying billing activity.

    Simple heuristic: require exact match on activity_label, category, artifact, and client_or_project.
    """
    return (
        a.activity_label
        and b.activity_label
        and a.activity_label == b.activity_label
        and a.category == b.category
        and a.artifact == b.artifact
        and a.client_or_project == b.client_or_project
    )


def load_frames(
    db_path: Path,
    session_id: Optional[str] = None,
) -> list[FrameLabel]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if session_id:
        rows = conn.execute(
            """
            SELECT id, timestamp, unix_time, activity
            FROM activity_entries
            WHERE session_id = ?
            ORDER BY unix_time ASC
            """,
            (session_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, timestamp, unix_time, activity
            FROM activity_entries
            ORDER BY unix_time ASC
            """
        ).fetchall()

    conn.close()

    frames: list[FrameLabel] = []
    for row in rows:
        ts_str = row["timestamp"]
        ts = datetime.fromisoformat(ts_str)
        meta = _parse_activity_json(row["activity"] or "")
        frames.append(
            FrameLabel(
                entry_id=row["id"],
                timestamp=ts,
                unix_time=row["unix_time"],
                activity_raw=row["activity"] or "",
                activity_label=meta.get("activity_label"),
                category=meta.get("category"),
                primary_tool=meta.get("primary_tool"),
                artifact=meta.get("artifact"),
                client_or_project=meta.get("client_or_project"),
            )
        )

    return frames


def build_segments(frames: list[FrameLabel]) -> list[ActivitySegment]:
    if not frames:
        return []

    segments: list[ActivitySegment] = []
    current: Optional[ActivitySegment] = None

    for frame in frames:
        if not frame.activity_label:
            # Unlabeled frame: either skip or close current segment.
            if current is not None:
                current.end_timestamp = frame.timestamp
                segments.append(current)
                current = None
            continue

        if current is None:
            current = ActivitySegment(
                activity_label=frame.activity_label,
                category=frame.category,
                primary_tool=frame.primary_tool,
                artifact=frame.artifact,
                client_or_project=frame.client_or_project,
                start_timestamp=frame.timestamp,
                end_timestamp=frame.timestamp,
                frame_count=1,
            )
            continue

        # Compare with previous labeled frame (implicitly represented by current segment).
        prev_frame = FrameLabel(
            entry_id="",
            timestamp=current.end_timestamp,
            unix_time=0.0,
            activity_raw="",
            activity_label=current.activity_label,
            category=current.category,
            primary_tool=current.primary_tool,
            artifact=current.artifact,
            client_or_project=current.client_or_project,
        )

        if _labels_equal(prev_frame, frame):
            current.end_timestamp = frame.timestamp
            current.frame_count += 1
        else:
            segments.append(current)
            current = ActivitySegment(
                activity_label=frame.activity_label,
                category=frame.category,
                primary_tool=frame.primary_tool,
                artifact=frame.artifact,
                client_or_project=frame.client_or_project,
                start_timestamp=frame.timestamp,
                end_timestamp=frame.timestamp,
                frame_count=1,
            )

    if current is not None:
        segments.append(current)

    return segments


def write_segments_csv(segments: list[ActivitySegment], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "activity_label",
                "category",
                "primary_tool",
                "artifact",
                "client_or_project",
                "start_timestamp",
                "end_timestamp",
                "duration_minutes",
                "frame_count",
            ]
        )
        for seg in segments:
            writer.writerow(
                [
                    seg.activity_label,
                    seg.category or "",
                    seg.primary_tool or "",
                    seg.artifact or "",
                    seg.client_or_project or "",
                    seg.start_timestamp.isoformat(),
                    seg.end_timestamp.isoformat(),
                    f"{seg.duration_minutes:.2f}",
                    seg.frame_count,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize SQLite activity entries into contiguous billing activity segments."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./activity_log.db",
        help="Path to SQLite activity log.",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Optional session_id to filter on. Defaults to all sessions.",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help="Optional path to write CSV summary. If omitted, prints a text summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    frames = load_frames(db_path=db_path, session_id=args.session_id)
    segments = build_segments(frames)

    if args.output_csv:
        out_path = Path(args.output_csv)
        write_segments_csv(segments, out_path)
        print(f"Wrote {len(segments)} segments to {out_path}")
    else:
        print(f"Found {len(segments)} activity segments.")
        for seg in segments:
            print(
                f"- {seg.start_timestamp.isoformat()} -> {seg.end_timestamp.isoformat()} "
                f"({seg.duration_minutes:.1f} min, {seg.frame_count} frames): "
                f"{seg.activity_label} [{seg.category}] / {seg.artifact} / {seg.client_or_project}"
            )


if __name__ == "__main__":
    main()

