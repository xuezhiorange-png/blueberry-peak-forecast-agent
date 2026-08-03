# V0.2 Release Readiness Evidence and Warning Triage

## 1. Document identity and immutable baseline

```text
VERSION=0.2.0
TASK_NAME=V0_2_RELEASE_READINESS_EVIDENCE_AND_WARNING_TRIAGE
TASK_TYPE=RELEASE_READINESS_REMEDIATION
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
BASE_BRANCH=main
BASE_SHA=24c3055633a3fb0d8b5f96be7ef225b588246b24
DOCUMENT_PATH=docs/v0-2/v0-2-release-readiness-evidence.md
DOCUMENTATION_ONLY=true
RAW_BUSINESS_DATA_COMMITTED=false
PERSONAL_DATA_COMMITTED=false
V0_2_RELEASE_AUTHORIZED=false
ROUND_C_IMPLEMENTATION_AUTHORIZED=false
```

The audit was performed against `origin/main` at the stated SHA. The
protected source worktree was not used for document creation. No production
database, source system, or repository code was modified.

The current main post-merge evidence is:

```text
POST_MERGE_CI_RUN_ID=30827466563
POST_MERGE_CI_EVENT=push
POST_MERGE_CI_HEAD_SHA=24c3055633a3fb0d8b5f96be7ef225b588246b24
POST_MERGE_CI_STATUS=completed
POST_MERGE_CI_CONCLUSION=success
ALEMBIC_HEAD_COUNT=1
ALEMBIC_HEAD=0028_quality_child_hash_scope
```

## 2. V0.2 scope completion summary

The engineering portion of V0.2-S5 is technically closed. PR #156 is merged
at the baseline SHA. Its post-merge run proved the real Vite application,
real Trial API, real backend, PostgreSQL 16, desktop/mobile browser projects,
frontend unit tests, and the existing full-suite canary.

The S5 implementation evidence is not business-data acceptance. The current
S5 authorization documents remain historical governance artifacts and retain
`V0_2_RELEASE_AUTHORIZED=false`.

```text
S5_ENGINEERING_SCOPE_COMPLETE=true
S5_REAL_DATA_ACCEPTANCE_COMPLETE=false
S5_RELEASE_AUTHORIZATION=false
```

## 3. Approved dataset identity

```text
APPROVED_DATASET=false
DATASET_SOURCE_SYSTEM=none
DATASET_SOURCE_DATASET=none
DATASET_SOURCE_VERSION=none
DATASET_SNAPSHOT_REFERENCE=none
DATASET_SHA256=none
DATASET_ROW_COUNT=unknown
DATASET_BYTE_SIZE=unknown
DATASET_APPROVED_PURPOSE=V0_2_REAL_DATA_ACCEPTANCE
```

No governed, immutable historical dataset was supplied or available in the
repository evidence. No `latest` table, mutable shared file, fixture, seed,
developer-created data, or Playwright data is promoted to an approved
dataset.

## 4. Business source attestation

The current governed evidence is explicitly negative:

- `docs/forecast-quality/q2e-source-owner-authority-evidence.md` records
  `SOURCE_OWNER=UNKNOWN` and `ATTESTATION_STATUS=NOT_ATTESTED`.
- `docs/forecast-quality/q2e-business-source-attestation-audit.md` records
  `Q2E_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER` and
  `BUSINESS_ATTESTATION_READY=false`.
- The current Issue #102 governance evidence contains no later
  `ATTESTED` source record.

```text
BUSINESS_ATTESTATION_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
BUSINESS_OWNER_ROLE_VERIFIED=false
ATTESTATION_STATUS=NOT_ATTESTED
ATTESTATION_HASH=none
```

No owner, source system, dataset release, effective attestation time,
snapshot manifest, or approval hash is inferred from Git identity, table
names, fixtures, or code.

## 5. Physical measurement and date/grain authority

The following are frozen contract targets, not verified business evidence:

