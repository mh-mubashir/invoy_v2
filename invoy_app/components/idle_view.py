"""
Invoy App — IdleView component.

Shown when no session is active. Full-window centred layout:

  ┌─────────────────────────────────────────────────────────┐
  │                                                         │
  │                      Invoy                             │
  │             Your private work journal                  │
  │                                                         │
  │               [ Begin Session ]                        │
  │            Qwen2-VL 2B · every 20 s                    │
  │                                                         │
  │   ─────────────────────────────────────────────────    │
  │   Earlier today                                        │
  │   ● 2 h 14 m  Coding, research, code review  10:30    │
  │   ● 45 min    Documentation, browser research  08:12  │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

import customtkinter as ctk

from invoy_app.styles.theme import (
    COLORS, FONTS, SPACING, RADIUS, RADIUS_SM,
)


class IdleView(ctk.CTkFrame):
    """
    Full-screen idle state — centred Begin Session CTA + optional session history.

    Parameters
    ----------
    master : widget
    on_begin : () -> None
        Called when the user clicks Begin Session.
    on_open_session : (session_id: str) -> None
        Called when the user clicks a past session row.
    model_label : str
        Short model name to display below the button.
    interval_seconds : float
        Capture interval shown below the button.
    """

    def __init__(
        self,
        master,
        on_begin: Callable[[], None],
        on_open_session: Optional[Callable[[str], None]] = None,
        model_label: str = "Qwen2-VL 2B",
        interval_seconds: float = 20.0,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["bg"],
            corner_radius=0,
            **kwargs,
        )
        self._on_begin       = on_begin
        self._on_open_session = on_open_session or (lambda sid: None)
        self._model_label    = model_label
        self._interval       = interval_seconds

        self._build()

    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Outer frame to handle vertical centering
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        centre = ctk.CTkFrame(self, fg_color="transparent")
        centre.grid(row=0, column=0)

        # ── Hero section ──────────────────────────────────────────────
        hero = ctk.CTkFrame(centre, fg_color="transparent")
        hero.pack(pady=(0, SPACING["xl"]))

        ctk.CTkLabel(
            hero,
            text="Invoy",
            font=FONTS["display"],
            text_color=COLORS["text"],
        ).pack()

        ctk.CTkLabel(
            hero,
            text="Your private work journal",
            font=FONTS["ui"],
            text_color=COLORS["subtext"],
        ).pack(pady=(SPACING["xs"], 0))

        # ── CTA ───────────────────────────────────────────────────────
        cta = ctk.CTkFrame(centre, fg_color="transparent")
        cta.pack(pady=(0, SPACING["xl"]))

        self._begin_btn = ctk.CTkButton(
            cta,
            text="Begin Session",
            font=FONTS["body_bold"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            width=240,
            height=52,
            corner_radius=RADIUS,
            command=self._on_begin,
        )
        self._begin_btn.pack()

        ctk.CTkLabel(
            cta,
            text=f"{self._model_label}  ·  every {int(self._interval)} s",
            font=FONTS["small"],
            text_color=COLORS["muted"],
        ).pack(pady=(SPACING["sm"], 0))

        # ── History section (populated by load_history) ───────────────
        self._history_frame = ctk.CTkFrame(centre, fg_color="transparent")
        # packed only if history exists

    # ──────────────────────────────────────────────────────────────────

    def set_loading(self, loading: bool) -> None:
        """Disable/enable the begin button during model load."""
        if loading:
            self._begin_btn.configure(
                state="disabled",
                text="Loading…",
                fg_color=COLORS["elevated"],
                text_color=COLORS["muted"],
            )
        else:
            self._begin_btn.configure(
                state="normal",
                text="Begin Session",
                fg_color=COLORS["accent"],
                text_color=COLORS["text"],
            )

    def load_history(self, sessions: list[dict]) -> None:
        """
        Populate the session history list below the CTA.

        Each session dict should have:
          session_id, start_time (ISO str), duration_s (int), summary_snippet (str)
        """
        # Clear previous
        for w in self._history_frame.winfo_children():
            w.destroy()

        if not sessions:
            return

        # Separator
        ctk.CTkFrame(
            self._history_frame,
            fg_color=COLORS["border"],
            height=1,
            corner_radius=0,
        ).pack(fill="x", pady=(0, SPACING["md"]))

        ctk.CTkLabel(
            self._history_frame,
            text="Earlier today",
            font=FONTS["small"],
            text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(0, SPACING["sm"]))

        for s in sessions[:5]:   # cap at 5 rows
            row = _SessionRow(
                self._history_frame,
                session=s,
                on_click=lambda sid=s.get("session_id", ""): self._on_open_session(sid),
            )
            row.pack(fill="x", pady=(0, SPACING["xs"]))

        self._history_frame.pack(pady=(0, SPACING["xl"]))


class _SessionRow(ctk.CTkFrame):
    """A single past-session row in the idle history list."""

    def __init__(self, master, session: dict, on_click: Callable[[], None], **kwargs) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS_SM,
            cursor="hand2",
            **kwargs,
        )
        self._build(session, on_click)

        # Make the whole row clickable
        self.bind("<Button-1>", lambda e: on_click())
        for child in self.winfo_children():
            child.bind("<Button-1>", lambda e: on_click())

        # Hover effect
        self.bind("<Enter>", lambda e: self.configure(fg_color=COLORS["elevated"]))
        self.bind("<Leave>", lambda e: self.configure(fg_color=COLORS["surface"]))

    def _build(self, session: dict, on_click: Callable) -> None:
        pad = SPACING["md"]

        # Duration pill
        dur_s = session.get("duration_s", 0)
        dur_str = _format_duration(dur_s)

        pill = ctk.CTkLabel(
            self,
            text=dur_str,
            font=FONTS["small"],
            text_color=COLORS["accent"],
            fg_color=COLORS["elevated"],
            corner_radius=RADIUS_SM,
            padx=SPACING["sm"],
            pady=2,
        )
        pill.pack(side="left", padx=(pad, SPACING["sm"]), pady=SPACING["sm"])

        # Summary snippet
        snippet = session.get("summary_snippet") or "No summary"
        if len(snippet) > 60:
            snippet = snippet[:57] + "…"
        ctk.CTkLabel(
            self,
            text=snippet,
            font=FONTS["ui"],
            text_color=COLORS["subtext"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Time-ago string
        start_raw = session.get("start_time", "")
        time_str = _time_ago(start_raw)
        ctk.CTkLabel(
            self,
            text=time_str,
            font=FONTS["timestamp"],
            text_color=COLORS["muted"],
            anchor="e",
        ).pack(side="right", padx=(0, pad))


# ── Utilities ──────────────────────────────────────────────────────────────

def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} s"
    m = seconds // 60
    h = m // 60
    m = m % 60
    if h:
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{m} min"


def _time_ago(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        delta = int((now - dt.astimezone(timezone.utc)).total_seconds())
        if delta < 60:
            return "just now"
        if delta < 3600:
            return f"{delta // 60} min ago"
        return f"{delta // 3600} h ago"
    except Exception:
        return ""
