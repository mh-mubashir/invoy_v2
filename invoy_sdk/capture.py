"""
Screenshot capture module: mss (X11), grim (Wayland), gnome-screenshot fallback.

Provides periodic screenshot capture on Linux with configurable
interval and storage.

Note: scrot produces BLACK screenshots on Wayland - do not use.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import mss
import mss.tools

logger = logging.getLogger(__name__)


def _is_linux() -> bool:
    """Check if running on Linux."""
    return sys.platform == "linux"


class ScreenshotCapture:
    """
    Periodic screenshot capture for Linux.

    Captures screenshots at a configurable interval and stores them
    to a directory. Designed to be extended later for screen activity
    analysis and judgment.

    Example:
        capture = ScreenshotCapture(interval_seconds=10, output_dir="./screenshots")
        capture.start()
        # ... runs in background ...
        capture.stop()
    """

    def __init__(
        self,
        interval_seconds: float = 10.0,
        output_dir: str | Path = "./screenshots",
        monitor: int = 0,
        on_capture: Optional[Callable[[str, bytes], None]] = None,
    ):
        """
        Initialize the screenshot capture.

        Args:
            interval_seconds: Time between screenshots in seconds. Default 10.
            output_dir: Directory to save screenshots. Created if it doesn't exist.
            monitor: Monitor index (0 = all monitors combined, 1 = first, etc.)
            on_capture: Optional callback(path, raw_bytes) called after each capture.
        """
        if not _is_linux():
            logger.warning(
                "Invoy SDK is primarily tested on Linux. "
                "Other platforms may have different behavior."
            )

        self.interval_seconds = interval_seconds
        self.output_dir = Path(output_dir)
        self.monitor = monitor
        self.on_capture = on_capture

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _take_screenshot_mss(self, filepath: Path) -> Optional[tuple[str, bytes]]:
        """Try mss (X11). Returns (path, bytes) or None."""
        try:
            with mss.mss() as sct:
                mon = sct.monitors[self.monitor]
                screenshot = sct.grab(mon)
                png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                filepath.write_bytes(png_bytes)
                return str(filepath), png_bytes
        except Exception as e:
            logger.debug("mss capture failed: %s", e)
            return None

    def _take_screenshot_grim(self, filepath: Path) -> Optional[tuple[str, bytes]]:
        """Wayland: grim (native Wayland capture). Returns (path, bytes) or None."""
        grim_path = shutil.which("grim")
        if not grim_path:
            return None
        try:
            subprocess.run(
                [grim_path, str(filepath)],
                check=True,
                capture_output=True,
                timeout=10,
            )
            if filepath.exists():
                return str(filepath), filepath.read_bytes()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.debug("grim capture failed: %s", e)
        return None

    def _take_screenshot_gnome(self, filepath: Path) -> Optional[tuple[str, bytes]]:
        """Fallback: gnome-screenshot (GNOME Wayland). Returns (path, bytes) or None."""
        gnome_path = shutil.which("gnome-screenshot")
        if not gnome_path:
            return None
        try:
            subprocess.run(
                [gnome_path, "-f", str(filepath)],
                check=True,
                capture_output=True,
                timeout=10,
            )
            if filepath.exists():
                return str(filepath), filepath.read_bytes()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.debug("gnome-screenshot capture failed: %s", e)
        return None

    def _take_screenshot(self) -> Optional[tuple[str, bytes]]:
        """
        Take a single screenshot and save it.

        Order: mss (X11) -> grim (Wayland) -> gnome-screenshot (GNOME).
        Note: scrot produces black images on Wayland and is not used.

        Returns:
            Tuple of (file_path, raw_png_bytes) or None on failure.
        """
        self._ensure_output_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = self.output_dir / filename

        result = self._take_screenshot_mss(filepath)
        if result is None:
            result = self._take_screenshot_gnome(filepath)
        if result is None:
            result = self._take_screenshot_grim(filepath)

        if result:
            logger.debug("Screenshot saved: %s", result[0])
        else:
            logger.error(
                "Screenshot capture failed (tried mss, gnome-screenshot, grim). "
                "On GNOME Wayland: sudo apt install gnome-screenshot. "
                "On Sway/wlroots: sudo apt install grim"
            )
        return result

    def _capture_loop(self) -> None:
        """Background loop that captures screenshots at the configured interval."""
        logger.info(
            "Screenshot capture started (interval=%ss, output=%s)",
            self.interval_seconds,
            self.output_dir,
        )

        while not self._stop_event.is_set():
            result = self._take_screenshot()
            if result and self.on_capture:
                path, raw_bytes = result
                try:
                    self.on_capture(path, raw_bytes)
                except Exception as e:
                    logger.exception("on_capture callback failed: %s", e)

            # Wait for interval, but check stop_event periodically
            for _ in range(int(self.interval_seconds * 10)):
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)

        self._running = False
        logger.info("Screenshot capture stopped")

    def start(self) -> None:
        """Start periodic screenshot capture in a background thread."""
        if self._running:
            logger.warning("Screenshot capture is already running")
            return

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop periodic screenshot capture."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds + 2)
            self._thread = None

    def capture_once(self) -> Optional[str]:
        """
        Take a single screenshot (blocking). Useful for testing.

        Returns:
            Path to the saved screenshot file, or None on failure.
        """
        result = self._take_screenshot()
        return result[0] if result else None

    @property
    def is_running(self) -> bool:
        """Whether periodic capture is currently running."""
        return self._running
