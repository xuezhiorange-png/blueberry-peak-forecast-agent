# V0.3-S3-B TRAIN/VALIDATION S3 Binding Pairing Package Contract

## Contract identity

```text
CONTRACT_ID=V0_3_S3_B_TRAIN_VAL_BINDING_PAIRING_PACKAGE_CONTRACT
CONTRACT_VERSION=v0-3-s3-b-train-val-binding-pairing-package-contract-v1
TASK_ID=V0_3_S3_B_TRAIN_VAL_BINDING_PAIRING_PACKAGE_CONTRACT_R1
TASK_CLASS=READ_ONLY_DISCOVERY_AND_CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_B_TRAIN_VALIDATION_PAIRING_PACKAGE_AND_PARTITION_AUTHORITY_CONTRACT_ONLY
ENGLISH_ID=TRAIN_VAL_S3_BINDING_PAIRING_PACKAGE
PARENT_PR=542
PARENT_MERGE_COMMIT=b8a825b2905c1c3b9c9a934a01af1e4917d4e67f
NO_STEP_IMPLIES_THE_NEXT=true
PRODUCTION_CODE_MUTATION=false
PAIRING_PACKAGE_IMPLEMENTATION=false
PARTITION_AUTHORITY_ISSUANCE=false
COVERAGE_EXECUTION=false
TEST_REMAINS_SEALED=true
```

This contract defines the **outer typed envelope** required to supply lawful
TRAIN/VALIDATION empirical coverage inputs to the frozen gate in
`backend/app/forecast_quality/quantile_coverage.py`. It does **not** modify
`S3EvaluationInput` and does **not** authorize implementation, issuance, or
execution.

## 1. Discovery verdict (current main)

### Q1 — Lawful `S3EvaluationInput` package status

```text
LAWFUL_S3_EVALUATION_INPUT_PACKAGE_STATUS=PARTIALLY_AVAILABLE
```

**Available on main**

- `S3EvaluationInput` and `S3BindingRow` schema
  (`backend/app/forecast_quality/schemas.py`)
