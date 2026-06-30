"""Deterministic floor-checks — every task must satisfy these structural invariants.

Covered checks:
  stage_2_goals.task_emits_at_least_one_goal
  stage_6_reward_declarations_coverage_manifest.task_emits_at_least_one_reward
  stage_7b_yaml_skeleton.task_has_non_empty_prompt
  stage_7b_yaml_skeleton.task_declares_at_least_one_tool
"""
from __future__ import annotations

from _common import (
    CheckResult, list_drafts, load_stage, load_yaml,
    bucket_to_result,
)


def task_emits_at_least_one_goal() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s02 = load_stage(draft, "02")
        if not s02:
            na.append(draft.name); continue
        goals = (s02.get("goal_graph") or {}).get("goals") or []
        (pf if len(goals) >= 1 else ff).append(draft.name)
    return bucket_to_result(
        "task_emits_at_least_one_goal", pf, ff, na,
        evidence_extra=["Reads `stage_02.json[goal_graph][goals]`; passes when len ≥ 1."],
    )


def task_emits_at_least_one_reward() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s06 = load_stage(draft, "06")
        if not s06:
            na.append(draft.name); continue
        rewards = (s06.get("reward_skeleton") or {}).get("templates") or []
        (pf if len(rewards) >= 1 else ff).append(draft.name)
    return bucket_to_result(
        "task_emits_at_least_one_reward", pf, ff, na,
        evidence_extra=["Reads `stage_06.json[reward_skeleton][templates]`; passes when len ≥ 1."],
    )


def task_has_non_empty_prompt() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = draft / "skeleton.yaml"
        if not sk.exists():
            na.append(draft.name); continue
        doc = load_yaml(sk) or {}
        prompt = ((doc.get("task") or {}).get("prompt") or "")
        (pf if str(prompt).strip() else ff).append(draft.name)
    return bucket_to_result(
        "task_has_non_empty_prompt", pf, ff, na,
        evidence_extra=["Reads `skeleton.yaml[task][prompt]`; passes when stripped length > 0."],
    )


def task_declares_at_least_one_tool() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = draft / "skeleton.yaml"
        if not sk.exists():
            na.append(draft.name); continue
        doc = load_yaml(sk) or {}
        tools = (doc.get("task") or {}).get("tools") or []
        (pf if len(tools) >= 1 else ff).append(draft.name)
    return bucket_to_result(
        "task_declares_at_least_one_tool", pf, ff, na,
        evidence_extra=["Reads `skeleton.yaml[task][tools]`; passes when len ≥ 1."],
    )


CHECKS: list[tuple[str, callable]] = [
    ("stage_2_goals.task_emits_at_least_one_goal", task_emits_at_least_one_goal),
    ("stage_6_reward_declarations_coverage_manifest.task_emits_at_least_one_reward", task_emits_at_least_one_reward),
    ("stage_7b_yaml_skeleton.task_has_non_empty_prompt", task_has_non_empty_prompt),
    ("stage_7b_yaml_skeleton.task_declares_at_least_one_tool", task_declares_at_least_one_tool),
]
