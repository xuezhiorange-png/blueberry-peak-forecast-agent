# Round A Implementation Boundary

```text
PACKAGE_STATUS=PROPOSED_FOR_INDEPENDENT_REREVIEW
PACKAGE_SOURCE_MAIN_SHA=4d7effe82c61e5fbd6ddcc22eefa61ab74a6663d
IMPLEMENTATION_BASE_SHA=NOT_BOUND_PENDING_PACKAGE_ACCEPTANCE_AND_MERGE
ROUND_A_AUTHORIZATION_PACKAGE_ACCEPTED=false
ROUND_A_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
ROUND_B_AUTHORIZED=false
ISSUE102_CLOSE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The three PR #131 design documents remain the only design authority. This
package is not implementation authorization. A separately authorized exact
implementation base must contain this accepted package and the exact scripts.

## Authorized Round A behavior

- public schemas, enums and exception hierarchy;
- Decimal-only six-place `ROUND_HALF_EVEN` arithmetic;
- canonical JSON, metric-input-mask hash and exact baseline canonical payloads;
- seven P50 daily point metrics;
- deterministic six-axis breakdown cells;
- cross-quantile P50/P80/P90 retention with one physical actual registry;
- subfarm-to-farm daily **forecast and actual** aggregation;
- prior-season analog date resolution and current-cutoff visibility;
- requested P50 baseline point outcome;
- requested P80/P90 executable blocked outcome:
  `BLOCKED / NOT_COMPUTABLE /
  BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED / null`.

```text
AUTHORIZED_CREATE_PATH_COUNT=26
AUTHORIZED_TEST_MODULE_COUNT=17
S3R12_ROUND_A_STATUS=EXECUTABLE_DOMAIN_OUTCOME
S3R12_IMPLEMENTED_BY_ROUND_A=true
S3R12_RUNTIME_AUDIT_CLAIM=true
```

The required baseline API is:

```text
resolve_baseline_point_forecast(
  request: BaselineRequest,
  source_snapshot: BaselineSourceSnapshot
) -> BaselineResult
```

`BaselineRequest` includes `requested_quantile`. `BaselineResult` includes
`baseline_point_forecast_kg`, `comparison_availability`, `metric_status` and
`reason_code`.

## Exact canonical sets and versions

```text
BASELINE_CANONICAL_ROOT_FIELD_COUNT=26
BASELINE_CANONICAL_CELL_FIELD_COUNT=15
BASELINE_ROOT_FIELD_SET_EQUALITY=true
BASELINE_CELL_FIELD_SET_EQUALITY=true
BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0
INTERNAL_REASON_CODE_PRESENT=false
INTERNAL_REASON_CODE_MEMBER_COUNT=0
PUBLIC_INTERNAL_REASON_CODE_DISJOINT=true
METRIC_INPUT_MASK_V1=v0.2-s3-metric-input-mask-v1
NAIVE_BASELINE_POLICY_V1=v0.2-s3-naive-baseline-policy-v1
SEASON_ANALOG_MAPPING_V1=v0.2-s3-season-analog-mapping-v1
FROZEN_VERSION_NAME_SET_EQUALITY=true
FROZEN_VERSION_VALUE_SET_EQUALITY=true
GENERIC_VERSION_BRANCH_SHADOW_COUNT=0
```

## Script identity

```text
SCRIPT_01_SHA256=ea64e802fbca112217d9ab07ae3e02b91d2d062b3e4a5ba99e371d8bb1b9eef0
SCRIPT_02_SHA256=0fa3232ddeade11ef7b377d37f4ff95802e8854b525afc2c24e214e383ecb978
SCRIPT_03_SHA256=d4aba63856822fdf814adaa19a621223716b1073422abe3e81858586b9bb4fcf
SCRIPT_04_SHA256=0c44c1d7764f88c110d505e81e8dddfeefeeed25946cd2066ee93b04544e2347
SCRIPT_HASH_RECORD_COUNT=4
SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=4
SCRIPT_HASH_MISMATCH_COUNT=0
SCRIPT_HASH_MISSING_PATH_COUNT=0
STALE_SCRIPT_HASH_REFERENCE_COUNT=0
```

The hash members are complete repository-relative paths. No gate accepts
absolute paths, `..`, package-root escapes or cwd-based path guessing.

## Stop boundary

No 27th implementation path, existing-file modification, persistence,
migration, API, integration/PostgreSQL test, CI wiring, Ready, Merge, Round B
or Issue #102 closure is authorized.
