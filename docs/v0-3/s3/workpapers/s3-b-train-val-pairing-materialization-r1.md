# V0.3-S3-B TRAIN/VALIDATION pairing materialization R1

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_TRAIN_VAL_PAIRING_MATERIALIZATION_R1
ARTIFACT_VERSION=s3-b-train-val-pairing-materialization-r1-v1
TASK_ID=V0_3_S3_B_TRAIN_VAL_PAIRING_MATERIALIZATION_R1
TASK_CLASS=CONTROLLED_PRODUCTION_IMPLEMENTATION_AND_REAL_MATERIALIZATION
AUTHORIZATION_SCOPE=V0_3_TRAIN_VALIDATION_PARTITION_SCOPED_S3_BINDING_PRODUCER+ROW_LEVEL_PARTITION_MEMBERSHIP_PROOF+EXACT_ACTUAL_PAIRING+HISTORICAL_CUTOFF_INCUMBENT_FORECAST_PAIRING+REAL_TRAIN_VALIDATION_S3_EVALUATION_INPUT_MATERIALIZATION+REAL_TRAIN_VALIDATION_PAIRING_PACKAGE_MATERIALIZATION
USER_GATE=可以
BASE_MAIN_SHA=624dab0642f17acc78a7e74c7cbd9707db8dfe45
REQUIRED_BASE_MAIN_SHA=624dab0642f17acc78a7e74c7cbd9707db8dfe45
MAIN_MATCHES_REQUIRED_BASE=true
MAIN_CONTAINS_PR547=true
PARENT_PR=547
PARENT_MERGE_COMMIT=624dab0642f17acc78a7e74c7cbd9707db8dfe45
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_TRAIN_VAL_PAIRING_MATERIALIZATION_RE_REVIEW
```

## Preflight

Fetched `origin/main` at `624dab0`. Matches required base SHA. PR #547 (dual pairing
policy issuance) is contained on main.

## Producer summary

Single production entry point:

```text
backend/app/forecast_quality/train_val_pairing_materialization.py
materialize_train_validation_pairing_inputs(...)
materialize_train_validation_pairing_inputs_live()
```

Pipeline:

```text
official SOURCE-002 TRAIN/VALIDATION content_bytes
  → parse_partition_bytes (canonical parser)
  → partition membership index + proofs
IncumbentForecastReplaySource.obtain()
  → reviewed P50/P80/P90 grains
  → IncumbentDailyCurveProvider via obtain_live_incumbent_forecast_daily_curve_provider()
  → s2_binding_key_hash forecast_business_key per row
  → S3BindingRow[] per partition
  → S3EvaluationInput (deterministic run/manifest/hash)
  → build_candidate_train_validation_pairing_package (issued policies)
  → validate + hash replay (not published)
```

### Reused authorities

| Component | Source |
| --- | --- |
| Actual partition bytes | `accepted_s2_train_val_source_002_row_level_read` + live obtain |
| Row parser | `s2_materialized_dataset/lane_d/canonical.py:parse_partition_bytes` |
| Forecast replay grains | `IncumbentForecastReplaySource.obtain()` |
| Reviewed grains | `s3_a2_coordinator_reviewed_live_origin_grain_identity_set` |
| Pairing package builder | `train_val_pairing.build_candidate_train_validation_pairing_package` |
| Forecast binding key | `rolling_backtest/signatures.py:s2_binding_key_hash` |
| Actual partition lookup | `(season,farm,subfarm,variety,target_date)` from official content |

### Partition membership proof

Each binding row with an actual carries `PartitionRowMembershipProof`:

```text
partition
source_partition_identity_sha256
source_partition_content_sha256
source_row_identity
```

Membership is derived from official partition content index lookup, not date-range
alone. Cross-partition `source_row_identity` overlap fails closed.

## Blocker remediation (re-review)

### Blocker 1 — live forecast value path

```text
LAWFUL_PIT_VISIBLE_INCUMBENT_DAILY_FORECAST_VALUE_SOURCE=NONE
ZERO_REAL_FORECAST_VALUES_CAN_COMPLETE_MATERIALIZATION=false
UNAVAILABLE_LIVE_PROVIDER_CAN_PRODUCE_PACKAGE=false
```

`obtain_live_incumbent_forecast_daily_curve_provider()` fail-closes until a production
PIT-visible adapter exists. Placeholder providers and zero comparable rows block with
`NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER` before package materialization.

### Blocker 2 — canonical S2 binding key

```text
ACTUAL_PARTITION_LOOKUP_KEY=(season,farm,subfarm,variety,target_date)
FORECAST_BINDING_KEY_AUTHORITY_SOURCE=backend/app/rolling_backtest/signatures.py:s2_binding_key_hash
```

Materialized `forecast_business_key` uses canonical `s2_binding_key_hash`, not a custom
pairing key shape.

## Live materialization attempt

Runtime call: `materialize_train_validation_pairing_inputs_live()`

```text
PRODUCER_IMPLEMENTED=true
REAL_MATERIALIZATION_COMPLETED=false
MATERIALIZATION_BLOCKER=SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
```

No bound live database session on this agent VM; attestation did not pass. No
package identities or binding rowset hashes were invented.

## Remaining blocked controls

```text
PAIRING_PACKAGE_PUBLICATION=false
PRODUCTION_PUBLISHED_PAIRING_PACKAGE_COUNT=0
PRODUCTION_ISSUED_PARTITION_AUTHORITY_RECORD_COUNT=0
ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSION_COUNT=0
S3_B_COVERAGE_EXECUTION=NOT_COMPUTABLE_OR_BLOCKED
TEST_REMAINS_SEALED=true
```

## Tests

`backend/tests/forecast_quality/test_s3_b_train_val_pairing_materialization_r1.py`
covers partition isolation, official hash fail-closed, membership proof, exact
pairing semantics, determinism, policy versions, empty replay blocker, and
production published registry remains empty.
