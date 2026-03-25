#!/usr/bin/env python3
"""
Send a single screenshot directly to qwen3-vl:8b via Ollama and print the raw response.
Useful to debug whether the model can see/read the Canvas grades page independently
of our analyzer pipeline.
"""

from __future__ import annotations

from pathlib import Path

from ollama import Client


def main() -> None:
    client = Client(host="http://localhost:11434")
    img = Path("screenshots_monitor1_10s/screenshot_20260316_073219.png").resolve()
    print("Image path:", img)

    prompt = (
        "Describe exactly what is on this screen. Name the website or app if you can read it, and "
        "list any clearly readable headings, menu items, or table column headers. "
        "Plain text only."
    )

    resp = client.chat(
        model="qwen3-vl:8b",
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [str(img)],
            }
        ],
        options={"num_predict": 512},
    )
    print("\nRAW QWEN RESPONSE:\n")
    print(resp.message.content)


if __name__ == "__main__":
    main()

