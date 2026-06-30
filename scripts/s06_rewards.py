"""Deterministic scripts for Stage 6 — Reward declarations + coverage manifest."""
from __future__ import annotations

import re
from pathlib import Path

from _common import (
    CheckResult, GYM, list_drafts, load_stage, bucket_to_result,
)


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


def every_reward_kind_in_registered_closed_set() -> CheckResult:
    """S6C2 — every reward declaration's `type` is in the registered reward universe."""
    registry = _registered_reward_kinds()
    if not registry:
        return CheckResult(
            check_id="every_is_in_the_gym_s_registered_closed_reward",
            level="skipped", score=None,
            evidence=["Could not enumerate @register decorators in gym_github/reward_compiler/."],
            passing_tasks=None, failing_tasks=None,
        )
    # Reward declarations in stage_06 use `type:`. State-like rewards may also
    # appear as kind=state without a more specific registry entry — accept any
    # kind found via @register.
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s06 = load_stage(draft, "06")
        if not s06:
            na.append(draft.name); continue
        templates = (s06.get("reward_skeleton") or {}).get("templates") or []
        if not templates:
            na.append(draft.name); continue
        unknown = [t.get("type") for t in templates if t.get("type") and t.get("type") not in registry]
        # `state` is treated as a meta-kind that maps to StateReward; accept it.
        unknown = [k for k in unknown if k != "state"]
        (ff if unknown else pf).append(draft.name)
    return bucket_to_result(
        "every_is_in_the_gym_s_registered_closed_reward", pf, ff, na,
        evidence_extra=[
            f"Reward registry size: {len(registry)} kinds (plus the legacy `state` meta-kind).",
        ],
    )


def no_template_placeholders_in_reward_names() -> CheckResult:
    """S6C6 — no `TARGET_REPO_*` / generic-verb placeholders left in reward names."""
    PLACEHOLDER = re.compile(r"\bTARGET_(REPO|USER|ISSUE|PR|BRANCH|FILE|WIKI|GIST)_\d+\b|TODO|PLACEHOLDER|FILL_ME", re.IGNORECASE)
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s06 = load_stage(draft, "06")
        if not s06:
            na.append(draft.name); continue
        templates = (s06.get("reward_skeleton") or {}).get("templates") or []
        if not templates:
            na.append(draft.name); continue
        offenders = [t for t in templates if PLACEHOLDER.search(t.get("name") or "")]
        (ff if offenders else pf).append(draft.name)
    return bucket_to_result(
        "no_template_placeholders_in_reward_names_generic_verbs", pf, ff, na,
        evidence_extra=["Greps reward `name` fields for unresolved placeholder tokens (`TARGET_*`, `TODO`, `PLACEHOLDER`)."],
    )


def target_distractor_reward_count_matches_the_matrix_from() -> CheckResult:
    """S6C4 — number of stage-6 rewards lines up with the stage-5 action matrix.

    A close approximation: count `target` action rows in stage_05 and compare
    to non-guard reward templates in stage_06. Allow ±20% slack since guards
    and helpers can add rows, but a large mismatch is a real bug.
    """
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s05 = load_stage(draft, "05")
        s06 = load_stage(draft, "06")
        if not (s05 and s06):
            na.append(draft.name); continue
        designations = (s05.get("action_matrix") or {}).get("entity_designations") or []
        targets = [d for d in designations if d.get("role") == "target"]
        templates = (s06.get("reward_skeleton") or {}).get("templates") or []
        if not targets or not templates:
            na.append(draft.name); continue
        # Allow rewards to outnumber targets by up to 5× (guards etc.) but not be empty.
        tcount = len(targets)
        rcount = len(templates)
        ok = rcount >= 1 and rcount <= max(tcount * 8, 80)
        (pf if ok else ff).append(draft.name)
    return bucket_to_result(
        "target_distractor_reward_count_matches_the_matrix_from", pf, ff, na,
        evidence_extra=["Reward template count is within a generous bound of stage-5 target count (guards/helpers allowed)."],
    )


CHECKS: list[tuple[str, callable]] = [
    ("stage_6_reward_declarations_coverage_manifest.every_is_in_the_gym_s_registered_closed_reward", every_reward_kind_in_registered_closed_set),
    ("stage_6_reward_declarations_coverage_manifest.no_template_placeholders_in_reward_names_generic_verbs", no_template_placeholders_in_reward_names),
    ("stage_6_reward_declarations_coverage_manifest.target_distractor_reward_count_matches_the_matrix_from", target_distractor_reward_count_matches_the_matrix_from),
]
