#!/usr/bin/env python3
"""ARCHIVED: used MoondreamAnalyzer(backend=\"ollama\"). See README.md in this folder."""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING)

from invoy_sdk.analyzer import MoondreamAnalyzer

imgs = sorted(Path("screenshots").glob("*.png"))[-5:]
analyzer = MoondreamAnalyzer(
    model="moondream:1.8b-v2-q8_0",
    backend="ollama",
    fallback_model=None,
)

out = []
out.append(f"Analyzing {len(imgs)} screenshots...\n")

for i, img in enumerate(imgs):
    print(f"[{i+1}/{len(imgs)}] {img.name}...", flush=True)
    activity, ms = analyzer.analyze(img)
    status = "TEXT" if activity and not activity.strip().startswith("[") else "BBOX/EMPTY"
    out.append(f"=== {img.name} ({status}, {(ms or 0):.0f}ms) ===")
    out.append((activity or "(none)")[:600])
    out.append("")

result = "\n".join(out)
Path("analyzer_results.txt").write_text(result)
print("\nDone. Results saved to analyzer_results.txt")
