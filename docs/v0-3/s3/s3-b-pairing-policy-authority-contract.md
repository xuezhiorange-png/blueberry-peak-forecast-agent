# V0.3-S3-B TRAIN/VALIDATION Pairing Policy Authority Contract

## Contract identity

```text
CONTRACT_ID=V0_3_S3_B_PAIRING_POLICY_AUTHORITY_CONTRACT
CONTRACT_VERSION=v0-3-s3-b-pairing-policy-authority-contract-v1
TASK_ID=V0_3_S3_B_PAIRING_POLICY_AUTHORITY_CONTRACT_R1
TASK_CLASS=READ_ONLY_DISCOVERY_AND_CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_B_PAIRING_POLICY_AND_EXACT_ACTUAL_PAIRING_POLICY_AUTHORITY_CONTRACT_ONLY
ENGLISH_ID=S3_B_PAIRING_POLICY_AUTHORITY
PARENT_PR=544
PARENT_MERGE_COMMIT=66ae5601865ff483e73f962431c21e02f2af2a69
NO_STEP_IMPLIES_THE_NEXT=true
PRODUCTION_CODE_MUTATION=false
PAIRING_POLICY_ISSUANCE=false
EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE=false
ISSUED_POLICY_ALLOWLIST_MUTATION=false
PAIRING_PACKAGE_PRODUCER_IMPLEMENTATION=false
REAL_PAIRING_PACKAGE_MATERIALIZATION=false
REAL_PAIRING_PACKAGE_PUBLICATION=false
AUTHORITY_RECORD_ISSUANCE=false
SCHEMA_VERSION_REGISTRATION=false
COVERAGE_EXECUTION=false
TEST_REMAINS_SEALED=true
```

This contract freezes **what pairing policies may be formally issued**, **who may
issue them**, and **how issued policy versions are referenced by pairing
packages**. It does **not** issue any policy version, populate any production
allowlist, materialize pairing packages, or authorize Coverage execution.

