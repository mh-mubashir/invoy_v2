"""
Invoy App — ActivityFeed component.

Full-width scrollable timeline of activity cards. Each card shows:
  • App-context chip (coloured dot + label derived from activity text)
  • Timestamp (right-aligned, same row as chip)
  • Full activity text — not truncated
  • Optional change note prefixed with ↳

New cards fade in from the top using a short opacity animation.

Empty state shows a countdown to the next capture.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Optional

import customtkinter as ctk

from invoy_app.styles.theme import (
    COLORS, FONTS, SPACING, RADIUS, CARD_PAD_X, CARD_PAD_Y, CARD_GAP,
)


# ── Context detection ──────────────────────────────────────────────────────

_CONTEXT_RULES: list[tuple[str, list[str], str]] = [
    # (label, keywords, color_key)
    ("VS Code",   ["vscode", "vs code", "visual studio", "code editor", "editor", ".py", ".ts", ".js", ".json", "function", "def ", "class ", "import "], "ctx_code"),
    ("Terminal",  ["terminal", "powershell", "bash", "shell", "command prompt", "cmd", "zsh", "fish", "npm", "pip ", "git "], "ctx_term"),
    ("Browser",   ["chrome", "firefox", "safari", "browser", "webpage", "website", "url", "http", "https", "google", "tab", "web"], "ctx_browser"),
]

def _detect_context(text: str) -> tuple[str, str]:
    """
    Parse activity text for app context.
    Tries the structured '[App] · [File] · [Action]' format first;
    falls back to keyword scan for legacy / unstructured output.
    Returns (display_label, color_hex).
    """
    # ── Structured format: use the App field directly ──────────────────
    if " · " in text:
        app_field = text.split(" · ")[0].strip().lower()
        for label, keywords, color_key in _CONTEXT_RULES:
            if any(kw in app_field for kw in keywords):
                return (label, COLORS[color_key])
        # App field present but didn't match a rule — use it as the label
        raw_label = text.split(" · ")[0].strip()
        return (raw_label[:20], COLORS["ctx_other"])

    # ── Fallback: keyword scan over full text ──────────────────────────
    lower = text.lower()
    scores: dict[str, int] = {}
    for label, keywords, color_key in _CONTEXT_RULES:
        scores[label] = sum(1 for kw in keywords if kw in lower)

    best_label = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best_label] == 0:
        return ("Desktop", COLORS["ctx_other"])

    for label, _, color_key in _CONTEXT_RULES:
        if label == best_label:
            return (label, COLORS[color_key])

    return ("Desktop", COLORS["ctx_other"])


# ── ActivityFeed ───────────────────────────────────────────────────────────

MAX_CARDS = 50   # keep last N cards; older ones are evicted to save memory

_SKIP_CHANGE = re.compile(
    r"^no significant change[\.\s]*$",
    re.IGNORECASE,
)


class ActivityFeed(ctk.CTkFrame):
    """Full-width timeline of activity cards for the Recording state."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(
            master,
            fg_color=COLORS["bg"],
            corner_radius=0,
            **kwargs,
        )
        self._cards: list[ActivityCard] = []
        self._empty_state_visible = True
        self._countdown_job: Optional[str] = None
        self._next_capture_secs = 0

        self._build()

    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Scrollable container — fills all available space
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg"],
            scrollbar_button_color=COLORS["elevated"],
            scrollbar_button_hover_color=COLORS["border"],
            corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["md"])
        self._scroll.columnconfigure(0, weight=1)

        # Empty state — shown until first card arrives
        self._empty_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._empty_frame.grid(row=0, column=0, pady=SPACING["xxl"])

        ctk.CTkLabel(
            self._empty_frame,
            text="Invoy is watching",
            font=FONTS["heading"],
            text_color=COLORS["subtext"],
        ).pack()

        self._countdown_lbl = ctk.CTkLabel(
            self._empty_frame,
            text="",
            font=FONTS["ui"],
            text_color=COLORS["muted"],
        )
        self._countdown_lbl.pack(pady=(SPACING["xs"], 0))

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def add_entry(
        self,
        activity_text: str,
        change_text: str,
        timestamp_iso: str,
    ) -> None:
        """Prepend a new ActivityCard with a fade-in animation."""
        if self._empty_state_visible:
            self._empty_frame.grid_forget()
            self._empty_state_visible = False

        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp_iso)
            ts_display = dt.astimezone().strftime("%H:%M")
        except Exception:
            ts_display = timestamp_iso[:5]

        # Detect context
        ctx_label, ctx_color = _detect_context(activity_text)

        # Normalise change text
        show_change = bool(change_text and not _SKIP_CHANGE.match(change_text.strip()))

        card = ActivityCard(
            self._scroll,
            activity_text=activity_text,
            change_text=change_text if show_change else "",
            timestamp=ts_display,
            ctx_label=ctx_label,
            ctx_color=ctx_color,
        )

        # Insert card at row 0 by shifting all existing cards down
        for existing in self._cards:
            info = existing.grid_info()
            if info:
                existing.grid(row=int(info["row"]) + 1, column=0, sticky="ew",
                               pady=(0, CARD_GAP))

        card.grid(row=0, column=0, sticky="ew", pady=(0, CARD_GAP))
        self._cards.insert(0, card)

        # Evict oldest
        while len(self._cards) > MAX_CARDS:
            old = self._cards.pop()
            old.destroy()

        # Fade in
        card.fade_in()

    def set_countdown(self, seconds: int) -> None:
        """Update the 'next capture in X s' label in the empty state."""
        self._next_capture_secs = seconds
        if self._empty_state_visible:
            if seconds > 0:
                self._countdown_lbl.configure(text=f"Next capture in {seconds} s")
            else:
                self._countdown_lbl.configure(text="Capturing…")

    def clear(self) -> None:
        for c in self._cards:
            c.destroy()
        self._cards.clear()
        self._empty_state_visible = True
        self._empty_frame.grid(row=0, column=0, pady=SPACING["xxl"])


