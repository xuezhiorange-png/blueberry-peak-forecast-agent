# V0.3-S3 Farm-total Baseline Estimator Owner Decision Binding (R1)

> Scope: owner decision binding and attestation only — no estimator implementation or execution
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_OWNER_DECISION_BINDING_R1`
> Parent merge: `7da22ce5a529a5637f0b5543ec22b03ae79137da` (PR #561)
> Decision request: `docs/v0-3/s3/s3-farm-total-baseline-estimator-owner-decision-request.md`
> Parent contract: `docs/v0-3/s3/s3-farm-total-baseline-estimator-contract.md`

## Machine-readable header

```text
DECISION_ID=V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTICS
DECISION=ACCEPT
DECIDED_ON=2026-09-06
DECIDED_AT=null

OWNER_DECISION_ISSUED=true
OWNER_DECISION_FINAL=true
OWNER_DECISION_STATUS=ACCEPTED
OWNER_DECISION_COMPLETE=true

OWNER_IDENTITY=xuezhiorange-png
OWNER_ROLE=model_validation_owner_role
OWNER_ROLE_ATTESTATION=I_AM_ACTING_AS_MODEL_VALIDATION_OWNER_ROLE
OWNER_PROVENANCE=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-09-06
OWNER_APPROVAL_TEXT=按推荐方案

OWNER_ATTESTATION_STATUS=ACCEPTED
OWNER_ATTESTATION_EVENT=AUTHENTICATED_REPOSITORY_OWNER_EXPLICIT_INTERACTIVE_APPROVAL_2026-09-06
OWNER_ATTESTATION_SCOPE=EXACT_RECOMMENDED_CONFIGURATION_ENUMERATED_IN_THIS_BINDING

IMPLEMENTATION_AUTHORIZED=false
ESTIMATOR_IMPLEMENTATION_GATE_OPEN=false
ESTIMATOR_IMPLEMENTATION_STATUS=BLOCKED_SEPARATE_IMPLEMENTATION_AUTHORIZATION

TEST_ACCESS=false
TEST_USE=SEALED
V0_3_S4_AUTHORIZED=false
MODEL_CHANGE=false
PARAMETER_CHANGE=false

