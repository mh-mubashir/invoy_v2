"""
Invoy App — HeaderBar component.

Full-width top bar:
  [Logo]  Invoy          ● Recording   ⚙
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable

import customtkinter as ctk
from PIL import Image

from invoy_app.styles.theme import COLORS, FONTS, SPACING, RADIUS


_LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo.png"


class HeaderBar(ctk.CTkFrame):
    """Full-width application header with logo, title, status indicator, and settings."""

    def __init__(
        self,
        master,
        on_settings: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=0,
            height=56,
            **kwargs,
        )
        self.pack_propagate(False)   # keep fixed height
        self._status_dot: Optional[ctk.CTkLabel] = None
        self._status_label: Optional[ctk.CTkLabel] = None

        self._build(on_settings)

    # ──────────────────────────────────────────────────────────────────

    def _build(self, on_settings: Callable[[], None]) -> None:
        pad = SPACING["md"]

        # Left group: logo + app name
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", padx=pad, pady=SPACING["sm"])

        # Logo image
        if _LOGO_PATH.exists():
            try:
                img = ctk.CTkImage(
                    light_image=Image.open(_LOGO_PATH),
                    dark_image=Image.open(_LOGO_PATH),
                    size=(32, 32),
                )
                ctk.CTkLabel(left, image=img, text="").pack(side="left", padx=(0, SPACING["sm"]))
            except Exception:
                pass  # logo load failure is non-fatal

        # App name
        ctk.CTkLabel(
            left,
            text="Invoy",
            font=FONTS["heading"],
            text_color=COLORS["text"],
        ).pack(side="left")

        # Right group: status dot + label + settings button
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=pad, pady=SPACING["sm"])

        # Settings gear
        ctk.CTkButton(
            right,
            text="⚙",
            width=36, height=36,
            corner_radius=RADIUS,
            fg_color="transparent",
            hover_color=COLORS["raised"],
            text_color=COLORS["subtext"],
            font=("Segoe UI", 16),
            command=on_settings,
        ).pack(side="right", padx=(SPACING["sm"], 0))

        # Status label
        self._status_label = ctk.CTkLabel(
            right,
            text="Idle",
            font=FONTS["small"],
            text_color=COLORS["subtext"],
        )
        self._status_label.pack(side="right", padx=SPACING["xs"])

        # Status dot
        self._status_dot = ctk.CTkLabel(
            right,
            text="●",
            font=("Segoe UI", 14),
            text_color=COLORS["subtext"],
        )
        self._status_dot.pack(side="right", padx=(0, SPACING["xs"]))

        # Separator line at the bottom
        ctk.CTkFrame(
            self,
            fg_color=COLORS["border"],
            height=1,
            corner_radius=0,
        ).pack(side="bottom", fill="x")

    # ──────────────────────────────────────────────────────────────────

    def set_status(self, state: str) -> None:
        """
        Update the status indicator.

        Parameters
        ----------
        state : "idle" | "loading" | "recording" | "error"
        """
        mapping = {
            "idle":      (COLORS["subtext"],  "Idle"),
            "loading":   ("#FFD60A",           "Loading model…"),
            "recording": (COLORS["success"],   "Recording"),
            "error":     (COLORS["danger"],    "Error"),
        }
        color, label = mapping.get(state, (COLORS["subtext"], state.capitalize()))
        if self._status_dot:
            self._status_dot.configure(text_color=color)
        if self._status_label:
            self._status_label.configure(text=label)