- Frozen upper-quantile coverage calculator and fail-closed execution gate
  (`backend/app/forecast_quality/quantile_coverage.py`, merged PR #542)
- Accepted SOURCE_002 TRAIN/VALIDATION dataset and partition identities
  (`docs/v0-3/s3/s3-accepted-s2-train-val-lawful-origin-contract.md`)
- Live actuals binding and SOURCE_002 row-level read attestation
  (`backend/app/s3_daily_rowset/live_accepted_s2_train_val_actuals_source.py`,
  `backend/app/s3_daily_rowset/accepted_s2_train_val_source_002_row_level_read.py`)
- Evaluation-instance catalog/registry availability closeout
  (`docs/v0-3/development-plan.md` §4.4:
  `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`,
  `NO_BINDABLE_CATALOG_IN_REPOSITORY=false`)
- V0.2 trial-only producer that can build `S3EvaluationInput` from rolling
  backtest rows (`backend/app/trial.py`)

**Not available on main**

- Versioned TRAIN/VALIDATION `S3BindingRow` pairing package artifact
- V0.3 producer that binds `source-002/e5-live-v1` actuals + incumbent
  forecasts into one partition-scoped `S3EvaluationInput`
- Issued `TrainValidationCoveragePartitionAuthority`
- Versioned incumbent forecast artifact in repository
  (`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true` in
  `docs/v0-3/development-plan.md` §4.4)

### Q2 — Partition authority issuer

```text
PARTITION_AUTHORITY_ISSUER_EXISTS=false
```

`TrainValidationCoveragePartitionAuthority` is typed on main, but
`_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS` remains empty. Caller-constructed
dataclass instances are rejected with
`TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED`.

### Q3 — `pairing_package_identity` binding authorities

`pairing_package_identity` MUST be the lowercase SHA-256 of the package
canonical payload (with `canonical_hash=""` in the preimage). The preimage MUST
bind only authorities that exist on current main:

| Field | Canonical authority source |
| --- | --- |
| `source_dataset_identity` | `source-002` / `e5-live-v1` / `f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785` (`backend/app/s3_daily_rowset/schemas.py`) |
| `partition` | `TRAIN` or `VALIDATION` partition identity from lawful-origin contract §3 (`partition_identity_sha256`, `content_sha256`, date range) |
| `actuals_authority_identity` | `V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION` (`backend/app/s3_daily_rowset/registry.py`) |
| `forecast_authority_identity` | `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` (`backend/app/s3_daily_rowset/registry.py`) |
| `forecast_cutoff_authority` | PIT-visible incumbent replay identity at historical cutoff (`s3_incumbent_forecast_replay_identity`; port envelope handoff contract family) |
| `exact_actual_pairing_authority` | `EXACT_ACTUAL_PAIRED` per V0.2 §11.1–§11.3 / S3-B remediation contract |
| `s2_run_identity` | 64-hex S2 run identity for the binding producer run |
| `s2_manifest_identity` | 64-hex S2 manifest identity for the binding producer run |
| `s2_binding_row_set_hash` | 64-hex hash of the paired `S3BindingRow` set (must match `evaluation_input.s2_binding_row_set_hash`) |
| `pairing_policy_version` | Versioned pairing policy id (new; not yet issued on main) |

Fields MUST NOT reference invented hashes, TEST partitions, or V0.2 immutable
backtest bindings as lawful V0.3 origin.

## 2. Non-equivalent upstream families (do not conflate)

| Family | Path | Covers | Not equivalent because |
| --- | --- | --- | --- |
| `ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN` | `docs/v0-3/s3/s3-accepted-s2-train-val-lawful-origin-contract.md` | Dataset + partition hashes | No `S3BindingRow` pairing |
| `SOURCE_002_ROW_LEVEL_READ` | `accepted_s2_train_val_source_002_row_level_read.py` | Live byte/hash attestation | No forecast pairing |
| `LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE` | `live_accepted_s2_train_val_actuals_source.py` | Actuals port | No binding rows |
| `DEFAULT_CATALOG_LIVE_BINDABILITY` | `s3-default-catalog-live-bindability-and-registry-availability-contract.md` | Catalog/registry cells | Catalog ≠ binding package |
| `V0_2_TRIAL_S3_EVALUATION_INPUT` | `backend/app/trial.py` | Trial quality path | Not partition-scoped V0.3 lawful origin |

```text
EXISTING_EQUIVALENT_CANONICAL_FAMILY=false
```

## 3. Frozen outer envelope: `TrainValidationS3BindingPairingPackage`

`S3EvaluationInput` remains unchanged. Partition provenance and pairing
authority are carried in this outer envelope only.

```text
schema_version=v0-3-s3-b-train-val-binding-pairing-package-v1
pairing_package_identity=<sha256>
partition=TRAIN|VALIDATION

source_dataset_identity={
  dataset_id,
  dataset_version,
  materialized_dataset_identity_sha256
}

partition_identity={
  partition_name,
  partition_identity_sha256,
  content_sha256,
  partition_start_date,
  partition_end_date
}

s2_run_identity
s2_manifest_identity
s2_binding_row_set_hash

forecast_authority_identity
actuals_authority_identity
forecast_cutoff_authority_identity
exact_actual_pairing_policy_version
pairing_policy_version

evaluation_input=<S3EvaluationInput unchanged>
canonical_hash=<sha256>
```

### 3.1 Invariants

```text
partition ∈ {TRAIN, VALIDATION}
TEST forbidden

no cross-partition rows in one package
exact pairing required (EXACT_ACTUAL_PAIRED)
missing actual != zero (NOT_COMPUTABLE; never coerce)

row-set hash bound:
  package.s2_binding_row_set_hash == evaluation_input.s2_binding_row_set_hash

package identity deterministic from canonical payload
canonical replay possible
native float forbidden in evaluation_input rows
```

### 3.2 Identity rule

```text
pairing_package_identity = SHA256(canonical_json_bytes(payload_with_canonical_hash_blank))
```

The preimage MUST include every authority field in §1 Q3. Any field drift
produces a new `pairing_package_identity`.

### 3.3 Pairing policy (frozen, not yet issued)

```text
PAIRING_POLICY_VERSION=v0-3-s3-b-train-val-binding-pairing-policy-v1
PAIRING_POLICY_STATUS=NOT_ISSUED_ON_MAIN
```

Until a future grant issues this policy version, no package may claim lawful
status.

## 4. Partition authority issuance contract (definition only)

Future issuance produces `TrainValidationCoveragePartitionAuthority`
(`backend/app/forecast_quality/quantile_coverage.py`) with:

```text
schema_version=TRAIN_VAL_COVERAGE_PARTITION_AUTHORITY_SCHEMA_V1
pairing_package_identity
s2_binding_row_set_hash
permitted_partitions ⊆ {TRAIN, VALIDATION}
```

### 4.1 WHO_ISSUES_AUTHORITY

```text
WHO_ISSUES_AUTHORITY=FUTURE_S3_B_PAIRING_PACKAGE_IMPLEMENTATION_AND_PARTITION_AUTHORITY_GRANT
CURRENT_ISSUER_EXISTS=false
```

Only a future authorized implementation slice may register issued schema
versions and emit authority records bound to a published pairing package.
Ordinary callers, trial adapters, and catalog classifiers are **not** issuers.

### 4.2 ISSUANCE_PREREQUISITES

1. Published `TrainValidationS3BindingPairingPackage` for one partition
   (`TRAIN` or `VALIDATION`) with replay-verified `canonical_hash`
2. `SOURCE_002_ROW_LEVEL_READ=true` and
   `LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=true` for the package's
   `source_dataset_identity`
3. `evaluation_input.s2_binding_row_set_hash` matches package binding
4. `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY` may remain true;
   forecast authority must still be explicitly bound via
   `forecast_authority_identity` and cutoff authority — issuance does not infer
   artifact presence
5. `TEST_REMAINS_SEALED=true`; no TEST partition in package or authority
6. Explicit grant authorizing partition authority issuance (not this contract)

### 4.3 ISSUED_SCHEMA_REGISTRATION_RULE

```text
ISSUED_SCHEMA_MAY_BE_REGISTERED_ONLY_BY_EXPLICIT_MAIN_MERGE_AUTHORIZED_GRANT
FORBIDDEN_POPULATE_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS_IN_THIS_CONTRACT=true
```

Registration means adding the schema version string to
`_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS` in production code via a
separate authorized implementation PR. This contract does **not** perform
registration.

### 4.4 REPLAY_VERIFICATION_RULE

1. Recompute package `canonical_hash` from stored payload → must match
2. Recompute `pairing_package_identity` → must match
3. Verify `evaluation_input.s2_binding_row_set_hash` matches authority and
   package
4. Verify every `S3BindingRow` satisfies coverage mask preconditions only after
   partition filter is applied
5. Verify `permitted_partitions` equals the package `partition` (single-partition
   packages) or explicit declared union for multi-package bundles (future)

### 4.5 REVOCATION_OR_VERSION_CHANGE_RULE

A new `schema_version` or `pairing_policy_version` requires a new contract
amendment and grant. Prior issued schema versions remain valid only for packages
whose `pairing_policy_version` matches. Revocation is affected by publishing a
superseding package identity with an explicit deprecation grant; silent reuse is
forbidden.

## 5. Coverage wiring (frozen; no formula change)

```text
lawful TRAIN/VALIDATION source
        ↓
TrainValidationS3BindingPairingPackage (this contract)
        ↓
issued TrainValidationCoveragePartitionAuthority (future grant)
        ↓
assess_train_validation_coverage_execution()
        ↓
P50/P80/P90 upper coverage (quantile_coverage.py)
```

```text
COVERAGE_FORMULA_UNCHANGED=true
P*_UPPER_COVERAGE = count(actual <= forecast_q over mask) / denominator

COVERAGE_MASK_UNCHANGED=true
S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P* AND EXACT_ACTUAL_PAIRED

COVERAGE_REQUIRES_COMPLETE_DAILY_ROW_SET=false
COVERAGE_REQUIRES_VALID_PAIRING=true
```

Completeness verification (`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false`)
is **not** a prerequisite for coverage under this contract.

## 6. Bridge to PR #542 coverage gate

Minimal衔接 (no production change in this contract):

1. Future pairing-package producer emits `TrainValidationS3BindingPairingPackage`
2. Future authority issuer emits `TrainValidationCoveragePartitionAuthority`
   bound to `pairing_package_identity` + `s2_binding_row_set_hash`
3. Caller passes `evaluation_input` from the package envelope and the issued
   authority into `assess_train_validation_coverage_execution()`
4. Gate remains fail-closed until both package publication grant and authority
   issuance grant land

Current execution blockers on main after PR #542:

```text
ACTUAL_EXECUTION_BLOCKER=NO_LEGAL_TRAIN_VALIDATION_S3_BINDING_PAIRING_PACKAGE
SECONDARY_AUTHORITY_GATE=TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED
```
