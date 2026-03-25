# Implementation history (technical)

This doc is the “dense” counterpart to [`PROJECT_HISTORY.md`](../PROJECT_HISTORY.md). It records the main implementation paths we built, where the code lives today, and why some paths are currently deprioritized.

## Current status (what we actually run)

### Current primary workflow: two-model offline compare (GPU-friendly)

- **Entry point**: `simplified_gpu_two_model_compare.py`
- **Inputs**: a directory of PNG screenshots (`--screenshots-dir`)
- **Core dependency**: `invoy_sdk.vlm_backends.Qwen2VLBackend`
- **What it does**:
  - Runs Model A and Model B over the same screenshot sequence
  - Writes per-frame rows into `simplified_activity_entries` in each run DB
  - Writes side-by-side rows into `model_comparison_results` in the eval DB
  - Optionally skips change generation via `--activity-only`

**Why this path is preferred right now**

- It makes model-to-model comparisons first-class.
- It avoids the heavier “extract → describe” orchestration while you’re iterating on *basic usefulness*.
- It’s easier to reason about performance because the loop is explicit and the schema is narrow.

### Data collection (capture-only)

- **Entry point**: `collect_periodic_screenshots.py`
- **Core dependency**: `invoy_sdk.capture.ScreenshotCapture`
- **Role**: collect raw screenshots without coupling to any inference path.

This keeps the workflow modular: collect once, rerun analysis many times.

## Live pipeline (implemented, but currently deprioritized)

- **Entry point**: `run_experiment.py`
- **Core class**: `invoy_sdk.pipeline.ActivityTrackingPipeline`
- **Role**: live capture → VLM inference → SQLite logging in a single loop.

**Why deprioritized**

In practice, inference latency dominates, so the loop doesn’t behave like “every 10s” unless inference is significantly faster than the interval. Right now we’re prioritizing **results/quality** and evaluation workflows, then we’ll return to efficiency.

Related demo script:
- `alt_vision_tests/live_activity_pipeline_demo.py`

## Offline “extract → describe” pipeline (archived)

This was an earlier (still useful) offline analysis path that relied on the SDK’s `ScreenActivityAnalyzer` orchestration and `SQLiteActivityLog` schema.

- `old_implementations/offline_analyze_screenshots.py`
  - Sorted screenshots → `activity_entries` in SQLite
- `old_implementations/teacher_analyze_screenshots.py`
  - Strong/teacher run → `teacher_activity_entries`
- `old_implementations/evaluate_teacher_student.py`
  - Join baseline vs teacher by `screenshot_path` → agreement stats / optional CSV

**Why archived**

You can already do the core comparison work (and faster iteration) using `simplified_gpu_two_model_compare.py`. The archived path is still valuable as a reference and for grounded/extracted-text experiments, but it’s not the path you’re actively iterating on.

## Post-processing / inspection utilities (archived)

These scripts were convenient while iterating on the older schema, but aren’t needed for the current compare workflow:

- `old_implementations/inspect_activity_db.py`: print sample rows from `activity_offline.db`
- `old_implementations/summarize_activity_segments.py`: merge frame labels into contiguous “segments”
- `old_implementations/experiments_analysis.ipynb`: starter notebook for analyzing SQLite outputs

## Smoke tests / model sanity checks

- `alt_vision_tests/qwen2_vl_canvas_test.py`: single-image smoke test (direct backend call)

## Earlier Ollama/Moondream era (archived)

See:
- `old_implementations/README.md`

That README also links to historical Cursor transcripts that motivated the move away from Ollama and toward in-repo HF backends.

