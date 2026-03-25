# Local Qwen VL (Qwen2-VL and Qwen2.5-VL)

> Note: This document describes the **current** Invoy stack only (Hugging Face Qwen vision models). Moondream and Ollama are not part of the supported path; see `old_implementations/` for archived scripts.

## Install

```bash
pip install -e ".[vlm-native]"
```

Requires `transformers>=4.51.0` (for Qwen2.5-VL), PyTorch, `qwen-vl-utils`, `accelerate`, Pillow.

## Code map

| Layer | File | Role |
|-------|------|------|
| Inference | [`invoy_sdk/vlm_backends.py`](../invoy_sdk/vlm_backends.py) | `Qwen2VLBackend`: `AutoProcessor`, `Qwen2VLForConditionalGeneration` or `Qwen2_5_VLForConditionalGeneration`, `apply_chat_template`, `process_vision_info`, `generate` |
| Orchestration | [`invoy_sdk/analyzer.py`](../invoy_sdk/analyzer.py) | `ScreenActivityAnalyzer`: prompts, extract → describe, fast CPU path |
| Live loop | [`invoy_sdk/pipeline.py`](../invoy_sdk/pipeline.py) | `ActivityTrackingPipeline` |
| Batch CLI (current) | [`simplified_gpu_two_model_compare.py`](../simplified_gpu_two_model_compare.py) | Two models over a screenshot dir → per-run DBs + comparison DB |
| Batch CLI (archived) | [`old_implementations/offline_analyze_screenshots.py`](../old_implementations/offline_analyze_screenshots.py) | Sorted PNGs → SQLite `activity_entries` |
| Strong run (archived) | [`old_implementations/teacher_analyze_screenshots.py`](../old_implementations/teacher_analyze_screenshots.py) | Same pipeline, larger model → `teacher_activity_entries` |
| Compare (archived) | [`old_implementations/evaluate_teacher_student.py`](../old_implementations/evaluate_teacher_student.py) | Join baseline vs strong rows |
| Smoke test | [`alt_vision_tests/qwen2_vl_canvas_test.py`](../alt_vision_tests/qwen2_vl_canvas_test.py) | Single image; calls `Qwen2VLBackend` directly |

## Model IDs

- **Small (baseline)**: `Qwen/Qwen2-VL-2B-Instruct`
- **Strong (< 7B typical)**: `Qwen/Qwen2.5-VL-3B-Instruct`

Family is detected from the model id string (`2.5-VL` / `qwen2.5`) to pick the correct HF model class.

## CPU fast mode

With `device=cpu` (or `auto` resolving to CPU), `ScreenActivityAnalyzer` defaults to **fast** mode: one full-frame view and shorter token budgets. Use `--full-vlm-views` on CLIs for multi-view extraction (slower, can help OCR).

## Troubleshooting

- **`KeyError` / config errors for Qwen2.5-VL**: upgrade transformers — `pip install -U 'transformers>=4.51.0'`
- **OOM**: use a smaller model, GPU with more memory, or `--fast-vlm`
