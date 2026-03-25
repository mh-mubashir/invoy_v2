#!/usr/bin/env python3
"""
Simplified two-model GPU workflow:
1) Run model A over screenshots -> simplified_activity_entries
2) Run model B over screenshots -> simplified_activity_entries
3) Persist side-by-side comparison -> model_comparison_results

This script intentionally uses a reduced schema focused on descriptive activity
and change text with extracted evidence.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Iterable

from invoy_sdk.vlm_backends import Qwen2VLBackend

SCHEMA_RUN = """
CREATE TABLE IF NOT EXISTS simplified_activity_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screenshot_path TEXT NOT NULL,
    frame_index INTEGER NOT NULL,
    run_label TEXT NOT NULL,
    model_name TEXT NOT NULL,
    activity_text TEXT,
    activity_extracted_text TEXT,
    change_text TEXT,
    change_prev_extracted_text TEXT,
    change_cur_extracted_text TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_simplified_run_label ON simplified_activity_entries(run_label);
CREATE INDEX IF NOT EXISTS idx_simplified_frame_idx ON simplified_activity_entries(frame_index);
CREATE INDEX IF NOT EXISTS idx_simplified_shot_path ON simplified_activity_entries(screenshot_path);
"""

SCHEMA_COMPARE = """
CREATE TABLE IF NOT EXISTS model_comparison_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_index INTEGER NOT NULL,
    screenshot_path TEXT NOT NULL,
    model_a_name TEXT NOT NULL,
    model_b_name TEXT NOT NULL,
    model_a_activity_text TEXT,
    model_b_activity_text TEXT,
    model_a_change_text TEXT,
    model_b_change_text TEXT,
    model_a_activity_extracted_text TEXT,
    model_b_activity_extracted_text TEXT,
    model_a_change_prev_extracted_text TEXT,
    model_b_change_prev_extracted_text TEXT,
    model_a_change_cur_extracted_text TEXT,
    model_b_change_cur_extracted_text TEXT,
    has_change_a INTEGER NOT NULL,
    has_change_b INTEGER NOT NULL,
    change_presence_match INTEGER NOT NULL,
    activity_exact_match INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_compare_frame_idx ON model_comparison_results(frame_index);
