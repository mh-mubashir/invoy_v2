#!/usr/bin/env python3
"""
Run full pipeline: analyze existing screenshots and log to SQLite.
Uses last 3 screenshots to test activity + change detection + DB save.
"""
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")

from invoy_sdk.analyzer import MoondreamAnalyzer
from invoy_sdk.activity_log import SQLiteActivityLog

def main():
    imgs = sorted(Path("screenshots").glob("*.png"))[-3:]
    if not imgs:
        print("No screenshots found in ./screenshots/")
        return

    analyzer = MoondreamAnalyzer(model="moondream:1.8b-v2-q8_0", fallback_model=None)
    log = SQLiteActivityLog(db_path="./activity_log.db")

    print(f"Analyzing {len(imgs)} screenshots and logging to activity_log.db...\n")
    prev = None
    for i, img in enumerate(imgs):
        print(f"[{i+1}/{len(imgs)}] {img.name}...", flush=True)
        activity, activity_ms = analyzer.analyze(str(img))
        change_summary, change_ms = None, None
        if prev:
            change_summary, change_ms = analyzer.analyze_change(str(img), str(prev))

        entry_id = log.log(
            screenshot_path=str(img),
            activity=activity,
            change_summary=change_summary,
            activity_inference_ms=activity_ms,
            change_inference_ms=change_ms,
        )
        print(f"  Logged {entry_id[:8]}... | Activity: {(activity or '')[:60]}...")
        prev = img

    log.close()
    print("\nDone. Check: sqlite3 activity_log.db \"SELECT id, substr(activity,1,80) FROM activity_entries ORDER BY unix_time DESC LIMIT 5\"")

if __name__ == "__main__":
    main()
