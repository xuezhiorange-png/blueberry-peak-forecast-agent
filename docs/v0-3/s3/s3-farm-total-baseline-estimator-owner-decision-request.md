# V0.3-S3 Farm-total Baseline Estimator Owner Decision Request (R1)

> Scope: owner decision request preparation only — no estimator decision, implementation, fitting, tuning, or evaluation
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_OWNER_DECISION_REQUEST_R1`
> Parent contract: `docs/v0-3/s3/s3-farm-total-baseline-estimator-contract.md`
> Base: `1cb21350531c30d09d5f3c6abd215a9e7a361a51`

## Machine-readable header

```text
DECISION_REQUEST_ID=V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTICS
DECISION_REQUEST_VERSION=R1
DECISION_REQUEST_STATUS=OWNER_DECISION_REQUIRED

OWNER_DECISION_REQUEST_PREPARED=true
OWNER_DECISION_ISSUED=false
OWNER_DECISION_FINAL=false

OWNER_IDENTITY=null
OWNER_ATTESTATION=null

IMPLEMENTATION_AUTHORIZED=false
ESTIMATOR_IMPLEMENTATION_GATE_OPEN=false
ESTIMATOR_IMPLEMENTATION_STATUS=BLOCKED_OWNER_DECISION

TEST_ACCESS=false
TEST_USE=SEALED
V0_3_S4_AUTHORIZED=false

NO_STEP_IMPLIES_THE_NEXT=true
```

This workpaper converts the 13 unresolved owner-decision fields from the
merged R0 contract into a concise, reviewable request. It is **not** an owner
decision, attestation, implementation authorization, or estimator formula freeze.

## 1. Decision request identity

| Attribute | Value |
| --- | --- |
| Decision request ID | `V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTICS` |
| Version | `R1` |
| Status | `OWNER_DECISION_REQUIRED` |
| Parent contract | `docs/v0-3/s3/s3-farm-total-baseline-estimator-contract.md` |
| Evidence artifact | `docs/v0-3/s3/evidence/s3-farm-total-baseline-estimator-owner-decision-request.json` |
| Base main SHA | `1cb21350531c30d09d5f3c6abd215a9e7a361a51` |

## 2. Frozen upstream facts (not decided here)

These facts are established by existing repository authority and bind any future
estimator. This request does not re-freeze or modify them.

| Fact | Authority |
| --- | --- |
| `V0_3_BASELINE_TARGET=FARM_TOTAL_HARVEST_QUANTITY` | `backend/app/forecast_quality/farm_total_policy.py` |
| `BASELINE_ENTITY=BASELINE_FARM_GROUP` | `backend/app/forecast_quality/farm_total_policy.py` |
| Target season `2025~2026` | `farm_total_policy.py` |
| Prior area source season `2024~2025` | `farm_total_policy.py` |
| Area authority class `PREVIOUS_SEASON_PROXY` | `farm_total_policy.py` |
| Eligible groups `31`; authorized area `21719.09138059892957` mu | `farm_total_policy.py` |
| Conflict exclusions: 双龙营, 新哨, 盘龙 | `farm_total_policy.py` |
| Row grain: `(season_business_key, baseline_farm_group_key, harvest_business_date)` | `farm_total_dataset.py` |
| TRAIN / VALIDATION partitions at data-plane boundary | `farm_total_dataset.py` |
| TEST rejected (`TEST_PARTITION_FORBIDDEN`) | `farm_total_dataset.py` |
| Authority bundle binding | `farm_total_data_plane.py`, `farm_total_authority_binding.py` |
| General split: `VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY` | `docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md` |
| Baseline P80/P90 not computable without distribution | `docs/v0-3/s3/s3-quantile-semantics-contract.md`, `docs/v0-3/s1/metric-coverage-and-quality-contract.md` |

```text
BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

## 3. Hard prohibition

