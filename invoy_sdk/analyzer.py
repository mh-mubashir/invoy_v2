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

try:
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover - Pillow optional at runtime
    Image = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Moondream sometimes returns bounding box coords instead of text (known Ollama issue #6365)
_BBOX_PATTERN = re.compile(r"^\s*\[\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*\]\s*$")

# Minimal prompts for retry when main prompt triggers bbox or prompt-echo
FALLBACK_ACTIVITY_PROMPT = (
    "In 2-3 sentences, describe what is clearly visible on the screen and what the person is doing. "
    "Only state things you can actually see. If text is too small to read, say 'text not readable' "
    "instead of guessing. Plain text only."
)

FALLBACK_CHANGE_PROMPT = (
    "In 1-2 sentences, say whether the person is doing the same task or a different task between the two screenshots, "
    "based only on visible evidence. If uncertain, say uncertain and what evidence is missing. Plain text only."
)

# Two-step prompting: extract readable text first, then describe using only that evidence.
EXTRACT_TEXT_PROMPT = """Extract clearly readable text from this desktop screenshot.

Rules:
- Return ONLY lines of text you can actually read on screen (window titles, app names, tab titles, file names, URLs, error messages).
- One item per line.
- If you cannot confidently read any meaningful text, return exactly: NO_READABLE_TEXT
- Do not add explanations or commentary."""

# More OCR-like prompt tuned for small models (Moondream): region-first, verbatim, short.
EXTRACT_TEXT_PROMPT_V2 = """Extract on-screen text from this desktop screenshot as if you are doing OCR.

Return ONLY the text you can actually read, copied verbatim (no rephrasing).

Focus (in order) on these regions:
1) Active window title bar (top)
2) Active tab title(s)
3) URL bar / address bar (if a browser)
4) Left sidebar / file tree (if an editor)
5) Main content headings (document title, page title)
6) Visible error messages

Output format rules:
- ONE short text snippet per line (max 15 lines)
- No sentences, no explanations, no bullets
- If a line is partially readable, include only the readable part (do not guess the rest)
- If nothing meaningful is readable, output exactly: NO_READABLE_TEXT"""

DESCRIBE_FROM_EXTRACTED_TEXT_PROMPT = """You are writing a grounded activity description.

You will be given the readable on-screen text extracted from a screenshot.
Using ONLY that text (and very generic UI cues if needed), describe what the person is doing in 1-3 sentences.

Rules:
- Do not invent app names, files, PR numbers, or URLs not present in the extracted text.
- If the extracted text is NO_READABLE_TEXT, describe only high-level visible activity (e.g. "viewing a browser page", "editing in an IDE") and explicitly say text not readable.
- Plain text only.

Extracted text:
"""

CHANGE_FROM_EXTRACTED_TEXT_PROMPT = """You are comparing two screenshots using only extracted text evidence.

You will be given readable text from image A (previous) and image B (current).
Decide if the person is doing the SAME task or a DIFFERENT task, and explain in 1-2 sentences.

Rules:
- Base your decision only on the provided extracted text.
- If either side is NO_READABLE_TEXT, you may say "uncertain" and explain what is missing.
- Plain text only.

Extracted text (A):
{prev}

Extracted text (B):
{cur}
"""

_PROMPT_ECHO_MARKERS = [
    # Phrases that indicate the model is copying our instruction text or template phrasing
    "the image shows a desktop screen",
    "this image shows a desktop screen",
    "write 3–6 sentences",
    "write 3-6 sentences",
    "the main application(s) visible",
    "what the person appears to be working on",
    "the person appears to be working on",
    "the screenshot provides a clear view",
    "as indicated by the presence of",
    "suggesting that the person might be",
]


def _looks_like_prompt_echo(text: str) -> bool:
    """
    Heuristic: detect when the model parrots prompt phrasing/examples instead of describing the screenshot.
    """
    if not text:
        return False
    t = " ".join(text.strip().lower().split())
    hit_count = sum(1 for m in _PROMPT_ECHO_MARKERS if m in t)
    # If it contains multiple instruction/example markers, it's likely parroting.
    if hit_count >= 2:
        return True
    # If it starts with generic template-y phrasing, treat as echo-y.
    if t.startswith("the image shows") or t.startswith("this image shows"):
        return True
    return False


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

# Legacy single-shot prompts (kept for fallback/debugging).
ACTIVITY_PROMPT = """Describe what the person is doing on this computer screen. 2-4 sentences. Plain text only."""
CHANGE_PROMPT = """Same task or different task between the screenshots? 1-3 sentences. Plain text only."""


def _clean_extracted_lines(text: str) -> str:
    """
    Normalize extracted text response into a newline-separated list or NO_READABLE_TEXT.
    """
    if not text:
        return "NO_READABLE_TEXT"
    t = text.strip()
    if not t:
        return "NO_READABLE_TEXT"
    if "NO_READABLE_TEXT" in t:
        return "NO_READABLE_TEXT"
    # Split into non-empty lines, strip bullets/quotes.
    lines: list[str] = []
    for raw in t.splitlines():
        line = raw.strip().strip("-").strip("*").strip().strip('"').strip("'").strip()
        if not line:
            continue
        # Drop obvious instruction echoes.
        low = line.lower()
        if "one item per line" in low or "do not add explanations" in low:
            continue
        lines.append(line)
    if not lines:
        return "NO_READABLE_TEXT"
    # Deduplicate while preserving order.
    seen = set()
    uniq: list[str] = []
    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(line)
    # Keep it short; extraction is meant to be small evidence, not a blob.
    return "\n".join(uniq[:20])


def _make_extraction_views(path: Path) -> list[str]:
    """
    Generate one or more derived images aimed at improving text readability for OCR-style extraction.
    Returns a list of file paths (strings) to use as `images` for extraction prompts.
    """
    views: list[str] = [str(path.absolute())]
    if Image is None:
        return views
    try:
        img = Image.open(path)
    except Exception:
        return views

    base_dir = path.parent / ".invoy_cache"
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Full-image upscale (2x) with high-quality resampling.
        upscaled = img.resize((img.width * 2, img.height * 2), resample=Image.LANCZOS)
        up_path = base_dir / f"{path.stem}_up2x.png"
        upscaled.save(up_path)
        views.append(str(up_path))

        # Top-bar crop (roughly 15% height), then upscale 3x for tiny title text.
        top_h = max(int(img.height * 0.15), 40)
        top_crop = img.crop((0, 0, img.width, top_h))
        top_up = top_crop.resize((img.width * 3, top_h * 3), resample=Image.LANCZOS)
        # Optional slight sharpen to help text edges.
        if ImageFilter is not None:
            top_up = top_up.filter(ImageFilter.SHARPEN)
        top_path = base_dir / f"{path.stem}_topbar_up3x.png"
        top_up.save(top_path)
        views.append(str(top_path))
    except Exception:
        # If any preprocessing fails, just fall back to original view.
        pass

    return views


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
        extractor_model: Optional[str] = None,
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
        # Optional separate model just for OCR-style text extraction (e.g. llava)
        self.extractor_model = extractor_model
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

    def _chat_once(
        self,
        *,
        prompt: str,
        image_paths: list[str],
        num_predict: int,
        use_extractor_model: bool = False,
    ) -> tuple[Optional[str], Optional[float]]:
        client = self._get_client()
        model_name = self.extractor_model if use_extractor_model and self.extractor_model else self.model
        t0 = time.perf_counter()
        response = client.chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": image_paths,
                }
            ],
            options={"num_predict": num_predict},
        )
        inference_ms = (time.perf_counter() - t0) * 1000
        content = response.message.content
        if content and isinstance(content, str):
            return content, inference_ms
        return None, inference_ms

    def analyze(self, image_path: str | Path) -> tuple[Optional[str], Optional[float]]:
        """Backward-compatible wrapper: returns (activity_text, inference_ms)."""
        activity, _extracted, ms = self.analyze_with_extracted(image_path)
        return activity, ms

    def analyze_with_extracted(
        self, image_path: str | Path
    ) -> tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Analyze a screenshot and return:
        - activity description (plain text),
        - extracted readable on-screen text (newline-separated or NO_READABLE_TEXT),
        - total inference time (ms) across subcalls.
        """
        path = Path(image_path)
        if not path.exists():
            logger.error("Image not found: %s", path)
            return None, None, None

        try:
            # Build multiple views of the same screenshot for better OCR.
            views = _make_extraction_views(path)
            total_ms = 0.0

            # Step A: extract readable text.
            extracted_raw, ms_a = self._chat_once(
                prompt=EXTRACT_TEXT_PROMPT_V2,
                image_paths=views,
                num_predict=256,
                use_extractor_model=True,
            )
            total_ms += ms_a or 0.0
            extracted_text = _clean_extracted_lines(_extract_text_from_response(extracted_raw or "") or "")

            # Retry extraction once if we got nothing.
            if extracted_text == "NO_READABLE_TEXT":
                # Fallback to simpler prompt on original image only.
                abs_img = str(path.absolute())
                extracted_raw2, ms_a2 = self._chat_once(
                    prompt=EXTRACT_TEXT_PROMPT,
                    image_paths=[abs_img],
                    num_predict=256,
                    use_extractor_model=True,
                )
                total_ms += ms_a2 or 0.0
                extracted_text2 = _clean_extracted_lines(
                    _extract_text_from_response(extracted_raw2 or "") or ""
                )
                if extracted_text2 != "NO_READABLE_TEXT":
                    extracted_text = extracted_text2

            # Step B: describe using extracted text only.
            describe_prompt = DESCRIBE_FROM_EXTRACTED_TEXT_PROMPT + extracted_text
            described_raw, ms_b = self._chat_once(
                prompt=describe_prompt,
                image_paths=views,
                num_predict=256,
            )
            total_ms += ms_b or 0.0

            described = _extract_text_from_response(described_raw or "")
            if described is not None and not _looks_like_prompt_echo(described):
                return described, extracted_text, total_ms

            # Retry: fallback simple prompt.
            logger.warning("Activity output weak/echo-y; retrying with fallback prompt")
            retry_raw, ms_c = self._chat_once(
                prompt=FALLBACK_ACTIVITY_PROMPT,
                image_paths=views,
                num_predict=256,
            )
            total_ms += ms_c or 0.0
            retry_text = _extract_text_from_response(retry_raw or "")
            return retry_text, extracted_text, total_ms
        except Exception as e:
            if self.fallback_model and self.model != self.fallback_model:
                if "memory" in str(e).lower() or "500" in str(e):
                    logger.warning("Model %s failed (likely OOM), trying fallback %s", self.model, self.fallback_model)
                    self.model, orig = self.fallback_model, self.model
                    result, extracted, ms = self.analyze_with_extracted(image_path)
                    self.model = orig
                    return result, extracted, ms
            logger.exception("MLLM analysis failed: %s", e)
            return None, None, None

    def analyze_change(
        self,
        current_path: str | Path,
        previous_path: str | Path,
    ) -> tuple[Optional[str], Optional[float]]:
        """Backward-compatible wrapper: returns (change_text, inference_ms)."""
        change, _prev_extracted, _cur_extracted, ms = self.analyze_change_with_extracted(
            current_path=current_path, previous_path=previous_path
        )
        return change, ms

    def analyze_change_with_extracted(
        self,
        current_path: str | Path,
        previous_path: str | Path,
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[float]]:
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
            return None, None, None, None
        if not previous.exists():
            logger.error("Previous image not found: %s", previous)
            return None, None, None, None

        try:
            prev_views = _make_extraction_views(previous)
            cur_views = _make_extraction_views(current)
            total_ms = 0.0

            # Step A: extract text from each screenshot separately.
            prev_raw, ms_a = self._chat_once(
                prompt=EXTRACT_TEXT_PROMPT_V2,
                image_paths=prev_views,
                num_predict=256,
                use_extractor_model=True,
            )
            total_ms += ms_a or 0.0
            cur_raw, ms_b = self._chat_once(
                prompt=EXTRACT_TEXT_PROMPT_V2,
                image_paths=cur_views,
                num_predict=256,
                use_extractor_model=True,
            )
            total_ms += ms_b or 0.0

            prev_text = _clean_extracted_lines(_extract_text_from_response(prev_raw or "") or "")
            cur_text = _clean_extracted_lines(_extract_text_from_response(cur_raw or "") or "")

            # Retry extraction once per side if missing.
            if prev_text == "NO_READABLE_TEXT":
                prev_raw2, ms_a2 = self._chat_once(
                    prompt=EXTRACT_TEXT_PROMPT,
                    image_paths=[str(previous.absolute())],
                    num_predict=256,
                    use_extractor_model=True,
                )
                total_ms += ms_a2 or 0.0
                prev_text2 = _clean_extracted_lines(
                    _extract_text_from_response(prev_raw2 or "") or ""
                )
                if prev_text2 != "NO_READABLE_TEXT":
                    prev_text = prev_text2
            if cur_text == "NO_READABLE_TEXT":
                cur_raw2, ms_b2 = self._chat_once(
                    prompt=EXTRACT_TEXT_PROMPT,
                    image_paths=[str(current.absolute())],
                    num_predict=256,
                    use_extractor_model=True,
                )
                total_ms += ms_b2 or 0.0
                cur_text2 = _clean_extracted_lines(
                    _extract_text_from_response(cur_raw2 or "") or ""
                )
                if cur_text2 != "NO_READABLE_TEXT":
                    cur_text = cur_text2

            # Step B: decide same/different using only extracted text.
            decide_prompt = CHANGE_FROM_EXTRACTED_TEXT_PROMPT.format(prev=prev_text, cur=cur_text)
            decision_raw, ms_c = self._chat_once(
                prompt=decide_prompt,
                image_paths=prev_views + cur_views,
                num_predict=256,
            )
            total_ms += ms_c or 0.0

            decision = _extract_text_from_response(decision_raw or "")
            if decision is not None and not _looks_like_prompt_echo(decision):
                return decision, prev_text, cur_text, total_ms

            # Retry fallback: simple question on both images.
            logger.warning("Change output weak/echo-y; retrying with fallback prompt")
            retry_raw, ms_d = self._chat_once(
                prompt=FALLBACK_CHANGE_PROMPT,
                image_paths=prev_views + cur_views,
                num_predict=256,
            )
            total_ms += ms_d or 0.0
            retry_text = _extract_text_from_response(retry_raw or "")
            return retry_text, prev_text, cur_text, total_ms
        except Exception as e:
            if self.fallback_model and self.model != self.fallback_model:
                if "memory" in str(e).lower() or "500" in str(e):
                    logger.warning("Model %s failed (likely OOM), trying fallback %s", self.model, self.fallback_model)
                    self.model, orig = self.fallback_model, self.model
                    result, prev_text, cur_text, ms = self.analyze_change_with_extracted(
                        current_path=current_path, previous_path=previous_path
                    )
                    self.model = orig
                    return result, prev_text, cur_text, ms
            logger.exception("MLLM change analysis failed: %s", e)
            return None, None, None, None
