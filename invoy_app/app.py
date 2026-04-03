"""
Invoy App — InvoyApp root window.

Three-state model
─────────────────
  IDLE      App opens / session ends.  Centred single-action view.
  RECORDING Model loaded, capture running.  Full-width activity timeline.
  REVIEW    User ends session.  Structured category cards (+ timeline toggle).

A single `content_frame` is cleared and repopulated on each state transition.
All UI updates that originate from background threads use root.after(0, fn).
"""

from __future__ import annotations

import enum
import time
from typing import Optional

import customtkinter as ctk

from invoy_app.settings.config import AppConfig
from invoy_app.settings.settings_window import SettingsWindow
from invoy_app.components.header import HeaderBar
from invoy_app.components.idle_view import IdleView
from invoy_app.components.activity_feed import ActivityFeed
from invoy_app.components.summary_panel import SummaryPanel
from invoy_app.core.recorder import InvoyRecorder
from invoy_app.core.notifier import WindowsNotifier
from invoy_app.core.summarizer import ClaudeSummarizer
from invoy_app.styles.theme import (
    COLORS, FONTS, SPACING,
    WINDOW_W, WINDOW_H, WINDOW_MIN_W, WINDOW_MIN_H,
)


class AppState(enum.Enum):
    IDLE      = "idle"
    RECORDING = "recording"
    REVIEW    = "review"


