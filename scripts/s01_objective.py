"""Deterministic scripts for Stage 1 — Objective."""
from __future__ import annotations

import json
import re

from _common import (
    CheckResult, list_drafts, load_stage, load_yaml, bucket_to_result,
    gym_wide_result, TABLES,
)


def exists_in_closed_set() -> CheckResult:
    """S1C1 — task_type_id ∈ goal_decompositions.yaml closed set."""
    table = load_yaml(TABLES / "goal_decompositions.yaml") or {}
    closed_ids = {row["id"] for row in (table.get("task_types") or [])}
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s01 = load_stage(draft, "01")
        if not s01:
            na.append(draft.name); continue
        ttid = s01.get("task_type_id")
        if ttid is None:
            na.append(draft.name); continue
        (pf if ttid in closed_ids else ff).append(draft.name)
    return bucket_to_result(
        "exists_in_closed_set", pf, ff, na,
        evidence_extra=[
            f"Closed set has {len(closed_ids)} task_type_ids in tables/goal_decompositions.yaml.",
        ],
    )


def description_floor_and_entity_kind() -> CheckResult:
    """S1C2 — description ≥ 20 chars AND names a concrete entity kind."""
    KIND_TOKENS = re.compile(
        r"\b(repo|repos|repository|file|files|wiki|issue|issues|pr|prs|"
        r"pull request|branch|branches|commit|commits|gist|test|tests|"
        r"directory|folder|document|page|library|function|class)\b",
        re.IGNORECASE,
    )
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s01 = load_stage(draft, "01")
        if not s01:
            na.append(draft.name); continue
        desc = (s01.get("objective_description") or s01.get("description") or "").strip()
        if not desc:
            na.append(draft.name); continue
        long_enough = len(desc) >= 20
        names_kind = bool(KIND_TOKENS.search(desc))
        (pf if (long_enough and names_kind) else ff).append(draft.name)
    return bucket_to_result(
        "20_chars_and_names_at_least_one_concrete_entity_kind", pf, ff, na,
        evidence_extra=[
            "Reads `stage_01.description`; passes if len ≥ 20 and the text mentions at least one schema entity kind.",
        ],
    )


def stage_is_deterministic_running_twice() -> CheckResult:
    """S1C4 — code-level property: stage source must not use unseeded randomness."""
    src = (TABLES.parent / "stages" / "s01_objective.py")
    text = src.read_text() if src.exists() else ""
    smells = []
    for pat in (r"\brandom\.(?!seed\()", r"\buuid\.uuid4\(", r"\btime\.time\(", r"\bdatetime\.now\("):
        if re.search(pat, text):
            smells.append(pat)
    passed = not smells
    return gym_wide_result(
        "stage_is_deterministic_running_twice_with_the_same",
        passed=passed,
        evidence=[
            f"Scanned `task-designer/stages/s01_objective.py` for unseeded randomness markers.",
            (
                "No `random.<call>`/`uuid4`/`time.time`/`datetime.now` found — stage relies on table lookup + explicit seed."
                if passed else
                f"Found suspicious patterns: {smells}. Verify they are seeded."
            ),
        ],
        remediation=(
            None if passed else
            "Audit the stage code for `random`, `uuid4`, `time.time`, dict iteration; introduce a seeded RNG."
        ),
    )


CHECKS: list[tuple[str, callable]] = [
    ("stage_1_objective.exists_in_closed_set", exists_in_closed_set),
    ("stage_1_objective.20_chars_and_names_at_least_one_concrete_entity_kind", description_floor_and_entity_kind),
    ("stage_1_objective.stage_is_deterministic_running_twice_with_the_same", stage_is_deterministic_running_twice),
]
