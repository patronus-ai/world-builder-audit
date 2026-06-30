"""Deterministic scripts for Stage 2 — Goals (excluding the floor-check, which lives in floor_checks.py)."""
from __future__ import annotations

import yaml

from _common import (
    CheckResult, list_drafts, load_stage, bucket_to_result, GYM,
)

CONFIG_PATH = GYM / "task-designer" / "config.yaml"


def _config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return yaml.safe_load(CONFIG_PATH.read_text()) or {}
    except Exception:
        return {}


def all_goal_ids_are_unique_within_the_task() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s02 = load_stage(draft, "02")
        if not s02:
            na.append(draft.name); continue
        goals = (s02.get("goal_graph") or {}).get("goals") or []
        if len(goals) < 2:
            na.append(draft.name); continue   # uniqueness vacuous for <2 goals
        ids = [g.get("id") for g in goals if isinstance(g, dict)]
        (pf if len(ids) == len(set(ids)) else ff).append(draft.name)
    return bucket_to_result(
        "all_goal_ids_are_unique_within_the_task", pf, ff, na,
        evidence_extra=["Reads `stage_02.goal_graph.goals[].id`; passes iff all IDs distinct."],
    )


def goal_count_is_within_band() -> CheckResult:
    band = ((_config().get("structure") or {}).get("goal_count")) or {}
    lo = band.get("min")
    hi = band.get("max")
    if lo is None and hi is None:
        return CheckResult(
            check_id="goal_count_is_within_band",
            level="skipped", score=None,
            evidence=["`config.structure.goal_count` band not declared — check is N/A everywhere."],
            passing_tasks=[], failing_tasks=[],
        )
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s02 = load_stage(draft, "02")
        if not s02:
            na.append(draft.name); continue
        n = len((s02.get("goal_graph") or {}).get("goals") or [])
        ok = (lo is None or n >= lo) and (hi is None or n <= hi)
        (pf if ok else ff).append(draft.name)
    return bucket_to_result(
        "goal_count_is_within_band", pf, ff, na,
        evidence_extra=[f"Band: min={lo} max={hi}; compared `len(goal_graph.goals)` against it per draft."],
    )


def every_goal_type_in_closed_enum() -> CheckResult:
    """S2C4 — Every Goal.type is in the GoalType enum (statically scanned)."""
    enum_src = GYM / "task-designer" / "models" / "goals.py"
    text = enum_src.read_text() if enum_src.exists() else ""
    import re
    closed = set(re.findall(r"^\s+([A-Z_]+)\s*=\s*\"[^\"]+\"\s*$", text, re.MULTILINE))
    # Also accept lowercase values (the actual enum values, not the constants)
    values = set(re.findall(r"=\s*\"([^\"]+)\"", text))
    accept = closed | values
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s02 = load_stage(draft, "02")
        if not s02:
            na.append(draft.name); continue
        goals = (s02.get("goal_graph") or {}).get("goals") or []
        if not any("type" in g for g in goals if isinstance(g, dict)):
            na.append(draft.name); continue
        bad = [g.get("type") for g in goals if isinstance(g, dict) and g.get("type") and g.get("type") not in accept]
        (ff if bad else pf).append(draft.name)
    return bucket_to_result(
        "every_is_a_member_of_the_closed_enum", pf, ff, na,
        evidence_extra=[f"Enum/values scanned from `models/goals.py`: {len(accept)} accepted tokens."],
    )


def subgoal_ids_unique_across_the_task() -> CheckResult:
    """S3C5 — Subgoals[].id all unique."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s03 = load_stage(draft, "03")
        if not s03:
            na.append(draft.name); continue
        subs = (s03.get("goal_graph") or {}).get("subgoals") or []
        if len(subs) < 2:
            na.append(draft.name); continue
        ids = [s.get("id") for s in subs if isinstance(s, dict)]
        (pf if len(ids) == len(set(ids)) else ff).append(draft.name)
    return bucket_to_result(
        "subgoal_ids_unique_across_the_task", pf, ff, na,
        evidence_extra=["Reads `stage_03.goal_graph.subgoals[].id`; passes iff all IDs distinct."],
    )


def every_subgoal_references_real_goal() -> CheckResult:
    """S3C2 — Every subgoal's parent goal exists."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s03 = load_stage(draft, "03")
        if not s03:
            na.append(draft.name); continue
        gg = s03.get("goal_graph") or {}
        goal_ids = {g.get("id") for g in (gg.get("goals") or [])}
        subs = gg.get("subgoals") or []
        if not subs:
            na.append(draft.name); continue
        # Field name varies across gym versions
        def _parent(s): return s.get("parent_goal_id") or s.get("parent_id") or s.get("goal_id")
        orphans = [s for s in subs if isinstance(s, dict) and _parent(s) not in goal_ids]
        (ff if orphans else pf).append(draft.name)
    return bucket_to_result(
        "every_subgoal_s_references_a_real_goal", pf, ff, na,
        evidence_extra=["Reads subgoal `parent_goal_id`; passes iff every parent resolves to a goal in the same draft."],
    )


CHECKS: list[tuple[str, callable]] = [
    ("stage_2_goals.all_goal_ids_are_unique_within_the_task", all_goal_ids_are_unique_within_the_task),
    ("stage_2_goals.goal_count_is_within_band", goal_count_is_within_band),
    ("stage_2_goals.every_is_a_member_of_the_closed_enum", every_goal_type_in_closed_enum),
    ("stage_3_subgoals_and_q_a_chains.subgoal_ids_unique_across_the_task", subgoal_ids_unique_across_the_task),
    ("stage_3_subgoals_and_q_a_chains.every_subgoal_s_references_a_real_goal", every_subgoal_references_real_goal),
]
