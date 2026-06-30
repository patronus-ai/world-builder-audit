# World Generation Lifecycle

A step-by-step trace of how a task goes from procedural seed → shippable YAML → live world in a container. Each step records its **inputs**, **outputs**, the **linters/assertions** that gate it, and the **files involved**.

The lifecycle has two halves:

- **Authoring** (offline, `task-designer/`) — 15+ stages that generate `task_NNN.yaml` from a grounding doc or random seed.
- **Runtime** (in-container, `gym_github/`) — 3 stages that turn the shipped YAML into a live world + compiled rewards when Taiga calls `setup_problem`.

Read the [Task Design Specification](TASK_DESIGN_SPEC.md) for the data model. This doc is the *flow*.

---

## Quick view

```
                    AUTHORING (task-designer/, offline)
┌───────────────────────────────────────────────────────────────────┐
│  Phase 1 — Skeleton (procedural, no LLM)                          │
│  s01 objective → s02 goals → s03 subgoals → s04 edges →           │
│  s05 action_matrix → 5b/5c/5d/5e → s06 reward declarations         │
│                                                                   │
│  Phase 2 — Hydration (LLM)                                        │
│  s07 narrative → s07b skeleton → s08 hydrate → 8a/8b screenshots │
│  → post-hydration hint gate                                       │
│                                                                   │
│  Phase 3 — Quality                                                │
│  yaml_fixes → reward lint-fix loop → s10 guide audit →            │
│  s11 refine → s12 judge → s13 improve                             │
│                                                                   │
│  Phase 4 — Ship                                                   │
│  final audit + Opus → s14 golden solution → s15 verify+fix        │
└───────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ generated/task_<id>.yaml +
                                    task_data/solutions/<id>_solution.yaml
┌───────────────────────────────────────────────────────────────────┐
│  RUNTIME (gym_github/, in container)                              │
│  load_tasks → world_builder → substitute_world_ids →              │
│  compile_rewards → agent runs → run_reward → Grade payload         │
└───────────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — Skeleton (procedural)

No LLM calls in this phase. Everything is deterministic table-lookup from `task-designer/tables/`.

### Stage 1 — Objective

- **Summary:** Picks the task type (1–N) from `tables/goal_decompositions.yaml` or accepts a grounded one.
- **Input:** Optional grounding YAML (`grounding/<file>.yaml`).
- **Output:** `stage_01.json` — `{task_type_id, description}`.
- **Assertions:** None — this is a free choice.
- **Files:** `stages/s01_objective.py`, `tables/goal_decompositions.yaml`.
- **Audit checks:**
  - `[per-task]` `task_type_id` exists in `tables/goal_decompositions.yaml` (closed set).
  - `[per-task]` `description` ≥ 20 chars and names at least one concrete entity kind from the gym's schema.
  - `[per-task]` When grounded, the grounding file's `objective.task_type_id` matches stage output exactly.
  - `[per-stage]` Stage is deterministic: running twice with the same inputs produces identical output.

### Stage 2 — Goals

- **Summary:** Expands the objective into a goal list. Enforces the **UI-required** invariant: at least one goal must require browser interaction.
- **Input:** Objective + grounding.
- **Output:** `stage_02.json` — `[Goal(id, type, output_type, ...)]`.
- **Assertions:** `_ensure_ui_required()` — fails if no goal would force a UI click (wiki CRUD, visual verification, etc.).
- **Files:** `stages/s02_goals.py`, `models/goals.py`.
- **Audit checks:**
  - `[per-task]` All goal IDs are unique within the task.
  - `[per-task]` Goal count is within `config.structure.goal_count` band.
  - `[per-task]` Every `Goal.type` is a member of the closed `GoalType` enum.
  - `[per-task]` At least one goal is UI-required (matches the same predicate `_ensure_ui_required()` uses).
  - `[per-task]` Every goal references at least one entity kind declared in the gym's closed world schema.
  - `[per-task]` When grounded, every grounding-supplied goal ID appears in the output unchanged.

### Stage 3 — Subgoals and Q&A chains

- **Summary:** Decomposes each goal into subgoals; emits a Q&A chain (length controlled by `config.difficulty.qa_chain_length`) that determines investigation hops + where evidence is placed.
- **Input:** Goal list + config (`config.yaml` difficulty / evidence weights).
- **Output:** `stage_03.json` — subgoals + QA hops + evidence placement weights.
- **Assertions:** Internal consistency of chain length vs goal count.
- **Files:** `stages/s03_subgoals.py`, `tables/subgoal_expansions.yaml`.
- **Audit checks:**
  - `[per-task]` Every goal has at least one subgoal; no orphan goals.
  - `[per-task]` Every subgoal's `parent_id` references a real goal.
  - `[per-task]` QA-chain length per goal equals (or falls within ±1 of) `config.difficulty.qa_chain_length`.
  - `[per-task]` Evidence-placement distribution within the task roughly matches `config.difficulty.evidence_weights` (chi-square or proportion check; don't expect exact).
  - `[per-task]` Subgoal IDs unique across the task.
  - `[per-task]` Each subgoal expansion comes from a row in `tables/subgoal_expansions.yaml` (no LLM-invented decompositions at this stage).

### Stage 4 — Dependency edges

- **Summary:** Builds the goal DAG from edge-pattern templates. Inserts metagoals (ordering traps, destructive-order traps) when `metagoals.*` is configured.
- **Input:** Goals from stage 2.
- **Output:** `stage_04.json` — `{edges: [...], metagoals: [...]}`.
- **Assertions:** `_has_cycle()` — graph must be acyclic.
- **Files:** `stages/s04_edges.py`, `tables/edge_patterns.yaml`.
- **Audit checks:**
  - `[per-task]` DAG check holds (no cycles); auditor re-runs `_has_cycle` on the emitted edges.
  - `[per-task]` Every edge endpoint (`from`, `to`) resolves to a declared goal ID.
  - `[per-task]` Every goal participates in at least one edge OR is explicitly terminal in `tables/edge_patterns.yaml`.
  - `[per-task]` No duplicate edges (same `from→to` pair).
  - `[per-task]` Metagoal IDs are unique and their referenced goals exist.
  - `[per-task]` Edge density falls within `config.structure.edge_density` band.

### Stage 5 — Action matrix

- **Summary:** Walks each entity (repo, wiki, issue, PR, file, …) and emits the action rows the agent could take: target / distractor / read-only.
- **Input:** Goal graph + entity inventory.
- **Output:** `stage_05.json` — `ActionMatrix(entries: [...])`.
- **Assertions:** None at this stage; the matrix is the source for stages 6 and 8.
- **Files:** `stages/s05_action_matrix.py`, `tables/action_matrix.yaml`.
- **Audit checks:**
  - `[per-task]` Every action entry has a target entity declared in the inventory.
  - `[per-task]` target/distractor/read-only ratio matches `config.structure.distractor_ratio`.
  - `[per-task]` No duplicate `(entity, verb)` pairs.
  - `[per-task]` Every verb in the matrix maps to a known reward kind in the gym's reward registry (catches "the world designer planned a verb that the gym can't compile a check for").
  - `[per-task]` Each goal in the DAG has at least one **target** action row (reachable from the seed).
  - `[per-task]` Distractors are paired: for every distractor, at least one same-kind target exists (avoids "distractor with nothing to confuse").

### Substages 5b–5e — Structural planning

Each substage plans one structural concern that hydration must respect.

| Substage | Role | Output | Files |
|---|---|---|---|
| **5b conventions** | Where in-world conventions live (AGENTS.md, CONTRIBUTING, wiki) — *format* only, not answers | `stage_05b.json` Conventions | `s05b_conventions.py` |
| **5c visual findings** | Picks defect types (wrong image, malformed table) + placements (wiki / README / PR review) | `stage_05c.json` `visual_findings_plan` | `s05c_visual_findings.py` |
| **5d distractors** | Plans distractor entities + the guard rewards required to keep them from leaking credit | `stage_05d.json` | `s05d_distractors.py` |
| **5e tech stack** | Primary language, test framework, package manager | `stage_05e.json` | `s05e_tech_stack.py` |

- **Audit checks:**
  - `[per-task]` **5b:** convention placements name a *format* (e.g. "a content surface titled 'Conventions'") and never the *answer*; auditor greps for hint-style phrases ("do not", "this is the bug") in any convention body and fails on hit.
  - `[per-task]` **5c:** visual-finding count matches `config.difficulty.visual_finding_count`; every `defect_type` is in the closed catalog; every `placement` belongs to the closed set of agent-visible content surfaces.
  - `[per-task]` **5d:** distractor count matches `config.structure.distractor_count`; every distractor declares a **guard reward kind** (`no_extra_*`); for each target reward, at least one structural distractor exists. *This is the per-task analog of the rubric check [`distractors_procedurally_generated`].*
  - `[per-task]` **5e:** every tech-stack choice belongs to the closed set declared in `config`; cross-choices are internally consistent (no mismatched language / build tool pairs).
  - `[per-stage]` All four substage outputs must be deterministic given the same seed + config + previous stages — auditor re-runs and diffs.

### Stage 6 — Reward declarations + coverage manifest

- **Summary:** Materializes the action matrix into compiler-format reward declarations (`agent_created_issue`, `file_content_replaced`, `state_unchanged`, …) and builds a **coverage manifest**: every reward maps to evidence pointers (files / wiki / issues / reasoning hops).
- **Input:** Action matrix + conventions + distractor plan + tech stack.
- **Output:** `stage_06.json` — `{rewards: [...], coverage: [...]}`.
- **Assertions:**
  - Every reward has a matching coverage row (by exact `name:`).
  - No orphan or template rows (`TARGET_REPO_*`, "File an issue on this target repo").
  - Evidence entities + artifacts must exist in the world.
- **Files:** `stages/s06_rewards.py`, `prompts/reward_compiler_spec.md`, `gym_github/table_writes.py` (write-table source of truth).
- **Audit checks:**
  - `[per-task]` Every `reward.kind` is in the gym's registered closed reward universe (closed-check-universe invariant at design time).
  - `[per-task]` Each declared write-target (`writes_to:` or equivalent) is in the gym's closed set of agent-writable surfaces.
  - `[per-task]` For every action whose target is a writable surface, a dedup field (`accounted_by` or equivalent) is present — else the corresponding "no-extra-X" guard will over-fire at grade time.
  - `[per-task]` Target/distractor reward count matches the matrix from stage 5 — no rewards added or dropped.
  - `[per-task]` Coverage manifest is bijective with rewards: `len(coverage) == len(rewards)`, paired by exact `name:`.
  - `[per-task]` No template placeholders in reward names (`TARGET_REPO_*`, generic verbs, etc.).
  - `[per-task]` Evidence pointers resolve: every `(entity_kind, entity_id, artifact_path)` triple has a planned home in the world (will be filled by hydration).
  - `[per-task]` Mutual-exclusion sets cover all sibling action verbs on the same entity (e.g. `create_X` vs `edit_X` cannot both award credit).

---

## Phase 2 — Hydration (LLM)

### Stage 7 — Narrative

- **Summary:** First LLM call. Turns the procedural skeleton into a real-world narrative (story, entity names, terminology) without inventing structure.
- **Input:** Procedural artifacts from 1–6 + seed-data samples from `task-designer/seed-data/seed.db`.
- **Output:** `stage_07.json` — `NarrativeOutput(entities, conventions, narrative_hints)`.
- **Assertions:** JSON shape validated by Pydantic (`models/narrative.py`).
- **Files:** `stages/s07_narrative.py`, `prompts/narrative.md`.
- **Audit checks:**
  - `[per-task]` Entity name diversity: no all-Greek-letter (`alpha/beta/gamma`) or all-generic (`entity1/entity2`) sets; auditor flags Levenshtein-similarity > 0.7 across same-kind entities.
  - `[per-task]` Entity count per kind matches stage 5 inventory exactly (LLM didn't add or drop entities).
  - `[per-task]` `narrative_hints` body contains zero matches against the hint-leak regex (same patterns used by `_check_answer_hints`).
  - `[per-task]` Domain vocabulary is present in `conventions` — terminology matches the task's stated domain rather than generic verbs.
  - `[per-task]` Every entity ID referenced by stages 1–6 has a name field assigned.
  - `[per-task]` Auditor re-runs LLM verification by sampling 3 entity descriptions and asking a separate verifier: "does this read like a real-company artifact or like a template?"

### Stage 7b — YAML skeleton

- **Summary:** Builds a **parseable, linter-clean** YAML skeleton with `LLM_MUST_FILL_THIS_PLACEHOLDER` tags. No LLM. Hydration fills placeholders rather than inventing structure.
- **Input:** Narrative output + procedural stages 1–6.
- **Output:** `task_<id>_skeleton.yaml` — full file shape, just unfilled.
- **Assertions:** `has_placeholders()` lists outstanding tags; structural sanity (`_to_commented` round-trip).
- **Files:** `stages/s07b_skeleton.py`.
- **Audit checks:**
  - `[per-task]` Skeleton parses with `yaml.safe_load`.
  - `[per-task]` Round-trip stable: `yaml.dump(yaml.safe_load(skel)) == skel` (modulo formatting).
  - `[per-task]` Required top-level sections present (whatever the gym's task schema mandates — e.g. world block, bootstrap, task, coverage manifest).
  - `[per-task]` Every `LLM_MUST_FILL_THIS_PLACEHOLDER` carries a comment hint describing what to fill (else hydration LLM has no signal).
  - `[per-task]` Every reward from stage 6 has a corresponding entry in `task.rewards` (even if fields are placeholders).
  - `[per-task]` Every entity from stage 7 has a skeleton row in `world.*` with the correct ID.
  - `[per-task]` `tools:` is the gym's canonical tool list — no truncation, no foreign tools.

### Stage 8 — Hydrate world YAML

- **Summary:** LLM fills placeholders in chunks (per-repo, per-section) using `prompts/hydrate.md`. Produces the full world.
- **Input:** Skeleton + narrative + reward declarations.
- **Output:** `task_<id>_hydrated.yaml`.
- **Assertions:**
  - `_validate_structure()` — round-trip parse + section presence.
  - `_attempt_yaml_repair()` — auto-fixes common YAML quoting errors.
- **Files:** `stages/s08_hydrate.py`, `prompts/hydrate.md`.
- **Audit checks:**
  - `[per-task]` **Zero surviving placeholders** — `LLM_MUST_FILL_THIS_PLACEHOLDER` count == 0 across the file.
  - `[per-task]` **Entity reference closure** — every cross-reference field (whatever names the gym uses for "owner", "actor", "subject", "collaborator", etc.) resolves to a declared entity in the same file.
  - `[per-task]` **Reward → world reachability** — every entity referenced by a reward declaration has a hydrated row (per-task analog of `entity_references_resolve` and `reward_to_entity_resolution_at_generator`).
  - `[per-task]` **Prompt → reward grounding** — every entity referenced by a reward is mentioned (by name or unambiguous descriptor) in the `task.prompt` (per-task analog of `prompt_grounds_reward_entities`).
  - `[per-task]` **World schema validates** — running the gym's world-state validator on the parsed YAML succeeds.
  - `[per-task]` **Entity counts match plan** — counts per entity kind match the stage 5 + stage 7 inventory.
  - `[per-task]` **No fabricated fields** — every key in the YAML is allowed by the closed Pydantic schema (catches LLM-invented properties).
  - `[per-batch]` **Distractor identities differ across variants** — when a variant family shares a skeleton, the hydrated distractor names must vary (per-task analog of `cross_variant_entity_consistency`).

### Stages 8a + 8b — Visual findings

- **Summary:** If 5c planned visual findings, 8a writes screenshot prompts from world context; 8b renders them (Chrome or Pillow) and injects `content_base64` into the YAML.
- **Input:** Hydrated YAML + visual plan from 5c.
- **Output:** `task_<id>_hydrated_with_screenshots.yaml`.
- **Assertions:** Image URL format — leading slash, namespace, no bare relative paths in wiki.
- **Files:** `stages/s08a_visual_prompts.py`, `stages/s08b_screenshots.py`.
- **Audit checks:**
- **Audit checks** *(skip this entire block for non-visual gyms — CLI/headless gyms have no rendered media to validate):*
  - `[per-task]` Every visual finding from 5c has either a generated screenshot OR a scoped lint-ignore annotation (deliberate-defect path).
  - `[per-task]` Image URLs follow the gym's namespace convention.
  - `[per-task]` No bare relative paths in any agent-rendered content.
  - `[per-task]` Embedded media blobs decode + match an allowed MIME type.
  - `[per-task]` Visual-prompt text contains no answer leakage (run hint scanner over it).
  - `[per-task]` Visual prompts reference entities that exist in the hydrated YAML (no "render entity Foo" when Foo isn't in the world).

### Post-hydration hint gate

- **Summary:** Scans every agent-visible string for answer leakage ("do not migrate", "out of scope", "this is the bug") and rewrites via LLM. Skips `task_design_commentary` and `task.coverage` (reviewer-only fields).
- **Input:** Hydrated YAML.
- **Output:** YAML with offending strings reworded.
- **Assertions:** Hint regex matches from `_check_answer_hints` in `reward_linter.py`.
- **Files:** `stages/s08_post_hydration_gate.py`.
- **Audit checks:**
  - `[per-task]` Re-run the hint scanner on the post-gate output; expect zero matches.
  - `[per-task]` Field-scope correctness: scanner did not rewrite reviewer-only fields (commentary, coverage manifest, etc.).
  - `[per-task]` Reword diff size is small: each replaced span ≤ 2× original length (catches over-rewriting that changes semantics).
  - `[per-task]` Cross-field consistency: when a hint mentions an entity (e.g. "this artifact X is the bug"), the reworded text still mentions a comparable entity (the gate didn't silently delete the reference).

---

## Phase 3 — Quality gates

This phase loops: lint → fix → re-lint until clean or budget exhausted.

### `yaml_fixes.py` + reward lint-fix loop

- **Summary:** Programmatic fixes that don't need an LLM pass (canonical `tools:` list, `start_url`, wiki `body`→`content`, `state_unchanged` table lists, `accounted_by` auto-population, regexp quoting). Then `_lint_fix_loop` runs the reward linter and either applies fixes or asks an LLM agent to repair.
- **Input:** Hydrated YAML.
- **Output:** Linted YAML; remaining findings persisted to `drafts/.../lint_findings.json`.
- **Assertions:** **Blocking** lint categories (must fix or scope-suppress):
  - `COVERAGE_*` (missing, orphan, invalid entity, missing artifact)
  - `BROKEN_IMAGE_URL`, `MEDIA_URL_CASE_MISMATCH`, `WIKI_IMAGE_CONFLICT`
  - CRITICAL SQL/parse errors
- **Files:** `yaml_fixes.py`, `stages/reward_linter.py`, `prompts/lint_suppressions.md`.
- **Audit checks:**
  - `[gym-wide]` **Linter presence** — a reward-linter binary exists and is wired into the pipeline orchestrator.
  - `[gym-wide]` **Rule coverage** — every rule listed in the gym's lint-rule manifest exists in the linter codebase.
  - `[per-task]` **Blocking categories clean** — `lint_findings.json` has zero unresolved blocking findings; any suppression has a `# lint-ignore:` comment with scope.
  - `[per-task]` **No silent drops** — finding count after fix loop ≤ before; any net-new findings mean the loop regressed.
  - `[per-task]` **Suppression discipline** — every `# lint-ignore` carries a one-line reason; auditor flags suppressions without rationale.
  - `[per-task]` **Loop terminates** — number of LLM repair iterations < `config.lint.max_attempts` (else flag "loop budget exhausted, ship anyway" as a smell).

