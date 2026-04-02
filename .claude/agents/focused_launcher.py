"""
Focused launcher — same as app_launcher.py but brings the Invoy window
to the foreground before every screenshot so the app is always visible.
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
    import pygetwindow as gw
    _HAS_GW = True
except ImportError:
    _HAS_GW = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE    = 0.05
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

_REPO_ROOT   = Path(__file__).parents[2]
_WORKSPACE   = Path(__file__).parent / "workspace" / "current"
_SCREENSHOTS = _WORKSPACE / "screenshots"
_CONFIG_FILE = Path.home() / ".invoy" / "config.json"
_PYTHON      = sys.executable

_RECORDING_COLOR = "#F87171"
_ACCENT_COLOR    = "#3B82F6"


def _focus_invoy() -> bool:
    """Bring the Invoy window to the foreground. Returns True if found."""
    if not _HAS_GW:
        return False
    try:
        wins = gw.getWindowsWithTitle("Invoy")
        if wins:
            w = wins[0]
            w.restore()
            w.activate()
            time.sleep(0.4)   # let OS actually bring it to front
            return True
    except Exception as e:
        print(f"[launcher] focus failed: {e}")
    return False


def _capture_screen(path: Path) -> Image.Image:
    _focus_invoy()
    time.sleep(0.2)
    with mss.mss() as sct:
        monitor = sct.monitors[1]   # primary monitor only (not all combined)
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", (raw.width, raw.height), raw.rgb)
        img.save(str(path))
    return img


def _pixel_present(img: Image.Image, target_hex: str, tolerance: int = 20) -> bool:
    r = int(target_hex[1:3], 16)
    g = int(target_hex[3:5], 16)
    b = int(target_hex[5:7], 16)
    for pr, pg, pb in img.getdata():
        if abs(pr - r) < tolerance and abs(pg - g) < tolerance and abs(pb - b) < tolerance:
            return True
    return False


def _find_button_centre(img, target_hex, tolerance=15):
    r_t = int(target_hex[1:3], 16)
    g_t = int(target_hex[3:5], 16)
    b_t = int(target_hex[5:7], 16)
    w, h = img.size
    xs, ys = [], []
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            pr, pg, pb = img.getpixel((x, y))
            if abs(pr-r_t)<tolerance and abs(pg-g_t)<tolerance and abs(pb-b_t)<tolerance:
                xs.append(x); ys.append(y)
    if not xs:
        return None
    return int(sum(xs)/len(xs)), int(sum(ys)/len(ys))


def main() -> None:
    _SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    meta: dict = {
        "launched": False, "model_loaded": False, "card_appeared": False,
        "elapsed_to_card_s": 0, "timeout_hit": False, "screenshots": [], "error": "",
    }

    interval_s = 20.0
    try:
        cfg = json.loads(_CONFIG_FILE.read_text())
        interval_s = float(cfg.get("interval_seconds", 20.0))
    except Exception:
        pass

    proc = None
    try:
        print("[launcher] Starting Invoy app...")
        proc = subprocess.Popen(
            [_PYTHON, "-m", "invoy_app.main"],
            cwd=str(_REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        meta["launched"] = True
        time.sleep(5)   # wait for window to open and render

        # Focus and screenshot IDLE
        focused = _focus_invoy()
        print(f"[launcher] Window focused: {focused}")
        time.sleep(0.5)
        idle_path = _SCREENSHOTS / "01_idle.png"
        idle_img  = _capture_screen(idle_path)
        meta["screenshots"].append("01_idle.png")
        print("[launcher] Captured 01_idle.png")

        # Begin session
        if _HAS_PYAUTOGUI:
            _focus_invoy()
            pyautogui.hotkey("ctrl", "r")
            print("[launcher] Sent Ctrl+R to begin session")
        else:
            centre = _find_button_centre(idle_img, _ACCENT_COLOR)
            if centre and _HAS_PYAUTOGUI:
                pyautogui.click(centre[0], centre[1])
            else:
                meta["error"] = "pyautogui not available"

        # Poll for RECORDING (red pulse dot)
        load_timeout  = 180
        poll_interval = 5
        elapsed_load  = 0
        recording_confirmed = False

        print(f"[launcher] Waiting for recording state (timeout {load_timeout}s)...")
        while elapsed_load < load_timeout:
            time.sleep(poll_interval)
            elapsed_load += poll_interval
            _focus_invoy()
            screen = _capture_screen(_SCREENSHOTS / "_poll.png")
            if _pixel_present(screen, _RECORDING_COLOR, tolerance=25):
                recording_confirmed = True
                print(f"[launcher] Recording state detected at {elapsed_load}s")
                break

        if not recording_confirmed:
            meta["timeout_hit"] = True
            print("[launcher] Timed out waiting for recording state")
            (_SCREENSHOTS / "_poll.png").rename(_SCREENSHOTS / "02_recording.png")
            meta["screenshots"].append("02_recording.png")
        else:
            meta["model_loaded"] = True
            _focus_invoy()
            time.sleep(0.3)
            _capture_screen(_SCREENSHOTS / "02_recording.png")
            meta["screenshots"].append("02_recording.png")
            print("[launcher] Captured 02_recording.png")

            # Wait for first activity card
            card_wait = int(interval_s) + 50
            print(f"[launcher] Waiting {card_wait}s for first inference card...")
            time.sleep(card_wait)

            _focus_invoy()
            time.sleep(0.3)
            _capture_screen(_SCREENSHOTS / "03_first_card.png")
            meta["screenshots"].append("03_first_card.png")
            meta["card_appeared"]     = True
            meta["elapsed_to_card_s"] = card_wait
            print("[launcher] Captured 03_first_card.png")

            # End session
            if _HAS_PYAUTOGUI:
                _focus_invoy()
                pyautogui.hotkey("ctrl", "r")
                print("[launcher] Sent Ctrl+R to end session")
            time.sleep(5)

            _focus_invoy()
            time.sleep(0.3)
            _capture_screen(_SCREENSHOTS / "04_review.png")
            meta["screenshots"].append("04_review.png")
            print("[launcher] Captured 04_review.png")

    except Exception as exc:
        meta["error"] = str(exc)
        print(f"[launcher] ERROR: {exc}")
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
        (_SCREENSHOTS / "_poll.png").unlink(missing_ok=True)

    meta_path = _SCREENSHOTS / "launcher_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"[launcher] Done. Screenshots: {meta['screenshots']}")


if __name__ == "__main__":
    main()