```text
THIS_DOCUMENT_IS_NOT_AN_OWNER_DECISION=true
OWNER_DECISION_ISSUED=false
IMPLEMENTATION_AUTHORIZED=false
```

Do not treat proposal identifiers, candidate shapes, or tradeoff descriptions
in this request as accepted values. Cursor, developers, and data availability
must not infer `ACCEPTED_VALUE` for any field.

## 4. Owner decision table

All `ACCEPTED_VALUE` entries are `null` / `UNSET`.

| FIELD | CURRENT_STATUS | CURRENT_AUTHORITY | CANDIDATE_VALUES_OR_DECISION_SHAPE | KEY_CONSEQUENCE | ACCEPTED_VALUE | OWNER_ACTION_REQUIRED |
| --- | --- | --- | --- | --- | --- | --- |
| `BASELINE_ESTIMATOR_FAMILY` | `OWNER_DECISION_REQUIRED` | None (R0: not found in repo) | `GROUP_SPECIFIC_HISTORICAL_STATISTIC`; `AREA_NORMALIZED_KG_PER_MU_PROJECTION`; `POOLED_FARM_TOTAL_SEASONAL_PROFILE`; `PRIOR_PERIOD_OR_ANALOG_DATE` — all `PROPOSAL_ONLY` / `NOT_AUTHORIZED` / `DO_NOT_IMPLEMENT` | Defines entire baseline formula; families are not interchangeable | `null` | Freeze one named family with deterministic definition |
| `TIME_AXIS` | `OWNER_DECISION_REQUIRED` | None | `HARVEST_BUSINESS_DATE`; `SEASON_DAY_INDEX`; `OWNER_DEFINED_ANALOG_DATE_MAPPING`; `OTHER_EXPLICITLY_DEFINED_TIME_AXIS` | Misalignment causes leakage or off-by-one harvest-day errors | `null` | Freeze calendar alignment rule |
| `AREA_NORMALIZATION_POLICY` | `OWNER_DECISION_REQUIRED` | `area_mu` bound via area authority; use policy unset | `RAW_HARVEST_KG`; `KG_PER_MU_THEN_PROJECT_BY_AUTHORIZED_AREA`; `NO_AREA_NORMALIZATION`; `OTHER_EXPLICIT_OWNER_POLICY` | Wrong policy double-counts or mis-scales yield; area is `PREVIOUS_SEASON_PROXY` | `null` | Freeze whether/how `area_mu` enters computation |
| `POOLING_GRAIN` | `OWNER_DECISION_REQUIRED` | None | `BASELINE_FARM_GROUP_SPECIFIC`; `POOLED_ACROSS_ELIGIBLE_GROUPS`; `OTHER_EXPLICIT_OWNER_GRAIN` | Pooling changes support and heterogeneity treatment | `null` | Freeze group-specific vs pooled statistic scope |
| `TRAIN_AGGREGATION_STATISTIC` | `OWNER_DECISION_REQUIRED` | None | Example shapes only: `MEAN`; `MEDIAN`; `TRIMMED_STATISTIC`; `ANALOG_LOOKUP`; `PERSISTENCE`; `OWNER_DEFINED_DETERMINISTIC_STATISTIC` | Defines point value per `(group, date)` | `null` | Freeze statistic plus tie-break and window rules |
| `MIN_TRAIN_SUPPORT` | `OWNER_DECISION_REQUIRED` | None | `EXPLICIT_NON_NEGATIVE_INTEGER_OR_DETERMINISTIC_SUPPORT_RULE` | Too low → unstable baselines; too high → sparse output gaps | `null` | Freeze support threshold or rule (no numeric default here) |
| `UNSEEN_GROUP_POLICY` | `OWNER_DECISION_REQUIRED` | 31 eligible groups frozen | `FAIL_CLOSED`; `POOL_FALLBACK`; `GLOBAL_FALLBACK`; `OTHER_EXPLICIT_OWNER_POLICY` | Governs groups with no TRAIN rows | `null` | Freeze behavior for empty-group support |
| `MISSING_DAY_POLICY` | `OWNER_DECISION_REQUIRED` | None | `FAIL_CLOSED`; `SKIP_OUTPUT`; `NEAREST_PRIOR_ALLOWED_SOURCE`; `INTERPOLATION_IF_SEPARATELY_AUTHORIZED`; `OTHER_EXPLICIT_OWNER_POLICY` | Rows exist only on harvest days with actuals | `null` | Freeze gap behavior for missing `harvest_business_date` |
| `COLD_START_POLICY` | `OWNER_DECISION_REQUIRED` | TRAIN start `2025-08-05` frozen | `FAIL_CLOSED`; `EXPLICIT_POOL_FALLBACK`; `EXPLICIT_PRIOR_PERIOD_FALLBACK`; `OTHER_OWNER_DEFINED_POLICY` | Distinct from unseen-group policy; early-season dates may lack in-season TRAIN | `null` | Freeze early-season behavior |
| `VALIDATION_USE_POLICY` | `OWNER_DECISION_REQUIRED` | General: `CANDIDATE_SELECTION_AND_VALIDATION_ONLY` (S1 split) | Farm-total candidates: `EVALUATION_ONLY` (`PROPOSAL_ONLY`, not accepted); `INHERIT_GENERAL_CANDIDATE_SELECTION_AND_VALIDATION_ONLY`; other explicit baseline-specific policy | Stricter `EVALUATION_ONLY` blocks VALIDATION-driven family/parameter selection for this baseline | `null` | Accept, reject, or replace proposed `EVALUATION_ONLY` restriction |
| `OUTPUT_SEMANTICS` | `OWNER_DECISION_REQUIRED` | `V0_3_BASELINE_TARGET` frozen; point transform unset | `DAILY_HARVEST_KG_PER_BASELINE_FARM_GROUP`; `KG_PER_MU_INTERMEDIATE_PROJECTED_TO_DAILY_KG`; `CUMULATIVE_HARVEST_KG`; `OTHER_EXPLICIT_POINT_TARGET_TRANSFORM` | Downstream metrics require unambiguous units; does **not** authorize P80/P90 | `null` | Freeze point-target transform only |
| `OWNER_IDENTITY` | `OWNER_INPUT_REQUIRED` | None | Human owner identity per project governance | Required for accountable freeze | `null` | Provide owner identity |
| `OWNER_ATTESTATION` | `OWNER_INPUT_REQUIRED` | None | Signed attestation referencing decision request and frozen field values | Opens implementation gate when all fields frozen | `null` | Provide attestation |

