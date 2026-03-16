"""
Screen activity analyzer using a local multimodal LLM via Ollama.

Analyzes screenshots to describe on-screen activity. Runs locally.
Default model: llava (better quality). Alternative: llava-phi3 (lighter, CPU-friendly).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Moondream sometimes returns bounding box coords instead of text (known Ollama issue #6365)
_BBOX_PATTERN = re.compile(r"^\s*\[\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*\]\s*$")

# Minimal prompts for retry when main prompt still triggers bbox
FALLBACK_ACTIVITY_PROMPT = """Describe this image. What is the user doing? Plain text only."""

FALLBACK_CHANGE_PROMPT = """Same work or different? Answer in 1-2 sentences."""


def _extract_text_from_response(content: str) -> Optional[str]:
    """
    Return valid activity text, or None if response is bbox-only.
    When bbox-only, we cannot extract text (there is none); caller should retry with fallback prompt.
    """
    if not content or not content.strip():
        return None
    stripped = content.strip()
    if _BBOX_PATTERN.match(stripped):
        return None
    return stripped

# Prompt for activity description.
ACTIVITY_PROMPT = """Analyze this desktop screenshot. Write a dense, information-packed description of the work being done. You must write at least 3-5 sentences—pack as much observable detail as possible.

Include:
- **Primary app and window**: Name the focused application, tab, or file (e.g., "Cursor IDE with capture.py", "Chrome on docs.ollama.com").
- **Visible content**: Quote or paraphrase any readable text: filenames, URLs, code, document titles, error messages, search queries.
- **Specific task**: What is the user doing right now? Be concrete (e.g., "editing the _take_screenshot function", "reading the Ollama API section", "viewing a terminal with pip install output").
- **Context**: Project, topic, or domain if inferable from visible content.

Avoid generic phrases like "the user is working on" or "multiple applications". Instead, name what you see. Every sentence should add new, specific information. Do not repeat yourself."""

# Prompt for change detection.
CHANGE_PROMPT = """Compare these two desktop screenshots. The first image is the previous state, the second is the current state. Write a dense, information-packed summary of whether the work is the same or different. Pack as much observable detail as possible into 2-4 sentences.

Include:
- **Same or different**: State clearly whether the work in the second image is the SAME as the first, or DIFFERENT.
- **What changed (if different)**: Name the specific change—e.g., switched app, different file, new tab, scroll position, new content, different task.
- **What stayed the same (if same)**: Briefly note what remained unchanged—e.g., same app, same file, minor edit or scroll.

