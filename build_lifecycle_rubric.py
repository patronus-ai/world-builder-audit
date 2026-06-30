"""Parse docs/world_generation_lifecycle.md into audit/lifecycle_rubric.yaml.

The lifecycle doc has structure:
  ## Phase 1 — Skeleton (procedural)
  ### Stage 1 — Objective
  - **Summary:** ...
  - **Input:** ...
  - **Output:** ...
  - **Assertions:** ...
  - **Files:** ...
  - **Audit checks:**
    - `[per-task]` task_type_id exists in ...
    - `[per-stage]` Stage is deterministic ...

This script walks the markdown and emits a YAML keyed by phase → stage → check.
Each check carries: id (slugified), scope, what (bullet text), files, why (stub),
suggestion (stub). The stubs are placeholders the auditor can refine later.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "world_generation_lifecycle.md"
OUT_PATH = Path(__file__).resolve().parent / "lifecycle_rubric.yaml"

SCOPE_TAG_RE = re.compile(r"`\[(per-task|per-stage|per-batch|gym-wide)\]`\s*(.*)")
H2_RE = re.compile(r"^## (.+)$")
H3_RE = re.compile(r"^### (.+)$")
BULLET_RE = re.compile(r"^\s*-\s+(.*)$")
FIELD_RE = re.compile(r"^\s*-\s+\*\*([^:*]+):\*\*\s*(.*)$")

PHASE_PREFIX_RE = re.compile(r"^Phase (\d+)\b", re.IGNORECASE)
STAGE_PREFIX_RE = re.compile(r"^(Stage|Substages?|R\d|Post-hydration|Final|`yaml_fixes\.py`)", re.IGNORECASE)


def slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"`[^`]*`", " ", text)              # strip inline code
    text = re.sub(r"\*\*[^*]*\*\*", " ", text)        # strip bold markers
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    if len(text) > max_len:
        text = text[:max_len].rsplit("_", 1)[0]
    return text or "check"


def parse_doc(md: str) -> list[dict]:
    """Walk markdown lines, accumulate phase/stage/check rows."""
    phases: list[dict] = []
    current_phase: dict | None = None
    current_stage: dict | None = None
    in_audit_block = False
    in_files_field = False
    files_buf: list[str] = []

    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # ── H2 phase ─────────────────────────────────────────
        if (m := H2_RE.match(line)):
            title = m.group(1).strip()
            if PHASE_PREFIX_RE.match(title) or title.startswith("Runtime"):
                current_phase = {"name": title, "id": slugify(title, 40), "stages": []}
                phases.append(current_phase)
                current_stage = None
                in_audit_block = False
                i += 1
                continue
            # other H2s aren't lifecycle phases — stop tracking
            current_phase = None
            current_stage = None
            in_audit_block = False
            i += 1
            continue

        # ── H3 stage ─────────────────────────────────────────
        if current_phase is not None and (m := H3_RE.match(line)):
            title = m.group(1).strip()
            current_stage = {
                "name": title,
                "id": slugify(title, 50),
                "summary": "",
                "files": [],
                "checks": [],
            }
            current_phase["stages"].append(current_stage)
            in_audit_block = False
            in_files_field = False
            i += 1
            continue

        if current_stage is None:
            i += 1
            continue

        # ── Field bullets (Summary / Input / Output / Assertions / Files) ──
        if (m := FIELD_RE.match(line)):
            label = m.group(1).strip().lower()
            value = m.group(2).strip()
            in_audit_block = (label == "audit checks")
            in_files_field = (label == "files")
            if label == "summary":
                current_stage["summary"] = value
            elif label == "files":
                # files can be a single line or multiple — captured below
                files_buf = [s.strip().strip("`") for s in re.split(r",", value) if s.strip()]
                current_stage["files"].extend([f for f in files_buf if f])
            i += 1
            continue

        # ── Audit-check bullets ──────────────────────────────
        if in_audit_block and (m := BULLET_RE.match(line)) and line.lstrip().startswith("- "):
            bullet = m.group(1).strip()
            # Match the [scope] tag
            scope_match = SCOPE_TAG_RE.match(bullet)
            if scope_match:
                scope = scope_match.group(1)
                what_text = scope_match.group(2).strip()
            else:
                # Skipped a non-tagged note (e.g. the "skip this block for non-visual gyms" line)
                i += 1
                continue
            # Strip leading bold markers like "**Linter presence** — ..." but keep readable
            what_clean = re.sub(r"\s+", " ", what_text).strip()
            cid = slugify(what_clean, 55)
            # disambiguate within stage
            existing = {c["id"] for c in current_stage["checks"]}
            if cid in existing:
                n = 2
                while f"{cid}_{n}" in existing:
                    n += 1
                cid = f"{cid}_{n}"
            current_stage["checks"].append(
                {
                    "id": cid,
                    "scope": scope,
                    "what": what_clean,
                    "why": _why_stub(what_clean, scope),
                    "suggestion": _suggestion_stub(what_clean, scope),
                }
            )
            i += 1
            continue

        # End of audit block when we hit a blank line followed by non-bullet
        if in_audit_block and line.strip() == "":
            # peek next non-blank line; if not a bullet, stop
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and not BULLET_RE.match(lines[j]):
                in_audit_block = False

        i += 1

    return phases


def _why_stub(what: str, scope: str) -> str:
    """Heuristic why-blurb based on what the check asserts."""
    wl = what.lower()
    if "closed set" in wl or "closed" in wl and "universe" in wl:
        return "Catches LLM-invented or hand-typed values outside the gym's declared closed universe — these would fail downstream compilation or grading."
    if "deterministic" in wl:
        return "Non-determinism here means identical inputs produce different tasks across runs, which breaks goldens, regression tests, and cross-variant comparisons."
    if "idempoten" in wl:
        return "If running twice diverges, downstream snapshots, caches, or goldens can't trust the build's reproducibility."
    if "no orphan" in wl or "orphan goal" in wl or "every goal" in wl and "edge" in wl:
        return "Goals or subgoals not connected to the DAG never get exercised by any reward — they're dead structure that inflates apparent task complexity."
    if "unique" in wl and "id" in wl:
        return "Duplicate IDs collide in entity lookup and silently overwrite each other during build."
    if "placeholder" in wl:
        return "Surviving placeholders mean the substitution layer or hydration LLM skipped a section — agents see template strings instead of real values."
    if "no cycle" in wl or "dag" in wl:
        return "Cyclic dependencies are unsolvable as graded: the agent can't satisfy A before B if B depends on A."
    if "match" in wl and ("count" in wl or "matrix" in wl or "inventory" in wl):
        return "A count drift between stages means one stage silently dropped or added entities/rewards — downstream stages will be miscalibrated."
    if "every reward" in wl and "registered" in wl:
        return "Reward kinds not in the registry fail to compile at runtime; the task is unscorable."
    if "ref" in wl and "resolve" in wl:
        return "An unresolved reference (entity, branch, file) is a runtime crash or a silently-skipped grading step."
    if "linter" in wl or "lint" in wl:
        return "Linter coverage is the only mechanical guard against structural defects sneaking in from LLM stages."
    if "hint" in wl or "leak" in wl:
        return "Answer leakage in agent-visible text gives the agent free credit without exercising the intended skill."
    if "harness" in wl and "pass" in wl:
        return "If the golden solution doesn't pass every reward, the task is broken-by-design: no agent can pass it cleanly."
    if "diff" in wl and "target" in wl:
        return "Wide-blast-radius edits during a fix step suggest the LLM rewrote unrelated content, risking regressions."
    return "Add why-this-matters: this check guards a structural invariant the rest of the pipeline assumes."


def _suggestion_stub(what: str, scope: str) -> str:
    """Heuristic remediation suggestion."""
    wl = what.lower()
    if "deterministic" in wl:
        return "Audit the stage code for `random`, `uuid4`, `time.time`, dict-iteration order; introduce a seeded RNG or sort outputs before emission."
    if "closed set" in wl or "registered" in wl:
        return "Add the missing value to the registry, OR reject the LLM/grounding output that introduced it."
    if "placeholder" in wl:
        return "Re-run hydration on the affected section; if recurrent, harden the prompt to require placeholder closure."
    if "no orphan" in wl or "orphan goal" in wl or ("every goal" in wl and "edge" in wl):
        return "Either add an edge connecting the orphan goal to the rest of the DAG, or remove the orphan if it's no longer required."
    if "linter" in wl:
        return "Add the missing lint rule to the gym's linter module; back-fill against the corpus to confirm it fires correctly."
    if "ref" in wl and "resolve" in wl:
        return "Fix the dangling reference in the offending stage's output; or, if structural, add a lint rule that catches it earlier."
    if "harness" in wl and "pass" in wl:
        return "Run the harness locally; for each failing reward, patch either the task definition or the golden solution and re-run stage 15."
    if "hint" in wl or "leak" in wl:
        return "Re-run the post-hydration hint gate; if the gate missed it, extend its regex catalog."
    return "Investigate the offending stage output; remediation depends on which invariant failed — see the stage's Files entry for the implementing module."


def main() -> int:
    if not DOC_PATH.exists():
        print(f"Doc not found: {DOC_PATH}", file=sys.stderr)
        return 1

    md = DOC_PATH.read_text()
    phases = parse_doc(md)

    # Stats
    total_checks = sum(len(s["checks"]) for p in phases for s in p["stages"])
    print(f"Parsed {len(phases)} phases, {sum(len(p['stages']) for p in phases)} stages, {total_checks} checks.")
    for p in phases:
        print(f"\n{p['name']}")
        for s in p["stages"]:
            print(f"  {s['name']:55s}  {len(s['checks']):2d} checks")

    payload = {
        "schema_version": 1,
        "source_doc": "docs/world_generation_lifecycle.md",
        "phases": phases,
    }
    OUT_PATH.write_text(yaml.safe_dump(payload, sort_keys=False, width=120, allow_unicode=True))
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
