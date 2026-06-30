# Deterministic audit scripts

Each script in this folder evaluates one or more lifecycle-rubric checks
**without LLM judgment** — pure file inspection, parsing, counting, graph
traversal, or grep. The results are reproducible byte-for-byte from the gym
filesystem alone.

The gym-audit skill calls these scripts **before** asking any LLM-evaluator
to assess the same checks. Where a script exists, its result is the source
of truth; LLM evaluation is only used for the remaining (Tier 3 / Tier 4)
checks that require semantic judgment or runtime execution.

## How a script works

1. Import helpers from `_common.py`.
2. Define one function per check. Each function takes no arguments and
   returns a `CheckResult` whose `check_id` matches the rubric's check id.
3. Export a `CHECKS = [(rubric_key, fn), …]` registry at module bottom,
   where `rubric_key` is the full `stage_id.check_id` string.

The orchestrator (`run_all.py`) discovers every `CHECKS` registry,
runs the functions, and merges results into the most-recent session's
`04-scored.json` under `lifecycle_evaluations`.

## Running

```bash
# Run all deterministic scripts and merge into the latest session
uv run python audit/scripts/run_all.py

# Dry-run — print summary without writing
uv run python audit/scripts/run_all.py --print-only

# Merge into a specific session
uv run python audit/scripts/run_all.py --session self-20260623T174804
```

## Adding a new deterministic check

1. Find the check's `stage_id.check_id` in `audit/lifecycle_rubric.yaml`.
2. Pick the right script (or create a new one named after the stage).
3. Add a function returning a `CheckResult`; use `bucket_to_result(...)` for
   per-task checks or `gym_wide_result(...)` for gym-wide ones.
4. Register it in the file's `CHECKS = [...]` list.
5. Add a `script: audit/scripts/<file>.py::<fn>` field to the check in
   `audit/lifecycle_rubric.yaml` so the viewer can mark it as deterministic
   and the skill knows to skip its LLM evaluation.

## What belongs here

- **YES**: pass-rate computation from draft artifacts; closed-set
  membership; uniqueness; cycle detection; reference resolution; file
  presence; YAML parse; counts vs config bands; lint-rule existence in code.
- **NO**: anything requiring an LLM judgment about meaning, vibe, or
  semantic correctness; anything that requires running the gym container.

If you're unsure, check what the rubric's `what:` text actually asserts —
if a human auditor would resolve it by writing a Python loop, it belongs
here.
