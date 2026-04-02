## Changes Made
- `invoy_sdk/vlm_backends.py:24` — Added `_is_internvl2_model_id(model_id: str) -> bool` helper; returns True when 'internvl' appears case-insensitively in model_id (AC-1)
- `invoy_sdk/vlm_backends.py:194` — Added module-level `IMAGENET_MEAN` and `IMAGENET_STD` constants used by InternVL2 image preprocessing
- `invoy_sdk/vlm_backends.py:198` — Added `InternVL2Backend(VLMBackend)` class: `log_model_name` returns `f'internvl2:{self.model_id}'`, `_ensure_loaded()` uses AutoModel + AutoTokenizer with trust_remote_code=True and torch.bfloat16, torchvision transform (448x448 BICUBIC, ToTensor, ImageNet Normalize), `generate()` wraps inference in try/except returning `(None, 0.0)` on any error, uses `model.chat()` which returns a plain string (no decode step) (AC-2, AC-6)
- `invoy_app/settings/config.py:19` — Added 'InternVL2 2B' -> 'OpenGVLab/InternVL2-2B' and 'InternVL2 4B' -> 'OpenGVLab/InternVL2-4B' to AVAILABLE_MODELS dict, after the two existing Qwen entries (AC-3)
- `invoy_app/core/recorder.py:33` — Added `InternVL2Backend`, `VLMBackend`, and `_is_internvl2_model_id` to the try/except SDK import guard alongside the existing `Qwen2VLBackend` import (AC-4)
- `invoy_app/core/recorder.py:128` — Widened `self._backend` type annotation from `Optional[Qwen2VLBackend]` to `Optional[VLMBackend]` (AC-4)
- `invoy_app/core/recorder.py:240` — Added dispatch in `_load_model_then_capture`: instantiates `InternVL2Backend` when `_is_internvl2_model_id(self._config.model_id)` is True, `Qwen2VLBackend` otherwise (AC-4)
- `invoy_app/app.py:32` — Added `FONTS` to the theme import (required by D-1 fix)
- `invoy_app/app.py:381` — Added InternVL2-4B check before InternVL2-2B check, both before the existing '3B'/'2B'/'7B' substring checks in `_short_model_label()` (AC-5)
- `invoy_app/app.py:295` — Replaced raw `font=("Segoe UI", 12)` with `font=FONTS["status"]` on the error label in `_on_error()` (D-1 from design_review.json)

## Design Decisions
- `FONTS["status"]` is `("Segoe UI", 12)` — an exact token match for the raw tuple that was there. This is the correct token for the error label since it sits alongside the status bar text and is the same visual weight.
- InternVL2's `generate()` method swallows all exceptions with `print()` and returns `(None, 0.0)` as specified; this differs from Qwen2VLBackend which uses assert and lets exceptions bubble. The difference is intentional per the spec risk flags.
- The `_is_internvl2_model_id` check in `_load_model_then_capture` uses the same guard function as the type dispatch in the backend, ensuring a single source of truth for the routing logic.
- device_map="auto" is used for GPU (cuda/mps) loading; `.to(device)` is used for CPU only, mirroring the Qwen2VLBackend pattern exactly.
- InternVL2 4B check comes before 2B check in `_short_model_label()` because "InternVL2-2B" is a substring of neither "InternVL2-4B" — but if a hypothetical "InternVL2-42B" existed, ordering matters. Spec mandates 4B first explicitly.

## Thread Safety Notes
- `_load_model_then_capture` runs on a daemon thread. The dispatch logic added there (the `if _is_internvl2_model_id` branch) only sets `self._backend` — a plain Python attribute assignment — and then calls `_ensure_loaded()`. No widgets are touched. This is identical in thread-safety terms to the existing Qwen2VLBackend instantiation that was already there.
- `InternVL2Backend.generate()` runs on the capture thread (called from `_on_capture`). It only touches torch tensors and the model — no widgets. This is safe.
- The `_on_error()` fix in `app.py` (D-1) runs on the Tk main thread (it is always called via `root.after(0, ...)` from `_ui_error()`). No thread-safety concern.

## Known Limitations
- InternVL2Backend does not implement a resize-before-inference step (like `_resize_for_inference` used for Qwen). The torchvision transform always resizes to 448x448, so token count is inherently bounded — but the original full-resolution screenshot is still opened via PIL before the transform, which may consume more memory for 4K screenshots.
- The change inference path in recorder.py passes `image_paths=[]` for InternVL2 change prompts (text-only), which means `pixel_values` will be None. The `model.chat()` API accepts None for pixel_values (text-only mode), so this is correct but relies on InternVL2's documented API behavior.
- No unit tests were added or modified — test files were not listed in files_to_change and spec did not call for test changes.

## Status
done
