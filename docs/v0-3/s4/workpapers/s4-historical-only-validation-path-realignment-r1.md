# Workpaper — V0.3 S4 historical-only validation path realignment R1

```text
TASK_ID=V0_3_S4_HISTORICAL_ONLY_VALIDATION_PATH_REALIGNMENT_R1
BASE_MAIN_SHA=606ef99c10ae66e1a1e0a222ea51953dea528298
PR595_MERGE_IN_BASE=true
TASK_CLASS=GOVERNANCE_AND_EXECUTION_PATH_CORRECTION
```

## Finding and correction

The previous live pointer treated the absence of a real prospective production
forecast authority as a prerequisite for current S4 validation. That conflated
an online pilot authority path with the already accepted offline historical
evaluation authority. The correction restores the product boundary:

```text
TRAIN -> finite candidate fitting/calibration -> VALIDATION scoring
      -> candidate selection -> separately authorized locked TEST
```

The current accepted authority is SOURCE-002 historical TRAIN/VALIDATION. The
prospective retention path remains a reusable future online-pilot capability,
not a condition for current S4.

## Leakage-safe horizon interpretation

Horizon values 7, 14, and 21 are target offsets from a deterministically
governed historical evaluation cutoff. They are not a request to wait for
future wall-clock outcomes. The validator must construct features only from
information visible at that historical cutoff and compare predictions with
held-out VALIDATION outcomes. No retained historical production forecast,
Task8/Task9 forecast, weather authority, or production-plan authority is
required merely to define this offline boundary.

## Candidate audit method

Each registered candidate was checked against the current input policy rather
than accepted by family name. The audit asks whether its required parameter or
feature domain is demonstrably derivable from the frozen SOURCE-002
TRAIN/VALIDATION and model-training path.

* 01, 02, 03, 04, 05, and 07 are compatible at the input-policy level. They
  still need finite V2-bound manifests, exact parameter/feature identities, and
  separate execution authorization.
* 06 is not compatible because its registered hypothesis explicitly requires
  weather-response features. It is deferred to a future product version.
* 08 is not currently proven compatible. The registered “residual features”
  have no V2-bound source-002-only manifest, and the existing residual feature
  registry includes TASK9 and WEATHER domains. It remains fail-closed until a
  future manifest proves a historical-only feature set.

This does not delete or rewrite the V1 registry. The eight IDs, order, family,
hypothesis, and four-run registration remain preserved in V2; V2 adds current
historical-only execution eligibility as a governance overlay.

## C03 disposition

The existing C03 manifest is explicitly tied to the old V1 execution plan and
is not executable under this correction. If C03 remains selected for a future
historical-only lane, a new V2-bound manifest must bind the same owner-selected
parameter semantics to the V2 plan hash. That future task must separately
authorize execution and must not use this correction as authorization.

## Preserved budget and boundaries

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
C01_RERUN_PERFORMED=false
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
TEST_ACCESS_REQUESTED=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
S1_SPLIT_MANIFEST_MUTATED=false
S4_PROSPECTIVE_SCAN_PERFORMED=false
S5_IMPLEMENTATION_STARTED=false
S6_IMPLEMENTATION_STARTED=false
```

PR #591–#595 remain historical audit evidence. No prior evidence is edited or
deleted. No prospective recovery, pilot-runtime discovery, database change,
seed, backfill, candidate run, validation scoring, or TEST access occurred.

## Verification record

```text
JSON_VALIDATION=REQUIRED
RELEVANT_CONTRACT_TESTS=NOT_RUN_BY_DOCS_ONLY_CHANGE
PRODUCTION_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CHANGED=false
MODEL_CHANGED=false
PARAMETERS_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_HISTORICAL_ONLY_REALIGNMENT_REVIEW
```
