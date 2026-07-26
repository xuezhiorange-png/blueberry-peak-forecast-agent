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
AUTHORIZED_MODIFY_EXISTING_PATH_COUNT=0
AUTHORIZED_DELETE_PATH_COUNT=0
DUPLICATE_AUTHORIZED_PATH_COUNT=0
PACKAGE_PATH_COUNT_DERIVED_NOT_COPIED_FROM_HISTORICAL_SUMMARY=true
AUTHORIZED_MANIFEST_RECORD_COUNT=26
AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=4
AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=0
AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=0
AUTHORIZED_TEST_METADATA_LINE_COUNT=5
TEST_METADATA_PARSED_AS_MODULE_COUNT=0
INVALID_TEST_MODULE_RECORD_COUNT=0
SCRIPT_HASH_RECORD_COUNT=4
SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=4
SCRIPT_HASH_MISMATCH_COUNT=0
SCRIPT_HASH_MISSING_PATH_COUNT=0
STALE_SCRIPT_HASH_REFERENCE_COUNT=0
SCRIPT_01_SHA256=464806cda8e86575c43d5b4297e97a9552c0e7109ed429076508ff7609895c3c
SCRIPT_02_SHA256=7157aaa0a302235227db2349d1f1db5e3eb635bb6bd87a8bd4ab7ddf86d6977e
SCRIPT_03_SHA256=56e24c5c5b28f9f823d1b7cbca5897a98b2c3a87655aea2a1905d56fa9626587
SCRIPT_04_SHA256=f3f6de562d397625bb5f5ea8e762211c0d3d975753a7950cad1eb97bfe14c32c
```

The complete path allocation and per-path requirements are in
`authorized-paths.txt`. No implementation path is allowed outside that file.
The future S3R-16 allocation includes both actual and forecast farm
aggregation; it does not add a path.

## Required domain API shape

The future implementation must expose the following pure, internal-domain
signatures. These are not HTTP APIs:

```text
compute_daily_metrics(evaluation_input: S3EvaluationInput, breakdown_spec: BreakdownSpec) -> DailyMetricResult
aggregate_daily_actuals(rows: Sequence[S3BindingRow]) -> Sequence[FarmDailyActualAggregate]
aggregate_daily_forecasts(rows: Sequence[S3BindingRow]) -> Sequence[FarmDailyForecastAggregate]
resolve_prior_season_analog_date(current_target_date, current_season_start, current_season_end, prior_season_start, prior_season_end, policy_version) -> date | None
resolve_baseline_point_forecast(request: BaselineRequest, source_snapshot: BaselineSourceSnapshot) -> BaselineResult
```

For `BaselineRequest.requested_quantile=P50`, the resolver returns the
point-only baseline. For `P80` and `P90`, it must return the executable
S3R-12 outcome `comparison_availability=BLOCKED`,
`metric_status=NOT_COMPUTABLE`,
`reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED`, and
`baseline_point_forecast_kg=null`; no point value may be copied across
quantiles. This is a Round A domain outcome, not a quality-metric publication.

`canonical.py` must expose `canonical_json_bytes`,
`compute_metric_input_mask_hash`, and `emit_s3_decimal`. All public symbols
have one owner in `public-symbol-owners.txt`; no module may re-export a
second definition under the same public name.

The canonical owner also exposes
`build_baseline_canonical_payload_root` and
`build_baseline_canonical_payload_cell` so the exact 26-field root and
15-field breakdown-cell contracts are runtime-verifiable.

`aggregate_daily_forecasts` groups exactly by
`season_business_key`, `farm_business_key`, `variety_business_key`, target
date, `forecast_cutoff_at`, `model_identity`, `forecast_quantile`, and
`forecast_horizon_days`. Its value is the sum of exact, deduplicated subfarm
forecast rows and its source keys are retained. It must reject duplicate
forecast business keys and must not merge quantiles, cutoffs, models, or
horizons. `aggregate_daily_actuals` independently deduplicates actual
physical rows; forecast and actual aggregates are never substituted for one
another.

## Test derivation

The 17 modules in `authorized-test-modules.txt` are domain-only tests mapped
to the non-blocked S3 requirements and the explicit architecture/blocked-
surface boundary. The test list is derived from the matrix requirements and
the two contract documents; it is not a claim that the tests currently exist.

```text
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

