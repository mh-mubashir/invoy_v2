"""
Invoy App — SummaryPanel component.

Shown in the Review state. Parses Claude's Markdown output into structured
CategoryCard widgets and renders a distribution bar at the bottom.

States:
  empty     — "Generate Work Summary" button + soft prompt text
  loading   — button disabled + braille spinner
  result    — category cards grid + distribution bar + "Regenerate →" button
  error     — error message + retry button
"""

from __future__ import annotations

import itertools
import re
from typing import Callable

import customtkinter as ctk

from invoy_app.styles.theme import (
    COLORS, FONTS, SPACING, RADIUS, RADIUS_SM, RADIUS_XS,
)

# Braille spinner frames
_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Cycling palette for category distribution bar
_DIST_COLORS = [
    COLORS["ctx_code"],
    COLORS["ctx_browser"],
    COLORS["ctx_term"],
    COLORS["accent"],
    "#F59E0B",   # amber
    "#EC4899",   # pink
]


# ── SummaryPanel ───────────────────────────────────────────────────────────

class SummaryPanel(ctk.CTkFrame):
    """
    Review-state panel: structured work summary cards + distribution bar.

    Parameters
    ----------
    master : widget
    on_generate : () -> None
        Called when the user clicks Generate / Regenerate.
    recording_active : bool
        If True, shows "end your session first" message instead of the button.
    """

    def __init__(
        self,
        master,
        on_generate: Callable[[], None],
        recording_active: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["bg"],
            corner_radius=0,
            **kwargs,
        )
        self._on_generate      = on_generate
        self._recording_active = recording_active
        self._spinner_iter     = itertools.cycle(_SPINNER)
        self._spinner_job      = None
        self._categories: list[dict] = []

        self._build()

    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Scrollable outer container
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg"],
            scrollbar_button_color=COLORS["elevated"],
            scrollbar_button_hover_color=COLORS["border"],
            corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True,
                          padx=SPACING["lg"], pady=SPACING["md"])
        self._scroll.columnconfigure(0, weight=1)
        self._scroll.columnconfigure(1, weight=1)

        # Top action bar (always visible)
        self._action_bar = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._action_bar.grid(row=0, column=0, columnspan=2, sticky="ew",
                              pady=(0, SPACING["lg"]))
        self._action_bar.columnconfigure(0, weight=1)

        self._gen_btn = ctk.CTkButton(
            self._action_bar,
            text="Generate Work Summary",
            font=FONTS["body_bold"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            height=48,
            corner_radius=RADIUS,
            command=self._on_generate,
        )
        self._gen_btn.grid(row=0, column=0, sticky="ew")

        # Spinner label (beside button when loading)
        self._spinner_lbl = ctk.CTkLabel(
            self._action_bar,
            text="",
            font=FONTS["body"],
            text_color=COLORS["muted"],
            width=28,
        )
        self._spinner_lbl.grid(row=0, column=1, padx=(SPACING["sm"], 0))

        # Soft prompt below button
        if self._recording_active:
            msg = "End your session to generate a work summary."
        else:
            msg = "Summarise your session into categories of work."
        self._prompt_lbl = ctk.CTkLabel(
            self._scroll,
            text=msg,
            font=FONTS["ui"],
            text_color=COLORS["muted"],
            justify="left",
            anchor="w",
        )
        self._prompt_lbl.grid(row=1, column=0, columnspan=2, sticky="w",
                              pady=(0, SPACING["xl"]))

        # Placeholder for category cards (populated in show_result)
        self._cards_start_row = 2
        self._dist_bar: ctk.CTkFrame | None = None

    # ──────────────────────────────────────────────────────────────────
    # State transitions
    # ──────────────────────────────────────────────────────────────────

    def show_loading(self) -> None:
        self._clear_cards()
        self._gen_btn.configure(state="disabled", text="Generating…",
                                fg_color=COLORS["elevated"], text_color=COLORS["muted"])
        self._prompt_lbl.configure(text="")
        self._start_spinner()

    def show_result(self, markdown_text: str) -> None:
        self._stop_spinner()
        self._clear_cards()
        self._categories = _parse_markdown(markdown_text)

        if not self._categories:
            self.show_error("Could not parse the summary. Raw text:\n\n" + markdown_text[:400])
            return

        self._gen_btn.configure(
            state="normal",
            text="Regenerate →",
            fg_color="transparent",
            hover_color=COLORS["elevated"],
            text_color=COLORS["subtext"],
        )
        self._prompt_lbl.configure(text="")

        # Render category cards in a 2-column grid
        for i, cat in enumerate(self._categories):
            row = self._cards_start_row + (i // 2)
            col = i % 2
            card = CategoryCard(self._scroll, category=cat,
                                color=_DIST_COLORS[i % len(_DIST_COLORS)])
            card.grid(row=row, column=col, sticky="nsew",
                      padx=(0 if col == 0 else SPACING["sm"] // 2, 0),
                      pady=(0, SPACING["sm"]))

        # Distribution bar
        total = sum(max(1, len(c["bullets"])) for c in self._categories)
        bar_row = self._cards_start_row + ((len(self._categories) + 1) // 2)
        self._dist_bar = _DistributionBar(
            self._scroll,
            categories=self._categories,
            weights=[len(c["bullets"]) / total for c in self._categories],
            colors=[_DIST_COLORS[i % len(_DIST_COLORS)] for i in range(len(self._categories))],
        )
        self._dist_bar.grid(row=bar_row, column=0, columnspan=2, sticky="ew",
                            pady=(SPACING["md"], 0))

    def show_error(self, message: str) -> None:
        self._stop_spinner()
        self._clear_cards()
        self._gen_btn.configure(state="normal", text="Generate Work Summary",
                                fg_color=COLORS["accent"], text_color=COLORS["text"])
        self._prompt_lbl.configure(
            text=f"Error: {message[:200]}",
            text_color=COLORS["danger"],
        )

    def set_button_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._gen_btn.configure(state=state)

    # ──────────────────────────────────────────────────────────────────

    def _clear_cards(self) -> None:
        for w in self._scroll.winfo_children():
            info = w.grid_info()
            if info and int(info.get("row", 0)) >= self._cards_start_row:
                w.destroy()
        self._dist_bar = None

    def _start_spinner(self) -> None:
        def _tick() -> None:
            self._spinner_lbl.configure(text=next(self._spinner_iter))
            self._spinner_job = self._spinner_lbl.after(100, _tick)
        _tick()

    def _stop_spinner(self) -> None:
        if self._spinner_job:
            try:
                self._spinner_lbl.after_cancel(self._spinner_job)
            except Exception:
                pass
        self._spinner_job = None
        self._spinner_lbl.configure(text="")


# ── CategoryCard ───────────────────────────────────────────────────────────

class CategoryCard(ctk.CTkFrame):
    """
    A single work category rendered as a card.

    ┌──────────────────────────────────────────────────┐
    │  ▌ CODE REVIEW                        ~34 min    │
    │    Reviewed 3 PRs in the invoy repo               │
    │    Left inline comments on recorder.py            │
    │    Approved the paper metrics PR                  │
    └──────────────────────────────────────────────────┘
    """

    def __init__(self, master, category: dict, color: str, **kwargs) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS,
            **kwargs,
        )
        self._build(category, color)

    def _build(self, category: dict, color: str) -> None:
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True,
                   padx=SPACING["md"], pady=SPACING["md"])

        # Header row: colour accent bar + title + duration
        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill="x")

        # Small colour accent bar
        ctk.CTkFrame(
            header,
            fg_color=color,
            width=3,
            height=16,
            corner_radius=RADIUS_XS,
        ).pack(side="left", padx=(0, SPACING["sm"]))

        ctk.CTkLabel(
            header,
            text=category["title"].upper(),
            font=FONTS["ui_bold"],
            text_color=COLORS["subtext"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        if category.get("duration"):
            ctk.CTkLabel(
                header,
                text=category["duration"],
                font=FONTS["small"],
                text_color=COLORS["muted"],
            ).pack(side="right")

        # Bullets
        for bullet in category["bullets"]:
            ctk.CTkLabel(
                inner,
                text=bullet,
                font=FONTS["ui"],
                text_color=COLORS["text"],
                wraplength=380,
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=(SPACING["xs"], 0))


# ── Distribution bar ───────────────────────────────────────────────────────

class _DistributionBar(ctk.CTkFrame):
    """Proportional coloured blocks showing session time per category."""

    def __init__(
        self,
        master,
        categories: list[dict],
        weights: list[float],
        colors: list[str],
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", height=20, **kwargs)
        self.pack_propagate(False)
        self._build(categories, weights, colors)

    def _build(
        self,
        categories: list[dict],
        weights: list[float],
        colors: list[str],
    ) -> None:
        bar_frame = ctk.CTkFrame(self, fg_color=COLORS["elevated"],
                                 corner_radius=RADIUS_SM, height=6)
        bar_frame.pack(fill="x", pady=(SPACING["xs"], 0))
        bar_frame.pack_propagate(False)

        for i, (w, color) in enumerate(zip(weights, colors)):
            is_last = i == len(weights) - 1
            radius = RADIUS_SM if is_last else 0
            seg = ctk.CTkFrame(
                bar_frame,
                fg_color=color,
                corner_radius=radius,
                height=6,
            )
            seg.pack(side="left", fill="y",
                     expand=False,
                     ipadx=0, ipady=0)
            # Force width by relwidth
            seg.place_forget()  # use pack with relwidth via a trick

        # Rebuild with place for proportional widths
        for w in bar_frame.winfo_children():
            w.destroy()

        for i, (wt, color) in enumerate(zip(weights, colors)):
            seg = ctk.CTkFrame(
                bar_frame,
                fg_color=color,
                corner_radius=RADIUS_XS,
                height=6,
            )
            seg.place(relx=sum(weights[:i]), rely=0, relwidth=wt, relheight=1.0)


# ── Markdown parser ────────────────────────────────────────────────────────

_DURATION_PAT = re.compile(r"~\s*\d+\s*(?:min|h|hour|minute)", re.IGNORECASE)


def _parse_markdown(text: str) -> list[dict]:
    """
    Parse Claude's ## Category output into a list of dicts:
      {title, bullets: [str], duration: str | None}
    """
    categories: list[dict] = []
    current: dict | None   = None

    for line in text.splitlines():
        line = line.strip()

        if line.startswith("## "):
            if current:
                categories.append(current)
            title = line[3:].strip()
            # Extract duration from title if present e.g. "## Code Review (~34 min)"
            dur_match = _DURATION_PAT.search(title)
            duration = dur_match.group(0) if dur_match else None
            clean_title = _DURATION_PAT.sub("", title).strip(" ()")
            current = {"title": clean_title, "bullets": [], "duration": duration}

        elif current and line.startswith("- "):
            bullet = line[2:].strip()
            if bullet:
                current["bullets"].append(bullet)

        elif current and line.startswith("* "):
            bullet = line[2:].strip()
            if bullet:
                current["bullets"].append(bullet)

    if current:
        categories.append(current)

    # Filter out empty categories
    return [c for c in categories if c["bullets"]]