### Stage 10 — Guide audit

- **Summary:** Runs `scripts/guide_task_design.py` (static + LLM review): undisclosed constraints, reward-hacking review, narrative coherence.
- **Input:** Linted YAML.
- **Output:** `stage_10.json` with findings.
- **Assertions:** Findings classified as `static`, `undisclosed_constraints`, `reward_hacking`, `llm_review`.
- **Files:** `stages/s10_validate.py`, `scripts/guide_task_design.py`.
- **Audit checks:**
  - `[per-task]` Findings carry a category, severity, and a YAML pointer (jsonpath or file:line).
  - `[per-task]` Reward-hacking review specifically reasons about each reward in turn — auditor counts review entries vs reward count and flags any reward never mentioned.
  - `[per-task]` LLM review confidence is recorded (cheap-judgment vs strong-judgment).
  - `[per-stage]` Audit re-runs are stable: re-running stage 10 on the same input must produce the same finding count ± small noise budget.

### Stage 11 — Refine

- **Summary:** Claude Agent SDK fixes the YAML based on stage-10 findings, batched by category.
- **Input:** Findings + YAML.
- **Output:** Refined YAML; on no-progress, raises.
- **Assertions:** Inherits stage-10 finding gates.
- **Files:** `stages/s11_refine.py`.
- **Audit checks:**
  - `[per-task]` Net finding count after refine < before (no-progress is a fail-state).
  - `[per-task]` No new blocking findings introduced — auditor diffs before/after and flags any net-new `BLOCKING_*` category.
  - `[per-task]` Diff is targeted: edits touch only sections referenced in findings (no full-file rewrites).
  - `[per-task]` Refined YAML still passes linter (no regressions on rules already clean).
  - `[per-task]` Entity count + reward count unchanged before/after refine (no silent drops while fixing).

