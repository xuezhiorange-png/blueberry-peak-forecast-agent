# Round A Implementation Boundary

```text
PACKAGE_STATUS=PROPOSED_FOR_INDEPENDENT_REVIEW
ROUND_A_AUTHORIZATION_PACKAGE_COMPLETE=true
ROUND_A_AUTHORIZATION_PACKAGE_ACCEPTED=false
ROUND_A_IMPLEMENTATION_AUTHORIZED=false
COMMIT_IMPLEMENTATION_AUTHORIZED=false
PUSH_IMPLEMENTATION_AUTHORIZED=false
OPEN_IMPLEMENTATION_PR_AUTHORIZED=false
ROUND_B_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## Authority and provenance

The source is the current `origin/main` at:

```text
PACKAGE_SOURCE_MAIN_SHA=4d7effe82c61e5fbd6ddcc22eefa61ab74a6663d
IMPLEMENTATION_BASE_SHA=NOT_BOUND_PENDING_PACKAGE_ACCEPTANCE_AND_MERGE
IMPLEMENTATION_BASE_BOUND_BY_THIS_PR=false
IMPLEMENTATION_BASE_REQUIRES_SEPARATE_CHARLES_AUTHORIZATION=true
PACKAGE_SOURCE_SHA_IS_IMPLEMENTATION_BASE=false
SOURCE_DESIGN_HEAD_SHA=c2fb3415dfdf6cb214cb7c2f246dc442e57778a9
PR131_MERGE_COMMIT_IS_ANCESTOR=true
PR131_DESIGN_DOCUMENT_COUNT=3
S3_IMPLEMENTATION_AUTHORIZED_BY_PR131=false
```

The three design documents are the only design authority. No prior report,
chat summary, temporary directory, review comment, implementation hash, or
historical path count is an authorization source.

`PACKAGE_SOURCE_MAIN_SHA` identifies the source used to author this package;
it is not a future implementation diff base. A future implementation round
must receive an exact `IMPLEMENTATION_BASE_SHA` from Charles after this
package is independently accepted and merged. The acceptance scripts require
that bound commit to be an ancestor of the implementation worktree, contain
this package, and carry the exact package script hashes.

## Round A boundary

```text
ROUND_A_IS_DOMAIN_ONLY=true
ROUND_A_POSTGRES_REQUIRED=false
ROUND_A_MIGRATION_REQUIRED=false
ROUND_A_CONCURRENCY_REQUIRED=false
ROUND_A_PUBLIC_HTTP_API=false
ROUND_A_FULL_S3_ACCEPTANCE_POSSIBLE=false
REAL_DATA_EXECUTION=false
ISSUE102_MUTATION=false
```

Authorized domain behavior:

- public schemas, enums, and the public exception hierarchy;
- Decimal-only arithmetic with `0.000001` quantum and final-boundary
  `ROUND_HALF_EVEN` rounding;
- canonical JSON and metric-input-mask hashes;
- P50 daily MAE, WAPE, sMAPE, MAPE, bias, relative bias, and absolute-error
  sum;
- deterministic six-axis breakdown cells and minimum-sample status;
- cross-quantile P50/P80/P90 forecast-row retention with one actual physical
  row per physical grain;
- subfarm-to-farm daily forecast and actual aggregation after exact deduplication;
- current-season to prior-season analog-date resolution, including the
  frozen Feb-29 to prior-Feb-28 rule;
- point-only prior-season analog baseline and current-cutoff visibility;
- immutable-in-memory canonical payloads and fail-closed structural errors.

Explicitly excluded surfaces:

```text
COMPLETE_WINDOW_CUMULATIVE_METRICS=false
SINGLE_DAY_PEAK=false
SUSTAINED_7DAY_PEAK=false
QUANTILE_COVERAGE_PUBLICATION=false
PINBALL_LOSS_PUBLICATION=false
PREDICTION_INTERVALS=false
MODEL_BASELINE_COMPARISON_PERSISTENCE=false
PERSISTENCE=false
REPOSITORY=false
APPLICATION_SERVICE=false
ORM=false
MIGRATION=false
HTTP_API=false
INTEGRATION_TESTS=false
POSTGRES_TESTS=false
CONCURRENCY_TESTS=false
CI_WIRING=false
FRONTEND=false
```

The future implementation must not add a `peak.py`, `quantile.py`,
`comparison.py`, `persistence.py`, repository, application, ORM, migration,
API, integration test, or CI path in this round. Absence of these surfaces is
checked by `acceptance/02_runtime_policy_audit.py` and
`acceptance/04_static_gate.sh`.

The public `ReasonCode` member
`PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE` is a closed-contract status
token, not an implemented prediction-interval surface. Gate 23 scans AST
function/method/class definitions only. It therefore rejects blocked
implementation definitions while allowing reason-code members, contract
state declarations, and negative-test assertions:

```text
BLOCKED_IMPLEMENTATION_DEFINITION_COUNT=0
REASON_CODE_FALSE_POSITIVE_COUNT=0
GATE_21_GATE_23_CONTRADICTION_COUNT=0
```

## Path derivation

The path allocation is the minimal coherent allocation for the explicit
Round A concerns in the three design documents. `schemas.py`, `enums.py`,
and `exceptions.py` own public contract declarations; `canonical.py` owns
identity and Decimal policy; the remaining files own the named domain
behaviors. The matrix's named owner paths are retained for those behaviors.

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
SCRIPT_01_SHA256=11242ef9a548140fd0c9af74614782fbe5298704edf932f587895968196bcd82
SCRIPT_02_SHA256=e3df38dd1fce67cd441e98e8933080b995320a3a6961f07da7027b27fc4366cb
SCRIPT_03_SHA256=1b229e80129d876836747b1aefb1e13f8b71202f5546fb2a5aebf54a1341575f
SCRIPT_04_SHA256=c7112a42cd20ebfac855f96997084c92cd91ff47bf58b7ea317d031c1534fdb0
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
TEST_REQUIREMENT_WITHOUT_OWNER_COUNT=0
TEST_MODULE_WITHOUT_REQUIREMENT_COUNT=0
ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT=0
S3R11_TEST_OWNER_PRESENT=true
S3R12_TEST_OWNER_PRESENT=true
S3R12_ROUND_A_STATUS=IMPLEMENTED_DOMAIN_OUTCOME
S3R12_IMPLEMENTED_BY_ROUND_A=true
S3R12_RUNTIME_AUDIT_CLAIM=true
BASELINE_CANONICAL_ROOT_FIELD_COUNT=26
BASELINE_CANONICAL_CELL_FIELD_COUNT=15
BASELINE_ROOT_FIELD_SET_EQUALITY=true
BASELINE_CELL_FIELD_SET_EQUALITY=true
BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0
```