Parent infrastructure (merged PR #544) provides typed envelopes, trusted
registries, and fail-closed verification hooks. Policy **semantics** and policy
**version issuance** remain distinct layers.

## 1. Discovery verdict (current main)

### 1.1 Preflight

```text
BASE_MAIN_SHA=66ae5601865ff483e73f962431c21e02f2af2a69
REQUIRED_BASE_MAIN_SHA=66ae5601865ff483e73f962431c21e02f2af2a69
MAIN_MATCHES_REQUIRED_BASE=true
MAIN_CONTAINS_PR544=true
```

### 1.2 Current-main policy constants

| Constant | Value on main | Status |
| --- | --- | --- |
| `TRAIN_VAL_PAIRING_PACKAGE_SCHEMA_V1` | `v0-3-s3-b-train-val-binding-pairing-package-v1` | DEFINED |
| `TRAIN_VAL_PAIRING_POLICY_V1` | `v0-3-s3-b-train-val-binding-pairing-policy-v1` | DEFINED, NOT_ISSUED |
| `FROZEN_EXACT_ACTUAL_PAIRING_RULE` | `EXACT_ACTUAL_PAIRED` | SEMANTICS_FROZEN |
| `EXISTING_VERSIONED_EXACT_ACTUAL_PAIRING_POLICY_ID` | `NOT_AVAILABLE` | — |
| `_ISSUED_PAIRING_POLICY_VERSIONS` | `frozenset()` | EMPTY |
| `ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS` | `frozenset()` | EMPTY |
| `_ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSIONS` | `frozenset()` | EMPTY |
| `PRODUCTION_PUBLISHED_PACKAGE_COUNT` | `0` | — |
| `PRODUCTION_ISSUED_AUTHORITY_RECORD_COUNT` | `0` | — |

Sources:

- `backend/app/forecast_quality/train_val_pairing.py`
- `backend/app/forecast_quality/train_val_trusted_registry.py`
- `backend/app/forecast_quality/quantile_coverage.py`

### 1.3 Equivalent policy-authority family check

```text
EXISTING_EQUIVALENT_POLICY_AUTHORITY_FAMILY=false
```

Related but **non-equivalent** families:

| Family | Path | Covers | Not equivalent because |
| --- | --- | --- | --- |
| `TRAIN_VAL_PAIRING_PACKAGE` | `docs/v0-3/s3/s3-train-val-binding-pairing-package-contract.md` | Package envelope + partition authority issuance | Names `pairing_policy_version` and `exact_actual_pairing_policy_version` fields but does not freeze unified policy issuance authority |
| `S3_B_QUANTILE_SEMANTICS_REMEDIATION` | `docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md` | `EXACT_ACTUAL_PAIRED` semantic authority | Semantics only; no versioned policy ID or issuance registry |
| `V0_2_S3_QUALITY_METRICS` | `docs/forecast-quality/s3-quality-metrics-contract.md` §11.1–§11.3 | Coverage mask pairing predicate | Metric contract; not S3-B policy issuance |
| `PAIRING_PACKAGE_INFRA` | `backend/app/forecast_quality/train_val_pairing.py` | Constants + verification hooks | Infrastructure; empty issued-policy sets |

No second authority system is introduced. This contract **extends** the pairing
package contract family with a dedicated policy-issuance layer.

## 2. Policy semantics vs policy version issuance

```text
POLICY_CONSTANT_EXISTENCE != POLICY_ISSUANCE
CALLER_DEFINED_VERSION_STRING_IS_NOT_AUTHORITY=true
CONTRACT_DEFINED_BUT_NOT_ISSUED_POLICY_IS_NOT_EXECUTABLE=true
ISSUANCE_REQUIRES_EXPLICIT_FUTURE_GRANT=true
```

A string constant or contract definition does **not** imply the policy is issued.
Production execution requires membership in an explicit issued-policy registry /
allowlist updated only by a future authorized grant.

## 3. Frozen exact-actual pairing semantics (`EXACT_ACTUAL_PAIRED`)

### 3.1 Semantic rule (frozen; not a version ID)

```text
FROZEN_EXACT_ACTUAL_PAIRING_RULE=EXACT_ACTUAL_PAIRED
```

`EXACT_ACTUAL_PAIRED` is the **semantic rule name**. It is **not** a versioned
policy ID and is **not** sufficient alone for published package execution.

### 3.2 Authoritative semantic sources (current main)

| Authority | Path | Binding |
| --- | --- | --- |
| V0.2 pairing section | `docs/forecast-quality/s3-quality-metrics-contract.md` §11.1–§11.3 | Cross-quantile actual reuse; coverage masks |
| S3-B remediation | `docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md` §3.2 | `FINAL_TARGET_PAIRING_RULE` |
| S3-B quantile semantics | `docs/v0-3/s3/s3-quantile-semantics-contract.md` §3 | `P*_COVERAGE_MASK` predicates |
| Production predicate | `backend/app/forecast_quality/quantile_coverage.py` `_is_exact_actual_paired()` | Runtime mask gate (unchanged) |
| Pairing package contract | `docs/v0-3/s3/s3-train-val-binding-pairing-package-contract.md` §3.1 | Package invariant: exact pairing required |

### 3.3 Frozen semantic requirements

```text
forecast row must have exact actual physical pairing

actual_physical_key != null
stable_actual_identity != null

forecast_value_kg != null
actual_value_kg != null

native float forbidden

missing actual != zero
missing/invalid pair => excluded from exact-paired mask / NOT_COMPUTABLE

one physical actual may lawfully pair to corresponding
P50/P80/P90 forecast rows at the same governed physical grain

TEST remains sealed
```

```text
COVERAGE_MASK_UNCHANGED=true
COVERAGE_FORMULA_UNCHANGED=true
```

This contract does **not** alter `P*_COVERAGE_MASK` or
`_is_exact_actual_paired()` behavior.

## 4. Versioned exact-actual pairing policy ID

### 4.1 Discovery

```text
EXISTING_VERSIONED_EXACT_ACTUAL_PAIRING_POLICY_ID=NOT_AVAILABLE
REUSE_EXISTING_ID=false
```

Current main contains **no** canonical issued exact-actual policy version ID.
The previously removed identifier `v0-2-exact-actual-paired-v1` does **not**
appear anywhere on current main and is **not** resurrected.

### 4.2 Proposed canonical version ID (defined only; not issued)

```text
PROPOSED_EXACT_ACTUAL_PAIRING_POLICY_VERSION=v0-3-s3-b-exact-actual-pairing-policy-v1
EXACT_ACTUAL_PAIRING_POLICY_VERSION_DEFINED=true
EXACT_ACTUAL_PAIRING_POLICY_VERSION_ISSUED=false
```

Naming rationale:

- Prefix `v0-3-s3-b-` aligns with S3-B TRAIN/VALIDATION pairing family
- Scope `exact-actual-pairing` distinguishes from general binding pairing policy
- Suffix `-v1` matches repository version naming conventions
- Does **not** impersonate any V0.2 issued policy constant

Until a future issuance grant registers this ID in
`ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS`, packages referencing it remain
non-executable at the published/execution boundary
(`TRAIN_VALIDATION_EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED`).

## 5. General TRAIN/VALIDATION pairing policy

### 5.1 Frozen version identity (do not rename)

```text
TRAIN_VAL_PAIRING_POLICY_VERSION=v0-3-s3-b-train-val-binding-pairing-policy-v1
PAIRING_POLICY_VERSION_DEFINED=true
PAIRING_POLICY_VERSION_ISSUED=false
```

Constant: `TRAIN_VAL_PAIRING_POLICY_V1` in `train_val_pairing.py`.
Parent contract §3.3: `PAIRING_POLICY_STATUS=NOT_ISSUED_ON_MAIN`.

### 5.2 Semantic boundary

The general pairing policy governs the **outer envelope** binding rules for one
`TRAIN` or `VALIDATION` partition-scoped package:

```text
TRAIN/VALIDATION only
TEST forbidden

canonical source-002/e5-live-v1 authority

canonical TRAIN or VALIDATION partition identity

V0_3_S3_ACTUALS_AUTHORITY binding

V0_3_S3_FORECASTS_AUTHORITY binding

forecast cutoff authority required

exact-actual policy version required (at published/execution boundary)

S2 run identity bound

S2 manifest identity bound

S2 binding row-set hash bound

evaluation_input identity fields exactly match envelope

canonical deterministic hash replay

no silent sort / dedupe / zero-fill / partition substitution
```

Canonical authority bindings on main:

| Field | Authority |
| --- | --- |
| `source_dataset_identity` | `source-002` / `e5-live-v1` / materialized hash (`schemas.py`) |
| `partition_identity` | Lawful-origin TRAIN/VALIDATION (`s3-accepted-s2-train-val-lawful-origin-contract.md`) |
| `actuals_authority_identity` | `V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION` |
| `forecast_authority_identity` | `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` |
| `forecast_cutoff_authority_identity` | PIT incumbent replay identity (port envelope handoff family) |

## 6. Policy issuance authority (definition only)

### 6.1 Issuers

```text
WHO_ISSUES_PAIRING_POLICY=FUTURE_S3_B_PAIRING_POLICY_ISSUANCE_GRANT
WHO_ISSUES_EXACT_ACTUAL_PAIRING_POLICY=FUTURE_S3_B_EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE_GRANT
CURRENT_PAIRING_POLICY_ISSUER_EXISTS=false
CURRENT_EXACT_ACTUAL_POLICY_ISSUER_EXISTS=false
```

Only a future **main-merge-authorized grant** may:

1. Register a policy version in the production issued-policy allowlist
2. Publish immutable issuance metadata (issuer identity, effective date, scope)
3. Authorize downstream package producers to reference the issued version

Ordinary callers, trial adapters, test helpers, and infrastructure builders are
**not** issuers. Candidate packages may carry version strings for structural
testing; that does **not** constitute issuance.

### 6.2 Issuance prerequisites

**General pairing policy (`v0-3-s3-b-train-val-binding-pairing-policy-v1`)**

```text
PAIRING_POLICY_ISSUANCE_PREREQUISITES=
  1. This contract merged and coordinator-reviewed
  2. Pairing package infrastructure landed (PR #544)
  3. Exact-actual pairing semantics frozen (§3; unchanged from V0.2/S3-B)
  4. Explicit S3_B_PAIRING_POLICY_ISSUANCE grant (separate from this contract)
  5. Issued-policy registry/allowlist implementation authorized
  6. No TEST partition exposure; TEST_REMAINS_SEALED=true
```

**Exact-actual pairing policy (`v0-3-s3-b-exact-actual-pairing-policy-v1`)**

```text
EXACT_ACTUAL_POLICY_ISSUANCE_PREREQUISITES=
  1. General pairing policy issuance prerequisites (items 1–3, 6)
  2. PROPOSED_EXACT_ACTUAL_PAIRING_POLICY_VERSION coordinator-approved
  3. Semantic traceability to V0.2 §11.1–§11.3 verified (no mask change)
  4. Explicit S3_B_EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE grant
  5. Registration in ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS authorized
  6. Published package verifier enforces membership (PR #544 hook present)
```

Issuance of the exact-actual policy may proceed **independently** of general
pairing policy issuance timing, but **both** must be issued before lawful
published package execution.

### 6.3 Policy version registration rule

```text
POLICY_VERSION_REGISTRATION_RULE=
  immutable append-only issued-policy registry or production frozenset
  keyed by policy version string
  registration requires explicit main-merge-authorized grant
  no silent population of _ISSUED_PAIRING_POLICY_VERSIONS or
    ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS in contract or infra PRs
  contract-defined constants are necessary but not sufficient for execution
```

### 6.4 Policy replay verification rule

```text
POLICY_REPLAY_VERIFICATION_RULE=
  1. Published package pairing_policy_version ∈ _ISSUED_PAIRING_POLICY_VERSIONS
  2. Published package exact_actual_pairing_policy_version non-empty
     AND ∈ ISSUED_EXACT_ACTUAL_PAIRING_POLICY_VERSIONS
  3. Issued authority record pairing_policy_version matches published package
  4. Verifier rejects empty or caller-crafted unissued version strings
  5. Candidate structural validation may allow empty exact policy; published path may not
```

Implemented hook (infrastructure only; production sets empty):
`verify_train_validation_coverage_authority()` in
`train_val_trusted_registry.py`.

### 6.5 Policy revocation or supersession rule

```text
POLICY_REVOCATION_OR_SUPERSESSION_RULE=
  new policy version requires new contract amendment + explicit grant
  prior issued versions remain valid only for packages whose version fields match
  revocation by explicit deprecation grant only; no silent reuse
  superseding version must be registered before packages may claim new version
  package publication and policy issuance are independent steps (§7)
```

## 7. Issuance order (frozen minimum sequence)

```text
policy semantics frozen
→ version identity frozen
→ explicit policy issuance grant
→ production issued-policy registry/allowlist update
→ partition-scoped live pairing producer
→ real TRAIN/VALIDATION pairing package materialization
→ package verification
→ package publication
→ issued partition authority record
→ schema registration
→ Coverage execution
```

```text
POLICY_ISSUANCE != PACKAGE_PUBLICATION
PACKAGE_PUBLICATION != AUTHORITY_ISSUANCE
AUTHORITY_ISSUANCE != COVERAGE_EXECUTION
```

Each step requires a **separate** explicit authorization. No step implies the
next.

## 8. Remaining producer gap

```text
V0_3_PARTITION_SCOPED_S3_BINDING_ROW_PRODUCER_AVAILABLE=false
ROW_LEVEL_PARTITION_MEMBERSHIP_PROVEN=false
REAL_PAIRING_PACKAGE_MATERIALIZATION_ELIGIBLE=false
```

Evidence (current main):

- `docs/v0-3/s3/evidence/s3-b-train-val-pairing-package-contract-r1.json`
  lists `NO_V0_3_PARTITION_SCOPED_S3_BINDING_ROW_PRODUCER`
- No production path binds `source-002/e5-live-v1` actuals + incumbent forecasts
  into one partition-scoped `S3EvaluationInput` with proven row-level partition
  membership
- `backend/app/trial.py` builds `S3EvaluationInput` but is not partition-scoped
  V0.3 lawful origin

Envelope `partition` label does **not** prove row-level partition membership.
Membership must be demonstrated by a future partition-scoped producer.

### 8.1 Package materialization prerequisites (pre-materialization only)

```text
REAL_PAIRING_PACKAGE_MATERIALIZATION_PREREQUISITES=

1. GENERAL_PAIRING_POLICY_ISSUED
2. EXACT_ACTUAL_PAIRING_POLICY_ISSUED
3. V0_3_PARTITION_SCOPED_S3_BINDING_ROW_PRODUCER_AVAILABLE
4. ROW_LEVEL_PARTITION_MEMBERSHIP_PROVEN
5. lawful source-002/e5-live-v1 actuals authority available
6. lawful incumbent forecast + cutoff authority available
7. TEST_REMAINS_SEALED
```

The following are **not** materialization prerequisites (they occur after
materialization per §7):

```text
PACKAGE_PUBLICATION_IS_MATERIALIZATION_PREREQUISITE=false
AUTHORITY_ISSUANCE_IS_MATERIALIZATION_PREREQUISITE=false
SCHEMA_REGISTRATION_IS_MATERIALIZATION_PREREQUISITE=false
COVERAGE_EXECUTION_IS_MATERIALIZATION_PREREQUISITE=false
```

```text
MATERIALIZATION_PREREQUISITES != FULL_COVERAGE_CHAIN_PREREQUISITES
```

### 8.2 Materialization eligibility (current main)

```text
REAL_PAIRING_PACKAGE_MATERIALIZATION_ELIGIBLE=false
```

Eligibility is blocked only by **pre-materialization** gaps:

```text
PAIRING_POLICY_NOT_ISSUED
EXACT_ACTUAL_PAIRING_POLICY_NOT_ISSUED
NO_PARTITION_SCOPED_PRODUCER
ROW_LEVEL_PARTITION_MEMBERSHIP_NOT_PROVEN
```

Do **not** use post-materialization states to explain why materialization is
not yet eligible:

```text
PACKAGE_NOT_PUBLISHED — not a materialization blocker
AUTHORITY_NOT_ISSUED — not a materialization blocker
SCHEMA_NOT_REGISTERED — not a materialization blocker
```

### 8.3 Full downstream Coverage-chain remaining prerequisites

```text
REMAINING_COVERAGE_EXECUTION_CHAIN=

policy issuance
partition-scoped producer
row-level membership proof
real package materialization
package verification
package publication
partition authority issuance
schema registration
Coverage execution authorization
```

This chain includes steps that occur **after** materialization. It must not be
conflated with `REAL_PAIRING_PACKAGE_MATERIALIZATION_PREREQUISITES` (§8.1).

## 9. Relationship to pairing package contract

| Concern | Pairing package contract (PR #543) | This contract |
| --- | --- | --- |
| Outer envelope fields | §3 | References; does not redefine |
| `pairing_policy_version` field | §3.3 NOT_ISSUED | Issuance authority §6 |
| `exact_actual_pairing_policy_version` field | §1 Q3 | Proposed ID §4.2 + issuance §6 |
| Partition authority issuance | §4 | Out of scope |
| Trusted registries | §3.4, §4.2 | Policy allowlists only |

## 10. Coverage wiring (unchanged)

```text
S3_B_COVERAGE_EXECUTION=NOT_COMPUTABLE_OR_BLOCKED
COVERAGE_FORMULA_UNCHANGED=true
COVERAGE_MASK_UNCHANGED=true
TEST_REMAINS_SEALED=true
```

Lawful Coverage remains blocked until the full chain in §7 completes.

## 11. Strict out of scope

```text
PRODUCTION_CODE_MUTATION=false
PAIRING_POLICY_ISSUANCE=false
EXACT_ACTUAL_PAIRING_POLICY_ISSUANCE=false
ISSUED_POLICY_ALLOWLIST_MUTATION=false
PAIRING_PACKAGE_PRODUCER_IMPLEMENTATION=false
LIVE_PAIRING_EXECUTION=false
REAL_PAIRING_PACKAGE_MATERIALIZATION=false
REAL_PAIRING_PACKAGE_PUBLICATION=false
AUTHORITY_RECORD_ISSUANCE=false
SCHEMA_VERSION_REGISTRATION=false
COVERAGE_EXECUTION=false
PINBALL_EXECUTION=false
BACKTEST_EXECUTION=false
TEST_READ=false
TEST_EVALUATION=false
S3_C_EXECUTION=false
S3_D_EXECUTION=false
S4_AUTHORIZED=false
MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION=false
```

No real P50/P80/P90 Coverage values are produced by this contract.