### Stage 12 — Blind judge

- **Summary:** Sonnet does a **blind A/B comparison** vs `task_001_licensing_audit_hard.yaml` (random side assignment).
- **Input:** Refined YAML + exemplar.
- **Output:** `stage_12.json` — verdict + reasoning.
- **Assertions:** Pass criteria: reward specificity, distractor quality, chain depth, narrative, action-matrix coverage, UI requirement.
- **Files:** `stages/s12_judge.py`, `prompts/judge.md`.
- **Audit checks:**
  - `[per-batch]` Side assignment is recorded and randomized (auditor checks the side-assignment log for ~50/50 distribution across a batch).
  - `[per-task]` Verdict has scores on every required dimension (reward specificity, distractors, chain depth, narrative, coverage, UI).
  - `[per-task]` Reasoning cites concrete YAML sections (line numbers / jsonpaths) — no vague "this task is better" claims.
  - `[per-batch]` Auditor spot-runs judge with sides swapped on a sample of N tasks and expects consistent preferences (a flippy judge means weak criteria).

### Stage 13 — Improve

- **Summary:** Up to `max_improvement_rounds` LLM passes applying judge feedback.
- **Input:** Judge verdict + YAML.
- **Output:** Improved YAML.
- **Assertions:** Re-runs judge for verification.
- **Files:** `stages/s13_improve.py`.
- **Audit checks:**
  - `[per-task]` Improvement diff targets only judge-flagged sections (no full rewrites).
  - `[per-task]` Post-improvement judge run shows non-decreasing score on every dimension.
  - `[per-task]` Reward count unchanged before/after improvement.
  - `[per-task]` Linter remains clean after improvement (no regressions).
  - `[per-task]` Total LLM rounds used ≤ `max_improvement_rounds`; if equal, log it as a quality smell.