```text
PHYSICAL_EVENT=FARM_PICK
QUANTITY_BASIS=OBSERVED_WEIGHT
UNIT=KG
TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
```

The required proof of weighing location and timing, picked-fruit population,
sorting and rejection rules, transport and post-harvest loss, tare,
precision, Decimal rounding, timezone/day boundary, late entry, revision,
void/finalization, and historical publication visibility is absent.

```text
MEASUREMENT_BOUNDARY_VERIFIED=false
DATE_AND_GRAIN_AUTHORITY_VERIFIED=false
REVISION_AUTHORITY_VERIFIED=false
HISTORICAL_VISIBILITY_VERIFIED=false
PHYSICAL_TARGET_EQUIVALENCE_VERIFIED=false
```

## 6. Revision and historical visibility authority

The software contracts and persistence tests provide fail-closed mechanisms
for revision selection and point-in-time visibility. They do not identify a
business publication boundary or provide an approved real-data visibility
manifest.

```text
HISTORICAL_VISIBILITY_MANIFEST=missing
CURRENT_OR_LATEST_LOOKUP_ACCEPTED=false
RECEIPT_OR_ARRIVAL_PROXY_ACCEPTED_AS_FARM_PICK=false
```

## 7. Real-data acceptance execution evidence

Real-data acceptance was not started. The preflight stopped before any data
read or import because both the attestation and immutable approved snapshot
were missing. This is a fail-closed block, not a passing empty-data run.

```text
REAL_DATA_ACCEPTANCE_COMPLETE=false
REAL_DATA_ACCEPTANCE_RUN_ID=none
REAL_DATA_ACCEPTANCE_APPLICATION_SHA=none
REAL_DATA_ACCEPTANCE_DATASET_SHA256=none
REAL_DATA_ACCEPTANCE_ATTESTATION_HASH=none
REAL_DATA_ACCEPTANCE_STARTED_AT=none
REAL_DATA_ACCEPTANCE_COMPLETED_AT=none
SOURCE_ROWS=unknown
ACCEPTED_ROWS=unknown
EXCLUDED_ROWS=unknown
MISSING_ROWS_OR_DAYS=unknown
MISSING_DATA_PROPORTION=unknown
COVERAGE_REPORT_STATUS=BLOCKED_BEFORE_DATA_ACCESS
GLOBAL_FORECAST_ACCURACY_CLAIM=false
```

No ephemeral PostgreSQL acceptance database was created for this blocked
attempt. No raw rows, credentials, database identifiers, or private source
references were stored.

The required coverage report therefore remains unavailable:

- farms: unknown;
- varieties: unknown;
- seasons: unknown;
- date range: unknown;
- subfarm/plot grain coverage: unknown;
- missing days: unknown;
- excluded records and reasons: unknown;
- not-computable metrics: unknown;
- insufficient-coverage limitations: unknown.

## 8. Coverage and representativeness decision

There is no approved real-data result from which to calculate coverage,
missing-data proportion, exclusions, or representativeness. A single
Playwright seed or synthetic engineering fixture would not satisfy this
section and is not used.

```text
REAL_DATA_COVERAGE_PROVEN=false
REAL_DATA_REPRESENTATIVENESS_PROVEN=false
GLOBAL_FORECAST_ACCURACY_CLAIM=false
```

## 9. Complete V0.2 release-gate evidence matrix

`PASS` below means technical evidence was observed in the current main
engineering CI or browser acceptance. It does not substitute for the
blocked business-data gate. Every row remains reviewable because this is a
Draft documentation PR.

