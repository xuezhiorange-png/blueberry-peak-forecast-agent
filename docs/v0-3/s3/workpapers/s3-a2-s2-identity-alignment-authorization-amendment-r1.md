# V0.3-S3-A2 S2 identity alignment implementation authorization amendment R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZATION_AMENDMENT_R1
ARTIFACT_VERSION=s3-a2-s2-identity-alignment-authorization-amendment-r1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZATION_AMENDMENT_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_AMENDMENT
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_GRANT_AMENDMENT_ONLY
SLICE=V0.3-S3
USER_GATE=可以继续
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=1de24c0d6120d680d5a310427379ca7ba86ad091
BASE_MAIN_TREE_SHA=9dd6f3adceee05e76974d891d0769e3245253063
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization-amendment-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-authorization-amendment-r1.json
EVIDENCE_JSON_SHA256=c4d26633413dcde42b989684c1eb372443f5598c210d6a920dc51e50bc4093a4
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
AMENDMENT_ONLY=true
NO_STATE_FLIPS=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

This amendment resolves a contract conflict between the merged S2 identity
alignment implementation authorization (#321) and the frozen structural-acceptance
test path in `backend/tests/s3_daily_rowset/test_catalog_artifact.py`
(`blob=af59a9f1d291ab32eff23684aca477f0e4a852cd`). It amends authorization
semantics only. It does **not** implement code, modify backend/tests, flip live
flags, or rewrite the original authorization workpaper or evidence JSON.

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only; bodies not rewritten)

~~~text
ORIGINAL_AUTH_WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization.md
ORIGINAL_AUTH_WORKPAPER_GIT_BLOB_SHA=39b5979a0e81d6bb2ff4c749507b627f8e7da8b2
ORIGINAL_AUTH_EVIDENCE_JSON_SHA256=1d1b213e6a31e899ce777440f1f1dce63be66006520e417775cdb330d335221d
ALIGNMENT_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-contract.md
ALIGNMENT_CONTRACT_GIT_BLOB_SHA=4fdc32bd6c2ac10cf8b02b3be0a6e2ba4f0f665d
ALIGNMENT_CONTRACT_EVIDENCE_JSON_SHA256=e69478f732675f04e3c981d99676b6f28e6bf7ddee43a7af7174f0a75802212a
CATALOG_ARTIFACT_PY_BLOB=d4212b8c8888b866eb613660d4f645da8e257081
REGISTRY_PY_BLOB=b5ad9e87dadf9947348d6576cdcb544a58a20b95
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
S2_IDENTITY_ALIGNMENT_SOURCE_KIND=SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
~~~

Evidence JSON self-hashes above are binding references, not whole-file
`sha256sum` values.

## 2. Conflict identified (read-only audit)

The merged authorization workpaper §3.1 states that `catalog_artifact.py` must
reject non-empty `aligned_identities()` when `alignment_source_kind()` is
`UNBOUND`, `BOUND_FIXTURE`/test fixture, or forbidden. That blanket rejection of
`BOUND_FIXTURE` conflicts with the frozen test
`test_injected_forecast_and_alignment_produces_deterministic_fixture_catalog`,
which explicitly injects `FakeS2IdentityAlignmentPort` with default
`alignment_source_kind_value=CatalogSourceKind.BOUND_FIXTURE` and expects
`FIXTURE_ONLY_CATALOG_NOT_BINDABLE` with `in_memory_structural_acceptance=True`.

This amendment narrows the rejection rule without changing port signatures,
fixture test semantics, or catalog/binding state machines.

## 3. Amended authorization semantics (future implementation only)

### 3.1 Live alignment authority

~~~text
BOUND_FIXTURE_IS_NOT_LIVE_ALIGNMENT_AUTHORITY=true
LIVE_ALIGNMENT_SOURCE_KIND=SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
~~~

Live alignment may use only `SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT`.
`BOUND_FIXTURE` is not a live alignment authority and must not be treated as
repository-backed or bindable source evidence.

### 3.2 Preserved test-only structural fixture path

~~~text
TEST_ONLY_EXPLICIT_INJECTION_BOUND_FIXTURE_PATH_PRESERVED=true
FIXTURE_PATH_OUTCOME=FIXTURE_ONLY_CATALOG_NOT_BINDABLE
FIXTURE_PATH_IN_MEMORY_STRUCTURAL_ACCEPTANCE=true
FIXTURE_PATH_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
FIXTURE_PATH_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
FIXTURE_PATH_MAY_NOT_CREATE_BINDABLE_CATALOG=true
FIXTURE_PATH_MAY_NOT_CREATE_LIVE_SOURCE_STATUS=true
~~~

The existing explicit-injection, test-only `BOUND_FIXTURE` path in
`test_catalog_artifact.py` is preserved. That path may yield only:

- `BindingClassification.FIXTURE_ONLY_CATALOG_NOT_BINDABLE`
- `in_memory_structural_acceptance=True`

It must never produce a bindable catalog, flip `EVALUATION_INSTANCE_REGISTRY_AVAILABLE`,
flip `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, or establish live source
status.

### 3.3 Producer alignment source validation (amended)

For future `catalog_artifact.py` alignment source validation:

1. **Fail closed:** non-empty `aligned_identities()` + `alignment_source_kind()`
   `UNBOUND`.
2. **Fail closed:** non-empty `aligned_identities()` + any member of
   `FORBIDDEN_CATALOG_SOURCE_KINDS`.
3. **Fail closed:** non-empty live identities + any non-fixture source kind other
   than `SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT`.
4. **Allowed only in test-only structural fixture scope:** non-empty
   `aligned_identities()` + explicit-injected `BOUND_FIXTURE` with outcome limited
   to §3.2 above.

The original authorization §3.1 wording that `BOUND_FIXTURE`/test fixture must always
be rejected is superseded **only** within this test-only structural fixture scope
by this amendment. All other live/default paths remain fail-closed.

### 3.4 Unchanged constraints

~~~text
NO_PORT_SIGNATURE_CHANGES=true
NO_FIXTURE_TEST_SEMANTICS_CHANGES=true
NO_CATALOG_BINDING_STATE_MACHINE_CHANGES=true
NO_BACKEND_CHANGES_IN_THIS_AMENDMENT=true
NO_TEST_CHANGES_IN_THIS_AMENDMENT=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_PR_MAY_NOT_FLIP_COMPLETENESS_VERIFIED=true
~~~

## 4. What remains forbidden / not authorized

~~~text
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 5. Amendment pointer manifest (no live flag flips)

~~~text
NO_STATE_FLIPS=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED_UNCHANGED=true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §12 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §29 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §13 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §17 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §18 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §21 pointer

Original authorization artifacts remain authoritative and are not rewritten:

- `docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization.md`
- `docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-authorization.json`

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AMENDMENT_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
AMENDMENT_MERGE_DOES_NOT_FLIP_LIVE_FLAGS=true
AWAITING_COORDINATOR_REVIEW=true
~~~