---

## Phase 4 — Ship

### Final audit + Opus corrective pass

- **Summary:** Runs `s10_validate` + `guide_task_design.py` once more; batched Opus Agent SDK fixes any remaining audit issues; final lint-fix loop with the same blocking categories.
- **Input:** YAML after stage 13.
- **Output:** Ship-candidate YAML.
- **Assertions:** Same blocking categories as Phase 3.
- **Files:** `run.py` `_final_audit`, `stages/reward_linter.py`.
- **Audit checks:**
  - `[per-task]` Final lint findings count = 0 in blocking categories (else block ship).
  - `[per-stage]` Idempotency: re-running the final audit must produce identical findings (no flakiness across runs).
  - `[per-task]` Reward + entity counts unchanged from stage 13 (no silent drops while fixing).
  - `[per-task]` Opus diff scope: edits limited to flagged sections; auditor flags refactors that touch the whole task body.

### Stage 14 — Golden solution

- **Summary:** Batched LLM emits a `task_<id>_solution.yaml` describing the trajectory + final-state mutations a perfect agent would produce.
- **Input:** Final task YAML.
- **Output:** `task_data/solutions/task_<id>_solution.yaml`.
- **Assertions:** Solution YAML shape parse + entity-reference resolution.
- **Files:** `stages/s14_solution.py`, `stages/solution_helpers.py`.
- **Audit checks:**
  - `[per-task]` Solution YAML parses; every entity reference resolves to a world entity.
  - `[per-task]` **Reward coverage** — for every reward in the task, the solution has at least one trajectory step or final-state mutation that targets it.
  - `[per-task]` No magic numbers/strings — every value in the solution is derivable from (or quoted from) the world YAML; no LLM-invented identifiers.
  - `[per-task]` File-edit instructions match `solution_helpers.py` schema (no free-form prose where the harness expects JSON).
  - `[per-task]` Trajectory length is plausible: < `config.solution.max_trajectory_length` steps; > 1 step (a one-step solution is a smell).

