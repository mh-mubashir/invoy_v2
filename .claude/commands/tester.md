Run the Testing Agent (live UI verification) in isolation.

## What this does

Launches the Invoy app, drives it through IDLE → RECORDING → (wait for card) → REVIEW, captures screenshots at each state, then analyzes those screenshots with vision to assess whether the app is rendering correctly and producing quality inference output.

## Steps

1. Run the launcher script to capture screenshots:
   ```
   python .claude/agents/app_launcher.py
   ```
   This will take 2-4 minutes (model load + one capture cycle).

2. Once the launcher finishes, read `.claude/agents/roles/tester.md` — this is your complete instruction set.

3. Read `.claude/agents/workspace/current/screenshots/launcher_meta.json`.

4. Read each screenshot listed in `launcher_meta.json.screenshots` using your image reading capability.

5. If `spec.json` exists, read it for context on what was recently changed.

6. Produce `.claude/agents/workspace/current/live_test_report.json` per the schema in your role file.

7. Report to the user:
   - Overall verdict (`pass` / `fail` / `inconclusive`)
   - The exact text of any activity card you saw (the `format_sample` field)
   - Any issues found with output quality or UI state rendering

## Standalone mode

`/tester` can run without a `spec.json` — it will assess the current state of the app as-is, which is useful for general health checks without an active development task.

## Important

Do NOT write any code. You read screenshots and produce a report only.