# ── ActivityCard ───────────────────────────────────────────────────────────

class ActivityCard(ctk.CTkFrame):
    """
    A single activity entry.

    Layout:
      ┌────────────────────────────────────────────────────────────┐
      │  ● VS Code                                          10:43  │
      │                                                            │
      │  Full activity text, unwrapped, line-height 1.6            │
      │                                                            │
      │  ↳ Change note (if non-trivial)                            │
      └────────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        master,
        activity_text: str,
        change_text: str,
        timestamp: str,
        ctx_label: str,
        ctx_color: str,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS,
            **kwargs,
        )
        self._build(activity_text, change_text, timestamp, ctx_label, ctx_color)

    def _build(
        self,
        activity_text: str,
        change_text: str,
        timestamp: str,
        ctx_label: str,
        ctx_color: str,
    ) -> None:
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True,
                   padx=CARD_PAD_X, pady=CARD_PAD_Y)
        inner.columnconfigure(1, weight=1)

        # ── Row 0: context chip + timestamp ──────────────────────────
        meta_row = ctk.CTkFrame(inner, fg_color="transparent")
        meta_row.pack(fill="x")

        # Coloured dot
        dot = ctk.CTkLabel(
            meta_row,
            text="●",
            font=("Segoe UI", 9),
            text_color=ctx_color,
        )
        dot.pack(side="left", padx=(0, SPACING["xs"]))

        # Context label
        ctk.CTkLabel(
            meta_row,
            text=ctx_label,
            font=FONTS["timestamp"],
            text_color=COLORS["muted"],
        ).pack(side="left")

        # Timestamp right-aligned
        ctk.CTkLabel(
            meta_row,
            text=timestamp,
            font=FONTS["timestamp"],
            text_color=COLORS["muted"],
        ).pack(side="right")

        # ── Row 1: activity text ──────────────────────────────────────
        ctk.CTkLabel(
            inner,
            text=activity_text,
            font=FONTS["body"],
            text_color=COLORS["text"],
            wraplength=900,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(SPACING["sm"], 0))

        # ── Row 2: change note (optional) ────────────────────────────
        if change_text:
            ctk.CTkLabel(
                inner,
                text=f"↳  {change_text}",
                font=FONTS["ui"],
                text_color=COLORS["subtext"],
                wraplength=900,
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=(SPACING["xs"], 0))

    def fade_in(self) -> None:
        """Animate card from transparent to opaque over ~200 ms."""
        # customtkinter doesn't expose widget-level alpha, but we can approximate
        # by transitioning the fg_color from bg to surface colour over several steps.
        from invoy_app.components.header import _blend_hex
        steps = 8
        duration_ms = 200
        step_ms = duration_ms // steps

        def _step(i: int) -> None:
            if i > steps:
                self.configure(fg_color=COLORS["surface"])
                return
            alpha = i / steps
            blended = _blend_hex(COLORS["surface"], COLORS["bg"], alpha)
            self.configure(fg_color=blended)
            self.after(step_ms, lambda: _step(i + 1))

        _step(0)