NO_STEP_IMPLIES_THE_NEXT=true
```

## 1. Binding identity

| Attribute | Value |
| --- | --- |
| Decision ID | `V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTICS` |
| Decision | `ACCEPT` |
| Decided on | `2026-09-06` (no fabricated clock time; `DECIDED_AT=null`) |
| Source request | `docs/v0-3/s3/s3-farm-total-baseline-estimator-owner-decision-request.md` |
| Source request evidence | `docs/v0-3/s3/evidence/s3-farm-total-baseline-estimator-owner-decision-request.json` |
| Binding evidence | `docs/v0-3/s3/evidence/s3-farm-total-baseline-estimator-owner-decision-binding.json` |
| Parent merge SHA | `7da22ce5a529a5637f0b5543ec22b03ae79137da` |

The authenticated repository owner explicitly approved the complete recommended
configuration on 2026-09-06 with:

```text
OWNER_APPROVAL_TEXT=按推荐方案
```

The coordinator had immediately before enumerated the complete recommended
configuration. This binding normalizes that approval **only** to the accepted
values below. No broader approval is inferred.

## 2. Accepted owner values (13 fields resolved)

| FIELD | ACCEPTED_VALUE |
| --- | --- |
| `BASELINE_ESTIMATOR_FAMILY` | `GROUP_SPECIFIC_HISTORICAL_STATISTIC` |
| `TIME_AXIS` | `HARVEST_BUSINESS_DATE` |
| `AREA_NORMALIZATION_POLICY` | `NO_AREA_NORMALIZATION` |
| `POOLING_GRAIN` | `BASELINE_FARM_GROUP_SPECIFIC` |
| `TRAIN_AGGREGATION_STATISTIC` | `MEDIAN` |
| `MIN_TRAIN_SUPPORT` | `5` |
| `UNSEEN_GROUP_POLICY` | `FAIL_CLOSED` |
| `MISSING_DAY_POLICY` | `SKIP_OUTPUT` |
| `COLD_START_POLICY` | `FAIL_CLOSED` |
| `VALIDATION_USE_POLICY` | `EVALUATION_ONLY` |
| `OUTPUT_SEMANTICS` | `DAILY_HARVEST_KG_PER_BASELINE_FARM_GROUP` |
| `OWNER_IDENTITY` | `xuezhiorange-png` |
| `OWNER_ATTESTATION` | `OWNER_ATTESTATION_STATUS=ACCEPTED`; event and scope per header |

```text
OWNER_DECISION_FIELD_COUNT=13
UNRESOLVED_OWNER_DECISION_FIELD_COUNT=0
```

Deterministic normalization of `MIN_TRAIN_SUPPORT` (not a 14th owner-decision
field):

```text
MIN_TRAIN_SUPPORT=5
MIN_TRAIN_SUPPORT_UNIT=DISTINCT_VALID_TRAIN_HARVEST_DAYS_PER_BASELINE_FARM_GROUP
MIN_TRAIN_SUPPORT_UNIT_CLASS=DERIVED_SEMANTIC_NORMALIZATION
MIN_TRAIN_SUPPORT_UNIT_DERIVED_FROM=MIN_TRAIN_SUPPORT
DERIVED_SEMANTIC_NORMALIZATION=true
```

`MIN_TRAIN_SUPPORT_UNIT` is not an additional owner-decision field and does not
increase `OWNER_DECISION_FIELD_COUNT` above 13.

## 3. Estimator semantic normalization (owner-frozen)

For each `baseline_farm_group_key` independently:

1. Use TRAIN partition rows only.
2. Do not pool rows across `baseline_farm_group_key` values.
3. Do not use `area_mu` in the mathematical estimator.
4. Count support as the number of distinct `harvest_business_date` rows for that
   `baseline_farm_group_key` that are already valid rows emitted by the governed
   Farm-total TRAIN data plane.
5. Do **not** introduce a new definition of “valid row”. Existing Farm-total
   data-plane validation is authoritative.
6. Require at least **5** distinct valid TRAIN `harvest_business_date` rows for
   the `baseline_farm_group_key`.
7. If support &lt; 5: `FAIL_CLOSED` — do not emit a fallback estimate.
8. If support ≥ 5: compute the standard statistical **median** of
   `actual_harvest_quantity_kg` across all governed TRAIN rows for that
   `baseline_farm_group_key`.
9. Standard median semantics: odd count → middle ordered value; even count →
   arithmetic mean of the two middle ordered values. This is deterministic
   normalization of `MEDIAN`, not authorization of a new estimator family.
10. The resulting group-level TRAIN median is the point baseline value applied
    to eligible output dates for that `baseline_farm_group_key`.
11. Output is keyed by `baseline_farm_group_key` × `harvest_business_date`.
12. Output unit is **kg**.
13. Do not synthesize an output row for an absent governed output date
    (`MISSING_DAY_POLICY=SKIP_OUTPUT`).

### 3.1 Explicit prohibitions (frozen by this decision)

Do not use:

- area normalization;
- cross-group pooling;
- global fallback;
- interpolation;
- nearest-date substitution;
- analog-date substitution;
- persistence;
- VALIDATION fitting;
- VALIDATION family selection;
- VALIDATION parameter tuning;
- TEST access.

## 4. Validation authority layering

### 4.1 General split authority (unchanged)

```text
GENERAL_SPLIT_AUTHORITY=true
GENERAL_VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY
```

Source: `docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md`

This binding does **not** rewrite general S1 split authority.

### 4.2 Farm-total baseline-specific owner decision

```text
FARM_TOTAL_BASELINE_SPECIFIC_OWNER_DECISION=true
VALIDATION_USE_POLICY=EVALUATION_ONLY
VALIDATION_USES_FOR_FITTING=false
VALIDATION_USES_FOR_FAMILY_SELECTION=false
VALIDATION_USES_FOR_PARAMETER_TUNING=false
VALIDATION_USES_FOR_EVALUATION=true
```

## 5. Quantile / distribution authority (unchanged)

This owner decision does **not** authorize baseline quantiles.

```text
BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

Do not manufacture P80/P90, copy incumbent quantiles, derive a residual
distribution, or infer a distribution from the selected median estimator.

## 6. TEST custody

```text
TEST_ACCESS=false
TEST_USE=SEALED
```

TEST must remain unread and unevaluated.

## 7. Canonical payload and SHA-256 replay

Canonicalization: UTF-8, uppercase keys as issued, sorted JSON keys, compact
`,:` separators, SHA-256 over the semantic payload excluding self-referential
hash fields.

```text
OWNER_DECISION_SHA256=39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463
OWNER_DECISION_HASH_REPLAY=PASS
OWNER_DECISION_PAYLOAD_BINDING=PASS
OWNER_DECISION_BINDING=PASS
```

Exact canonical serialized payload is recorded in
`docs/v0-3/s3/evidence/s3-farm-total-baseline-estimator-owner-decision-binding.json`.

## 8. Implementation gate

```text
OWNER_DECISION_COMPLETE=true
IMPLEMENTATION_AUTHORIZED=false
ESTIMATOR_IMPLEMENTATION_GATE_OPEN=false
ESTIMATOR_IMPLEMENTATION_STATUS=BLOCKED_SEPARATE_IMPLEMENTATION_AUTHORIZATION
V0_3_S4_AUTHORIZED=false
```

Owner semantics are frozen. Estimator **implementation** requires a separate
implementation-authorization task after this binding is reviewed, merged, and
main CI is green.

This binding does not modify Python, materialize datasets, score VALIDATION,
read TEST, or compute medians from real data.

## 9. References

| Role | Path |
| --- | --- |
| Parent contract | `docs/v0-3/s3/s3-farm-total-baseline-estimator-contract.md` |
| Decision request | `docs/v0-3/s3/s3-farm-total-baseline-estimator-owner-decision-request.md` |
| Decision request evidence | `docs/v0-3/s3/evidence/s3-farm-total-baseline-estimator-owner-decision-request.json` |
| S1 general split | `docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md` |
| Quantile limitation | `docs/v0-3/s3/s3-quantile-semantics-contract.md` |
