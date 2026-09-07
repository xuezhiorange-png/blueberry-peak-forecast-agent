# V0.3-S3-C legal backtest package contract R1 workpaper

## Workpaper identity

~~~text
ARTIFACT_ID=V0_3_S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_R1
ARTIFACT_VERSION=s3-c-legal-backtest-package-contract-r1-v1
TASK_ID=V0_3_S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_R1
TASK_CLASS=READ_ONLY_DISCOVERY_AND_CONTRACT_FREEZE
AUTHORIZATION_SCOPE=S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_ONLY
BASE_MAIN_SHA=3b31f390a69ed8984570fe7d3d5ec9eb6c0d6349
PARENT_PR=570
PARENT_MERGE_COMMIT=3b31f390a69ed8984570fe7d3d5ec9eb6c0d6349
USER_GATE=可以下一任务
S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_FROZEN=true
S3_C_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_AUTHORIZED=false
LEGAL_BACKTEST_PACKAGE_IMPLEMENTED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the read-only discovery supporting the R1 legal
backtest package contract. No S3-C backtest, metric calculation, incumbent
comparison, or TEST evaluation was performed.

## 1. Discovery method and inspected authorities

The review used current main only. It inspected:

| Area | Current-main source | Finding used here |
| --- | --- | --- |
| SOURCE-002 cohort | docs/v0-3/s1/evidence/source-002-final-source-cohort-manifest.json | 84 farms and 192 subfarms are the durable cohort scope; TEST is not a source of members |
| Partition identity | backend/app/forecast_quality/train_val_pairing.py | Accepted source, TRAIN, and VALIDATION identities are explicit |
| Pairing materialization | backend/app/forecast_quality/train_val_pairing_materialization.py | A single producer returns candidate TRAIN and VALIDATION packages; it validates but does not publish |
| Pairing hash replay | backend/app/forecast_quality/train_val_pairing.py | Existing two-stage package identity and canonical replay helpers exist |
| Trusted registries | backend/app/forecast_quality/train_val_trusted_registry.py | Production published-package and issued-authority registries are empty |
| Coverage authority gate | backend/app/forecast_quality/quantile_coverage.py | It resolves the production trusted registries and an empty issued schema-version set |
| PIT incumbent | backend/app/s3_daily_rowset/incumbent_forecast_daily_curve_live_obtain.py and PIT loader/provider modules | Exact PIT forecast lookup exists for the reviewed cutoff and exact cell/target-date/horizon |
| Reviewed cutoff | backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py | One reviewed cutoff is durably represented for P50/P80/P90 |
| Current planning state | docs/v0-3/development-plan.md §4.4 live state block | S3-C and S3 metric execution are authorized but remain contract-bound and blocked; daily rowset completeness remains unverified |

The A2 evaluation-instance catalog is recorded as a separate authority family.
Its availability does not establish a trusted S3-B pairing package or an
issued partition authority record.

## 2. SOURCE-002 binding facts

~~~text
SOURCE_DATASET_ID=source-002
SOURCE_DATASET_VERSION=e5-live-v1
SOURCE_MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
SOURCE_COHORT_MANIFEST=docs/v0-3/s1/evidence/source-002-final-source-cohort-manifest.json
SOURCE_COHORT_FARM_COUNT=84
SOURCE_COHORT_SUBFARM_COUNT=192
TRAIN_PARTITION_IDENTITY_SHA256=55d8e97e73568def2cd368bcf76deeb13de5089361f70b08c8101ea8f745097b
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
TRAIN_ROW_COUNT=16224
TRAIN_START_DATE=2025-08-05
TRAIN_END_DATE=2026-01-30
VALIDATION_PARTITION_IDENTITY_SHA256=006c80ff6bc88ecf7112fd082ab7e27e71655ebd2f00ff105d6110a8473244ba
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
VALIDATION_ROW_COUNT=8006
VALIDATION_START_DATE=2026-01-31
VALIDATION_END_DATE=2026-03-09
TEST_ROW_COUNT=0
TEST_REMAINS_SEALED=true
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
~~~