| Gate name | Status | Authoritative evidence | Evidence SHA or run ID | Application SHA | Scope | Limitations | Review needed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `V0_2_S1_COMPLETE` | PASS | Actual-harvest lifecycle and atomicity tests in the full-suite canary | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Engineering implementation | No approved real dataset | yes |
| `V0_2_S2_COMPLETE` | PASS | Point-in-time, lineage, binding, and backtest test suites in the full-suite canary | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Engineering implementation | Real-data execution remains blocked | yes |
| `V0_2_S3_COMPLETE` | PASS | Quality metric, baseline, persistence, and replay tests in the full-suite canary | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Engineering implementation | No business-attested labels | yes |
| `V0_2_S4_COMPLETE` | PASS | Trial API contract and regression evidence on current main | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Public API engineering | Does not prove source ownership | yes |
| `V0_2_S5_COMPLETE` | PASS | PR #156 post-merge frontend unit and real browser acceptance | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Two-page Trial frontend | Browser data is engineering seed data | yes |
| `ACTUAL_HARVEST_COMMIT_ATOMIC` | PASS | Full-suite lifecycle/concurrency coverage and real Trial E2E commit path | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Atomic software behavior | Not a real-data business acceptance | yes |
| `POINT_IN_TIME_LABEL_SNAPSHOT_COMPLETE` | PASS | Snapshot, cutoff, revision, and immutability tests in full suite | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Technical snapshot behavior | Source publication boundary is unattested | yes |
| `HISTORICAL_BACKTEST_REPRODUCIBLE` | PASS | Historical backtest persistence/replay/concurrency test evidence | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Synthetic/engineering reproducibility | No approved historical dataset result | yes |
| `LEAKAGE_AUDIT_PASSED` | PASS | Cutoff and visibility negative-path tests in full suite | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Software leakage controls | Cannot attest to external source publication | yes |
| `QUALITY_METRICS_COMPLETE` | PASS | Quality persistence, API, and browser rendering evidence | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Technical metric path | Real-data representativeness unavailable | yes |
| `NAIVE_BASELINE_COMPARISON_COMPLETE` | PASS | Baseline comparison tests and persisted Quality E2E readback | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Technical comparison path | No business-approved label set | yes |
| `REAL_DATA_ACCEPTANCE_COMPLETE` | BLOCKED | Q2E source-owner and attestation evidence | `Q2E_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER` | not executed | Approved historical data and business evidence | Owner, attestation, snapshot, and physical boundary missing | yes |
| `POSTGRESQL_E2E_PASSED` | PASS | PostgreSQL 16 service, isolated database, Alembic, full suite, cleanup, and Trial E2E steps | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Engineering/database acceptance | Uses CI fixtures, not approved historical data | yes |
| `FRONTEND_E2E_PASSED` | PASS | Real Vite/backend/PostgreSQL 16 desktop and mobile Playwright run | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Browser integration | Not real-data acceptance | yes |
| `BROWSER_FORECAST_FLOW_PASSED` | PASS | Forecast authority, create, readback, curve, and export browser scenarios | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Trial Forecast flow | Fixture authority and forecast data | yes |
| `BROWSER_FORECAST_VS_ACTUAL_FLOW_PASSED` | PASS | Import, validation, commit, Quality readback, comparison, and export scenarios | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Trial Forecast-vs-actual flow | Fixture actual data and no business attestation | yes |
| `NO_CLI_REQUIRED_FOR_TRIAL_USER` | PASS | Complete browser path executed without CLI interaction | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | User interaction boundary | Does not establish production data representativeness | yes |
| `UNIQUE_ALEMBIC_HEAD` | PASS | `uv run alembic -c backend/alembic.ini heads` | `0028_quality_child_hash_scope` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Migration topology | None observed | yes |
| `FULL_SUITE_CI_PASSED` | PASS | Full pytest JUnit and successful canary job | `30827466563` | `24c3055633a3fb0d8b5f96be7ef225b588246b24` | Main engineering regression | 646279 warnings require separate triage | yes |

```text
RELEASE_GATE_TOTAL=19
RELEASE_GATE_PASS=18
RELEASE_GATE_FAIL=0
RELEASE_GATE_BLOCKED=1
V0_2_RELEASE_READINESS=NOT_READY
V0_2_RELEASE_AUTHORIZED=false
```

