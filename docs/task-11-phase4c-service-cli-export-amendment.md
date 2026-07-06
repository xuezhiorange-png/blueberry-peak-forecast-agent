# TASK-011 Phase 4c — Design Amendment: Service Layer, CLI, and Deterministic Export

> **Status:** Design-only DRAFT. **Not** implementation. **Not** migration. **Not** production code.
> **Phase 4c is design-only.** **Implementation is NOT authorized.**
> **Freeze / Ready / merge require separate Charles authorization.**

## 1. Header / status

- **TASK-011 Phase 4c — Design-Only Amendment**
- **Branch**: `docs/task-11-phase4c-service-cli-export-amendment`
- **Implementation NOT authorized** in this PR
- **Branch / PR / merge / Ready / freeze require explicit Charles authorization**
- **References**: Issue #38 (canonical Phase 4c planning issue, OPEN) · Issue #33 (Phase 4 continuity anchor, OPEN) · Issue #21 (TASK-011 umbrella, OPEN) · Issue #36 (Phase 4b planning, CLOSED / COMPLETED) · PR #37 (Phase 4b design amendment, MERGED)

## 2. Background

- **Phase 4a** (PR #35) is complete and archived: design amendment for evaluation materialization and mask foundation, MERGED at `50e9e6c69b45af7f69c969996ff60611f899e608`.
- **Phase 4b** (PR #37) is complete and archived: design amendment for metric formulas and scoped metrics, MERGED at `e236ce63e65962f5535f49ac0ac381ee52f9a071`.
- **Phase 4c** begins only after **Phase 4b merge + post-merge main CI 28773759009 success** (status: completed / success, 2/2 jobs green).
- **Phase 4c consumes Phase 4a and Phase 4b contracts as frozen inputs**, but **does NOT redefine** them.

## 3. Frozen dependencies

Phase 4c must consume (NOT redefine):

- **Phase 4a design doc**: `docs/task-11-phase4a-evaluation-mask-amendment.md` (in origin/main, byte count 17,824, SHA `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`)
- **Phase 4a Frozen Content SHA**: `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`
- **Phase 4a freeze comment**: `4889240526` (on PR #35)
- **Issue #34 closeout comment**: `4889491442`
- **Phase 4b design doc**: `docs/task-11-phase4b-metric-formulas-amendment.md` (in origin/main, byte count 18,000, SHA `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a`)
- **Phase 4b Frozen Content SHA**: `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a`
- **Phase 4b freeze comment**: `4889788635` (on PR #37)
- **PR #37 merge commit**: `e236ce63e65962f5535f49ac0ac381ee52f9a071`
- **PR #37 head SHA**: `6b59092933205ba4b0e37f3539c8eaca2a506246`
- **Post-merge main CI 28773759009**: completed / success (2/2 jobs: compose-smoke success + backend success)
- **origin/main**: `e236ce63e65962f5535f49ac0ac381ee52f9a071` (3-way match with ls-remote)

## 4. Phase 4c objective

Define the **design contract** for:

- **Service layer** — public function surface
- **CLI entrypoint** — command contract
- **Deterministic export** — JSON / CSV / manifest
- **Metric report assembly** — payload composition
- **Audit / provenance payload** — execution metadata
- **Stable output naming** — file / path conventions
- **Reproducible run identity** — run_id semantics
- **Integration boundary with Phase 4a materialization** — read-only
- **Integration boundary with Phase 4b metrics** — read-only

## 5. Required dependency discipline

Phase 4c must **consume, NOT redefine**:

- Phase 4a evaluation materialization
- Phase 4a evaluation row identity (`node_id`, `evaluation_as_of_date`, `forecast_output_id`)
- Phase 4a `evaluation_mask_hash`
- Phase 4a assertion-only row parity (`structural_corrected_row_set_parity`)
- Phase 4a mask provenance (mask state, mask identity, mask audit)
- Phase 4b metric formula definitions (row_count, comparable_row_count, masked_row_count, withheld_row_count, absolute_error, signed_error, squared_error, MAE, MSE, RMSE, bias, weighted variants, coverage, parity)
- Phase 4b scoped metric identity (composite hash of run / node / horizon / farm / variety / model_version / evaluation_mask_hash / metric_family)
- Phase 4b deterministic aggregation rules (ROUND_HALF_EVEN, canonical decimal, stable sort)
- Phase 4b blocker / error model (10 kinds: empty_mask / zero_denominator / missing_target / missing_prediction / non_comparable_row / duplicate_row_identity / mixed_units / invalid_scope / unsupported_aggregation / hash_mismatch)
- Phase 4b frozen Content SHA `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a` (semantic version `4b-1.0.0`)

## 6. Service layer contract

Define:

- **public service function names** — for example `materialize_evaluation(eval_input) -> EvaluationMaterialization`, `compute_metrics(eval_materialization, metric_definition_version) -> MetricReport`, `export_report(metric_report, export_target) -> ExportResult`
- **inputs** — typed (Pydantic models or equivalent)
- **outputs** — typed (Pydantic models or equivalent)
- **required identifiers** — `run_id`, `node_id`, `evaluation_mask_hash`, `metric_definition_version`, `metric_scope_identity`
- **dependency injection boundaries** — service interface, repository interface, exporter interface
- **read-only / transaction expectations** — read-only when consuming Phase 4a materialization
- **deterministic ordering** — stable iteration (sort by `(node_id, evaluation_as_of_date, forecast_output_id)`)
- **blocker return model** — `MetricBlocker` shape: `{kind, metric, scope_id, message, evaluation_mask_hash, metric_definition_version}`
- **provenance attachment rules** — every output includes full provenance payload
- **idempotency expectations** — repeated calls with same inputs return same outputs (byte-for-byte for JSON, line-for-line for CSV)
- **no exception-as-control-flow for expected blockers** — expected blockers returned as part of payload, NOT raised as exceptions

## 7. CLI contract

Define:

- **command name** — for example `blueberry-eval run` (single subcommand for Phase 4c)
- **required arguments** — `--eval-input` (path to evaluation input), `--metric-definition-version` (e.g. `4b-1.0.0`), `--output-path` (export target dir)
- **optional arguments** — `--scopes` (comma-separated scope filter), `--dry-run` (compute but no export), `--overwrite` (default: fail on collision)
- **output path behavior** — directory path; service creates subdirectory with `run_id` name
- **dry-run behavior** — compute + print summary to stdout; do NOT write files
- **exit codes** — `0` (success), `1` (blocker — non-fatal), `2` (error — fatal), `3` (output collision), `4` (invalid arguments)
- **stdout contract** — JSON summary with run_id, scope count, blocker count, export status (only on success or in dry-run)
- **stderr contract** — human-readable warnings for non-fatal blockers; explicit error messages for fatal errors
- **JSON output contract** — canonical ordering, decimal canonical, deterministic bytes
- **repeated-run behavior** — same inputs → same output bytes (idempotency)
- **behavior when output already exists** — by default, fail with exit code 3; with `--overwrite`, overwrite

## 8. Deterministic export contract

Define:

- **export formats** — JSON (canonical), CSV (RFC 4180 with LF line endings), Manifest (JSON)
- **canonical JSON ordering** — alphabetical keys, no whitespace between tokens
- **decimal / string representation** — Decimal canonical string, no scientific notation
- **timestamp representation** — UTC ISO-8601 with `Z` suffix (e.g. `2026-07-06T07:00:22Z`)
- **path determinism** — `${output_path}/${run_id}/${metric_scope_identity_hash}.json` (stable)
- **filename determinism** — `metric_report.json`, `manifest.json`, `metric_report.csv`, `audit.json`
- **manifest fields** — `manifest_schema_version`, `run_id`, `created_at`, `metric_definition_version`, `evaluation_mask_hash`, `content_hashes`, `input_artifacts`, `output_artifacts`
- **content hash fields** — `sha256(content)` for each output file; listed in manifest
- **schema version fields** — `metric_definition_version`, `metric_payload_schema_version`, `manifest_schema_version`
- **compatibility guarantees** — schema versions are monotonic; no breaking changes within `4c-X.Y.Z` series
- **reproducibility checks** — `blueberry-eval verify --run-id <run_id>` compares re-exported content hashes against manifest

## 9. Report manifest contract

Define:

- **manifest schema version** — `4c-1.0.0` (semantic, monotonic, frozen at design time)
- **run identity** — UUIDv5 derived from `(metric_definition_version, evaluation_mask_hash, sorted_input_artifact_paths)` — deterministic
- **node identity** — `node_id` from input (NOT generated)
- **metric definition version** — `4b-1.0.0` (frozen from Phase 4b)
- **evaluation_mask_hash** — from Phase 4a materialization
- **input artifact references** — sorted list of `(path, sha256)` tuples
- **output artifact references** — sorted list of `(path, sha256)` tuples
- **content hashes** — `sha256(metric_report.json)`, `sha256(metric_report.csv)`, `sha256(audit.json)`
- **generated_at semantics** — UTC ISO-8601 with `Z` suffix; fixed at export time, not re-read on verify
- **environment metadata** — `service_version`, `git_sha`, `os`, `python_version`, `timezone=UTC`
- **deterministic ordering fields** — all lists sorted; all dicts in alphabetical key order

## 10. Metric payload contract

Define:

- **metric value payload** — `Decimal` (string) for non-integer metrics, `int` for counts
- **scoped metric identity** — composite hash from Phase 4b
- **row count fields** — `row_count`, `comparable_row_count`, `masked_row_count`, `withheld_row_count`
- **included / excluded row references** — sample of `node_id`, `evaluation_as_of_date`, `forecast_output_id` (deterministic subset, NOT full dump)
- **blocker payload attachment** — `blockers: [MetricBlocker]`
- **provenance payload attachment** — `provenance: {source, evaluation_mask_hash, metric_definition_version, ...}`
- **rounding / decimal representation** — Phase 4b canonical (ROUND_HALF_EVEN, `decimal_scale = max(decimal_places(target), decimal_places(prediction))`)
- **null / missing semantics** — null values explicitly marked as `null` in JSON; not omitted
- **compatibility with Phase 4b metric formulas** — every metric's payload shape matches Phase 4b definition

## 11. Audit / provenance contract

Define:

- **source artifact references** — input files (paths + SHA-256)
- **Phase 4a materialization references** — `evaluation_mask_hash` + `materialization_run_id`
- **Phase 4b frozen metric definition reference** — `metric_definition_version = 4b-1.0.0` + frozen SHA `7ed7cb567c72f107b4a83ed64f0ed66309fdd98049110afa4ec3831598e7c63a`
- **`evaluation_mask_hash`** — from Phase 4a
- **`metric_definition_version`** — `4b-1.0.0`
- **output content hash** — `sha256(output_file)` for each file
- **execution environment metadata** — `service_version`, `git_sha`, `os`, `python_version`, `timezone=UTC`
- **created_at / generated_at semantics** — UTC ISO-8601 with `Z` suffix
- **historical visibility / no-leakage expectations** — export must NOT include evaluation data from outside the requested `scopes` filter

## 12. Error and blocker contract

Define behavior for:

- **missing materialized evaluation input** — `Blocker(kind='missing_evaluation_input', scope_id, message)`; exit code 2
- **missing metric definition** — `Blocker(kind='missing_metric_definition', metric, version)`; exit code 2
- **hash mismatch** — `Blocker(kind='hash_mismatch', expected, actual)`; exit code 2
- **incompatible schema version** — `Blocker(kind='incompatible_schema_version', expected, actual)`; exit code 2
- **empty metric scope** — `Blocker(kind='empty_scope', scope_id)`; exit code 1 (non-fatal)
- **unsupported export format** — exit code 4 (fatal)
- **output path collision** — exit code 3 (with `--overwrite` overwrite; without, fail)
- **duplicate output identity** — `Blocker(kind='duplicate_output_identity', run_id)`; exit code 2
- **partial export failure** — if any file fails, leave partial files with `.partial` suffix; exit code 2
- **invalid CLI arguments** — exit code 4
- **permission / filesystem errors** — exit code 2 with clear error message

## 13. Determinism and reproducibility

Define:

- **stable ordering** — `(node_id, evaluation_as_of_date, forecast_output_id)` for row set; alphabetical for dicts
- **canonical serialization** — JSON with sorted keys, no whitespace, Decimal canonical string
- **canonical decimal representation** — Phase 4b `ROUND_HALF_EVEN`, `decimal_scale = max(...)`
- **timestamp normalization** — UTC ISO-8601 with `Z` suffix; reject local timezone
- **hash input ordering** — alphabetical keys, canonical string values
- **path normalization** — absolute paths, no symlinks
- **deterministic overwrite policy** — with `--overwrite`, file replaced; without, exit 3
- **deterministic failure payload** — `Blocker` shape is deterministic
- **reproducibility verification command or future hook** — `blueberry-eval verify --run-id <run_id>` re-exports + compares content hashes

## 14. Future test contract

Specify future tests only (NOT implement them):

- **service unit tests** — per service function, per input shape, per output shape
- **CLI tests** — per argument combination, per exit code
- **deterministic export golden tests** — per format, per scope
- **hash stability tests** — repeated runs with same inputs produce same hashes
- **blocker / error tests** — per blocker kind, per error kind
- **idempotency tests** — repeated runs produce same output bytes
- **output path collision tests** — with/without `--overwrite`
- **PostgreSQL parity** — if applicable
- **no-leakage / historical visibility tests** — verify export doesn't include data outside scopes
- **no source / test / migration / frontend implementation in this design PR** — explicit

## 15. Out of scope

Explicitly exclude:

- **implementation code** (service, CLI, export)
- **database migrations**
- **frontend work**
- **model training changes**
- **Task 10 `replay_trained_model`**
- **Phase 4a redesign**
- **Phase 4b metric formula redesign**
- **production deployment**
- **closeout PR**
- **Issue #21 closure**
- **Issue #33 closure**
- **Issue #38 closure**
- **branch deletion**

## 16. Governance / stop conditions

State:

- **This PR is design-only.**
- **Implementation is NOT authorized.**
- **Freeze is NOT performed in this round.**
- **Ready is NOT performed in this round.**
- **Merge is NOT authorized.**
- **Phase 4c implementation requires separate Charles authorization.**
- **Any source / test / migration / frontend changes are P0 scope violation.**
- **Any attempt to close Issue #21, #33, or #38 is P0 governance violation.**

**Ready gate (CI green before Ready)**:

- PR #39 must remain Draft until CI is `completed / success` on the exact PR head SHA.
- CI success alone does NOT authorize Ready.
- Ready requires separate Charles authorization after design review and evidence reconciliation.
- No freeze / Ready / merge may happen in the same round as design-doc correction.
- Any new commit to PR #39 invalidates previous candidate SHA and requires recalculating candidate SHA-256 and re-running CI.

### Refs

- Refs #21 — TASK-011 umbrella, OPEN
- Refs #33 — Phase 4 planning, OPEN (continuity anchor)
- Refs #36 — Phase 4b planning, CLOSED / COMPLETED
- Refs #37 — Phase 4b design amendment, MERGED
- Refs #38 — Phase 4c planning, OPEN (canonical planning issue for this PR)

### Hard rules

- Do NOT close Issue #21 / #33 / #38
- Do NOT reopen Issue #36 / #34 / #29
- Do NOT delete PR #37 branch
- Do NOT clean .config / .hermes
- Do NOT start implementation
- Do NOT create migrations
- Do NOT create API endpoints
- Do NOT create CLI code
- Do NOT create frontend code
- Do NOT manually trigger CI
