"""
Invoy Multi-Agent Orchestrator

Sequences the pipeline by invoking the `claude` CLI headlessly for each
agent role. Agents communicate through structured files in
.claude/agents/workspace/current/.

Usage:
    python .claude/agents/orchestrator.py --phase all
    python .claude/agents/orchestrator.py --phase all --methodology design-first
    python .claude/agents/orchestrator.py --phase qa-only [--if-spec-present] [--trigger post-commit]
    python .claude/agents/orchestrator.py --phase tester-only

Phases:
    all          Pipeline run (see --methodology for order)
    qa-only      Static QA only (used by post-commit hook)
    tester-only  app_launcher + Testing Agent only

Methodologies:
    classic       PM(spec) -> Programmer -> Designer -> QA -> Tester -> PM(decision)
    design-first  PM(spec) -> Designer(spec review) -> Programmer -> Tester -> PM(decision)
                  Designer reviews the spec and existing code BEFORE the programmer
                  starts, providing design guidance. QA is skipped entirely.

Exit codes:
    0  Pipeline passed (verdict: pass)
    1  Pipeline failed or rework limit reached
    2  Setup error (missing files, claude CLI not found)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# -- Paths -----------------------------------------------------------------

_AGENTS_DIR   = Path(__file__).parent
_ROLES_DIR    = _AGENTS_DIR / "roles"
_WORKSPACE    = _AGENTS_DIR / "workspace" / "current"
_ARCHIVE_DIR  = _AGENTS_DIR / "workspace" / "archive"
_REPO_ROOT    = Path(__file__).parents[2]

def _find_claude() -> str:
    """Locate the claude CLI binary, checking common Windows install paths."""
    import glob as _glob
    import shutil as _shutil
    found = _shutil.which("claude")
    if found:
        return found
    pattern = str(Path.home() / "AppData" / "Local" / "AnthropicClaude" / "app-*" / "claude.exe")
    matches = sorted(_glob.glob(pattern), reverse=True)
    if matches:
        return matches[0]
    return "claude"

_CLAUDE_BIN = _find_claude()

_MAX_LOOPS    = 3
_LOOP_FILE    = _WORKSPACE / ".loop_count"
_STATUS_FILE  = _WORKSPACE / "pipeline_status.json"

# Current loop — set at start of each loop so _run_agent can include it in status
_current_loop: int = 0


# -- Utilities -------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _read_json(filename: str) -> dict:
    path = _WORKSPACE / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[orchestrator] WARNING: could not parse {filename}: {exc}")
        return {}


def _file_exists(filename: str) -> bool:
    return (_WORKSPACE / filename).exists()


def _get_loop_count() -> int:
    try:
        return int(_LOOP_FILE.read_text().strip())
    except Exception:
        return 0


def _increment_loop() -> int:
    count = _get_loop_count() + 1
    _LOOP_FILE.write_text(str(count))
    return count


def _archive_workspace() -> None:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    dest = _ARCHIVE_DIR / ts
    dest.mkdir(parents=True, exist_ok=True)
    for f in _WORKSPACE.iterdir():
        if f.name != ".gitkeep":
            shutil.move(str(f), str(dest / f.name))
    _LOOP_FILE.unlink(missing_ok=True)
    print(f"[orchestrator] Workspace archived -> {dest}")


def _has_critical_issues() -> bool:
    """Check if design_review or qa_report contain any critical issues."""
    design = _read_json("design_review.json")
    qa     = _read_json("qa_report.json")
    design_crit = any(
        i.get("severity") == "critical"
        for i in design.get("issues", [])
    )
    qa_crit = any(
        i.get("severity") == "critical"
        for i in qa.get("critical_issues", [])
    )
    return design_crit or qa_crit


# -- Live status file ------------------------------------------------------

def _write_status(phase: str, state: str, loop: int = 0, extra: dict | None = None) -> None:
    """Write/update pipeline_status.json with current pipeline state."""
    existing: dict = {}
    if _STATUS_FILE.exists():
        try:
            existing = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    phases_done: list = existing.get("phases_completed", [])
    if state == "completed":
        phases_done.append({
            "phase": phase,
            "completed_at": datetime.now().isoformat(),
        })

    status = {
        "pipeline_state": state,
        "current_phase": phase,
        "loop": loop,
        "max_loops": _MAX_LOOPS,
        "updated_at": datetime.now().isoformat(),
        "phases_completed": phases_done,
        **(extra or {}),
    }
    _STATUS_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")


def _agent_summary(role: str) -> str:
    """Return a one-line summary of what an agent produced."""
    if role == "pm":
        # Could be spec or decision — check which files exist
        if _file_exists("pm_decision.json"):
            d = _read_json("pm_decision.json")
            verdict = d.get("verdict", "?")
            summary = d.get("summary", "")[:80]
            return f"verdict={verdict} | {summary}"
        d = _read_json("spec.json")
        n_ac = len(d.get("acceptance_criteria", []))
        return f"{d.get('request_summary', '?')} | {n_ac} ACs"
    if role == "programmer":
        impl = (_WORKSPACE / "implementation.md")
        if impl.exists():
            lines = impl.read_text(encoding="utf-8").splitlines()
            first = next((l for l in lines if l.strip() and not l.startswith("#")), "done")
            return first[:100]
        return "implementation.md written"
    if role == "designer":
        d = _read_json("design_review.json")
        n = len(d.get("issues", []))
        return f"verdict={d.get('verdict','?')} | {n} issue(s)"
    if role == "qa":
        d = _read_json("qa_report.json")
        n_crit = len(d.get("critical_issues", []))
        overall = d.get("overall", "?")
        return f"overall={overall} | {n_crit} critical issue(s)"
    if role == "tester":
        d = _read_json("live_test_report.json")
        cards = d.get("output_quality", {}).get("cards_appeared", "?")
        return f"overall={d.get('overall','?')} | cards_appeared={cards}"
    return "done"


# -- Agent invocation ------------------------------------------------------

def _run_agent(role: str, task_prompt: str, timeout_s: int = 900) -> bool:
    """
    Invoke `claude --print --system-prompt <role_file>` with task via stdin.
    Returns True if the agent ran successfully (exit code 0).
    """
    global _current_loop

    role_file = _ROLES_DIR / f"{role}.md"
    if not role_file.exists():
        print(f"[orchestrator] ERROR: role file not found: {role_file}")
        return False

    system_prompt = role_file.read_text(encoding="utf-8")

    full_prompt = (
        f"Working directory: {_REPO_ROOT}\n"
        f"Workspace: {_WORKSPACE}\n\n"
        f"{task_prompt}"
    )

    print(f"\n[orchestrator] [{_ts()}] >>> {role.upper()} starting (loop {_current_loop}/{_MAX_LOOPS})")
    _write_status(phase=role, state="running", loop=_current_loop)

    env = os.environ.copy()
    env["NODE_NO_WARNINGS"] = "1"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [_CLAUDE_BIN, "--print", "--dangerously-skip-permissions", "--system-prompt", system_prompt],
        input=full_prompt,
        cwd=str(_REPO_ROOT),
        timeout=timeout_s,
        capture_output=False,
        text=True,
        encoding="utf-8",
        env=env,
    )

    if result.returncode != 0:
        print(f"[orchestrator] [{_ts()}] {role.upper()} FAILED (exit {result.returncode})")
        _write_status(phase=role, state="agent_failed", loop=_current_loop)
        return False

    summary = _agent_summary(role)
    print(f"[orchestrator] [{_ts()}] <<< {role.upper()} done | {summary}")
    _write_status(phase=role, state="completed", loop=_current_loop, extra={"last_agent_summary": summary})
    return True


# -- Pipeline phases -------------------------------------------------------

def phase_pm_spec() -> bool:
    if not _file_exists("request.md"):
        print("[orchestrator] ERROR: request.md not found in workspace/current/")
        return False
    return _run_agent(
        "pm",
        "Run in SPEC mode. "
        f"Read {_WORKSPACE}/request.md. "
        f"Produce {_WORKSPACE}/spec.json per the schema in your role file.",
        timeout_s=900,
    )


def phase_programmer() -> bool:
    if not _file_exists("spec.json"):
        print("[orchestrator] ERROR: spec.json not found — PM spec phase must run first")
        return False
    decision_note = ""
    if _file_exists("pm_decision.json"):
        decision = _read_json("pm_decision.json")
        if decision.get("verdict") == "rework":
            decision_note = (
                f"pm_decision.json exists with verdict 'rework'. "
                f"Read rework_instructions carefully: {decision.get('rework_instructions', '')}"
            )
    return _run_agent(
        "programmer",
        f"Read {_WORKSPACE}/spec.json. "
        + (decision_note + " " if decision_note else "")
        + f"Implement the changes. Write {_WORKSPACE}/implementation.md.",
        timeout_s=900,
    )


def phase_designer(pre_implementation: bool = False) -> bool:
    if pre_implementation:
        # Design-first: designer reviews the spec + existing files BEFORE programmer runs.
        # Produces design_review.json with guidance for the programmer.
        if not _file_exists("spec.json"):
            print("[orchestrator] ERROR: spec.json not found — PM spec phase must run first")
            return False
        return _run_agent(
            "designer",
            f"You are running in PRE-IMPLEMENTATION mode. "
            f"implementation.md does NOT exist yet — the programmer has not started. "
            f"Read {_WORKSPACE}/spec.json carefully. "
            f"Read every file listed in spec.json files_to_change to understand the CURRENT state. "
            f"Your job: identify design constraints, colour/spacing/font token violations to watch out for, "
            f"and any UI patterns the programmer must follow for this change. "
            f"Write design_review.json with your verdict and issues — treat this as pre-flight guidance "
            f"for the programmer, not a post-implementation audit. "
            f"Produce {_WORKSPACE}/design_review.json.",
            timeout_s=900,
        )
    else:
        if not _file_exists("implementation.md"):
            print("[orchestrator] ERROR: implementation.md not found — Programmer must run first")
            return False
        return _run_agent(
            "designer",
            f"Read {_WORKSPACE}/spec.json and {_WORKSPACE}/implementation.md, "
            f"then read every file listed in spec.json files_to_change. "
            f"Produce {_WORKSPACE}/design_review.json.",
            timeout_s=900,
        )


def phase_qa() -> bool:
    if not _file_exists("spec.json"):
        print("[orchestrator] ERROR: spec.json not found")
        return False
    return _run_agent(
        "qa",
        f"Read {_WORKSPACE}/spec.json and {_WORKSPACE}/implementation.md (if it exists), "
        f"then read every file listed in spec.json files_to_change. "
        f"Produce {_WORKSPACE}/qa_report.json.",
        timeout_s=900,
    )


def phase_tester() -> bool:
    """Run app_launcher.py then the Testing Agent."""
    print(f"\n[orchestrator] [{_ts()}] Running app_launcher.py ...")
    _write_status(phase="app_launcher", state="running", loop=_current_loop)
    launcher = _AGENTS_DIR / "app_launcher.py"
    result = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=str(_REPO_ROOT),
        timeout=300,
    )
    if result.returncode != 0:
        print(f"[orchestrator] app_launcher.py failed (exit {result.returncode}) — tester will mark inconclusive")
    return _run_agent(
        "tester",
        f"Read {_WORKSPACE}/screenshots/launcher_meta.json, "
        f"then read each screenshot in {_WORKSPACE}/screenshots/. "
        + (f"Also read {_WORKSPACE}/spec.json for context on what changed. " if _file_exists("spec.json") else "")
        + f"Produce {_WORKSPACE}/live_test_report.json.",
        timeout_s=900,
    )


def phase_pm_decision() -> bool:
    inputs = []
    for f in ("spec.json", "design_review.json", "qa_report.json"):
        if _file_exists(f):
            inputs.append(f"{_WORKSPACE}/{f}")
    if _file_exists("live_test_report.json"):
        inputs.append(f"{_WORKSPACE}/live_test_report.json")

    return _run_agent(
        "pm",
        f"Run in DECISION mode. "
        f"Read these files: {', '.join(inputs)}. "
        f"Produce {_WORKSPACE}/pm_decision.json.",
        timeout_s=900,
    )


# -- Full pipeline ---------------------------------------------------------

def run_full_pipeline() -> int:
    global _current_loop

    print(f"[orchestrator] [{_ts()}] === Invoy Pipeline Start ===")
    _write_status(phase="start", state="running", loop=0)

    # Phase 1: PM Spec (skip if spec.json already exists)
    if (_WORKSPACE / "spec.json").exists():
        print("[orchestrator] spec.json already present — skipping PM spec phase")
    else:
        _current_loop = 0
        if not phase_pm_spec():
            print("[orchestrator] Pipeline aborted: PM spec phase failed")
            _write_status(phase="pm_spec", state="failed", loop=0)
            return 2

    for loop in range(1, _MAX_LOOPS + 1):
        _current_loop = loop
        _LOOP_FILE.write_text(str(loop))
        print(f"\n[orchestrator] [{_ts()}] ===== LOOP {loop}/{_MAX_LOOPS} =====")
        _write_status(phase="loop_start", state="running", loop=loop)

        # Phase 2: Programmer
        if not phase_programmer():
            print("[orchestrator] Pipeline aborted: Programmer phase failed")
            _write_status(phase="programmer", state="failed", loop=loop)
            return 2

        # Phase 3a: Designer (non-fatal)
        phase_designer()

        # Phase 3b: QA (non-fatal)
        phase_qa()

        # Phase 3c: Testing Agent (skip if critical static issues)
        if not _has_critical_issues():
            phase_tester()
        else:
            print("[orchestrator] Skipping Testing Agent — critical issues in static checks")
            _write_status(phase="tester", state="skipped", loop=loop,
                          extra={"reason": "critical issues in designer/qa"})

        # Phase 4: PM Decision
        if not phase_pm_decision():
            print("[orchestrator] Pipeline aborted: PM decision phase failed")
            _write_status(phase="pm_decision", state="failed", loop=loop)
            return 2

        decision = _read_json("pm_decision.json")
        verdict  = decision.get("verdict", "fail")
        rework   = decision.get("rework_instructions", "")
        summary  = decision.get("summary", "")

        print(f"\n[orchestrator] [{_ts()}] PM VERDICT: {verdict.upper()}")
        print(f"[orchestrator]   {summary[:120]}")

        if verdict == "pass":
            _print_pass_summary(decision)
            _write_status(phase="complete", state="passed", loop=loop,
                          extra={"verdict": "pass", "summary": summary})
            _archive_workspace()
            print(f"[orchestrator] [{_ts()}] === Pipeline Complete - PASSED ===")
            return 0

        if verdict == "fail" or loop >= _MAX_LOOPS:
            _print_fail_summary(decision, loop)
            _write_status(phase="complete", state="failed", loop=loop,
                          extra={"verdict": verdict, "summary": summary,
                                 "blockers": decision.get("blockers", [])})
            print(f"[orchestrator] [{_ts()}] === Pipeline Complete - FAILED ===")
            return 1

        # verdict == "rework" — continue loop
        print(f"[orchestrator] [{_ts()}] Rework required (loop {loop}/{_MAX_LOOPS})")
        print(f"[orchestrator]   Instructions: {rework[:200]}")
        _write_status(phase="rework", state="running", loop=loop,
                      extra={"rework_instructions": rework})

    return 1


# -- Summary helpers -------------------------------------------------------

def _print_pass_summary(decision: dict) -> None:
    print("\n[PASS] All checks passed.")
    print(f"  {decision.get('summary', '')}")
    spec = _read_json("spec.json")
    files = spec.get("files_to_change", [])
    if files:
        print(f"  Changed files: {', '.join(files)}")
    print("  Review changes and commit when ready.")


def _print_fail_summary(decision: dict, loops: int) -> None:
    print(f"\n[FAIL] Pipeline failed after {loops} loop(s).")
    print(f"  {decision.get('summary', '')}")
    for b in decision.get("blockers", []):
        print(f"  [{b.get('severity','?').upper()}] {b.get('source','?')}: {b.get('id','?')}")
    if decision.get("rework_instructions"):
        print(f"  Rework needed: {decision['rework_instructions']}")


# -- Entry point -----------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Invoy multi-agent pipeline orchestrator")
    parser.add_argument(
        "--phase",
        choices=["all", "qa-only", "tester-only"],
        default="all",
    )
    parser.add_argument(
        "--if-spec-present",
        action="store_true",
        help="Only run if spec.json exists in workspace (for hook use)",
    )
    parser.add_argument(
        "--trigger",
        default="manual",
        help="Trigger source for logging (e.g. post-commit)",
    )
    args = parser.parse_args()

    if args.if_spec_present and not _file_exists("spec.json"):
        print("[orchestrator] No active spec — skipping")
        sys.exit(0)

    _WORKSPACE.mkdir(parents=True, exist_ok=True)
    (_WORKSPACE / "screenshots").mkdir(parents=True, exist_ok=True)

    print(f"[orchestrator] Trigger: {args.trigger}  Phase: {args.phase}")

    if args.phase == "all":
        sys.exit(run_full_pipeline())

    elif args.phase == "qa-only":
        ok = phase_qa()
        sys.exit(0 if ok else 1)

    elif args.phase == "tester-only":
        ok = phase_tester()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
