# Slice Q2A — Label Snapshot and Revision Contract

> **Issue:** #102
> **Slice:** Q2A — Actual-harvest source, label snapshot, prediction alignment
> **Type:** Docs-only design freeze (Final fixup round)
> **Authorizations:**
> - Issue #102 comment ID `4975150023` (initial design authorization)
> - Issue #102 comment ID `4975425033` (re-review with P0 fixups)
> **Status:** PENDING_REVIEW
> **Companion documents:**
> - `q2a-actual-harvest-source-contract.md`
> - `q2a-prediction-label-alignment-decision.md`
> - `q2a-data-coverage-audit.md`

---

## 1. Scope

This document freezes:

1. the four-time model (forecast cutoff, label observation cutoff, replay timestamp);
2. evaluation modes (`AS_OF_EVALUATION` and `FINAL_ADJUDICATED`);
3. the explicit-supersession-terminal revision rule (fail-closed);
4. the separation between `record_status` and `lineage winner / effective status` (P1 fix).

These contracts govern the label side of any future alignment decision. They are required regardless of whether a direct actual-harvest source is found.

## 2. Four-time model (FROZEN, inherited from Q1)

```
forecast_cutoff_at
  < forecast_target_date_or_window_end
    <= label_observation_cutoff_at
      <= replay_executed_at
```

| timestamp | meaning | source |
|---|---|---|
| `forecast_cutoff_at` | latest input timestamp for the forecast run | `HarvestStateRun.forecast_effective_cutoff_at` (nullable) |
| `forecast_target_date_or_window_end` | end of the forecast horizon | `HarvestStateRun.forecast_end_date` |
| `label_observation_cutoff_at` | latest label observation allowed for an evaluation window | evaluation policy (DESIGN_CANDIDATE_ONLY) |
| `replay_executed_at` | wall-clock timestamp when the historical replay is invoked | `HarvestStateRun.replay_executed_at` (replay-only, NULL on non-replay runs) |

The strict less-than / less-than-or-equal relationships above are preserved.

### 2.1 Forecast cutoff is sacred

`forecast_cutoff_at` is the historical forecast-input cutoff. It must **not** be polluted by the final-label timestamp. A forecast run that uses a label timestamp as input has been contaminated.

### 2.2 Source schema realization status

`HarvestStateRun` (in `backend/app/models/harvest_state.py`) provides:

- `forecast_season_id` (BIGINT, nullable, FK to `dim_season`)
- `forecast_start_date` (Date)
- `forecast_end_date` (Date)
- `as_of_date` (Date)
- `is_replay` (Boolean, nullable)
- `forecast_effective_cutoff_at` (DateTime timezone-aware, nullable)
- `replay_executed_at` (DateTime timezone-aware, nullable)
- `replay_code_version` (Text, nullable)
- `replay_run_correlation_id` (Text, nullable)

These columns are **production-wired** in `HarvestStateRun`. They are **not yet bound** by an accepted Q2A prediction-label snapshot selection contract — see Doc 3 §3 / §4 (P0-1 / P0-4 corrections).

## 3. Evaluation modes (FROZEN, two modes)

### 3.1 `AS_OF_EVALUATION`

- Only uses records with `recorded_at <= label_observation_cutoff_at`.
- Must resolve by **explicit supersession lineage** (§4).
- Used for in-period, point-in-time evaluation.
- Susceptible to late-arriving records that arrive after `label_observation_cutoff_at` but are excluded.

### 3.2 `FINAL_ADJUDICATED`

- Only uses records that have reached final business adjudication (`FINALIZED`).
- Used for retrospective end-of-season evaluation.
- Records still in `ACTIVE` state are excluded.
- Records marked `VOID` are excluded.

### 3.3 Cutoff binding

- `forecast_cutoff_at` is preserved as the historical forecast-input cutoff in both modes.
- `label_observation_cutoff_at` and `replay_executed_at` are independent and bound by §2.

## 4. Revision winner rule (FROZEN, fail-closed)

### 4.1 The rule

A label evaluation consumes **the unique visible terminal revision on one explicit valid supersession chain within one source family.**

### 4.2 Forbidden fallbacks (no exceptions without explicit Charles authority)

The following fallbacks are **forbidden** for revision selection:

- "latest `recorded_at` wins"
- "largest `revision_number` wins"
- "latest row wins"
- "lexical hash wins"
- "arbitrary source priority"