CREATE INDEX IF NOT EXISTS idx_compare_shot_path ON model_comparison_results(screenshot_path);
"""

ACTIVITY_PROMPT = (
    "You are analyzing a single desktop screenshot.\n\n"
    "Write 2–4 sentences describing the SPECIFIC work the person is doing right now.\n\n"
    "Rules:\n"
    "- Name the main active application and, if readable, the window/page/document title.\n"
    "- Mention any clearly visible tab names, headings, file names, URLs, or key UI labels as evidence.\n"
    "- Do NOT guess details you cannot read; if text is too small/blurry, say \"text not readable\".\n"
    "- Focus on the active window, not background apps.\n"
    "- Plain text only (no bullets, no JSON).\n"
)

CHANGE_FROM_ACTIVITY_TEXT_PROMPT = (
    "You are given two activity descriptions of consecutive desktop screenshots: PREVIOUS then CURRENT.\n\n"
    "Task:\n"
    "1) Describe what changed between PREVIOUS and CURRENT in 1–3 sentences.\n"
    "2) State whether it looks like the SAME task or a DIFFERENT task.\n\n"
    "Rules:\n"
    "- Use ONLY the provided text; do not assume anything not stated.\n"
    "- If the text is too vague or missing, say \"uncertain\" and explain what information is missing.\n"
    "- Plain text only.\n\n"
    "PREVIOUS:\n"
    "{prev}\n\n"
    "CURRENT:\n"
    "{cur}\n"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run simplified two-model GPU analysis and compare.")
    parser.add_argument("--screenshots-dir", type=str, required=True, help="Directory containing PNG screenshots.")
    parser.add_argument(
        "--model-a",
        type=str,
        default="Qwen/Qwen2-VL-2B-Instruct",
        help="First model for simplified run.",
    )
    parser.add_argument(
        "--model-b",
        type=str,
        default="Qwen/Qwen2.5-VL-3B-Instruct",
        help="Second model for simplified run.",
    )
    parser.add_argument(
        "--run-a-db",
        type=str,
        default="qwen2vl2b_gpu_activity_change.db",
        help="Output DB for model A simplified rows.",
    )
    parser.add_argument(
        "--run-b-db",
        type=str,
        default="qwen25vl3b_gpu_activity_change.db",
        help="Output DB for model B simplified rows.",
    )
    parser.add_argument(
        "--eval-db",
        type=str,
        default="model_compare_eval_gpu.db",
        help="Output DB for model comparison results.",
    )
    parser.add_argument("--run-a-label", type=str, default="run_qwen2vl2b_gpu", help="run_label for model A.")
    parser.add_argument("--run-b-label", type=str, default="run_qwen25vl3b_gpu", help="run_label for model B.")
    parser.add_argument("--device", type=str, default="cuda", help="Device to use: cuda/cpu/mps/auto.")
    parser.add_argument(
        "--fast-vlm",
        action="store_true",
        default=True,
        help="Enable fast mode for lower VRAM use (default true).",
    )
    parser.add_argument(
        "--activity-only",
        action="store_true",
        default=False,
        help="Only run per-screenshot activity generation (skips CHANGE generation between frames).",
    )
    parser.add_argument(
        "--db-commit-every",
        type=int,
        default=25,
        help="Commit SQLite every N inserted rows to reduce stalls (use 1 to commit every row).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit for quick testing (0 means all screenshots).",
    )
    parser.add_argument(
        "--activity-max-tokens",
        type=int,
        default=128,
        help="Max new tokens for activity description.",
    )
    parser.add_argument(
        "--change-max-tokens",
        type=int,
        default=96,
        help="Max new tokens for change description.",
    )
    return parser.parse_args()


def _list_screenshots(path: Path) -> list[Path]:
    return sorted(p for p in path.glob("*.png") if p.is_file())


def _ensure_schema(db_path: Path, schema_sql: str) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql)
    return conn


def _normalize_text(v: str | None) -> str:
    return (v or "").strip()


def run_single_model(
    *,
    screenshots: Iterable[Path],
    db_path: Path,
    model_name: str,
    run_label: str,
    device: str,
    fast_vlm: bool,
    activity_only: bool,
    activity_max_tokens: int,
    change_max_tokens: int,
    db_commit_every: int,
) -> int:
    logger = logging.getLogger("simplified_run")
    conn = _ensure_schema(db_path, SCHEMA_RUN)
    # NOTE on timing comparisons:
    # - This script can call the backend 2x per screenshot after the first frame: ACTIVITY(frame)
    #   and CHANGE(prev, frame). A single-image smoke test (like `qwen2_vl_canvas_test.py`)
    #   performs only 1 backend call per image.
    # - SQLite `commit()` calls can also add periodic stalls. `--activity-only` and
    #   `--db-commit-every` exist to make timing more comparable.
    #
    # Direct backend path (1 activity call per frame + 1 change call from frame 2 onward)
    # is substantially faster than the grounded extract/retry pipeline.
    backend = Qwen2VLBackend(model_id=model_name, device=device)

    # Fresh run for this label so repeated executions are deterministic.
    conn.execute("DELETE FROM simplified_activity_entries WHERE run_label = ?", (run_label,))
    conn.commit()

    commit_every = max(1, db_commit_every)
    screenshots_list = list(screenshots)
    # Cache absolute paths so the hot loop does not repeatedly call Path.resolve().
    screenshots_info = [(shot, str(shot.resolve())) for shot in screenshots_list]

    previous_activity_text: str | None = None
    count = 0
    rows_since_commit = 0
    for idx, (shot, shot_abs) in enumerate(screenshots_info, start=1):
        activity_text, activity_ms = backend.generate(
            prompt=ACTIVITY_PROMPT,
            image_paths=[shot_abs],
            max_new_tokens=activity_max_tokens,
        )
        activity_extracted = ""  # simplified schema keeps extracted fields for compatibility

        change_text = None
        change_prev_extracted = None
        change_cur_extracted = None
        change_ms = 0.0

        if (not activity_only) and previous_activity_text is not None:
            # Text-only change: compare previous+current activity descriptions.
            # This is faster than re-encoding two images, but depends on activity quality.
            prev = _normalize_text(previous_activity_text)
            cur = _normalize_text(activity_text)
            change_prompt = CHANGE_FROM_ACTIVITY_TEXT_PROMPT.format(prev=prev or "(empty)", cur=cur or "(empty)")
            change_text, change_ms = backend.generate(
                prompt=change_prompt,
                image_paths=[],
                max_new_tokens=change_max_tokens,
            )
            change_prev_extracted = ""
            change_cur_extracted = ""

        db_start = time.perf_counter()
        conn.execute(
            """
            INSERT INTO simplified_activity_entries (
                screenshot_path, frame_index, run_label, model_name,
                activity_text, activity_extracted_text,
                change_text, change_prev_extracted_text, change_cur_extracted_text,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                shot_abs,
                idx,
                run_label,
                model_name,
                _normalize_text(activity_text),
                _normalize_text(activity_extracted),
                _normalize_text(change_text),
                _normalize_text(change_prev_extracted),
                _normalize_text(change_cur_extracted),
            ),
        )

        count += 1
        rows_since_commit += 1
        committed_now = False
        if commit_every == 1 or rows_since_commit >= commit_every:
            conn.commit()
            committed_now = True
            rows_since_commit = 0
        db_ms = (time.perf_counter() - db_start) * 1000

        # One line per frame with inference + DB timing.
        # (Wall time per image ~= activity_ms + change_ms + db_ms, plus any Python overhead.)
        logger.info(
            "[%s] idx=%d shot=%s activity_ms=%.1f change_ms=%.1f db_ms=%.1f%s",
            run_label,
            idx,
            shot.name,
            activity_ms or 0.0,
            change_ms or 0.0,
            db_ms,
            " commit" if committed_now else "",
        )

        previous_activity_text = activity_text

    # Flush remaining pending inserts.
    if rows_since_commit > 0:
        conn.commit()
    conn.close()
    return count


