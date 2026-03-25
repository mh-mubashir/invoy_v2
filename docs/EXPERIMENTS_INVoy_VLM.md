## Invoy VLM Experiments – Local Screen Activity Tracking

> Note: This document contains a historical experiment write-up (originally Ollama-based) plus a progress log. The **current actively used** workflow is the two-model GPU compare in `simplified_gpu_two_model_compare.py` (see repo `README.md`).

### 1. Motivation & Goal

We want to evaluate how well local vision-language models (VLMs) running via Ollama can:

- **Describe on-screen work activity** from periodic desktop screenshots.
- **Detect changes between consecutive screenshots**, distinguishing SAME vs DIFFERENT work.

The goal is to produce quantitative metrics, visualizations, and a reproducible protocol that can be shared with supervisors and collaborators.

### 2. Experimental Setup

- **Hardware**: CPU, RAM, OS details for the experiment machine (to be filled in).
- **Software**:
  - Python version
  - Ollama version
  - Invoy SDK version / commit hash
  - Models pulled via Ollama (e.g. `moondream`, `moondream:1.8b-v2-q5_K_M`, `moondream:1.8b-v2-q8_0`, `llava`, `llava-phi3`)
- **Environment**:
  - Screenshot interval and resolution
  - Desktop environment / window manager
  - Typical applications used during sessions (IDE, browser, email client, etc.)

### 3. Methodology

- **Pipeline**:
  - `ActivityTrackingPipeline` captures screenshots every _N_ seconds.
  - `MoondreamAnalyzer` (or other VLMs via Ollama) generates:
    - Activity description for each screenshot.
    - Change summary comparing current vs previous screenshot.
  - `SQLiteActivityLog` stores entries in a SQLite DB.
- **Variables we vary**:
  - **Model**: `moondream`, `moondream:1.8b-v2-q8_0`, `llava`, `llava-phi3`, etc.
  - **Prompting**: current dense prompts vs alternative/shorter prompts (tracked via `prompt_version`).
  - **Task type**: coding sessions, reading docs, email/communication, document writing, general browsing.
  - **Sampling interval**: e.g. 10s, 20s, 30s.
- **Logging schema (SQLite)**:
  - Core fields: `timestamp`, `unix_time`, `screenshot_path`, `activity`, `change_summary`,
    `activity_inference_ms`, `change_inference_ms`, `session_id`, `created_at`.
  - Experiment fields:
    - `model_name`: VLM model actually used for the inference.
    - `prompt_version`: identifier for the prompt configuration.
    - `activity_quality_score`: optional human rating (1–5) for activity description quality.
    - `change_correct`: optional human label for correctness of the change summary.
- **Human annotation**:
  - A later step will provide a small UI / notebook / script to:
    - Assign `activity_quality_score` per screenshot.
    - Mark `change_correct` for screenshot pairs.

### 4. Running Experiments

- Use `run_experiment.py` to control live pipeline experiments from the CLI (kept for reference; not actively used right now):
  - **Arguments**:
    - `--model`: Ollama model name (e.g. `moondream:1.8b-v2-q8_0`).
    - `--interval`: seconds between screenshots.
    - `--db-path`: SQLite DB file path for this experiment.
    - `--output-dir`: directory for screenshots.
    - `--session-tag`: human-readable tag; used as `session_id` in SQLite.
    - `--prompt-version`: string ID for the prompt configuration.
    - `--ollama-host`: Ollama host URL.
  - **Recommended pattern**:
    - Use a dedicated DB per model × task type combination (e.g. `activity_moondream_coding.db`).
    - Use a meaningful `--session-tag` to distinguish runs.

### 5. Results

This section will summarize:

- **Latency metrics**:
  - Distributions of `activity_inference_ms` and `change_inference_ms` per model and task type.
- **Quality metrics** (after annotation):
  - Average `activity_quality_score` per model / task type.
  - Proportion of correct `change_correct` labels per model.
- **Example cases**:
  - Screenshot thumbnails with model descriptions and commentary (good vs bad behavior).

Tables and plots can be produced from the analysis notebook (`old_implementations/experiments_analysis.ipynb`) or custom scripts.

### 6. Discussion

- **Viability** of local VLM-based activity tracking.
- **Trade-offs** between models (quality vs latency vs resource usage).
- **Impact** of prompt design and sampling interval.

### 7. Next Steps

- Extend experiments to additional models and prompt variants.
- Improve human annotation tooling for faster labeling.
- Optionally compare against cloud-hosted VLMs using the same protocol.

---

