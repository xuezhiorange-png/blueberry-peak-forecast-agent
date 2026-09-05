# V0.3-S3 Farm-total Baseline Estimator Contract (R0)

> Scope: source-definition and owner-decision contract only
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_CONTRACT_R0`
> Authority correction: `V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_CONTRACT_R0_AUTHORITY_CORRECTION_R1`
> Base: `5aa872fc327690420544ab43b51951efcd5338b7`
> Companion data plane: `backend/app/forecast_quality/farm_total_*`
> Historical separation: `docs/forecast-quality/s3-naive-baseline-decision.md`

## Authority block

```text
V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_CONTRACT_VERSION=R0
CONTRACT_STATUS=OWNER_DECISION_REQUIRED
IMPLEMENTATION_AUTHORIZED=false

V0_3_BASELINE_TARGET=FARM_TOTAL_HARVEST_QUANTITY
BASELINE_ENTITY=BASELINE_FARM_GROUP

TRAIN_USE=ESTIMATOR_DERIVATION_ALLOWED
GENERAL_VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY
FARM_TOTAL_BASELINE_VALIDATION_USE_POLICY=OWNER_DECISION_REQUIRED
PROPOSED_FARM_TOTAL_BASELINE_VALIDATION_USE=EVALUATION_ONLY
PROPOSAL_ONLY=true
OWNER_ACCEPTANCE_REQUIRED=true
TEST_USE=SEALED

MODEL_CHANGE=false
PARAMETER_CHANGE=false
V0_3_S4_AUTHORIZED=false

