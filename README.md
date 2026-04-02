# Invoy SDK

SDK for periodic screenshot capture (Linux-first) and **local screen activity analysis** with Hugging Face **Qwen2-VL** and **Qwen2.5-VL**.

## What is actively used right now (current workflow)

We are currently prioritizing **results/quality first** (prompting + model comparison) over “live/real-time” efficiency.

1) **Collect screenshots** (capture-only):

```bash
python collect_periodic_screenshots.py --monitor 1 --interval 10 --output-dir ./my_shots
```

2) **Run two models + persist a side-by-side comparison** (this is the main workflow):

```bash
python simplified_gpu_two_model_compare.py --screenshots-dir ./my_shots
```

That script writes:
- Per-model per-frame rows into `simplified_activity_entries` (in each run DB)
- Side-by-side joins into `model_comparison_results` (in the eval DB)

## Evaluation pipeline (current)

Use this when you already have:
- `qwen2vl2b_gpu_activity_change.db`
- `qwen25vl3b_gpu_activity_change.db`

### Script responsibilities

1) `tools/inspect_simplified_db.py`
- Purpose: DB sanity check before evaluation
- Confirms: tables, columns, run labels, and sample rows

2) `evaluate_simplified_compare.py`
- Purpose: rebuild analytic evaluation outputs without rerunning models
- Reads `simplified_activity_entries` from both model DBs
- Rebuilds `model_compare_eval_gpu.db` tables:
  - `model_comparison_results` (legacy compatibility)
  - `frame_eval` (analytic metrics)
- Exports:
  - `eval_reports/eval_frames.csv`
  - `eval_reports/disagreements_top50.csv`

3) `plot_compare_eval.py`
- Purpose: create publication-style visual summaries
- Reads `frame_eval` from `model_compare_eval_gpu.db` (or CSV)
- Writes:
  - `eval_reports/plots/activity_cosine_hist.png`
  - `eval_reports/plots/change_cosine_hist.png` (if `change_cosine` is present)
  - `eval_reports/plots/drift_timeseries.png`
  - `eval_reports/plots/top_disagreements.csv`

### Recommended execution order

```bash
python tools/inspect_simplified_db.py
python evaluate_simplified_compare.py --export-dir eval_reports
python plot_compare_eval.py --eval-db model_compare_eval_gpu.db --out-dir eval_reports/plots
```

See [eval_reports/README.md](eval_reports/README.md) for detailed artifact interpretation.

## Smoke tests / demos

Smoke test (same backend as the SDK):

```bash
python alt_vision_tests/qwen2_vl_canvas_test.py --image path/to/screenshot.png --model Qwen/Qwen2-VL-2B-Instruct
```

Runnable demos (kept as references):
- `alt_vision_tests/screenshot_capture_10s_demo.py`
- `alt_vision_tests/live_activity_pipeline_demo.py`

## Live pipeline (kept, but not actively used)

`run_experiment.py` runs the **live** `ActivityTrackingPipeline` (capture → Qwen VL → SQLite).

We originally started by focusing on **efficiency** and a live loop. In practice, **inference time dominates** the cadence, so we’re not actively using the live pipeline right now. We’re keeping it around as a reference path for future optimization once the offline “results” are solid.

```bash
python run_experiment.py --interval 10 --db-path ./activity_qwen.db --session-tag my_run
```

## Supported vision stack (current)

There is **one supported path**: load models locally via `transformers` (`Qwen2VLBackend` in `invoy_sdk/vlm_backends.py`). The SDK still contains `ScreenActivityAnalyzer` (`invoy_sdk/analyzer.py`) for an extract → describe pipeline, but the current experiments are centered on `simplified_gpu_two_model_compare.py`.

Older and alternative entry points live under `old_implementations/` for reference.

## Requirements

- Linux (primary target; other platforms may work but are untested)
- Python 3.9+
- **Display**: Active graphical session. On **X11**, mss is used. On **GNOME Wayland**, gnome-screenshot is required (`sudo apt install gnome-screenshot`). On **Sway/wlroots**, grim is used. **Note:** scrot produces black/empty screenshots on Wayland—do not use. See [docs/SCREENSHOT_PLATFORM.md](docs/SCREENSHOT_PLATFORM.md) for tested configurations.

## Installation

**Capture only** (no VLM):

```bash
pip install -e .
```

**Activity analysis** (Qwen VL):

```bash
pip install -e ".[vlm-native]"
```

First run downloads weights from Hugging Face (default: `Qwen/Qwen2-VL-2B-Instruct`).

## Docs index

- [docs/SCREENSHOT_PLATFORM.md](docs/SCREENSHOT_PLATFORM.md): screenshot stack notes by platform/WM
- [docs/LOCAL_VLM_QWEN_AND_MOONDREAM.md](docs/LOCAL_VLM_QWEN_AND_MOONDREAM.md): code map (some sections are historical)
- [docs/ACTIVITY_TRACKING.md](docs/ACTIVITY_TRACKING.md): activity tracking notes (some sections are historical)
- [docs/EXPERIMENTS_INVoy_VLM.md](docs/EXPERIMENTS_INVoy_VLM.md): experiment notes (historical + progress log)
- [GITHUB_SETUP.md](GITHUB_SETUP.md): pushing repo to GitHub (update may be needed depending on your setup)
- [PROJECT_HISTORY.md](PROJECT_HISTORY.md): what we tried, what works now, what we’re doing next
- [docs/IMPLEMENTATION_HISTORY.md](docs/IMPLEMENTATION_HISTORY.md): dense technical history + how to reproduce older paths

