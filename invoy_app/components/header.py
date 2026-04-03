"""
Invoy App — HeaderBar component.

Three visual modes:
  idle      — wordmark + settings gear
  loading   — wordmark + amber pulse + "Loading model…" + settings gear
  recording — wordmark + red pulse + status string + "End Session →" + settings gear
  review    — wordmark + "← New Session" + view toggle + settings gear

The pulse dot is animated via a sine-approximated breathing cycle using
root.after() — no external animation library required.
"""

from __future__ import annotations

import math
import time
from typing import Callable, Optional

import customtkinter as ctk

from invoy_app.styles.theme import (
    COLORS, FONTS, SPACING, RADIUS_SM, HEADER_H,
)


class HeaderBar(ctk.CTkFrame):
    """Full-width application header — adapts to Idle / Recording / Review."""

    def __init__(
        self,
        master,
        on_settings: Callable[[], None],
        on_end_session: Optional[Callable[[], None]] = None,
        on_new_session: Optional[Callable[[], None]] = None,
        on_view_toggle: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["bg"],
            corner_radius=0,
            height=HEADER_H,
            **kwargs,
        )
        self.pack_propagate(False)

        self._on_settings    = on_settings
        self._on_end_session = on_end_session or (lambda: None)
        self._on_new_session = on_new_session or (lambda: None)
        self._on_view_toggle = on_view_toggle or (lambda v: None)

        self._mode            = "idle"
        self._pulse_job: Optional[str] = None
        self._pulse_start     = 0.0
        self._current_view    = "cards"   # "cards" or "list"

        # Widgets created in _build, referenced in _update_*
        self._dot_canvas:     Optional[ctk.CTkCanvas]  = None
        self._status_lbl:     Optional[ctk.CTkLabel]   = None
        self._end_btn:        Optional[ctk.CTkButton]  = None
        self._new_btn:        Optional[ctk.CTkButton]  = None
        self._toggle_cards:   Optional[ctk.CTkButton]  = None
        self._toggle_list:    Optional[ctk.CTkButton]  = None
        self._centre_frame:   Optional[ctk.CTkFrame]   = None

        self._build()

    # ──────────────────────────────────────────────────────────────────
    # Build
    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        pad = SPACING["lg"]

        # ── Left: wordmark ────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", padx=pad)

        ctk.CTkLabel(
            left,
            text="Invoy",
            font=FONTS["wordmark"],
            text_color=COLORS["text"],
        ).pack(side="left")

        # "← New Session" button — hidden until review mode
        self._new_btn = ctk.CTkButton(
            left,
            text="← New Session",
            font=FONTS["status"],
            text_color=COLORS["muted"],
            fg_color="transparent",
            hover_color=COLORS["elevated"],
            corner_radius=RADIUS_SM,
            height=28,
            width=110,
            command=self._on_new_session,
        )
        # not packed yet — shown in review mode

        # ── Centre: status area ───────────────────────────────────────
        self._centre_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._centre_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Pulse dot drawn on a tiny canvas so we can change its colour
        # programmatically without re-creating the widget.
        dot_size = 20   # canvas size; dot drawn centred
        self._dot_canvas = ctk.CTkCanvas(
            self._centre_frame,
            width=dot_size, height=dot_size,
            bg=COLORS["bg"],
            highlightthickness=0,
        )
        # dot drawn lazily in _set_dot_color

        self._status_lbl = ctk.CTkLabel(
            self._centre_frame,
            text="",
            font=FONTS["status"],
            text_color=COLORS["subtext"],
        )
        # both packed when mode changes

        # ── Right: action buttons + settings ─────────────────────────
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=pad)

        # Settings gear
        self._settings_btn = ctk.CTkButton(
            right,
            text="⚙",
            width=32, height=32,
            corner_radius=RADIUS_SM,
            fg_color="transparent",
            hover_color=COLORS["elevated"],
            text_color=COLORS["muted"],
            font=("Segoe UI", 15),
            command=self._on_settings,
        )
        self._settings_btn.pack(side="right", padx=(SPACING["xs"], 0))

        # "End Session →" — hidden until recording mode
        self._end_btn = ctk.CTkButton(
            right,
            text="End Session →",
            font=FONTS["status"],
            text_color=COLORS["muted"],
            fg_color="transparent",
            hover_color=COLORS["elevated"],
            corner_radius=RADIUS_SM,
            height=28,
            width=100,
            command=self._on_end_session,
        )

        # View toggle buttons — hidden until review mode
        toggle_frame = ctk.CTkFrame(right, fg_color=COLORS["elevated"], corner_radius=RADIUS_SM)
        self._toggle_frame = toggle_frame

        self._toggle_cards = ctk.CTkButton(
            toggle_frame,
            text="▦",
            width=28, height=26,
            corner_radius=RADIUS_SM,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            font=("Segoe UI", 13),
            command=lambda: self._switch_view("cards"),
        )
        self._toggle_cards.grid(row=0, column=0, padx=2, pady=2)

        self._toggle_list = ctk.CTkButton(
            toggle_frame,
            text="≡",
            width=28, height=26,
            corner_radius=RADIUS_SM,
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["subtext"],
            font=("Segoe UI", 14),
            command=lambda: self._switch_view("list"),
        )
        self._toggle_list.grid(row=0, column=1, padx=2, pady=2)

        # Hairline separator at the bottom
        ctk.CTkFrame(
            self, fg_color=COLORS["border"], height=1, corner_radius=0,
        ).pack(side="bottom", fill="x")

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        """
        Switch header visual mode.

        mode: "idle" | "loading" | "recording" | "review"
        """
        self._stop_pulse()
        self._mode = mode

        # Clear centre frame
        for w in self._centre_frame.winfo_children():
            w.pack_forget()

        # Hide all right-side contextual buttons first
        self._end_btn.pack_forget()
        self._toggle_frame.pack_forget()
        self._new_btn.pack_forget()

        if mode == "idle":
            pass   # clean header — wordmark + settings only

        elif mode == "loading":
            self._set_dot_color(COLORS["loading"])
            self._dot_canvas.pack(side="left", padx=(0, SPACING["xs"]))
            self._status_lbl.configure(text="Loading model…", text_color=COLORS["subtext"])
            self._status_lbl.pack(side="left")
            self._start_pulse(COLORS["loading"])

        elif mode == "recording":
            self._set_dot_color(COLORS["recording"])
            self._dot_canvas.pack(side="left", padx=(0, SPACING["xs"]))
            self._status_lbl.configure(text="Recording", text_color=COLORS["subtext"])
            self._status_lbl.pack(side="left")
            self._start_pulse(COLORS["recording"])
            self._end_btn.pack(side="right", padx=(0, SPACING["sm"]))

        elif mode == "review":
            self._status_lbl.configure(text="", text_color=COLORS["subtext"])
            self._new_btn.pack(side="left", padx=(SPACING["sm"], 0))
            self._toggle_frame.pack(side="right", padx=(0, SPACING["sm"]))

    def update_status(self, text: str) -> None:
        """Update the status string text (e.g. timer + countdown)."""
        if self._status_lbl:
            self._status_lbl.configure(text=text)

    # ──────────────────────────────────────────────────────────────────
    # Pulse animation
    # ──────────────────────────────────────────────────────────────────

    def _set_dot_color(self, hex_color: str) -> None:
        """Draw a 6px filled circle on the dot canvas in the given colour."""
        c = self._dot_canvas
        c.delete("all")
        # Canvas is 20×20; draw a 6px dot centred at (10,10)
        c.create_oval(7, 7, 13, 13, fill=hex_color, outline="")

    def _start_pulse(self, base_color: str) -> None:
        self._pulse_start  = time.monotonic()
        self._pulse_color  = base_color
        self._pulse_tick()

    def _pulse_tick(self) -> None:
        if self._mode not in ("loading", "recording"):
            return
        # Sine wave: period 2 s, opacity oscillates between 0.35 and 1.0
        elapsed = time.monotonic() - self._pulse_start
        alpha   = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(math.pi * elapsed))
        # Blend the dot colour with the bg colour using alpha
        dot_hex = _blend_hex(self._pulse_color, COLORS["bg"], alpha)
        self._set_dot_color(dot_hex)
        self._pulse_job = self._dot_canvas.after(50, self._pulse_tick)

    def _stop_pulse(self) -> None:
        if self._pulse_job:
            try:
                self._dot_canvas.after_cancel(self._pulse_job)
            except Exception:
                pass
        self._pulse_job = None

    # ──────────────────────────────────────────────────────────────────
    # View toggle
    # ──────────────────────────────────────────────────────────────────

    def _switch_view(self, view: str) -> None:
        self._current_view = view
        if view == "cards":
            self._toggle_cards.configure(fg_color=COLORS["accent"], text_color=COLORS["text"])
            self._toggle_list.configure(fg_color="transparent", text_color=COLORS["subtext"])
        else:
            self._toggle_list.configure(fg_color=COLORS["accent"], text_color=COLORS["text"])
            self._toggle_cards.configure(fg_color="transparent", text_color=COLORS["subtext"])
        self._on_view_toggle(view)


# ── Colour utilities ───────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _blend_hex(fg: str, bg: str, alpha: float) -> str:
    """Linearly blend fg over bg at opacity alpha → '#rrggbb'."""
    fr, fg_, fb = _hex_to_rgb(fg)
    br, bg_, bb = _hex_to_rgb(bg)
    r = int(fr * alpha + br * (1 - alpha))
    g = int(fg_ * alpha + bg_ * (1 - alpha))
    b = int(fb * alpha + bb * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"
