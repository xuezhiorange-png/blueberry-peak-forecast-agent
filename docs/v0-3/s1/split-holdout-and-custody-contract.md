# S1 Split, Holdout, and Custody Contract

## Current state

```text
CURRENT_S1_SPLIT_POLICY_STATUS=BLOCKED
CURRENT_S1_HOLDOUT_FEASIBILITY_DECISION=NOT_EVALUATED
PROPOSED_S1_HOLDOUT_FEASIBILITY_DECISION=BLOCKED
CURRENT_EXTERNAL_HOLDOUT_GATE_STATUS=BLOCKED
CURRENT_EXTERNAL_HOLDOUT_GATE_BLOCK_REASON=FEASIBILITY_NOT_YET_ACCEPTED
CURRENT_EXTERNAL_HOLDOUT_NOT_APPLICABLE=false
CURRENT_CROSS_FARM_GENERALIZATION_CLAIM_ALLOWED=false
```

The proposed feasibility status is blocked because no accepted source cohort,
coverage summary, or independent review is available. The current decision is
still `NOT_EVALUATED`; the conditional examples below are not active decisions.

## Required split sets

S1 freezes the identities and rules for four logical partitions:

```text
TRAIN
VALIDATION
TEST
EXTERNAL_HOLDOUT
```

The first three are required. `EXTERNAL_HOLDOUT` is required only if S1
independently accepts its feasibility. Each split must have a versioned
manifest, source-cohort identity, row-set identity, and hash.

Splits must use complete time intervals or complete seasons. Randomly splitting
adjacent dates is prohibited as the primary evaluation method. A split must
not expose future labels or future source revisions to an earlier historical
cutoff.

## Candidate split policy

The accepted policy must record, without row data:

- ordered season and farm/date interval membership;
- whether a farm or season is isolated from validation and test;
- label observation cutoff and forecast cutoff policy;
- source and mapping manifest hashes;
- exclusion policy and missing-day semantics;
- all requested forecast horizons;
- whether the split is for model selection, final test, or external
  generalization only.

No split is valid if its manifest omits source lineage, time visibility, or
revision winner evidence.

## External holdout feasibility

The external holdout decision requires evidence of a distinct source cohort or
farm/season boundary that is not used to tune candidates. It also requires
adequate coverage at the canonical grain and an independent custody record.

```text
WHEN_EXTERNAL_HOLDOUT_FEASIBILITY_ACCEPTED:
  EXTERNAL_HOLDOUT_REQUIRED=true
  EXTERNAL_HOLDOUT_USAGE=FINAL_GENERALIZATION_ONLY
  EXTERNAL_HOLDOUT_TUNING_ALLOWED=false
```

```text
WHEN_EXTERNAL_HOLDOUT_FEASIBILITY_REJECTED_WITH_REVIEW:
  EXTERNAL_HOLDOUT_REQUIRED=false
  EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
  EXTERNAL_HOLDOUT_REJECTION_REASON=REVIEWED_AND_RECORDED
```

Neither conditional block is active in this package. `CURRENT_EXTERNAL_HOLDOUT_NOT_APPLICABLE=false`
prevents an unreviewed omission from becoming an exception.

## Leakage and re-use controls

- TEST and external holdout labels are sealed before candidate tuning.
- Validation results may not be used to adjust the test split.
- A failed, cancelled, or retried evaluation does not alter split identity.
- New data or a revised mapping manifest creates a new split manifest and hash.
- A historical snapshot is identified by its source universe, cutoff, mapping,
  winner, and exclusion manifests.
- Any source-time, revision, or mapping drift blocks the split rather than
  silently regenerating it.

## Custody and repository boundary

The repository may contain schemas, policy documents, and aggregate evidence
identities only. It must not contain business rows, raw exports, source files,
database dumps, credentials, private URLs, or test/external-holdout data.

```text
REAL_DATA_IMPORT_AUTHORIZED=false
REAL_DATA_READ=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_DATA_ACCESS=false
REAL_DATA_COMMITTED_TO_GIT=false
RAW_SOURCE_IMMUTABLE=true
CLEANED_DATA_VERSIONED=true
SOURCE_ROW_LINEAGE_REQUIRED=true
```

## Acceptance requirements

```text
S1_ACCEPTANCE_REQUIRES_TIME_ORDERED_SPLIT_MANIFESTS=true
S1_ACCEPTANCE_REQUIRES_TEST_CUSTODY=true
S1_ACCEPTANCE_REQUIRES_EXTERNAL_HOLDOUT_FEASIBILITY_REVIEW=true
S1_ACCEPTANCE_REQUIRES_NO_RANDOM_ADJACENT_DATE_SPLIT=true
S1_ACCEPTANCE_REQUIRES_NO_TEST_TUNING=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SPLIT_HASHES=true
```

No split is issued, and no holdout is accessed, by this document.
