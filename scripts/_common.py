"""Shared helpers for deterministic audit scripts.

The TARGET gym being audited is resolved via:
  1. the ``TARGET_GYM`` environment variable (set by the CLI), or
  2. the file ``.last_target`` at this repo's root (written by the CLI).
This decouples the scripts from any fixed location on disk.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Audit-repo anchor ─────────────────────────────────────────────────
AUDIT_REPO = Path(__file__).resolve().parent.parent


def _resolve_target() -> Path:
    """Resolve the gym repo being audited (the target). Hard-fails if unset."""
    env = os.environ.get("TARGET_GYM")
    if env:
        p = Path(env).expanduser().resolve()
        if not p.exists():
            raise SystemExit(f"TARGET_GYM is set to {p} but the directory does not exist.")
        return p
    last = AUDIT_REPO / ".last_target"
    if last.exists():
        p = Path(last.read_text().strip()).expanduser().resolve()
        if p.exists():
            return p
    raise SystemExit(
        "No target gym configured. Set TARGET_GYM=/path/to/gym OR run "
        "`uv run ./audit.py` to be prompted (it writes .last_target for the scripts to read)."
    )


# Target paths — all derive from the configured target gym
GYM    = _resolve_target()
DRAFTS = GYM / "task-designer" / "drafts"
WORLDS = GYM / "task_data" / "worlds"
TABLES = GYM / "task-designer" / "tables"
STAGES = GYM / "task-designer" / "stages"

# Audit-repo paths
RUBRIC   = AUDIT_REPO / "lifecycle_rubric.yaml"
SESSIONS = AUDIT_REPO / "sessions"


@dataclass
class CheckResult:
    check_id: str
    level: str
    score: float | None
    evidence: list[str] = field(default_factory=list)
    passing_tasks: list[str] | None = None
    failing_tasks: list[str] | None = None
    remediation: str | None = None
    source_script: str = ""


def list_drafts() -> list[Path]:
    if not DRAFTS.exists():
        return []
    return sorted(p for p in DRAFTS.iterdir() if p.is_dir() and p.name.startswith("task_"))


def list_shipped_worlds() -> list[Path]:
    if not WORLDS.exists():
        return []
    return sorted(WORLDS.glob("task_*.yaml"))


def load_stage(draft: Path, stage_n: str) -> dict | None:
    p = draft / f"stage_{stage_n}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def load_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text())
    except Exception:
        return None


def bucket_to_result(
    check_id: str,
    pass_ids: list[str],
    fail_ids: list[str],
    na_ids: list[str] | None = None,
    *,
    evidence_extra: list[str] | None = None,
    remediation_hint: str | None = None,
) -> CheckResult:
    pass_n, fail_n = len(pass_ids), len(fail_ids)
    na_n = len(na_ids or [])
    total_eval = pass_n + fail_n
    if total_eval == 0:
        level, score = "skipped", None
    elif fail_n == 0:
        level, score = "present", 1.0
    elif pass_n == 0:
        level, score = "absent", 0.0
    else:
        level, score = "partial", round(pass_n / total_eval, 4)
    evidence = [
        f"Deterministic script ran on {total_eval + na_n} candidate tasks "
        f"({total_eval} evaluable, {na_n} not applicable).",
        f"Result: {pass_n} pass / {fail_n} fail / {na_n} n/a.",
    ]
    if evidence_extra:
        evidence.extend(evidence_extra)
    remediation = None
    if fail_n > 0:
        remediation = (
            remediation_hint
            or "See the check's `suggestion` in lifecycle_rubric.yaml for the canonical fix."
        )
    return CheckResult(
        check_id=check_id,
        level=level,
        score=score,
        evidence=evidence,
        passing_tasks=sorted(pass_ids),
        failing_tasks=sorted(fail_ids),
        remediation=remediation,
    )


def gym_wide_result(
    check_id: str,
    *,
    passed: bool,
    evidence: list[str],
    remediation: str | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        level="present" if passed else "absent",
        score=1.0 if passed else 0.0,
        evidence=evidence,
        remediation=None if passed else remediation,
    )
