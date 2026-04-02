"""
Invoy App — InvoyRecorder.

Composes ScreenshotCapture + Qwen2VLBackend + SQLiteActivityLog from the
invoy_sdk without going through ActivityTrackingPipeline (which is tied
to the Ollama/MoondreamAnalyzer path).

Threading model
───────────────
• ScreenshotCapture runs its own daemon thread (ThreadLoop inside capture.py).
• _on_capture() is called from that thread.
• All Qwen inference happens on the capture thread (GPU calls are blocking;
  that's correct — no parallel inference).
• SQLiteActivityLog.log() uses check_same_thread=False so it is safe to call
  from the capture thread.
• UI callbacks are scheduled with root.after(0, fn) so they execute on the
  Tk main thread — the only thread allowed to touch widgets.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

# SDK primitives
try:
    from invoy_sdk.capture import ScreenshotCapture
    from invoy_sdk.vlm_backends import Qwen2VLBackend
    from invoy_sdk.activity_log import SQLiteActivityLog
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

from invoy_app.settings.config import AppConfig


# ── Prompts ────────────────────────────────────────────────────────────────

ACTIVITY_PROMPT = (
    "You are a desktop activity monitor. "
    "Describe what the person is currently doing on this screen in 1-3 sentences. "
    "Name the specific application, file name, or webpage URL if visible. "
    "Be concrete and factual. Plain text only — no markdown."
)

CHANGE_PROMPT_TMPL = (
    "Previous activity: {prev}\n"
    "Current activity: {curr}\n\n"
    "What changed between these two activities? "
    "Answer in one sentence. "
    "If nothing significant changed, say exactly: No significant change."
)


# ── InvoyRecorder ─────────────────────────────────────────────────────────

class InvoyRecorder:
    """
    Manages a live recording session.

    Parameters
    ----------
    config : AppConfig
        Runtime configuration (db path, screenshot dir, model ID, interval).
    root : tk widget
        Tkinter root used for thread-safe ``root.after(0, fn)`` callbacks.
    on_activity : (activity_text, change_text, timestamp_iso) -> None
        Called on the Tk thread whenever a new frame is processed.
    on_error : (message) -> None
        Called on the Tk thread on inference or IO errors.
    on_model_loaded : () -> None
        Called on the Tk thread once the VLM is ready (heavy load done).
    """

    def __init__(
        self,
        config: AppConfig,
        root,
        on_activity: Callable[[str, str, str], None],
        on_error: Callable[[str], None],
        on_model_loaded: Optional[Callable[[], None]] = None,
    ) -> None:
        self._config       = config
        self._root         = root
        self._on_activity  = on_activity
        self._on_error     = on_error
        self._on_model_loaded = on_model_loaded or (lambda: None)

        self._capture:  Optional[ScreenshotCapture]   = None
        self._backend:  Optional[Qwen2VLBackend]      = None
        self._log:      Optional[SQLiteActivityLog]   = None
        self._session_id: Optional[str] = None
        self._prev_activity: Optional[str] = None
        self._lock = threading.Lock()
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start a new recording session (non-blocking)."""
        if self._running:
            return
        if not _SDK_AVAILABLE:
            self._ui_error("invoy_sdk not installed — cannot start recording.")
            return

        self._config.ensure_dirs()
        self._session_id  = str(uuid.uuid4())[:8]
        self._prev_activity = None
        self._running     = True

        # Open DB (fast)
        self._log = SQLiteActivityLog(db_path=self._config.db_path)

        # Load model in a background thread so the UI stays responsive
        threading.Thread(target=self._load_model_then_capture, daemon=True).start()

    def stop(self) -> None:
        """Stop recording and flush the database."""
        self._running = False
        if self._capture and self._capture.is_running:
            self._capture.stop()
        if self._log:
            try:
                self._log.__exit__(None, None, None)
            except Exception:
                pass
        self._capture = None

    def get_session_entries(self, limit: int = 200) -> list[dict]:
        """Return recent log rows for the current session."""
        if not self._log or not self._session_id:
            return []
        try:
            return self._log.get_entries(session_id=self._session_id, limit=limit)
        except Exception:
            return []

    def get_all_entries(self, limit: int = 100) -> list[dict]:
        """Return recent rows across all sessions (for the DB viewer)."""
        if not self._log:
            # open a read-only connection temporarily
            try:
                tmp = SQLiteActivityLog(db_path=self._config.db_path)
                rows = tmp.get_entries(limit=limit)
                tmp.__exit__(None, None, None)
                return rows
            except Exception:
                return []
        try:
            return self._log.get_entries(limit=limit)
        except Exception:
            return []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    # ── Internal ───────────────────────────────────────────────────────

    def _load_model_then_capture(self) -> None:
        """Heavy model load → then kick off ScreenshotCapture. Runs in thread."""
        try:
            self._backend = Qwen2VLBackend(model_id=self._config.model_id)
            # Force the model to load now (lazy load on first generate())
            self._backend._ensure_loaded()
        except Exception as exc:
            self._ui_error(f"Model load failed: {exc}")
            self._running = False
            return

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

        ts = datetime.now(timezone.utc).isoformat()

        # ── Activity inference ─────────────────────────────────────────
        try:
            activity_text, act_ms = self._backend.generate(
                prompt=ACTIVITY_PROMPT,
                image_paths=[path],
                max_new_tokens=200,
            )
            if not activity_text:
                activity_text = "(no description)"
        except Exception as exc:
            self._ui_error(f"Activity inference error: {exc}")
            return

        # ── Change inference (text-only, uses prev activity) ───────────
        change_text = ""
        with self._lock:
            prev = self._prev_activity
            self._prev_activity = activity_text

        if prev:
            prompt = CHANGE_PROMPT_TMPL.format(prev=prev, curr=activity_text)
            try:
                change_text, _ = self._backend.generate(
                    prompt=prompt,
                    image_paths=None,    # text-only
                    max_new_tokens=80,
                )
                if not change_text:
                    change_text = ""
            except Exception:
                change_text = ""

        # ── Log to SQLite ──────────────────────────────────────────────
        try:
            self._log.log(
                screenshot_path=path,
                activity=activity_text,
                change_summary=change_text,
                model_name=self._config.model_id,
                session_id=self._session_id,
            )
        except Exception as exc:
            # Don't abort; just warn
            self._ui_error(f"DB log error (non-fatal): {exc}")

        # ── Notify UI (thread-safe) ────────────────────────────────────
        self._root.after(
            0,
            lambda a=activity_text, c=change_text, t=ts: self._on_activity(a, c, t),
        )

    def _ui_error(self, msg: str) -> None:
        self._root.after(0, lambda m=msg: self._on_error(m))
