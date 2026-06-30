"""Stage 8 — Hydrate world YAML: entity-reference closure, prompt grounding."""
from __future__ import annotations

import re
from pathlib import Path

from _common import (
    CheckResult, list_drafts, load_yaml, bucket_to_result,
)


def _hydrated_yaml(draft: Path) -> Path | None:
    """Pick the freshest hydrated world artifact for a draft."""
    cands = list(draft.glob("world_v*.yaml"))
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def _collect_declared_entity_ids(world: dict) -> set[str]:
    """All IDs declared in the world block, across kinds."""
    ids: set[str] = set()
    if not isinstance(world, dict):
        return ids
    for kind, items in world.items():
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and "id" in it:
                    ids.add(str(it["id"]))
    return ids


# Cross-reference fields commonly used across entity kinds. Anything appearing
# in any kind under world.* whose value should resolve to a declared id.
_REF_FIELDS = (
    "owner", "org", "author", "assignee", "assignees",
    "reviewer", "reviewers", "members",
)


def entity_reference_closure() -> CheckResult:
    """S8C2 — every cross-reference field resolves to a declared entity in the same hydrated world."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = _hydrated_yaml(draft)
        if not sk:
            na.append(draft.name); continue
        doc = load_yaml(sk) or {}
        world = doc.get("world") or {}
        declared = _collect_declared_entity_ids(world)
        if not declared:
            na.append(draft.name); continue
        unresolved = []
        for kind, items in world.items():
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                for f in _REF_FIELDS:
                    v = it.get(f)
                    if v is None:
                        continue
                    targets = v if isinstance(v, list) else [v]
                    for t in targets:
                        if isinstance(t, str) and t not in declared:
                            unresolved.append((kind, it.get("id"), f, t))
                            break
                    if unresolved and unresolved[-1][0] == kind:
                        break
        (ff if unresolved else pf).append(draft.name)
    return bucket_to_result(
        "every_cross_reference_field_whatever_names_the_gym", pf, ff, na,
        evidence_extra=[
            f"Cross-reference fields scanned: {_REF_FIELDS}",
            "Passes when every scalar/list ref resolves to a declared `id` in the same hydrated world.",
        ],
    )


def prompt_grounds_reward_entities() -> CheckResult:
    """S8C4 — every entity referenced by a reward template appears in the prompt text."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = _hydrated_yaml(draft)
        if not sk:
            na.append(draft.name); continue
        doc = load_yaml(sk) or {}
        task = doc.get("task") or {}
        prompt = str(task.get("prompt") or "")
        rewards = task.get("rewards") or []
        if not prompt or not rewards:
            na.append(draft.name); continue
        # Pull entity tokens from rewards: source_entity_id, target.entity_id, body refs
        ref_tokens: set[str] = set()
        def collect(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("source_entity_id", "entity_id", "repo", "owner", "branch"):
                        if isinstance(v, str):
                            ref_tokens.add(v)
                    collect(v)
            elif isinstance(o, list):
                for v in o: collect(v)
        collect(rewards)
        # Each token should appear as a substring in the prompt (loose check)
        missing = [t for t in ref_tokens if t and t not in prompt]
        # Tolerance: allow up to 30% of tokens to be missing (rendered as descriptions instead)
        if not ref_tokens:
            na.append(draft.name); continue
        if len(missing) > len(ref_tokens) * 0.3:
            ff.append(draft.name)
        else:
            pf.append(draft.name)
    return bucket_to_result(
        "every_entity_referenced_by_a_reward_is_mentioned_by", pf, ff, na,
        evidence_extra=[
            "Tolerance: ≤30% of reward-referenced entity tokens may be absent from the prompt "
            "(the rest of the prompt may describe them).",
        ],
    )


def zero_surviving_placeholders_alias() -> CheckResult:
    """Alias check that lives in S7b's `count_0_across_the_file` — already scripted there."""
    raise NotImplementedError  # not registered


CHECKS = [
    ("stage_8_hydrate_world_yaml.every_cross_reference_field_whatever_names_the_gym", entity_reference_closure),
    ("stage_8_hydrate_world_yaml.every_entity_referenced_by_a_reward_is_mentioned_by", prompt_grounds_reward_entities),
]
