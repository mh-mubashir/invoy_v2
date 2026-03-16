# Activity Tracking – MLLM + SQLite

Screen activity tracking using a local multimodal LLM (Moondream) and SQLite logging.

## Overview

1. **Screenshot** – Captured every N seconds (default 10)
2. **MLLM** – Moondream analyzes each screenshot locally (CPU)
3. **Log** – Activity description stored in SQLite with timestamps

Change detection is not yet implemented; every screenshot is sent to the MLLM.

## Prerequisites

### Ollama

Install [Ollama](https://ollama.com/download), then pull a vision model:

```bash
ollama pull llava        # Best quality (~5GB RAM needed)
ollama pull llava-phi3   # Good quality (~4.6GB RAM needed)
ollama pull moondream:1.8b-v2-q5_K_M   # Best for ~4GB RAM: better than default moondream
ollama pull moondream    # Smallest: ~2GB RAM, fastest
```

**Memory**: With ~4GB available, use `moondream:1.8b-v2-q5_K_M` for better quality than default moondream.

### Python

```bash
pip install invoy-sdk
# or: pip install -e .
```

## Usage

```python
from invoy_sdk import ActivityTrackingPipeline

pipeline = ActivityTrackingPipeline(
    interval_seconds=10,
    output_dir="./screenshots",
    db_path="./activity_log.db",
)
pipeline.start()

# ... let it run ...

pipeline.stop()
entries = pipeline.get_entries(limit=20)
```

## SQLite Schema

```sql
CREATE TABLE activity_entries (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    unix_time REAL NOT NULL,
    screenshot_path TEXT NOT NULL,
    activity TEXT,
    change_summary TEXT,
    activity_inference_ms REAL,
    change_inference_ms REAL,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

- **activity**: MLLM description of work being done on the current screen
- **change_summary**: MLLM description of what changed from the previous screenshot (NULL for first entry)
- **activity_inference_ms**: Edge inference time for the activity MLLM call (milliseconds)
- **change_inference_ms**: Edge inference time for the change detection MLLM call (milliseconds, NULL for first entry)

## MLLM Calls

Activity and change detection use **separate MLLM calls** with distinct purposes:

- **Activity**: Single image → detailed description of what work the user is doing (exact nature, topic, context, applications)
- **Change**: Two images (previous + current) → states whether the work is the SAME or DIFFERENT, with brief explanation

## Querying the Log

```python
from invoy_sdk import SQLiteActivityLog

log = SQLiteActivityLog(db_path="./activity_log.db")
entries = log.get_entries(limit=50)
for e in entries:
    print(e["timestamp"], e["activity"])
```

Or with SQLite directly:

```bash
sqlite3 activity_log.db "SELECT timestamp, activity FROM activity_entries ORDER BY unix_time DESC LIMIT 10"
```

## Hardware

- **CPU only** – Moondream (~1.6B params) runs on CPU via Ollama
- Expect ~5–30 seconds per screenshot depending on CPU
- Interval is minimum; actual cadence = interval + analysis time

## Model

- **moondream** – Small vision-language model, CPU-friendly
- Alternative: `ollama pull llava` (larger, slower, more accurate)
