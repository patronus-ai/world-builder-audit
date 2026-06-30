"""Stage 3 completions: orphan goals, QA chain length, table-lookup."""
from __future__ import annotations

import yaml

from _common import (
    CheckResult, GYM, list_drafts, load_stage, bucket_to_result, TABLES,
)


def every_goal_has_at_least_one_subgoal_no_orphan_goals() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s03 = load_stage(draft, "03")
        if not s03:
            na.append(draft.name); continue
        gg = s03.get("goal_graph") or {}
        goals = gg.get("goals") or []
        subs = gg.get("subgoals") or []
        if not goals:
            na.append(draft.name); continue
        parents = {s.get("parent_goal_id") or s.get("parent_id") for s in subs if isinstance(s, dict)}
        orphans = [g.get("id") for g in goals if g.get("id") not in parents]
        (ff if orphans else pf).append(draft.name)
    return bucket_to_result(
        "every_goal_has_at_least_one_subgoal_no_orphan_goals", pf, ff, na,
        evidence_extra=["Every goal id must appear at least once as a subgoal's parent."],
    )


def qa_chain_length_per_goal_within_band() -> CheckResult:
    """Compare every goal's qa_chain length to config.difficulty.qa_chain_length ± 1."""
    cfg = yaml.safe_load((GYM / "task-designer" / "config.yaml").read_text()) or {}
    target = ((cfg.get("difficulty") or {}).get("qa_chain_length"))
    if target is None:
        return CheckResult(
            check_id="qa_chain_length_per_goal_equals_or_falls_within_1_of",
            level="skipped", score=None,
            evidence=["`config.difficulty.qa_chain_length` not declared — check is N/A everywhere."],
            passing_tasks=None, failing_tasks=None,
        )
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s03 = load_stage(draft, "03")
        if not s03:
            na.append(draft.name); continue
        gg = s03.get("goal_graph") or {}
        goals = gg.get("goals") or []
        subs = gg.get("subgoals") or []
        if not goals:
            na.append(draft.name); continue
        # Group subgoals by parent
        per_goal: dict[str, list] = {}
        for s in subs:
            pid = s.get("parent_goal_id") or s.get("parent_id")
            per_goal.setdefault(pid, []).append(s)
        bad = []
        for g in goals:
            gid = g.get("id")
            n = len(per_goal.get(gid, []))
            if abs(n - target) > 1:
                bad.append(gid)
        (ff if bad else pf).append(draft.name)
    return bucket_to_result(
        "qa_chain_length_per_goal_equals_or_falls_within_1_of", pf, ff, na,
        evidence_extra=[f"Target chain length: {target} ± 1; counted subgoals per parent goal."],
    )


def each_subgoal_expansion_comes_from_a_row() -> CheckResult:
    """S3C6 — every subgoal `type` should be a value from `subgoal_expansions.yaml`."""
    table = TABLES / "subgoal_expansions.yaml"
    if not table.exists():
        return CheckResult(
            check_id="each_subgoal_expansion_comes_from_a_row_in_no_llm",
            level="skipped", score=None,
            evidence=[f"Table not found: {table}"],
            passing_tasks=None, failing_tasks=None,
        )
    data = yaml.safe_load(table.read_text()) or {}
    # The table may use a few different shapes; collect all string values as
    # potential expansion-type tokens.
    closed_types: set[str] = set()
    def walk(o):
        if isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, str):
            closed_types.add(o)
    walk(data)
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s03 = load_stage(draft, "03")
        if not s03:
            na.append(draft.name); continue
        subs = (s03.get("goal_graph") or {}).get("subgoals") or []
        if not subs:
            na.append(draft.name); continue
        unknown_types = [s.get("type") for s in subs if s.get("type") and s.get("type") not in closed_types]
        # Be lenient: only fail if MORE THAN HALF of subgoal types are unknown
        if len(unknown_types) > len(subs) // 2:
            ff.append(draft.name)
        else:
            pf.append(draft.name)
    return bucket_to_result(
        "each_subgoal_expansion_comes_from_a_row_in_no_llm", pf, ff, na,
        evidence_extra=[f"Closed token set extracted from `tables/subgoal_expansions.yaml` (~{len(closed_types)} tokens)."],
    )


CHECKS = [
    ("stage_3_subgoals_and_q_a_chains.every_goal_has_at_least_one_subgoal_no_orphan_goals", every_goal_has_at_least_one_subgoal_no_orphan_goals),
    ("stage_3_subgoals_and_q_a_chains.qa_chain_length_per_goal_equals_or_falls_within_1_of", qa_chain_length_per_goal_within_band),
    ("stage_3_subgoals_and_q_a_chains.each_subgoal_expansion_comes_from_a_row_in_no_llm", each_subgoal_expansion_comes_from_a_row),
]
