"""Deterministic scripts for Stage 5 — Action matrix."""
from __future__ import annotations

import re
from pathlib import Path

from _common import (
    CheckResult, GYM, list_drafts, load_stage, bucket_to_result,
)


# Build the registered reward kinds once. Used by the "verb maps to known
# reward kind" check below.
def _registered_reward_kinds() -> set[str]:
    out: set[str] = set()
    base = GYM / "gym_github" / "reward_compiler"
    if not base.exists():
        return out
    for py in base.rglob("*.py"):
        try:
            text = py.read_text(errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r'@register\(["\']([^"\']+)["\']', text):
            out.add(m.group(1))
    return out


_KIND_TO_VERB_HINT = {
    "edit_file": ("file_content_added", "file_content_removed", "file_content_replaced", "file_content_contains", "agent_edited_file"),
    "create_issue": ("agent_created_issue",),
    "create_pr": ("agent_created_pr", "all_agent_prs_from_branch"),
    "delete_branch": ("branch_deleted",),
    "create_branch": ("branch_exists",),
    "add_collaborator": ("collaborator_added",),
    "commit": ("commit_message",),
    "create_file": ("agent_created_file",),
    "delete_file": ("file_deleted",),
    "create_gist": ("agent_created_gist",),
    "edit_wiki": ("agent_edited_wiki",),
    "visit_url": ("agent_visited_url",),
}


def every_action_entry_has_a_target_entity_declared_in_the() -> CheckResult:
    """S5C1 — every action entry binds to a declared entity."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s05 = load_stage(draft, "05")
        if not s05:
            na.append(draft.name); continue
        am = s05.get("action_matrix") or {}
        entries = am.get("entries") or []
        designations = am.get("entity_designations") or []
        if not entries:
            na.append(draft.name); continue
        declared = {
            (d.get("entity", {}).get("entity_type"), d.get("entity", {}).get("entity_id"))
            for d in designations
            if isinstance(d, dict)
        }
        bad = [
            e for e in entries
            if (e.get("entity", {}).get("entity_type"), e.get("entity", {}).get("entity_id")) not in declared
        ]
        (ff if bad else pf).append(draft.name)
    return bucket_to_result(
        "every_action_entry_has_a_target_entity_declared_in_the", pf, ff, na,
        evidence_extra=["Every `entries[i].entity` must appear in `entity_designations`."],
    )


def no_duplicate_pairs() -> CheckResult:
    """S5C3 — no duplicate (entity, verb) pairs in the action matrix."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s05 = load_stage(draft, "05")
        if not s05:
            na.append(draft.name); continue
        entries = (s05.get("action_matrix") or {}).get("entries") or []
        if len(entries) < 2:
            na.append(draft.name); continue
        pairs = [
            (e.get("entity", {}).get("entity_id"), e.get("action"))
            for e in entries
        ]
        (pf if len(pairs) == len(set(pairs)) else ff).append(draft.name)
    return bucket_to_result(
        "no_duplicate_pairs", pf, ff, na,
        evidence_extra=["Compares `len(entries)` to `len(set((entity_id, action)))` per draft."],
    )


def every_verb_in_the_matrix_maps_to_a_known_reward_kind() -> CheckResult:
    """S5C4 — every action verb is a member of the closed ActionVerb enum.

    The closed-set discipline is enforced by `models/action_matrix.py`'s
    `ActionVerb` StrEnum. We extract the enum values once and check every
    action in every draft's matrix.
    """
    enum_src = GYM / "task-designer" / "models" / "action_matrix.py"
    text = enum_src.read_text() if enum_src.exists() else ""
    accepted = set(re.findall(r'^\s+[A-Z_]+\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE))
    pf, ff, na = [], [], []
    if not accepted:
        return CheckResult(
            check_id="every_verb_in_the_matrix_maps_to_a_known_reward_kind",
            level="skipped", score=None,
            evidence=[f"Could not parse `ActionVerb` enum from {enum_src}."],
            passing_tasks=None, failing_tasks=None,
        )
    for draft in list_drafts():
        s05 = load_stage(draft, "05")
        if not s05:
            na.append(draft.name); continue
        entries = (s05.get("action_matrix") or {}).get("entries") or []
        if not entries:
            na.append(draft.name); continue
        verbs = {e.get("action") for e in entries if e.get("action")}
        unknown = sorted(v for v in verbs if v not in accepted)
        (ff if unknown else pf).append(draft.name)
    return bucket_to_result(
        "every_verb_in_the_matrix_maps_to_a_known_reward_kind", pf, ff, na,
        evidence_extra=[
            f"ActionVerb enum has {len(accepted)} accepted verbs (parsed from `task-designer/models/action_matrix.py`).",
            "Passes when every `entries[i].action` is in that closed set.",
        ],
    )


CHECKS: list[tuple[str, callable]] = [
    ("stage_5_action_matrix.every_action_entry_has_a_target_entity_declared_in_the", every_action_entry_has_a_target_entity_declared_in_the),
    ("stage_5_action_matrix.no_duplicate_pairs", no_duplicate_pairs),
    ("stage_5_action_matrix.every_verb_in_the_matrix_maps_to_a_known_reward_kind", every_verb_in_the_matrix_maps_to_a_known_reward_kind),
]