## Progress log (implementation notes)

### 2026-03-16 — Prompt iterations and grounding

- **What we implemented**
  - Added `offline_analyze_screenshots.py` to run analysis over an existing screenshot directory and write results to SQLite. (Now archived at `old_implementations/offline_analyze_screenshots.py`.)
  - Extended prompts in `invoy_sdk/analyzer.py` multiple times to improve output quality and reduce “generic” labels.
  - Added helper scripts:
    - `summarize_activity_segments.py`: turns per-frame labels into contiguous activity segments. (Archived at `old_implementations/summarize_activity_segments.py`.)
    - `inspect_activity_db.py`: prints sample rows from `activity_offline.db` to quickly spot bad generations. (Archived at `old_implementations/inspect_activity_db.py`.)
    - `teacher_analyze_screenshots.py` + `evaluate_teacher_student.py`: teacher/student evaluation scaffold. (Archived at `old_implementations/teacher_analyze_screenshots.py` and `old_implementations/evaluate_teacher_student.py`.)

- **Issues we observed**
  - **Prompt parroting / template echo**: Moondream would repeat phrasing from the prompt (and sometimes even our example strings), producing text like “Chrome showing a GitHub PR / Outlook composing an email” regardless of what was on screen.
  - **Over-asking (structured JSON) led to generic labels**: forcing a schema caused broad, low-signal outputs (e.g. “code review”, “payment service”) and occasionally weird wrapper formats like arrays.
  - **Hallucinated detail**: the model would confidently name apps/files that were not readable or not actually present.

- **Fixes / improvements we made**
  - **Removed example strings** from prompts and added explicit “don’t guess” constraints.
  - Added a **prompt-echo detector** and **automatic retry** using a simpler fallback prompt when generations look like they copied the instructions.

- **Current direction (grounded, two-step prompting)**
  - To reduce hallucination and parroting, we’re shifting to a *grounding-first strategy*:
    - **Step A (extract):** extract clearly readable on-screen text tokens; if none, return `NO_READABLE_TEXT`.
    - **Step B (describe/decide):** generate the activity or same/different decision using only extracted evidence.
  - This trades a bit of latency (extra call) for improved faithfulness, which is the right priority at this stage.

### 2026-03-16 — Make grounding debuggable (log extracted text)

- **Problem**
  - The grounded approach reduced parroting, but outputs became too generic (“viewing a webpage”) because we couldn’t see what the extraction step was returning.

- **Fix**
  - Extended SQLite logging to persist the extracted evidence:
    - `activity_extracted_text`
    - `change_prev_extracted_text`
    - `change_cur_extracted_text`
  - Updated both offline and realtime pipelines to store these fields.
  - Updated `inspect_activity_db.py` to print extracted text next to the activity/change outputs. (Now archived at `old_implementations/inspect_activity_db.py`.)

- **Why this matters**
  - We can now answer: “Is Moondream failing OCR (returning `NO_READABLE_TEXT`), or is the describe step ignoring good evidence?”
  - This enables prompt iteration on extraction with direct feedback, instead of guessing.

### 2026-03-16 — Moondream OCR-tuned extraction prompt + retry

- **Observation**
  - With extraction logging enabled, we confirmed Moondream was returning `NO_READABLE_TEXT` for most frames, which forced generic downstream descriptions.

- **Change**
  - Added an OCR-tuned extraction prompt (`EXTRACT_TEXT_PROMPT_V2`) that:
    - Prioritizes specific UI regions (title bar, active tab, URL bar, file tree).
    - Forces verbatim snippets, one per line, max 15 lines.
  - Added a **single extraction retry**: if V2 returns `NO_READABLE_TEXT`, re-run a simpler extraction prompt once.

- **Expected result**
  - `activity_extracted_text` becomes non-empty for many frames.
  - Activity descriptions become more specific (actual tab titles, filenames, URLs) and less generic.

### 2026-03-16 — Image preprocessing + optional extractor model

- **What we changed**
  - Added a lightweight image preprocessing step before extraction:
    - Generate 2× upscaled full-image view.
    - Generate 3× upscaled top-bar crop (with optional sharpening).
  - Extended `MoondreamAnalyzer` to support a separate `extractor_model` used only for OCR-style prompts (defaulting to the main model if not provided).

- **Why**
  - Desktop screenshots at full resolution have very small UI text; upscaling/cropping increases effective text size for the VLM.
  - A future iteration can plug in a more OCR-capable model (e.g. `llava`) for extraction only, while keeping Moondream for activity descriptions.

