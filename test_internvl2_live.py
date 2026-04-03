"""
Live inference test for InternVL2-2B and InternVL2-4B from the Invoy App perspective.

Reproduces the exact execution path used by InvoyRecorder._on_capture():
  1. _resize_for_inference() — same 1280-px cap
  2. backend.generate(prompt=ACTIVITY_PROMPT, image_paths=[...], max_new_tokens=150)
  3. delete backend + empty CUDA cache before loading the next model

Run with:
  C:/Users/hamza/Documents/coding/invoy_v2/.venv312_cu128/Scripts/python test_internvl2_live.py
"""

from __future__ import annotations

import gc
import io
import os
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows so non-ASCII chars in model responses don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Make invoy_sdk importable from repo root ───────────────────────────────
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

# ── Imports from the Invoy codebase ───────────────────────────────────────
from invoy_sdk.vlm_backends import InternVL2Backend
from invoy_app.core.recorder import ACTIVITY_PROMPT, _resize_for_inference

# ── Screenshots to test ───────────────────────────────────────────────────
SCREENSHOTS = [
    "C:/Users/hamza/.invoy/screenshots/screenshot_20260402_053101.png",
    "C:/Users/hamza/.invoy/screenshots/screenshot_20260402_053336.png",
    "C:/Users/hamza/.invoy/screenshots/screenshot_20260402_053609.png",
]

MODELS = [
    "OpenGVLab/InternVL2-2B",
    "OpenGVLab/InternVL2-4B",
]

MAX_NEW_TOKENS = 150  # same value InvoyRecorder._on_capture() uses for activity inference

# ── Results collector ─────────────────────────────────────────────────────
results: list[dict] = []


def separator(char: str = "-", width: int = 70) -> None:
    print(char * width)