class InvoyApp(ctk.CTk):
    """Invoy desktop application root window."""

    def __init__(self) -> None:
        self._config = AppConfig.load()
        ctk.set_appearance_mode(self._config.appearance_mode)
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("Invoy")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.configure(fg_color=COLORS["bg"])

        try:
            from pathlib import Path
            icon = Path(__file__).parent / "assets" / "icon.ico"
            if icon.exists():
                self.iconbitmap(str(icon))
        except Exception:
            pass

        # Core services
        self._notifier   = WindowsNotifier()
        self._summarizer = ClaudeSummarizer(api_key=self._config.claude_api_key)
        self._recorder   = InvoyRecorder(
            config=self._config,
            root=self,
            on_activity=self._on_activity,
            on_error=self._on_error,
            on_model_loaded=self._on_model_loaded,
        )

        # State
        self._state: AppState         = AppState.IDLE
        self._session_start: Optional[float] = None
        self._poll_job: Optional[str] = None

        # Live component references (populated per-state)
        self._idle_view:      Optional[IdleView]      = None
        self._activity_feed:  Optional[ActivityFeed]  = None
        self._summary_panel:  Optional[SummaryPanel]  = None
        # Keep a persistent ActivityFeed for the review toggle
        self._review_feed:    Optional[ActivityFeed]  = None

        self._build_chrome()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start in Idle state
        self._enter_idle()

    # ──────────────────────────────────────────────────────────────────
    # Chrome (persistent, never replaced)
    # ──────────────────────────────────────────────────────────────────

    def _build_chrome(self) -> None:
        self.header = HeaderBar(
            self,
            on_settings=self._open_settings,
            on_end_session=self._on_end_session,
            on_new_session=self._on_new_session,
            on_view_toggle=self._on_view_toggle,
        )
        self.header.pack(fill="x", side="top")

        self._content_frame = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self._content_frame.pack(fill="both", expand=True)

    def _clear_content(self) -> None:
        for w in self._content_frame.winfo_children():
            w.destroy()
        self._idle_view     = None
        self._activity_feed = None
        self._summary_panel = None
        self._review_feed   = None

    # ──────────────────────────────────────────────────────────────────
    # State transitions
    # ──────────────────────────────────────────────────────────────────

    def _enter_idle(self) -> None:
        self._stop_poll()
        self._clear_content()
        self._state = AppState.IDLE
        self.header.set_mode("idle")

        sessions = self._get_recent_sessions()
        self._idle_view = IdleView(
            self._content_frame,
            on_begin=self._on_begin_session,
            on_open_session=self._on_open_past_session,
            model_label=self._short_model_label(),
            interval_seconds=self._config.interval_seconds,
        )
        self._idle_view.pack(fill="both", expand=True)
        if sessions:
            self._idle_view.load_history(sessions)

    def _enter_loading(self) -> None:
        """Visual-only transition while the model is loading."""
        self._state = AppState.RECORDING   # will be "live" once model loaded
        self.header.set_mode("loading")
        if self._idle_view:
            self._idle_view.set_loading(True)

    def _enter_recording(self) -> None:
        """Called once the model is ready and capture is live."""
        self._clear_content()
        self._state = AppState.RECORDING
        self.header.set_mode("recording")
        self._session_start = time.monotonic()

        self._activity_feed = ActivityFeed(self._content_frame)
        self._activity_feed.pack(fill="both", expand=True)

        self._start_poll()

    def _enter_review(self) -> None:
        self._stop_poll()

        # Capture the feed entries before clearing the frame
        entries = self._recorder.get_session_entries(limit=500)
        if not entries:
            entries = self._recorder.get_all_entries(limit=200)

        self._clear_content()
        self._state = AppState.REVIEW
        self.header.set_mode("review")

        has_api_key = bool(self._config.claude_api_key)
        self._summary_panel = SummaryPanel(
            self._content_frame,
            on_generate=lambda: self._run_summarize(entries),
            recording_active=False,
        )
        self._summary_panel.pack(fill="both", expand=True)

        # Auto-trigger if API key is present
        if has_api_key and entries:
            self._run_summarize(entries)
        elif not has_api_key:
            self._summary_panel.show_error(
                "No Claude API key — open Settings ⚙ to add one."
            )

    # ──────────────────────────────────────────────────────────────────
    # User-initiated events
    # ──────────────────────────────────────────────────────────────────

    def _on_begin_session(self) -> None:
        self._enter_loading()
        self._recorder.start()

    def _on_end_session(self) -> None:
        self._recorder.stop()
        self._enter_review()

    def _on_new_session(self) -> None:
        self._enter_idle()

    def _on_open_past_session(self, session_id: str) -> None:
        """Navigate to Review for a past session from the idle history."""
        entries = self._recorder.get_all_entries(limit=200)
        # Filter to the chosen session
        session_entries = [e for e in entries if e.get("session_id") == session_id]
        if not session_entries:
            session_entries = entries  # fallback: show all

        self._clear_content()
        self._state = AppState.REVIEW
        self.header.set_mode("review")

        has_api_key = bool(self._config.claude_api_key)
        self._summary_panel = SummaryPanel(
            self._content_frame,
            on_generate=lambda: self._run_summarize(session_entries),
            recording_active=False,
        )
        self._summary_panel.pack(fill="both", expand=True)

        if has_api_key and session_entries:
            self._run_summarize(session_entries)
        elif not has_api_key:
            self._summary_panel.show_error(
                "No Claude API key — open Settings ⚙ to add one."
            )

    def _on_view_toggle(self, view: str) -> None:
        """Switch Review content between summary cards and raw timeline."""
        if self._state != AppState.REVIEW:
            return

        if view == "list":
            # Hide summary panel, show timeline
            if self._summary_panel:
                self._summary_panel.pack_forget()
            if not self._review_feed:
                self._review_feed = ActivityFeed(self._content_frame)
                entries = self._recorder.get_session_entries(limit=200)
                if not entries:
                    entries = self._recorder.get_all_entries(limit=200)
                for e in reversed(entries):
                    self._review_feed.add_entry(
                        e.get("activity") or "",
                        e.get("change_summary") or "",
                        e.get("timestamp") or "",
                    )
            self._review_feed.pack(fill="both", expand=True)

        else:
            # Back to cards
            if self._review_feed:
                self._review_feed.pack_forget()
            if self._summary_panel:
                self._summary_panel.pack(fill="both", expand=True)

    # ──────────────────────────────────────────────────────────────────
    # Recorder callbacks
    # ──────────────────────────────────────────────────────────────────

    def _on_model_loaded(self) -> None:
        """Called on Tk thread once the VLM has finished loading."""
        self._enter_recording()

    def _on_activity(self, activity_text: str, change_text: str, timestamp_iso: str) -> None:
        """Called on Tk thread for every new captured frame."""
        if self._activity_feed:
            self._activity_feed.add_entry(activity_text, change_text, timestamp_iso)
        if self._config.notifications_enabled:
            self._notifier.notify(activity_text)

    def _on_error(self, message: str) -> None:
        """Called on Tk thread on recorder errors."""
        self._stop_poll()
        self.header.set_mode("idle")
        self._clear_content()
        self._state = AppState.IDLE

        self._idle_view = IdleView(
            self._content_frame,
            on_begin=self._on_begin_session,
            on_open_session=self._on_open_past_session,
            model_label=self._short_model_label(),
            interval_seconds=self._config.interval_seconds,
        )
        self._idle_view.pack(fill="both", expand=True)
        # Show error inline via a label overlay (keep UI clean)
        import customtkinter as _ctk
        err_lbl = _ctk.CTkLabel(
            self._content_frame,
            text=f"Error: {message}",
            font=FONTS["status"],
            text_color=COLORS["danger"],
        )
        err_lbl.place(relx=0.5, rely=0.95, anchor="s")

    # ──────────────────────────────────────────────────────────────────
    # Countdown / status poll
    # ──────────────────────────────────────────────────────────────────

    def _start_poll(self) -> None:
        self._poll_tick()

    def _poll_tick(self) -> None:
        if self._state != AppState.RECORDING:
            return
        elapsed = int(time.monotonic() - (self._session_start or time.monotonic()))
        h, rem  = divmod(elapsed, 3600)
        m, s    = divmod(rem, 60)
        time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

        countdown = self._recorder.seconds_until_next_capture
        model_short = self._short_model_label()
        status = f"{time_str}  ·  {model_short}  ·  next in {countdown} s"
        self.header.update_status(status)

        # Push countdown to the feed's empty state
        if self._activity_feed:
            self._activity_feed.set_countdown(countdown)

        self._poll_job = self.after(1000, self._poll_tick)

    def _stop_poll(self) -> None:
        if self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
        self._poll_job = None
        self._session_start = None

    # ──────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────

    def _run_summarize(self, entries: list[dict]) -> None:
        if not self._summary_panel:
            return
        if not self._config.claude_api_key:
            self._summary_panel.show_error(
                "No Claude API key — open Settings ⚙ to add one."
            )
            return

        self._summary_panel.show_loading()
        self._summarizer.summarize(
            entries=entries,
            on_complete=lambda t: self.after(
                0, lambda: self._summary_panel.show_result(t) if self._summary_panel else None
            ),
            on_error=lambda m: self.after(
                0, lambda: self._summary_panel.show_error(m) if self._summary_panel else None
            ),
        )

    # ──────────────────────────────────────────────────────────────────
    # Settings
    # ──────────────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        SettingsWindow(
            master=self,
            config=self._config,
            on_save=self._on_settings_saved,
            recording_active=self._recorder.is_running,
        )

    def _on_settings_saved(self, new_config: AppConfig) -> None:
        self._config = new_config
        self._recorder._config = new_config
        self._summarizer.update_api_key(new_config.claude_api_key)
        ctk.set_appearance_mode(new_config.appearance_mode)

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    def _short_model_label(self) -> str:
        mid = self._config.model_id
        if "InternVL2-4B" in mid or "InternVL2_4B" in mid:
            return "InternVL2 4B"
        if "InternVL2-2B" in mid or "InternVL2_2B" in mid:
            return "InternVL2 2B"
        if "3B" in mid:
            return "Qwen2.5-VL 3B"
        if "2B" in mid:
            return "Qwen2-VL 2B"
        if "7B" in mid:
            return "Qwen2-VL 7B"
        return mid.split("/")[-1][:20]

    def _get_recent_sessions(self) -> list[dict]:
        """Return a condensed list of recent sessions for the idle history."""
        try:
            entries = self._recorder.get_all_entries(limit=500)
            if not entries:
                return []
            # Group by session_id
            seen: dict[str, dict] = {}
            for e in entries:
                sid = e.get("session_id") or ""
                if sid not in seen:
                    seen[sid] = {
                        "session_id": sid,
                        "start_time": e.get("timestamp", ""),
                        "end_time":   e.get("timestamp", ""),
                        "summary_snippet": (e.get("activity") or "")[:60],
                        "_count": 0,
                    }
                seen[sid]["start_time"] = e.get("timestamp", "")  # entries are DESC
                seen[sid]["_count"] += 1

            sessions = list(seen.values())
            # Compute approximate duration from count × interval
            for s in sessions:
                s["duration_s"] = s["_count"] * int(self._config.interval_seconds)

            return sessions[:5]
        except Exception:
            return []

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self._stop_poll()
        if self._recorder.is_running:
            self._recorder.stop()
        self.destroy()
