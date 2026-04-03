"""
Invoy App — RecordingPanel component.

Left-column panel containing:
  • Large Start / Stop button
  • Session timer
  • Model badge
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from invoy_app.styles.theme import COLORS, FONTS, SPACING, RADIUS, RADIUS_BTN


def _fmt_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class RecordingPanel(ctk.CTkFrame):
    """Start/Stop recording controls with session timer and model badge."""

    def __init__(
        self,
        master,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS,
            **kwargs,
        )
        self._on_start   = on_start
        self._on_stop    = on_stop
        self._recording  = False

        self._btn:       ctk.CTkButton | None = None
        self._timer_lbl: ctk.CTkLabel  | None = None

        self._build()

    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        pad = SPACING["lg"]

        # Section title
        ctk.CTkLabel(
            self,
            text="Recording",
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["md"], 0))

        ctk.CTkFrame(
            self, fg_color=COLORS["border"], height=1, corner_radius=0
        ).pack(fill="x", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]))

        # Main action button — pill shaped
        self._btn = ctk.CTkButton(
            self,
            text="Start Recording",
            width=200, height=52,
            corner_radius=RADIUS_BTN,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            font=FONTS["body_bold"],
            command=self._toggle,
        )
        self._btn.pack(pady=(0, SPACING["md"]))

        # Session timer
        timer_frame = ctk.CTkFrame(self, fg_color=COLORS["raised"], corner_radius=RADIUS)
        timer_frame.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["sm"]))

        ctk.CTkLabel(
            timer_frame,
            text="Session",
            font=FONTS["small"],
            text_color=COLORS["subtext"],
        ).pack(side="left", padx=SPACING["sm"], pady=SPACING["sm"])

        self._timer_lbl = ctk.CTkLabel(
            timer_frame,
            text="00:00:00",
            font=FONTS["mono"],
            text_color=COLORS["text"],
        )
        self._timer_lbl.pack(side="right", padx=SPACING["sm"], pady=SPACING["sm"])

        # Model badge
        badge = ctk.CTkFrame(self, fg_color=COLORS["raised"], corner_radius=RADIUS)
        badge.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["md"]))

        ctk.CTkLabel(
            badge,
            text="Model",
            font=FONTS["small"],
            text_color=COLORS["subtext"],
        ).pack(side="left", padx=SPACING["sm"], pady=SPACING["sm"])

        ctk.CTkLabel(
            badge,
            text="Qwen2-VL 2B",
            font=FONTS["small"],
            text_color=COLORS["accent"],
        ).pack(side="right", padx=SPACING["sm"], pady=SPACING["sm"])

        # Interval badge
        interval_badge = ctk.CTkFrame(self, fg_color=COLORS["raised"], corner_radius=RADIUS)
        interval_badge.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["md"]))

        ctk.CTkLabel(
            interval_badge,
            text="Interval",
            font=FONTS["small"],
            text_color=COLORS["subtext"],
        ).pack(side="left", padx=SPACING["sm"], pady=SPACING["sm"])

        ctk.CTkLabel(
            interval_badge,
            text="20 s",
            font=FONTS["small"],
            text_color=COLORS["text"],
        ).pack(side="right", padx=SPACING["sm"], pady=SPACING["sm"])

    # ──────────────────────────────────────────────────────────────────

    def _toggle(self) -> None:
        if self._recording:
            self._on_stop()
        else:
            self._on_start()

    def set_recording(self, recording: bool) -> None:
        """Flip button text and colour to reflect recording state."""
        self._recording = recording
        if recording:
            self._btn.configure(
                text="Stop Recording",
                fg_color=COLORS["danger"],
                hover_color="#cc3530",
            )
        else:
            self._btn.configure(
                text="Start Recording",
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
            )

    def set_loading(self, loading: bool) -> None:
        """Disable button while the model is loading."""
        if loading:
            self._btn.configure(
                text="Loading model…",
                state="disabled",
                fg_color=COLORS["raised"],
            )
        else:
            self.set_recording(False)
            self._btn.configure(state="normal")

    def update_timer(self, elapsed_seconds: int) -> None:
        if self._timer_lbl:
            self._timer_lbl.configure(text=_fmt_duration(elapsed_seconds))
