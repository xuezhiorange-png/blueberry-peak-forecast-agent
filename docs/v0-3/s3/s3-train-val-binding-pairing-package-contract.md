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
- Issued `TrainValidationCoveragePartitionAuthority` **record** in a trusted
  issued-authority registry (see §4)
- Issued `pairing_policy_version`
- Trusted published pairing-package registry (see §3.4)

**Repository state (not a pairing-package blocker)**

- `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true` on current main
  (`docs/v0-3/development-plan.md` §4.4). Coverage pairing packages do **not**
  require a versioned incumbent forecast artifact in repository; see §3.5.

### Q2 — Partition authority issuer

```text
PARTITION_AUTHORITY_ISSUER_EXISTS=false
```

`TrainValidationCoveragePartitionAuthority` is typed on main, but
`_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS` remains empty and the gate performs
**no** lookup of an issued authority record or published pairing package.
Caller-constructed dataclass instances are rejected with
`TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED`.

```text
SCHEMA_VERSION_ALLOWLIST_IS_NECESSARY_BUT_NOT_SUFFICIENT=true
CALLER_CONSTRUCTED_DATACLASS_IS_NEVER_SUFFICIENT=true
REGISTER_SCHEMA_VERSION != NON_FORGEABLE_AUTHORITY_ISSUANCE
```

Future implementation must verify a concrete
`IssuedTrainValidationCoverageAuthorityRecord` in a trusted registry (§4.2);
schema-version allowlisting alone is insufficient.

### Q3 — `pairing_package_identity` binding authorities

`pairing_package_identity` is derived from a **non-self-referential identity
preimage** (§3.2). The preimage MUST bind only authorities that exist on
current main:

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

### 3.2 Identity and canonical hash rules (non-self-referential)

Two distinct hashes are frozen. Neither hash field may appear in its own
preimage.

```text
PAIRING_PACKAGE_IDENTITY_EXCLUDED_OR_BLANKED_FROM_ITS_OWN_PREIMAGE=true
CANONICAL_HASH_EXCLUDED_OR_BLANKED_FROM_ITS_OWN_PREIMAGE=true
HASH_REPLAY_DETERMINISTIC=true
PAIRING_PACKAGE_IDENTITY_SELF_REFERENCE=false
```

**Step 1 — identity preimage**

Build `PAIRING_PACKAGE_IDENTITY_PREIMAGE` from the full semantic payload with
both hash fields blanked:

```text
PAIRING_PACKAGE_IDENTITY_PREIMAGE = semantic_payload where:
  pairing_package_identity = ""
  canonical_hash = ""
```

The identity preimage MUST include every authority field in §1 Q3 (excluding
only the two hash fields above).

**Step 2 — `pairing_package_identity`**

```text
pairing_package_identity =
  SHA256(canonical_json_bytes(PAIRING_PACKAGE_IDENTITY_PREIMAGE))
```

**Step 3 — final payload and `canonical_hash`**

Insert the computed `pairing_package_identity` into the semantic payload.
Build `CANONICAL_HASH_PREIMAGE` from the final semantic payload with only
`canonical_hash` blanked:

```text
CANONICAL_HASH_PREIMAGE = final_semantic_payload where:
  pairing_package_identity = <computed from Step 2>
  canonical_hash = ""
```

```text
canonical_hash =
  SHA256(canonical_json_bytes(CANONICAL_HASH_PREIMAGE))
```

**Stored package** carries the final `pairing_package_identity` and
`canonical_hash`. Replay MUST recompute both hashes in this order; any field
drift produces a new identity.

### 3.3 Pairing policy (frozen, not yet issued)

```text
PAIRING_POLICY_VERSION=v0-3-s3-b-train-val-binding-pairing-policy-v1
PAIRING_POLICY_STATUS=NOT_ISSUED_ON_MAIN
```

Until a future grant issues this policy version, no package may claim lawful
status.

### 3.4 Published pairing-package registry (definition only)

Lawful packages MUST be resolvable from a trusted, immutable/versioned
published pairing-package registry. This contract does **not** create the
registry.

