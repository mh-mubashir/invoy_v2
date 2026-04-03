Run the full Invoy multi-agent pipeline.

## What this does

Sequences five agents — PM (spec) → Programmer → Designer → QA → Testing Agent → PM (decision) — to take a raw user request, implement it, review it, and produce a final pass/rework/fail verdict.

## Steps

1. Check if `.claude/agents/workspace/current/request.md` exists and is non-empty.
   - If missing or empty: ask the user "What change do you want to make to Invoy?" and write their answer to that file.

2. Run the full pipeline:
   ```
   python .claude/agents/orchestrator.py --phase all
   ```

3. After the orchestrator exits:
   - If exit code 0 (pass): read `pm_decision.json`, show the changed files, and tell the user "Review the changes and commit when ready."
   - If exit code 1 (fail/rework limit): read `pm_decision.json`, show all blockers and rework instructions. Ask the user if they want to resolve the issues manually or discard the changes.
   - If exit code 2 (setup error): show the error and ask the user to check that `spec.json` or `request.md` exists.

## Context to read first

Before running the orchestrator, read:
- `CLAUDE.md` — project conventions
- `.claude/agents/workspace/current/request.md` — if it exists
- `.claude/agents/workspace/current/pm_decision.json` — if it exists (shows previous loop state)