Avoid generic phrases like "the user switched" or "things changed". Instead, name what you see. Every sentence should add new, specific information. Do not repeat yourself."""


class MoondreamAnalyzer:
    """
    Analyzes screenshots using a vision-language model via Ollama.

    Recommended models (run `ollama pull <model>` first):
        - llava: Better quality, ~4GB (default)
        - llava-phi3: Lighter, CPU-friendly, ~2.5GB
        - moondream: Smallest, fastest, ~1.7GB (lower quality)
    """

    def __init__(
        self,
        model: str = "llava",
        host: str = "http://localhost:11434",
        fallback_model: Optional[str] = "moondream",
    ):
        """
        Initialize the analyzer.

        Args:
            model: Ollama model name (default: llava).
            host: Ollama API host URL.
            fallback_model: If model fails (e.g. OOM), try this. None to disable.
        """
        self.model = model
        self.fallback_model = fallback_model
        self.host = host
        self._client = None

    def _get_client(self):
        """Lazy-load ollama client to avoid import errors if not installed."""
        if self._client is None:
            try:
                from ollama import Client

                self._client = Client(host=self.host)
            except ImportError:
                raise ImportError(
                    "ollama package required. Install with: pip install ollama"
                )
        return self._client

    def analyze(self, image_path: str | Path) -> tuple[Optional[str], Optional[float]]:
        """
        Analyze a screenshot and return activity description + inference time.

        Args:
            image_path: Path to the screenshot PNG file.

        Returns:
            Tuple of (activity_description, inference_ms). Either may be None on failure.
        """
        path = Path(image_path)
        if not path.exists():
            logger.error("Image not found: %s", path)
            return None, None

        try:
            client = self._get_client()
            t0 = time.perf_counter()
            response = client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": ACTIVITY_PROMPT,
                        "images": [str(path.absolute())],
                    }
                ],
                options={"num_predict": 512},  # Moondream defaults to 256; 512 worked better than 1024
            )
            inference_ms = (time.perf_counter() - t0) * 1000
            content = response.message.content
            if content and isinstance(content, str):
                text = _extract_text_from_response(content)
                if text is not None:
                    return text, inference_ms
                # Bbox-only: retry with simpler prompt that elicits text
                logger.warning("Model returned bbox instead of text, retrying with fallback prompt")
                t1 = time.perf_counter()
                retry_resp = client.chat(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": FALLBACK_ACTIVITY_PROMPT, "images": [str(path.absolute())]},
                    ],
                    options={"num_predict": 512},
                )
                inference_ms += (time.perf_counter() - t1) * 1000
                retry_content = retry_resp.message.content
                if retry_content and isinstance(retry_content, str):
                    retry_text = _extract_text_from_response(retry_content)
                    if retry_text is not None:
                        return retry_text, inference_ms
            return None, inference_ms
        except Exception as e:
            if self.fallback_model and self.model != self.fallback_model:
                if "memory" in str(e).lower() or "500" in str(e):
                    logger.warning("Model %s failed (likely OOM), trying fallback %s", self.model, self.fallback_model)
                    self.model, orig = self.fallback_model, self.model
                    result, ms = self.analyze(image_path)
                    self.model = orig
                    return result, ms
            logger.exception("MLLM analysis failed: %s", e)
            return None, None

    def analyze_change(
        self,
        current_path: str | Path,
        previous_path: str | Path,
    ) -> tuple[Optional[str], Optional[float]]:
        """
        Compare two consecutive screenshots and describe what changed.
        Separate MLLM call from activity detection.

        Args:
            current_path: Path to the current screenshot.
            previous_path: Path to the immediately preceding screenshot.

        Returns:
            Tuple of (change_summary, inference_ms). Either may be None on failure.
        """
        current = Path(current_path)
        previous = Path(previous_path)
        if not current.exists():
            logger.error("Current image not found: %s", current)
            return None, None
        if not previous.exists():
            logger.error("Previous image not found: %s", previous)
            return None, None

        try:
            client = self._get_client()
            t0 = time.perf_counter()
            response = client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": CHANGE_PROMPT,
                        "images": [
                            str(previous.absolute()),
                            str(current.absolute()),
                        ],
                    }
                ],
                options={"num_predict": 512},  # Allow 2-4 sentences for change summary
            )
            inference_ms = (time.perf_counter() - t0) * 1000
            content = response.message.content
            if content and isinstance(content, str):
                text = _extract_text_from_response(content)
                if text is not None:
                    return text, inference_ms
                # Bbox-only: retry with simpler prompt
                logger.warning("Model returned bbox instead of text for change detection, retrying with fallback prompt")
                t1 = time.perf_counter()
                retry_resp = client.chat(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": FALLBACK_CHANGE_PROMPT,
                            "images": [str(previous.absolute()), str(current.absolute())],
                        },
                    ],
                    options={"num_predict": 512},
                )
                inference_ms += (time.perf_counter() - t1) * 1000
                retry_content = retry_resp.message.content
                if retry_content and isinstance(retry_content, str):
                    retry_text = _extract_text_from_response(retry_content)
                    if retry_text is not None:
                        return retry_text, inference_ms
            return None, inference_ms
        except Exception as e:
            if self.fallback_model and self.model != self.fallback_model:
                if "memory" in str(e).lower() or "500" in str(e):
                    logger.warning("Model %s failed (likely OOM), trying fallback %s", self.model, self.fallback_model)
                    self.model, orig = self.fallback_model, self.model
                    result, ms = self.analyze_change(current_path, previous_path)
                    self.model = orig
                    return result, ms
            logger.exception("MLLM change analysis failed: %s", e)
            return None, None
