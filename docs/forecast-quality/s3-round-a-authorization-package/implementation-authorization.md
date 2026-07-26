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
- subfarm-to-farm daily actual aggregation after exact deduplication;
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
```

`test_baseline.py` owns S3R-11 red-source rejection and S3R-12 point-only
baseline semantics. `test_baseline_visibility.py` owns cutoff visibility and
the shared S3R-11 late-revision cases. These are executable owner mappings,
not prose-only coverage claims.

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
