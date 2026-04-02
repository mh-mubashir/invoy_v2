# Request: Rewrite ACTIVITY_PROMPT as Zero-Shot (No Examples)

## Problem

The Qwen2-VL 2B model is copying our few-shot examples verbatim from `ACTIVITY_PROMPT`.

Confirmed DB evidence from live testing (today):
- `"Figma · Invoy dashboard v3 · adjusting spacing on activity card"` (x2) — exact copy of the Figma example line
- `"App · Figma · Adjusting spacing on activity card"` — model echoing field label literally
- `"Command Prompt"` — bare output, no format

Root cause: small 2B VLMs pattern-match on few-shot examples when the screen content even vaguely resembles them. We tried Terminal, Chrome, VS Code, Slack, Figma, Notion examples over 3 loops — copying persisted every time.

## What to change

**File:** `invoy_app/core/recorder.py`
**Constant:** `ACTIVITY_PROMPT` only

Remove ALL three few-shot examples (Figma, Notion, Slack lines). Do NOT replace them with different examples. Goal is zero-shot — no examples at all.

Keep:
- The grounding line: `"Look at this screenshot. Read the title bar, tab title, and URL bar."`
- The format line: `"App · File/URL · Action"` (U+00B7 MIDDLE DOT, spaces around dots)
- A tight rules section (3 rules max) describing what each field should contain

The rules must guide the model to output specific, screen-observable values:
- **App**: name of the foreground application
- **File/URL**: the full URL, file name, document title, or current directory — whatever is most specific and visible
- **Action**: a specific visible element or identifier — function name, URL path, command, error message, heading; do NOT use vague verbs

Do NOT change `CHANGE_PROMPT_TMPL`. Do NOT change any other code.

## Success criteria

After the change, running the app and checking `~/.invoy/activity.db` should show:
- No entry that matches any line in the new `ACTIVITY_PROMPT` verbatim
- Entries that vary across captures (not the same string repeated)
- Each entry uses `App · File/URL · Action` format with exactly two ` · ` separators

## Constraints

- Only modify `ACTIVITY_PROMPT` in `invoy_app/core/recorder.py`
- Do NOT change `CHANGE_PROMPT_TMPL` or any other code
- Do NOT add any examples — zero-shot only
- Keep U+00B7 MIDDLE DOT separators — `activity_feed.py` parses on ` · `
