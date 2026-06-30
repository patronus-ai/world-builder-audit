"""Deterministic scripts for the lint-fix loop (LFL) infrastructure
and Stage 14 golden-solution presence.

Covered checks:
  reward_lint_fix_loop.a_reward_linter_binary_exists_and_is_wired_into_the
  reward_lint_fix_loop.every_rule_listed_in_the_gym_s_lint_rule_manifest
  stage_14_golden_solution.solution_yaml_parses_every_entity_reference_resolves  (presence + parse)
"""
from __future__ import annotations

import re
from pathlib import Path

from _common import (
    CheckResult, GYM, list_drafts, load_yaml, gym_wide_result, bucket_to_result,
    STAGES,
)


def reward_linter_exists_and_wired() -> CheckResult:
    """LFLC1 — `reward_linter.py` exists AND `run.py` references it."""
    linter = STAGES / "reward_linter.py"
    run_py = GYM / "task-designer" / "run.py"
    exists = linter.exists()
    wired = False
    if run_py.exists():
        text = run_py.read_text()
        wired = "reward_linter" in text or "_lint_fix_loop" in text or "lint_fix" in text
    passed = exists and wired
    return gym_wide_result(
        "a_reward_linter_binary_exists_and_is_wired_into_the",
        passed=passed,
        evidence=[
            f"`task-designer/stages/reward_linter.py` exists: {exists}",
            f"`task-designer/run.py` references the linter or lint-fix loop: {wired}",
        ],
        remediation=(
            None if passed else
            "Add the linter under `task-designer/stages/` and wire its invocation into `run.py`'s pipeline."
        ),
    )


def every_lint_rule_in_manifest_exists() -> CheckResult:
    """LFLC2 — every `_check_*` referenced by the manifest exists in code.

    Manifest = `audit/CHECKS.md` (per-check reference doc). Each rule referenced
    in the linters section must have a `def _check_<name>` somewhere in
    `task-designer/stages/*.py`.
    """
    manifest = GYM / "audit" / "CHECKS.md"
    linter_src_paths = list((STAGES).glob("*.py"))
    src_text = "\n".join(p.read_text(errors="ignore") for p in linter_src_paths if p.is_file())
    declared_defs = set(re.findall(r"^\s*def\s+(_check_[A-Za-z0-9_]+)", src_text, re.MULTILINE))

    referenced = set()
    if manifest.exists():
        for m in re.finditer(r"_check_[A-Za-z0-9_]+", manifest.read_text()):
            referenced.add(m.group(0))

    if not referenced:
        return CheckResult(
            check_id="every_rule_listed_in_the_gym_s_lint_rule_manifest",
            level="skipped", score=None,
            evidence=[f"No `_check_*` references found in `audit/CHECKS.md` — manifest absent or empty for linter rules."],
            passing_tasks=None, failing_tasks=None,
        )

    missing = sorted(referenced - declared_defs)
    passed = not missing
    return gym_wide_result(
        "every_rule_listed_in_the_gym_s_lint_rule_manifest",
        passed=passed,
        evidence=[
            f"Manifest declares {len(referenced)} `_check_*` rules.",
            f"Codebase defines {len(declared_defs)} `_check_*` functions under task-designer/stages/.",
            (f"All manifest rules implemented." if passed else f"Missing in code: {missing[:8]}" + (" …" if len(missing) > 8 else "")),
        ],
        remediation=None if passed else "Add the missing `_check_*` functions or remove them from the manifest.",
    )


def golden_solution_yaml_parses() -> CheckResult:
    """S14C1 — solution YAML exists and parses for every shipped task."""
    solutions = GYM / "task_data" / "solutions"
    if not solutions.exists():
        return CheckResult(
            check_id="solution_yaml_parses_every_entity_reference_resolves",
            level="skipped", score=None,
            evidence=["`task_data/solutions/` directory not found."],
            passing_tasks=None, failing_tasks=None,
        )
    pf, ff, na = [], [], []
    # We iterate solution files (not drafts) because this check is about shipped goldens.
    for sol in sorted(solutions.glob("task_*_solution.yaml")):
        task_id = sol.name.replace("_solution.yaml", "")
        doc = load_yaml(sol)
        if doc is None:
            ff.append(task_id)
        else:
            pf.append(task_id)
    return bucket_to_result(
        "solution_yaml_parses_every_entity_reference_resolves", pf, ff, na,
        evidence_extra=[f"Checked every `task_data/solutions/task_*_solution.yaml` parses via yaml.safe_load."],
    )


CHECKS: list[tuple[str, callable]] = [
    ("reward_lint_fix_loop.a_reward_linter_binary_exists_and_is_wired_into_the", reward_linter_exists_and_wired),
    ("reward_lint_fix_loop.every_rule_listed_in_the_gym_s_lint_rule_manifest", every_lint_rule_in_manifest_exists),
    ("stage_14_golden_solution.solution_yaml_parses_every_entity_reference_resolves", golden_solution_yaml_parses),
]
