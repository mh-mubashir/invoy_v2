#!/usr/bin/env python
"""
Test Moondream2 directly on the Canvas grades screenshot (outside Ollama).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from moondream import Moondream, detect_device


def run_moondream(image_path: Path, device: str = "auto") -> None:
    if device == "auto":
        device = detect_device()

    print(f"Using device: {device}")
    print(f"Image path: {image_path}")

    model_id = "vikhyatk/moondream2"
    model = Moondream.from_pretrained(model_id, device=device)

    image = Image.open(image_path).convert("RGB")

    prompt = (
        "You are an assistant that reads screenshots of a learning management system.\n"
        "Describe exactly what is on this screen. Name the website or app if you can read it, "
        "and list any clearly readable headings, menu items, or table column headers. "
        "Plain text only."
    )

    # Use Moondream's high-level helper API.
    encoded_image = model.encode_image(image)
    answer = model.answer_question(encoded_image, prompt)

    print("\n===== Moondream2 Output =====\n")
    print(answer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        type=str,
        default="screenshots_monitor1_10s/screenshot_20260316_073219.png",
        help="Path to the Canvas grades screenshot.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device to use: auto, cpu, cuda, or mps.",
    )
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    run_moondream(image_path, device=args.device)


if __name__ == "__main__":
    main()