### Stage 15 — Verify + fix

- **Summary:** Runs `tests/reward_harness.py` against the compiled rewards using the emitted solution. If any reward fails, LLM diagnoses + fixes either the **solution** or the **task definition**, then retries (up to `solution.fix_max_attempts`, default 24).
- **Input:** Task YAML + solution YAML.
- **Output:** Both files in mutually-consistent final state, OR pipeline failure if budget exhausted.
- **Assertions:**
  - Every reward must `pass=true` against the solution. *This is the analog of the rubric check `solution_satisfies_all_rewards`.*
  - Structural task errors (unparseable rewards, missing tables) short-circuit to task-side fixes.
- **Files:** `stages/s15_solution_fix.py`, `tests/reward_harness.py`, `gym_github/reward_compiler/`.
- **Audit checks:**
  - `[per-task]` Final reward-harness run shows **N/N pass** (no waivers). Auditor re-runs the harness as an independent verification.
  - `[per-task]` Attempts used < `solution.fix_max_attempts` — burning the budget is a quality smell flag.
  - `[per-batch]` Diagnosis classification — across the batch, fix attempts split between **task** and **solution** patches roughly evenly. Per-task lopsidedness ("always patched the solution") is also a smell.
  - `[per-task]` No regression — rewards that passed in attempt N must still pass in attempt N+1; auditor checks for pass→fail flips across fix iterations.
  - `[per-task]` Both files (`generated/task_<id>.yaml` + `task_data/solutions/task_<id>_solution.yaml`) are written atomically; auditor checks mtimes to confirm they were updated in lock-step.