OWNER_DECISION_STATUS=PENDING
```

This document closes the **authority-gap** between the frozen Farm-total data
plane and a future Farm-total baseline estimator. It does **not** implement an
estimator, freeze an estimator formula, or authorize V0.3-S4.

```text
NO_STEP_IMPLIES_THE_NEXT=true
ESTIMATOR_IMPLEMENTATION_STATUS=BLOCKED_OWNER_DECISION
```

## 1. Discovery verdict

### 1.1 Preflight

```text
BASE_MAIN_SHA=5aa872fc327690420544ab43b51951efcd5338b7
REPOSITORY_SEARCH_FOR_BASELINE_ESTIMATOR_FAMILY=NOT_FOUND
FARM_TOTAL_DATA_PLANE_IMPLEMENTED=true
FARM_TOTAL_ESTIMATOR_IMPLEMENTED=false
```

Repository search does **not** establish a frozen Farm-total estimator formula.
In particular, there is no authoritative frozen value for `BASELINE_ESTIMATOR_FAMILY`.

### 1.2 Facts already frozen by existing authority

The following facts are established by current repository sources and MUST be
treated as frozen inputs to any future estimator implementation. This contract
does **not** re-freeze them; it records their binding role.

| Fact | Repository source | Frozen value / semantics |
| --- | --- | --- |
| Baseline target | `backend/app/forecast_quality/farm_total_policy.py` | `V0_3_BASELINE_TARGET = "FARM_TOTAL_HARVEST_QUANTITY"` |
| Baseline entity | `backend/app/forecast_quality/farm_total_policy.py` | `V0_3_BASELINE_ENTITY = "BASELINE_FARM_GROUP"` |
| Target season | `backend/app/forecast_quality/farm_total_policy.py` | `FARM_TOTAL_TARGET_SEASON = "2025~2026"` |
| Prior area source season | `backend/app/forecast_quality/farm_total_policy.py` | `FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON = "2024~2025"` |
| Area authority class (R1) | `backend/app/forecast_quality/farm_total_policy.py` | `AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY = "PREVIOUS_SEASON_PROXY"` |
| Eligible group count | `backend/app/forecast_quality/farm_total_policy.py` | `REVIEWED_ELIGIBLE_PROXY_GROUP_COUNT = 31` |
| Authorized area total | `backend/app/forecast_quality/farm_total_policy.py` | `REVIEWED_ELIGIBLE_PROXY_AREA_MU = "21719.09138059892957"` |
| Conflict exclusions | `backend/app/forecast_quality/farm_total_policy.py` | `CONFLICT_EXCLUDED_BASELINE_FARM_GROUPS = {"双龙营", "新哨", "盘龙"}` |
| Dataset row grain | `backend/app/forecast_quality/farm_total_dataset.py` | `(season_business_key, baseline_farm_group_key, harvest_business_date)` |
| Row fields | `backend/app/forecast_quality/farm_total_dataset.py` | `area_mu`, `actual_harvest_quantity_kg`, `actual_harvest_kg_per_mu`, `partition`, `area_authority_class`, provenance hashes |
| Partition labels | `backend/app/forecast_quality/farm_total_dataset.py` | `TRAIN`, `VALIDATION` only at data-plane boundary |
| TEST partition rejection | `backend/app/forecast_quality/farm_total_dataset.py` | `TEST_PARTITION_FORBIDDEN`, `PARTITION_MEMBERSHIP_MISMATCH` |
| Authority bundle | `backend/app/forecast_quality/farm_total_data_plane.py` | `FarmTotalAuthorityBundle` = mapping package + area package |
| Cross-package binding | `backend/app/forecast_quality/farm_total_authority_binding.py` | mapping ↔ area group set, source members, mapping hash, season must align |

The Farm-total data plane already provides deterministic TRAIN and VALIDATION
rows at the `BASELINE_FARM_GROUP` grain via
`materialize_farm_total_baseline_data_plane()`. This contract MUST NOT modify
that data plane.

### 1.3 Decisions still requiring owner authorization

All fields in Section 3 remain `UNRESOLVED` / `OWNER_DECISION_REQUIRED` until
explicit owner authorization and attestation exist. Cursor MUST NOT populate
these fields by preference.

### 1.4 Prohibited assumptions

The following assumptions are **forbidden** before owner authorization:

| Prohibited assumption | Why forbidden |
| --- | --- |
| Transplant `PRIOR_SEASON_ANALOG_DAY_ACTUAL` from V0.2 | Different target (`FARM_TOTAL_HARVEST_QUANTITY`) and entity (`BASELINE_FARM_GROUP`) |
| Infer `BASELINE_ESTIMATOR_FAMILY` from code absence | Repository search found no frozen family |
| Use VALIDATION to choose estimator family or parameters under a stricter baseline policy not yet owner-accepted | Proposed `EVALUATION_ONLY` restriction is not frozen; general S1 split permits candidate selection on VALIDATION |
| Use TEST for fitting, selection, or inspection | TEST remains sealed |
| Copy incumbent model output as baseline | Not authorized for Farm-total baseline |
| Use post-target actuals unavailable at forecast time | Leakage |
| Emit P80/P90 without distribution authority | Inherited quantile limitation exists; Farm-total output semantics remain unresolved |
| Treat proposal options in Section 8 as frozen choices | All options are `PROPOSAL_ONLY` |

## 2. Historical separation from V0.2 naive baseline

`docs/forecast-quality/s3-naive-baseline-decision.md` freezes:

```text
NAIVE_BASELINE_NAME=PRIOR_SEASON_ANALOG_DAY_ACTUAL
NAIVE_BASELINE_TYPE=POINT_FORECAST
```

at grain:

```text
(farm_business_key, subfarm_business_key, variety_business_key)
```

That V0.2 authority is valid **for its own fine-grain scope**. It is **NOT**
automatically authority for:

```text
V0_3_BASELINE_TARGET=FARM_TOTAL_HARVEST_QUANTITY
BASELINE_ENTITY=BASELINE_FARM_GROUP
```

No silent inheritance of the V0.2 formula, season-analog mapping policy, or
point-forecast semantics is permitted for the Farm-total baseline.

## 3. Required owner-decision fields

Until owner authorization exists, each field below is `UNRESOLVED`. For each
field: what it controls, admissible decision shape, semantic impact, and
forbidden pre-authorization behavior.

### 3.1 `BASELINE_ESTIMATOR_FAMILY`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | The mathematical family used to produce the Farm-total point baseline |
| Admissible shape | Named family identifier plus deterministic definition (e.g. group-specific historical statistic, area-normalized projection, pooled seasonal profile, analog-date lookup) |
| Why it matters | Defines the entire baseline semantics; different families are not interchangeable |
| Forbidden before freeze | Implementing any estimator module, hard-coding a family constant, or claiming repository authority for a chosen family |

### 3.2 `TIME_AXIS`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Calendar alignment for estimator inputs and outputs (`harvest_business_date`, season-day index, analog mapping, lag structure) |
| Admissible shape | Explicit axis definition binding forecast date to TRAIN history lookup |
| Why it matters | Misaligned time axes create leakage or off-by-one harvest-day errors |
| Forbidden before freeze | Assuming V0.2 season-analog mapping without owner freeze; inventing calendar rules |

### 3.3 `AREA_NORMALIZATION_POLICY`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Whether and how `area_mu` participates in baseline computation |
| Admissible shape | Policies such as: raw kg only; kg/mu then multiply by authorized area; no area use |
| Why it matters | Area is bound via authority package; using it incorrectly double-counts or mis-scales yield |
| Forbidden before freeze | Defaulting to kg/mu or kg without owner decision; using non-authority area |

### 3.4 `POOLING_GRAIN`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Whether statistics are computed per `baseline_farm_group_key` or pooled across groups |
| Admissible shape | `GROUP_SPECIFIC`, `POOLED_FARM_TOTAL`, or other explicitly named pooling grain |
| Why it matters | Pooling changes support requirements and cold-start behavior |
| Forbidden before freeze | Silent cross-group pooling; using subfarm/variety grain |

### 3.5 `TRAIN_AGGREGATION_STATISTIC`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Deterministic statistic applied to TRAIN history (mean, median, trimmed mean, analog-day match, last observation, etc.) |
| Admissible shape | Named statistic plus tie-break and window rules |
| Why it matters | Defines the point forecast value for each `(group, date)` |
| Forbidden before freeze | Choosing mean/median by developer preference |

### 3.6 `MIN_TRAIN_SUPPORT`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Minimum TRAIN observations required before emitting a baseline for a group/date |
| Admissible shape | Non-negative integer or explicit rule (e.g. require N distinct harvest dates) |
| Why it matters | Prevents unstable baselines from sparse history |
| Forbidden before freeze | Hard-coding thresholds without owner freeze |

### 3.7 `UNSEEN_GROUP_POLICY`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Behavior when a `baseline_farm_group_key` has no TRAIN rows |
| Admissible shape | `FAIL_CLOSED`, `POOL_FALLBACK`, `GLOBAL_DEFAULT`, or other explicit policy |
| Why it matters | Eligible groups are fixed at 31, but date-level support may still be missing |
| Forbidden before freeze | Returning zero or global mean without owner decision |

### 3.8 `MISSING_DAY_POLICY`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Behavior when TRAIN has no row for a requested `harvest_business_date` (or aligned index) |
| Admissible shape | `FAIL_CLOSED`, `NEAREST_PRIOR_TRAIN_DAY`, `INTERPOLATE`, `SKIP_OUTPUT` |
| Why it matters | Farm-total rows exist only on harvest days with actuals |
| Forbidden before freeze | Implicit gap-filling |

### 3.9 `COLD_START_POLICY`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Behavior at early-season dates with insufficient within-season TRAIN history |
| Admissible shape | Explicit cold-start rule distinct from unseen-group and missing-day policies |
| Why it matters | TRAIN partition starts `2025-08-05`; early forecast dates may lack in-season context |
| Forbidden before freeze | Assuming full-season TRAIN availability |

### 3.10 `VALIDATION_USE_POLICY`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` |
| Controls | Whether the Farm-total baseline estimator adopts a stricter VALIDATION-use rule than the general V0.3 split contract |
| Why it matters | General split authority and baseline-specific restriction are separate layers; R0 does not narrow S1 authority by itself |