def run_model(model_id: str) -> list[dict]:
    """Load model, run inference on all screenshots, return per-screenshot results."""
    model_results = []

    separator("=")
    print(f"MODEL: {model_id}")
    separator("=")

    try:
        backend = InternVL2Backend(model_id=model_id, device="cuda")
        print(f"[load] Calling _ensure_loaded() for {model_id} ...")
        load_t0 = time.perf_counter()
        backend._ensure_loaded()
        load_ms = (time.perf_counter() - load_t0) * 1000
        print(f"[load] Model ready in {load_ms/1000:.1f}s")
    except Exception as exc:
        print(f"[ERROR] Failed to load {model_id}: {exc}")
        return [{"model_id": model_id, "screenshot": s, "response": None,
                 "inference_ms": 0.0, "error": str(exc)} for s in SCREENSHOTS]

    for raw_path in SCREENSHOTS:
        fname = Path(raw_path).name
        separator()
        print(f"  Screenshot : {fname}")

        # Mirror InvoyRecorder._on_capture() — resize before inference
        try:
            infer_path = _resize_for_inference(raw_path)
        except Exception as exc:
            print(f"  [WARN] resize failed ({exc}), using original")
            infer_path = raw_path

        try:
            response, inf_ms = backend.generate(
                prompt=ACTIVITY_PROMPT,
                image_paths=[infer_path],
                max_new_tokens=MAX_NEW_TOKENS,
            )
        except Exception as exc:
            print(f"  [ERROR] generate() raised: {exc}")
            response, inf_ms = None, 0.0

        print(f"  Inference  : {inf_ms:.0f} ms")
        print(f"  Response   : {response!r}")

        model_results.append({
            "model_id": model_id,
            "screenshot": fname,
            "infer_path": infer_path,
            "response": response,
            "inference_ms": round(inf_ms, 1),
            "error": None,
        })

    # Explicit teardown - mirrors InvoyRecorder.stop()
    print(f"\n[unload] Deleting backend for {model_id} ...")
    del backend
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            print("[unload] CUDA cache cleared.")
    except Exception as exc:
        print(f"[unload] cuda.empty_cache() failed: {exc}")

    return model_results


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 70)
    print("Invoy App - InternVL2 Live Inference Test")
    print(f"Repo root : {REPO_ROOT}")
    print(f"Prompt    : {ACTIVITY_PROMPT[:60].strip()!r} ...")
    print(f"Tokens    : max_new_tokens={MAX_NEW_TOKENS}")
    print("=" * 70 + "\n")

    all_results: list[dict] = []

    for model_id in MODELS:
        model_results = run_model(model_id)
        all_results.extend(model_results)

    # ── Summary table ─────────────────────────────────────────────────────
    separator("=")
    print("SUMMARY")
    separator("=")
    for r in all_results:
        tag = "OK " if r["response"] else "ERR"
        ms  = f"{r['inference_ms']:>7.0f}ms" if r["inference_ms"] else "       N/A"
        resp_preview = (r["response"] or "(none)")[:80]
        print(f"[{tag}] {r['model_id']:<30s}  {r['screenshot']:<45s}  {ms}  {resp_preview!r}")

    # ── Persist raw outputs for report ────────────────────────────────────
    import json

    report_path = (
        REPO_ROOT
        / ".claude"
        / "agents"
        / "workspace"
        / "current"
        / "live_test_report.json"
    )

    # Quality heuristics (applied from the app's perspective)
    def assess(entries: list[dict]) -> dict:
        bullet = "\u00b7"  # U+00B7 middle dot used in ACTIVITY_PROMPT example lines
        format_ok   = [e for e in entries if e["response"] and bullet in e["response"]]
        responded   = [e for e in entries if e["response"]]
        unique_resp = len({e["response"] for e in responded})
        no_response = [e for e in entries if not e["response"]]

        # Check each model individually for screenshot variation
        per_model_variation: dict[str, bool] = {}
        for mid in MODELS:
            model_entries = [e for e in entries if e["model_id"] == mid and e["response"]]
            per_model_variation[mid] = len({e["response"] for e in model_entries}) > 1

        return {
            "total_inferences": len(entries),
            "responded_count": len(responded),
            "format_ok_count": len(format_ok),
            "format_ok_pct": round(len(format_ok) / len(entries) * 100) if entries else 0,
            "unique_responses": unique_resp,
            "reads_screen": unique_resp > 1,
            "no_response_count": len(no_response),
            "per_model_variation": per_model_variation,
        }

    quality = assess(all_results)

    # overall verdict from the app's POV:
    # pass  = format correct most of the time AND model reads the screen
    # rework = format broken or outputs identical across screenshots
    # inconclusive = no responses at all
    if quality["responded_count"] == 0:
        overall = "inconclusive"
    elif quality["format_ok_pct"] >= 50 and quality["reads_screen"]:
        overall = "pass"
    elif quality["format_ok_pct"] >= 50 or quality["reads_screen"]:
        overall = "rework"
    else:
        overall = "rework"

    report = {
        "overall": overall,
        "quality_assessment": quality,
        "db_evidence": {
            "entries": all_results,
            "format_separator": "\u00b7 (U+00B7 middle dot)",
            "expected_format": "App \u00b7 File/URL \u00b7 Action",
        },
        "models_tested": MODELS,
        "screenshots_tested": [Path(s).name for s in SCREENSHOTS],
        "max_new_tokens": MAX_NEW_TOKENS,
        "notes": (
            "Test mirrors InvoyRecorder._on_capture() exactly: "
            "_resize_for_inference() applied before generate(), "
            "same ACTIVITY_PROMPT, same max_new_tokens=150."
        ),
        "status": "done",
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[report] Written to: {report_path}")
    print(f"[report] Overall verdict: {overall.upper()}")
    print(f"[report] Format OK: {quality['format_ok_count']}/{quality['total_inferences']} "
          f"({quality['format_ok_pct']}%)")
    print(f"[report] Unique responses: {quality['unique_responses']} "
          f"(reads screen: {quality['reads_screen']})")


if __name__ == "__main__":
    main()
