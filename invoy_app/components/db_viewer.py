"""
Invoy App — DatabaseViewer component.

Embedded table viewer showing recent entries from all sessions in the
SQLite database.  Renders as a CTkScrollableFrame grid.

Columns displayed:
  Time  |  Activity (truncated)  |  Change  |  Inference ms
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import customtkinter as ctk

from invoy_app.styles.theme import COLORS, FONTS, SPACING, RADIUS, RADIUS_SM


_COLS = ["Time", "Activity", "Change", "ms"]
_COL_WIDTHS = [80, 320, 200, 55]
_TRUNCATE_ACTIVITY = 90
_TRUNCATE_CHANGE   = 60


class DatabaseViewer(ctk.CTkFrame):
    """
    Scrollable table of recent SQLite activity log entries.

    Parameters
    ----------
    master : widget
        Parent widget.
    get_entries : () -> list[dict]
        Callable that returns a list of row dicts from the activity log.
        Called on each Refresh.
    """

    def __init__(
        self,
        master,
        get_entries: Callable[[], list[dict]],
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS,
            **kwargs,
        )
        self._get_entries = get_entries
        self._build()

    # ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header row
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACING["md"], pady=(SPACING["md"], 0))

        ctk.CTkLabel(
            header,
            text="Activity Database",
            font=FONTS["subheading"],
            text_color=COLORS["text"],
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Refresh",
            width=70, height=28,
            corner_radius=RADIUS_SM,
            fg_color=COLORS["raised"],
            hover_color=COLORS["border"],
            text_color=COLORS["subtext"],
            font=FONTS["small"],
            command=self.refresh,
        ).pack(side="right")

        ctk.CTkFrame(
            self, fg_color=COLORS["border"], height=1, corner_radius=0
        ).pack(fill="x", padx=SPACING["md"], pady=(SPACING["xs"], SPACING["sm"]))

        # Column headers
        col_header = ctk.CTkFrame(self, fg_color="transparent")
        col_header.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["xs"]))
        for i, (col, w) in enumerate(zip(_COLS, _COL_WIDTHS)):
            ctk.CTkLabel(
                col_header,
                text=col,
                font=FONTS["small"],
                text_color=COLORS["subtext"],
                width=w,
                anchor="w",
            ).grid(row=0, column=i, padx=(0, SPACING["xs"]))

        # Scrollable body
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=COLORS["raised"],
            scrollbar_button_hover_color=COLORS["border"],
            corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True, padx=SPACING["sm"], pady=(0, SPACING["sm"]))

        self._row_count_lbl = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["tiny"],
            text_color=COLORS["subtext"],
        )
        self._row_count_lbl.pack(anchor="e", padx=SPACING["md"], pady=(0, SPACING["sm"]))

    # ──────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload entries from the database and re-render the table."""
        # Clear old rows
        for widget in self._scroll.winfo_children():
            widget.destroy()

        entries = self._get_entries()

        for i, entry in enumerate(entries):
            bg = COLORS["raised"] if i % 2 == 0 else COLORS["surface"]
            row_frame = ctk.CTkFrame(
                self._scroll,
                fg_color=bg,
                corner_radius=RADIUS_SM,
                height=28,
            )
            row_frame.pack(fill="x", pady=(0, 2))
            row_frame.pack_propagate(False)

            # ── Time ─────────────────────────────────────────────────
            ts_raw = entry.get("timestamp") or entry.get("created_at") or ""
            try:
                dt = datetime.fromisoformat(ts_raw)
                ts_display = dt.astimezone().strftime("%d/%m %H:%M")
            except Exception:
                ts_display = ts_raw[:16]

            ctk.CTkLabel(
                row_frame,
                text=ts_display,
                font=FONTS["tiny"],
                text_color=COLORS["subtext"],
                width=_COL_WIDTHS[0],
                anchor="w",
            ).grid(row=0, column=0, padx=(SPACING["sm"], SPACING["xs"]), pady=2, sticky="w")

            # ── Activity ─────────────────────────────────────────────
            activity = (entry.get("activity") or entry.get("activity_text") or "—").strip()
            if len(activity) > _TRUNCATE_ACTIVITY:
                activity = activity[:_TRUNCATE_ACTIVITY - 1] + "…"

            ctk.CTkLabel(
                row_frame,
                text=activity,
                font=FONTS["tiny"],
                text_color=COLORS["text"],
                width=_COL_WIDTHS[1],
                anchor="w",
            ).grid(row=0, column=1, padx=(0, SPACING["xs"]), pady=2, sticky="w")

            # ── Change ───────────────────────────────────────────────
            change = (entry.get("change_summary") or "").strip()
            if len(change) > _TRUNCATE_CHANGE:
                change = change[:_TRUNCATE_CHANGE - 1] + "…"

            ctk.CTkLabel(
                row_frame,
                text=change,
                font=FONTS["tiny"],
                text_color=COLORS["subtext"],
                width=_COL_WIDTHS[2],
                anchor="w",
            ).grid(row=0, column=2, padx=(0, SPACING["xs"]), pady=2, sticky="w")

            # ── Inference ms ─────────────────────────────────────────
            ms_raw = entry.get("activity_inference_ms") or 0
            ms_str = f"{int(ms_raw):,}" if ms_raw else "—"

            ctk.CTkLabel(
                row_frame,
                text=ms_str,
                font=FONTS["tiny"],
                text_color=COLORS["subtext"],
                width=_COL_WIDTHS[3],
                anchor="e",
            ).grid(row=0, column=3, padx=(0, SPACING["sm"]), pady=2, sticky="e")

        n = len(entries)
        self._row_count_lbl.configure(text=f"{n} row{'s' if n != 1 else ''}")