```text
PAIRING_PACKAGE_IDENTITY_MUST_RESOLVE_TO_PUBLISHED_PACKAGE=true
TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY_NOT_PRESENT_ON_MAIN=true
```

**Resolution rule**

1. `pairing_package_identity` MUST exist as a published record in
   `TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY`
2. Stored package bytes MUST replay `canonical_hash` per §3.2
3. `evaluation_input.s2_binding_row_set_hash` MUST equal package
   `s2_binding_row_set_hash`
4. Package `partition` MUST be `TRAIN` or `VALIDATION` only

### 3.5 Forecast-side provenance (not artifact-required)

```text
VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED_FOR_COVERAGE_PAIRING=false
NO_VERSIONED_FORECAST_CONTRADICTION_RESOLVED=true
```

Current main binds forecast side via PIT incumbent authority, not via a
versioned in-repository artifact:

| Requirement | Authority on main |
| --- | --- |
| `forecast_authority_identity` | `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` (`backend/app/s3_daily_rowset/registry.py`) |
| `forecast_cutoff_authority_identity` | PIT-visible incumbent replay identity at historical cutoff (`s3_incumbent_forecast_replay_identity` contract family) |

`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true` is a repository
state fact. It is **not** a missing pairing-package prerequisite. Packages MUST
still bind both forecast authorities explicitly; issuance does not infer artifact
presence.

## 4. Partition authority issuance contract (definition only)

Future issuance produces an immutable
`IssuedTrainValidationCoverageAuthorityRecord` and registers it in
`TRUSTED_ISSUED_AUTHORITY_REGISTRY`. The existing
`TrainValidationCoveragePartitionAuthority` dataclass on main
(`backend/app/forecast_quality/quantile_coverage.py`) is a **carrier/handle**
only; it is never sufficient on its own.

```text
SCHEMA_VERSION_ALLOWLIST_IS_NECESSARY_BUT_NOT_SUFFICIENT=true
CALLER_CONSTRUCTED_DATACLASS_IS_NEVER_SUFFICIENT=true
AUTHORITY_RECORD_MUST_BIND_EXACT_PACKAGE_IDENTITY=true
```

### 4.1 Frozen issued authority record

```text
IssuedTrainValidationCoverageAuthorityRecord

authority_record_identity          # lowercase SHA-256; see §4.1.1
schema_version                     # e.g. v0.2-s3-train-val-coverage-partition-authority-v1
pairing_package_identity           # MUST match published package
s2_binding_row_set_hash            # MUST match package + evaluation_input
permitted_partitions               # ⊆ {TRAIN, VALIDATION}; TEST forbidden
pairing_policy_version             # MUST match published package
issuer_identity_or_version         # authorized issuer identity
canonical_hash                     # replay of full record bytes
```

#### 4.1.1 `authority_record_identity` rule

Same two-stage non-self-referential rule as §3.2:

```text
AUTHORITY_RECORD_IDENTITY_PREIMAGE = record_semantic_payload where:
  authority_record_identity = ""
  canonical_hash = ""

authority_record_identity =
  SHA256(canonical_json_bytes(AUTHORITY_RECORD_IDENTITY_PREIMAGE))

record_canonical_hash =
  SHA256(canonical_json_bytes(final_record_with_canonical_hash_blank))
```

### 4.2 Trusted issued-authority registry

```text
TRUSTED_ISSUED_AUTHORITY_REGISTRY_NOT_PRESENT_ON_MAIN=true
ISSUED_AUTHORITY_REGISTRY_RULE=
  immutable/versioned append-only registry of IssuedTrainValidationCoverageAuthorityRecord
  keyed by authority_record_identity
  publication requires explicit main-merge-authorized grant
  revocation/supersession by explicit deprecation grant only
```

**Execution verification rule (future implementation; not satisfied by #542
gate alone)**

