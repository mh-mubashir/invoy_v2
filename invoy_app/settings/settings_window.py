"""
Invoy App — Settings window (CTkToplevel).

Fields:
  • Claude API key  (masked, show/hide toggle)
  • Database path   (text entry + browse button)
  • Screenshot dir  (text entry + browse button)
  • Capture interval (seconds)
  • Appearance mode (Dark / Light / System)
  • Notifications   (on / off)
"""

from __future__ import annotations

import tkinter as tk
import tkinter.filedialog as filedialog
from typing import Callable

import customtkinter as ctk

from invoy_app.settings.config import AppConfig
from invoy_app.styles.theme import COLORS, FONTS, RADIUS, SPACING


class SettingsWindow(ctk.CTkToplevel):
    """Modal-style settings window that overlays the main app."""

    def __init__(
        self,
        master: ctk.CTk,
        config: AppConfig,
        on_save: Callable[[AppConfig], None],
    ) -> None:
        super().__init__(master)
        self._config = config
        self._on_save = on_save
        self._show_key = False

        self.title("Invoy — Settings")
        self.geometry("500x540")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["surface"])
        self.grab_set()   # make modal
        self.focus_set()

        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        pad = SPACING["md"]

        # Title
        ctk.CTkLabel(
            self, text="Settings",
            font=FONTS["heading"], text_color=COLORS["text"],
        ).pack(anchor="w", padx=pad, pady=(pad, SPACING["sm"]))

        # ---- Claude API key ----------------------------------------
        self._section("Claude API Key")
        key_row = ctk.CTkFrame(self, fg_color="transparent")
        key_row.pack(fill="x", padx=pad, pady=(0, SPACING["sm"]))
        key_row.columnconfigure(0, weight=1)

        self._key_var = tk.StringVar(value=self._config.claude_api_key)
        self._key_entry = ctk.CTkEntry(
            key_row, textvariable=self._key_var, show="*",
            fg_color=COLORS["raised"], border_color=COLORS["border"],
            text_color=COLORS["text"], font=FONTS["mono"],
            corner_radius=RADIUS,
        )
        self._key_entry.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        self._eye_btn = ctk.CTkButton(
            key_row, text="Show", width=60,
            fg_color=COLORS["raised"], hover_color=COLORS["border"],
            text_color=COLORS["subtext"], font=FONTS["small"],
            corner_radius=RADIUS, command=self._toggle_key_visibility,
        )
        self._eye_btn.grid(row=0, column=1)

        # ---- DB path -----------------------------------------------
        self._section("Database Path")
        self._db_var = tk.StringVar(value=self._config.db_path)
        self._path_row(self._db_var, self._browse_db)

        # ---- Screenshot dir ----------------------------------------
        self._section("Screenshot Directory")
        self._ss_var = tk.StringVar(value=self._config.screenshot_dir)
        self._path_row(self._ss_var, self._browse_ss)

        # ---- Interval ----------------------------------------------
        self._section("Capture Interval (seconds)")
        self._interval_var = tk.StringVar(value=str(self._config.interval_seconds))
        ctk.CTkEntry(
            self, textvariable=self._interval_var, width=80,
            fg_color=COLORS["raised"], border_color=COLORS["border"],
            text_color=COLORS["text"], font=FONTS["body"],
            corner_radius=RADIUS,
        ).pack(anchor="w", padx=pad, pady=(0, SPACING["sm"]))

        # ---- Appearance --------------------------------------------
        self._section("Appearance")
        self._appearance_var = tk.StringVar(value=self._config.appearance_mode.capitalize())
        ctk.CTkSegmentedButton(
            self,
            values=["Dark", "Light", "System"],
            variable=self._appearance_var,
            fg_color=COLORS["raised"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["raised"],
            unselected_hover_color=COLORS["border"],
            text_color=COLORS["text"],
            font=FONTS["body"],
            corner_radius=RADIUS,
        ).pack(anchor="w", padx=pad, pady=(0, SPACING["sm"]))

        # ---- Notifications -----------------------------------------
        self._section("Windows Notifications")
        self._notif_var = tk.BooleanVar(value=self._config.notifications_enabled)
        ctk.CTkSwitch(
            self, text="Show toast notifications",
            variable=self._notif_var,
            onvalue=True, offvalue=False,
            button_color=COLORS["accent"],
            progress_color=COLORS["accent"],
            text_color=COLORS["text"], font=FONTS["body"],
        ).pack(anchor="w", padx=pad, pady=(0, SPACING["sm"]))

        # ---- Save button -------------------------------------------
        ctk.CTkButton(
            self, text="Save",
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"], font=FONTS["body_bold"],
            corner_radius=RADIUS, height=40,
            command=self._save,
        ).pack(fill="x", padx=pad, pady=(SPACING["md"], pad))

    def _section(self, label: str) -> None:
        ctk.CTkLabel(
            self, text=label,
            font=FONTS["small"], text_color=COLORS["subtext"],
        ).pack(anchor="w", padx=SPACING["md"], pady=(SPACING["sm"], 2))

    def _path_row(self, var: tk.StringVar, browse_cmd: Callable) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=SPACING["md"], pady=(0, SPACING["sm"]))
        row.columnconfigure(0, weight=1)
        ctk.CTkEntry(
            row, textvariable=var,
            fg_color=COLORS["raised"], border_color=COLORS["border"],
            text_color=COLORS["text"], font=FONTS["small"],
            corner_radius=RADIUS,
        ).grid(row=0, column=0, sticky="ew", padx=(0, SPACING["sm"]))
        ctk.CTkButton(
            row, text="Browse", width=70,
            fg_color=COLORS["raised"], hover_color=COLORS["border"],
            text_color=COLORS["subtext"], font=FONTS["small"],
            corner_radius=RADIUS, command=browse_cmd,
        ).grid(row=0, column=1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_key_visibility(self) -> None:
        self._show_key = not self._show_key
        self._key_entry.configure(show="" if self._show_key else "*")
        self._eye_btn.configure(text="Hide" if self._show_key else "Show")

    def _browse_db(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Choose database file",
            defaultextension=".db",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if path:
            self._db_var.set(path)

    def _browse_ss(self) -> None:
        path = filedialog.askdirectory(title="Choose screenshot directory")
        if path:
            self._ss_var.set(path)

    def _save(self) -> None:
        try:
            interval = float(self._interval_var.get())
        except ValueError:
            interval = self._config.interval_seconds

        new_cfg = AppConfig(
            claude_api_key=self._key_var.get().strip(),
            db_path=self._db_var.get().strip(),
            screenshot_dir=self._ss_var.get().strip(),
            interval_seconds=max(5.0, interval),
            model_id=self._config.model_id,
            appearance_mode=self._appearance_var.get().lower(),
            notifications_enabled=self._notif_var.get(),
        )
        new_cfg.save()
        self._on_save(new_cfg)
        self.destroy()
