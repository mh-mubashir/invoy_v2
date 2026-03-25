"""
Hugging Face Qwen2-VL and Qwen2.5-VL backends for vision-language inference.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BACKEND_QWEN2VL = "qwen2vl"


def _is_qwen25_model_id(model_id: str) -> bool:
    """True if ``model_id`` refers to the Qwen2.5-VL family (uses Qwen2_5_VLForConditionalGeneration)."""
    m = model_id.lower().replace("_", ".")
    return "qwen2.5" in m or "2.5-vl" in m


class VLMBackend(ABC):
    """Minimal interface used by ScreenActivityAnalyzer."""

    @property
    @abstractmethod
    def log_model_name(self) -> str:
        """String stored in SQLite / logs for this backend."""
        ...

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        image_paths: list[str],
        max_new_tokens: int,
        use_extractor_model: bool = False,
    ) -> tuple[Optional[str], float]:
        """
        Run one vision+text generation.

        Returns:
            (decoded_text_or_none, wall_time_ms)
        """
        ...


class Qwen2VLBackend(VLMBackend):
    """
    Hugging Face Qwen2-VL and Qwen2.5-VL (local).

    Same flow as the Qwen reference scripts: ``AutoProcessor``, vision model class, ``apply_chat_template``,
    ``process_vision_info``, ``processor(...)`` → device, ``generate``, decode new tokens only.
    """

    def __init__(
        self,
        model_id: str = "Qwen/Qwen2-VL-2B-Instruct",
        device: str = "auto",
    ):
        self.model_id = model_id
        self.device_pref = device
        self._processor = None
        self._model = None
        self._resolved_device: Optional[str] = None
        self._torch = None  # type: ignore[assignment]
        self._process_vision_info = None  # type: ignore[assignment]

    @property
    def log_model_name(self) -> str:
        return f"qwen_vl:{self.model_id}"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoProcessor
            from qwen_vl_utils import process_vision_info
        except ImportError as e:
            raise ImportError(
                "Qwen VL backend requires: pip install 'invoy-sdk[vlm-native]' "
                "(or transformers, torch, qwen-vl-utils, accelerate, pillow)."
            ) from e

        if _is_qwen25_model_id(self.model_id):
            try:
                from transformers import Qwen2_5_VLForConditionalGeneration as ModelClass
            except ImportError as e:  # pragma: no cover
                raise ImportError(
                    "Qwen2.5-VL needs a newer transformers. Try: pip install -U 'transformers>=4.51.0'"
                ) from e
        else:
            from transformers import Qwen2VLForConditionalGeneration as ModelClass

        device = self.device_pref
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self._resolved_device = device

        dtype = torch.float16 if device != "cpu" else torch.float32
        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = ModelClass.from_pretrained(
            self.model_id,
            torch_dtype=dtype,
            device_map="auto" if device != "cpu" else None,
        )
        if device == "cpu":
            self._model = self._model.to(device)
        self._torch = torch
        self._process_vision_info = process_vision_info
        logger.info("Qwen VL loaded: %s on %s", self.model_id, device)

    def generate(
        self,
        *,
        prompt: str,
        image_paths: list[str],
        max_new_tokens: int,
        use_extractor_model: bool = False,
    ) -> tuple[Optional[str], float]:
        _ = use_extractor_model
        self._ensure_loaded()
        assert self._processor is not None and self._model is not None

        torch = self._torch
        process_vision_info = self._process_vision_info

        content: list[dict] = []
        for p in image_paths:
            path = Path(p)
            if not path.exists():
                logger.warning("Qwen VL: missing image path, skipping: %s", p)
                continue
            content.append({"type": "image", "image": str(path.resolve())})
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]

        text = self._processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        if any(c.get("type") == "image" for c in content):
            images, videos = process_vision_info(messages)
            inputs = self._processor(
                text=[text],
                images=images,
                videos=videos,
                padding=True,
                return_tensors="pt",
            ).to(self._model.device)
        else:
            # Text-only chat (used for change-from-activity-text mode).
            inputs = self._processor(
                text=[text],
                padding=True,
                return_tensors="pt",
            ).to(self._model.device)

        # For accurate wall-time measurements on CUDA, synchronize before/after generate().
        # Without this, queued async GPU work can make timings look inconsistent.
        device_type = getattr(getattr(self._model, "device", None), "type", None)
        if device_type == "cuda" and torch.cuda.is_available():
            torch.cuda.synchronize()

        t0 = time.perf_counter()
        with torch.no_grad():
            # Force greedy decoding for stability. Some configs default to sampling and can
            # trigger CUDA asserts (e.g., if probabilities become invalid).
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        if device_type == "cuda" and torch.cuda.is_available():
            torch.cuda.synchronize()
        inference_ms = (time.perf_counter() - t0) * 1000

        prompt_len = inputs["input_ids"].shape[1]
        output_ids = generated_ids[:, prompt_len:]
        output_text = self._processor.batch_decode(output_ids, skip_special_tokens=True)[0]
        return (output_text.strip() or None), inference_ms