## F16-F20 corrective freeze

The Round A package fixes the following review boundaries without creating
implementation files:

```text
F16_BASELINE_NO_ANALOG_FIXTURE_FIXED=true
BASELINE_FIXTURE=no_analog_day|analog_date=None|status=NOT_COMPUTABLE|reason=NO_PRIOR_SEASON_ANALOG_DAY
BASELINE_FIXTURE=no_analog_actual|analog_date=<actual date>|status=NOT_COMPUTABLE|reason=NO_PRIOR_SEASON_ANALOG_ACTUAL
BASELINE_REQUEST_CALENDAR_BOUNDARY_OVERRIDES=true

F17_REAL_GATE_SELF_TEST=true
POSITIVE_GATE_EXECUTION_COUNT=4
POSITIVE_GATE_PASS_COUNT=4
NEGATIVE_GATE_EXECUTION_COUNT=10
NEGATIVE_EXPECTED_FAILURE_COUNT=10
NEGATIVE_UNEXPECTED_PASS_COUNT=0
PACKAGE_GATE_SELF_TEST_RESULT=PASS

F18_ALL_17_MODULES_COLLECT_TESTS=true
PYTEST_EXPECTED_MODULE_COUNT=17
PYTEST_COLLECTED_MODULE_COUNT=17
PYTEST_MODULE_WITH_ZERO_COLLECTED_TEST_COUNT=0
PYTEST_UNEXPECTED_COLLECTED_MODULE_COUNT=0

F19_ALL_PUBLIC_SCHEMAS_EXACT=true
PUBLIC_SCHEMA_COUNT=11
PUBLIC_SCHEMA_FIELD_SET_EQUALITY_COUNT=11
PUBLIC_SCHEMA_FIELD_ORDER_EQUALITY_COUNT=11
PUBLIC_SCHEMA_TYPE_EQUALITY_COUNT=11
PUBLIC_SCHEMA_REQUIREDNESS_EQUALITY_COUNT=11
PUBLIC_SCHEMA_DRIFT_COUNT=0
BASELINE_REQUEST_QUANTILE_FIELD=requested_quantile
BASELINE_REQUEST_FORECAST_QUANTILE_ALIAS_ALLOWED=false

F20_METRIC_STATUS_REASON_ORACLES=true
DAILY_METRIC_VALUE_ORACLE_COUNT=7
DAILY_METRIC_STATUS_ORACLE_COUNT=7
DAILY_METRIC_REASON_ORACLE_COUNT=7
DENOMINATOR_ZERO_RUNTIME_CASE_COUNT=3
DAILY_METRIC_ORACLE_FAILURE_COUNT=0
```

`01_changed_path_gate.sh` now builds a real temporary Git repository with a
package base commit, a positive 26-path implementation commit, and separate
adversarial clones. It invokes all four gate scripts through their normal
entrypoints. Expected non-zero cases include wrong or missing script blobs,
invalid manifest records, a 27th path, a blocked path, a zero-test module,
root/cell field drift, a wrong frozen version, and a blocked AST definition.
No string-only assertion, `seq` count, `bash -n`, or `py_compile` result is a
positive gate fixture.

The test gate derives `collected_modules` from recorded pytest node IDs and
requires exact equality with the 17 authorized modules. A module with no
collected node ID or an unexpected 18th module fails the gate. The runtime
gate executes all seven normal metrics and asserts `COMPUTED`/`NONE` status
and reason, plus the WAPE, relative-bias, and MAPE denominator-zero cases.
The 11-schema matrix, including exact order, type, requiredness, nullability,
default, canonical, and identity policy, is frozen in
`schema-enum-contract.md` and checked structurally by the runtime gate.
