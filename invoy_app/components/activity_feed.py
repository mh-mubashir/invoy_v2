"""
Invoy App — ActivityFeed component.

Scrollable live feed showing the most recent N activity descriptions
from the current session.  New entries are prepended; oldest are evicted
when the list exceeds MAX_ENTRIES.
"""

from __future__ import annotations

from datetime import datetime, timezone

import customtkinter as ctk

from invoy_app.styles.theme import COLORS, FONTS, SPACING, RADIUS, RADIUS_SM


MAX_ENTRIES = 12   # keep last N cards in the feed


class ActivityFeed(ctk.CTkFrame):
    """Live activity feed — shows the last N activity descriptions."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS,
            **kwargs,
        )
        self._cards: list[ctk.CTkFrame] = []
        self._build()

    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], 0))

        ctk.CTkLabel(
            header,
            text="Live Activity",
            font=FONTS["subheading"],
            text_color=COLORS["text"],
        ).pack(side="left")

        self._count_lbl = ctk.CTkLabel(
            header,
            text="0 frames",
            font=FONTS["small"],
            text_color=COLORS["subtext"],
        )
        self._count_lbl.pack(side="right")

        ctk.CTkFrame(
            self, fg_color=COLORS["border"], height=1, corner_radius=0
        ).pack(fill="x", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["sm"]))

        # Scrollable container
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=COLORS["raised"],
            scrollbar_button_hover_color=COLORS["border"],
            corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True, padx=SPACING["sm"], pady=(0, SPACING["sm"]))

    # ──────────────────────────────────────────────────────────────────

    def add_entry(self, activity_text: str, change_text: str, timestamp_iso: str) -> None:
        """
        Prepend a new ActivityCard and evict the oldest if over MAX_ENTRIES.

        Parameters
        ----------
        activity_text : str
            The activity description from the VLM.
        change_text : str
            The change description (may be empty string for the first frame).
        timestamp_iso : str
            ISO-8601 UTC timestamp.
        """
        # Format timestamp for display
        try:
            dt = datetime.fromisoformat(timestamp_iso)
            ts_display = dt.astimezone().strftime("%H:%M:%S")
        except Exception:
            ts_display = timestamp_iso[:8]

        card = ActivityCard(
            self._scroll,
            activity_text=activity_text,
            change_text=change_text,
            timestamp=ts_display,
        )
        card.pack(fill="x", pady=(0, SPACING["xs"]))

        # Move new card to the top of the scroll frame
        card.lift()
        for existing in self._cards:
            existing.pack_forget()
            existing.pack(fill="x", pady=(0, SPACING["xs"]))

        self._cards.insert(0, card)

        # Evict oldest
        while len(self._cards) > MAX_ENTRIES:
            oldest = self._cards.pop()
            oldest.destroy()

        # Update counter
        self._count_lbl.configure(text=f"{len(self._cards)} frame{'s' if len(self._cards) != 1 else ''}")

    def clear(self) -> None:
        for c in self._cards:
            c.destroy()
        self._cards.clear()
        self._count_lbl.configure(text="0 frames")


class ActivityCard(ctk.CTkFrame):
    """A single activity entry card with timestamp, activity text, and optional change text."""

    def __init__(
        self,
        master,
        activity_text: str,
        change_text: str,
        timestamp: str,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["raised"],
            corner_radius=RADIUS_SM,
            **kwargs,
        )
        self._build(activity_text, change_text, timestamp)

    def _build(self, activity_text: str, change_text: str, timestamp: str) -> None:
        # Accent left border effect via a narrow coloured frame
        accent_bar = ctk.CTkFrame(self, fg_color=COLORS["accent"], width=3, corner_radius=0)
        accent_bar.pack(side="left", fill="y", padx=(0, SPACING["sm"]))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, pady=SPACING["xs"])

        # Timestamp
        ctk.CTkLabel(
            content,
            text=timestamp,
            font=FONTS["tiny"],
            text_color=COLORS["subtext"],
            anchor="w",
        ).pack(anchor="w")

        # Activity text (truncated at display for brevity, full text in tooltip)
        display_text = activity_text if len(activity_text) <= 200 else activity_text[:197] + "…"
        ctk.CTkLabel(
            content,
            text=display_text,
            font=FONTS["body"],
            text_color=COLORS["text"],
            wraplength=420,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # Change text (if present and meaningful)
        if change_text and change_text.strip().lower() not in (
            "", "no significant change.", "no significant change"
        ):
            ctk.CTkLabel(
                content,
                text=f"↳ {change_text[:160]}",
                font=FONTS["small"],
                text_color=COLORS["subtext"],
                wraplength=420,
                justify="left",
                anchor="w",
            ).pack(anchor="w", pady=(2, SPACING["xs"]))
