Run the QA Agent (static analysis) in isolation.

## What this does

Verifies the Programmer's implementation against the PM's acceptance criteria and a standard quality checklist, through static code reading only.

## Prerequisites

`.claude/agents/workspace/current/spec.json` must exist. If it doesn't, stop and tell the user to run `/pm` first.

## Steps

1. Read `.claude/agents/roles/qa.md` — this is your complete instruction set for this role.
2. Read `.claude/agents/workspace/current/spec.json`.
3. Read `.claude/agents/workspace/current/implementation.md` if it exists.
4. Read every file listed in `spec.json.files_to_change`.
5. Verify each acceptance criterion against the code.
6. Run every check in the quality checklist from your role file.
7. Write `.claude/agents/workspace/current/qa_report.json` per the schema in your role file.
8. Report the overall verdict (`pass` / `fail`) and any critical issues immediately.

## Important

Do NOT write any code. Report only what you can verify through static analysis. Do not flag design or visual issues — those belong to `/designer`.
