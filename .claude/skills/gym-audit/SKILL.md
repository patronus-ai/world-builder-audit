---
name: gym-audit
description: Audit a world-builder gym (target) against the canonical lifecycle rubric and produce a scored Markdown report with concrete remediation. Run from inside the world-builder-audit repo.
triggers:
  - gym-audit
  - audit gym
  - audit-gym
---

# Gym Audit

This skill lives inside the standalone **world-builder-audit** repo. The
audit repo holds the rubric, the deterministic scripts, and the viewer; it
does NOT contain the gym being audited. The TARGET gym lives elsewhere.

## Inputs

The audit operates on a TARGET gym. Resolution order:
1. Env var **`TARGET_GYM`** — set by `audit.py` when it prompts for the target.
2. Fallback file **`.last_target`** at this repo's root.
3. Otherwise: ask the user via `audit.py` and write `.last_target`.

If neither is set, run `uv run ./audit.py` once (it prompts the user) before
invoking any phase below.

## Rubric source

The canonical rubric is at `lifecycle_rubric.yaml` in THIS repo. Read it at
the start of every audit. Honor:
- `scoring.severity_weights` and `scoring.level_scores`
- `target_band` for context
- `cross_cutting[]` entries — run after per-category eval
- `universal_aspirations.ids` — score absolutely, don't penalize against baseline
- `load_bearing_meta_checks.ids` — these dominate the top-line verdict

Checks marked `domain_specific: true` should be **skipped** when their underlying
concern isn't applicable to the target gym (e.g., text-content predicates if the
gym only grades structured state). Record "skipped: domain_specific" in the
evidence so the report explains why.

## Procedure

This skill always runs the **full** audit — all five phases, every applicable
check. The deterministic scripts are Phase 2a (the reproducible floor), not a
standalone mode; never stop after them or treat a deterministic-only run as a
complete audit. Always proceed through Phase 2b (LLM eval), Phase 3
(cross-cutting), and Phase 4 (synthesis + report).

Run the five phases in order. Each phase writes a structured artifact under
`sessions/<session_id>/<NN>-<name>.json` so later phases can read earlier output.

### Phase 0 — Recon (one shot, ~5 min)

Goal: produce a `fingerprint` of the target gym so detector logic doesn't
hallucinate paths.

Steps:
1. Read `<target>/README.md`, `<target>/CLAUDE.md` (or equivalent), root
   `Makefile`/`justfile`/`package.json`/`Cargo.toml`.
2. Determine the gym's domain (cli? web-agent? GitHub-like? robotics?) so you
   can decide which `domain_specific: true` checks to skip.
3. Locate canonical directories. For each, record either the path or `null`:
   - `task_dir` — where task/scenario specs live
   - `task_spec_format` — yaml/json/toml/code
   - `compiler_dir` — reward/check compiler
   - `builder_dir` — world/env builder
   - `models_module` — typed schemas for entities + check kinds
   - `linter_dir` — reward-quality linter
   - `golden_dir` — golden solutions, if any
   - `pipeline_dir` — deployment / image-build scripts
   - `qa_dir` — QA tooling
   - `ci_dir` — `.github/workflows/`, `.gitlab-ci.yml`, etc.

Write `sessions/<session_id>/00-fingerprint.json`.

### Phase 1 — Component mapping (parallel, ~15 min)

