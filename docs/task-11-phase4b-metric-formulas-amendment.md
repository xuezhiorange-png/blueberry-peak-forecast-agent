# TASK-011 Phase 4b — Design Amendment: Metric Formulas and Scoped Metrics

> **Status:** Design-only. **NOT** implementation. **NOT** migration. **NOT** tests. **NOT** production code.
> **This PR does NOT implement code, modify tests, or create migrations.** Phase 4b depends on Phase 4a as a frozen design input.

---

## 0. Header / Status

- **Phase 4b is design-only.**
- **Implementation is NOT authorized.**
- **This PR does NOT implement code.**
- **This PR does NOT modify tests.**
- **This PR does NOT create migrations.**
- **Phase 4b depends on Phase 4a as a frozen design input.**
- This document is the Phase 4b design contract. It does not implement code, migrations, or tests. It defines metric formulas, scoped metrics, mask-aware semantics, determinism rules, error/blocker model, and the test contract for future implementation.
- Phase 4b planning Issue: #36 (canonical, OPEN).
- Phase 4b planning Issue: #36 must remain OPEN for this PR to proceed.
- PR must remain **Draft** until Charles explicitly authorizes freeze + Ready.

---

## 1. Dependency anchors

Phase 4b consumes these frozen Phase 4a outputs:

