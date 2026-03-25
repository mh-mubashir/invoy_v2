#!/usr/bin/env python
"""
Test Qwen2-VL / Qwen2.5-VL on a screenshot using the same backend as the main SDK
(invoy_sdk.vlm_backends.Qwen2VLBackend).

Default image and prompt match the Canvas grades smoke test.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without pip install -e . when repo root is on PYTHONPATH
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from invoy_sdk.vlm_backends import Qwen2VLBackend

CANVAS_GRADES_PROMPT = (
    "You are an assistant that reads screenshots of a learning management system.\n"
    "Describe exactly what is on this screen. Name the website or app if you can read it, "
    "and list any clearly readable headings, menu items, or table column headers. "
    "Plain text only."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen VL canvas smoke test (SDK backend).")
    parser.add_argument(
        "--image",
        type=str,
        default="screenshots_monitor1_10s/screenshot_20260316_073219.png",
        help="Path to a PNG screenshot.",
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
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    backend = Qwen2VLBackend(model_id=args.model, device=args.device)
    text, ms = backend.generate(
        prompt=CANVAS_GRADES_PROMPT,
        image_paths=[str(image_path)],
        max_new_tokens=512,
    )
    print(f"Model: {args.model}")
    print(f"Image: {image_path}")
    print(f"Inference: {ms:.0f} ms" if ms is not None else "")
    print("\n===== Qwen VL Output =====\n")
    print(text or "(empty)")


if __name__ == "__main__":
    main()