These fallbacks are forbidden because they mask lineage breaks.

### 4.3 Fail-closed cases

The following lineage states **must** raise an error and halt evaluation:

| failure mode | definition | behavior |
|---|---|---|
| `MULTIPLE_VISIBLE_TERMINAL_REVISIONS` | more than one terminal node visible in chain | fail closed |
| `SUPERSESSION_CHAIN_FORK` | one parent superseded by multiple children | fail closed |
| `SUPERSESSION_CHAIN_CYCLE` | cycle in supersession graph | fail closed |
| `MISSING_SUPERSEDED_PARENT` | child references parent not present | fail closed |
| `CROSS_SOURCE_FAMILY_CONFLICT` | same business-key resolves differently across source families | fail closed |
| `REVISION_NUMBER_DISCONTINUITY` | gap in revision_number sequence | fail closed |
| `INVALID_VOID_LINEAGE` | VOID record referenced as parent by ACTIVE record | fail closed |

### 4.4 When can source priority be used?

Source priority is **only** invoked in `CROSS_SOURCE_FAMILY_CONFLICT` resolution, and only with **explicit Charles authorization** of the priority order. Until Charles issues such authorization, `CROSS_SOURCE_FAMILY_CONFLICT` is fail-closed (§4.3).

## 5. `record_status` vs lineage winner — separation (P1 fix)

This section corrects a semantic ambiguity noted in re-review comment `4975425033`: previously, `CORRECTED` was simultaneously described as "superseded" (non-terminal) and as a state eligible for `AS_OF_EVALUATION` winner selection. These two roles are now separated explicitly.

### 5.1 `record_status` (state of an individual record)

| status | meaning |
|---|---|
| `ACTIVE` | a currently effective non-final terminal revision |
| `FINALIZED` | a terminal revision with final business adjudication (no further revisions allowed) |
| `CORRECTED` | a non-terminal superseded revision (never selected as winner) |
| `VOID` | an explicitly invalid terminal or lineage-ending revision, depending on source contract |

`CORRECTED` is **non-terminal**. A `CORRECTED` row is, by definition, no longer effective — its child carries the effective state.

`FINALIZED` is **terminal**. A `FINALIZED` row cannot be revised or voided.

### 5.2 Lineage winner / effective status (role in evaluation)

The **lineage winner** of a given supersession chain is the unique terminal revision visible in the chain. The effective status of that terminal revision is the relevant binding for evaluation:

| mode | lineage winner condition | effective status filter |
|---|---|---|
| `AS_OF_EVALUATION` | unique visible terminal revision at or before `label_observation_cutoff_at` | `ACTIVE` or `FINALIZED` |
| `FINAL_ADJUDICATED` | unique terminal revision visible under final-adjudication snapshot | `FINALIZED` only |

A `CORRECTED` row is **never** a winner, in either mode. It is a superseded intermediate record, present in the chain for auditability but not eligible for selection.

A `VOID` row is **never** a winner. It is an explicitly invalid terminal or lineage-ending record.

### 5.3 State transitions (FROZEN)

```
        +--------+
        | ACTIVE |
        +---+----+
            |
            | revise
            v
        +-----+-----+
        | CORRECTED |  (non-terminal, never winner)
        +-----+-----+
              |
              | finalize
              v
        +-----+-----+      +------+
        | FINALIZED |  or  | VOID |
        +-----------+      +------+
```

### 5.4 Source schema realization status

The `record_status` column, lineage pointers (`supersedes_record_id`), and revision_number semantics in §5 are **DESIGN_CANDIDATE_ONLY** for the actual-harvest source.

- `NOT_IMPLEMENTED` — no production actual-harvest table exists;
- `NOT_VALIDATED_AGAINST_REAL_SOURCE` — no real source data has been used to validate these semantics.

This label-side contract is frozen as a design; its binding to a real source is the prerequisite for any future validation round.

## 6. Mode-binding contract

| mode | reads from | state filter | lineage filter | cutoff |
|---|---|---|---|---|
| `AS_OF_EVALUATION` | source records with `recorded_at <= label_observation_cutoff_at` | `ACTIVE` or `FINALIZED` | explicit supersession chain | `label_observation_cutoff_at` |
| `FINAL_ADJUDICATED` | all source records | `FINALIZED` | explicit supersession chain | none (adjudication complete) |