#### Existing general split authority (`EXISTING_GENERAL_SPLIT_AUTHORITY`)

```text
GENERAL_SPLIT_VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY
```

Source:

- `docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md`
- `docs/v0-3/s1/evidence/s1-split-policy-owner-decision-binding.json`

The owner-approved V0.3 S1 split contract permits candidate selection and
validation on the VALIDATION partition. R0 does **not** override or silently
narrow that authority.

#### Proposed Farm-total baseline restriction (`PROPOSED_FARM_TOTAL_BASELINE_RESTRICTION`)

```text
PROPOSED_FARM_TOTAL_BASELINE_VALIDATION_USE=EVALUATION_ONLY
PROPOSAL_ONLY=true
OWNER_ACCEPTANCE_REQUIRED=true
IMPLEMENTATION_AUTHORIZED=false
```

This R0 **proposes**, but does not freeze, a stricter rule for the Farm-total
baseline estimator: if owner-accepted, VALIDATION would be evaluation-only and
would **not** select estimator family or tune estimator parameters.

Until explicit owner acceptance:

```text
FARM_TOTAL_BASELINE_VALIDATION_USE_POLICY=OWNER_DECISION_REQUIRED
```

| Admissible shape | Owner accepts `EVALUATION_ONLY` for Farm-total baseline; or accepts a different explicitly named baseline-specific VALIDATION policy |
| Forbidden before freeze | Treating `EVALUATION_ONLY` as frozen by this contract; claiming R0 overrides S1 split authority; implementing leakage prohibitions as if already accepted |