**Final output of authoring:** `generated/task_<id>.yaml` + `task_data/solutions/task_<id>_solution.yaml`.

---

## Runtime — In-container instantiation

When Taiga calls `setup_problem(problem_id, ...)`:

### R1 — Load task

- **Summary:** Reads the task definition; resolves `definition.yaml` or the consolidated `tasks_world.json`.
- **Input:** `problem_id` (UUID-shaped).
- **Output:** `Task` Pydantic model — `(prompt, tools, rewards, world, bootstrap_data, evidence)`.
- **Assertions:** Pydantic validation; unknown reward kinds reject at load.
- **Files:** `gym_github/task_loading.py`, `gym_github/task.py`.
- **Audit checks:**
  - `[per-task]` `task.id` matches the source filename or the manifest key — no name drift.
  - `[per-task]` Every reward `kind` is in the gym's registered closed reward universe.
  - `[per-task]` All `tools:` strings exist in the gym's registered tool catalog.
  - `[per-task]` Every bootstrap identity (e.g. agent user) resolves to a declared entity in the world.
  - `[per-stage]` Loading is deterministic: same task ID returns byte-identical Task across calls.

### R2 — Build the world

- **Summary:** `WorldBuilder` validates the `world:` block into a `WorldState`, wipes/lays-on-top of the DB per `seed_base`, INSERTs all rows, `git init`s repos, creates branches, snapshots per-table checksums.
- **Input:** `Task.world`, `bootstrap_data.agent_user_id`.
- **Output:** Populated SQLite DB + git repos under `/tmp/.git-server`; `id_map`, `number_map`, `next_number_map` for substitution.
- **Assertions:**
  - `WorldState.model_validate` — closed entity universe, typed kinds.
  - Cross-entity invariants from `world_schema.py` validators (every `author:` resolves to a declared user, etc.).
  - Per-table checksums stored in `_world_builder_state` for later freeze detection.