## 10. Warning normalized signature inventory

Primary source: full-suite canary run `30827466563`, job
`full-suite-canary`, pytest summary:

```text
3423 passed, 3 skipped, 646279 warnings in 1349.88s
```

The CI log exposes 13 normalized warning signatures. Pytest provides large
aggregate counts by test file, but does not emit a complete per-signature
instance ledger. The visible detail count is therefore not substituted for
the authoritative total `646279`.

| Normalized signature | Visible detail count | Aggregate source | Provisional classification | Data/transaction/security risk | Recommended stage |
| --- | ---: | --- | --- | --- | --- |
| Pydantic serializer unexpected `date` for field `date` | 91 | pytest warning summary | PRE_RELEASE_FIX_RECOMMENDED | Date serialization correctness; exact total not decomposable | Before release |
| Pydantic serializer unexpected `enum` for `source_recorded_at_authority_status` | 2 | pytest warning summary | PRE_RELEASE_FIX_RECOMMENDED | Contract serialization correctness | Before release |
| Pydantic serializer unexpected `enum` for `record_status` | 2 | pytest warning summary | PRE_RELEASE_FIX_RECOMMENDED | Contract serialization correctness | Before release |
| Pydantic serializer unexpected `str` for `effective_marketable_quantity_kg` float input | 1 | pytest warning summary | PRE_RELEASE_FIX_RECOMMENDED | Decimal/business quantity serialization | Before release |
| SQLAlchemy garbage collector cleanup of unreturned asyncpg connection | 12 | pytest warning summary | PRE_RELEASE_FIX_RECOMMENDED | Transaction/resource lifecycle risk | Before release |
| Deprecated `HTTP_422_UNPROCESSABLE_ENTITY` constant | 5 | pytest warning summary | POST_RELEASE_TECHNICAL_DEBT | Dependency/API deprecation | Scheduled debt |
| Deprecated NumPy array shape assignment in joblib | 1 | pytest warning summary | POST_RELEASE_TECHNICAL_DEBT | Future dependency behavior | Scheduled debt |
| Deprecated sqlite3 default datetime adapter | 1 | pytest warning summary | POST_RELEASE_TECHNICAL_DEBT | Date/time behavior debt | Scheduled debt |
| Deprecated concurrency helper shim | 1 | pytest warning summary | POST_RELEASE_TECHNICAL_DEBT | Test helper migration | Scheduled debt |
| Deprecated migration helper shim | 3 | pytest warning summary | POST_RELEASE_TECHNICAL_DEBT | Test helper migration | Scheduled debt |
| Deprecated PostgreSQL profile helper shim | 1 | pytest warning summary | POST_RELEASE_TECHNICAL_DEBT | Test helper migration | Scheduled debt |
| `pytest.mark.asyncio` on synchronous tests | 15 | pytest warning summary | TEST_OR_TOOLING_NOISE | Test collection/configuration | Test maintenance |
| `record_property` incompatible with xunit2 | 1 | pytest warning summary | TEST_OR_TOOLING_NOISE | JUnit metadata only | Test maintenance |

The visible detail counts sum to 136 and are not the total warning count.
They are included only to identify the observed signatures; the module-level
pytest aggregates account for the authoritative total. No warning filter,
global suppression, test deletion, or pytest configuration change was made.