The accepted grain is season, farm, subfarm, variety, and harvest business
date. Partition content and row membership must remain bound to the accepted
identities; a date range alone is not sufficient.

## 3. Answers to the required discovery questions

### A and B — candidate pairing materialization

~~~text
TRAIN_PAIRING_PACKAGE_PRODUCIBLE=true
VALIDATION_PAIRING_PACKAGE_PRODUCIBLE=true
TRAIN_PAIRING_PACKAGE_LIVE_RUN_PERFORMED=false
VALIDATION_PAIRING_PACKAGE_LIVE_RUN_PERFORMED=false
~~~

The materializer creates partition-scoped S3EvaluationInput values and passes
them through build_candidate_train_validation_pairing_package. It uses the
accepted partition identities, exact actual lookup, cross-partition source-row
checks, reviewed forecast entries, and exact PIT forecast-provider calls.
This is a candidate producer capability finding, not a claim that this task
ran the live producer.

### C — published pairing packages

~~~text
TRAIN_PAIRING_PACKAGE_PUBLISHED=false
VALIDATION_PAIRING_PACKAGE_PUBLISHED=false
PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_COUNT=0
~~~

The production trusted published registry is instantiated empty. The
materializer module states that it does not publish packages. Therefore no
real TRAIN or VALIDATION pairing identity can currently be resolved from the
trusted published registry.

### D — trusted authority records

~~~text
TRAIN_AUTHORITY_RECORD_TRUSTED=false
VALIDATION_AUTHORITY_RECORD_TRUSTED=false
PRODUCTION_TRUSTED_ISSUED_AUTHORITY_RECORD_COUNT=0
ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSION_COUNT=0
~~~

The current registry verifier requires an issued authority record, replayable
record hash, published package resolution, and matching row-set identities.
The existing carrier type and the two general pairing policies do not satisfy
those requirements.

### E — historical cutoff coverage

~~~text
FORECAST_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
REVIEWED_CUTOFF_AT=2026-02-16T00:00:00+08:00
REVIEWED_CUTOFF_MEMBER_COUNT=3
IN_SCOPE_FORECAST_CUTOFF_COUNT_IF_DURABLY_KNOWN=1
FULL_HISTORICAL_CUTOFF_COVERAGE_AVAILABLE=false
~~~

The existing live obtain path uses the reviewed cutoff and the PIT loader
accepts one cutoff for exact forecast cells. No complete S3-C historical
cutoff set was found. The harvest business date is not a forecast cutoff.
The visibility rule remains SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT in the
Asia/Shanghai timezone.

### F — complete legal package availability

~~~text
LEGAL_BACKTEST_PACKAGE_CURRENTLY_AVAILABLE=false
NO_LEGAL_BACKTEST_PACKAGE=true
LEGAL_BACKTEST_PACKAGE_IMPLEMENTED=false
~~~

Current main has candidate pairing and PIT authority components but no legal
package type or builder that combines trusted package publication, trusted
authority issuance, full cutoff-set coverage, and package-level replay into a
single legal status.

## 4. Current blockers

The current legal-package conclusion is blocked by all of the following:

~~~text
TRAIN_PAIRING_PACKAGE_NOT_PUBLISHED
VALIDATION_PAIRING_PACKAGE_NOT_PUBLISHED
TRAIN_AUTHORITY_RECORD_NOT_TRUSTED
VALIDATION_AUTHORITY_RECORD_NOT_TRUSTED
HISTORICAL_CUTOFF_SET_INCOMPLETE
LEGAL_BACKTEST_PACKAGE_NOT_IMPLEMENTED
~~~

The first four are supported by zero-count production registries and the
current fail-closed verifier. The cutoff blocker is supported by the single
reviewed cutoff and the absence of a complete declared cutoff set. The final
blocker is a current code-surface finding: no S3LegalBacktestPackage
construction API exists on main.

No package hash, pairing identity, authority identity, cutoff count beyond the
one observed reviewed cutoff, or metric value is invented in this workpaper.