### 3.11 `OUTPUT_SEMANTICS`

| Attribute | Value |
| --- | --- |
| Status | `OWNER_DECISION_REQUIRED` (`UNRESOLVED_OUTPUT_SEMANTICS`) |
| Controls | Units and interpretation of the Farm-total baseline point output |
| Admissible shape | Owner must explicitly choose among authorized point-target transforms such as: daily harvest kg per `baseline_farm_group_key`; kg/mu intermediate projected to kg via authorized `area_mu`; cumulative value; or another explicitly authorized point-target transform aligned with `V0_3_BASELINE_TARGET` |
| Why it matters | Downstream metrics require unambiguous units; different transforms are not interchangeable |
| Forbidden before freeze | Cursor choosing daily kg vs kg/mu vs cumulative; emitting unnamed or dual-unit outputs; treating inherited quantile limitations as a substitute for resolving output semantics |

#### Inherited baseline quantile limitation (`INHERITED_BASELINE_QUANTILE_LIMITATION`)

Separate from unresolved `OUTPUT_SEMANTICS`, the repository already establishes
that baseline P80/P90 are not computable without a quantile distribution:

```text
BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
INHERITED_CURRENT_LIMITATION=true
```

Sources:

- `docs/v0-3/s3/s3-quantile-semantics-contract.md`
- `docs/v0-3/s1/metric-coverage-and-quality-contract.md`
- `docs/forecast-quality/s3-naive-baseline-decision.md`

This inherited limitation is **not** `FROZEN_BY_THIS_CONTRACT`. R0 records it
but does not manufacture a Farm-total quantile distribution. Resolving
`OUTPUT_SEMANTICS` does not, by itself, authorize P80/P90 emission.

### 3.12 `OWNER_IDENTITY`

| Attribute | Value |
| --- | --- |
| Status | `UNRESOLVED` |
| Controls | Named owner authorized to freeze estimator decisions |
| Admissible shape | Human owner identity per project governance |
| Why it matters | Implementation gate requires accountable authorization |
| Forbidden | Cursor-invented owner identity |

### 3.13 `OWNER_ATTESTATION`

| Attribute | Value |
| --- | --- |
| Status | `UNRESOLVED` |
| Controls | Signed owner record that all Section 3 fields are frozen |
| Admissible shape | Dated attestation referencing this contract version and frozen field values |
| Why it matters | Opens implementation gate |
| Forbidden | Cursor-generated attestation; treating this document as attestation |

## 4. Data-plane binding

Any future estimator derivation MUST bind to the existing Farm-total authority
stack. Bypassing the data plane is forbidden.

### 4.1 Required authority chain

```text
FarmGroupMappingPackage
  -> FarmTotalAreaAuthorityPackage
  -> validate_mapping_area_authority_binding()
  -> FarmTotalAuthorityBundle
  -> materialize_farm_total_baseline_data_plane()
  -> FarmTotalTrainingDataset / FarmTotalValidationDataset
```

Sources:

- `backend/app/forecast_quality/farm_total_group_mapping.py`
- `backend/app/forecast_quality/farm_total_area_authority.py`
- `backend/app/forecast_quality/farm_total_authority_binding.py`
- `backend/app/forecast_quality/farm_total_data_plane.py`
- `backend/app/forecast_quality/farm_total_dataset.py`

### 4.2 Dataset fields available to a future estimator

From `FarmTotalDatasetRow`:

| Field | Role |
| --- | --- |
| `baseline_farm_group_key` | Baseline entity key |
| `harvest_business_date` | Time index |
| `partition` | `TRAIN` or `VALIDATION` membership |
| `area_mu` | Authorized area from area authority package |
| `area_authority_class` | e.g. `PREVIOUS_SEASON_PROXY` |
| `actual_harvest_quantity_kg` | Observed Farm-total harvest kg |
| `actual_harvest_kg_per_mu` | Derived kg per authorized mu |
| `source_farm_business_keys` | Member farms aggregated into group |
| `area_authority_row_hash`, `actual_projection_hash`, `row_hash` | Provenance |

### 4.3 Partition use rules

#### General V0.3 split authority

```text
EXISTING_GENERAL_SPLIT_AUTHORITY=true
GENERAL_SPLIT_VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY
```

Source: `docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md`

#### Farm-total baseline-specific proposal (not frozen)

```text
PROPOSED_FARM_TOTAL_BASELINE_VALIDATION_USE=EVALUATION_ONLY
PROPOSAL_ONLY=true
OWNER_ACCEPTANCE_REQUIRED=true
FARM_TOTAL_BASELINE_VALIDATION_USE_POLICY=OWNER_DECISION_REQUIRED
```

If owner-accepted, the proposed stricter rule would mean:

```text
TRAIN may be used for estimator derivation ONLY AFTER estimator semantics are owner-authorized.
VALIDATION MUST NOT be used to fit, select, tune, or derive Farm-total baseline estimator parameters.
VALIDATION would be evaluation-only for this baseline scope.
```

Until owner acceptance, implementers MUST NOT assume the stricter rule is in
force. The general S1 split authority remains binding for non-baseline scopes.

#### TEST custody (frozen by S1 split authority)

```text
TEST_USE=SEALED
TEST remains sealed and MUST NOT be read, scored, inspected, or used for selection.
```

Partition boundaries are enforced at data-plane materialization
(`TEST_PARTITION_FORBIDDEN`, `PARTITION_MEMBERSHIP_MISMATCH`).

## 5. Leakage contract

### 5.1 Proposed Farm-total baseline restrictions (not frozen)

If and only if the owner accepts
`PROPOSED_FARM_TOTAL_BASELINE_VALIDATION_USE=EVALUATION_ONLY`, the following
baseline-specific prohibitions would apply:

```text
PROPOSAL_ONLY=true
OWNER_ACCEPTANCE_REQUIRED=true
BASELINE_USES_VALIDATION_TO_FIT=false
BASELINE_USES_VALIDATION_TO_SELECT_FAMILY=false
BASELINE_USES_VALIDATION_TO_SELECT_PARAMETERS=false
```

Until `FARM_TOTAL_BASELINE_VALIDATION_USE_POLICY` is owner-frozen, these flags
describe a **proposal**, not current authority. They do not override the general
S1 rule that VALIDATION may be used for candidate selection elsewhere.

### 5.2 Unconditional prohibitions (independent of validation-use proposal)

```text
BASELINE_USES_TEST=false
BASELINE_USES_INCUMBENT_MODEL_OUTPUT=false
BASELINE_USES_POST_TARGET_ACTUALS=false
```

Explicit prohibitions:

- No TEST partition access for any Farm-total baseline purpose (`TEST_USE=SEALED`).
- No borrowing incumbent forecast outputs as the Farm-total baseline.
- No use of actuals that would not be available at the forecast issuance time
  for the target date.

If the proposed `EVALUATION_ONLY` restriction is owner-accepted:

- No Farm-total baseline estimator decision may be justified using VALIDATION
  performance.
- No Farm-total baseline tuning loop may read VALIDATION rows during estimator
  definition.

## 6. Output semantics and quantile boundary

This section separates two distinct layers:

```text
UNRESOLVED_OUTPUT_SEMANTICS=true
INHERITED_BASELINE_QUANTILE_LIMITATION=true
```

### 6.1 Unresolved Farm-total output semantics (`OUTPUT_SEMANTICS`)

`OUTPUT_SEMANTICS` remains `OWNER_DECISION_REQUIRED`. The owner must still
decide whether the Farm-total estimator emits semantics such as:

