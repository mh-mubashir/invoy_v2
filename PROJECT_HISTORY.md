# Project history (human-readable)

This is a short, narrative “what we did and why” document. For a denser technical breakdown (scripts, schemas, reproduction steps), see [`docs/IMPLEMENTATION_HISTORY.md`](docs/IMPLEMENTATION_HISTORY.md).

## What this project is

Invoy is an SDK + experiment playground for:

- Periodic **screenshot capture**
- Local VLM-based **activity description**
- Comparing consecutive frames for **change / task continuity**

The goal is to make the outputs good enough to be useful first, then make the pipeline efficient.

## What’s working for us right now

### Current “main loop”

We currently run experiments through:

- `simplified_gpu_two_model_compare.py`

This is the workflow we’re actively iterating on because it makes it easy to:

- Compare **Model A vs Model B** on the same screenshot sequence
- Persist results into SQLite for later analysis
- Keep prompts and outputs **simple and inspectable**

### Data collection that’s still useful

We still want a clean, reliable “capture-only” path:

- `collect_periodic_screenshots.py` (capture-only; no VLM, no DB)

That keeps data collection separate from inference, which is helpful when inference is slow or when you want to rerun analysis with different prompts/models.

### Quick smoke tests / demos

- `alt_vision_tests/qwen2_vl_canvas_test.py`: single-image smoke test using the SDK backend
- `alt_vision_tests/screenshot_capture_10s_demo.py`: minimal capture demo

## What we built but aren’t using actively (and why)

### Live pipeline (capture → inference → SQLite)

There is a “live” loop kept in the repo:

- `run_experiment.py` (CLI entrypoint for `ActivityTrackingPipeline`)
- `alt_vision_tests/live_activity_pipeline_demo.py` (tiny demo)

We’re not actively using this because, in practice, **inference time dominates**: the effective cadence is closer to:

\[
\\text{effective interval} \\approx \\text{capture interval} + \\text{inference time}
\]

We’re intentionally focusing on **output quality and comparison workflows first**, then returning to efficiency and real-time behavior later.

## What we tried earlier (high level)

Over time we explored multiple paths (some now archived under `old_implementations/`):

- “Offline analyze a folder of screenshots” pipelines
- Teacher/student comparisons on a different schema
- Post-processing scripts for segmenting activity into “billable” chunks
- Earlier Ollama/Moondream era experiments (archived; see `old_implementations/README.md`)

## What we’re working on right now

- Tightening prompts and output formats for the **two-model compare** workflow
- Making capture + offline runs reproducible across machines
- Building enough analysis around SQLite outputs to quickly spot improvements/regressions

