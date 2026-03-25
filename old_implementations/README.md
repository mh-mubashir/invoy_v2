# Archived Ollama and non-Qwen entry points

This folder holds scripts and experiments that targeted **Ollama** (`ollama` Python client + local daemon) or **native Moondream** in isolation. The main repo path is now **Qwen2-VL via Hugging Face** (`transformers`) inside `MoondreamAnalyzer`, with optional **native Moondream fallback** only after recoverable Qwen errors.

## Why Ollama lived here originally

The SDK originally coupled vision inference to Ollama’s HTTP API: one process pulls models (`ollama pull …`), and Python calls `Client(host=…).chat(..., images=[...])`. That was simple for prototyping but led to operational issues (daemon state, model tags, fewer levers for preprocessing/token limits). A later design moved **primary** inference to **`Qwen2VLBackend`** so prompts, multi-image extraction views, and CPU **fast mode** are controlled in-repo.

Relevant Cursor transcripts (parent conversations, not subagents):

- [Ollama migration plan and native backends](826461af-e880-446f-8716-10e66c428e9b) — You asked to move off Ollama for local, quality-first runs; outcome was `Qwen2VLBackend` + `MoondreamNativeBackend` fallback, optional Ollama opt-in (now removed from the main SDK).
- [File inventory vs Qwen2-VL stack](02519c99-1504-466d-81a9-252a1674cc69) — Maps entry points (`offline_analyze_screenshots.py`, `run_experiment.py`) to `analyzer.py` / `vlm_backends.py`. (Some entry points have since been moved under `old_implementations/`.)

## What you learned in practice (from those runs)

- **`Qwen/Qwen2-VL-2B-Instruct`** is already the **smallest** public Qwen2-VL variant; slow runs on **CPU** were largely from **many vision tokens** (multi-view extraction), not from using an oversized checkpoint.
- **Fast CPU path**: default single-view extraction + shorter generation budgets made offline and live runs tractable.
- **Stuck / duplicate Python processes**: multiple concurrent `offline_analyze_screenshots.py` jobs were observed; stopping extras before a new run avoids contention.

## Files in this folder

| File | Role | Methodology |
|------|------|-------------|
| `run_analyzer_test.py` | Quick loop over last few PNGs in `./screenshots`, write `analyzer_results.txt`. | **`MoondreamAnalyzer(..., backend="ollama")`** — archived; **will not run** on the current SDK without restoring `OllamaBackend` (see below). |
| `run_full_test.py` | Last 3 screenshots → activity + change + SQLite log. | Same Ollama-backed **`MoondreamAnalyzer`** pattern as above; archived. |
| `direct_qwen_test.py` | One hardcoded PNG → **`qwen3-vl:8b`** via Ollama. | **Direct `ollama.Client`**, bypasses the analyzer; useful to see raw model behavior (e.g. Canvas grades page) without the extract→describe pipeline. |
| `direct_moondream_test.py` | Same, **Moondream** Ollama tag. | Direct Ollama chat; isol Moondream vs Qwen3-VL on the same image. |
| `direct_llava_test.py` | Same, **LLaVA** Ollama tag. | Direct Ollama chat; baseline comparison for OCR-heavy screens. |
| `moondream_canvas_test.py` | Standalone **native** `moondream` package on a Canvas screenshot. | Not Ollama; archived here so the **main** tree stays Qwen-first. Still requires the native Moondream stack (and Python version constraints per upstream). |

## Restoring Ollama support (if needed)

The class **`OllamaBackend`** was removed from `invoy_sdk/vlm_backends.py`. To revive these scripts:

1. Retrieve the previous implementation from **git history** before this cleanup, **or**
2. Reintroduce a small `OllamaBackend` implementing the same `VLMBackend.generate(...)` contract and wire it in `MoondreamAnalyzer` behind a flag.

Historical **`pip install -e ".[ollama]"`** extra was removed from `pyproject.toml`; add `ollama>=0.3.0` to your environment manually if you restore the backend.
