#!/usr/bin/env python3
"""
Send the Canvas grades screenshot directly to LLaVA via Ollama and print the raw response.
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
        model="llava",
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [str(img)],
            }
        ],
        options={"num_predict": 512},
    )
    print("\nRAW LLAVA RESPONSE:\n")
    print(resp.message.content)


if __name__ == "__main__":
    main()

