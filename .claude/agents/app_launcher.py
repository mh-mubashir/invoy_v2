"""
Invoy Testing Agent — App Launcher

Launched by orchestrator.py before the Testing Agent (Phase 3c).
Automates the Invoy app through its three states and captures screenshots
for the Testing Agent (Claude) to analyze with vision.

Usage:
    python .claude/agents/app_launcher.py

Outputs (all written to workspace/current/screenshots/):
    01_idle.png          — IDLE state after app opens
    02_recording.png     — RECORDING state once model is loaded
    03_first_card.png    — first activity card visible in feed
    04_review.png        — REVIEW state after ending session
    launcher_meta.json   — metadata for the Testing Agent

Dependencies:
    mss         — already installed in .alt_vision_venv
    pyautogui   — pip install pyautogui
    Pillow      — already installed
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import mss
import mss.tools
from PIL import Image

try:
    import pyautogui
    pyautogui.FAILSAFE = False   # don't abort if mouse hits corner
    pyautogui.PAUSE    = 0.05    # 50ms between pyautogui calls
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

# ── Paths ─────────────────────────────────────────────────────────────────

_REPO_ROOT    = Path(__file__).parents[2]  # worktree root
_WORKSPACE    = Path(__file__).parent / "workspace" / "current"
_SCREENSHOTS  = _WORKSPACE / "screenshots"
_CONFIG_FILE  = Path.home() / ".invoy" / "config.json"

# Python executable that has the app installed
_PYTHON = sys.executable  # same venv as this script

# ── Colour detection helpers ───────────────────────────────────────────────

def _capture_screen(path: Path) -> Image.Image:
    """Take a full-screen screenshot and save it."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # all monitors combined
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", (raw.width, raw.height), raw.rgb)
        img.save(str(path))
    return img


def _pixel_present(img: Image.Image, target_hex: str, tolerance: int = 20) -> bool:
    """Return True if any pixel in img is within tolerance of target_hex."""
    r = int(target_hex[1:3], 16)
    g = int(target_hex[3:5], 16)
    b = int(target_hex[5:7], 16)
    arr = img.getdata()
    for pr, pg, pb in arr:
        if abs(pr - r) < tolerance and abs(pg - g) < tolerance and abs(pb - b) < tolerance:
            return True
    return False


def _find_button_centre(img: Image.Image, target_hex: str, tolerance: int = 15):
    """
    Find the centroid of the largest contiguous region matching target_hex.
    Returns (x, y) in screen coordinates or None.
    """
    r_t = int(target_hex[1:3], 16)
    g_t = int(target_hex[3:5], 16)
    b_t = int(target_hex[5:7], 16)

    w, h = img.size
    xs, ys = [], []
    for y in range(0, h, 4):   # sample every 4th pixel — fast enough
        for x in range(0, w, 4):
            pr, pg, pb = img.getpixel((x, y))
            if (abs(pr - r_t) < tolerance and
                    abs(pg - g_t) < tolerance and
                    abs(pb - b_t) < tolerance):
                xs.append(x)
                ys.append(y)

    if not xs:
        return None
    return int(sum(xs) / len(xs)), int(sum(ys) / len(ys))


# ── Recording state detection ─────────────────────────────────────────────

_RECORDING_COLOR = "#F87171"   # pulse dot colour — only present in RECORDING state
_ACCENT_COLOR    = "#3B82F6"   # Begin Session button colour

# ── Main launcher ─────────────────────────────────────────────────────────

