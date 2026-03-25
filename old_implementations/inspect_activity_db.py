#!/usr/bin/env python3
"""
Quick inspection tool for activity_offline.db to see what Moondream produced.
Prints a handful of rows with activity + change snippets and tries to show the JSON footer if present.
"""

from __future__ import annotations

import json
import sqlite3
import textwrap
from pathlib import Path


def extract_json_footer(text: str) -> str:
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("JSON:"):
            return line
    return ""


def main() -> None:
    db_path = Path("activity_offline.db")
    if not db_path.exists():
        print("No activity_offline.db found in current directory.")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    cur = conn.execute(
        """
        SELECT id, timestamp, screenshot_path, activity, activity_extracted_text,
               change_summary, change_prev_extracted_text, change_cur_extracted_text
        FROM activity_entries
        WHERE activity != ''
        ORDER BY unix_time ASC
        LIMIT 10
        """
    )
    rows = cur.fetchall()
    print(f"Loaded {len(rows)} non-empty activity rows.")

    for r in rows:
        print("\nID:", r["id"])
        print("TS:", r["timestamp"])
        print("Screenshot:", r["screenshot_path"])
        act = (r["activity"] or "").strip()
        extracted = (r["activity_extracted_text"] or "").strip()
        chg = (r["change_summary"] or "").strip()
        prev_ex = (r["change_prev_extracted_text"] or "").strip()
        cur_ex = (r["change_cur_extracted_text"] or "").strip()
        print("ACTIVITY:")
        print(act[:800] + ("..." if len(act) > 800 else ""))
        print("EXTRACTED TEXT:")
        print(extracted[:500] + ("..." if len(extracted) > 500 else ""))
        if chg:
            print("CHANGE:")
            print(chg[:500] + ("..." if len(chg) > 500 else ""))
            if prev_ex or cur_ex:
                print("CHANGE EXTRACTED (prev):")
                print(prev_ex[:250] + ("..." if len(prev_ex) > 250 else ""))
                print("CHANGE EXTRACTED (cur):")
                print(cur_ex[:250] + ("..." if len(cur_ex) > 250 else ""))
        else:
            print("CHANGE: <empty>")

    conn.close()


if __name__ == "__main__":
    main()

