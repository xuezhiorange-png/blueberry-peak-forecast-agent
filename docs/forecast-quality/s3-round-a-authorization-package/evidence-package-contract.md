# Round A Evidence Package Contract

A future implementation review must include raw outputs for all four exact
acceptance scripts. A prose `PASS`, collection-only result or omitted stderr is
not evidence.

## Required facts

```text
AUTHORIZED_MANIFEST_RECORD_COUNT=26
AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=4
AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=0
AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=0
AUTHORIZED_TEST_MODULE_COUNT=17
AUTHORIZED_TEST_METADATA_LINE_COUNT=5
TEST_METADATA_PARSED_AS_MODULE_COUNT=0
INVALID_TEST_MODULE_RECORD_COUNT=0

SCRIPT_HASH_RECORD_COUNT=4
SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=4
SCRIPT_HASH_MISMATCH_COUNT=0
SCRIPT_HASH_MISSING_PATH_COUNT=0
STALE_SCRIPT_HASH_REFERENCE_COUNT=0
```

The SHA records are:

```text
ea64e802fbca112217d9ab07ae3e02b91d2d062b3e4a5ba99e371d8bb1b9eef0  docs/forecast-quality/s3-round-a-authorization-package/acceptance/01_changed_path_gate.sh
0fa3232ddeade11ef7b377d37f4ff95802e8854b525afc2c24e214e383ecb978  docs/forecast-quality/s3-round-a-authorization-package/acceptance/02_runtime_policy_audit.py
d4aba63856822fdf814adaa19a621223716b1073422abe3e81858586b9bb4fcf  docs/forecast-quality/s3-round-a-authorization-package/acceptance/03_test_gate.sh
0c44c1d7764f88c110d505e81e8dddfeefeeed25946cd2066ee93b04544e2347  docs/forecast-quality/s3-round-a-authorization-package/acceptance/04_static_gate.sh
```

All gates resolve script bytes only with:

```text
git show "${IMPLEMENTATION_BASE_SHA}:${repository_relative_path}"
```

Every member must start with
`docs/forecast-quality/s3-round-a-authorization-package/acceptance/`.
Absolute paths, `..`, other roots and cwd inference are forbidden.

## Runtime evidence

The runtime audit must execute—not merely print—daily metrics, forecast and
actual aggregation, breakdown, eight season-calendar cases, six baseline
fixtures, S3R-11 forbidden-source cases and requested P50/P80/P90 S3R-12
outcomes.

```text
INTERNAL_REASON_CODE_PRESENT=false
INTERNAL_REASON_CODE_MEMBER_COUNT=0
PUBLIC_INTERNAL_REASON_CODE_DISJOINT=true
BASELINE_CANONICAL_ROOT_FIELD_COUNT=26
BASELINE_CANONICAL_CELL_FIELD_COUNT=15
BASELINE_ROOT_FIELD_SET_EQUALITY=true
BASELINE_CELL_FIELD_SET_EQUALITY=true
BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0
FROZEN_VERSION_NAME_SET_EQUALITY=true
FROZEN_VERSION_VALUE_SET_EQUALITY=true
GENERIC_VERSION_BRANCH_SHADOW_COUNT=0
S3R12_EXECUTABLE_OUTCOME=true
```

Requested P80/P90 must produce:

```text
comparison_availability=BLOCKED
metric_status=NOT_COMPUTABLE
reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
baseline_point_forecast_kg=null
```

## Test evidence

The pytest gate records the complete node list and exact collected-module,
collected-test, passed, failed, error, skipped, xfailed, xpassed and exit
counts. All 17 authorized modules must exist and the directory may contain no
additional `test_*.py` module.

## Package self-test evidence

The package-level self-test must be run from the exact head and retain raw
stdout/stderr. It creates an isolated `/tmp` Git fixture and proves:

- legal 26-path manifest passes;
- legal 17-module manifest passes;
- metadata never enters arrays;
- wrong hash fails;
- missing script fails;
- blocked path fails;
- 27th path fails;
- baseline root drift fails;
- baseline cell drift fails;
- absent `InternalReasonCode` passes with zero members;
- wrong FrozenVersion fails.

```text
NEGATIVE_FIXTURE_UNEXPECTED_PASS_COUNT=0
PACKAGE_GATE_SELF_TEST_RESULT=PASS
PACKAGE_SELF_AUDIT_RESULT=PASS
```

Even all PASS results do not authorize implementation commit/push, Ready,
Merge, Round B or Issue #102 closure.