- daily harvest kg per `baseline_farm_group_key`;
- kg/mu intermediate projected to kg via authorized `area_mu`;
- cumulative value;
- another explicitly authorized point-target transform.

No choice may be made by Cursor. R0 does not freeze any of these options.

### 6.2 Inherited current quantile-distribution limitation (`INHERITED_BASELINE_QUANTILE_LIMITATION`)

The repository already establishes, via separate authorities, that baseline
P80/P90 are not computable without a quantile distribution:

```text
BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
INHERITED_CURRENT_LIMITATION=true
NOT_FROZEN_BY_THIS_CONTRACT=true
```

Sources:

- `docs/v0-3/s3/s3-quantile-semantics-contract.md`
- `docs/v0-3/s1/metric-coverage-and-quality-contract.md`
- `docs/forecast-quality/s3-naive-baseline-decision.md`

R0 records this inherited limitation. It does **not** manufacture a Farm-total
quantile distribution. The Farm-total baseline contract MUST NOT create P80/P90
values by:

- copying the point forecast;
- copying incumbent P80/P90;
- applying arbitrary multipliers;
- interpreting empirical residual spread as authority;
- inventing a distribution.

Resolving `OUTPUT_SEMANTICS` addresses the point-target transform only. It does
not authorize `BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=true` unless a separate
owner authority explicitly grants distribution semantics.

## 7. Estimator decision boundary

The following are **mathematical decisions** requiring explicit owner
authorization before implementation:

| Decision area | Examples |
| --- | --- |
| Target transform | daily kg, kg/mu, cumulative yield, other |
| Pooling | group-specific vs pooled across `baseline_farm_group_key` |
| Area normalization timing | before aggregation, after aggregation, not used |
| Estimator family | mean, median, trimmed statistic, analog-day, seasonal profile, persistence |
| Calendar alignment | harvest_business_date rules, season-day index, analog mapping |
| Support thresholds | `MIN_TRAIN_SUPPORT` |
| Unseen groups | `UNSEEN_GROUP_POLICY` |
| Missing days | `MISSING_DAY_POLICY` |
| Cold start | `COLD_START_POLICY` |

```text
CURSOR_MUST_NOT_RESOLVE_THESE_ITEMS=true
```

## 8. Non-authoritative estimator options for owner review

Every option below is labelled:

```text
PROPOSAL_ONLY
NOT_AUTHORIZED
DO_NOT_IMPLEMENT
```

No winner is assigned. No performance claims from VALIDATION are made.

### Option A — Group-specific deterministic historical statistic

```text
PROPOSAL_ONLY
NOT_AUTHORIZED
DO_NOT_IMPLEMENT
```

| Attribute | Description |
| --- | --- |
| Input grain | TRAIN rows per `baseline_farm_group_key` × `harvest_business_date` |
| Semantic idea | Compute a deterministic statistic (e.g. mean/median) of `actual_harvest_quantity_kg` or `actual_harvest_kg_per_mu` within each group over TRAIN dates aligned to the forecast date rule |
| Principal benefit | Simple, interpretable, respects group heterogeneity |
| Principal risk | Sparse dates produce unstable estimates; requires explicit missing-day and min-support policies |
| Owner decisions required | `BASELINE_ESTIMATOR_FAMILY`, `TRAIN_AGGREGATION_STATISTIC`, `TIME_AXIS`, `MIN_TRAIN_SUPPORT`, `MISSING_DAY_POLICY` |

### Option B — Area-normalized kg/mu estimator projected through authorized area

```text
PROPOSAL_ONLY
NOT_AUTHORIZED
DO_NOT_IMPLEMENT
```

| Attribute | Description |
| --- | --- |
| Input grain | TRAIN `actual_harvest_kg_per_mu` per group × date; `area_mu` from area authority |
| Semantic idea | Estimate kg/mu from TRAIN, multiply by authorized `area_mu` to emit kg baseline |
| Principal benefit | Separates yield rate from authorized area binding |
| Principal risk | Area is `PREVIOUS_SEASON_PROXY`; mis-normalization if area policy not explicit |
| Owner decisions required | `AREA_NORMALIZATION_POLICY`, `OUTPUT_SEMANTICS`, `TRAIN_AGGREGATION_STATISTIC`, `TIME_AXIS` |