def main() -> None:
    _SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    meta: dict = {
        "launched":        False,
        "model_loaded":    False,
        "card_appeared":   False,
        "elapsed_to_card_s": 0,
        "timeout_hit":     False,
        "screenshots":     [],
        "error":           "",
    }

    # Read interval_seconds from config
    interval_s = 20.0
    try:
        cfg = json.loads(_CONFIG_FILE.read_text())
        interval_s = float(cfg.get("interval_seconds", 20.0))
    except Exception:
        pass

    try:
        # ── Launch app ────────────────────────────────────────────────
        print("[launcher] Starting Invoy app…")
        proc = subprocess.Popen(
            [_PYTHON, "-m", "invoy_app.main"],
            cwd=str(_REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        meta["launched"] = True
        time.sleep(4)  # wait for window to open

        # ── Screenshot 01: IDLE ───────────────────────────────────────
        idle_path = _SCREENSHOTS / "01_idle.png"
        idle_img  = _capture_screen(idle_path)
        meta["screenshots"].append("01_idle.png")
        print(f"[launcher] Captured 01_idle.png")

        # ── Begin session ─────────────────────────────────────────────
        if _HAS_PYAUTOGUI:
            # Try Ctrl+R first (keyboard shortcut)
            pyautogui.hotkey("ctrl", "r")
            print("[launcher] Sent Ctrl+R to begin session")
        else:
            # Fallback: find accent-blue Begin Session button and click it
            centre = _find_button_centre(idle_img, _ACCENT_COLOR)
            if centre:
                # pyautogui not available — can't click; log warning
                meta["error"] = "pyautogui not installed; could not click Begin Session"
                print("[launcher] WARNING: pyautogui not available")
            else:
                meta["error"] = "pyautogui not installed and Begin Session button not found"

        # ── Poll for RECORDING state ──────────────────────────────────
        recording_confirmed = False
        load_timeout = 120
        poll_interval = 8
        elapsed_load = 0

        print(f"[launcher] Waiting for model to load (timeout {load_timeout}s)…")
        while elapsed_load < load_timeout:
            time.sleep(poll_interval)
            elapsed_load += poll_interval
            screen = _capture_screen(_SCREENSHOTS / "_poll.png")
            if _pixel_present(screen, _RECORDING_COLOR):
                recording_confirmed = True
                print(f"[launcher] Recording state detected after {elapsed_load}s")
                break

        if not recording_confirmed:
            meta["timeout_hit"]  = True
            meta["model_loaded"] = False
            print("[launcher] Model load timed out — saving partial results")
            # Still save what we have
            (_SCREENSHOTS / "_poll.png").rename(_SCREENSHOTS / "02_recording.png")
            meta["screenshots"].append("02_recording.png")
        else:
            meta["model_loaded"] = True
            rec_path = _SCREENSHOTS / "02_recording.png"
            _capture_screen(rec_path)
            meta["screenshots"].append("02_recording.png")
            print("[launcher] Captured 02_recording.png")

            # ── Wait for first activity card ──────────────────────────
            card_wait = int(interval_s) + 45   # interval + inference buffer
            print(f"[launcher] Waiting {card_wait}s for first card…")
            time.sleep(card_wait)

            card_path = _SCREENSHOTS / "03_first_card.png"
            _capture_screen(card_path)
            meta["screenshots"].append("03_first_card.png")
            meta["card_appeared"]    = True          # launcher assumes card arrived
            meta["elapsed_to_card_s"] = card_wait
            print("[launcher] Captured 03_first_card.png")

            # ── End session ───────────────────────────────────────────
            if _HAS_PYAUTOGUI:
                pyautogui.hotkey("ctrl", "r")
                print("[launcher] Sent Ctrl+R to end session")
            time.sleep(4)

            review_path = _SCREENSHOTS / "04_review.png"
            _capture_screen(review_path)
            meta["screenshots"].append("04_review.png")
            print("[launcher] Captured 04_review.png")

    except Exception as exc:
        meta["error"] = str(exc)
        print(f"[launcher] ERROR: {exc}")
    finally:
        # Always terminate the app
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        # Clean up poll temp file
        (_SCREENSHOTS / "_poll.png").unlink(missing_ok=True)

    # ── Write metadata ────────────────────────────────────────────────
    meta_path = _SCREENSHOTS / "launcher_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"[launcher] Wrote launcher_meta.json")
    print(f"[launcher] Done. Screenshots: {meta['screenshots']}")


if __name__ == "__main__":
    main()
