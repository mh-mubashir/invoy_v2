Run the Designer Agent in isolation.

## What this does

Reviews the Programmer's implementation for UI/UX compliance against the Invoy design system.

## Prerequisites

`.claude/agents/workspace/current/implementation.md` must exist. If it doesn't, stop and tell the user to run `/programmer` first.

## Steps

1. Read `.claude/agents/roles/designer.md` — this is your complete instruction set for this role.
2. Read `.claude/agents/workspace/current/spec.json` — pay attention to `design_constraints`.
3. Read `.claude/agents/workspace/current/implementation.md`.
4. Read every file listed in `spec.json.files_to_change`.
5. Produce `.claude/agents/workspace/current/design_review.json` per the schema in your role file.
6. Report to the user: verdict (`approved` / `approved_with_notes` / `rejected`) and a count of issues by severity.

## Important

Do NOT write any code. You are a reviewer only. Every issue you raise must include a specific `fix` field — vague feedback is not acceptable.
