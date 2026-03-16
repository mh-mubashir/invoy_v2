# Invoy SDK

SDK for periodic screenshot capture on Linux. Designed to support future features like screen activity analysis and work-type judgment.

## Requirements

- Linux (primary target; other platforms may work but are untested)
- Python 3.9+
- **Display**: Active graphical session. On **X11**, mss is used. On **GNOME Wayland**, gnome-screenshot is required (`sudo apt install gnome-screenshot`). On **Sway/wlroots**, grim is used. **Note:** scrot produces black/empty screenshots on Wayland—do not use. See [docs/SCREENSHOT_PLATFORM.md](docs/SCREENSHOT_PLATFORM.md) for tested configurations.

## Installation

```bash
cd invoy_v2
pip install -e .
```

Or install dependencies only:

```bash
pip install mss
```

## Quick Start

### Periodic capture (every 10 seconds)

```python
from invoy_sdk import ScreenshotCapture

# Capture screenshots every 10 seconds, save to ./screenshots
capture = ScreenshotCapture(interval_seconds=10, output_dir="./screenshots")
capture.start()

# Let it run... (e.g. in your application)
# capture.stop()  # when done
```

### Single screenshot (blocking)

```python
from invoy_sdk import ScreenshotCapture

capture = ScreenshotCapture(output_dir="./screenshots")
path = capture.capture_once()
print(f"Saved to: {path}")
```

### Custom callback on each capture

```python
def on_screenshot(path: str, raw_bytes: bytes):
    print(f"Captured: {path} ({len(raw_bytes)} bytes)")
    # Future: pass to activity analysis, upload, etc.

capture = ScreenshotCapture(
    interval_seconds=10,
    output_dir="./screenshots",
    on_capture=on_screenshot,
)
capture.start()
```

## API Reference

### `ScreenshotCapture`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `interval_seconds` | float | 10.0 | Seconds between screenshots |
| `output_dir` | str/Path | "./screenshots" | Directory to save PNG files |
| `monitor` | int | 0 | Monitor index (0=all, 1=first, 2=second, ...) |
| `on_capture` | callable | None | Optional callback(path, raw_bytes) after each capture |

### Methods

- **`start()`** — Start periodic capture in a background thread
- **`stop()`** — Stop periodic capture
- **`capture_once()`** — Take a single screenshot (blocking)
- **`is_running`** — Property: whether capture is active

## Project Structure

```
invoy_v2/
├── invoy_sdk/
│   ├── __init__.py      # Public API
│   └── capture.py       # Screenshot capture + scheduler
├── pyproject.toml
└── README.md
```

## Activity Tracking (MLLM + SQLite)

Capture screenshots, analyze with a local multimodal LLM (Moondream), and log to SQLite.

### Prerequisites

1. **Ollama** – [Install](https://ollama.com/download)
2. **Vision model** – `ollama pull llava` (recommended, better quality) or `ollama pull llava-phi3` (lighter, CPU-friendly)

### Usage

```python
from invoy_sdk import ActivityTrackingPipeline

pipeline = ActivityTrackingPipeline(
    interval_seconds=10,
    output_dir="./screenshots",
    db_path="./activity_log.db",
)
pipeline.start()
# ...
pipeline.stop()

# Query activity log
entries = pipeline.get_entries(limit=20)
```

Run the example: `python example_activity.py`

### SQLite Schema

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | UUID |
| timestamp | TEXT | ISO format |
| unix_time | REAL | Unix timestamp |
| screenshot_path | TEXT | Path to PNG |
| activity | TEXT | MLLM description of current work |
| change_summary | TEXT | MLLM description of what changed from previous screenshot |
| activity_inference_ms | REAL | Edge inference time for activity MLLM call (ms) |
| change_inference_ms | REAL | Edge inference time for change detection MLLM call (ms) |
| session_id | TEXT | Session UUID |

---

## Roadmap

- [x] Periodic screenshot capture (configurable interval)
- [x] MLLM analysis (Moondream via Ollama)
- [x] SQLite activity logging
- [ ] Change detection (skip MLLM when no change)
- [ ] Configurable storage backends (local, S3, etc.)
- [ ] Cross-platform support (macOS, Windows)