```text
1. schema_version recognized in _ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS
2. authority_record ∈ TRUSTED_ISSUED_AUTHORITY_REGISTRY
3. authority_record_identity replays from stored record bytes
4. pairing_package_identity resolves to published lawful package (§3.4)
5. published package canonical_hash replays (§3.2)
6. package.s2_binding_row_set_hash == authority.s2_binding_row_set_hash
7. evaluation_input.s2_binding_row_set_hash == package.s2_binding_row_set_hash
8. package.partition ∈ authority.permitted_partitions
9. TEST absent from package and authority
```

Steps 2–9 are mandatory. Step 1 alone is insufficient.

### 4.3 WHO_ISSUES_AUTHORITY

```text
WHO_ISSUES_AUTHORITY=FUTURE_S3_B_PAIRING_PACKAGE_IMPLEMENTATION_AND_PARTITION_AUTHORITY_GRANT
CURRENT_ISSUER_EXISTS=false
```

Only a future authorized implementation slice may publish pairing packages,
register issued authority records, and (separately) register schema versions.
Ordinary callers, trial adapters, and catalog classifiers are **not** issuers.

### 4.4 ISSUANCE_PREREQUISITES

1. Published `TrainValidationS3BindingPairingPackage` for one partition
   (`TRAIN` or `VALIDATION`) present in `TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY`
   with replay-verified `canonical_hash` (§3.2)
2. `SOURCE_002_ROW_LEVEL_READ=true` and
   `LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=true` for the package's
   `source_dataset_identity`
3. `evaluation_input.s2_binding_row_set_hash` matches package binding
4. `forecast_authority_identity` and `forecast_cutoff_authority_identity`
   explicitly bound per §3.5 (`VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED_FOR_COVERAGE_PAIRING=false`)
5. `TEST_REMAINS_SEALED=true`; no TEST partition in package or authority
6. Explicit grant authorizing partition authority issuance (not this contract)

### 4.5 ISSUED_SCHEMA_REGISTRATION_RULE

```text
ISSUED_SCHEMA_MAY_BE_REGISTERED_ONLY_BY_EXPLICIT_MAIN_MERGE_AUTHORIZED_GRANT
FORBIDDEN_POPULATE_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS_IN_THIS_CONTRACT=true
SCHEMA_ALLOWLIST_SUFFICIENT_FOR_ISSUANCE=false
```

Registration of `schema_version` in `_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS`
is **necessary but not sufficient**. A separate authorized implementation PR
must also introduce (or bind to) `TRUSTED_ISSUED_AUTHORITY_REGISTRY` lookup.
This contract does **not** perform registration or create the registry.

### 4.6 REPLAY_VERIFICATION_RULE

1. Recompute package `canonical_hash` and `pairing_package_identity` per §3.2
2. Recompute `authority_record_identity` and record `canonical_hash` per §4.1.1
3. Verify registry membership for both package and authority record
4. Verify `evaluation_input.s2_binding_row_set_hash` matches authority and package
5. Verify every `S3BindingRow` satisfies coverage mask preconditions only after
   partition filter is applied
6. Verify `permitted_partitions` equals the package `partition` (single-partition
   packages) or explicit declared union for multi-package bundles (future)

### 4.7 REVOCATION_OR_VERSION_CHANGE_RULE

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

1. Future pairing-package producer publishes
   `TrainValidationS3BindingPairingPackage` to
   `TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY`
2. Future authority issuer publishes
   `IssuedTrainValidationCoverageAuthorityRecord` to
   `TRUSTED_ISSUED_AUTHORITY_REGISTRY`, bound to the published
   `pairing_package_identity` + `s2_binding_row_set_hash`
3. Future gate amendment requires `authority_record_identity` lookup and package
   resolution (§4.2 steps 1–9); caller-supplied
   `TrainValidationCoveragePartitionAuthority` alone is never sufficient
4. Gate remains fail-closed until package publication grant, authority registry
   grant, and schema registration grant land

Current execution blockers on main after PR #542:

```text
ACTUAL_EXECUTION_BLOCKER=NO_LEGAL_TRAIN_VALIDATION_S3_BINDING_PAIRING_PACKAGE
SECONDARY_AUTHORITY_GATE=TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED
```