Goal: For each rubric category, find the structural analog in the target gym
(don't assess quality yet — just map).

Strategy: launch **one Explore agent per category** in parallel (10–11 agents).
Each agent's prompt:

> You are mapping rubric category `<category.id>` onto a target gym at
> `<target_path>`. The fingerprint is `<fingerprint>`. For each check in this
> category (listed below), find the closest structural analog in the target
> gym and record the path(s) — or `null` if no analog exists. Don't assess
> quality. Don't run anything. Return JSON: `{check_id: {analog_paths: [...], notes: "..."}}`.
> Under 400 words.

Write `sessions/<session_id>/01-mapping.json`.

### Phase 2 — Per-check evaluation (parallel, ~30 min)

Goal: Run every detector and classify each check as `absent` / `partial` /
`present`, with concrete evidence.

#### Step 2a — Deterministic scripts first (MANDATORY, no LLM)

The deterministic scripts are **not optional and not a subset to sample
from** — the audit MUST run *every* available script and rely on *all* of
their results. They cover every rubric check that carries a `script:` field
in `lifecycle_rubric.yaml`, are byte-reproducible from the gym filesystem
alone, and are the source of truth wherever they exist.

Before launching any LLM agent, run the orchestrator (it auto-discovers and
runs every `CHECKS = [...]` registry under `scripts/` — that is the complete
set of available deterministic scripts):

```bash
TARGET_GYM=/path/to/target/gym uv run python scripts/run_all.py
```

This step is a hard gate. You may NOT proceed to Step 2b until all of the
following hold:

1. **It ran to completion.** `run_all.py` exited 0 and printed
   `Ran <N> deterministic checks.` with N > 0. A non-zero exit means the
   environment is broken (e.g. missing deps, unreadable target) — fix it and
   re-run; do NOT skip ahead and let LLM agents cover scripted checks.
2. **No script silently degraded.** `run_all.py` records a crashed script as
   an `absent` result whose evidence begins `Script <file> raised:`. Scan the
   merged `04-scored.json` for any such evidence string. If present, the
   deterministic floor is incomplete — investigate the script (target path
   wrong? unhandled gym shape?) and re-run until it produces a real verdict.
   Treat a `Script … raised` result as a tooling failure to fix, NOT as a
   genuine `absent` finding about the gym.
3. **Coverage is complete.** Every check that carries a `script:` field in
   `lifecycle_rubric.yaml` MUST have a corresponding entry in
   `04-scored.json` after this run. Cross-check the two: a `script:`-bearing
   check with no merged result means its script wasn't discovered/registered —
   surface that as a toolkit gap; never fill it in with an LLM agent.

The orchestrator merges results into the most-recent session's
`04-scored.json` under `lifecycle_evaluations`. Any LLM evaluation that
contradicts a script result is wrong by construction.

#### Step 2b — LLM evaluation for the remaining checks ONLY

For every rubric check that **does NOT** carry a `script:` field
(Tier 3 — semantic judgment; Tier 4 — needs runtime; or simply not yet
scripted), launch **one Agent per check** in parallel batches (cap at 16
concurrent). **Never launch an agent for a check that has a `script:`
field** — that result is already locked in from Step 2a and an LLM may not
override, re-evaluate, or "second-guess" it, even if it looks wrong (if a
script is genuinely wrong, fix the script, don't bypass it). Each agent
receives:

```
You are evaluating one check in a gym audit.

Check ID: <category.id>.<check.id>
Principle: <check.principle>
Detector method: <check.detector.method>
Detector steps:
  - <step 1>
  - <step 2>
  ...
Baseline example (for grounding): <check.baseline_example>
Target gym path: <target>
Target gym fingerprint: <relevant slice of fingerprint>
Mapping result for this check: <01-mapping.json[check_id]>
Levels:
  absent:  <levels.absent>
  partial: <levels.partial>
  present: <levels.present>

Run the detector against the target gym. Read files. If the detector method
calls for injecting a bad value and running a build, do it in a scratch copy
under /tmp.

Classify as absent/partial/present.

EVIDENCE QUALITY BAR — every evidence string must be **specific and verifiable**.
Treat each entry as something a reader can re-run themselves. Required shape:

1. **Cite a precise location.** Prefer `<file>:<line>` (e.g. `gym/world.py:34`)
   or `<file>:<symbol>` (e.g. `gym/world.py:WorldState`). Bare file paths are
   acceptable only when the whole file is the evidence (e.g. presence of a
   linter script).
2. **Quote concrete numbers.** If counting, give the actual count and the
   command that produced it. "1150 YAML files (find task_data -name '*.yaml'
   | wc -l = 1150)" — not "many YAML files".
3. **Show the matched content** when the check is a grep. Include the matched
   line verbatim if short, or a representative snippet. Don't just say "the
   linter has the rule" — quote the function signature or the matching line.
4. **For inject-and-run detectors, report the command and its exit/output.**
   "Ran `make validate-tasks` after inserting `unknown_field: 1` into a copy
   of task_001.yaml — exited 1 with `ValidationError: unknown_field` at
   line 42." Not just "validation works."
5. **Multiple supporting bullets are better than one summarizing bullet.**
   Three short verifiable claims beat one paragraph of prose.
6. **Enumerate failing tasks when the check applies per-task.** If a check
   aggregates over the task corpus (any check in a `scope: tasks` category,
   or environment checks that fan out over tasks — e.g. `entity_to_goal_coverage`,
   `prompt_grounds_reward_entities`), and the level is `absent` or `partial`,
   list **every** failing task ID in a dedicated `failing_tasks` array on the
   JSON result. Also surface a compact summary in the evidence ("47/200 tasks
   missing a golden_solution.yaml; see failing_tasks"). Don't truncate — the
   point is that a reader can grep for one ID and reproduce the failure.
   Skip the field when the check is gym-wide (e.g. `per_kind_modules`,
   `generator_determinism`) and no per-task list applies.

Anti-patterns (do NOT produce):
- "There is a linter" (no path, no rule list)
- "Validation seems to work" (no command, no output)
- "Coverage is high" (no number, no source)
- "Convention is followed in most tasks" (no count, no sample)
- "Many tasks lack X" without listing which ones (use `failing_tasks`)

If skipped because no longer applicable, record "skipped: <reason>" with
reasoning that's just as specific.

If absent/partial: write a 1-2 sentence remediation naming a small first step,
referencing the baseline example.

Return JSON:
  {
    "check_id": "...",
    "level": "absent" | "partial" | "present" | "skipped",
    "score": 0.0 | 0.5 | 1.0 | null,
    "evidence": ["file:line — ...", "command output: ...", ...],
    "failing_tasks": ["task_001", "task_017", ...] | null,
    "remediation": "..." | null,
    "skip_reason": null | "domain_specific" | "n/a"
  }

`failing_tasks` is required when the check aggregates over tasks AND the
level is absent/partial; otherwise null. Always list **all** failing IDs —
never truncate.

Under 300 words.
```

For checks under `reward_quality_linting.rule_checks` (the ~28 lint rules):
- Detect by **looking for an equivalent rule** in the target's linter
- If linter exists but rule is missing, classify as `partial` and remediate
  "add this lint rule to <target>/<linter_dir>"
- If no linter at all, classify as `absent` — but note this is a category-level
  finding, not 28 separate findings

Write `sessions/<session_id>/02-evaluation.json`.

### Phase 3 — Cross-cutting (~20 min, serial)

Run cross-cutting checks. These need the gym in motion:

1. **round_trip_parity**: pick 10 random tasks, run the gym's build → seed → grade
   → teardown cycle on each. Use the gym's own `make build`/equivalent. Report
   any phase failure per-task.

2. **calibration_vocabulary**: list all task variants, classify each filename as
   "intent-described" (matches `/(drop|relax|tighten|combo|round|breadcrumb)_/`)
   vs "opaque" (matches `/_v\d+$/`). Compute ratio.

3. **documented_defect_backlog**: locate `KNOWN_ISSUES.md` / `BUGS.md`. Check
   last-modified date; structure; entries-have-status-field.

Write `sessions/<session_id>/03-cross-cutting.json`.

### Phase 4 — Synthesis (~10 min, single agent)

Compute scores and write the report.

1. **Per-category score**: sum(check.severity_weight × check.level_score) /
   max_possible for that category. Skip `domain_specific` checks that were
   marked `skipped` (don't include in denominator).

2. **Load-bearing verdict**: separately compute the status of the 4
   `load_bearing_meta_checks` IDs. If any is `absent`, the report's top-line
   verdict is "structural gap" regardless of overall score.

3. **Top findings**: sort all `absent` + `partial` checks by
   `severity_weight × (1 - level_score)`. The top 15 go in the prioritized
   list.

4. **Universal-aspiration block**: list any `universal_aspirations.ids` that
   landed `absent`/`partial` separately, with a "(also absent in baseline)"
   note so the user doesn't read them as "this gym is worse than baseline."

5. Write the report to `sessions/<session_id>/REPORT.md` (see Template below) plus
   `sessions/<session_id>/04-scored.json` for downstream tooling.

## Report Template

```markdown
# Gym Audit Report — <target name>

**Audited:** <ISO date>
**Auditor rubric:** `lifecycle_rubric.yaml` (schema v<N>)
**Target gym:** <target path>

## Top-line verdict

<one-line verdict based on load-bearing meta-checks + overall score>

| Load-bearing meta-check | Status |
|---|---|
| Closed entity universe | <present/partial/absent> |
| Closed reward-compiler universe | <present/partial/absent> |
| Invariants per check kind | <present/partial/absent> |
| Golden solution per task | <present/partial/absent> |

**Overall score:** <X.XX / 1.00> (weighted across <N> categories,
<M> domain-specific checks skipped)

## Category scores

| Category | Score | Notes |
|---|---|---|
| environment_seeding | 0.XX | ... |
| ...                 | ...  | ... |

## Top 15 prioritized findings

### 1. <Finding name> — <severity>, level: <absent|partial>
**Principle:** <check.principle>
**Evidence:** <bullet list of evidence>
**Remediation:** <1-2 sentences naming a first step>
**Baseline reference:** <baseline_example>

### 2. ...

## Universal aspirations (gaps the baseline shares)

- **<check_id>** — <level>. <remediation>
  *(absent in baseline gym too; treat as universal aspiration)*

## Domain-specific checks skipped

<list of skipped check_ids with one-line reason each>

## Appendix: full check matrix

<table: check_id | level | score | evidence-summary>
```

## Implementation notes

- **Parallelism**: Phase 1 and Phase 2 dispatch via the `Agent` tool with
  `subagent_type: Explore` for read-only mapping/detection. For inject-and-run
  detectors (e.g., `inject_typo`, `inject_unresolved`), use `subagent_type:
  general-purpose` since they need to write scratch files.
- **Scratch directory**: any "inject and run" detector should work in `/tmp/audit-<runid>/`
  and clean up after itself. Never modify files inside `<target>` other than
  writing under `sessions/<session_id>/`.
- **Budget guardrails**: cap Phase 2 at 100 agent calls. If the rubric grows
  past that, batch checks by category (one agent evaluates a whole category).
- **Comparing against baseline**: if the user asks "is target X better/worse
  than baseline Y," run the audit on both, then diff per-check. Highlight
  checks where baseline is `present` and target is `absent`.

## Output

When the user runs `/gym-audit` for the first time:
1. Confirm target path (default to cwd if it looks like a gym).
2. Run Phases 0–4.
3. Print one-paragraph summary to chat: load-bearing status, overall score,
   top 3 findings, link to the full report file.

Subsequent invocations on the same target with `--diff`: re-run, then diff
against the previous `04-scored.json` to show progress/regressions.
