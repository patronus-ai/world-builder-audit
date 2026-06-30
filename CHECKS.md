# Gym Audit — Check Reference

Detailed catalogue of every check in [`audit/rubric.yaml`](rubric.yaml).

**Conventions used in this document:**
- **Baseline reference** points at where this gym (gym-cua-anthropic) implements the pattern, for grounding.
- **Load-bearing meta-check** dominates the top-line verdict; an `absent` here outweighs many smaller `present` checks.

---

## Table of contents

1. [Load-bearing meta-checks](#load-bearing-meta-checks) — the 4 structural questions
2. [environment_seeding](#environment_seeding) — 8 checks
3. [reward_compilers](#reward_compilers) — 9 checks
4. [check_composition](#check_composition) — 7 checks
5. [task_design_discovery](#task_design_discovery) — 4 checks
6. [self_documentation](#self_documentation) — 4 checks
7. [calibration_discipline](#calibration_discipline) — 3 checks
8. [validation_infrastructure](#validation_infrastructure) — 8 checks (incl. golden solutions)
9. [linters](#linters) — 28 rule checks + 5 infrastructure checks
10. [deployment_pipeline](#deployment_pipeline) — 6 checks
11. [qa_observability](#qa_observability) — 5 checks
12. [runtime_correctness](#runtime_correctness) — 5 checks
13. [Cross-cutting](#cross-cutting) — 2 checks (round-trip, vocabulary)

---

## Load-bearing meta-checks

The four checks below determine whether the gym can catch invalid reward configurations *in principle*. If any is `absent`, the audit's top-line verdict is "structural gap" — independent of how well other checks score.

| ID | Why load-bearing |
|---|---|
| `environment_seeding.closed_entity_universe` | Without a closed typed entity set, no schema-level invariant can be enforced |
| `reward_compilers.closed_reward_compiler_universe` | Without a closed set of check kinds, you can't enumerate what needs invariants |
| `reward_compilers.invariants_per_check_kind` | Without invariants, task authors can declare semantically broken rewards that look syntactically fine |
| `validation_infrastructure.golden_solution_per_task` | Tasks without goldens are unverified theory; you can't prove the reward set actually grades the right thing |

---

## environment_seeding

How the gym constructs the initial state each task runs against. The foundation: if seeding is unreliable or unstructured, everything above it is fragile.

### environment_seeding.declarative_seed_specs

| Field | Value |
|---|---|
| Baseline | `task_data/worlds/*.yaml` |

**What is checked.** Every task has a single structured spec file describing the initial state — *not* a Python script with imperative `seed()` calls or a hand-curated DB dump.

**How it is checked.**
1. List files under the gym's task directory.
2. Classify each: `.yaml`/`.json`/`.toml` → declarative; `.py` containing `def setup()` or `def seed()` → imperative.
3. Compute the declarative ratio.

**Levels.**
- `absent` — every task is a Python script or SQL fixture.
- `partial` — mix of declarative and imperative.
- `present` — >90% declarative.

---

### environment_seeding.schema_validation

| Field | Value |
|---|---|
| Baseline | `WorldState.model_validate` (pydantic) |

**What is checked.** Malformed seed specs fail at build time with a typed error message, not silently at runtime.

**How it is checked.**
1. Grep for `model_validate` / `jsonschema` / `pydantic` / `TypedDict` in the seed loader module.
2. Inject a bad field (e.g., wrong type, missing required field) into a copy of one spec.
3. Run the build; expect non-zero exit with a typed error pointing at the bad field.

**Levels.**
- `absent` — no validation; runtime failures only.
- `partial` — validation exists but skips inner objects or yields opaque errors.
- `present` — typed validator with field-level error messages, runs at build.

---

### environment_seeding.stable_id_substitution

| Field | Value |
|---|---|
| Baseline | `substitute_world_ids` in `gym_github/world_builder.py` |

**What is checked.** Specs reference entities by author-chosen IDs (e.g., `user_alice`, `repo_main`) and a substitution layer maps these to runtime identifiers (UUIDs, generated paths, sequence numbers) before use.

**How it is checked.**
1. Grep for substitution syntax: `$world${...}` / `{{...}}` / `@ref` / `<<...>>`.
2. Trace the substitution function — confirm it walks the whole spec tree (dicts, lists, strings).
3. Verify it handles multiple ID kinds: entity refs, sequence numbers, derived/next IDs.

**Levels.**
- `absent` — tasks hardcode runtime IDs (UUIDs literally in spec).
- `partial` — substitution only for one ID kind.
- `present` — entity refs + sequence/number refs + derived/next refs.

---

### environment_seeding.post_seed_snapshot

| Field | Value |
|---|---|
| Baseline | `_world_builder_state` table with `row_checksums` |

**What is checked.** A snapshot of the seeded state is captured immediately after build, enabling later "what did the agent change?" diffs.

**How it is checked.**
1. Find a snapshot mechanism — table, file, or in-memory store with a discoverable name (`_state`, `_snapshot`, `baseline_*`).
2. Confirm the snapshot stores **row IDs AND per-row hashes**, not just an aggregate row count / table checksum. (Per-row hashes are what enables `except:` carve-outs at verify time.)

**Levels.**
- `absent` — freeze guards reconstruct expected state from the spec.
- `partial` — aggregate snapshot only.
- `present` — per-row checksums + row IDs stored.

---

### environment_seeding.auto_mutated_field_exclusion

| Field | Value |
|---|---|
| Baseline | `_AUTO_UPDATED_COLUMNS` in `world_builder.py` |

**What is checked.** Denormalized counters, `updated_at` timestamps, and cached fields are excluded from "unchanged" checks so normal agent activity doesn't trip state guards.

**How it is checked.**
1. Grep for excluded-column lists: `AUTO_UPDATED`, `EXCLUDED_COLUMNS`, `skip_columns`, `unchanged_ignore`.
2. Verify exclusion is applied at both snapshot time and verify time.

**Levels.**
- `absent` — no exclusion list; routine agent actions trip guards.
- `partial` — exclusions exist but undocumented or incomplete.
- `present` — explicit per-table list applied consistently.

---

### environment_seeding.external_services_materialized

| Field | Value |
|---|---|
| Baseline | git-server tar materialized at startup |

**What is checked.** Every external dependency the task references (file systems, services, repositories, message queues) is *seeded* at build time, not stubbed at runtime.

**How it is checked.**
1. Confirm the build step populates everything the runtime reads.
2. No surprise mock layers should fill in gaps when the task references a resource.

**Levels.**
- `absent` — runtime mocks fill in gaps.
- `partial` — main store seeded but secondary stores stubbed.
- `present` — every dependency materialized at build.

---

### environment_seeding.agent_permission_seeding

| Field | Value |
|---|---|
| Baseline | Agent auto-added as `write` collaborator on every repo |

**What is checked.** The agent's runtime identity gets the permissions it needs to act on every resource the task may require it to mutate.

**How it is checked.** Grep the builder for permission/collaborator/role grants applied to the agent user during build.

**Levels.**
- `absent` — agent must be granted permission at runtime by the task.
- `partial` — permission granted on some resources only.
- `present` — automatic grant on every resource the agent may mutate.

---

### environment_seeding.closed_entity_universe ⚙ load-bearing

| Field | Value |
|---|---|
| Baseline | `WorldState` with `Repo` / `User` / `Org` / `Issue` / `PR` / `Gist` / `Label` / `Wiki` models |

**What is checked.** The kinds of entities a task can declare in its world are a **closed, typed set**. Adding a new entity kind requires a code change to the schema, not just a YAML edit. This is what makes lint rules tractable — you can enumerate every shape that needs validation.

**How it is checked.**
1. Locate the schema module declaring entity types (Pydantic / dataclass / JSONSchema).
2. Confirm it enumerates a closed set — not `Dict[str, Any]` or extensible-anything.
3. Spot-check: try a task with a fabricated entity-kind key and confirm the build fails clearly.

**Levels.**
- `absent` — world spec is `Dict[str, Any]`; any field accepted.
- `partial` — top-level entity classes are typed but inner fields are dicts.
- `present` — every entity kind has a typed model; unknown kinds fail at build.

---

### environment_seeding.entity_invariants_declared

| Field | Value |
|---|---|
| Baseline | `model_validator` + reward-linter rules like `_check_label_seeding` |

**What is checked.** Each entity type carries invariants (constraints, required fields, cross-field rules) — declared in the schema or enforced by lint rules. A task author can't produce a syntactically valid but semantically incoherent entity.

**How it is checked.**
1. For each entity type, count constraint-bearing fields (`Field(min_length=...)`, `@field_validator`, `@model_validator`).
2. Cross-reference: does the lint corpus include rules that check inter-entity invariants? (e.g., a reward referencing entity X requires X to exist in the world.)

**Levels.**
- `absent` — models are bag-of-fields; no constraints; no inter-entity checks.
- `partial` — some constraints in models OR some cross-entity lint rules.
- `present` — invariants declared in models AND cross-entity lint rules exist.

---

## reward_compilers

The architecture of the reward/check compiler. This is where the "can we enforce invariants" question lives.

### reward_compilers.per_kind_modules

| Field | Value |
|---|---|
| Baseline | `gym_github/reward_compiler/compilers/{issue,pr,wiki,file,state,guards,commit}.py` |

**What is checked.** Compilers split by check family (issues / files / state / guards / etc.), not one monolithic file.

**How it is checked.**
1. List the reward-compiler directory.
2. Confirm ≥5 focused modules; no single file >800 LOC.

**Levels.**
- `absent` — single compiler file, 1500+ LOC.
- `partial` — 2–3 files, some concerns still mixed.
- `present` — 5+ focused modules.

---

### reward_compilers.registry_pattern

| Field | Value |
|---|---|
| Baseline | `@register` decorator in `reward_compiler/registry.py` |

**What is checked.** Check-kind strings dispatch to compiler functions via decorator registration — not a giant if/elif chain in a central `compile()` function.

**How it is checked.** Grep for `@register` / `REGISTRY[` / `dispatch_table`.

**Levels.**
- `absent` — if/elif in central compile().
- `partial` — registry exists but some kinds still hardcoded.
- `present` — all kinds registered; adding a kind = adding a decorated function.

---

### reward_compilers.typed_check_models

| Field | Value |
|---|---|
| Baseline | `gym_github/reward_compiler/models.py` (15+ models) |

**What is checked.** Each check kind has a typed model with field constraints — not free-form `dict[str, Any]`.

**How it is checked.**
1. Grep for `class .*Model` / `@dataclass` / `TypedDict`.
2. Confirm one model per registered check kind.

**Levels.**
- `absent` — free-form dicts.
- `partial` — some kinds modeled.
- `present` — >90% of kinds have a typed model.

---

### reward_compilers.reusable_filter_primitives

| Field | Value |
|---|---|
| Baseline | `gym_github/reward_compiler/helpers.py` |

**What is checked.** Body/content/scope matching primitives are shared across compilers, not reimplemented per check kind.

**How it is checked.**
1. Find shared helpers (`_body_conditions`, `_repo_condition`, `_title_conditions`, etc.).
2. Confirm they're called by 3+ compilers.

**Levels.**
- `absent` — each compiler reimplements its own LIKE/regex/case logic.
- `partial` — helpers exist but inconsistently used.
- `present` — primitives in `helpers.py`, used widely.

---


### reward_compilers.closed_reward_compiler_universe ⚙ load-bearing

| Field | Value |
|---|---|
| Baseline | `@register` dispatch table in reward_compiler |

**What is checked.** The set of reward/check KINDS the framework supports is **closed and enumerable**. New kinds require a code change (new compiler module + registered model), not just a YAML edit. Task authors choose *from* the universe; they don't invent kinds. This is what makes lint rules tractable.

**How it is checked.**
1. List the registry / dispatch table.
2. Confirm it's a fixed Dict/Enum, not loaded from config.
3. Spot-check: try a task with `check: nonsense_kind` and confirm the build fails clearly.

**Levels.**
- `absent` — kinds are strings looked up in dynamic config; anything accepted.
- `partial` — closed set but unclear error for unknown kinds.
- `present` — closed enumerable set; unknown kinds fail with a helpful error.

---

### reward_compilers.invariants_per_check_kind ⚙ load-bearing

| Field | Value |
|---|---|
| Baseline | `models.py` + `task-designer/stages/reward_linter.py` (~30 rules) |

**What is checked.** Every reward kind has invariants declared — via typed model fields, cross-field validators, or paired lint rules — that catch invalid structures at task-definition time. A task author writing a malformed reward instance gets feedback *before* deployment.

**How it is checked.**
1. List every reward kind in the registry.
2. For each, locate its typed model (Pydantic class or equivalent).
3. For each, list lint rules that target that kind.
4. Compute coverage: kinds with model + ≥1 lint rule / total kinds.

**Levels.**
- `absent` — <30% of kinds have model + lint coverage.
- `partial` — 30–70% covered.
- `present` — >70% covered; missing kinds documented as low-risk.

**Note.** This is the load-bearing meta-check. If false, the target gym cannot catch invalid reward structures regardless of how good its other infrastructure is.

---

### reward_compilers.every_kind_smoke_compiled

| Field | Value |
|---|---|
| Baseline | `scripts/world_to_tasks_json.py` over `task_data/worlds/*.yaml` (compiles every kind used across the corpus) |

**What is checked.** Every registered reward kind compiles end-to-end on at least one representative task without raising. Catches drift where a new field/option works in isolation but breaks when the full compile pipeline runs over a real task.

**How it is checked.**
1. Enumerate every kind from the compiler's registry.
2. Find (or synthesize) at least one task per kind that exercises it.
3. Compile each task to its runtime form; expect no exceptions.
4. Fail the check if any registered kind has zero representative tasks.

**Levels.**
- `absent` — no per-kind smoke; broken kinds discovered only when an agent runs into them.
- `partial` — smoke exists but some kinds have no representative task or are skipped.
- `present` — every registered kind has ≥1 representative compile-tested task, run via a documented smoke command.

---

### reward_compilers.compiled_output_executes

| Field | Value |
|---|---|
| Baseline | `task-designer/stages/reward_linter.py` uses SQLite `EXPLAIN` to validate SQL syntax (extending this to schema-level validation would satisfy the check) |

**What is checked.** Compiled rewards produce predicates / SQL / matchers that actually parse and execute against the snapshot DB schema (or equivalent backing store). Catches the bug class where the compiler emits syntactically-malformed SQL or references nonexistent columns — which would otherwise only surface at grading time, per-task.

**How it is checked.**
1. Build a representative world to populate the snapshot store.
2. For each reward in a sample of compiled tasks, `EXPLAIN` (or dry-run) the produced predicate.
3. Fail on any parse error, missing column, or missing table.

**Levels.**
- `absent` — no end-to-end execution check; compiled output errors surface only on a live grade.
- `partial` — smoke executes for a few kinds; columns/tables not verified against the actual schema.
- `present` — every compiled predicate parses + executes against a fresh snapshot store without error.

---

### reward_compilers.compiler_output_determinism

| Field | Value |
|---|---|
| Baseline | Would extend `scripts/audit_reward_compiler.py` with a double-compile diff over a sampled corpus |

**What is checked.** Compiling the same task definition twice produces byte-identical output. Catches the bug class where a refactor introduces non-deterministic ordering (set iteration, dict-key order, randomized UUIDs in compiled output, etc.) that silently changes grading semantics across runs of the same task.

**How it is checked.**
1. Pick a corpus sample of representative tasks.
2. Compile each task twice in fresh processes.
3. Diff the two outputs byte-for-byte; fail on any difference.

**Levels.**
- `absent` — no determinism check; cross-run drift can creep in unnoticed.
- `partial` — smoke covers one or two compilers, not the full set.
- `present` — byte-identical output across compiles for every kind, verified by a repeatable smoke command.

---

## check_composition

How rewards combine to enforce task contracts. The patterns below let task authors express both positive requirements and negative constraints without reward-hacking loopholes.

### check_composition.paired_positive_negative

| Field | Value |
|---|---|
| Baseline | `no_extra_agent_issues` with `accounted_by` |

**What is checked.** Every "agent did X" positive check has a paired "no extra X" guard referencing it — so reward-hacking by spamming actions doesn't pay.

**How it is checked.**
1. Sample 5 tasks.
2. Count `agent_did_*` positives and `no_extra_*` guards.
3. Expect ≥70% pairing ratio on action checks.

**Levels.** absent / partial / present at <30% / 30–70% / >70% pairing.

---

### check_composition.freeze_with_carveouts

| Field | Value |
|---|---|
| Baseline | `pre_existing_rows_unchanged` with `except: {table: [entity_ids]}` |

**What is checked.** Freeze guards can *except* specific entities the agent is legitimately allowed to mutate. Without this, freeze and mutate become incompatible — task authors must choose.

**How it is checked.** Grep for `except:` / `allowlist:` / `carve_out:` on freeze checks; confirm runtime correctly excludes those entities from checksums.

**Levels.** absent / partial / present per "freeze + mutate incompatible" / "carve-out for one resource type only" / "works on any frozen resource".

---

### check_composition.scope_qualifiers

| Field | Value |
|---|---|
| Baseline | `branch:` field on `file_content_replaced` |

**What is checked.** Content checks accept scope qualifiers (branch, ref, snapshot, sub-tree).

**How it is checked.** Grep for `branch:` / `ref:` / `scope:` field on content checks; confirm the field changes the query.

**Levels.** absent / partial / present per "always runs against canonical" / "field accepted but ignored" / "fully honored end-to-end".

---



### check_composition.scoring_mode_switch

| Field | Value |
|---|---|
| Baseline | `BINARY_SCORING` build-arg → `_reward_to_grade` |

**What is checked.** Binary vs fractional grading is a single flag wired build → runtime, not a code fork.

**How it is checked.** Grep one flag across Makefile → build script → Dockerfile → runtime. Confirm the chain is intact.

**Levels.** absent / partial / present per "hardcoded" / "runtime-only" / "single env var end-to-end".

---

### check_composition.mutual_exclusion_between_checks

| Field | Value |
|---|---|
| Baseline | `agent_created_issue` defaults to mutual-exclusion-on; opt out per-check with `mutual_exclusion: false` |

**What is checked.** When two checks could be satisfied by the same agent artifact (e.g., two `agent_created_issue` rewards matching different anchors on the same repo), the framework partitions them — one artifact counts toward one reward, not many. Without this, a clever agent satisfies N rewards with one well-crafted action.

**How it is checked.**
1. Find the field controlling exclusivity (e.g., `mutual_exclusion`).
2. Confirm compiled queries reference sibling checks (NOT IN clause, accounted-by exclusion, or equivalent) so each artifact lands in at most one bucket.
3. Sample a task with multiple same-kind checks on the same scope and verify the artifacts are partitioned, not double-counted.

**Levels.**
- `absent` — no dedup; the same artifact can count for multiple checks (reward-hacking surface).
- `partial` — dedup is opt-in only; the silent default allows double-counting.
- `present` — dedup is the default; explicit per-check opt-out is required to allow overlap.

---

### check_composition.contradictory_rewards_detection

| Field | Value |
|---|---|
| Baseline | `_check_duplicate_reward_names` + `_check_indistinguishable_siblings` (in `task-designer/stages/reward_linter.py`) catch structural duplicates; a semantic negation-pair detector would extend the family |

**What is checked.** Within a single task, no two rewards may be mutually unsatisfiable. A task requiring both "issue X is closed" and "issue X remains open" is unsolvable; every run scores 0 regardless of action. The framework should detect such contradictions at compile time, not at grade time.

**How it is checked.**
1. For each task, group rewards by the entity they target (`_on:` value).
2. Within each group, detect negation pairs: `state=closed` vs `state=open`; `body_contains: X` vs `body_not_contains: X`; `agent_created_*` vs `agent_did_not_create_*`; conflicting status assertions.
3. Fail at compile time on any detected contradiction, citing both reward names.

**Levels.**
- `absent` — no contradiction analysis; an unsolvable task can ship and every run scores 0 without explanation.
- `partial` — some specific contradictions caught (e.g., duplicate names, indistinguishable siblings) but the general negation-pair sweep is missing.
- `present` — compile-time analyzer enumerates entity-scoped reward pairs and flags any negation/state contradiction.

---

### check_composition.writes_to_consistency

| Field | Value |
|---|---|
| Baseline | `_check_nonexistent_guard_tables` + `pre_existing_rows_unchanged.except:` cover parts of this; extending to a per-task writes-vs-frozen reconciliation would close the gap |

**What is checked.** The set of entities / tables the agent is expected to mutate (via positive rewards: `agent_created_*`, `file_content_replaced`, `branch_exists`, `wiki_content_contains`, etc.) must be consistent with what the freeze guards permit. A reward requiring `file_content_replaced` on `repo_x/file.py` while the same task freezes `repo_x` entirely (without an `except:` carve-out) is unsolvable.

**How it is checked.**
1. For each task, extract the set of entities / tables touched by positive rewards (the "writes" set).
2. Extract the set of entities / tables under freeze guards minus their `except:` carve-outs (the "frozen" set).
3. Fail at compile time on any positive-reward target that lies inside the frozen set without a matching carve-out.

**Levels.**
- `absent` — no consistency check; contradictions surface only at grade time.
- `partial` — specific freeze classes validated (e.g., `nonexistent_guard_tables`, `state_unchanged` table existence) but the full writes-vs-frozen reconciliation is missing.
- `present` — compile-time linter cross-validates: every positive-reward target either lies outside the freeze set or has a matching `except:` carve-out.

---

## task_design_discovery

How well the gym's task corpus forces agents to discover constraints, rather than read them off the prompt.

### task_design_discovery.in_world_conventions

| Field | Value |
|---|---|
| Baseline | Rules in `AGENTS.md` / `CONTRIBUTING.md` / wiki / gists / code comments |

**What is checked.** Rules live in seeded artifacts (config files, docs, code comments), not in the prompt itself.

**How it is checked.**
1. Sample 5 hard task prompts.
2. Word-count each (target <150 words).
3. Confirm seeded artifacts carry the rules the agent must follow.

**Levels.** absent / partial / present per "prompt enumerates conventions" / "mixed" / "prompt is vague nudge".

---

### task_design_discovery.distractor_density

| Field | Value |
|---|---|

**What is checked.** Each task has enough distractors that pattern-matching alone fails — similar-named entities, wrong-conclusion threads, mistakenly-filed reports with corrections, decoys that look reopenable but aren't.

**How it is checked.**
1. Sample 5 hard tasks.
2. Grep for entity IDs with `_distractor` / `_wrong` / `_misfile` / `_decoy` / `_legacy` suffixes.
3. Threshold: ≥3 distractors per target on hard tasks.

**Levels.** absent / partial / present.

---

### task_design_discovery.ordering_traps

| Field | Value |
|---|---|

**What is checked.** Some tasks include reverse-order checklists or deliverable-first trackers to penalize naive sequencing.

**How it is checked.** Grep for "ordering trap" / "reverse" / "reverse-dependency" in design commentary; spot-check that seeded data actually contains the trap.

**Levels.** absent / partial / present.

---


### task_design_discovery.scope_declaration

| Field | Value |
|---|---|

**What is checked.** Hard tasks declare in-scope vs out-of-scope entities in structured design commentary.

**How it is checked.** Parse commentary for "in scope" / "out of scope" sections; confirm both lists exist.

**Levels.** absent / partial / present.

---

## self_documentation

How well the task corpus explains itself to readers (future engineers, auditors, agents).

### self_documentation.design_commentary

| Field | Value |
|---|---|
| Baseline | `task_design_commentary:` literal block in every world YAML |

**What is checked.** Every task file has a top-level design rationale section.

**How it is checked.** For every task file, confirm a non-empty `task_design_commentary` (or equivalent) field exists.

**Levels.** absent / partial / present at <20% / 20–80% / >80% coverage.

---

### self_documentation.per_reward_evidence

| Field | Value |
|---|---|
| Baseline | `evidence: [{type, entity, description}, ...]` per reward |

**What is checked.** Each reward has structured pointers to what supports it in the world.

**How it is checked.** Sample 3 tasks; confirm rewards have an `evidence:` / `sources:` array with typed entries (not free-form prose).

**Levels.** absent / partial / present.

---

### self_documentation.inline_calibration_comments

| Field | Value |
|---|---|

**What is checked.** Adjusted anchors carry a comment explaining the change.

**How it is checked.** Grep for `CALIBRATION` / `QA fix` / `Round N` / `softened` / `tightened` in task files.

**Levels.** absent / partial / present.

---

### self_documentation.published_coverage

| Field | Value |
|---|---|
| Baseline | `problems-metadata.json` with `reward_count` + `covered_rewards` per problem |

**What is checked.** Deployment metadata exposes reward count + named reward list per problem.

**How it is checked.** Inspect generated metadata: confirm `reward_count` and `covered_rewards` fields per problem.

**Levels.** absent / partial / present.

---

## calibration_discipline

How the gym manages iterative reward calibration over time.

### calibration_discipline.intent_in_filenames

| Field | Value |
|---|---|

**What is checked.** Calibration variants name their lever (drop / relax / tighten / combo / round-N).

**How it is checked.** List calibrated variants; ratio matching `/(drop|relax|tighten|combo|round|breadcrumb)_/` vs opaque `/_v\d+$/`.

**Levels.** absent / partial / present at <30% / 30–70% / >70% intent-described.

---

### calibration_discipline.baseline_preserved

| Field | Value |
|---|---|

**What is checked.** Original (uncalibrated) task kept alongside variants so you can always see what was changed from.

**How it is checked.** For each calibrated family, confirm a non-suffixed base file exists.

**Levels.** absent / partial / present.

---

### calibration_discipline.target_band_documented

| Field | Value |
|---|---|

**What is checked.** The calibration target (e.g., pass rate band) is written down somewhere queryable.

**How it is checked.** Grep README / docs / rubric for "target band" / "pass rate" / "calibration target".

**Levels.** absent / partial / present.

---

## validation_infrastructure

Static and semi-static validation that runs before tasks reach an agent — including golden solutions.

### validation_infrastructure.validate_target

| Field | Value |
|---|---|
| Baseline | `make validate-tasks` |

**What is checked.** A `make` / `just` / `npm` target schema-validates all task specs without running them.

**How it is checked.** Grep the Makefile for a `validate-*` target; run it on a clean tree; expect exit 0.

**Levels.** absent / partial / present.

---

### validation_infrastructure.filterable_batch

| Field | Value |
|---|---|
| Baseline | `world_to_tasks_json.py --task-ids` |

**What is checked.** Subset compile possible — broken specs don't block validating others.

**How it is checked.** Confirm `--task-ids` / `--filter` / `--ids` flag on the validator.

**Levels.** absent / partial / present at "all-or-nothing" / "exact-match filter" / "substring/glob filter".

---

### validation_infrastructure.unresolved_substitution_logging

| Field | Value |
|---|---|
| Baseline | `[setup_task] Unresolved refs: {...}` log line |

**What is checked.** Partial substitution failures log unresolved refs at setup, info-level.

**How it is checked.** Grep setup code for "unresolved" / "missing.ref"; confirm log statement exists.

**Levels.** absent / partial / present.

---

### validation_infrastructure.entity_references_resolve

| Field | Value |
|---|---|
| Baseline | `_check_label_seeding`, `_check_wiki_reward_seeding`, `_check_nonexistent_guard_tables` in `task-designer/stages/reward_linter.py` cover labels/wikis/tables |

**What is checked.** Every entity ID referenced from a check (`_on:`, `entity:`, fields inside `accounted_by`, `$world${id}` substitutions, etc.) must resolve to an entity declared in the same task's world section. Catches typos, stale references, and drift between rewards and seeded data at build time, not at grading time.

**How it is checked.**
1. For each task, collect the set of declared entity IDs from the world section.
2. Scan the rewards for every entity reference: `_on`, `entity:`, `$world${...}`, `accounted_by` names.
3. Flag every reference that doesn't resolve to a declared entity.

**Levels.**
- `absent` — no cross-validation; dangling refs surface only at grade time (or silently produce empty queries).
- `partial` — validators exist for specific entity types (labels, wikis, tables) but not exhaustive across all reference points.
- `present` — every entity reference is cross-validated at build time; build fails on any unresolved ref.

---

### validation_infrastructure.cross_reference_validation

| Field | Value |
|---|---|
| Baseline | `_auto_populate_accounted_by` |

**What is checked.** Guards that reference positive checks by name fail at compile if the name is wrong.

**How it is checked.**
1. Copy a task.
2. Rename a positive reward but leave the guard pointing at the old name.
3. Expect `ValueError` with location info.

**Levels.** absent / partial / present.

---

### validation_infrastructure.golden_solution_per_task ⚙ load-bearing

| Field | Value |
|---|---|

**What is checked.** Every task has a stored golden solution — a known-good trajectory, action sequence, or final-state snapshot proving the task is *actually solvable* and the reward set fully passes for it. Tasks without a golden are unverified theory.

**How it is checked.**
1. Find golden directory (`golden/`, `solutions/`, `expected/`, `fixtures/golden/`).
2. Compute coverage: tasks with a golden file / total tasks.

**Levels.** absent / partial / present at <30% / 30–90% / >90% coverage.

---

### validation_infrastructure.golden_solution_regression_test

| Field | Value |
|---|---|

**What is checked.** A CI-runnable test verifies all goldens still pass after changes to the world builder, reward compiler, or linter. Catches the bug class where infrastructure changes silently break grading.

**How it is checked.**
1. Find a script/test that replays goldens against the current grader.
2. Run on the current tree; expect every golden to score 1.0.
3. Confirm the script runs in CI as a blocking gate.

**Levels.** absent / partial / present.

---

### validation_infrastructure.golden_solution_format

| Field | Value |
|---|---|

**What is checked.** Goldens are structured and machine-comparable (JSON trajectory, DB-state snapshot, or replayable action log) — not free-form notes.

**How it is checked.** Sample 3 golden files; confirm structured format with discriminator fields; single typed format across the corpus.

**Levels.** absent / partial / present.

---

## linters

Static analyzers catching problematic reward configs *before runtime*. Covers ~28 rule classes plus 5 infrastructure checks.

> All rule checks below assume the gym has a closed reward-compiler universe (see [load-bearing meta-checks](#load-bearing-meta-checks)). If the universe is open, these rules are largely meaningless — the auditor should fail the meta-check first and skip this section.

### Rule checks (~28)

Each rule check follows the same shape — only the principle and the baseline-rule reference differ. The detector for every rule is:

> 1. Locate the linter module (`scripts/lint_tasks.py` / `linter/` / `lint/`).
> 2. Search check functions whose docstring or name matches the principle.
> 3. Inject the example defect into a scratch spec; run the linter; confirm the rule fires.

If no linter exists at all, classify all rule checks as `absent` at the *category* level — don't produce 28 separate findings (the report should aggregate).

| Rule ID |---|---|---|---|
| `unknown_compiler_keys` | high | Typoed field names (`body_contians`) flagged at lint, not silently dropped | `_check_unknown_compiler_keys` |
| `duplicate_reward_names` | high | Reward names unique so `accounted_by` isn't ambiguous | `_check_duplicate_reward_names` |
| `indistinguishable_sibling_rewards` | medium | Two rewards with identical predicates flagged | `_check_indistinguishable_siblings` |
| `weak_body_anchors` | high | Substring anchors below length threshold or matching common words flagged. Example defect: `body_contains: ['refs #']` — 7 chars, matches `prefs #1` | `_check_weak_body_anchors` |
| `name_assertion_polarity` | medium | Positive name with negative assertion (or vice versa) flagged | `_check_name_assertion_polarity` |
| `numeric_match_path` | medium | `NUMERIC_MATCH` operator requires a numeric path | `_check_numeric_match_needs_path` |
| `assertion_key_validity` | medium | Assertion keys match the model | `_check_assertion_keys` |
| `missing_positive_for_guard` | high | Guards without a positive counterpart flagged | `_check_missing_positive_content` |
| `nonexistent_guard_tables` | high | `tables:` list on freeze guards must reference real tables | `_check_nonexistent_guard_tables` |
| `label_seeding` | medium | Labels referenced by rewards must be seeded | `_check_label_seeding` |
| `wiki_reward_seeding` | medium | Wiki/doc artifacts referenced by rewards must exist as seeded | `_check_wiki_reward_seeding` |
| `wiki_slug_mismatch` | medium | Slug used in content checks matches a seeded artifact slug | `_check_wiki_reward_slug_mismatch` |
| `leaked_annotations` | high | Author notes (TODO/REVIEWME/SOLUTION) don't appear in agent-visible seeded text | `_check_leaked_annotations` |
| `surviving_placeholders` | high | Templating placeholders don't survive into agent-visible text | `_check_surviving_placeholders` |
| `answer_hints_in_seeded_text` | high | Seeded text doesn't trivially leak the solution | `_check_answer_hints` |
| `world_template_in_agent_fields` | high | Substitution placeholders (`$world${...}`) don't leak into prompts | `_check_world_template_in_agent_fields` |
| `double_interpolation` | medium | Nested substitution markers flagged | `_check_double_interpolation` |
| `thin_source_files` | low | Implausibly thin seeded source files flagged | `_check_thin_source_files` |
| `leading_slash_paths` | low | Absolute paths flagged where relative was meant | `_check_leading_slash_paths` |
| `url_namespace_consistency` | medium | Resource URL namespace matches platform routing | `_check_url_namespace` |
| `image_urls_format` | medium | Image references use the seeded format | `_check_image_urls` |
| `wiki_image_conflicts` | low | Same image referenced from multiple pages flagged | `_check_wiki_image_conflicts` |
| `slug_special_chars` | low | Slugs don't contain URL-breaking characters | `_check_wiki_slug_special_chars` |
| `link_slugs_resolve` | medium | Markdown links to slugs resolve to seeded artifacts | `_check_wiki_link_slugs` |
| `coverage_manifest_consistency` | medium | `covered_rewards` manifest matches actual reward set | `_check_coverage_manifest` |
| `state_unchanged_completeness` | medium | `state_unchanged` guards cover tables the agent can mutate | `_check_state_unchanged` |
| `timestamp_guard` | low | SQL doesn't compare to fixed timestamps the world doesn't reproduce | `_check_timestamp_guard` |

### Infrastructure checks (5)

#### linters.lint_cli_with_severity

| Field | Value |
|---|---|
| Baseline | `scripts/lint_tasks.py --min-severity high` |

**What is checked.** Lint runs as a single CLI, exits non-zero on findings, supports severity filtering.

**How it is checked.** Find lint script; confirm `--min-severity` flag; confirm non-zero exit semantics on findings.

**Levels.** absent / partial / present.

---


---

#### linters.compiler_ast_audit

| Field | Value |
|---|---|
| Baseline | `scripts/audit_reward_compiler.py` |

**What is checked.** AST-level audit catches silent field-drop bugs in the compiler itself (declared model field never read by the compile function).

**How it is checked.** Find `audit_*compiler*.py` or equivalent; confirm it walks the compiler with `ast` and diffs declared-vs-referenced fields.

**Levels.** absent / partial / present.

---

#### linters.systematic_fixers

| Field | Value |
|---|---|
| Baseline | `scripts/fix_duplicate_reward_names.py`, `fix_audit_findings.py` |

**What is checked.** Common defect classes have batch-fix scripts so manual sweeps are repeatable.

**How it is checked.** Find `fix_*.py` / `repair_*.py` family; confirm ≥3 scripts.

**Levels.** absent / partial / present.

---

#### linters.rule_fixture_testing

| Field | Value |
|---|---|

**What is checked.** Each lint rule has paired bad+ok fixtures and a unit test asserting both.

**How it is checked.** Find `linter/fixtures/` or `tests/` directory; confirm `<rule_id>_bad.yaml` + `<rule_id>_ok.yaml` per rule; confirm pytest asserts both.

**Levels.** absent / partial / present.

---

## deployment_pipeline

How code/spec changes ship to a deployable artifact.

### deployment_pipeline.release_target

| Field | Value |
|---|---|
| Baseline | `make release-world` |

**What is checked.** Single command takes a clean tree → deployed image (metadata gen + build + tag + push, idempotent).

**How it is checked.** Find a release target; confirm it runs all phases; running twice produces identical artifacts (modulo timestamp).

**Levels.** absent / partial / present.

---

### deployment_pipeline.env_threading

| Field | Value |
|---|---|
| Baseline | `BINARY_SCORING` threaded Makefile → build.sh → Dockerfile → runtime |

**What is checked.** Build-time env vars are threaded to runtime config via build args, end-to-end.

**How it is checked.** Pick one build-time flag; trace through Makefile → build script → Dockerfile → runtime config.

**Levels.** absent / partial / present.

---

### deployment_pipeline.reproducible_tags

| Field | Value |
|---|---|
| Baseline | `tga-cu_world_v001_pat:YYYYMMDD-HHMMSS` |

**What is checked.** Image tags encode time or commit; old tags are pullable.

**How it is checked.** Inspect tag generation in the build script.

**Levels.** absent / partial / present at "always 'latest'" / "v1/v2 monotonic" / "timestamp or SHA, all preserved".

---

### deployment_pipeline.last_deployed_tag_persisted

| Field | Value |
|---|---|
| Baseline | `taiga/.problem-image` |

**What is checked.** Build writes the deployed tag to a file; push reads from it.

**How it is checked.** Find `.image-tag` / `.problem-image` / `.last-build`; confirm written by build and read by push.

**Levels.** absent / partial / present.

---

### deployment_pipeline.subset_metadata

| Field | Value |
|---|---|
| Baseline | `taiga/scripts/subset_problems.py` |

**What is checked.** Partial reruns supported via subset metadata generation (not rebuilding the full corpus).

**How it is checked.** Find `subset_*` / `filter_*` / `partial-*` script accepting an ID list.

**Levels.** absent / partial / present.

---

### deployment_pipeline.coverage_in_metadata

| Field | Value |
|---|---|

**What is checked.** Deployment manifest carries per-problem reward count + named reward list for downstream analysis.

**How it is checked.** Inspect generated metadata; confirm both `reward_count` and `covered_rewards` fields per problem.

**Levels.** absent / partial / present.

---

## qa_observability

How well operators can inspect, diagnose, and respond to grading results.

### qa_observability.structured_grading_output

| Field | Value |
|---|---|

**What is checked.** Per-attempt grading output lists failing checks by name — not just a single pass/fail bit.

**How it is checked.** Run one task with a known-failing agent; confirm `passed` / `total` / `failing[]` fields in the output.

**Levels.** absent / partial / present.

---

### qa_observability.trajectory_analyzer

| Field | Value |
|---|---|
| Baseline | `scripts/analyze_trajectory*.py` |

**What is checked.** Tooling exists to inspect/replay an attempt's actions, not just read raw logs.

**How it is checked.** Find `analyze_trajectory*` / `replay_*` / `inspect_run*` scripts.

**Levels.** absent / partial / present.

---

### qa_observability.external_qa_loop

| Field | Value |
|---|---|
| Baseline | `taiga/scripts/taiga_qa_review.py` |

**What is checked.** Bidirectional loop with the grading service — fetch findings AND push decisions back.

**How it is checked.** Find `qa_review` / `qa_feedback` CLI; confirm both fetch and push operations.

**Levels.** absent / partial / present at "out-of-band" / "one-way fetch" / "bidirectional CLI".

---

### qa_observability.calibration_batch_tools

| Field | Value |
|---|---|
| Baseline | `scripts/calibrate_round2.py`, `calibrate_batch.py` |

**What is checked.** Scripts to apply systematic adjustments across N tasks.

**How it is checked.** Find `calibrate_*` / `calib_*` script family.

**Levels.** absent / partial / present.

---

### qa_observability.failure_pattern_aggregation

| Field | Value |
|---|---|

**What is checked.** Failure breakdown across N attempts is queryable — "most-failed reward across last 10 runs" is a one-liner, not custom code.

**How it is checked.** Given a grading-output file, confirm `jq` (or equivalent) can compute the aggregation in one command.

**Levels.** absent / partial / present.

---

## runtime_correctness

Behaviors the gym must get right at grading time, beyond just "specs validate."

### runtime_correctness.snapshot_based_freeze

| Field | Value |
|---|---|
| Baseline | `_world_builder_state` table queried by `pre_existing_rows_unchanged` |

**What is checked.** Unchanged checks compare against a captured snapshot, not a re-derived expected state.

**How it is checked.** Find freeze-check implementation; confirm it reads from the snapshot table, not re-evaluates the spec.

**Levels.** absent / partial / present.

---

### runtime_correctness.per_entity_checksum

| Field | Value |
|---|---|
| Baseline | `row_checksums` column in `_world_builder_state` |

**What is checked.** Per-row hashes enable carve-outs at verification time.

**How it is checked.** Inspect snapshot schema; confirm `row_ids` AND `row_checksums` columns.

**Levels.** absent / partial / present.

---

### runtime_correctness.resilient_substitution

| Field | Value |
|---|---|
| Baseline | `substitute_world_ids` returns `m.group(0)` on miss |

**What is checked.** Unresolved references log a message and leave the token in place; don't crash.

**How it is checked.** Inject an unresolved `$world${nonexistent}` ref into a copy spec; run the build; expect completion with a log line.

**Levels.** absent / partial / present.

---

### runtime_correctness.faithful_app_mock

| Field | Value |
|---|---|

**What is checked.** Seeded state mirrors the live application's behavior for derived / denormalized fields. When the agent acts in the seeded env, the resulting state matches what the real app would have produced.

**How it is checked.** Pick one denormalized field (counter, last-updated, derived); perform the same action in the real app vs. the seeded env; diff the final state.

**Levels.** absent / partial / present.

---

### runtime_correctness.counter_separation

| Field | Value |
|---|---|
| Baseline | `_issue_counters` / `_pr_counters` (independent sequences per repo) |

**What is checked.** Independent number sequences for different entity classes — matching the live app's behavior.

**How it is checked.** Find counter logic; confirm separate state for each class; confirm pin-skip logic for explicitly numbered entities.

**Levels.** absent / partial / present.

---

## Cross-cutting

Three checks that apply across the whole gym, not within a single category. Run after per-category evaluation.

### cross_cutting.round_trip_parity

| Field | Value |
|---|---|

**What is checked.** Sampled tasks compile, seed, grade, and tear down with zero unhandled errors.

**How it is checked.**
1. Sample 10 random tasks.
2. For each, run the full cycle: build → seed → run dummy agent → grade → teardown.
3. Report any task failing any phase.

**Levels.** absent / partial / present per "many failures" / "1–2 failures" / "all pass".

---

### cross_cutting.calibration_vocabulary

| Field | Value |
|---|---|

**What is checked.** Filenames describe levers (drop/relax/tighten/combo/round-N), not opaque versions.

**How it is checked.** List all task variants; classify intent-described vs opaque (`_v2`, `_v3`, ...); threshold >60% intent-described.

**Levels.** absent / partial / present.

---

## Summary tables

### Load-bearing meta-checks (dominate the top-line verdict)

| Check | Why |
|---|---|
| `environment_seeding.closed_entity_universe` | Required precondition for schema invariants |
| `reward_compilers.closed_reward_compiler_universe` | Required precondition for lint coverage |
| `reward_compilers.invariants_per_check_kind` | Determines whether invalid reward structures can be caught at all |
| `validation_infrastructure.golden_solution_per_task` | Determines whether tasks are verified-solvable theory |
