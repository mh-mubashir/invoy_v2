"""
Invoy App — InvoyRecorder.

Composes ScreenshotCapture + Qwen2VLBackend + SQLiteActivityLog from the
invoy_sdk without going through ActivityTrackingPipeline (which is tied
to the Ollama/MoondreamAnalyzer path).

Threading model
───────────────
• ScreenshotCapture runs its own daemon thread.
• _on_capture() is called from that thread — all inference runs there too.
• SQLiteActivityLog uses check_same_thread=False so it is safe to write
  from the capture thread.
• UI callbacks are scheduled with root.after(0, fn) so they execute on the
  Tk main thread — the only thread allowed to touch widgets.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

# SDK primitives
try:
    from invoy_sdk.capture import ScreenshotCapture
    from invoy_sdk.vlm_backends import Qwen2VLBackend, InternVL2Backend, VLMBackend, _is_internvl2_model_id
    from invoy_sdk.activity_log import SQLiteActivityLog
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

from invoy_app.settings.config import AppConfig


# ── Constants ──────────────────────────────────────────────────────────────

# Qwen2-VL uses dynamic tiling: a 1920×1080 screenshot can produce 2000+
# vision tokens and makes inference take 20–30 s on a mid-range GPU.
# Resizing to MAX_INFERENCE_WIDTH keeps vision tokens under ~500 and cuts
# inference to 3–8 s without meaningfully harming text legibility.
MAX_INFERENCE_WIDTH = 1280   # pixels; height scaled proportionally


def _resize_for_inference(src_path: str) -> str:
    """
    Return a path to a resized copy of the screenshot if it is wider than
    MAX_INFERENCE_WIDTH, otherwise return the original path unchanged.

    The resized file is written next to the original with a '_thumb' suffix.
    """
    img = Image.open(src_path)
    w, h = img.size
    if w <= MAX_INFERENCE_WIDTH:
        return src_path
    new_h = int(h * MAX_INFERENCE_WIDTH / w)
    img_small = img.resize((MAX_INFERENCE_WIDTH, new_h), Image.LANCZOS)
    thumb_path = str(src_path).replace(".png", "_thumb.png")
    img_small.save(thumb_path)
    print(f"[Invoy] Resized {w}×{h} → {MAX_INFERENCE_WIDTH}×{new_h} for inference")
    return thumb_path


# ── Prompts ────────────────────────────────────────────────────────────────

ACTIVITY_PROMPT = (
    "Reply with one line — no extra text:\n"
    "App · File/URL · Action\n"
    "\n"
    "VS Code · auth.py · editing validate_token function\n"
    "Chrome · https://github.com/user/repo/pull/42 · reviewing PR \"Add rate limiting\"\n"
    "Terminal · ~/projects/invoy · running pytest tests/test_recorder.py\n"
    "\n"
    "- App: foreground application name\n"
    "- File/URL: full URL, file name, or current directory\n"
    "- Action: name a specific visible element — function name, URL path, command, "
    "error message, heading, or PR title"
)

CHANGE_PROMPT_TMPL = (
    "Previous: {prev}\n"
    "Current: {curr}\n\n"
    "Each entry has three fields: App, File/URL, and Action.\n"
    "Compare App, File/URL, and Action individually between the two entries.\n"
    "Write one concise sentence describing what changed or progressed.\n"
    "Reply 'No significant change' ONLY when App, File/URL, and Action are all three "
    "identical between Previous and Current — if any single field differs, describe the change."
)


# ── InvoyRecorder ─────────────────────────────────────────────────────────

class InvoyRecorder:
    """
    Manages a live recording session.

    Parameters
    ----------
    config : AppConfig
    root : tk widget
        Tkinter root — used for thread-safe root.after(0, fn) callbacks.
    on_activity : (activity_text, change_text, timestamp_iso) -> None
    on_error : (message) -> None   — called for fatal errors only
    on_model_loaded : () -> None
    """

    def __init__(
        self,
        config: AppConfig,
        root,
        on_activity: Callable[[str, str, str], None],
        on_error: Callable[[str], None],
        on_model_loaded: Optional[Callable[[], None]] = None,
    ) -> None:
        self._config          = config
        self._root            = root
        self._on_activity     = on_activity
        self._on_error        = on_error
        self._on_model_loaded = on_model_loaded or (lambda: None)

        self._capture:    Optional[ScreenshotCapture] = None
        self._backend:    Optional[VLMBackend]        = None
        self._log:        Optional[SQLiteActivityLog] = None
        self._session_id: Optional[str]               = None
        self._prev_activity: Optional[str]            = None
        self._lock = threading.Lock()
        self._running = False
        self._last_capture_time: float = 0.0

    # ── Public API ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start a new recording session (non-blocking)."""
        if self._running:
            return
        if not _SDK_AVAILABLE:
            self._ui_error("invoy_sdk not installed — cannot start recording.")
            return

        self._config.ensure_dirs()
        self._session_id    = str(uuid.uuid4())[:8]
        self._prev_activity = None
        self._running       = True

        # BUG FIX: pass session_id to the constructor — log() does NOT accept it
        self._log = SQLiteActivityLog(
            db_path=self._config.db_path,
            session_id=self._session_id,
        )

        threading.Thread(target=self._load_model_then_capture, daemon=True).start()

    def stop(self) -> None:
        """Stop recording and close the database."""
        self._running = False
        if self._capture and self._capture.is_running:
            self._capture.stop()
        if self._log:
            try:
                self._log.close()
            except Exception:
                pass
        self._capture = None
        self._backend = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def get_session_entries(self, limit: int = 200) -> list[dict]:
        """Return recent entries for the current session."""
        if not self._log:
            return []
        try:
            # Pass session_id explicitly so it always queries the right session
            return self._log.get_entries(session_id=self._session_id, limit=limit)
        except Exception:
            return []

    def get_all_entries(self, limit: int = 100) -> list[dict]:
        """
        Return the most recent entries across ALL sessions (for the DB viewer).

        get_entries() always filters by session_id, so we do a direct SQL query
        here to show the full history without a session filter.
        """
        db_path = Path(self._config.db_path)
        if not db_path.exists():
            return []
        try:
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, timestamp, unix_time, screenshot_path,
                       activity, change_summary,
                       activity_inference_ms, change_inference_ms,
                       model_name, session_id
                FROM activity_entries
                ORDER BY unix_time DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            print(f"[Invoy] get_all_entries error: {exc}")
            return []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def seconds_until_next_capture(self) -> int:
        """Approximate seconds until the next screenshot, for UI countdown."""
        elapsed = time.monotonic() - self._last_capture_time
        return max(0, int(self._config.interval_seconds - elapsed))

    # ── Internal ───────────────────────────────────────────────────────

    def _load_model_then_capture(self) -> None:
        """Load the VLM (blocking), then start ScreenshotCapture. Runs in thread."""
        print(f"[Invoy] Loading model {self._config.model_id}…")
        try:
            if _is_internvl2_model_id(self._config.model_id):
                self._backend = InternVL2Backend(
                    model_id=self._config.model_id,
                    device=self._config.device,
                )
            else:
                self._backend = Qwen2VLBackend(
                    model_id=self._config.model_id,
                    device=self._config.device,
                )
            self._backend._ensure_loaded()
        except Exception as exc:
            print(f"[Invoy] Model load FAILED: {exc}")
            self._ui_error(f"Model load failed: {exc}")
            self._running = False
            return

        print("[Invoy] Model ready. Starting screenshot capture.")
        self._root.after(0, self._on_model_loaded)

        self._capture = ScreenshotCapture(
            interval_seconds=self._config.interval_seconds,
            output_dir=self._config.screenshot_dir,
            on_capture=self._on_capture,
        )
        self._capture.start()

    def _on_capture(self, path: str, _raw: bytes) -> None:
        """Called from the ScreenshotCapture daemon thread for every frame."""
        if not self._running:
            return

        self._last_capture_time = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        print(f"[Invoy] Frame captured: {path}")

        # Resize screenshot so vision token count stays manageable
        infer_path = _resize_for_inference(path)

        # ── Activity inference ─────────────────────────────────────────
        try:
            print("[Invoy] Running activity inference…")
            activity_text, act_ms = self._backend.generate(
                prompt=ACTIVITY_PROMPT,
                image_paths=[infer_path],
                max_new_tokens=150,
            )
            activity_text = activity_text or "(no description)"
            print(f"[Invoy] Activity ({act_ms:.0f} ms): {activity_text[:80]}")
        except Exception as exc:
            print(f"[Invoy] Activity inference FAILED: {exc}")
            self._ui_error(f"Activity inference error: {exc}")
            return

        # ── Change inference (text-only — image_paths must be [], not None) ──
        change_text = ""
        chg_ms: float = 0.0
        with self._lock:
            prev = self._prev_activity
            self._prev_activity = activity_text

        if prev:
            prompt = CHANGE_PROMPT_TMPL.format(prev=prev, curr=activity_text)
            try:
                change_text, chg_ms = self._backend.generate(
                    prompt=prompt,
                    image_paths=[],   # BUG FIX: empty list, not None
                    max_new_tokens=80,
                )
                change_text = change_text or ""
                print(f"[Invoy] Change ({chg_ms:.0f} ms): {change_text[:60]}")
            except Exception as exc:
                print(f"[Invoy] Change inference error (non-fatal): {exc}")
                change_text = ""

        # ── Log to SQLite ──────────────────────────────────────────────
        # BUG FIX: session_id is set on the log object at construction time,
        # NOT passed as a kwarg to log(). The log() signature does not accept it.
        try:
            self._log.log(
                screenshot_path=path,
                activity=activity_text,
                change_summary=change_text,
                model_name=self._config.model_id,
                activity_inference_ms=act_ms,
                change_inference_ms=chg_ms if chg_ms else None,
            )
            print("[Invoy] Entry saved to DB.")
        except Exception as exc:
            # Truly non-fatal — only print, do NOT call _ui_error
            # (calling _on_error would flip the UI to Error state and confuse the user)
            print(f"[Invoy] DB log error (non-fatal): {exc}")

        # ── Notify UI (thread-safe) ────────────────────────────────────
        self._root.after(
            0,
            lambda a=activity_text, c=change_text, t=ts: self._on_activity(a, c, t),
        )

    def _ui_error(self, msg: str) -> None:
        """Schedule a fatal error callback on the Tk thread."""
        print(f"[Invoy] Fatal error: {msg}")
        self._root.after(0, lambda m=msg: self._on_error(m))
