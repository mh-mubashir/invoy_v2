#!/usr/bin/env python3
"""
Offline analysis of pre-collected screenshots for Invoy experiments.

Given a directory of screenshots, this script:
  - Sorts them chronologically,
  - Runs activity and change analysis with a chosen VLM via Ollama,
  - Logs results into a SQLite database using SQLiteActivityLog.

This lets you separate data collection (screenshot capture) from VLM inference.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

from invoy_sdk.analyzer import MoondreamAnalyzer
from invoy_sdk.activity_log import SQLiteActivityLog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run offline VLM analysis over a directory of screenshots and log to SQLite."
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
        default="moondream:1.8b-v2-q8_0",
        help="Ollama vision model to use for analysis.",
    )
    parser.add_argument(
        "--extractor-model",
        type=str,
        default=None,
        help="Optional Ollama model to use only for OCR-style text extraction (e.g. llava).",
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
        "--ollama-host",
        type=str,
        default="http://localhost:11434",
        help="Ollama host URL.",
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
    if args.extractor_model:
        logger.info("Extractor model: %s", args.extractor_model)
    logger.info("DB path: %s", args.db_path)
    logger.info("Session tag (session_id): %s", args.session_tag)

    analyzer = MoondreamAnalyzer(
        model=args.model,
        host=args.ollama_host,
        fallback_model="moondream",
        extractor_model=args.extractor_model,
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