- **Files:** `gym_github/world_schema.py`, `gym_github/world_builder.py`.
- **Audit checks:**
  - `[per-task]` Post-build resource counts (DB rows, files, services, etc.) match the world declaration per kind.
  - `[per-task]` The post-seed snapshot store exists and has one entry per audited resource container.
  - `[per-task]` Per-item checksums present (not just aggregate hashes) — required for carve-out freezes downstream.
  - `[per-task]` Agent identity has the permissions required to act on every target resource (per `agent_permission_seeding` rubric check).
  - `[per-task]` Every external resource declared in the world (repos, services, file trees, datasets) is materialized at the expected path and reachable through the gym's standard accessor.
  - `[per-stage]` Build is idempotent under a "wipe then seed" base — running twice produces identical checksums.

### R3 — Substitute IDs

- **Summary:** `substitute_world_ids` walks the *entire* task dict (rewards, prompt, bootstrap_data, evidence) replacing `$world${...}`, `$world_number${...}`, `$next_number${...}` with live values from the maps built in R2.
- **Input:** Task dict + `id_map`/`number_map`/`next_number_map`.
- **Output:** Substituted Task dict — runtime IDs everywhere.
- **Assertions:** **Unresolved substitution logging** — any placeholder that survives is logged and treated as a fatal error (resilient-substitution invariant).
- **Files:** `gym_github/world_builder.py:substitute_world_ids`.
- **Audit checks:**
  - `[per-task]` Post-substitution scan: zero of the gym's substitution tokens survive in the task dict.
  - `[per-task]` Every substituted value maps to a valid runtime ID (UUID, integer, etc.) — no `None`, no `null` strings.
  - `[per-task]` Substitution walks the full tree — auditor checks recursion-depth log against expected (catches "only top-level got substituted").
  - `[per-task]` `task.prompt` substitutions are non-empty when rewards use placeholders (catches a prompt-side regression where the substitution skipped the prompt).

### R4 — Compile rewards

- **Summary:** Each declarative `check:` reward is dispatched through the `@register` registry to a per-kind compiler (`issue`, `pr`, `commit`, `file`, `wiki`, `state`, `misc`, `guards`). The compiler emits SQL + Python predicates the grader can execute.
- **Input:** Substituted reward list + live world.
- **Output:** Compiled `Task` with executable reward functions held by the gym.
- **Assertions:**
  - `scope_inference` materializer fills `scope:` defaults.
  - `auto_populate_accounted_by` — populates dedup keys for `no_extra_*` guards.
  - Mutual exclusion sets validated.
  - Per-check Pydantic models reject malformed args.
  - v3 emission gate verifies evidence + `evidence_strict`.
- **Files:** `gym_github/reward_compiler/__init__.py`, `gym_github/reward_compiler/compilers/*.py`, `gym_github/reward_compiler/registry.py`.
- **Audit checks:**
  - `[per-task]` Every reward kind in the input is dispatched (count of registry hits == reward count).
  - `[per-task]` Compiled output is **executable**: auditor compiles + dry-runs each predicate against the live snapshot and checks for runtime errors (analog of `compiled_output_executes`).
  - `[per-task]` Mutual exclusion sets are pairwise disjoint for sibling verbs on the same entity (per `mutual_exclusion_between_checks`).
  - `[per-task]` `accounted_by` populated for every `no_extra_*` guard targeting a write-table.
  - `[per-stage]` Compilation is **deterministic**: compile twice and diff (`compiler_output_determinism`).
  - `[per-task]` When `evidence_strict: true`, every reward has a non-empty evidence block — else emission fails.

### R5 — Agent runs, then grade

- **Summary:** Agent drives the browser. On `grade_problem`, the gym rebuilds the trajectory from `/tmp/taiga_github_adapter/tool_calls.jsonl` + the trailing assistant text, runs every compiled reward against live DB state, packages a `Grade` payload.
- **Input:** Trajectory + live DB state.
- **Output:** `Grade(subscores, failing_details)` returned over MCP.
- **Assertions:** Binary scoring (each reward → 0.0 or 1.0); `failing_details` carries per-reward diagnostic text for QA.
- **Files:** `gym_github/server.py`, `gym_github/taiga_transport.py`, `gym_github/rewards.py`.
- **Audit checks:**
  - `[per-task]` Subscore count == reward count (no rewards silently dropped at grade time).
  - `[per-task]` Every score ∈ {0.0, 1.0}; no NaN, no fractional, no missing.
  - `[per-task]` Every failing reward carries a non-empty `failing_details` message (so QA can triage).
  - `[per-task]` Grade payload schema validates against the Taiga contract (no extra fields, all required fields present).
  - `[per-stage]` Re-grading the same trajectory yields identical scores — grader determinism.
  - `[per-task]` When agent's golden solution is replayed, expect N/N pass (this is the runtime mirror of stage-15's harness check).

---

## Lint rules — when each fires

