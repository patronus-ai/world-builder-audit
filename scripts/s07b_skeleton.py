"""Deterministic scripts for Stage 7b (YAML skeleton) and Stage 8 (hydration)."""
from __future__ import annotations

import re

from _common import (
    CheckResult, list_drafts, load_yaml, bucket_to_result,
)


CANONICAL_TOOLS = ["mcp__*", "ui_*"]


def skeleton_parses_with_yaml_safe_load() -> CheckResult:
    """S7bC3 — every draft's skeleton.yaml parses cleanly."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = draft / "skeleton.yaml"
        if not sk.exists():
            na.append(draft.name); continue
        try:
            doc = load_yaml(sk)
            (ff if doc is None else pf).append(draft.name)
        except Exception:
            ff.append(draft.name)
    return bucket_to_result(
        "skeleton_parses_with", pf, ff, na,
        evidence_extra=["Runs `yaml.safe_load` on every `skeleton.yaml` and counts parse failures."],
    )


def required_top_level_sections_present() -> CheckResult:
    """S7bC4 — skeleton declares the required gym-cua top-level sections."""
    REQUIRED = ["seed_base", "world", "bootstrap_data", "task"]
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = draft / "skeleton.yaml"
        if not sk.exists():
            na.append(draft.name); continue
        doc = load_yaml(sk) or {}
        missing = [k for k in REQUIRED if k not in doc]
        (ff if missing else pf).append(draft.name)
    return bucket_to_result(
        "required_top_level_sections_present_whatever_the_gym_s", pf, ff, na,
        evidence_extra=[f"Required sections: {REQUIRED} — verified per skeleton."],
    )


def tools_is_canonical_list() -> CheckResult:
    """S7bC7 — task.tools is the canonical list ([mcp__*, ui_*])."""
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = draft / "skeleton.yaml"
        if not sk.exists():
            na.append(draft.name); continue
        doc = load_yaml(sk) or {}
        tools = (doc.get("task") or {}).get("tools") or []
        # Canonical pattern: at least the two glob entries should appear.
        ok = all(t in tools for t in CANONICAL_TOOLS)
        (pf if ok else ff).append(draft.name)
    return bucket_to_result(
        "is_the_gym_s_canonical_tool_list_no_truncation_no", pf, ff, na,
        evidence_extra=[f"Required tool globs: {CANONICAL_TOOLS}. Skeleton's `task.tools` must contain both."],
    )


def placeholders_carry_comment_hint() -> CheckResult:
    """S7bC4 — every LLM_MUST_FILL_THIS_PLACEHOLDER must be preceded by a `# hint:`."""
    PLACEHOLDER = "LLM_MUST_FILL_THIS_PLACEHOLDER"
    pf, ff, na = [], [], []
    for draft in list_drafts():
        sk = draft / "skeleton.yaml"
        if not sk.exists():
            na.append(draft.name); continue
        try:
            text = sk.read_text()
        except Exception:
            ff.append(draft.name); continue
        if PLACEHOLDER not in text:
            na.append(draft.name); continue
        # For every line containing the placeholder, the previous non-blank line
        # must contain "hint" (case insensitive).
        lines = text.splitlines()
        bad = 0
        for i, line in enumerate(lines):
            if PLACEHOLDER not in line:
                continue
            # Look back at most 3 lines for a comment with "hint"
            found_hint = False
            for j in range(max(0, i - 3), i):
                if "#" in lines[j] and "hint" in lines[j].lower():
                    found_hint = True
                    break
            if not found_hint:
                bad += 1
        (ff if bad else pf).append(draft.name)
    return bucket_to_result(
        "every_carries_a_comment_hint_describing_what_to_fill", pf, ff, na,
        evidence_extra=["For every `LLM_MUST_FILL_THIS_PLACEHOLDER` token, scans the preceding 3 lines for a `# hint:`-style comment."],
    )


def zero_surviving_placeholders_in_hydrated() -> CheckResult:
    """S8C1 — hydrated YAML carries zero LLM_MUST_FILL_THIS_PLACEHOLDER tokens."""
    PLACEHOLDER = "LLM_MUST_FILL_THIS_PLACEHOLDER"
    pf, ff, na = [], [], []
    for draft in list_drafts():
        # Hydration outputs vary: world_v1.yaml is the most common artifact.
        candidates = list(draft.glob("world_v*.yaml")) + list(draft.glob("hydrated*.yaml"))
        if not candidates:
            na.append(draft.name); continue
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        try:
            text = latest.read_text()
        except Exception:
            ff.append(draft.name); continue
        (ff if PLACEHOLDER in text else pf).append(draft.name)
    return bucket_to_result(
        "count_0_across_the_file", pf, ff, na,
        evidence_extra=["Counts `LLM_MUST_FILL_THIS_PLACEHOLDER` occurrences in the most-recent hydrated `world_v*.yaml`."],
    )


CHECKS: list[tuple[str, callable]] = [
    ("stage_7b_yaml_skeleton.skeleton_parses_with", skeleton_parses_with_yaml_safe_load),
    ("stage_7b_yaml_skeleton.required_top_level_sections_present_whatever_the_gym_s", required_top_level_sections_present),
    ("stage_7b_yaml_skeleton.is_the_gym_s_canonical_tool_list_no_truncation_no", tools_is_canonical_list),
    ("stage_7b_yaml_skeleton.every_carries_a_comment_hint_describing_what_to_fill", placeholders_carry_comment_hint),
    ("stage_8_hydrate_world_yaml.count_0_across_the_file", zero_surviving_placeholders_in_hydrated),
]