### Option C — Pooled Farm-total seasonal-profile estimator

```text
PROPOSAL_ONLY
NOT_AUTHORIZED
DO_NOT_IMPLEMENT
```

| Attribute | Description |
| --- | --- |
| Input grain | Pooled TRAIN rows across all eligible `baseline_farm_group_key` values |
| Semantic idea | Build a single seasonal profile over harvest calendar, optionally allocate to groups by weights |
| Principal benefit | More support per calendar position for sparse groups |
| Principal risk | Dilutes group-specific behavior; pooling grain must be explicit |
| Owner decisions required | `POOLING_GRAIN`, `BASELINE_ESTIMATOR_FAMILY`, `TIME_AXIS`, `UNSEEN_GROUP_POLICY` |

### Option D — Prior-period / analog-date estimator

```text
PROPOSAL_ONLY
NOT_AUTHORIZED
DO_NOT_IMPLEMENT
```

| Attribute | Description |
| --- | --- |
| Input grain | TRAIN history aligned by explicit analog calendar rule (not V0.2 fine-grain analog) |
| Semantic idea | Map forecast `harvest_business_date` to a TRAIN lookup date or prior-season proxy per owner-defined analog policy |
| Principal benefit | Seasonal structure explicit; familiar decision shape |
| Principal risk | Easy to accidentally import V0.2 fine-grain analog semantics inappropriately |
| Owner decisions required | `TIME_AXIS`, `BASELINE_ESTIMATOR_FAMILY`, `MISSING_DAY_POLICY`, `COLD_START_POLICY` |

## 9. Recommendation boundary

This contract includes **no owner recommendation** with implementation force.

If a future amendment adds a recommendation, it MUST be written as:

```text
RECOMMENDATION_STATUS=PROPOSAL_ONLY
OWNER_ACCEPTANCE_REQUIRED=true
IMPLEMENTATION_AUTHORIZED=false
```

A recommendation MUST NOT become a frozen contract merely because it appears
in documentation.

## 10. Implementation gate

```text
ESTIMATOR_IMPLEMENTATION_GATE_OPEN=false
ESTIMATOR_IMPLEMENTATION_STATUS=BLOCKED_OWNER_DECISION
```

`ESTIMATOR_IMPLEMENTATION_GATE_OPEN` may become `true` only if **all** of the
following hold:

1. Every owner-decision field in Section 3 is frozen to an explicit value (not
   `UNRESOLVED`).
2. `OWNER_IDENTITY` is recorded.
3. `OWNER_ATTESTATION` is present and references this contract version.
4. A separate implementation authorization PR is opened with
   `IMPLEMENTATION_AUTHORIZED=true`.
5. `V0_3_S4_AUTHORIZED` is explicitly granted by owner governance if S4 scope
   is required.

Until then, no estimator code, tests, migrations, or parameter files may be
added under Farm-total baseline estimator scope.

## 11. Acceptance matrix

