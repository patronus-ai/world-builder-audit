# world-builder-audit

Standalone audit toolkit for procedural world-builder gyms.

Walks a target gym repo against the canonical **lifecycle rubric** (141 checks across 5 phases / 25 stages), runs a battery of **deterministic Python scripts** where possible, and produces a scored Markdown report plus an interactive viewer.

![Pipeline DAG view of the audit results — 5 phase lanes, one node per stage, in-circle pass/mixed/fail counts](docs/viewer-screenshot.png)

> Pipeline view of an audit session — each circle is one of the 25 lifecycle stages (`S1` … `R5`). Border color summarizes the stage (green = all checks pass, yellow = mixed, red = at least one failing check). Inline counts (`3✓ 1~ 2✗`) show the per-stage pass / mixed / fail breakdown at a glance. Click any node to drill into its individual checks + evidence.

## Quick start

The audit is **full by default**: it scores all 141 checks — the deterministic
scripts run first as the reproducible floor, then LLM evaluation covers the rest.
Run it with the **`/gym-audit` skill inside Claude Code**, from this repo:

```text
1. Install:  uv sync
2. In Claude Code, from this repo, run:  /gym-audit
   (it prompts for the gym to audit — local path or git URL)
```

That single command runs the complete five-phase audit (recon → mapping →
per-check eval → cross-cutting → synthesis) and writes a scored
`sessions/<id>/REPORT.md`. The deterministic scripts are **Phase 2a inside it**,
not a separate "lite" mode — there's no way to get only-deterministic from the
skill, which is what makes the full audit the default.

> The LLM phases require an agent runtime, so the full audit only runs through
> the skill in Claude Code — not from a bare terminal.

### Helper: `audit.py` (deterministic floor + viewer only)

`audit.py` is a non-LLM convenience launcher. Use it to set the target, run just
the deterministic floor, or open the viewer on existing sessions — it does **not**
run the full audit:

```bash
uv run ./audit.py scripts        # run only the deterministic checks (the floor)
uv run ./audit.py viewer         # launch viewer at http://127.0.0.1:8765
uv run ./audit.py both           # deterministic scripts, then viewer
```

> **Note:** run via `uv run ./audit.py`, not a bare `./audit.py`. The script's
> shebang resolves to your system Python, which won't have the dependencies
> installed — `uv run` (or an activated venv) points it at the right interpreter.
> If dependencies are missing, `audit.py` fails fast with install instructions
> instead of a confusing traceback. (Prefer `pip`? `python3 -m venv .venv &&
> source .venv/bin/activate && pip install -e .`, then drop the `uv run` prefix.)

The selected target is recorded in `.last_target` so subsequent runs (skill or `audit.py`) can reuse it (just hit Enter at the prompt).

## What's inside

| File / dir | Purpose |
|---|---|
| `lifecycle_rubric.yaml` | The canonical rubric — 141 checks, codes (`S1C1` … `R5C6`), why/suggestion/na_reason per check |
| `rubric.yaml` | Older category-based rubric, kept for legacy sessions |
| `CHECKS.md` | Per-rule manifest for the linter-rule checks |
| `world_generation_lifecycle.md` | Canonical reference doc describing each lifecycle stage |
| `scripts/` | Deterministic check runners (`s01_objective.py`, `s04_edges.py`, …) |
| `scripts/run_all.py` | Orchestrator — runs every `CHECKS = [...]` registry and merges into a session |
| `viewer/` | FastAPI server + single-page DAG view |
| `sessions/` | Audit results land here, one folder per session |
| `.claude/skills/gym-audit/` | **The full audit.** Claude Code skill that runs all five phases (deterministic floor + LLM eval) — invoke via `/gym-audit` |
| `audit.py` | Helper launcher (non-LLM): deterministic floor + viewer only |

## How the audit works

Two complementary passes:

1. **Deterministic scripts** (`scripts/run_all.py`) — currently 44 of 141 checks (31%). Pure file inspection, parsing, counting, cycle detection, closed-set membership, reference resolution. Reproducible byte-for-byte from the target gym's filesystem alone — no LLM, no agent, no API.
2. **LLM evaluation** (via the `gym-audit` Claude Code skill) — covers the remaining checks that genuinely need semantic judgment (narrative quality, domain vocabulary, semantic distractor coherence, etc.).

The skill runs the scripts FIRST, then dispatches LLM agents only for the un-scripted checks. Wherever a script result exists, it is the source of truth.

## Adding a new deterministic check

1. Find the check in `lifecycle_rubric.yaml`.
2. Add a runner function to the appropriate `scripts/sXX_*.py` (or create a new one named after the stage).
3. Register it in the file's `CHECKS = [...]` registry.
4. Add `script: scripts/<file>.py::<fn>` to the check in `lifecycle_rubric.yaml`.
5. Run `uv run ./audit.py scripts` against your target gym to verify.

See `scripts/README.md` for the helper API (`bucket_to_result`, `gym_wide_result`, `list_drafts`, `load_stage`, etc.).

## Repo conventions

- Audit results NEVER touch the target gym. Sessions live under `sessions/` in THIS repo.
- The rubric is authored to be **gym-agnostic**: it speaks in terms of phases/stages and corpus paths (`task-designer/drafts/`, `task-designer/worlds/`). Per-gym overrides go in a future `gym_overrides/` folder.

## License

Proprietary — © Patronus AI.
