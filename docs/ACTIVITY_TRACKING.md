# Activity Tracking – Qwen VL + SQLite

Screen activity tracking using a **local** Qwen2-VL or Qwen2.5-VL model and SQLite logging.

> Note: This doc includes historical approaches. The **current actively used workflow** is described in the repo `README.md` and centers on `simplified_gpu_two_model_compare.py`.

## Overview

1. **Screenshot** – Captured every N seconds (default 10)
2. **VLM** – Each screenshot (and pairs for change detection) is analyzed locally via Hugging Face `transformers`
3. **Log** – Activity text, optional extracted text, and change summaries go to SQLite

**Change detection**: each frame after the first runs a separate pass comparing the previous and current screenshot.

**Implementation details and versions:** [LOCAL_VLM_QWEN_AND_MOONDREAM.md](LOCAL_VLM_QWEN_AND_MOONDREAM.md) (Qwen-only; filename is legacy).

## Stack

Install:

```bash
pip install -e ".[vlm-native]"
```

| Model family | Example HF id | Class (in `vlm_backends`) |
|--------------|---------------|---------------------------|
| Qwen2-VL | `Qwen/Qwen2-VL-2B-Instruct` | `Qwen2VLForConditionalGeneration` |
| Qwen2.5-VL | `Qwen/Qwen2.5-VL-3B-Instruct` | `Qwen2_5_VLForConditionalGeneration` |

Orchestration: **`ScreenActivityAnalyzer`** (`invoy_sdk/analyzer.py`) — extract → describe, retries, CPU **fast** mode (`--fast-vlm`).

A CUDA GPU is recommended; CPU/MPS work but are slower.

## Usage

```python
from invoy_sdk import ActivityTrackingPipeline

pipeline = ActivityTrackingPipeline(
    interval_seconds=10,
    output_dir="./screenshots",
    db_path="./activity_log.db",
    model="Qwen/Qwen2-VL-2B-Instruct",
    device="auto",
)
pipeline.start()
pipeline.stop()
entries = pipeline.get_entries(limit=20)
```

### Constructor options (pipeline)

- `model`: Hugging Face model id
- `device`: `"auto"` | `"cpu"` | `"cuda"` | `"mps"`
- `fast_vlm`: optional bool override for single-view / shorter generations

## SQLite

See schema in `invoy_sdk/activity_log.py`. Notable columns: `model_name`, `session_id`, `activity`, `change_summary`.

## MLLM calls

- **Activity**: multi-view (or single in fast mode) → extract → describe
- **Change**: extract both sides → decision prompt with both image sets

## Baseline vs strong model

This workflow is still available, but the scripts live under `old_implementations/`:

1. Run `old_implementations/offline_analyze_screenshots.py` with a small model → `activity_entries`
2. Run `old_implementations/teacher_analyze_screenshots.py` with a larger Qwen VL → `teacher_activity_entries`
3. Run `old_implementations/evaluate_teacher_student.py` with `--session-id` and `--teacher-model` as needed

## Hardware

- **Qwen2-VL / 2.5-VL**: GPU recommended for throughput; use `--fast-vlm` on CPU
- Interval is a minimum; actual cadence ≈ interval + inference time
