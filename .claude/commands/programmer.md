Run the Programmer Agent in isolation.

## What this does

Implements code changes for the current spec in the workspace.

## Prerequisites

`.claude/agents/workspace/current/spec.json` must exist. If it doesn't, stop and tell the user to run `/pm` first.

## Steps

1. Read `.claude/agents/roles/programmer.md` — this is your complete instruction set for this role.
2. Read `CLAUDE.md` — all code conventions apply strictly.
3. Read `.claude/agents/workspace/current/spec.json`.
4. If `pm_decision.json` exists and `"verdict"` is `"rework"`, read `rework_instructions` carefully — these are the specific fixes required.
5. Read every file in `spec.json.files_to_change` before making changes.
6. Implement the changes.
7. Write `.claude/agents/workspace/current/implementation.md` per the schema in your role file.
8. Report to the user: which files were changed and what `## Status` you wrote.
