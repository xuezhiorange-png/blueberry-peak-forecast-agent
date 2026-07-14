# Slice Q2A — Label Snapshot and Revision Contract

> **Issue:** #102
> **Slice:** Q2A — Actual-harvest source, label snapshot, prediction alignment
> **Type:** Docs-only design freeze
> **Authorization:** Issue #102 comment ID `4975150023`
> **Status:** PENDING_REVIEW
> **Companion documents:**
> - `q2a-actual-harvest-source-contract.md`
> - `q2a-prediction-label-alignment-decision.md`
> - `q2a-data-coverage-audit.md`

---

## 1. Scope

This document freezes:

1. the four-time model (forecast cutoff, label observation cutoff, replay timestamp);
2. evaluation modes (AS_OF_EVALUATION and FINAL_ADJUDICATED);
3. the explicit-supersession-terminal revision rule (fail-closed).

These contracts are required regardless of whether a direct actual-harvest source is found, because they govern the label side of any future alignment decision.

## 2. Four-time model (FROZEN, inherited from Q1)

```
forecast_cutoff_at
  < forecast_target_date_or_window_end
    <= label_observation_cutoff_at
      <= replay_executed_at
```

| timestamp | meaning | source |
|---|---|---|
| `forecast_cutoff_at` | latest input timestamp for the forecast run | model run metadata |
| `forecast_target_date_or_window_end` | end of the forecast horizon (date or window) | forecast definition |
| `label_observation_cutoff_at` | latest label observation allowed for an evaluation window | evaluation policy |
| `replay_executed_at` | wall-clock timestamp when the historical replay is invoked | replay execution log |

The strict less-than / less-than-or-equal relationships above are preserved.

### 2.1 Forecast cutoff is sacred

`forecast_cutoff_at` is the historical forecast-input cutoff. It must **not** be polluted by the final-label timestamp. A forecast run that uses a label timestamp as input has been contaminated.

## 3. Evaluation modes (FROZEN, two modes)

### 3.1 AS_OF_EVALUATION

- Only uses records with `recorded_at <= label_observation_cutoff_at`.
- Must resolve by **explicit supersession lineage** (§4).
- Used for in-period, point-in-time evaluation.
- Susceptible to late-arriving records that arrive after `label_observation_cutoff_at` but are excluded.

### 3.2 FINAL_ADJUDICATED

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

## 5. Record state transitions

### 5.1 State diagram

```
        +--------+
        | ACTIVE |
        +---+----+
            |
            | revise
            v
        +-----+-----+
        | CORRECTED |
        +-----+-----+
              |
              | finalize
              v
        +-----+-----+      +------+
        | FINALIZED |  or  | VOID |
        +-----------+      +------+
```

### 5.2 Transitions (FROZEN)

| from | to | trigger |
|---|---|---|
| ACTIVE | CORRECTED | a newer revision supersedes |
| ACTIVE | VOID | business owner voids |
| ACTIVE | FINALIZED | business owner finalizes (no further revisions expected) |
| CORRECTED | FINALIZED | final adjudication reached |
| CORRECTED | VOID | business owner voids |
| FINALIZED | (terminal) | no further transitions |

`FINALIZED` is **terminal**. Once a record is `FINALIZED`, it cannot be revised or voided.

## 6. Mode-binding contract

| mode | reads from | state filter | lineage filter | cutoff |
|---|---|---|---|---|
| `AS_OF_EVALUATION` | source records with `recorded_at <= label_observation_cutoff_at` | `ACTIVE` or `CORRECTED` | explicit supersession chain | `label_observation_cutoff_at` |
| `FINAL_ADJUDICATED` | all source records | `FINALIZED` | explicit supersession chain | none (adjudication complete) |

## 7. Storage of timestamp metadata

The four timestamps in §2 must be:

- present on every forecast run (cutoff, target);
- present on every evaluation (cutoff, observation_cutoff, replay);
- immutable once recorded.

Replay logs must record all four for each evaluation invocation, in UTC.

## 8. Conclusion (FINAL)

- `LABEL_OBSERVATION_CUTOFF_MODEL = CONFIRMED_DESIGN_ONLY`
  - Design frozen in this document.
  - **Cannot be confirmed against production data** because no production actual-harvest source exists (see `q2a-actual-harvest-source-contract.md` §5).
- `LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED`
- `AS_OF_EVALUATION` and `FINAL_ADJUDICATED` modes are defined and binding.
- `forecast_cutoff_at` is preserved as historical forecast-input cutoff.

This contract is **design-only**. No implementation is authorized under this round.

---

## §X. Change log

- **v1.0** (Q2A design round): freeze four-time model, two evaluation modes, and explicit-supersession-terminal revision rule with fail-closed lineage states.

---

## §X.1 Q2A final decision table (cross-document consistency block)

These status values are emitted by this document and must be identical in the companion documents `q2a-actual-harvest-source-contract.md`, `q2a-prediction-label-alignment-decision.md`, and `q2a-data-coverage-audit.md`.

```
DIRECT_ACTUAL_HARVEST_SOURCE_STATUS = DIRECT_ACTUAL_HARVEST_SOURCE_NOT_FOUND
PRIMARY_ACTUAL_HARVEST_LABEL_READY = NO
ACTUAL_LABEL_CANONICAL_GRAIN = FARM_X_SUBFARM_OR_PLOT_X_VARIETY_X_HARVEST_DATE
ACTUAL_LABEL_UNIT = KG
FORECAST_CUTOFF_MODEL = CONFIRMED
LABEL_OBSERVATION_CUTOFF_MODEL = CONFIRMED_DESIGN_ONLY
LABEL_REVISION_POLICY = EXPLICIT_UNIQUE_TERMINAL_FAIL_CLOSED
TASK9_MEMBER_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
AGENT_AGGREGATE_PREDICTION_STATUS = AVAILABLE_MODEL_OUTPUT
ARRIVAL_PROXY_STATUS = NON_PRIMARY_PROXY
ARRIVAL_PROXY_DOES_NOT_SATISFY_PRIMARY_TARGET = YES
PHYSICAL_QUANTITY_ALIGNMENT = NOT_PROVEN
GRAIN_ALIGNMENT = NOT_ALIGNED
ALIGNMENT_DECISION = ALIGNMENT_BLOCKED
REAL_DATA_COVERAGE_STATUS = NOT_VERIFIED_SOURCE_UNAVAILABLE
Q2A_STATUS = PENDING_REVIEW
Q2A_IMPLEMENTATION_READY = NO
Q2B_AUTHORIZED = NO
Q3_AUTHORIZED = NO
MODEL_CHANGE_AUTHORIZED = NO
```