- **PR #35 merge commit:** `50e9e6c69b45af7f69c969996ff60611f899e608`
- **Phase 4a Design Amendment Content SHA:** `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`
- **Phase 4a Design Amendment byte count:** 17,824
- **Phase 4a freeze comment (on PR #35):** `#4889240526`
- **Issue #34 canonical closeout comment:** `#4889491442`
- **Issue #33:** Phase 4 planning continuity anchor, OPEN
- **Issue #21:** TASK-011 umbrella, OPEN
- **Phase 4a docs:** `docs/task-11-phase4a-evaluation-mask-amendment.md`
- **Phase 4a Frozen Authority Base SHA:** `7340ec51865645a2c06b2d2e1e54d24cd457c831` (preserved, not rotated)
- **Phase 4a Frozen Amendment Content SHA:** `f2896ae475d4e007fb2e54ad07f294e718d1e171` (preserved, not rotated)

---

## 2. Phase 4b scope (design only)

This design amendment covers:

- metric formulas (exact mathematical definitions)
- scoped metrics (per-node, per-season, per-factory, per-horizon, per-calendar-phase, per-mode)
- metric applicability rules (which metrics apply to which evaluation rows)
- mask-aware metric semantics (how `true_zero` / `excluded` / `blocked` rows affect metric inputs)
- deterministic aggregation rules (ordering, ties, stable sort, canonical decimal)
- metric identity / provenance / audit fields (per-metric output, which inputs / mask hash / config version it consumed)
- edge-case behavior (empty mask, zero denominator, missing target, missing prediction, non-comparable row, withheld row, duplicate row identity, mixed units, invalid scope, unsupported aggregation, hash mismatch)
- test contract for future implementation (unit / golden / integration design, NOT implementation)

---

## 3. Required metric formula design

For each metric, define:

- numerator
- denominator
- row inclusion rule (which evaluation rows feed the metric)
- mask behavior (how `true_zero` / `excluded` / `blocked` rows are treated)
- null / missing behavior (what happens if a required field is missing)
- zero-denominator behavior (return 0, NaN, error, or skip)
- deterministic rounding behavior (Decimal canonical, no float ambiguity)
- output type (float / Decimal / string / struct)
- provenance fields (per-metric audit: which inputs / mask hash / config version it consumed)
- blocker behavior (raises / errors / null when blocker condition met)

### 3.1 Counters

#### `row_count`

- **numerator:** 1 (per evaluation row in scope)
- **denominator:** N/A
- **row inclusion rule:** all evaluation rows in scope (regardless of mask)
- **mask behavior:** all rows counted (mask state recorded but not filtered)
- **null / missing behavior:** row not present → not counted
- **zero-denominator behavior:** N/A
- **deterministic rounding:** N/A (integer)
- **output type:** int
- **provenance fields:** `evaluation_mask_hash`, `run_id`, `node_id`, `scope_dimensions`
- **blocker behavior:** no blockers (always defined)

#### `comparable_row_count`

- **numerator:** 1 (per evaluation row where target AND prediction are both present and non-null)
- **denominator:** N/A
- **row inclusion rule:** target present AND prediction present AND row comparable
- **mask behavior:** `true_zero` rows included; `excluded` / `blocked` rows excluded
- **null / missing behavior:** row missing target or prediction → not counted
- **zero-denominator behavior:** N/A
- **deterministic rounding:** N/A (integer)
- **output type:** int
- **provenance fields:** `evaluation_mask_hash`, `target_presence_count`, `prediction_presence_count`
- **blocker behavior:** no blockers (always defined, can be 0)

#### `masked_row_count`

- **numerator:** 1 (per evaluation row where mask_state ∈ {`excluded`, `blocked`})
- **denominator:** N/A
- **row inclusion rule:** mask state in masked set
- **mask behavior:** counter is defined by mask state
- **null / missing behavior:** row not present → not counted
- **zero-denominator behavior:** N/A
- **deterministic rounding:** N/A
- **output type:** int
- **provenance fields:** `evaluation_mask_hash`, `mask_state_distribution`
- **blocker behavior:** no blockers

#### `withheld_row_count`

- **numerator:** 1 (per evaluation row where mask_state = `withheld` — a future-state we reserve for future schema extensions; Phase 4a does not currently emit `withheld`, but Phase 4b design accommodates it)
- **denominator:** N/A
- **row inclusion rule:** mask state = `withheld`
- **mask behavior:** counter is defined by mask state
- **null / missing behavior:** row not present → not counted
- **zero-denominator behavior:** N/A
- **deterministic rounding:** N/A
- **output type:** int
- **provenance fields:** `evaluation_mask_hash`, `withheld_state_count`
- **blocker behavior:** no blockers

### 3.2 Error metrics

#### `absolute_error`

- **numerator:** `|prediction - target|`
- **denominator:** N/A (per-row scalar)
- **row inclusion rule:** comparable rows (target + prediction both present)
- **mask behavior:** `true_zero` rows included; `excluded` / `blocked` rows excluded; `withheld` rows excluded
- **null / missing behavior:** row not comparable → output omitted from aggregation
- **zero-denominator behavior:** N/A (per-row)
- **deterministic rounding:** Decimal canonical, no float
- **output type:** Decimal
- **provenance fields:** `target`, `prediction`, `mask_state`, `evaluation_mask_hash`
- **blocker behavior:** no blockers (per-row metric)

#### `signed_error`

- **numerator:** `prediction - target`
- **denominator:** N/A
- **row inclusion rule:** same as `absolute_error`
- **mask behavior:** same as `absolute_error`
- **null / missing behavior:** same as `absolute_error`
- **zero-denominator behavior:** N/A
- **deterministic rounding:** Decimal canonical
- **output type:** Decimal
- **provenance fields:** same as `absolute_error`
- **blocker behavior:** no blockers

#### `squared_error`

- **numerator:** `(prediction - target) ** 2`
- **denominator:** N/A
- **row inclusion rule:** same as `absolute_error`
- **mask behavior:** same as `absolute_error`
- **null / missing behavior:** same as `absolute_error`
- **zero-denominator behavior:** N/A
- **deterministic rounding:** Decimal canonical
- **output type:** Decimal
- **provenance fields:** same as `absolute_error`
- **blocker behavior:** no blockers

### 3.3 Aggregate error metrics

#### `mean_absolute_error` (MAE)

- **numerator:** `sum(absolute_error for each comparable row)`
- **denominator:** `comparable_row_count`
- **row inclusion rule:** comparable rows
- **mask behavior:** `true_zero` included; `excluded` / `blocked` / `withheld` excluded
- **null / missing behavior:** rows missing target or prediction → excluded from numerator and denominator
- **zero-denominator behavior:** **blocker** — return error / null; do NOT silently return 0
- **deterministic rounding:** Decimal canonical, scale = `max(decimal_places(target), decimal_places(prediction))`
- **output type:** Decimal (or None if blocker)
- **provenance fields:** `comparable_row_count`, `evaluation_mask_hash`, `decimal_scale`, `metric_definition_version`
- **blocker behavior:** if `comparable_row_count == 0`, return `MetricBlocker(kind='zero_denominator', metric='mean_absolute_error')`

#### `mean_signed_error` (Bias)

- **numerator:** `sum(signed_error for each comparable row)`
- **denominator:** `comparable_row_count`
- **row inclusion rule:** comparable rows
- **mask behavior:** same as MAE
- **null / missing behavior:** same as MAE
- **zero-denominator behavior:** blocker (same as MAE)
- **deterministic rounding:** Decimal canonical
- **output type:** Decimal (or None if blocker)
- **provenance fields:** same as MAE
- **blocker behavior:** same as MAE

#### `root_mean_squared_error` (RMSE)

- **numerator:** `sqrt(sum(squared_error for each comparable row))`
- **denominator:** `comparable_row_count` (under sqrt)
- **row inclusion rule:** comparable rows
- **mask behavior:** same as MAE
- **null / missing behavior:** same as MAE
- **zero-denominator behavior:** blocker
- **deterministic rounding:** Decimal canonical
- **output type:** Decimal (or None if blocker)
- **provenance fields:** same as MAE
- **blocker behavior:** same as MAE

### 3.4 Weighted variants (Phase 4b reserved for future implementation)

- `weighted_mean_absolute_error` (uses row weights from Phase 4a forecast / actual weights)
- `weighted_root_mean_squared_error`
- Definitions deferred to Phase 4b implementation buckets; design reserves the name and binding

### 3.5 Coverage / availability metrics

- `target_coverage_ratio` = `comparable_row_count / row_count`
- `prediction_coverage_ratio` (analogous)
- `masked_ratio` = `masked_row_count / row_count`
- `withheld_ratio` = `withheld_row_count / row_count`

### 3.6 Assertion-only parity metrics

- `structural_corrected_row_set_parity` — assertion-only check that the ordered row set from structural and corrected forecast paths is identical
- Returns boolean (True = identical, False = mismatch)
- **Mismatched row set is a stop condition (MASK-ROWSET-MISMATCH)**

---

## 4. Scoped metrics

Supported dimensions and grouping rules:

- **run** — a single execution of a Phase 3 retrospective_replay or Phase 4a materialization
- **node** — processing line / factory (per Phase 4a row `node_id`)
- **horizon** — forecast horizon bucket (e.g., daily, weekly, monthly)
- **farm / subfarm** — if present in Phase 4a row identity
- **variety** — if present in Phase 4a row identity
- **model version** — Phase 3 model identifier
- **evaluation mask** — mask hash grouping (`evaluation_mask_hash`)
- **metric family** — name of the metric (e.g., `mean_absolute_error`)
- **metric scope identity** — composite hash of `(run, node, horizon, farm, variety, model_version, evaluation_mask_hash, metric_family)` — provides a stable, deterministic identity for a metric output

Grouping rules:

- All metrics are computed per `(metric_scope_identity)` unit.
- Aggregation across scopes is **out of scope** for Phase 4b; it is reserved for Phase 4c service layer.
- Within a scope, the canonical ordered row set is the Phase 4a evaluation row set sorted by `(node_id, evaluation_as_of_date, forecast_output_id)`.
- Scoped metric outputs carry the `metric_scope_identity` hash as a provenance field.

---

## 5. Mask-aware semantics

Phase 4b metrics MUST bind to Phase 4a concepts via the following binding rules:

- **evaluation materialization** — read-only input from Phase 4a materialized evaluation rows
- **evaluation row identity** — `(forecast_output_id, node_id, evaluation_as_of_date)` (from Phase 4a §5.1)
- **evaluation_mask_hash** — read-only input; metric outputs include it as provenance
- **assertion-only row parity** — `structural_corrected_row_set_parity` is a STOP-CONDITION metric, NOT a value-bearing metric
- **mask provenance** — per-metric output includes the mask hash and the mask state distribution
- **comparable / non-comparable rows** — defined by target + prediction presence; non-comparable rows excluded from MAE / RMSE / Bias
- **withheld rows** — future-state; reserved for schema extensions

**Do NOT redefine Phase 4a materialization or masks.** All Phase 4a semantics are frozen.

Mask state → metric input mapping:

| Mask state | comparable_row_count | MAE / RMSE / Bias | counter metrics |
|---|---|---|---|
| (no mask, row present) | yes (if target + prediction) | yes (if comparable) | counted in row_count |
| `true_zero` | yes (if target = 0 AND prediction present) | yes (value is 0) | counted in row_count |
| `excluded` | no | no | counted in masked_row_count + row_count |
| `blocked` | no | no | counted in masked_row_count + row_count |
| `withheld` | no | no | counted in withheld_row_count + row_count |

---

## 6. Determinism and identity

- **stable ordering:** canonical ordered row set sorted by `(node_id, evaluation_as_of_date, forecast_output_id)`
- **canonical decimal / rounding rules:** all Decimal with `ROUND_HALF_EVEN` (banker's rounding); explicit `decimal_scale` per metric
- **hash input ordering:** keys sorted alphabetically before hashing; values rendered as canonical strings
- **metric identity hash fields:** `(run, node, horizon, farm, variety, model_version, evaluation_mask_hash, metric_family, decimal_scale)` — sorted and SHA-256'd
- **audit payload shape:** `{metric_name, metric_value, metric_scope_identity, evaluation_mask_hash, comparable_row_count, blocked_reasons: [...], decimal_scale, metric_definition_version}`
- **reproducibility requirements:** given the same inputs (Phase 4a evaluation rows + Phase 4a evaluation mask + Phase 4b metric definition version), the metric output MUST be byte-identical
- **versioned metric definition identity:** every Phase 4b implementation must include a `metric_definition_version` (semantic version, e.g., `4b-1.0.0`) — frozen at design time; bumps only on new design amendment PR

---

## 7. Error / blocker model

Planned blocker / error semantics for future implementation:

| Condition | Metric | Blocker kind | Return value |
|---|---|---|---|
| empty mask | any aggregate | `empty_mask` | None + blocker |
| zero denominator | MAE / RMSE / Bias | `zero_denominator` | None + blocker |
| missing target | `comparable_row_count` (decrements) | `missing_target` | (row excluded, no metric blocker) |
| missing prediction | `comparable_row_count` (decrements) | `missing_prediction` | (row excluded, no metric blocker) |
| non-comparable row | any aggregate | `non_comparable_row` | (row excluded, recorded in audit) |
| duplicate row identity | any aggregate | `duplicate_row_identity` | None + blocker (one of the duplicates is excluded deterministically) |
| mixed units or incompatible units | any aggregate | `mixed_units` | None + blocker |
| invalid metric scope | any aggregate | `invalid_scope` | None + blocker |
| unsupported aggregation | any aggregate | `unsupported_aggregation` | None + blocker |
| hash mismatch | `metric_identity_hash` | `hash_mismatch` | None + blocker |

`MetricBlocker` shape: `{kind: str, metric: str, scope_id: str, message: str, evaluation_mask_hash: str, metric_definition_version: str}`

All blockers are returned as part of the metric output payload (not raised exceptions), so callers can inspect and decide.

---

## 8. Test contract (design only, not implementation)

Future tests must cover:

- **unit test vectors** — per metric, deterministic input → deterministic output
- **golden metric vectors** — fixed input + fixed mask → fixed metric output (regression against known fixture)
- **mask edge-case vectors** — `true_zero` / `excluded` / `blocked` / `withheld` mix; verify mask_state → metric mapping
- **deterministic ordering tests** — verify ordered row set hash stability across runs
- **hash stability tests** — verify `metric_identity_hash` and `metric_audit_hash` stability
- **PostgreSQL parity expectations** — SQL aggregation MUST match Python aggregation byte-for-byte
- **no-leakage / historical visibility** — verify metric outputs reference only the evaluation rows in scope (no leakage from other runs or scopes)

---

## 9. Out of scope

Explicitly excluded from this design and from any later Phase 4b implementation:

- Phase 4a implementation (already complete; do not touch)
- Phase 4c service layer
- Phase 4c CLI
- Phase 4c deterministic JSON / CSV export
- Task 10 `replay_trained_model`
- model training changes
- database migrations
- API endpoint implementation
- frontend work
- any implementation code
- closeout PR

---

## 10. Stop conditions

Work must halt and return to planning if any of the following are detected:

- implementation code is introduced
- source / test / migration files are modified
- Phase 4a frozen semantics are changed
- Phase 4c service / CLI / export scope is entered
- Task 10 `replay_trained_model` is touched
- Issue #36 is closed
- PR is marked Ready before Charles authorizes freeze + Ready

---

## Refs

- **Issue #21** — TASK-011 umbrella, OPEN
- **Issue #29** — Phase 3.1, CLOSED / COMPLETED
- **Issue #33** — Phase 4 planning, OPEN
- **Issue #34** — Phase 4a design planning, CLOSED / COMPLETED
- **Issue #36** — Phase 4b planning, OPEN
- **PR #30** — Phase 3.1 implementation, MERGED
- **PR #35** — Phase 4a design amendment, MERGED
- **Freeze comment 4889240526** on PR #35
- **Issue #34 closeout comment 4889491442**
- **Phase 4a Design Amendment Content SHA:** `632e2e1f2880c9a6d7b87ee9f90565223ece69aaee43bea620f526c1fe1c8f3c`
- **Phase 4a docs:** `docs/task-11-phase4a-evaluation-mask-amendment.md`
- **Phase 4a Frozen Authority Base SHA:** `7340ec51865645a2c06b2d2e1e54d24cd457c831` (preserved, not rotated)
- **Phase 4a Frozen Amendment Content SHA:** `f2896ae475d4e007fb2e54ad07f294e718d1e171` (preserved, not rotated)
- **Task 10 `replay_trained_model`:** explicitly deferred to a later independent design decision
