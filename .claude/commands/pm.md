Run the PM Agent in isolation.

## What this does

Runs the Product Manager agent for either spec writing or decision making, depending on the current workspace state.

## Mode detection

Check which files exist in `.claude/agents/workspace/current/`:

- If **both** `qa_report.json` and `design_review.json` exist → **DECISION mode**
- Otherwise → **SPEC mode**

## Steps

1. Read `.claude/agents/roles/pm.md` — this is your complete instruction set for this role.
2. Read `CLAUDE.md` to understand the codebase.
3. Run in the detected mode per your role file instructions.
4. Write the output file (`spec.json` or `pm_decision.json`) to `.claude/agents/workspace/current/`.
5. Report to the user: which mode ran, what file was produced, and a one-line summary of the output.

## If SPEC mode and no request.md

Ask the user: "What change do you want to make to Invoy?" Write their answer to `.claude/agents/workspace/current/request.md`, then proceed with spec writing.
