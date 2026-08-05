# S1 Split, Holdout, and Custody Contract

## Current state

```text
CURRENT_S1_SPLIT_POLICY_STATUS=BLOCKED
CURRENT_S1_HOLDOUT_FEASIBILITY_DECISION=NOT_EVALUATED
CURRENT_S1_HOLDOUT_FEASIBILITY_REVIEWED=false
CURRENT_S1_HOLDOUT_FEASIBILITY_CONDITIONAL_BRANCH=NONE_ACTIVE
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
REQUIRED_DATASET_SPLITS=TRAIN,VALIDATION,TEST
EXTERNAL_HOLDOUT_POLICY=CONDITIONAL_ON_S1_FEASIBILITY_GATE
```

The first three are required. `EXTERNAL_HOLDOUT` becomes required only if S1
independently accepts its feasibility. Each future split must have a versioned
manifest, source-cohort identity, row-set identity, and hash. S1 does not
materialize any split.

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

## TEST seal and holdout boundary

TEST and external holdout labels are sealed before candidate tuning. A seal is
not an access authorization. Validation results may not be used to adjust the
TEST split, choose a TEST threshold, or tune a candidate after the TEST seal.
External holdout data is for one final generalization evaluation only and is
never used for tuning, feature selection, or threshold selection.

```text
TEST_SEAL_IS_NOT_TEST_ACCESS_AUTHORIZATION=true
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
EXTERNAL_HOLDOUT_DATA_ACCESS=false
```

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

Neither conditional block is active in this package. The current
`NOT_EVALUATED` decision and `CURRENT_EXTERNAL_HOLDOUT_NOT_APPLICABLE=false`
prevent an unreviewed omission from becoming an exception. The required S1
feasibility gate is not itself an external-holdout materialization gate.

## Leakage and re-use controls

- A failed, cancelled, or retried evaluation does not alter split identity.
- New data or a revised mapping manifest creates a new split manifest and hash.
- A historical snapshot is identified by its source universe, cutoff, mapping,
  winner, and exclusion manifests.
- Any source-time, revision, or mapping drift blocks the split rather than
  silently regenerating it.
- `RANDOM_ADJACENT_DATE_SPLIT_ALLOWED=false`.

## Versioned custody record

Every accepted source cohort and future split reference must bind a versioned
custody record. The record contains policy identities, role identities, and
non-sensitive hashes only.

```text
CUSTODY_RECORD_FIELDS=
custody_policy_version,
storage_type,
access_owner_role,
source_owner_role,
approved_usage_purpose,
least_privilege_scope,
authorized_role_set,
credential_reference_policy,
retention_policy_version,
retention_period_or_rule,
withdrawal_policy_version,
void_propagation_policy_version,
downstream_propagation_targets,
external_object_binding_hash,
custody_record_hash
```

The record must not contain credentials, tokens, private URLs, plaintext
storage locators, or personal identity. `external_object_binding_hash` is a
hash identity, not a locator.

## Withdrawal and void propagation

1. Source withdrawal never silently deletes existing evidence.
2. Withdrawal creates a new versioned custody/status record.
3. Withdrawn or void identities propagate to the source cohort, future split
   manifest, future snapshot manifest, and acceptance record.
4. Every affected unfinished gate becomes `BLOCKED`.
5. Accepted artifacts are immutable and are not rewritten in place.
6. A replacement source creates a new identity and new hashes.
7. Git stores only non-sensitive hashes and policy identities.

## Repository boundary and authorization

The repository may contain schemas, policy documents, and aggregate evidence
identities only. It must not contain business rows, raw exports, source files,
database dumps, credentials, private URLs, or TEST/external-holdout data.

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
S1_ACCEPTANCE_REQUIRES_CUSTODY_LIFECYCLE_RECORD=true
S1_ACCEPTANCE_REQUIRES_WITHDRAWAL_PROPAGATION_RULE=true
S1_ACCEPTANCE_REQUIRES_VOID_PROPAGATION_RULE=true
S1_ACCEPTANCE_REQUIRES_EXTERNAL_HOLDOUT_FEASIBILITY_REVIEW=true
S1_ACCEPTANCE_REQUIRES_NO_RANDOM_ADJACENT_DATE_SPLIT=true
S1_ACCEPTANCE_REQUIRES_NO_TEST_TUNING=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SPLIT_HASHES=true
```

No split is issued, no holdout is accessed, and no custody acceptance is
claimed by this document.