| Rule | Stage | Source |
|---|---|---|
| `_check_answer_hints` | post-hydration gate | `task-designer/stages/reward_linter.py` |
| `_check_coverage_*` | reward lint-fix loop | `reward_linter.py` |
| `BROKEN_IMAGE_URL`, `MEDIA_URL_CASE_MISMATCH`, `WIKI_IMAGE_CONFLICT` | lint-fix loop | `reward_linter.py` |
| `_check_label_seeding`, `_check_branch_seeding`, etc. (entity-ref invariants) | lint-fix loop | `reward_linter.py` |
| Pydantic field validators on `WorldState` | R2 (world builder) | `gym_github/world_schema.py` |
| `model_validator` cross-entity rules | R2 | `gym_github/world_schema.py` |
| `unresolved_substitution_logging` | R3 (substitution) | `gym_github/world_builder.py` |
| `compiler_receipts_validated` (per-kind Pydantic) | R4 (compile) | `gym_github/reward_compiler/models.py` |
| `scope_inference` materializer | R4 | `gym_github/scope_inference.py` |

---

## Files cheat sheet

**Authoring side**
- `task-designer/run.py` — orchestrator
- `task-designer/stages/sNN_*.py` — one file per stage
- `task-designer/stages/reward_linter.py` — the lint pass
- `task-designer/tables/*.yaml` — procedural grammar (goals, edges, actions)
- `task-designer/prompts/*.md` — LLM prompts
- `task-designer/config.yaml` — difficulty + LLM knobs
- `task-designer/drafts/task_<id>/` — resumable per-stage artifacts
- `task-designer/generated/task_<id>.yaml` — final task

**Runtime side**
- `gym_github/task_loading.py` — task model loader
- `gym_github/world_schema.py` — `WorldState` Pydantic
- `gym_github/world_builder.py` — DB + git materialization, substitution
- `gym_github/reward_compiler/` — declarative → executable rewards
- `gym_github/rewards.py` — reward base classes
- `gym_github/server.py` — meta `setup_task` / `run_reward`
- `gym_github/taiga_transport.py` — Taiga MCP shim
- `task_data/tasks_world.json` — consolidated task list loaded at runtime
- `task_data/solutions/task_<id>_solution.yaml` — golden solution per task

---

## Where each rubric audit check lives in this lifecycle

| Audit check | Lifecycle step |
|---|---|
| `entity_to_goal_coverage` | Stage 5 + Stage 6 |
| `reward_to_entity_resolution_at_generator` | Stage 6, lint-fix loop |
| `subgoal_supports_goal` | Stage 3 + Stage 4 (DAG) |
| `generator_parameter_space_enumerated` | `config.yaml` declared axes |
| `generator_determinism` | Stages 1–6 (procedural, seeded) |
| `cross_variant_entity_consistency` | Shared `grounding/` + skeleton (7b) |
| `prompt_grounds_reward_entities` | Hydration + hint gate |
| `distractors_procedurally_generated` | Stage 5d + Stage 8 |
| `solution_satisfies_all_rewards` | Stage 15 (verify + fix loop) |
| `closed_entity_universe` | R2 — `WorldState.model_validate` |
| `closed_check_universe` | R4 — `@register` dispatch |
| `kind_specific_invariants` | R4 — per-kind Pydantic |
| `golden_solution_exists` | Stage 14 output |

---

## Using these checks — supervisor agent workflow

Each **Audit check** above is tagged with its scope:

- **`[per-task]`** — run on every task. The default; the bulk of the checks.
- **`[per-stage]`** — a property of the stage itself (determinism, idempotency). Verify once per pipeline build using a sample task; once verified, trust until the stage code changes.
- **`[per-batch]`** — only meaningful across a batch (judge side-assignment, cross-variant diversity, fix-attempt classification distribution).
- **`[gym-wide]`** — once per gym (linter presence, lint-rule coverage).

A supervisor agent watches the world-designer pipeline and runs the per-stage audit checks after each stage commits. Suggested protocol:

1. **Pre-stage** — read the stage's `draft/.../stage_<NN-1>.json` input. Confirm the prior stage's outputs match the next stage's inputs (e.g., stage 5 needs the stage-2 goal IDs intact).
2. **Post-stage** — run the **Audit checks** for that stage against the new `stage_<NN>.json` (or YAML for hydration stages). Failures are categorized:
   - **BLOCK** — a hard invariant violated (cycle, unresolved placeholder, missing reward kind). Pipeline must halt.
   - **REGRESS** — counts shrank or finding-count grew vs prior stage. Roll back or rerun.
   - **SMELL** — quality signal (budget burned, low entity diversity, narrow distractors). Log + ship-or-reject by policy.
3. **Cross-stage** — once a stage passes, the supervisor records its evidence so later stages can reuse it (avoids re-counting entities at every step).
4. **Final ship gate** — run the full `audit/rubric.yaml` rubric one last time against the shipped task; require all load-bearing meta-checks green.

A useful first implementation is a single Python script `task-designer/supervisor.py` that loads `stage_<NN>.json`, dispatches to per-stage check functions (`audit_stage_01`, `audit_stage_02`, …), and writes `drafts/<id>/audit_<NN>.json` next to each stage artifact. The script is **pure Python** for ~85% of the checks (Tier 1/2 in the audit rubric); only judge-side and runtime checks need agents.