def persist_comparison(
    *,
    db_a: Path,
    db_b: Path,
    eval_db: Path,
    run_a_label: str,
    run_b_label: str,
) -> int:
    conn_a = _ensure_schema(db_a, SCHEMA_RUN)
    conn_b = _ensure_schema(db_b, SCHEMA_RUN)
    conn_eval = _ensure_schema(eval_db, SCHEMA_COMPARE)
    conn_eval.execute("DELETE FROM model_comparison_results")
    conn_eval.commit()

    a_rows = conn_a.execute(
        """
        SELECT screenshot_path, frame_index, model_name,
               activity_text, activity_extracted_text,
               change_text, change_prev_extracted_text, change_cur_extracted_text
        FROM simplified_activity_entries
        WHERE run_label = ?
        ORDER BY frame_index ASC
        """,
        (run_a_label,),
    ).fetchall()
    b_rows = conn_b.execute(
        """
        SELECT screenshot_path, frame_index, model_name,
               activity_text, activity_extracted_text,
               change_text, change_prev_extracted_text, change_cur_extracted_text
        FROM simplified_activity_entries
        WHERE run_label = ?
        ORDER BY frame_index ASC
        """,
        (run_b_label,),
    ).fetchall()

    b_by_key = {(r[1], r[0]): r for r in b_rows}
    inserted = 0
    for a in a_rows:
        key = (a[1], a[0])
        b = b_by_key.get(key)
        if not b:
            continue
        has_change_a = 1 if _normalize_text(a[5]) else 0
        has_change_b = 1 if _normalize_text(b[5]) else 0
        change_presence_match = 1 if has_change_a == has_change_b else 0
        activity_exact_match = 1 if _normalize_text(a[3]) == _normalize_text(b[3]) else 0

        conn_eval.execute(
            """
            INSERT INTO model_comparison_results (
                frame_index, screenshot_path,
                model_a_name, model_b_name,
                model_a_activity_text, model_b_activity_text,
                model_a_change_text, model_b_change_text,
                model_a_activity_extracted_text, model_b_activity_extracted_text,
                model_a_change_prev_extracted_text, model_b_change_prev_extracted_text,
                model_a_change_cur_extracted_text, model_b_change_cur_extracted_text,
                has_change_a, has_change_b, change_presence_match, activity_exact_match,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                a[1],
                a[0],
                a[2],
                b[2],
                _normalize_text(a[3]),
                _normalize_text(b[3]),
                _normalize_text(a[5]),
                _normalize_text(b[5]),
                _normalize_text(a[4]),
                _normalize_text(b[4]),
                _normalize_text(a[6]),
                _normalize_text(b[6]),
                _normalize_text(a[7]),
                _normalize_text(b[7]),
                has_change_a,
                has_change_b,
                change_presence_match,
                activity_exact_match,
            ),
        )
        inserted += 1

    conn_eval.commit()
    conn_a.close()
    conn_b.close()
    conn_eval.close()
    return inserted


def main() -> None:
    args = parse_args()
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logger = logging.getLogger("simplified_gpu_two_model_compare")

    shots_dir = Path(args.screenshots_dir)
    if not shots_dir.exists() or not shots_dir.is_dir():
        raise SystemExit(f"Invalid screenshots dir: {shots_dir}")

    shots = _list_screenshots(shots_dir)
    if args.limit > 0:
        shots = shots[: args.limit]
    if not shots:
        raise SystemExit(f"No PNG screenshots found in: {shots_dir}")

    logger.info("Screenshots: %d", len(shots))
    logger.info("Run A model: %s", args.model_a)
    logger.info("Run B model: %s", args.model_b)
    logger.info("Device: %s | fast_vlm=%s", args.device, args.fast_vlm)
    logger.info("activity_only=%s | db_commit_every=%d", args.activity_only, args.db_commit_every)
    if args.db_commit_every < 1:
        raise SystemExit("--db-commit-every must be >= 1")

    count_a = run_single_model(
        screenshots=shots,
        db_path=Path(args.run_a_db),
        model_name=args.model_a,
        run_label=args.run_a_label,
        device=args.device,
        fast_vlm=args.fast_vlm,
        activity_only=args.activity_only,
        activity_max_tokens=args.activity_max_tokens,
        change_max_tokens=args.change_max_tokens,
        db_commit_every=args.db_commit_every,
    )
    logger.info("Run A rows written: %d", count_a)

    count_b = run_single_model(
        screenshots=shots,
        db_path=Path(args.run_b_db),
        model_name=args.model_b,
        run_label=args.run_b_label,
        device=args.device,
        fast_vlm=args.fast_vlm,
        activity_only=args.activity_only,
        activity_max_tokens=args.activity_max_tokens,
        change_max_tokens=args.change_max_tokens,
        db_commit_every=args.db_commit_every,
    )
    logger.info("Run B rows written: %d", count_b)

    compared = persist_comparison(
        db_a=Path(args.run_a_db),
        db_b=Path(args.run_b_db),
        eval_db=Path(args.eval_db),
        run_a_label=args.run_a_label,
        run_b_label=args.run_b_label,
    )
    logger.info("Comparison rows written: %d", compared)
    logger.info("Done.")


if __name__ == "__main__":
    main()

