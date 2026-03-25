#!/usr/bin/env python3
"""
Offline analysis of pre-collected screenshots for Invoy experiments.

Given a directory of screenshots, this script:
  - Sorts them chronologically,
  - Runs activity and change analysis with **Qwen2-VL / Qwen2.5-VL** (Hugging Face) via ScreenActivityAnalyzer,
  - Logs results into SQLite using SQLiteActivityLog.

Separate data collection (e.g. collect_screenshots.py) from VLM inference. Install weights:
  pip install -e ".[vlm-native]"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

from invoy_sdk.activity_log import SQLiteActivityLog
from invoy_sdk.analyzer import ScreenActivityAnalyzer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run offline Qwen VL analysis over a directory of screenshots and log to SQLite."
    )
    parser.add_argument(
        "--screenshots-dir",
        type=str,
        required=True,
        help="Directory containing PNG screenshots (e.g. from collect_screenshots.py).",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="./activity_offline.db",
        help="SQLite database path for logging analysis results.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="Qwen/Qwen2-VL-2B-Instruct",
        help="Hugging Face Qwen2-VL or Qwen2.5-VL model id.",
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
        help="Force fast path (single extraction view; shorter outputs). Default on CPU.",
    )
    vlm_speed.add_argument(
        "--full-vlm-views",
        action="store_true",
        help="Force multi-view extraction (slower on CPU; better OCR).",
    )
    parser.add_argument(
        "--prompt-version",
        type=str,
        default="activity_dense_v1_change_v1",
        help="Identifier for the prompt configuration used.",
    )
    parser.add_argument(
        "--session-tag",
        type=str,
        default="offline_analysis",
        help="Session identifier used in SQLite to group this run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of screenshots to analyze (0 = all).",
    )
    return parser.parse_args()


def _list_screenshots(dir_path: Path) -> List[Path]:
    files = sorted(p for p in dir_path.glob("*.png") if p.is_file())
    return files


def main() -> None:
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("offline_analyze_screenshots")

    screenshots_dir = Path(args.screenshots_dir)
    if not screenshots_dir.exists() or not screenshots_dir.is_dir():
        logger.error("Screenshots directory does not exist or is not a directory: %s", screenshots_dir)
        sys.exit(1)

    screenshots = _list_screenshots(screenshots_dir)
    if not screenshots:
        logger.error("No PNG screenshots found in %s", screenshots_dir)
        sys.exit(1)

    if args.limit and args.limit > 0:
        screenshots = screenshots[: args.limit]

    logger.info("Found %d screenshots in %s", len(screenshots), screenshots_dir)
    logger.info("Model: %s", args.model)
    logger.info("DB path: %s", args.db_path)
    logger.info("Session tag (session_id): %s", args.session_tag)

    fast_vlm_kw: bool | None = None
    if args.fast_vlm:
        fast_vlm_kw = True
    elif args.full_vlm_views:
        fast_vlm_kw = False

    analyzer = ScreenActivityAnalyzer(
        model=args.model,
        device=args.device,
        fast_vlm=fast_vlm_kw,
    )
    activity_log = SQLiteActivityLog(db_path=args.db_path, session_id=args.session_tag)

    previous_path: Path | None = None

    for idx, img_path in enumerate(screenshots, start=1):
        logger.info("Analyzing screenshot %d/%d: %s", idx, len(screenshots), img_path.name)

        activity, activity_extracted_text, activity_ms = analyzer.analyze_with_extracted(img_path)

        change_summary = None
        change_prev_extracted_text = None
        change_cur_extracted_text = None
        change_ms = None
        if previous_path is not None:
            change_summary, change_prev_extracted_text, change_cur_extracted_text, change_ms = (
                analyzer.analyze_change_with_extracted(
                    current_path=img_path,
                    previous_path=previous_path,
                )
            )

        activity_log.log(
            screenshot_path=str(img_path.resolve()),
            activity=activity,
            activity_extracted_text=activity_extracted_text,
            change_summary=change_summary,
            change_prev_extracted_text=change_prev_extracted_text,
            change_cur_extracted_text=change_cur_extracted_text,
            activity_inference_ms=activity_ms,
            change_inference_ms=change_ms,
            model_name=analyzer.model,
            prompt_version=args.prompt_version,
        )

        previous_path = img_path

    activity_log.close()
    logger.info("Offline analysis complete. Results saved to %s", args.db_path)


if __name__ == "__main__":
    main()