| Field | Current status | Authority source | Implementation blocker | Evidence to close |
| --- | --- | --- | --- | --- |
| `BASELINE_ESTIMATOR_FAMILY` | `OWNER_DECISION_REQUIRED` | None | No formula defined | Owner freeze + attestation |
| `TIME_AXIS` | `OWNER_DECISION_REQUIRED` | None | Calendar alignment undefined | Owner freeze + attestation |
| `AREA_NORMALIZATION_POLICY` | `OWNER_DECISION_REQUIRED` | Area authority binds `area_mu`; policy for use unset | Normalization path undefined | Owner freeze + attestation |
| `POOLING_GRAIN` | `OWNER_DECISION_REQUIRED` | None | Group vs pooled undefined | Owner freeze + attestation |
| `TRAIN_AGGREGATION_STATISTIC` | `OWNER_DECISION_REQUIRED` | None | Statistic undefined | Owner freeze + attestation |
| `MIN_TRAIN_SUPPORT` | `OWNER_DECISION_REQUIRED` | None | Support rule undefined | Owner freeze + attestation |
| `UNSEEN_GROUP_POLICY` | `OWNER_DECISION_REQUIRED` | 31 eligible groups frozen | Sparse/empty group behavior undefined | Owner freeze + attestation |
| `MISSING_DAY_POLICY` | `OWNER_DECISION_REQUIRED` | None | Gap behavior undefined | Owner freeze + attestation |
| `COLD_START_POLICY` | `OWNER_DECISION_REQUIRED` | TRAIN start `2025-08-05` frozen | Early-season behavior undefined | Owner freeze + attestation |
| `VALIDATION_USE_POLICY` | `OWNER_DECISION_REQUIRED` | S1 split: `VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY` (`docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md`); R0 proposes `EVALUATION_ONLY` only | Stricter baseline VALIDATION rule not accepted | Owner freeze + attestation accepting or rejecting proposed restriction |
| `OUTPUT_SEMANTICS` | `OWNER_DECISION_REQUIRED` | `V0_3_BASELINE_TARGET` frozen in `farm_total_policy.py`; point transform unset | Output unit/path undefined | Owner freeze + attestation |
| `OWNER_IDENTITY` | `UNRESOLVED` | None | No accountable owner | Owner record |
| `OWNER_ATTESTATION` | `UNRESOLVED` | None | Gate closed | Signed attestation |
| Inherited baseline P80/P90 limitation | `INHERITED_CURRENT_LIMITATION` | `docs/v0-3/s3/s3-quantile-semantics-contract.md`, `docs/v0-3/s1/metric-coverage-and-quality-contract.md` | P80/P90 not computable without distribution authority | Separate distribution authority if ever needed |
| Data-plane binding | `FROZEN` | `farm_total_*` modules | Estimator must use bundle | Implementation review |
| TEST sealed | `FROZEN` | S1 split policy (`TEST_PURPOSE=SEALED_FINAL_EVALUATION_ONLY`) | TEST access forbidden | N/A |

## 12. References

References are grouped by role. Not every reference is estimator-formula
authority; some establish split custody, metric limitations, or data-plane facts
only.

### 12.1 Farm-total data-plane authority (binding for future estimator inputs)

| Reference | Path | Role |
| --- | --- | --- |
| Farm-total policy constants | `backend/app/forecast_quality/farm_total_policy.py` | Frozen target, entity, season, area totals |
| Data plane orchestrator | `backend/app/forecast_quality/farm_total_data_plane.py` | Authority bundle materialization |
| Dataset projection | `backend/app/forecast_quality/farm_total_dataset.py` | TRAIN/VALIDATION row grain and fields |
| Mapping authority | `backend/app/forecast_quality/farm_total_group_mapping.py` | `baseline_farm_group_key` mapping |
| Area authority | `backend/app/forecast_quality/farm_total_area_authority.py` | `area_mu` authority package |
| Authority binding | `backend/app/forecast_quality/farm_total_authority_binding.py` | Cross-package binding |

### 12.2 General V0.3 split authority (not overridden by R0)

| Reference | Path | Role |
| --- | --- | --- |
| S1 split policy owner binding | `docs/v0-3/s1/workpapers/s1-split-policy-owner-decision-binding.md` | Owner-frozen `VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY` |
| S1 split policy evidence | `docs/v0-3/s1/evidence/s1-split-policy-owner-decision-binding.json` | Canonical acceptance record for split policy |

### 12.3 Inherited quantile and metric limitations (not Farm-total formula authority)

| Reference | Path | Role |
| --- | --- | --- |
| Quantile semantics contract | `docs/v0-3/s3/s3-quantile-semantics-contract.md` | `NOT_COMPUTABLE` baseline P80/P90 rules |
| Metric coverage and quality | `docs/v0-3/s1/metric-coverage-and-quality-contract.md` | `CURRENT_BASELINE_P80_STATUS=NOT_COMPUTABLE` etc. |
| V0.2 naive baseline (historical, non-inherited) | `docs/forecast-quality/s3-naive-baseline-decision.md` | Fine-grain point baseline; not Farm-total formula authority |

## 13. Change log

| Version | Date | Change |
| --- | --- | --- |
| R0 | 2026-09-05 | Initial owner-decision contract; no estimator implementation |
| R1 | 2026-09-05 | Authority correction: `VALIDATION_USE_POLICY` and `OUTPUT_SEMANTICS` no longer self-authorized by R0; distinguish general S1 split authority from proposed Farm-total baseline restriction; distinguish unresolved output semantics from inherited quantile limitation |