## 5. Frozen future package controls

### 5.1 Package shape and status

The future package schema is:

~~~text
LEGAL_BACKTEST_PACKAGE_SCHEMA_VERSION=v0-3-s3-c-legal-backtest-package-v1
LEGAL_PACKAGE_STATUS_VALUES=LEGAL,BLOCKED
LEGAL_PACKAGE_PARTIAL_STATUS_FORBIDDEN=true
LEGAL_PACKAGE_SUCCESS_REQUIRES_ALL_PREDICATES=true
~~~

It must bind source and partition identities, both pairing package identities,
both authority-record identities, both evaluation-input identities, forecast
authority, the explicit cutoff set and its identity, model identity, evaluation
window, PIT visibility policy, exact actual-pairing policy, missing-day
policy, aggregate diagnostics, and sealed TEST status.

### 5.2 Required deterministic controls

The future builder must:

- resolve TRAIN and VALIDATION pairing packages from a trusted published
  registry and replay their identities;
- resolve TRAIN and VALIDATION authority records from a trusted issued
  registry and replay their identities;
- bind each package, authority record, and S2 row-set hash to the correct
  partition;
- reject cross-partition row overlap, missing exact actual pairing, missing
  exact forecast authority, and forecast values not visible at the cutoff;
- verify every declared cutoff and the deterministic
  IN_SCOPE_FORECAST_CUTOFF_SET_IDENTITY_SHA256;
- preserve UNKNOWN_NOT_ZERO missing-day semantics;
- reject native floats and use the existing canonical_json_bytes behavior;
- exclude TEST payload and keep blocker output aggregate-only.

The package identity must use a two-stage non-self-referential SHA-256:
identity preimage with both identity fields blank, followed by canonical-hash
preimage with only the canonical hash blank. No timestamps, process ids,
filesystem paths, connection details, or worker identity may enter the
preimages.

### 5.3 Generic incumbent artifact decision

The PIT path supplies exact per-cell, target-date, quantile, and horizon
authority for the reviewed cutoff. The repository also records that no
generic versioned incumbent forecast artifact is present. Since trusted
pairing/authority publication and complete cutoff coverage are not yet
established, the artifact decision remains:

~~~text
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED=UNRESOLVED_BLOCKING
~~~

This is intentionally not a silent requirement or waiver. A future decision
may resolve it only after all lawful PIT, binding-replay, trusted-registry,
and full-cutoff predicates pass.

## 6. S3-B semantic and completeness boundary

Current main records P50, P80, and P90 as verified true upper quantiles. That
semantic state is separate from package legality. Current daily rowset
completeness remains unverified:

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
~~~

Legal package construction does not itself assert complete daily-rowset
coverage. Sparse point metrics may be evaluated only where the legal package
and downstream metric contract permit them.

## 7. Explicit exclusions and next gate

~~~text
S3_C_BACKTEST_EXECUTION_AUTHORIZED=true
S3_METRIC_EXECUTION_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_METRIC_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
BASELINE_VS_INCUMBENT_COMPARISON_AUTHORIZED=false
BASELINE_VS_INCUMBENT_COMPARISON_EXECUTED=false
TEST_EVALUATION=false
TEST_REMAINS_SEALED=true
NO_PRODUCTION_CODE_CHANGE=true
NO_TEST_CODE_CHANGE=true
NO_DATABASE_MUTATION=true
NO_MIGRATION=true
NO_SCHEMA_CHANGE=true
NO_MODEL_CHANGE=true
NO_PARAMETER_CHANGE=true
NO_TEST_ACCESS=true
NO_NEW_METRIC_EXECUTION=true
NO_S3_C_EXECUTION=true
NO_S3_D_EXECUTION=true
NO_S4=true
S3_C_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_AUTHORIZED=false
NEXT_GATE=授权实施legal backtest package
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper freezes the package contract only. It does not authorize the
implementation grant, package publication, authority issuance, S3-C replay,
metric execution, attribution, TEST access, or S4.
