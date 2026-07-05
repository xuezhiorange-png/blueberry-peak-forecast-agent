# Task 11 Phase 3.1 — Retrospective Replay Implementation Amendment

Refs: #29 (Phase 3 umbrella), #21 (Task 11 umbrella),
PR #30 (`codex/task-11-phase3-retrospective-replay`,
head `7340ec51865645a2c06b2d2e1e54d24cd457c831` as of this merge),
PR #31 / `c0377521` (Phase 3.0 schema prerequisite, MERGED),
PR #32 / `0d748737` (Phase 3.0 governance closeout, MERGED),
`docs/task-11-phase3-design-amendment.md` (archived historical Phase 3
review checkpoint, non-normative).

This document **freezes** the design decisions that downstream Phase 3.1
implementation commits must honor. It deliberately contains **no
implementation code**; it is doc-only. Any conflict between this document
and existing implementation code is resolved **in favor of this document**;
existing code is updated to match on a per-implementation-bucket basis per
§13.

---

## 1. Authorized scope reminder

This phase may implement:

- `retrospective_replay` execution mode semantics.
- Replay source visibility audit writing.
- Replay metadata persistence / fresh-session reload.
- Task 9 replay authority creation through the **existing** Task 9 service
  path (see §3).
- Downstream Task 10 binding to the replay-produced Task 9 authority
  (see §11).
- Stable structured blocker codes for missing / invisible / ambiguous /
  incompatible replay sources (see §7).
- Deterministic unit / golden / PostgreSQL evidence.

This phase must not implement:

- evaluation materialization; metrics; exports; CLI; API; frontend;
  Task 12; Task 13; production scheduling; drift monitoring; alerting;
- new Task 8 natural maturity behaviour;
- new Task 9 harvest-state equations;
- new Task 10 residual model semantics.

This document does **not** introduce new SQL migrations. The only schema
authoritative source is PR #31 / `0015_task11_phase3_schema_gap`
(merged at `c0377521`).

---

## 2. Frozen vocabulary

