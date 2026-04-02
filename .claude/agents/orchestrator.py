"""
Invoy Multi-Agent Orchestrator

Sequences the five-phase pipeline by invoking the `claude` CLI headlessly
for each agent role. Agents communicate through structured files in
.claude/agents/workspace/current/.

Usage:
    python .claude/agents/orchestrator.py --phase all
    python .claude/agents/orchestrator.py --phase qa-only [--if-spec-present] [--trigger post-commit]
    python .claude/agents/orchestrator.py --phase tester-only

Phases:
    all          Full pipeline: PM(spec) → Prog → Designer → QA → Tester → PM(decision)
    qa-only      Static QA only (used by post-commit hook)
    tester-only  app_launcher + Testing Agent only

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

# ── Paths ─────────────────────────────────────────────────────────────────

_AGENTS_DIR   = Path(__file__).parent
_ROLES_DIR    = _AGENTS_DIR / "roles"
_WORKSPACE    = _AGENTS_DIR / "workspace" / "current"
_ARCHIVE_DIR  = _AGENTS_DIR / "workspace" / "archive"
_REPO_ROOT    = Path(__file__).parents[2]
def _find_claude() -> str:
    """Locate the claude CLI binary, checking common Windows install paths."""
    import glob as _glob
    # Check PATH first (works in terminals where claude wrapper is present)
    import shutil as _shutil
    found = _shutil.which("claude")
    if found:
        return found
    # Claude Code desktop app installs under AppData/Local/AnthropicClaude/app-*/
    pattern = str(Path.home() / "AppData" / "Local" / "AnthropicClaude" / "app-*" / "claude.exe")
    matches = sorted(_glob.glob(pattern), reverse=True)  # newest version first
    if matches:
        return matches[0]
    return "claude"   # fallback — will fail with clear FileNotFoundError

_CLAUDE_BIN = _find_claude()

_MAX_LOOPS    = 3
_LOOP_FILE    = _WORKSPACE / ".loop_count"


# ── Utilities ─────────────────────────────────────────────────────────────

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
    print(f"[orchestrator] Workspace archived → {dest}")


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


# ── Agent invocation ──────────────────────────────────────────────────────

def _run_agent(role: str, task_prompt: str, timeout_s: int = 300) -> bool:
    """
    Invoke `claude --print --system <role_file> <task_prompt>`.
    Returns True if the agent ran successfully (exit code 0).
    """
    role_file = _ROLES_DIR / f"{role}.md"
    if not role_file.exists():
        print(f"[orchestrator] ERROR: role file not found: {role_file}")
        return False

    system_prompt = role_file.read_text(encoding="utf-8")

    # Inject workspace context into the task prompt
    full_prompt = (
        f"Working directory: {_REPO_ROOT}\n"
        f"Workspace: {_WORKSPACE}\n\n"
        f"{task_prompt}"
    )

    print(f"\n[orchestrator] --- Running {role.upper()} agent ---")

    env = os.environ.copy()
    env["NODE_NO_WARNINGS"] = "1"   # suppress Node.js deprecation warnings
    env["PYTHONUTF8"] = "1"         # ensure UTF-8 stdout on Windows

    result = subprocess.run(
        [_CLAUDE_BIN, "--print", "--system", system_prompt, full_prompt],
        cwd=str(_REPO_ROOT),
        timeout=timeout_s,
        capture_output=False,   # let agent output stream to terminal
        text=True,
        env=env,
    )
    if result.returncode != 0:
        print(f"[orchestrator] {role} agent exited with code {result.returncode}")
        return False
    return True


# ── Pipeline phases ───────────────────────────────────────────────────────

def phase_pm_spec() -> bool:
    if not _file_exists("request.md"):
        print("[orchestrator] ERROR: request.md not found in workspace/current/")
        return False
    return _run_agent(
        "pm",
        "Run in SPEC mode. "
        f"Read {_WORKSPACE}/request.md. "
        f"Produce {_WORKSPACE}/spec.json per the schema in your role file.",
        timeout_s=120,
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
        timeout_s=600,
    )


def phase_designer() -> bool:
    if not _file_exists("implementation.md"):
        print("[orchestrator] ERROR: implementation.md not found — Programmer must run first")
        return False
    return _run_agent(
        "designer",
        f"Read {_WORKSPACE}/spec.json and {_WORKSPACE}/implementation.md, "
        f"then read every file listed in spec.json files_to_change. "
        f"Produce {_WORKSPACE}/design_review.json.",
        timeout_s=180,
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
        timeout_s=180,
    )


def phase_tester() -> bool:
    """Run app_launcher.py then the Testing Agent."""
    print("\n[orchestrator] ── Running app_launcher.py ──")
    launcher = _AGENTS_DIR / "app_launcher.py"
    result = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=str(_REPO_ROOT),
        timeout=300,
    )
    if result.returncode != 0:
        print(f"[orchestrator] app_launcher.py failed (exit {result.returncode})")
        # Don't abort pipeline — tester will mark inconclusive
    return _run_agent(
        "tester",
        f"Read {_WORKSPACE}/screenshots/launcher_meta.json, "
        f"then read each screenshot in {_WORKSPACE}/screenshots/. "
        + (f"Also read {_WORKSPACE}/spec.json for context on what changed. " if _file_exists("spec.json") else "")
        + f"Produce {_WORKSPACE}/live_test_report.json.",
        timeout_s=180,
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
        timeout_s=120,
    )


# ── Full pipeline ─────────────────────────────────────────────────────────

def run_full_pipeline() -> int:
    print("[orchestrator] ═══ Invoy Pipeline Start ═══")

    # Phase 1: PM Spec (skip if spec.json already exists)
    if (_WORKSPACE / "spec.json").exists():
        print("[orchestrator] spec.json already present — skipping PM spec phase")
    else:
        if not phase_pm_spec():
            print("[orchestrator] Pipeline aborted: PM spec phase failed")
            return 2

    for loop in range(1, _MAX_LOOPS + 1):
        _LOOP_FILE.write_text(str(loop))
        print(f"\n[orchestrator] --- Loop {loop}/{_MAX_LOOPS} ---")

        # Phase 2: Programmer
        if not phase_programmer():
            print("[orchestrator] Pipeline aborted: Programmer phase failed")
            return 2

        # Phase 3a: Designer
        phase_designer()   # non-fatal if it fails — PM will catch missing file

        # Phase 3b: QA
        phase_qa()         # same

        # Phase 3c: Testing Agent (only if no critical static issues)
        if not _has_critical_issues():
            phase_tester()
        else:
            print("[orchestrator] Skipping Testing Agent — critical issues in static checks")

        # Phase 4: PM Decision
        if not phase_pm_decision():
            print("[orchestrator] Pipeline aborted: PM decision phase failed")
            return 2

        decision = _read_json("pm_decision.json")
        verdict  = decision.get("verdict", "fail")

        print(f"\n[orchestrator] PM verdict: {verdict.upper()}")

        if verdict == "pass":
            _print_pass_summary(decision)
            _archive_workspace()
            print("[orchestrator] ═══ Pipeline Complete — PASSED ═══")
            return 0

        if verdict == "fail" or loop >= _MAX_LOOPS:
            _print_fail_summary(decision, loop)
            print("[orchestrator] ═══ Pipeline Complete — FAILED ═══")
            return 1

        # verdict == "rework" — loop
        print(f"[orchestrator] Rework required. Instructions: {decision.get('rework_instructions', '')}")

    return 1


# ── Summary helpers ────────────────────────────────────────────────────────

def _print_pass_summary(decision: dict) -> None:
    print("\n✓ All checks passed.")
    print(f"  {decision.get('summary', '')}")
    spec = _read_json("spec.json")
    files = spec.get("files_to_change", [])
    if files:
        print(f"  Changed files: {', '.join(files)}")
    print("  Review changes and commit when ready.")


def _print_fail_summary(decision: dict, loops: int) -> None:
    print(f"\n✗ Pipeline failed after {loops} loop(s).")
    print(f"  {decision.get('summary', '')}")
    for b in decision.get("blockers", []):
        print(f"  [{b.get('severity','?').upper()}] {b.get('source','?')}: {b.get('id','?')}")
    if decision.get("rework_instructions"):
        print(f"  Rework needed: {decision['rework_instructions']}")


# ── Entry point ───────────────────────────────────────────────────────────

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