`test_baseline.py` owns S3R-11 red-source rejection and S3R-12 point-only
baseline semantics. `test_baseline_visibility.py` owns cutoff visibility and
the shared S3R-11 late-revision cases. These are executable owner mappings,
not prose-only coverage claims.

The package gate's `PACKAGE_SELF_TEST=1` mode is part of the acceptance
contract. It must report positive and expected-negative fixtures for manifest
metadata parsing, script hash failures, blocked paths, a 27th path, baseline
root/cell field drift, absent `InternalReasonCode`, and invalid frozen policy
values, ending with `PACKAGE_GATE_SELF_TEST_RESULT=PASS`.

No collection-only result is acceptance evidence. The test gate must execute
pytest and record its complete node and outcome counts.

## Implementation stop conditions

The future implementer must stop without broadening scope if any of these is
needed: an existing-file modification, a deleted/renamed path, persistence,
an integration or PostgreSQL test, a migration, an API, CI wiring, a model
change, a real-data source, or a 27th path. Such a request requires a new
independent authorization. This package does not authorize commit, push,
Draft PR creation for implementation, Ready, Merge, Round B, or Issue #102
closure.

## Acceptance relationship

Passing the package scripts only proves that a future implementation stayed
inside this declared domain boundary and exercised the declared tests. It
does not prove full S3 acceptance. Complete-window metrics and all persistence
and PostgreSQL obligations remain outside Round A.