## 7. Storage of timestamp metadata

The four timestamps in §2 must be:

- present on every forecast run (cutoff, target);
- present on every evaluation (cutoff, observation_cutoff, replay);
- immutable once recorded.

Replay logs must record all four for each evaluation invocation, in UTC.

`HarvestStateRun` provides the forecast-side carry for `forecast_effective_cutoff_at` / `replay_executed_at`. The label-side timestamp carrier is **DESIGN_CANDIDATE_ONLY** until a real source exists.

## 8. Conclusion (FINAL)

- `LABEL_OBSERVATION_CUTOFF_MODEL = CONFIRMED_DESIGN_ONLY`
  - Design frozen in this document.
  - **Cannot be confirmed against production data** because no production actual-harvest source exists (see `q2a-actual-harvest-source-contract.md` §5).
- `LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED`
- `AS_OF_EVALUATION` and `FINAL_ADJUDICATED` modes are defined and binding.
- `forecast_cutoff_at` is preserved as historical forecast-input cutoff.
- `record_status` and lineage winner are separated; `CORRECTED` is never a winner.

This contract is **design-only**. No implementation is authorized under this round.

---


---




## §X. Change log

- **v1.0** (Q2A design round): freeze four-time model, two evaluation modes, and explicit-supersession-terminal revision rule with fail-closed lineage states.
- **v1.1** (Q2A final fixup round, comment `4975425033`): P1 fix — separate `record_status` from lineage winner / effective status; clarify that `CORRECTED` is non-terminal and never a winner; declare label-side schema status as `DESIGN_CANDIDATE_ONLY / NOT_IMPLEMENTED / NOT_VALIDATED_AGAINST_REAL_SOURCE`.

- **v1.2** (mechanical contract-block repair under Issue #102 comment `4976151116`): fix malformed authorization keys, remove duplicated status-table copy, and preserve all accepted Q2A substantive decisions.

## §X.1 Q2A final decision table (cross-document consistency block)

These status values are emitted by this document and are byte-for-byte identical in the companion documents.

```text
DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND_IN_CURRENT_REPOSITORY
SOURCE_DISCOVERY_SCOPE = CURRENT_REPOSITORY_AND_CHECKED_LOCAL_ARTIFACTS_ONLY
LIVE_DATABASE_SOURCE_DISCOVERY_STATUS = NOT_EXECUTED
EXTERNAL_BUSINESS_SOURCE_DISCOVERY_STATUS = NOT_AUTHORIZED_NOT_EXECUTED
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ACTUAL_LABEL_CANONICAL_GRAIN = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE
ACTUAL_LABEL_UNIT = KG
FORECAST_CUTOFF_MODEL = CONFIRMED
LABEL_OBSERVATION_CUTOFF_MODEL = CONFIRMED_DESIGN_ONLY
LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED
TASK9_MEMBER_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
TASK9_MEMBER_SCHEMA_PATH = backend/app/models/harvest_state.py
PATH_A_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AND_GRAIN_PROOF
AGENT_AGGREGATE_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
AGENT_DAILY_SCHEMA_PATH = backend/app/agent/schemas.py
PATH_B_DIRECT_ROW_GRAIN = RESOLVED_REQUEST_AGGREGATE_X_DATE
PATH_B_QUANTILE_STATUS = P50_P80_P90_AVAILABLE
PATH_B_PREDICTION_SIDE_ELIGIBILITY = STRUCTURALLY_ELIGIBLE_PENDING_LABEL_AGGREGATION_CONTRACT
ARRIVAL_PROXY_STATUS = NON_PRIMARY_PROXY
ARRIVAL_PROXY_SCHEMA_PATH = backend/app/models/analytics.py
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN_MISSING_LABEL
GRAIN_ALIGNMENT = NOT_PROVEN_MISSING_LABEL_AND_MEMBERSHIP_CONTRACT
ALIGNMENT_DECISION = ALIGNMENT_BLOCKED_BY_MISSING_PRIMARY_LABEL
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_SOURCE_UNAVAILABLE
REAL_DATA_COVERAGE_SCOPE = CURRENT_REPOSITORY_ONLY
Q2A_STATUS = PENDING_REVIEW
Q2A_IMPLEMENTATION_READY = NO
Q2B_AUTHORIZED = NO
Q3_AUTHORIZED = NO
MODEL_CHANGE_AUTHORIZED = NO
```
