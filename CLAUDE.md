# Invoy — Claude Code Project Instructions

## Project Identity

**Invoy** is a Windows 11 desktop application that periodically captures screenshots, runs local Qwen2-VL vision inference, and builds a structured work log. At the end of a session the log is summarised via the Claude API into categorised work cards.

- **UI framework**: customtkinter (CTk) — dark mode, Windows 11
- **Inference**: Qwen2-VL-2B (local, HuggingFace) via `invoy_sdk.Qwen2VLBackend`
- **Persistence**: SQLite via `invoy_sdk.SQLiteActivityLog` at `~/.invoy/activity.db`
- **Config**: JSON at `~/.invoy/config.json` via `invoy_app.settings.config.AppConfig`
- **Entry point**: `python -m invoy_app.main`

## Three-State Model

```
IDLE  ──(Begin Session)──►  RECORDING  ──(End Session)──►  REVIEW
 ▲                                                              │
 └──────────────────(New Session)──────────────────────────────┘
```

States live in `invoy_app/app.py` as `AppState` enum. Each state clears and repopulates `self._content_frame`. Never manipulate child widgets from a state that isn't active.

## Thread Model

- `ScreenshotCapture` runs a **daemon thread**. `_on_capture()` runs on that thread.
- All VLM inference runs on the capture thread.
- **Any UI mutation from a non-Tk thread MUST use `root.after(0, fn)`** — no exceptions.
- `SQLiteActivityLog` uses `check_same_thread=False` — safe to write from capture thread.
- The Tk main thread must never block (no `time.sleep`, no synchronous I/O).

## Design System

All tokens live in `invoy_app/styles/theme.py`. **Never hardcode hex values, font tuples, or pixel sizes in component files.**

| Token type | How to use |
|------------|-----------|
| Colors | `COLORS["key"]` — e.g. `COLORS["bg"]`, `COLORS["accent"]` |
| Fonts | `FONTS["key"]` — e.g. `FONTS["body"]`, `FONTS["ui_bold"]` |
| Spacing | `SPACING["key"]` — e.g. `SPACING["md"]` (16px), `SPACING["sm"]` (8px) |
| Radius | `RADIUS` (10), `RADIUS_SM` (6), `RADIUS_XS` (4) |

**Color semantics — non-negotiable:**
- `COLORS["bg"]` `#09090B` — root window background only
- `COLORS["surface"]` `#131316` — card and panel backgrounds
- `COLORS["elevated"]` `#1C1C1F` — hover states, selected rows
- `COLORS["accent"]` `#3B82F6` — primary CTA buttons and active toggle states **only**
- `COLORS["recording"]` `#F87171` — recording state pulse dot **only**
- `COLORS["muted"]` — timestamps and inactive labels; never use as foreground on a muted background

**Layout rules:**
- 8-px spacing grid throughout (`SPACING` tokens)
- `RADIUS = 10` for cards and buttons — not pill-shaped
- No gradients, no drop shadows, no box shadows
- Hover states: `COLORS["elevated"]` background only — no border or colour change
- Animations: only the existing breathing pulse (`after(50ms)` sine approximation) and card fade-in (`after(25ms)`, 8 steps)

## Code Conventions

- All UI components inherit from `ctk.CTkFrame`
- Import order: stdlib → third-party → `invoy_app.*` → `invoy_sdk.*`
- New `AppConfig` fields: add a type-annotated field with a safe default; update both `load()` (via known-key filter) and `save()` (via `asdict`) — both are automatic if you use `@dataclass`
- Non-fatal errors: `print()` only — do **not** call `_ui_error()` for recoverable conditions
- Fatal errors (recorder crashes): call `_on_error(message)` which transitions UI to Idle with an error label
- No changes to `invoy_sdk/` primitives unless the spec explicitly calls for it
- Do not import from `invoy_app.components.db_viewer` or `invoy_app.components.recording_controls` in `app.py` — those are unused legacy files

## Agent System

This project uses a five-role multi-agent pipeline for structured improvement:

```
PM (spec) → Programmer → Designer + QA → Testing Agent → PM (decision)
```

**Workspace:** `.claude/agents/workspace/current/` — all agent I/O files live here.

**Role files:** `.claude/agents/roles/<role>.md` — each agent reads its own role file at session start.

**Agent contracts:**
- Every agent MUST write its output file before ending its session
- Every output file MUST include a `"status"` field: `"done"`, `"blocked"`, or `"fail"`
- Agents MUST NOT modify files outside the repo root or `~/.invoy/`
- Programmer MUST NOT modify files not listed in `spec.json.files_to_change`
- Designer and QA MUST NOT write any code — review documents only

**Slash commands:**
- `/pipeline` — full five-phase loop
- `/pm` — PM agent only (auto-detects spec vs decision mode)
- `/programmer` — implement from spec
- `/designer` — UI/UX review only
- `/qa` — static analysis only
- `/tester` — live UI test (launches app, takes screenshots, vision analysis)

## File Map

```
invoy_app/
├── app.py                  AppState enum, state transitions, chrome
├── main.py                 Entry point
├── core/
│   ├── recorder.py         InvoyRecorder — capture + inference + logging
│   ├── summarizer.py       ClaudeSummarizer — Claude API work log
│   └── notifier.py         WindowsNotifier — toast notifications
├── components/
│   ├── header.py           HeaderBar — four modes: idle/loading/recording/review
│   ├── idle_view.py        IdleView — centred CTA + session history
│   ├── activity_feed.py    ActivityFeed — live timeline cards
│   └── summary_panel.py    SummaryPanel — category cards from Claude output
├── settings/
│   ├── config.py           AppConfig dataclass + JSON persistence
│   └── settings_window.py  Settings modal (CTkToplevel)
└── styles/
    └── theme.py            COLORS, FONTS, SPACING, RADIUS, window geometry

invoy_sdk/
├── capture.py              ScreenshotCapture — periodic screenshot daemon
├── vlm_backends.py         Qwen2VLBackend — HuggingFace local inference
├── activity_log.py         SQLiteActivityLog — schema + write/query
└── pipeline.py             ActivityTrackingPipeline (legacy, not used by app)
```