```text
ROUND_A_DOMAIN_IMPLEMENTATION_ACCEPTANCE_REQUIRES_INDEPENDENT_REVIEW=true
ROUND_A_FULL_S3_ACCEPTANCE=false
ROUND_B_PERSISTENCE_REQUIRED=true
PUBLIC_REASON_CODE_MEMBER_COUNT=16
PUBLIC_REASON_CODE_CLOSED_SET_EQUALITY=true
BLOCKED_IMPLEMENTATION_DEFINITION_COUNT=0
REASON_CODE_FALSE_POSITIVE_COUNT=0
GATE_21_GATE_23_CONTRADICTION_COUNT=0
CI_TEST_EVIDENCE_REQUIRES_REAL_RUNTIME_OUTPUT=true
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
NEGATIVE_GATE_EXECUTION_COUNT=37
NEGATIVE_EXPECTED_FAILURE_COUNT=37
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

## F21-F25 corrective freeze

The exact-head static failure was caused by package Python diagnostics in
`acceptance/02_runtime_policy_audit.py`. The corrective gate requires root
Ruff and mypy checks, not a narrowed backend-only substitute:

```text
ROOT_RUFF_CHECK_COMMAND=uv run ruff check .
ROOT_RUFF_FORMAT_CHECK_COMMAND=uv run ruff format --check .
ROOT_MYPY_COMMAND=uv run mypy backend/app
ROOT_RUFF_CHECK_EXIT_CODE=0
ROOT_RUFF_FORMAT_CHECK_EXIT_CODE=0
ROOT_MYPY_EXIT_CODE=0
PACKAGE_PYTHON_RUFF_PATH_COUNT=1
```

`BreakdownSpec` is exactly six business axes. The breakdown module owns the
fixed threshold of ten; callers cannot provide `minimum_sample_size`:

```text
BreakdownSpec_FIELD_COUNT=6
REQUIRED_BREAKDOWN_AXIS_COUNT=6
MIN_COMPARABLE_ROWS_FOR_REPORTING_OWNER=backend.app.forecast_quality.breakdown
MIN_COMPARABLE_ROWS_FOR_REPORTING_VALUE=10
CALLER_CONFIGURABLE_MINIMUM_SAMPLE_SIZE=false
```

The package chooses explicit source-object baseline canonical builders. The
root and cell builders require exact 26/15 sections, reject caller-injected
final mappings, and validate a 41-record machine-readable source map. Each
record contains canonical field, source schema, source field, nullable rule,
sentinel rule, and identity participation. Canonical bytes, SHA256 and replay
identity are recomputed; all-null, identity, visibility, counter, mask and
breakdown drift are rejected.

BASELINE_CANONICAL_SOURCE_MAP_RECORD_COUNT=41

`DailyMetricResult.mape_zero_actual_reason_code` is the single serialized
owner of the MAPE zero-row reason. Mixed eligible/zero rows remain
`COMPUTED/NONE`; all-zero input is
`NOT_COMPUTABLE/NO_MAPE_ELIGIBLE_ROWS` while retaining
`MAPE_DENOMINATOR_ZERO` as the row-level reason. The full result envelope
binds S2 identities, policy versions, counters, coverage, P50 input, exact
six-axis breakdown, independent mask hash and full canonical hash.

```text
F21_ROOT_STATIC_GATE_FIXED=true
F22_BREAKDOWNSPEC_SIX_FIELDS_FIXED=true
F23_BASELINE_CANONICAL_PROVENANCE_FIXED=true
F24_MAPE_ZERO_ROW_REASON_FIXED=true
F25_DAILY_RESULT_ENVELOPE_FIXED=true
```

## Round 5 corrective freeze

```text
F26_COMPLETE_PACKAGE_TREE_IDENTITY=true
AUTHORIZATION_PACKAGE_EXPECTED_FILE_COUNT=12
AUTHORIZATION_PACKAGE_ACCEPTED_FILE_COUNT=12
AUTHORIZATION_PACKAGE_BASE_FILE_COUNT=12
AUTHORIZATION_PACKAGE_CURRENT_FILE_COUNT=12
AUTHORIZATION_PACKAGE_CURRENT_WORKTREE_DRIFT_COUNT=0
AUTHORIZATION_PACKAGE_FILE_SET_MISMATCH_COUNT=0
F27_CANONICAL_REAL_SOURCE_PROVENANCE=true
BASELINE_CANONICAL_BUILDER_INPUT=SOURCE_OBJECTS_ONLY
BASELINE_CANONICAL_CALLER_INJECTION_SURFACE_COUNT=0
BASELINE_CANONICAL_SOURCE_MAP_RECORD_COUNT=41
BASELINE_CANONICAL_PROVENANCE_MUTATION_FAILURE_COUNT=0
BASELINE_SCHEMA_VERSION=v0.2-s3-baseline-v1
BASELINE_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE
BASELINE_HORIZON_RULE=TARGET_DATE_ENCODES_HORIZON
F28_CANONICAL_CONDITIONAL_NULLABILITY=true
BASELINE_CANONICAL_NULLABILITY_RULE_COUNT=5
BASELINE_CANONICAL_NULLABILITY_MISMATCH_COUNT=0
F29_DAILY_RESULT_MASK_POLICY_VERSION=true
DAILY_RESULT_ENVELOPE_FIELD_COUNT=21
DAILY_RESULT_MASK_POLICY_VERSION_PRESENT=true
DAILY_RESULT_MASK_POLICY_VERSION_VALUE=v0.2-s3-metric-input-mask-v1
DAILY_RESULT_MASK_POLICY_VERSION_MISMATCH_COUNT=0
F30_ALL_COLLECTED_TESTS_MUST_PASS=true
PYTEST_MODULE_WITH_ZERO_PASSED_TEST_COUNT=0
PYTEST_NONPASSING_MODULE_COUNT=0
PYTEST_ALL_COLLECTED_TESTS_PASSED=true
F31_STATIC_SUPPRESSIONS_FORBIDDEN=true
FILE_WIDE_MYPY_IGNORE_COUNT=0
FILE_WIDE_RUFF_NOQA_COUNT=0
BARE_TYPE_IGNORE_COUNT=0
BARE_NOQA_COUNT=0
TARGETED_TYPE_IGNORE_COUNT=0
TARGETED_NOQA_COUNT=0
F32_SINGLE_CURRENT_STATE_BLOCK=true
CURRENT_ROOT_RUFF_FAILED_PATH_COUNT=0
CURRENT_ROOT_RUFF_DIAGNOSTIC_COUNT=0
```

The baseline canonical builders accept only their declared source objects and
frozen constants. They reject preassembled root/cell mappings, preserve
explicit conditional JSON nulls, and bind every canonical field to a real
source schema field or named constant. All gates require the accepted package
commit/tree, implementation base, implementation worktree, and package
directory as explicit parameters.
