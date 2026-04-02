"""
Invoy App — Windows toast notifications.

Uses win10toast-persist (a fork of win10toast with no auto-dismiss bug).
Falls back silently on non-Windows platforms so the app still works for
development on macOS/Linux.
"""

from __future__ import annotations

import platform
import threading
from pathlib import Path

_IS_WINDOWS = platform.system() == "Windows"

_ICON_PATH: Path = Path(__file__).parent.parent / "assets" / "icon.ico"


class WindowsNotifier:
    """
    Fire-and-forget Windows toast notifications.

    All calls are non-blocking — the toast is shown in a daemon thread.
    Safe to call from any thread.
    """

    def __init__(self, app_name: str = "Invoy") -> None:
        self._app_name = app_name
        self._toaster  = None

        if _IS_WINDOWS:
            try:
                from win10toast_persist import ToastNotifier  # type: ignore
                self._toaster = ToastNotifier()
            except ImportError:
                pass   # win10toast-persist not installed — degrade silently

    # ──────────────────────────────────────────────────────────────────

    def notify(self, message: str, duration: int = 6) -> None:
        """Show a toast notification with *message*. Non-blocking."""
        if not self._toaster:
            return   # not on Windows or package missing
        # Clamp message length — Windows toasts truncate at ~200 chars anyway
        short = message[:160].replace("\n", " ")
        icon  = str(_ICON_PATH) if _ICON_PATH.exists() else None

        def _fire() -> None:
            try:
                self._toaster.show_toast(
                    title=self._app_name,
                    msg=short,
                    icon_path=icon,
                    duration=duration,
                    threaded=True,
                )
            except Exception:
                pass  # toast failures must never crash the app

        threading.Thread(target=_fire, daemon=True).start()