## 5. Candidate tradeoffs (proposal shapes only)

### 5.1 Estimator family proposals (from R0 §8)

| Proposal ID | Input grain | Principal benefit | Principal risk |
| --- | --- | --- | --- |
| `GROUP_SPECIFIC_HISTORICAL_STATISTIC` | TRAIN per `baseline_farm_group_key` × `harvest_business_date` | Simple, interpretable, respects group heterogeneity | Sparse dates need explicit missing-day and min-support policies |
| `AREA_NORMALIZED_KG_PER_MU_PROJECTION` | TRAIN `actual_harvest_kg_per_mu`; `area_mu` from authority | Separates yield rate from authorized area | `PREVIOUS_SEASON_PROXY` area; mis-normalization if policy unclear |
| `POOLED_FARM_TOTAL_SEASONAL_PROFILE` | Pooled TRAIN across eligible groups | More calendar support for sparse groups | Dilutes group-specific behavior |
| `PRIOR_PERIOD_OR_ANALOG_DATE` | TRAIN aligned by owner analog rule | Seasonal structure explicit | Risk of importing V0.2 fine-grain analog inappropriately |

```text
PROPOSAL_ONLY=true
NOT_AUTHORIZED=true
DO_NOT_IMPLEMENT=true
NO_WINNER_ASSIGNED=true
```

