"""R1 — Load task: deterministic structural checks on every shipped task YAML.

These checks operate on `task_data/worlds/task_*.yaml`. They are the
shipped-corpus analog of Stage 6/7b deterministic checks.
"""
from __future__ import annotations

import re
from pathlib import Path

from _common import (
    CheckResult, GYM, WORLDS, load_yaml, bucket_to_result,
    list_shipped_worlds,
)


def _registered_reward_kinds() -> set[str]:
    out: set[str] = set()
    base = GYM / "gym_github" / "reward_compiler"
    if not base.exists():
        return out
    for py in base.rglob("*.py"):
        for m in re.finditer(r'@register\(["\']([^"\']+)["\']', py.read_text(errors="ignore")):
            out.add(m.group(1))
    return out


def task_id_matches_source_filename() -> CheckResult:
    """R1C1 — `task.id` in the YAML matches the filename stem (or starts with it)."""
    pf, ff, na = [], [], []
    for wf in list_shipped_worlds():
        doc = load_yaml(wf)
        if not doc:
            ff.append(wf.stem); continue
        tid = (doc.get("task") or {}).get("id") or ""
        # Filename example: task_001_licensing_audit_easy.yaml → task_001
        m = re.match(r"^(task_\d+)", wf.stem)
        expected = m.group(1) if m else wf.stem
        # Pass if the id matches the prefix
        (pf if str(tid).startswith(expected) else ff).append(wf.stem)
    return bucket_to_result(
        "matches_the_source_filename_or_the_manifest_key_no", pf, ff, na,
        evidence_extra=["Compares `task.id` against `task_NNN` extracted from the filename."],
    )


def every_reward_kind_in_registered_closed_set() -> CheckResult:
    """R1C2 — every reward `kind` in a shipped task is in the registered universe."""
    registry = _registered_reward_kinds()
    if not registry:
        return CheckResult(
            check_id="every_reward_kind_is_in_the_gym_s_registered_closed",
            level="skipped", score=None,
            evidence=["Could not enumerate @register decorators in gym_github/reward_compiler/."],
            passing_tasks=None, failing_tasks=None,
        )
    pf, ff, na = [], [], []
    for wf in list_shipped_worlds():
        doc = load_yaml(wf)
        if not doc:
            na.append(wf.stem); continue
        rewards = (doc.get("task") or {}).get("rewards") or []
        if not rewards:
            na.append(wf.stem); continue
        # In shipped tasks, reward kind sits under `kind` (cua compiler input)
        # OR under `check.kind` in v3 evidence-based rewards.
        kinds: list[str] = []
        for r in rewards:
            if not isinstance(r, dict):
                continue
            if r.get("kind"):
                kinds.append(r["kind"])
            ch = r.get("check")
            if isinstance(ch, dict) and ch.get("kind"):
                kinds.append(ch["kind"])
        ALLOWED_META = {"state", "action", "answer", "nl_assertion"}
        unknown = [k for k in kinds if k not in registry and k not in ALLOWED_META]
        (ff if unknown else pf).append(wf.stem)
    return bucket_to_result(
        "every_reward_is_in_the_gym_s_registered_closed_reward", pf, ff, na,
        evidence_extra=[
            f"Reward registry size: {len(registry)} kinds + 4 legacy meta-kinds (state/action/answer/nl_assertion).",
        ],
    )


def bootstrap_identity_resolves() -> CheckResult:
    """R1C4 — `bootstrap_data.agent_user_id` resolves to a declared user."""
    pf, ff, na = [], [], []
    for wf in list_shipped_worlds():
        doc = load_yaml(wf)
        if not doc:
            na.append(wf.stem); continue
        agent_id = (doc.get("bootstrap_data") or {}).get("agent_user_id") \
                or (doc.get("bootstrap_data") or {}).get("user")
        if not agent_id:
            na.append(wf.stem); continue
        users = (doc.get("world") or {}).get("users") or []
        declared = {u.get("id") for u in users if isinstance(u, dict)}
        (pf if agent_id in declared else ff).append(wf.stem)
    return bucket_to_result(
        "every_bootstrap_identity_e_g_agent_user_resolves_to_a", pf, ff, na,
        evidence_extra=["Checks bootstrap agent_user_id (or `user`) against declared `world.users[*].id`."],
    )


def tools_list_belongs_to_catalog() -> CheckResult:
    """R1C3 — every entry in `task.tools` belongs to the gym's tool catalog."""
    # Allow the canonical globs plus literal tool names referenced in CLAUDE.md.
    ALLOWED_GLOBS = {"mcp__*", "ui_*"}
    EXACT = {
        "browser_navigate", "browser_get_page_text", "browser_screenshot",
        "browser_click", "browser_right_click", "browser_drag",
        "browser_type", "browser_press_key", "browser_scroll", "browser_wait",
        "browser_create_tab", "browser_switch_tab", "browser_list_tabs",
        "browser_evaluate",
    }
    pf, ff, na = [], [], []
    for wf in list_shipped_worlds():
        doc = load_yaml(wf)
        if not doc:
            na.append(wf.stem); continue
        tools = (doc.get("task") or {}).get("tools") or []
        if not tools:
            ff.append(wf.stem); continue
        ok = True
        for t in tools:
            if t in ALLOWED_GLOBS or t in EXACT or t.startswith("mcp__") or t.startswith("ui_") or t.startswith("browser_"):
                continue
            ok = False; break
        (pf if ok else ff).append(wf.stem)
    return bucket_to_result(
        "all_tools_strings_exist_in_the_gym_s_registered_tool", pf, ff, na,
        evidence_extra=["Tool entries must be canonical globs (`mcp__*`, `ui_*`), `browser_*`, or in the literal catalog."],
    )


CHECKS = [
    ("r1_load_task.matches_the_source_filename_or_the_manifest_key_no", task_id_matches_source_filename),
    ("r1_load_task.every_reward_is_in_the_gym_s_registered_closed_reward", every_reward_kind_in_registered_closed_set),
    ("r1_load_task.every_bootstrap_identity_e_g_agent_user_resolves_to_a", bootstrap_identity_resolves),
    ("r1_load_task.all_tools_strings_exist_in_the_gym_s_registered_tool", tools_list_belongs_to_catalog),
]
