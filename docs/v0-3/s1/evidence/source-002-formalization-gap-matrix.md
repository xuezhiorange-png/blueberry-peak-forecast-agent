# V0.3-S1 Source 002 Formalization Gap Matrix

## Matrix identity and interpretation

```text
MATRIX_ID=V0_3_S1_SOURCE_002_FORMALIZATION_GAP_MATRIX
MATRIX_STATUS=FROZEN_FOR_PREPARATION_REVIEW
BASELINE_MAIN_SHA=431a88fb4b542264fcf60d95a840202cc578f394
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
FORMALIZATION_GAP_COUNT=21
```

`RESOLVED` below means resolved for Source 002 preparation only. It never
means that a formal source authority, cohort, Q2C decision, or S1 acceptance
has been issued. `PENDING` means a governance or formal evidence input is
still required. `BLOCKED` means the dependent formal artifact or acceptance
gate cannot be issued in the current state.

## Resolved for Source 002 preparation only

| item | status | evidence boundary |
| --- | --- | --- |
| immutable source object identity | RESOLVED | Source SHA-256 and byte count were machine-generated during the authorized read; no source file is committed here. |
| observed schema identity | RESOLVED | `observed-source-schema-v1` and the observed schema SHA-256 are recorded in the companion evidence file. |
| required source field presence | RESOLVED | All seven required headers were observed; no row-level values are retained. |
| canonical grain support | RESOLVED | Date, farm, subfarm, and variety support the frozen grain; plot remains unsupported. |
| aggregate coverage preparation | RESOLVED | Mapped season, counts, date bounds, and July boundary evidence are recorded as aggregates. |
| source quantity precision observation | RESOLVED | Source 002 accepted precision is 0.001 kg with no observed value above three decimals. |

## Remaining formalization gaps

| gap | status | current state | required next evidence or decision |
| --- | --- | --- | --- |
| `FORMAL_SOURCE_ATTESTATION` | BLOCKED | The authority evidence record remains `NOT_ISSUED`; this preparation file is not an attestation. | Source-owner attestation with all 16 authority identity fields, `ATTESTED` status, and an attestation hash. |
| `FORMAL_SOURCE_COHORT_MANIFEST` | BLOCKED | No cohort identity or manifest hash is issued. | A separately reviewed aggregate cohort manifest with scope, policy identities, object identities, and custody record. |
| `FORMAL_CORRECTION_POLICY` | PENDING | Current business statements do not define formal correction semantics. | Versioned correction policy and source-system evidence for correction visibility and lineage. |
| `FORMAL_VOID_POLICY` | PENDING | Current business statements do not define formal void semantics. | Versioned void policy and propagation evidence. |
| `FORMAL_REVISION_POLICY` | PENDING | Q2A/I7 winner semantics are authoritative context, but source-specific revision evidence is not bound. | Source-specific revision policy identity and lineage evidence. |
| `REVISION_POLICY_VERSION` | PENDING | No source-specific version is issued. | Governance owner issues a stable revision-policy identity. |
| `WITHDRAWAL_POLICY_VERSION` | PENDING | No source-specific withdrawal policy version is issued. | Custody/governance owner issues retention and withdrawal policy identity. |
| `VOID_PROPAGATION_POLICY_VERSION` | PENDING | No source-specific void propagation identity is issued. | Governance owner binds downstream propagation targets and policy version. |
| `FORMAL_MISSING_DAY_RULE` | PENDING | `UNKNOWN_NOT_ZERO` is the fail-closed semantic; source completeness and July handling remain unresolved. | Formal missing-day/completeness rule and reviewed evidence. |
| `POINT_IN_TIME_VISIBILITY_RULE` | PENDING | The repository contract requires source availability/recorded/revised/finalized visibility evidence; Source 002 aggregate coverage does not provide it. | Source-system visibility fields or an approved policy-null rule, with cutoff reconstruction evidence. |
| `LATE_ENTRY_RULE` | PENDING_FORMALIZATION | Business context says the reported late-entry scenario is not applicable; this is not formal technical evidence. | Formal late-entry policy or source-system evidence establishing the applicable rule. |
| `FINAL_CONFIRMATION_FORMAL_EVIDENCE` | PENDING | Immediate scan completion is business-confirmed but not formally evidenced. | Source-owner confirmation bound to the attestation and source-system event semantics. |
| `UNMAPPED_DATE_POLICY` | PENDING | July 2025 contains 2 rows on 1 date and is deliberately not auto-assigned. | Business/governance decision for July ownership, exclusion, or exception handling. |
| `TARE_DEDUCTION_METHOD` | PENDING | Tare is business-confirmed as already deducted, but the method is not specified. | Formal tare method and measurement evidence. |
| `SCALE_PRECISION_FORMAL_EVIDENCE` | PENDING | Source 002 supports the 0.001 kg observed precision; no formal calibration/measurement authority record is bound. | Formal scale precision and calibration evidence for the governed source. |
| `MAPPING_POLICY_IDENTITY` | PENDING | Dimension support is observed, but no source-specific versioned farm/subfarm/variety mapping identity is frozen. | Versioned mapping policy/registry identity and review evidence. |
| `COVERAGE_SCOPE_ENTITY_ID_LISTS` | BLOCKED | The schema requires concrete season/farm/subfarm/variety arrays; this package retains counts and no row-derived identity lists. | Separately authorized, governed mapping evidence or a reviewed non-sensitive identity list. |
| `CUSTODY_RECORD` | BLOCKED | Current custody evidence remains `NOT_ISSUED`; no storage or credential locator is recorded. | Versioned custody record covering access, retention, withdrawal, void propagation, and external binding hash. |
| `INCLUSION_POLICY_AND_KNOWN_EXCLUSIONS` | PENDING | Aggregate coverage does not establish formal inclusion/exclusion policy or representativeness limits. | Versioned inclusion policy, known exclusions, and reconciled aggregate evidence. |
| `Q2C_DECISION` | BLOCKED | Q2C draft facts are not formally accepted and the authority/visibility/policy gaps remain open. | Independent Q2C decision record after required physical and source evidence closes. |
| `S1_INDEPENDENT_REVIEW` | BLOCKED | This package has not been independently reviewed as a complete S1 acceptance package. | Independent review of the complete S1 evidence package. |

## Explicit non-closure statements

```text
FORMAL_ATTESTATION_CREATED=false
FORMAL_COHORT_MANIFEST_CREATED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

Source 002 evidence does not create a second authority contract. The existing
source-authority, business-attestation, and source-cohort schemas remain the
canonical contracts. No formal JSON artifact is generated because the
required authority, policy, coverage-scope identity, and custody fields are
not all evidenced.

## Next gate impact

The package directly supports preparation for source identity, observed schema
identity, aggregate coverage, canonical-grain support, and quantity precision.
It partially informs physical/Q2C and inclusion discussions. It does not close
source authority, cohort freeze, point-in-time visibility, revision winner,
correction/void, custody, split, metric, minimum-coverage, quality-threshold,
holdout, or independent-review gates.
