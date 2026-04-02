# Request

Improve the activity description prompts in `invoy_app/core/recorder.py` so that the Qwen2-VL 2B model produces more precise, specific, and useful activity descriptions from desktop screenshots.

## Background

The app captures screenshots every 20 seconds and runs two sequential inferences:

1. **Activity inference** — uses `ACTIVITY_PROMPT` with the screenshot image → produces a one-line structured description
2. **Change inference** — uses `CHANGE_PROMPT_TMPL` (text-only, no image) → describes what changed between the previous and current activity

The current prompts use a structured `[App] · [File or URL] · [Action]` format. The format is correct but the quality of what the model produces in each field — especially the **Action** field and the **change description** — needs improvement for a 2B parameter model running on CPU/CUDA.

## Current prompts (in `invoy_app/core/recorder.py`)

```python
ACTIVITY_PROMPT = (
    "Look at this screenshot. Reply in this exact format:\n"
    "[App] · [File or URL] · [specific action with enough detail to be useful]\n\n"
    "Field rules:\n"
    "- App: foreground application (e.g. VS Code, Chrome, Excel, Terminal)\n"
    "- File or URL: full URL if a browser tab is active; file name if an editor is open; "
    "document title for Office/PDF; current directory or command for a terminal; "
    "window title otherwise\n"
    "- Action: name the specific thing being worked on — mention function names, "
    "topics, PR titles, error messages, or commands where visible. "
    "Aim for 8-15 words.\n\n"
    "e.g. VS Code · recorder.py · writing the _on_capture callback that triggers VLM inference\n"
    "e.g. Chrome · github.com/org/repo/pull/47 · reviewing diff in the streaming response module\n"
    "e.g. Terminal · ~/projects/invoy · running pytest on the activity log test suite\n"
    "One line. No extra text."
)

CHANGE_PROMPT_TMPL = (
    "Before: {prev}\n"
    "After: {curr}\n\n"
    "Describe what changed or progressed between these two moments. "
    "Cover: did the app, file, or URL change? Did the task or focus shift? "
    "What specific progress was made?\n"
    "Write one concise sentence. "
    "Only if nothing at all changed, reply exactly: No significant change."
)
```

## Known problems to solve

1. **Qwen2-VL 2B often ignores the `·` separator format** when the screen content is complex — it reverts to prose. The prompt needs stronger format enforcement for a small model.

2. **The Action field is often too generic** — the model writes "editing a Python file" instead of naming the specific function or section visible on screen. Need to force it to read visible text (function names, variable names, headings, error messages).

3. **The change prompt fires "No significant change" too often** — even when the user has clearly moved to a different task in the same app. The threshold for "significant" needs to be lowered.

4. **The change prompt doesn't leverage the structured format** — when both `{prev}` and `{curr}` are in `App · File · Action` format, the model should be comparing them field-by-field, not treating them as opaque strings.

5. **Token efficiency** — the activity prompt is ~138 tokens. For a 2B model on CPU, every token of system prompt costs inference time. The prompt should be as short as possible while still enforcing format.

## Success criteria

- Format compliance rate: >90% of outputs contain exactly two ` · ` separators
- Action specificity: the action field names something specific visible on screen (function name, URL path, document section, command) in >80% of outputs
- Change note generation: a non-"No significant change" note for >60% of consecutive frames (realistic for a working session)
- Token count of activity prompt: target ≤100 prompt tokens (currently ~138)

## Constraints

- Only modify `invoy_app/core/recorder.py` (the two prompt constants)
- Do not change the `·` separator character or the three-field structure — the `_detect_context()` function in `activity_feed.py` parses on ` · `
- `max_new_tokens` for activity inference is 150 — the prompt must produce output within that budget
- The prompts must work for Qwen2-VL 2B (a small model) — overly complex instructions will reduce compliance not increase it