| Term | Definition |
|---|---|
| `historical_observed` | ExecutionMode value that represents the wall-clock, as-of-date, normal Task 11 rolling backtest run. Replay metadata MUST be NULL on this run. See Phase 2 `RollingBacktestConfig.execution_mode` schema. |
| `retrospective_replay` | ExecutionMode value that represents a leakage-safe, post-cutoff re-execution of the upstream chain. Replay metadata MUST be filled on this run. See PR #31 schema. |
| `is_replay` | The discriminator column on `harvest_state_run` introduced by PR #31. Values: `NULL` / `FALSE` for `historical_observed`; `TRUE` for `retrospective_replay`. |
| `forecast_effective_cutoff_at` | The TIMESTAMPTZ (`forecast_cutoff_at` of the rolling node) at which `retrospective_replay` resolved cutoff-visible sources. Replay only. |
| `replay_executed_at` | The physical UTC moment the replay write-time happened. Replay only. **No server default** (PR #31 P0 fix). |
| `replay_code_version` | Free-text replay runtime identity (git SHA / container image tag / dependency lock fingerprint). Replay only. |
| `replay_run_correlation_id` | Per-replay unique correlation id shared by audit rows of the same replay run. Replay only. |
| `HarvestStateReplaySourceVisibilityAuditModel` | The append-only `harvest_state_replay_source_visibility_audit` table introduced by PR #31. Captures per-cutoff per-source replay visibility decisions. |
| `ReplayDocumentedAuthority` | The replay-produced `HarvestStateRun` whose `is_replay = TRUE` and whose replay metadata is fully populated. Downstream Task 10 MUST bind to this id. |

A row whose `is_replay` does not agree with the config `execution_mode`
at insert time is an integrity violation (PG composite CHECK enforces
the row partition; the application layer must pre-check the
`execution_mode` boundary before calling `execute_harvest_state_run`).

---

## 3. Decision 1 — Reusable Task 9 service entry point

Phase 3.1 calls the **existing** Task 9 service path. The single
canonical entry for replay-time execution is:

```text
backend.app.harvest_state.application.execute_harvest_state_run(
    session: AsyncSession,
    *,
    request: Task9ARequest | Mapping[str, object],
) -> HarvestStateRunEnvelope
```

Implementation rules:

1. Phase 3.1 **must not** call `run_harvest_state_model` directly; it
   must call `execute_harvest_state_run` from the application layer. This
   preserves the canonical-output parity invariant
   (`_canonical_output_json(saved) == _canonical_output_json(loaded)`)
   enforced inside `execute_harvest_state_run`.
2. Phase 3.1 **must not** modify `execute_harvest_state_run`,
   `save_harvest_state_output`, or `run_harvest_state_model` to add
   replay parameters. Replay metadata is added in a separate write step
   **after** `execute_harvest_state_run` returns successfully. (See §4.)
3. The `Task9ARequest` itself is not modified. The Task 9 service path
   does not learn about replay; replay is the *caller's* responsibility.
4. For re-reading the produced row, the canonical reader is
   `backend.app.harvest_state.application.get_harvest_state_run_by_id(
       session, *, run_id: int
   )`. For replay identity hashing, the persistence layer's
   `load_harvest_state_output_by_id` is used in §11.

---

## 4. Decision 2 — Replay metadata write boundary

After `execute_harvest_state_run` returns successfully with a
`HarvestStateRunEnvelope`:

1. The replay writer (a new helper in
   `backend.app.rolling_backtest.replay_metadata.py`, see §4.5 below) opens
   a follow-up transaction in the same `AsyncSession` (no savepoints)
   and UPDATEs the just-persisted `harvest_state_run` row by `id` with:

   ```python
   run.is_replay = True
   run.forecast_effective_cutoff_at = rolling_node.forecast_cutoff_at
   run.replay_executed_at = <utc_now>
   run.replay_code_version = <runtime identity>
   run.replay_run_correlation_id = <per-replay uuid>
   ```

   Field names map 1:1 to PR #31 ORM
   (`HarvestStateRun.is_replay`,
   `…forecast_effective_cutoff_at`,
   `…replay_executed_at`,
   `…replay_code_version`,
   `…replay_run_correlation_id`)
   and to PG columns / CHECK constraint
   `ck_harvest_state_run_replay_metadata_coupling`.

2. The UPDATE is **never** issued on rows whose `is_replay` is already
   `TRUE`. Idempotent replay re-runs produce **new** rows.

3. `replay_code_version` MUST be non-blank. If the runtime cannot
   compute one, the UPDATE is rejected with code
   `REPLAY_RUNTIME_IDENTITY_MISSING` (§7).

4. `replay_run_correlation_id` MUST be unique per replay attempt. The
   writer uses `uuid4().hex` and stamps it onto every audit row of the
   same replay run.

5. The follow-up UPDATE is logged as `replay_metadata_written` with
   the audit row's `semantic_identity_hash` recorded for replay run
   identity. The audit row's `source_role` MUST be
   `task9_harvest_state_run_replay:<run_id>` to allow downstream
   readers to reconstruct the replay.

6. The replay writer is in a new module
   `backend/app/rolling_backtest/replay_metadata.py`. The module is
   *not* imported by Phase 2 callers; only by the dispatch path
   described in §5.

---

## 5. Decision 3 — Replay runner / node orchestration location

The dispatch decision lives in
`backend.app.rolling_backtest.node_orchestration`. Specifically:

1. The hard gate at `node_orchestration.py` line ~2510
   (`if config.execution_mode != ExecutionMode.HISTORICAL_OBSERVED: raise`)
   is **lifted** to accept both values.
2. After `execute_harvest_state_run` (for replay runs only) the
   `replay_metadata.write_replay_metadata(...)` helper is called.
3. Before `execute_harvest_state_run` the replay availability audit
   loop (§6) writes one `harvest_state_replay_source_visibility_audit`
   row per upstream source.
4. Hardcoded `execution_mode=ExecutionMode.HISTORICAL_OBSERVED` at
   `node_orchestration.py` line 289 (in the orchestration context
   default) is replaced with `config.execution_mode` so context
   tracks config.
5. The Phase 2 dispatcher branch invariants
   (`get_execution_mode_for_node` returning
   `ExecutionMode.HISTORICAL_OBSERVED`) are relaxed to
   `config.execution_mode` and any `RETROSPECTIVE_REPLAY`-specific
   stage ordering is delegated to the new
   `backend.app.rolling_backtest.replay_pipeline` module that
   composes around (not replaces) existing Task 8 / Task 9 / Task 10
   steps.

Phase 3.1 does **not** call services outside the existing Task 9
service path. There is no parallel "replay Task 9".

---

## 6. Decision 4 — Source visibility audit

For every upstream source that the rolling resolver selects (each item
in `RollingNodeDefinition.resolved_upstream_semantic_identities`), the
replay writer stamps one row into
`HarvestStateReplaySourceVisibilityAuditModel`:

| Column (PG) | Source of value |
|---|---|
| `id` | autoincrement |
| `harvest_state_run_id` | id of the replay-produced `HarvestStateRun` |
| `source_role` | `<AvailabilitySourceType.value>:<role_qualifier>` (e.g. `task8_daily_prediction:<date>`) |
| `source_type` | `AvailabilitySourceType.value` |
| `source_visibility_source` | one of: `availability_audit`, `task8_visibility_manifest`, `task9_verification_snapshot`, derived from current `RollingNodeDefinition` |
| `forecast_cutoff_at` | copied from `RollingNodeDefinition.forecast_cutoff_at` |
| `visibility_passed` | result of the existing availability check (`True` / `False`) |
| `rejection_blocker_code` | one of `AvailabilityBlockerCode` enum values when `visibility_passed=False`; `NULL` when `True` |
| `semantic_identity_hash` | SHA-256 hex of `node_signature_hash(config, node) || source_role` — this is the deterministic ordering / hash policy for replay audit ordering |
| `captured_at` | `now()` server default — audit clocks are an attempt/runtime metadata (allowed by Phase 2 schema) |

Ordering policy: rows are written in the same order as
`node.resolved_upstream_semantic_identities` (sorted by
`source_role` lexicographically), so a replay produces a deterministic
audit row order across re-runs (modulo FK id allocation, which is the
audit allows).

A replay run that produces zero audit rows is rejected with code
`REPLAY_AUDIT_INCOMPLETE` (§7) — replay MUST produce a one-audit-row
per upstream source.

---

## 7. Decision 5 — Blocker code taxonomy and stability rule

Phase 3.1 introduces a new `StrEnum` and reuses existing ones:

- New: `OrchestrationBlocker.REPLAY_RUNTIME_IDENTITY_MISSING =
  "replay_runtime_identity_missing"`
- New: `OrchestrationBlocker.REPLAY_AUDIT_INCOMPLETE =
  "replay_audit_incomplete"`
- New: `OrchestrationBlocker.MISSING_TASK8_REPLAY_SOURCE =
  "missing_task8_replay_source"`
- New: `OrchestrationBlocker.CUTOFF_INVISIBLE_TASK9_INPUT =
  "cutoff_invisible_task9_input"`
- New: `OrchestrationBlocker.AMBIGUOUS_REPLAY_INPUT =
  "ambiguous_replay_input"`
- New: `OrchestrationBlocker.AUTHORITY_CHAIN_INCOMPATIBLE = "authority_chain_incompatible"`
- New: `OrchestrationBlocker.REPLAY_METADATA_INVALID =
  "replay_metadata_invalid"`
- New: `OrchestrationBlocker.TASK9_REPLAY_FAILED =
  "task9_replay_failed"`
- New: `OrchestrationBlocker.TASK10_REPLAY_BINDING_INVALID =
  "task10_replay_binding_invalid"`

Stability rule:

1. Each value MUST be a stable, machine-readable `lower_snake_case`
   string literal. The value MUST NOT be inferred from log message
   text.
2. Code values MUST NOT be reused across taxonomies.
3. Removing or renaming a blocker value requires a fresh amendment +
   PR review round. Additive values can land in any future round.

`TASK9_REPLAY_INPUT_INCOMPLETE` already exists in
`OrchestrationBlocker` (Phase 2 closeout) and is unchanged;
Phase 3.1 keeps it as the umbrella code for replay input
incompleteness and adds the more-specific taxonomy above.

---

## 8. Decision 6 — Signature separation rule

`backend/app/rolling_backtest/signatures.py` already excludes
`replay_executed_at` from the canonical
`node_signature_payload` and from the
`rolling_backtest_config_payload`. Phase 3.1 reaffirms this contract:

1. **Do not add** `replay_executed_at`, `replay_code_version`,
   `replay_run_correlation_id` to either payload. These are attempt /
   runtime metadata; they MUST NOT influence semantic input signature
   identity.
2. **Do not add** `forecast_effective_cutoff_at` to the semantic
   input signature either. Cutoff is part of the node definition and
   is already in the payload via `node.forecast_cutoff_at`.
3. The semantic input signature is defined per
   `RollingNodeDefinition` and is computed by
   `node_signature_hash(config, node)`. Phase 3.1 does not introduce a
   separate replay node signature; the existing
   `node_signature_hash` is reused by the replay audit
   `semantic_identity_hash` (§6) so callers can match replay audit
   rows to a known node signature without ambiguity.
4. Hard rule: changing `execution_mode` from `historical_observed`
   to `retrospective_replay` for the same `(season_id, node_key,
   as_of_local_date, …)` produces **different node signatures**
   because `execution_mode` is part of the payload. So replay runs
   never accidentally match historical runs in cache or hashing
   layers.

---

## 9. Decision 7 — `no current-data fallback` defences

Phase 3.1 must keep replay strictly bound to the
availability-evaluated upstream chain. Concretely:

1. **Hard prohibition:** the replay writer MUST NOT fall back to
   "latest row in table" / "current data" / "latest id" / "DB now()"
   to satisfy an upstream source. If the availability check returns
   zero rows for `TASK8_FORECAST_RUN` (or any other required source),
   Phase 3.1 records `MISSING_TASK8_REPLAY_SOURCE` and rejects the
   replay attempt with status `blocked`.
2. **No `now()`-as-of fallback:** when looking up Task 9 inputs /
   outputs for replay, the resolver MUST use
   `rolling_node.as_of_local_date` (and the rolling
   `forecast_cutoff_at`), never `datetime.now()` or any
   wall-clock anchor.
3. **Replay catalog:** replay rows in
   `harvest_state_replay_source_visibility_audit` use
   `RollingNodeDefinition.forecast_cutoff_at` (the rolling node's own
   cutoff), not the replay's wall-clock time. This guarantees replay
   audit rows are independent of replay execution time and can be
   replayed / cross-checked by an independent auditor using only the
   rolling node definition.
4. The same `cutoff_visibility_registry` that Phase 2 uses for
   `historical_observed` is the **single source of truth** for replay
   source visibility. There is no second / replay-only
   cutoff_visibility_registry.

---

## 10. Decision 8 — Replay output cannot pose as `historical_observed`

Persistence-layer guarantees:

1. The composite CHECK `ck_harvest_state_run_replay_metadata_coupling`
   (PR #31) makes it physically impossible for a row to claim
   `is_replay = TRUE` while missing any of the four replay metadata
   fields. PG itself rejects the UPDATE. Phase 3.1 reuses this.
2. Reporting layer: the rolling report
   (`backend.app.rolling_backtest.reports`) must partition results
   by `execution_mode` — the report MUST NOT mix `historical_observed`
   and `retrospective_replay` rows under a single label.
3. Public-facing APIs (out of Phase 3.1 scope; this contract asserts
   but does not implement) MUST surface `is_replay` and the four
   replay metadata fields if present, and MUST NOT silently collapse
   replay and historical rows.
4. The Task 9 service path's canonical-output parity invariant
   (`_canonical_output_json(saved) == _canonical_output_json(loaded)`)
   remains in force: replay metadata does not perturb that invariant
   because the columns are normalized / metadata-only and are not
   part of the canonical output envelope.

---

## 11. Decision 9 — Task 10 binding contract

Phase 2 already enforces at `node_orchestration.py` line ~1824:

```python
prediction_result.task9_run_id == ctx.task9_authority.run_reference.reference_value
prediction_result.task9_result_hash == ctx.task9_authority.result_hash
```

Phase 3.1 hardens this for replay:

1. **`task9_run_id` MUST equal the replay-produced `HarvestStateRun.id`**
   (the row whose `is_replay = TRUE`). When
   `config.execution_mode == RETROSPECTIVE_REPLAY`, Phase 2's
   resolver path that picks the latest historical row is **disabled**;
   only the row produced by this replay's `execute_harvest_state_run`
   + subsequent replay-metadata writer (§4) is binding-eligible.
2. **`task9_result_hash`** is loaded from
   `load_harvest_state_output_by_id(session, run_id=…)`, not from any
   earlier historical row.
3. **`task10_training_run` selection:** under
   `Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL`, the existing
   Phase 2 selection rule applies unchanged. Under
   `Task10ModelPolicy.REPLAY_TRAINED_MODEL`, Phase 3.1 only allows
   replay-trained strategies **that Issue #29 already covers**, and
   strictly **does not** introduce new training semantics. If a
   replay-time binding needs a replay-trained Task 10 strategy that
   is not already covered by Issue #29, Phase 3.1 must stop and
   report a schema-gap / spec-gap.
4. **Cross-run substitution** is rejected. Phase 2's resolver may, in
   general, pick an earlier Task 9 run if the latest is unavailable.
   For replay, that fallback is replaced with
   `TASK10_REPLAY_BINDING_INVALID` (§7): the only allowed
   `task9_run_id` is the one produced by the current replay.
5. **Audit trail:** the binding event is recorded as an
   `AvailabilityBlockerCode`-typed entry on the rolling
   `rolling_backtest_stage_event` table — replay's binding decision
   is an attempt/runtime metadata event, not a business semantic
   change.

---

## 12. Decision 10 — Required implementation buckets and order

Phase 3.1 implementation lands in the following order. Each bucket is
its own commit so a review can bisect Phase 3.1 cleanly.

| # | Bucket | Files (new / touched) | Tests added |
|---|---|---|---|
| 1 | `merge main into PR #30` | — (already landed, this commit) | — |
| 2 | Replay blocker taxonomy | `backend/app/rolling_backtest/enums.py` (extend `OrchestrationBlocker`) | unit: enum-value stability |
| 3 | Replay audit writer | new `backend/app/rolling_backtest/replay_audit.py`; new repository function `audit_repository.py` | unit + PG integration: round-trip + FK ON DELETE SET NULL |
| 4 | Replay metadata writer | new `backend/app/rolling_backtest/replay_metadata.py` | unit + PG integration: PG composite CHECK round-trip, server-default regression test, fresh-session reload |
| 5 | Dispatch lift | `backend/app/rolling_backtest/node_orchestration.py` (lift gate at L2510; replace L289 hardcode; add audit loop; add replay-metadata write after Task 9 dispatch) | unit + PG integration: replay pipeline happy path |
| 6 | Task 10 binding hardening | `backend/app/rolling_backtest/node_orchestration.py` (lock replay-produced Task 9 id) | unit: cross-run substitution rejected with `TASK10_REPLAY_BINDING_INVALID` |
| 7 | Replay tests | `backend/tests/test_task11_phase3_replay.py`, `backend/tests/integration/test_task11_phase3_replay_persistence.py` | full test matrix from §13 |
| 8 | Docs / PR body update | `docs/task-11-phase3-retrospective-replay.md` closeout section, PR #30 body | — |

Each commit is bisectable, each is a self-contained pass of the
targeted test, and each excludes unrelated reformatting.

---

## 13. Decision 11 — Hardcoded `HISTORICAL_OBSERVED` sites to be lifted

Specific sites in `backend/app/rolling_backtest/node_orchestration.py`
that must change in Phase 3.1 implementation:

| Line (approx.) | Current value | Phase 3.1 change |
|---|---|---|
| 4 | docstring "Supports execution_mode=historical_observed" | update docstring; both modes supported |
| 289 | `execution_mode=ExecutionMode.HISTORICAL_OBSERVED` (default ctx) | replace with `config.execution_mode` |
| 2510 | `if config.execution_mode != ExecutionMode.HISTORICAL_OBSERVED: raise` | lift gate; accept both modes; branch into replay pipeline if replay |
| 2552 / 2982 | `execution_mode=config.execution_mode` | unchanged — already correct |

All other `HISTORICAL_OBSERVED` references in the file are
*downstream signature / payload / config* references and are
unchanged.

---

## 14. Decision 12 — Test matrix

### Unit / golden

- `test_retrospective_replay_signature_does_not_include_replay_executed_at`
  — sign a node replay run, verify `node_signature_hash` is independent
  of `replay_executed_at`.
- `test_retrospective_replay_signature_includes_execution_mode` — a
  replay node and a historical node with identical `forecast_cutoff_at`
  produce different `node_signature_hash`.
- `test_replay_blocker_codes_are_stable_strings` — `OrchestrationBlocker`
  enum values are exact `lower_snake_case` strings; no surface derived
  from log messages.
- `test_replay_pipeline_dag_is_deterministic` — running the replay
  pipeline twice on the same input produces the same task ordering
  and stage ordering.
- `test_replay_does_not_fall_back_to_latest_row` — when no upstream
  source satisfies availability, replay is `BLOCKED` with
  `MISSING_TASK8_REPLAY_SOURCE`, never `completed-with-warnings`.
- `test_replay_output_cannot_be_reported_as_historical_observed` —
  reporting layer must partition by `execution_mode`; mixing raises.

### PostgreSQL integration (`RUN_POSTGRES_INTEGRATION=1`)

- `test_replay_persists_metadata_and_reloads_fresh_session`.
- `test_historical_observed_row_still_rejects_replay_metadata_leak`
  (carry-over from PR #31 PG test set).
- `test_replay_audit_round_trip_one_row_per_upstream_source`.
- `test_replay_audit_fk_ondelete_set_null` (carry-over from PR #31).
- `test_replay_run_blocks_when_task8_forecast_run_is_not_visible`.
- `test_replay_run_blocks_when_task9_input_observation_date_after_cutoff`.
- `test_replay_run_blocks_on_ambiguous_task8_daily_prediction`.
- `test_replay_produced_task9_run_id_is_unique_per_replay`.
- `test_task10_binding_rejects_historical_task9_substitution` —
  Phase 2 cross-run substitution is disabled for replay.
- `test_replay_execution_time_does_not_change_node_signature_hash`
  — replay twice with different `replay_executed_at`; both runs
  share `node_signature_hash`.

### Regression

- PR #31 / 0015 schema constraints remain valid (carry-over tests).
- historical_observed path behavior unchanged.
- Phase 2 historical_resolution behavior unchanged
  (`RollingBacktestConfig.execution_mode == HISTORICAL_OBSERVED` is
  the default; Phase 2 tests in `backend/tests/rolling_backtest/` must
  all continue to pass).

---

## 15. Decision 13 — Stop conditions (per Charles instruction)

Phase 3.1 implementation MUST stop and report, not continue, if any of
the following occur during bucket 4–7 of §12:

1. A new SQL migration is required beyond `0015_task11_phase3_schema_gap`.
2. Task 8 / Task 9 / Task 10 business semantics need to change (i.e.
   the canonical-output parity invariant is at risk; the
   harvesting-state equations need to change; the residual-model
   semantics need new training logic not covered by Issue #29).
3. Implementation crosses into evaluation / metrics / exports / API /
   frontend / Task 12 / Task 13 / scheduling / alerting / drift
   monitoring.
4. The replay cannot reuse `execute_harvest_state_run` — e.g. the
   canonical-output parity invariant is incompatible with replay
   metadata, or `execute_harvest_state_run` itself fails for replay
   requests in a way that requires a service-layer edit.
5. Task 10 binding needs a replay-trained strategy not covered by
   Issue #29.
6. Merge conflict with `origin/main` cannot be resolved in < 50
   lines.
7. An authority / visibility blocker can only be sidestepped by
   guessing or using current-data fallback.

In any of these cases the implementation commit is *not* made; a
schema-gap / spec-gap report is sent to Charles instead, and the
existing docs and frozen SHA stay untouched.

---

## 16. Frozen Authority SHA (base + content)

This document freezes Phase 3.1 design decisions on top of the
merge-main baseline. Two SHAs together identify the frozen contract:

- **Frozen Authority Base SHA: 7340ec51865645a2c06b2d2e1e54d24cd457c831**
  The merge-main commit on PR #30 branch
  `codex/task-11-phase3-retrospective-replay` that absorbed
  PR #31 (Phase 3.0 schema prerequisite, merge `c0377521`) +
  PR #32 (governance closeout, merge `0d748737`).
  This SHA is the *stable external anchor*: it identifies the schema
  and governance state that all 13 frozen decisions are scoped
  against. The Base SHA does **not** move when only the wording of
  this amendment changes.

- **Frozen Amendment Content SHA: 11545b59eb14414e54efe26dffa3338ba5d6c27c**
  The current commit on PR #30 branch (on top of the Base SHA)
  that contains the actual Phase 3.1 13 frozen decisions (`§3`
  through `§15`), the vocabulary table (`§2`), the Frozen Authority
  section (`§16`), and the provenance section (`§17`), with the
  `Base + Content` SHA pair exposed explicitly.
  This SHA moves whenever the doc wording changes; reviewers
  cross-check this SHA against the PR #30 body. The wording that
  introduced the `Base + Content` split was committed at
  `7fdf5aa63f05525c79c84168905a0669e2374862` (an intermediate
  amend) and finalized at this SHA after the §16 / §17 literals
  were aligned to point at each other; both readings are useful
  for review.

Clarification: The Base SHA is the **authority anchor** for Phase 3.1
implementation (i.e. the schema / governance state any code change must
be consistent with). The Content SHA is the **location** where the
13 frozen decisions are written. A reviewer can:
1. Open the commit at the Content SHA in GitHub and read the 13
   decisions in their final wording.
2. Cross-check the Base SHA to confirm the schema / governance
   state the decisions apply to.

If a future code change rotates the Base SHA (e.g. a follow-up
schema or governance PR merges into `main` and PR #30 re-absorbs
main), both SHAs MUST be rotated in `§16`, in the PR #30 body,
and in Issue #29 body — atomically. Adding a new SHA without
rotating the existing one is a freeze-lifecycle violation.

- Implementation authorization: **NOT GRANTED** as of this
  doc-only commit. Each implementation bucket (§12) requires its
  own review round before any code lands.
- Benchmark cases: **NOT IMPLEMENTED** (the test matrix in §14 is
  pending implementation PR).
- Provenance / governance chain (post-merge state):
  - PR #30 head branch baseline: `ed7c2a7fade0ec2c74413fe830333eabd811996c` (bootstrap note only)
  - PR #30 head after `merge main`: `7340ec51865645a2c06b2d2e1e54d24cd457c831`
  - main HEAD after PR #32: `0d748737251d91c7d4e3487eec62a2025c81ba8a`
  - Issue #21: **OPEN** (Task 11 umbrella)
  - Issue #29: **OPEN** (Phase 3 umbrella)
  - PR #30: **OPEN / Draft**
  - PR #31 / #32: **MERGED**
  - Phase 3.0 schema prerequisite + governance closeout: **DONE**
  - Phase 3.1 implementation: **NOT STARTED** in code by this commit

---

## 17. Provenance / governance chain (this commit)

- This commit: doc-only. No service / runner / repository /
  persistence / availability / resolution / ORM / migration /
  test / CI / frontend / API / exports / metrics file touched.
  The cleanup only rephrases `§16` to expose the
  `Base SHA + Content SHA` pair for freeze-lifecycle clarity.
- Frozen Authority Base SHA (from §16):
  `7340ec51865645a2c06b2d2e1e54d24cd457c831`.
- Frozen Amendment Content SHA (this commit):
  `11545b59eb14414e54efe26dffa3338ba5d6c27c`. The prior
  wording's Content SHA at `8272bec1...` is the SHA of the previous
  wording of this section; both readings are useful for review.
- Author: `root <root@C202606092244457.local>` (autodetected in the
  repo session).
- PR #30 milestone: **frozen design contract** at the Base SHA,
  locatable at the Content SHA. Ready / Merge / codegen are NOT
  authorized at this round.
