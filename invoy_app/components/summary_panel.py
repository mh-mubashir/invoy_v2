"""
Invoy App — SummaryPanel component.

Left-column panel that lets the user trigger a Claude API summary of
the current session and displays the Markdown-formatted result.
"""

from __future__ import annotations

import itertools
from typing import Callable

import customtkinter as ctk

from invoy_app.styles.theme import COLORS, FONTS, SPACING, RADIUS, RADIUS_SM


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class SummaryPanel(ctk.CTkFrame):
    """
    Work summary panel.

    Parameters
    ----------
    master : widget
        Parent container.
    on_summarize : () -> None
        Called when the user clicks Generate Summary.
    """

    def __init__(
        self,
        master,
        on_summarize: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS,
            **kwargs,
        )
        self._on_summarize  = on_summarize
        self._spinner_iter  = itertools.cycle(_SPINNER_FRAMES)
        self._spinner_job   = None
        self._build()

    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Section title
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], 0))

        ctk.CTkLabel(
            header,
            text="Work Summary",
            font=FONTS["subheading"],
            text_color=COLORS["text"],
        ).pack(side="left")

        self._spinner_lbl = ctk.CTkLabel(
            header,
            text="",
            font=FONTS["body"],
            text_color=COLORS["subtext"],
        )
        self._spinner_lbl.pack(side="right")

        ctk.CTkFrame(
            self, fg_color=COLORS["border"], height=1, corner_radius=0
        ).pack(fill="x", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["sm"]))

        # Hint text
        self._hint_lbl = ctk.CTkLabel(
            self,
            text="Generates a categorised work log\nfrom the current session via Claude.",
            font=FONTS["small"],
            text_color=COLORS["subtext"],
            justify="left",
            wraplength=240,
            anchor="w",
        )
        self._hint_lbl.pack(anchor="w", padx=SPACING["md"], pady=(0, SPACING["sm"]))

        # Generate button
        self._gen_btn = ctk.CTkButton(
            self,
            text="Generate Summary",
            height=40,
            corner_radius=RADIUS,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"],
            font=FONTS["body_bold"],
            command=self._on_summarize,
        )
        self._gen_btn.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["sm"]))

        # Output text box (read-only)
        self._output = ctk.CTkTextbox(
            self,
            fg_color=COLORS["raised"],
            text_color=COLORS["text"],
            font=FONTS["small"],
            corner_radius=RADIUS_SM,
            wrap="word",
            state="disabled",
            scrollbar_button_color=COLORS["border"],
        )
        self._output.pack(fill="both", expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

    # ──────────────────────────────────────────────────────────────────

    def show_loading(self) -> None:
        """Disable button and start spinner."""
        self._gen_btn.configure(state="disabled", text="Generating…")
        self._start_spinner()
        self._set_output("", placeholder="Calling Claude API…")

    def show_result(self, text: str) -> None:
        """Display the summary text and re-enable the button."""
        self._stop_spinner()
        self._gen_btn.configure(state="normal", text="Generate Summary")
        self._set_output(text)

    def show_error(self, message: str) -> None:
        """Display an error message and re-enable the button."""
        self._stop_spinner()
        self._gen_btn.configure(state="normal", text="Generate Summary")
        self._set_output(f"Error: {message}", color=COLORS["danger"])

    def set_button_enabled(self, enabled: bool) -> None:
        """Enable or disable the Generate button (e.g. when no API key is set)."""
        state = "normal" if enabled else "disabled"
        self._gen_btn.configure(state=state)

    # ──────────────────────────────────────────────────────────────────

    def _set_output(self, text: str, placeholder: str = "", color: str = "") -> None:
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        content = text or placeholder
        self._output.insert("1.0", content)
        if color:
            self._output.configure(text_color=color)
        else:
            self._output.configure(text_color=COLORS["text"])
        self._output.configure(state="disabled")

    def _start_spinner(self) -> None:
        def _tick() -> None:
            self._spinner_lbl.configure(text=next(self._spinner_iter))
            self._spinner_job = self._spinner_lbl.after(100, _tick)
        _tick()

    def _stop_spinner(self) -> None:
        if self._spinner_job:
            self._spinner_lbl.after_cancel(self._spinner_job)
            self._spinner_job = None
        self._spinner_lbl.configure(text="")