```text
WARNING_INSTANCE_COUNT=646279
WARNING_UNIQUE_SIGNATURE_COUNT=13
WARNING_CLASSIFIED_SIGNATURE_COUNT=13
WARNING_UNCLASSIFIED_SIGNATURE_COUNT=0
WARNING_SIGNATURE_OCCURRENCE_RECONCILIATION_COMPLETE=false
WARNING_RELEASE_BLOCKER_SIGNATURE_COUNT=0
WARNING_PRE_RELEASE_FIX_SIGNATURE_COUNT=5
WARNING_POST_RELEASE_TECH_DEBT_SIGNATURE_COUNT=6
WARNING_TEST_OR_TOOLING_NOISE_SIGNATURE_COUNT=2
DATA_CORRECTNESS_WARNING_SIGNATURE_COUNT=4
TRANSACTION_OR_CONCURRENCY_WARNING_SIGNATURE_COUNT=1
SECURITY_WARNING_SIGNATURE_COUNT=0
TIMEZONE_OR_DECIMAL_WARNING_SIGNATURE_COUNT=2
IMMINENT_RUNTIME_BREAKAGE_WARNING_SIGNATURE_COUNT=0
WARNINGS_RELEASE_CLASSIFICATION=INCOMPLETE
```

Because the occurrence ledger cannot be reconciled per signature and the
observed warning set contains data-serialization and connection-lifecycle
risks, the warning set cannot be certified as wholly non-blocking. The
current evidence does not prove a release-blocking warning, but it also does
not satisfy the zero-risk conditions for `NON_BLOCKING_TECHNICAL_DEBT`.

## 11. Warning release-risk decision

```text
NO_GLOBAL_WARNING_SUPPRESSION=true
NO_TEST_DELETION_FOR_WARNING_COUNT=true
NO_WARNING_STATISTICS_MODIFIED=true
NO_RELEASE_BLOCKING_WARNING_PROVEN=false
WARNING_TRIAGE_COMPLETE=false
```

The five pre-release recommendations are the four Pydantic serialization
signatures and the unreturned asyncpg connection signature. They require
separate engineering review; this documentation task does not fix them.

## 12. Remaining blockers and recommended next task

The release is blocked by the following evidence gates:

1. `BUSINESS_ATTESTATION_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER`.
2. `APPROVED_DATASET_VERIFIED=false`; no immutable approved snapshot or
   governed dataset SHA-256 is available.
3. Physical measurement boundary and historical visibility authority remain
   unverified.
4. Real-data acceptance, coverage, representativeness, and the required
   business-limited forecast report were not executed.
5. Warning occurrence reconciliation and risk clearance are incomplete.

Recommended next task, not authorized by this document:

```text
NEXT_TASK_NAME=V0_2_RELEASE_READINESS_EVIDENCE_RECONCILIATION
NEXT_TASK_TYPE=READ_ONLY_AUDIT
NEXT_TASK_SCOPE=Obtain and verify formal source-owner attestation and an approved immutable dataset; reconcile per-signature warning counts from authoritative CI evidence; do not import data or change code until those inputs exist.
NEXT_TASK_ALLOWED_PATHS=docs/v0-2/v0-2-release-readiness-evidence.md only
NEXT_TASK_STOP_BOUNDARY=Stop before real-data import, production database mutation, code changes, Ready, Merge, Round C, or V0.2 release authorization.
```

## 13. Governance and authorization status

```text
DOCUMENTATION_ONLY=true
REAL_DATA_ROWS_COMMITTED=false
BACKEND_CHANGED=false
FRONTEND_CHANGED=false
TEST_CHANGED=false
MIGRATION_CHANGED=false
WORKFLOW_CHANGED=false
DEPENDENCY_CHANGED=false
CONFIG_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
ROUND_C_IMPLEMENTATION_AUTHORIZED=false
V0_2_RELEASE_AUTHORIZED=false
ROUND_C_STARTED=false
V0_2_RELEASE_PERFORMED=false
```

This document records a truthful blocked release-readiness state. It is not
an attestation, does not substitute for an approved dataset, does not grant
release authorization, and does not authorize Round C.

```text
V0_2_RELEASE_READINESS_EVIDENCE_AND_WARNING_TRIAGE_RESULT=BLOCKED
BLOCK_REASON=BUSINESS_ATTESTATION_AND_APPROVED_DATASET_UNAVAILABLE;WARNING_OCCURRENCE_RECONCILIATION_INCOMPLETE
```