### 5.2 Validation-use layering

```text
EXISTING_GENERAL_SPLIT_AUTHORITY=true
GENERAL_VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY

PROPOSED_FARM_TOTAL_BASELINE_VALIDATION_USE=EVALUATION_ONLY
PROPOSAL_ONLY=true
OWNER_ACCEPTANCE_REQUIRED=true
NOT_CURRENTLY_ACCEPTED=true
```

If owner accepts `EVALUATION_ONLY` for Farm-total baseline: VALIDATION may score
but must not fit, select family, or tune parameters for this baseline. If owner
chooses `INHERIT_GENERAL_CANDIDATE_SELECTION_AND_VALIDATION_ONLY`, general S1
split authority applies without the stricter baseline restriction.

### 5.3 Output semantics vs quantile limitation

Resolving `OUTPUT_SEMANTICS` addresses the **point-target transform only**. It
does not set `BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=true` or make P80/P90
computable.

## 6. Owner response template

Copy, fill, and submit through project governance. Do **not** treat unfilled
placeholders as decided.

```text
DECISION_ID=V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_SEMANTICS
DECISION=ACCEPT

BASELINE_ESTIMATOR_FAMILY=<OWNER_VALUE>
TIME_AXIS=<OWNER_VALUE>
AREA_NORMALIZATION_POLICY=<OWNER_VALUE>
POOLING_GRAIN=<OWNER_VALUE>
TRAIN_AGGREGATION_STATISTIC=<OWNER_VALUE>
MIN_TRAIN_SUPPORT=<OWNER_VALUE>
UNSEEN_GROUP_POLICY=<OWNER_VALUE>
MISSING_DAY_POLICY=<OWNER_VALUE>
COLD_START_POLICY=<OWNER_VALUE>
VALIDATION_USE_POLICY=<OWNER_VALUE>
OUTPUT_SEMANTICS=<OWNER_VALUE>

OWNER_IDENTITY=<OWNER_VALUE>
OWNER_ATTESTATION=<OWNER_VALUE>
```

## 7. Downstream gate after owner decision

`ESTIMATOR_IMPLEMENTATION_GATE_OPEN` may become `true` only when **all** hold:

1. Every field in Section 4 has a non-null `ACCEPTED_VALUE` frozen by owner.
2. `OWNER_IDENTITY` is recorded.
3. `OWNER_ATTESTATION` is present and references this decision request version.
4. A separate implementation PR is opened with `IMPLEMENTATION_AUTHORIZED=true`.
5. `V0_3_S4_AUTHORIZED` is explicitly granted if S4 scope is required.

Until then:

```text
OWNER_DECISION_ISSUED=false
OWNER_DECISION_FINAL=false
IMPLEMENTATION_AUTHORIZED=false
ESTIMATOR_IMPLEMENTATION_GATE_OPEN=false
ESTIMATOR_IMPLEMENTATION_STATUS=BLOCKED_OWNER_DECISION
```

Submitting this response template does not, by itself, authorize implementation.
A follow-on binding workpaper and evidence artifact are required to record the
owner decision in repository canonical form.

## 8. References

| Role | Path |
| --- | --- |
| Parent contract (R0) | `docs/v0-3/s3/s3-farm-total-baseline-estimator-contract.md` |
| Farm-total policy | `backend/app/forecast_quality/farm_total_policy.py` |
| Data plane | `backend/app/forecast_quality/farm_total_data_plane.py` |
| Dataset | `backend/app/forecast_quality/farm_total_dataset.py` |
| S1 split authority | `docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md` |
| Quantile limitation | `docs/v0-3/s3/s3-quantile-semantics-contract.md` |
| V0.2 baseline (non-inherited) | `docs/forecast-quality/s3-naive-baseline-decision.md` |
