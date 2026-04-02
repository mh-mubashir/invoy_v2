"""
Invoy App — InvoyApp root window.

Layout (16:9 feel, 960 × 700)
──────────────────────────────────────────────────────
│          HeaderBar (full width, 56 px)              │
├──────────────────┬──────────────────────────────────┤
│  Left panel      │  Right panel                     │
│  (290 px fixed)  │  (flex)                          │
│                  │                                  │
│  RecordingPanel  │  ActivityFeed (top ~50%)         │
│                  │                                  │
│  ─────────────── │  ──────────────────────────────  │
│                  │                                  │
│  SummaryPanel    │  DatabaseViewer (bottom ~50%)    │
│  (fill + expand) │  (fill + expand)                 │
└──────────────────┴──────────────────────────────────┘
"""

from __future__ import annotations

import time
from typing import Optional

import customtkinter as ctk

from invoy_app.settings.config import AppConfig
from invoy_app.settings.settings_window import SettingsWindow
from invoy_app.components.header import HeaderBar
from invoy_app.components.recording_controls import RecordingPanel
from invoy_app.components.activity_feed import ActivityFeed
from invoy_app.components.db_viewer import DatabaseViewer
from invoy_app.components.summary_panel import SummaryPanel
from invoy_app.core.recorder import InvoyRecorder
from invoy_app.core.notifier import WindowsNotifier
from invoy_app.core.summarizer import ClaudeSummarizer
from invoy_app.styles.theme import (
    COLORS, SPACING, RADIUS,
    WINDOW_W, WINDOW_H, WINDOW_MIN_W, WINDOW_MIN_H,
    LEFT_PANEL_W,
)


class InvoyApp(ctk.CTk):
    """Invoy desktop application root window."""

    def __init__(self) -> None:
        # Load config before super().__init__ so theme is applied first
        self._config = AppConfig.load()
        ctk.set_appearance_mode(self._config.appearance_mode)
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("Invoy")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.configure(fg_color=COLORS["bg"])

        # Set window icon if available
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

        # Session timer state
        self._session_start: Optional[float] = None
        self._timer_job: Optional[str] = None

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ──────────────────────────────────────────────────────────────────
    # Layout
    # ──────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # ── Header (full width) ────────────────────────────────────────
        self.header = HeaderBar(self, on_settings=self._open_settings)
        self.header.pack(fill="x", side="top")

        # ── Body frame ────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        body.pack(fill="both", expand=True, padx=SPACING["md"], pady=SPACING["sm"])
        body.columnconfigure(0, weight=0, minsize=LEFT_PANEL_W)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ── Left panel ────────────────────────────────────────────────
        left = ctk.CTkFrame(body, fg_color=COLORS["bg"], corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["sm"]))
        left.rowconfigure(0, weight=0)
        left.rowconfigure(1, weight=1)

        self.recording_panel = RecordingPanel(
            left,
            on_start=self._on_start_recording,
            on_stop=self._on_stop_recording,
        )
        self.recording_panel.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))

        self.summary_panel = SummaryPanel(left, on_summarize=self._on_summarize)
        self.summary_panel.grid(row=1, column=0, sticky="nsew")
        # Disable summary if no API key
        self.summary_panel.set_button_enabled(bool(self._config.claude_api_key))

        # ── Right panel ───────────────────────────────────────────────
        right = ctk.CTkFrame(body, fg_color=COLORS["bg"], corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self.activity_feed = ActivityFeed(right)
        self.activity_feed.grid(row=0, column=0, sticky="nsew", pady=(0, SPACING["sm"]))

        self.db_viewer = DatabaseViewer(
            right, get_entries=self._recorder.get_all_entries
        )
        self.db_viewer.grid(row=1, column=0, sticky="nsew")
        self.db_viewer.refresh()

    # ──────────────────────────────────────────────────────────────────
    # Recording lifecycle
    # ──────────────────────────────────────────────────────────────────

    def _on_start_recording(self) -> None:
        self.header.set_status("loading")
        self.recording_panel.set_loading(True)
        self._recorder.start()

    def _on_stop_recording(self) -> None:
        self._recorder.stop()
        self._stop_timer()
        self.header.set_status("idle")
        self.recording_panel.set_recording(False)
        self.db_viewer.refresh()

    def _on_model_loaded(self) -> None:
        """Called (on Tk thread) when the VLM finishes loading."""
        self.header.set_status("recording")
        self.recording_panel.set_loading(False)
        self.recording_panel.set_recording(True)
        self._session_start = time.monotonic()
        self._tick_timer()

    # ──────────────────────────────────────────────────────────────────
    # Activity callbacks
    # ──────────────────────────────────────────────────────────────────

    def _on_activity(self, activity_text: str, change_text: str, timestamp_iso: str) -> None:
        """Called on Tk thread for every new frame."""
        self.activity_feed.add_entry(activity_text, change_text, timestamp_iso)
        if self._config.notifications_enabled:
            self._notifier.notify(activity_text)

    def _on_error(self, message: str) -> None:
        """Called on Tk thread on recorder errors."""
        self.header.set_status("error")
        self.recording_panel.set_loading(False)
        self.recording_panel.set_recording(False)
        self._stop_timer()
        # Show in summary panel as a non-fatal alert
        self.summary_panel.show_error(f"Recorder: {message}")

    # ──────────────────────────────────────────────────────────────────
    # Timer
    # ──────────────────────────────────────────────────────────────────

    def _tick_timer(self) -> None:
        if self._recorder.is_running and self._session_start is not None:
            elapsed = int(time.monotonic() - self._session_start)
            self.recording_panel.update_timer(elapsed)
            self._timer_job = self.after(1000, self._tick_timer)

    def _stop_timer(self) -> None:
        if self._timer_job:
            self.after_cancel(self._timer_job)
            self._timer_job = None
        self._session_start = None

    # ──────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────

    def _on_summarize(self) -> None:
        if not self._config.claude_api_key:
            self.summary_panel.show_error("No Claude API key — open Settings to add one.")
            return

        entries = self._recorder.get_session_entries(limit=500)
        if not entries:
            entries = self._recorder.get_all_entries(limit=200)

        self.summary_panel.show_loading()
        self._summarizer.summarize(
            entries=entries,
            on_complete=lambda t: self.after(0, lambda: self.summary_panel.show_result(t)),
            on_error=lambda m: self.after(0, lambda: self.summary_panel.show_error(m)),
        )

    # ──────────────────────────────────────────────────────────────────
    # Settings
    # ──────────────────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        SettingsWindow(
            master=self,
            config=self._config,
            on_save=self._on_settings_saved,
        )

    def _on_settings_saved(self, new_config: AppConfig) -> None:
        self._config = new_config
        self._summarizer.update_api_key(new_config.claude_api_key)
        self.summary_panel.set_button_enabled(bool(new_config.claude_api_key))
        ctk.set_appearance_mode(new_config.appearance_mode)

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self._recorder.is_running:
            self._recorder.stop()
        self.destroy()
