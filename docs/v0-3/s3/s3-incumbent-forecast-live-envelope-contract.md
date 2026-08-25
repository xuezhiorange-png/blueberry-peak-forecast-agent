# V0.3-S3-A2 Incumbent Forecast Live Envelope Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-incumbent-forecast-live-envelope-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_LIVE_ENVELOPE
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=e93474cf787b8ff2cd1eb96c5a202879585f8304
BASE_MAIN_TREE_SHA=7eba0765f28c2cc30e743897f96130983b9eb80b
BASE_REF=origin/main
PARENT_LIVE_SOURCE_KIND_CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT
PARENT_LIVE_SOURCE_KIND_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md
PARENT_CONTENT_PRODUCER_CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT
PARENT_CONTENT_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md
PARENT_REPLAY_SOURCE_CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT
PARENT_REPLAY_SOURCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
GRANDPARENT_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT
GRANDPARENT_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CURRENT_V0_3_S3_COMPLETE=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes deterministic **envelope assignment** authority: how
`VersionedIncumbentForecastArtifact` envelope field `catalog_source_kind` may be
set by the content producer (and therefore observed by the forecast adapter and
catalog artifact). Parent live source kind contract
`docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §§1–9 already
freeze which `CatalogSourceKind` may be called live forecast authority and which
kinds must never impersonate it; live source kind R1 (#335) already landed
`CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` in `registry.py`.
This contract does **not** re-freeze the enum, re-open live kind impersonation
rules, or authorize wiring.

This is a **live envelope assignment** governance contract only. It is **not** a
replay source contract, **not** a live source kind enum contract, **not**
default_factory wiring (`obtain` → `produce` → `adapter`), **not** V0.2 postgres
obtain implementation, **not** bindable catalog closeout, and **not** evidence
that versioned forecast artifacts exist in the repository today.

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_ENVELOPE_ASSIGNMENT=true
CONTRACT_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_PRODUCE_CATALOG=true
CONTRACT_MERGE_DOES_NOT_BIND_CATALOG=true
AVAILABLE_CLOSEOUT_REQUIRED_FOR_LIVE_FLIP=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent live source kind contract and landed R1 (reference only)

~~~text
LIVE_SOURCE_KIND_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md
LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
LIVE_SOURCE_KIND_AUTH_EVIDENCE_JSON_SHA256=759644330a0063560f11e53a74a92b03dbb6221ab6c58f523a74462dc145fa9e
LIVE_SOURCE_KIND_R1_EVIDENCE_JSON_SHA256=3a7a1f4f74074630c4eedb658ca361db579e16b1f7e4630f51b04266fa963a7a
LIVE_FORECAST_SOURCE_KIND=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
~~~

Live source kind contract §§1–9 and §6 future-envelope eligibility naming remain
authoritative for impersonation prohibition and bindable-catalog prerequisites.
R1 (#335) landed the enum member only; it did not change content producer
envelope assignment. This envelope contract operationalizes parent §6 assignment
rules without reopening §§1–5 enum or impersonation freeze.

### 1.2 Parent replay source contract and landed R1 (reference only)

~~~text
REPLAY_SOURCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=070f54311f08a5c7758602fbe105e511fefd8eca
TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=14a2c27f97fa50a37902558c9819f07cd3d71411
~~~

Replay source contract §§1–9 remain authoritative. `IncumbentForecastReplaySource`
(R1, #332) default `obtain()`=`()`. This contract does not authorize postgres
obtain or default_factory wiring from replay source to producer.

### 1.3 Parent content producer contract and landed R1 (reference only)

~~~text
CONTENT_PRODUCER_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=18c1b1c8d66f2e8ae4476f24692f5ebeb85a9a95
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
~~~

Content producer contract §§1–9 remain authoritative. `IncumbentForecastArtifactContentProducer`
(R1, #329) default `replay_rows=()` → `produce()`=`None`; when `replay_rows` is
non-empty the landed producer currently writes
`catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE` on every produced envelope.
This contract freezes when that assignment may become live kind instead; it does
not re-implement projection or content identity hashing.

### 1.4 Grandparent forecast artifact contract and adapter (reference only)

~~~text
INCUMBENT_FORECAST_ARTIFACT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md
FORECAST_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
~~~

Grandparent contract §§1–8 remain authoritative. `IncumbentForecastArtifactAdapter`
(R1, #319) default `artifact=None` → catalog `produce()` first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. `catalog_artifact.produce()` copies
`catalog_source_kind` from forecast envelope, not from alignment.

### 1.5 S2 binding seal (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 2. Why this contract is the unique remaining gap

After live source kind R1 (#335):

1. `CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` is landed in
   `registry.py` and is neither forbidden nor an alignment kind.
2. `IncumbentForecastReplaySource.obtain()` default remains `()`.
3. `IncumbentForecastArtifactContentProducer` still assigns
   `catalog_source_kind=BOUND_FIXTURE` whenever `replay_rows` is non-empty.
4. `IncumbentForecastArtifactAdapter` default `artifact=None` → catalog first
   blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
5. Binding: `BOUND_FIXTURE` → `FIXTURE_ONLY_CATALOG_NOT_BINDABLE`; structural
   passes without fixture remain `NOT_BINDABLE`; no live `BINDABLE` success path.
6. Replay row tuples carry only `model_id`, `forecast_cutoff_at`,
   `forecast_quantile` — row shape alone cannot distinguish live authority from
   fixture injection.

Parent live source kind contract §6 named future envelope eligibility only. This
contract freezes the deterministic assignment rules for `catalog_source_kind` on
produced forecast envelopes. It does not authorize wiring, postgres obtain, or
bindable catalog closeout.

## 3. Live envelope assignment freeze

### 3.1 Assignment locus and provenance

~~~text
ENVELOPE_ASSIGNMENT_LOCUS=IncumbentForecastArtifactContentProducer.produced_artifact.catalog_source_kind
ADAPTER_READS_ENVELOPE_FROM_INJECTED_ARTIFACT_ONLY=true
CATALOG_PRODUCE_COPIES_CATALOG_SOURCE_KIND_FROM_FORECAST_NOT_ALIGNMENT=true
FORBIDDEN_INFER_LIVE_KIND_FROM_ROW_TUPLE_ALONE=true
REPLAY_ROW_FIELDS=model_id,forecast_cutoff_at,forecast_quantile
~~~

Envelope `catalog_source_kind` is assigned at content producer production time on
`VersionedIncumbentForecastArtifact`. The forecast adapter exposes the injected
artifact envelope unchanged. Catalog artifact copies `catalog_source_kind` from
forecast, not from alignment evidence. Replay row field tuples alone are
insufficient to infer live vs fixture authority.

### 3.2 Permitted envelope values (assignment outcomes)

~~~text
LIVE_ENVELOPE_KIND=CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
FIXTURE_ENVELOPE_KIND=CatalogSourceKind.BOUND_FIXTURE
EMPTY_PRODUCTION_OUTCOME=produce()=None
~~~

A future implementation may assign exactly one of:

| Outcome | `catalog_source_kind` | When |
|---|---|---|
| No artifact | `produce()`=`None` | No replay rows, post-exclusion emptiness, or missing projection |
| Fixture envelope | `BOUND_FIXTURE` | Test-only explicit fixture injection path (preserved) |
| Live envelope | `V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` | Named live replay authority with non-empty post-exclusion rows (§3.3) |

`UNBOUND`, `FORBIDDEN_CATALOG_SOURCE_KINDS` members, and
`SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT` must never be assigned as
forecast envelope `catalog_source_kind`.

### 3.3 Live envelope eligibility (all required)

`catalog_source_kind=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` may be assigned
**only when all** of the following hold simultaneously:

1. **Named replay authority**: injected `replay_rows` are obtained under
   `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` with
   `SOURCE_002_IDFL_LABEL_SIDE` point-in-time visibility at historical cutoff
   (inherited from replay source contract; not re-derived from row tuples alone).
2. **Non-empty post-exclusion set**: after TEST partition and business exclusion
   filters, at least one `IncumbentForecastArtifactEntry` remains.
3. **Content identity computed**: `content_identity_sha256` is produced by the
   landed content identity recipe over actual produced rows (recipe not invented
   here).
4. **Explicit live assignment**: producer envelope assignment logic explicitly
   selects live kind; silent default or row-shape inference is forbidden.

If any condition fails → `produce()`=`None` or test-only `BOUND_FIXTURE`; must
not assign live kind.

### 3.4 Fixture test injection path (preserved)

~~~text
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
TEST_INJECTION_MUST_USE_BOUND_FIXTURE_NOT_LIVE_KIND=true
FIXTURE_PATH_OUTCOME=FIXTURE_ONLY_CATALOG_NOT_BINDABLE
FORBIDDEN_TOUCH_FROZEN_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_FROZEN_TEST_FORECAST_ARTIFACT_PY=true
FORBIDDEN_TOUCH_FROZEN_TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY=true
FORBIDDEN_TOUCH_FROZEN_TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
~~~

Test-injected non-empty `replay_rows` in frozen test modules must continue to
produce `catalog_source_kind=BOUND_FIXTURE` and yield
`FIXTURE_ONLY_CATALOG_NOT_BINDABLE`. Live envelope kind must not replace fixture
test envelopes.

### 3.5 Live envelope and bindable catalog (necessary, not sufficient)

~~~text
LIVE_ENVELOPE_KIND_NECESSARY_BUT_NOT_SUFFICIENT_FOR_BINDABLE_CATALOG=true
BOUND_FIXTURE_YIELDS_FIXTURE_ONLY_CATALOG_NOT_BINDABLE=true
THIS_CONTRACT_DOES_NOT_INTRODUCE_LIVE_BINDABLE_SUCCESS_ENUM=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
~~~

Assigning live envelope `catalog_source_kind` is **necessary but not sufficient**
for bindable catalog production. This contract does **not** introduce a
`BindingClassification` live `BINDABLE` success enumeration and does **not** flip
`NO_BINDABLE_CATALOG_IN_REPOSITORY` or `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`.

## 4. Empty-state and default-construction prohibition

~~~text
EMPTY_OBTAIN_MUST_NOT_ASSIGN_LIVE_ENVELOPE=true
EMPTY_REPLAY_ROWS_MUST_NOT_ASSIGN_LIVE_ENVELOPE=true
PRODUCE_NONE_MUST_NOT_ASSIGN_LIVE_ENVELOPE=true
ADAPTER_ARTIFACT_NONE_MUST_NOT_ASSIGN_LIVE_ENVELOPE=true
DEFAULT_CONSTRUCTION_MUST_FAIL_CLOSED=true
~~~

| Repository default | Live envelope prohibited |
|---|---|
| `IncumbentForecastReplaySource.obtain()`=`()` | yes |
| `IncumbentForecastArtifactContentProducer.replay_rows=()` → `produce()`=`None` | yes |
| `IncumbentForecastArtifactAdapter.artifact=None` | yes |

Catalog default `produce()` first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. Contract authorization does not mean
live forecast artifacts are materialized in the repository.

## 5. Explicit non-scope (not authorized by this contract)

This contract merge does **not** authorize:

- implementing envelope assignment in Python
- wiring `obtain()` → `replay_rows` → `produce()` → adapter `default_factory`
- obtaining replay rows from V0.2 postgres or repository scan
- modifying `registry.py` enum membership
- writing versioned incumbent forecast artifacts into the repository
- flipping `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`
- bindable catalog production or `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` closeout
- `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` closeout
- live S2 identity alignment facts
- S3-B semantics verified claims or S3-C backtest execution
- TEST evaluation or TEST unseal
- SOURCE_002 row-level primary read
- new Alembic migrations

~~~text
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
~~~

## 6. Forbidden inputs and substitutions

~~~text
FORBIDDEN_USE_HARVEST_BUSINESS_DATE_AS_FORECAST_CUTOFF=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_INFER_LIVE_ENVELOPE_FROM_ROW_TUPLE_SHAPE=true
FORBIDDEN_SUBSTITUTION_INCUMBENT_DAILY_CURVE_PROVIDER=true
FORBIDDEN_SUBSTITUTION_SPARSE_HORIZON_BINDING_FORECAST_PROVIDER=true
FORBIDDEN_SUBSTITUTION_S3_BINDING_ROW=true
FORBIDDEN_SUBSTITUTION_S2_HARVEST_GRAIN=true
FORBIDDEN_SUBSTITUTION_H7_FIXTURE=true
FORBIDDEN_MODIFY_FORECAST_ADAPTER_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_REPLAY_SOURCE_PORT_SIGNATURE=true
FORBIDDEN_MODIFY_CATALOG_SOURCE_KIND_PROVENANCE=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
FORBIDDEN_INVENT_CATALOG_IDENTITY=true
FORBIDDEN_INVENT_DISTINCT_ENTRY_COUNTS=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
~~~

## 7. TEST seal and exclusion policy

~~~text
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
TEST_PARTITION_DATES=2026-03-10..2026-04-16
FORBIDDEN_TEST_CUTOFF_OR_HORIZON_INTERSECTION=true
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
~~~

Post-exclusion emptiness after TEST partition filtering must not receive live
envelope assignment.

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Envelope assignment outcomes,
cutoff lists, identity hashes, and distinct entry counts must come from
deterministic producer logic and coordinator-reviewed artifacts only. LLM must
not invent tonnes, farms, cells, cutoff lists, identity hashes, or distinct
entry counts.

## 9. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live block and pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §18 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §27 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §43 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §26 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §31 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §32 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §35 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §20 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~
