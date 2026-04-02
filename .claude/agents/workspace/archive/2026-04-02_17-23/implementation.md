## Changes Made
- `invoy_app/core/recorder.py:72–80` — Rewrote ACTIVITY_PROMPT to zero-shot: removed all three few-shot example lines (Figma, Notion, Slack) and the blank lines that flanked them; retained the grounding line, the `App · File/URL · Action` format line (U+00B7 MIDDLE DOT), and the three rule lines covering App, File/URL, and Action fields.

## Design Decisions
- Removed the blank line between the format line and the rules block (was `"App · File/URL · Action\n\n"` → `"App · File/URL · Action\n"`). The blank line existed only to visually separate the format line from the examples; without examples it served no purpose and could create an unnecessary instruction boundary that confuses a small model.
- The three rule lines were kept verbatim. They describe screen-observable, specific values (function names, URLs, commands, error messages, headings) and explicitly discourage vague verbs — sufficient guidance for zero-shot use without any examples.
- CHANGE_PROMPT_TMPL is byte-for-byte unchanged (AC-4).

## Thread Safety Notes
- This change touches only a module-level string constant. No code that runs off the Tk main thread was modified. No `root.after(0, fn)` wrapping is needed or changed.

## Known Limitations
- Removing few-shot examples may increase malformed or bare outputs from Qwen2-VL 2B (e.g. a single app name with no separators). This is the accepted trade-off per spec; AC-6 in the live test catches regressions. No compensating examples were added back.

## Status
done
