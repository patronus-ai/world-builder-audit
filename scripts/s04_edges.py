"""Deterministic scripts for Stage 4 — Dependency edges."""
from __future__ import annotations

from collections import defaultdict

from _common import (
    CheckResult, list_drafts, load_stage, bucket_to_result,
)


def _has_cycle(adj: dict[str, list[str]]) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    def visit(n: str) -> bool:
        color[n] = GRAY
        for m in adj.get(n, ()):
            if color.get(m, WHITE) == GRAY: return True
            if color.get(m, WHITE) == WHITE and visit(m): return True
        color[n] = BLACK
        return False
    return any(color[n] == WHITE and visit(n) for n in adj)


def dag_check_holds_no_cycles() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s04 = load_stage(draft, "04")
        if not s04:
            na.append(draft.name); continue
        gg = s04.get("goal_graph") or {}
        edges = gg.get("edges") or []
        if len(edges) < 2:
            na.append(draft.name); continue   # cycle detection vacuous
        adj: dict[str, list[str]] = defaultdict(list)
        for e in edges:
            f = e.get("from_goal") or e.get("from")
            t = e.get("to_goal") or e.get("to")
            if f and t:
                adj[f].append(t)
                adj.setdefault(t, [])
        (ff if _has_cycle(adj) else pf).append(draft.name)
    return bucket_to_result(
        "dag_check_holds_no_cycles_auditor_re_runs_on_the", pf, ff, na,
        evidence_extra=["Re-runs `_has_cycle` (DFS with gray/black coloring) on every draft's edge list."],
    )


def every_edge_endpoint_resolves() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s04 = load_stage(draft, "04")
        if not s04:
            na.append(draft.name); continue
        gg = s04.get("goal_graph") or {}
        goal_ids = {g.get("id") for g in (gg.get("goals") or [])}
        edges = gg.get("edges") or []
        if not edges:
            na.append(draft.name); continue
        def _from(e): return e.get("from_goal") or e.get("from")
        def _to(e): return e.get("to_goal") or e.get("to")
        bad = [e for e in edges if _from(e) not in goal_ids or _to(e) not in goal_ids]
        (ff if bad else pf).append(draft.name)
    return bucket_to_result(
        "every_edge_endpoint_resolves_to_a_declared_goal_id", pf, ff, na,
        evidence_extra=["Cross-references each `from`/`to` against the goals declared in the same `stage_04.goal_graph`."],
    )


def no_duplicate_edges() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s04 = load_stage(draft, "04")
        if not s04:
            na.append(draft.name); continue
        edges = (s04.get("goal_graph") or {}).get("edges") or []
        if len(edges) < 2:
            na.append(draft.name); continue
        pairs = [
            (e.get("from_goal") or e.get("from"), e.get("to_goal") or e.get("to"))
            for e in edges
        ]
        (pf if len(pairs) == len(set(pairs)) else ff).append(draft.name)
    return bucket_to_result(
        "no_duplicate_edges_same_pair", pf, ff, na,
        evidence_extra=["Compares `len(edges)` against `len(set(from→to))` per draft."],
    )


def metagoal_ids_unique_and_referenced_goals_exist() -> CheckResult:
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s04 = load_stage(draft, "04")
        if not s04:
            na.append(draft.name); continue
        gg = s04.get("goal_graph") or {}
        metagoals = gg.get("metagoals") or []
        if not metagoals:
            na.append(draft.name); continue
        goal_ids = {g.get("id") for g in (gg.get("goals") or [])}
        ids = [m.get("id") for m in metagoals if isinstance(m, dict)]
        unique = len(ids) == len(set(ids))
        refs_ok = True
        for m in metagoals:
            refd = (m.get("goals") or m.get("goal_ids") or m.get("targets") or [])
            if any(r not in goal_ids for r in refd):
                refs_ok = False; break
        (pf if (unique and refs_ok) else ff).append(draft.name)
    return bucket_to_result(
        "metagoal_ids_are_unique_and_their_referenced_goals", pf, ff, na,
        evidence_extra=["Validates metagoal id uniqueness AND that every referenced goal exists."],
    )


def every_goal_participates_in_at_least_one_edge() -> CheckResult:
    """S4C3 — every goal appears as `from_goal` or `to_goal` in some edge.

    Skipped for tasks with <2 goals (no edges expected).
    """
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s04 = load_stage(draft, "04")
        if not s04:
            na.append(draft.name); continue
        gg = s04.get("goal_graph") or {}
        goals = gg.get("goals") or []
        edges = gg.get("edges") or []
        if len(goals) < 2:
            na.append(draft.name); continue
        endpoints = set()
        for e in edges:
            f = e.get("from_goal") or e.get("from")
            t = e.get("to_goal") or e.get("to")
            if f: endpoints.add(f)
            if t: endpoints.add(t)
        orphans = [g.get("id") for g in goals if g.get("id") not in endpoints]
        (ff if orphans else pf).append(draft.name)
    return bucket_to_result(
        "every_goal_participates_in_at_least_one_edge_or_is", pf, ff, na,
        evidence_extra=["Cross-references each goal id against the union of edge endpoints."],
    )


def edge_density_falls_within_band() -> CheckResult:
    """S4C6 — edge count is within the configured band, if a band exists."""
    import yaml
    from _common import GYM
    cfg = yaml.safe_load((GYM / "task-designer" / "config.yaml").read_text()) or {}
    band = ((cfg.get("structure") or {}).get("edge_density")) or {}
    lo = band.get("min"); hi = band.get("max")
    if lo is None and hi is None:
        return CheckResult(
            check_id="edge_density_falls_within_band",
            level="skipped", score=None,
            evidence=["`config.structure.edge_density` band not declared — check is N/A everywhere."],
            passing_tasks=None, failing_tasks=None,
        )
    pf, ff, na = [], [], []
    for draft in list_drafts():
        s04 = load_stage(draft, "04")
        if not s04:
            na.append(draft.name); continue
        edges = (s04.get("goal_graph") or {}).get("edges") or []
        n = len(edges)
        ok = (lo is None or n >= lo) and (hi is None or n <= hi)
        (pf if ok else ff).append(draft.name)
    return bucket_to_result(
        "edge_density_falls_within_band", pf, ff, na,
        evidence_extra=[f"Band min={lo} max={hi}; compared `len(edges)` per draft."],
    )


CHECKS: list[tuple[str, callable]] = [
    ("stage_4_dependency_edges.dag_check_holds_no_cycles_auditor_re_runs_on_the", dag_check_holds_no_cycles),
    ("stage_4_dependency_edges.every_edge_endpoint_resolves_to_a_declared_goal_id", every_edge_endpoint_resolves),
    ("stage_4_dependency_edges.no_duplicate_edges_same_pair", no_duplicate_edges),
    ("stage_4_dependency_edges.metagoal_ids_are_unique_and_their_referenced_goals", metagoal_ids_unique_and_referenced_goals_exist),
    ("stage_4_dependency_edges.every_goal_participates_in_at_least_one_edge_or_is", every_goal_participates_in_at_least_one_edge),
    ("stage_4_dependency_edges.edge_density_falls_within_band", edge_density_falls_within_band),
]
