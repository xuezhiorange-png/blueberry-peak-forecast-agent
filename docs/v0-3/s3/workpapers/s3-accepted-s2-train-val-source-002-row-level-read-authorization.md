# V0.3-S3-A2 Accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-accepted-s2-train-val-source-002-row-level-read-authorization-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_GRANT_ONLY
PARALLEL_LANE=S3-A2-ACCEPTED-S2-SOURCE-002-ROW-LEVEL-READ
SLICE=V0.3-S3
ENGLISH_ID=ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=17bff5d09c11c0a245f9b16d37d7a3bb30802dd5
BASE_MAIN_TREE_SHA=c2bf96e7754bac40966f81c19fc56098b5ad63dd
PARENT_CONTRACT_PR=410
PARENT_CONTRACT_MERGE=0ca99dec9a538fcfdc1d2ebe0bf6919d6b66d05b
PARENT_LIVE_AUTHORITY_PR=411
PARENT_LIVE_AUTHORITY_MERGE=17bff5d09c11c0a245f9b16d37d7a3bb30802dd5
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=1eddce85dfd6c49c4fbea674fb65b9a545d67ea2bba947b45eed11f46ea15f42
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-source-002-row-level-read-contract-live-authority.md
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=40adf316357dbaffcd1c9ee4a44b9ff4b955686f
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=a483abe1cd53e0c9dffb755a8c28e9fc16a3dc5f
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-source-002-row-level-read-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-accepted-s2-train-val-source-002-row-level-read-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_EXECUTE_THE_DETERMINISTIC_READER=true
GRANT_MERGE_DOES_NOT_ATTEST_OFFICIAL_HASHES_FROM_A_LIVE_READ=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
THIS_FAMILY_IS_THE_DETERMINISTIC_READER_ATTESTATION_SLICE=true
THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true
THIS_GRANT_DOES_NOT_AUTHORIZE_A_DOCS_ONLY_IMPLEMENTED_FLIP_AS_SUBSTITUTE_FOR_THE_READ=true
LATER_R1_THAT_UNIQUELY_FLIPS_SOURCE_002_ROW_LEVEL_READ_IS_THIS_FAMILY_DETERMINISTIC_READER_ATTESTATION=true
FORBIDDEN_REWRITE_POPULATED_ORIGIN_FREEZE=true
FORBIDDEN_REWRITE_KG_READ_FREEZE=true
FORBIDDEN_RESOLVE_3_VS_7=true
FORBIDDEN_AUTHORIZE_S3_B_COVERAGE=true
FORBIDDEN_AUTHORIZE_S4=true
~~~

The user authorized issuance of the S3-A2 **accepted S2 TRAIN/VALIDATION
SOURCE_002 row-level-read** implementation grant after live contract authority
merged on main (#411). This document records what a **later** implementation R1
of this deterministic-reader-attestation family may do when the user again says
「可以实施」. This PR does not execute the deterministic reader, does not attest
official hashes from a live read, does not flip
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED`, does
not flip `SOURCE_002_ROW_LEVEL_READ`, does not land identity-set members, and does
not authorize production or test code mutation.

This is **SOURCE_002 row-level-read implementation** authorization only. Parent
freeze (#410), live contract authority (#411), kg-read family (#406–#409), origin
family (#402–#405), populated-origin closed family, C0 §5 pending snapshot, P0,
S3-B family, and A2 identity-set family remain authoritative and are not reopened.

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED=false
SOURCE_002_ROW_LEVEL_READ=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
TEST_REMAINS_SEALED=true
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
DO_NOT_INVENT_HASHES_OR_TONNES=true
THIS_FAMILY_IS_THE_DETERMINISTIC_READER_ATTESTATION_SLICE=true
THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true
NAMING_KG_READ_IMPLEMENTED_IS_NOT_SOURCE_002_ROW_LEVEL_READ=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=true
~~~

`S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true` ≠
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED` ≠
`SOURCE_002_ROW_LEVEL_READ` ≠ kg row-level read performed ≠ deterministic reader
ran ≠ official hashes attested from a live read ≠ members landed ≠
`NO_REVIEWED` flipped ≠ versioned forecast artifact produced ≠ `NO_VERSIONED`
flipped ≠ catalog bindable ≠ completeness verified ≠ backtest/attribution/metrics
computed ≠ S3-B coverage ≠ S4 ≠ TEST unsealed ≠ populated-origin
`FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY` rewritten ≠ C0 §5 `PENDING_NOT_MERGED`
rewritten. `#410` / `#411` contract-file fence
`S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false`
remains historical freeze snapshot; live authority is
`docs/v0-3/development-plan.md` §4.4.
Kg-read `IMPLEMENTED=true` ≠ kg actually read ≠ `SOURCE_002_ROW_LEVEL_READ`.
This grant does not authorize a docs-only `IMPLEMENTED` flip as a substitute
for the read. Unique live flip of `SOURCE_002_ROW_LEVEL_READ` requires a later
implementation R1 of **this** family that actually runs a deterministic reader
attesting TRAIN+VAL official content hashes — not this grant and not a
docs-only R1 alone. This evidence JSON is **not** a versioned forecast artifact,
completeness verified package, backtest package, metric results package, or
attribution matrix. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_FREEZE_WORKPAPER_GIT_BLOB_SHA=996999f95867d6af2711fc5913835bddad57fad1
S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_FREEZE_EVIDENCE_JSON_SHA256=dabd3f2fe0970ddcfb9411ade5f70f6dda33cfbe84d622510fe88b1363f19b2b
UNIQUE_REMAINING_GAP=_deterministic_reader_has_not_attested_train_val_official_content_hashes_from_a_live_read
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED=false
SOURCE_002_ROW_LEVEL_READ=false
~~~

SOURCE_002 row-level-read freeze (#410) and live contract authority (#411) are
on main. The deterministic reader has not attested TRAIN+VAL official content
hashes from a live read. This grant authorizes a **later** implementation R1 of
this family to perform that read and attestation — it does not perform that
execution today, does not flip `IMPLEMENTED`, and does not flip
`SOURCE_002_ROW_LEVEL_READ`.

## 2. Upstream bindings

~~~text
PARENT_CONTRACT_PR=410
PARENT_CONTRACT_MERGE=0ca99dec9a538fcfdc1d2ebe0bf6919d6b66d05b
PARENT_LIVE_AUTHORITY_PR=411
PARENT_LIVE_AUTHORITY_MERGE=17bff5d09c11c0a245f9b16d37d7a3bb30802dd5
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=1eddce85dfd6c49c4fbea674fb65b9a545d67ea2bba947b45eed11f46ea15f42
S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=39fb3b60123b62ca0c0c9d53a187d231ba97d2a7
CURRENT_S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_CONTRACT_GIT_BLOB_SHA=eb51f67d7b320fa494c02d165647b44b245f423a
S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_FREEZE_EVIDENCE_JSON_SHA256=dabd3f2fe0970ddcfb9411ade5f70f6dda33cfbe84d622510fe88b1363f19b2b
KG_READ_R1_EVIDENCE_JSON_SHA256=8dd8fc438b0b9252e68bea9a94f693c6e98e5e037fbecc87340c29a933832298
CURRENT_S3_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_CONTRACT_GIT_BLOB_SHA=95f91c1b97f5ba840da64c67ed79f5268ca20f3f
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_KG_ROW_LEVEL_READ_IMPLEMENTED=true
NAMING_KG_READ_IMPLEMENTED_IS_NOT_SOURCE_002_ROW_LEVEL_READ=true
ORIGIN_R1_EVIDENCE_JSON_SHA256=c29070e45ac887c882c3488d5e18efc0c1ed7dac9e633e9b0ece1c051c3606d7
CURRENT_S3_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_CONTRACT_GIT_BLOB_SHA=e4a2fc260e2bf135d246018473edfc89ba671787
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_LAWFUL_ORIGIN_IMPLEMENTED=true
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=e59f8a2d255df392116c65d535ae22ae3854ae98
CURRENT_S3_D_CONTRACT_GIT_BLOB_SHA=0819f429dcaf390a97a51a674ca96405eb8ebab7
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=bc5f134f4bbffcfabb43e3cff31c0d2f43463122
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=b39fb863c8d52daf347d94dc3339e408774596c7
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=bb5542473066301da163bd662eb863a2abaebb63
A1_WORKPAPER_GIT_BLOB_SHA=c8c8ed7540ce2ae36bf07127494a508256a813d6
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical pointer snapshots (#401 completeness, origin #402–#405, kg-read
#406–#409, freeze #410, live-authority #411, etc.) retain their own `CURRENT_*`
at insert time and must not be refreshed by this grant.

## 3. Frozen subsequent R1 procedure (execution not authorized in this grant)

The following checklist is frozen for a future separately authorized
implementation R1 pass of this family. This grant does not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm SOURCE_002 row-level-read freeze workpaper blob is still
   `996999f95867d6af2711fc5913835bddad57fad1` and freeze evidence content SHA256
   is still `dabd3f2fe0970ddcfb9411ade5f70f6dda33cfbe84d622510fe88b1363f19b2b`;
   live-authority evidence SHA256 is still
   `1eddce85dfd6c49c4fbea674fb65b9a545d67ea2bba947b45eed11f46ea15f42`.
3. Confirm SOURCE_002 row-level-read contract file top fence still contains
   `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false`
   (historical freeze snapshot; R1 must not rewrite fence).
4. Confirm contract top identity block `BASE_MAIN_SHA` is still
   `7a1f825fa537066437859cf5e87b61b88b55542b` and §13 historical `CURRENT_*`
   snapshots are not refreshed.
5. Confirm live §4.4 has `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_CONTRACT_AUTHORIZED=true`
   and `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true`.
6. Confirm contract §3 official hashes still match S2 acceptance package
   (reference only, do not recompute); TEST remains sealed. Official TRAIN
   `16224` / `be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2`;
   VAL `8006` / `4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06`;
   dataset `source-002` / `e5-live-v1` /
   `f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785`. Grain
   `SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE`. Label
   `actual_harvest_quantity_kg`. Months 1–4. Exclude 普鲜/普青/普冻/废果 and 巴松.
   `HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true`. Replay table
   `s3_incumbent_forecast_replay_identity` is not the harvest kg target.
7. Confirm populated-origin freeze `FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY`
   is not rewritten; C0 §5 `PENDING_NOT_MERGED` is not rewritten.
8. Must not invent hashes/tonnes/farm/date/cutoff lists, unseal TEST, flip
   `SOURCE_002_ROW_LEVEL_READ` / `NO_VERSIONED` / `NO_REVIEWED` / completeness
   verified in this grant, change C0/S3-D/metric STATUS, authorize S3-B coverage
   or S4, touch Python in this grant, mutate V0.2 formulas, flip §4.5, adjudicate
   3 vs 7, write `SELECT`/`FROM`/`JOIN`/`WHERE` or DSN strings, or treat H7 fixture
   `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18` as live
   evidence.
9. Legal unique live flip of `SOURCE_002_ROW_LEVEL_READ` is reserved for a later
   implementation R1 of **this** family that actually runs a deterministic reader
   attesting TRAIN+VAL official content hashes. This grant does not execute that
   R1. A later docs-only R1, if issued, must not flip `SOURCE_002_ROW_LEVEL_READ`
   and must not claim the reader ran. This grant leaves
   `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED=false`
   and `SOURCE_002_ROW_LEVEL_READ=false`.

### 3.2 Honest boundary

SOURCE_002 row-level-read freeze (#410) ≠ live-authority (#411) ≠ this grant ≠
execution R1 ≠ kg read ≠ `SOURCE_002_ROW_LEVEL_READ`.
`GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true`.
`GRANT_MERGE_DOES_NOT_EXECUTE_THE_DETERMINISTIC_READER=true`.
`GRANT_MERGE_DOES_NOT_ATTEST_OFFICIAL_HASHES_FROM_A_LIVE_READ=true`.
`THIS_FAMILY_IS_THE_DETERMINISTIC_READER_ATTESTATION_SLICE=true`.
`THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true`.
`THIS_GRANT_DOES_NOT_AUTHORIZE_A_DOCS_ONLY_IMPLEMENTED_FLIP_AS_SUBSTITUTE_FOR_THE_READ=true`.
`FORBIDDEN_REWRITE_POPULATED_ORIGIN_FREEZE=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`.

## 4. Six-file manifest

| # | path |
|---|------|
| 1 | `docs/v0-3/development-plan.md` |
| 2 | `docs/v0-3/s3/s3-daily-rowset-amendment.md` |
| 3 | `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` |
| 4 | `docs/v0-3/s3/s3-accepted-s2-train-val-source-002-row-level-read-contract.md` |
| 5 | `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-source-002-row-level-read-authorization.md` |
| 6 | `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-source-002-row-level-read-authorization.json` |

## 5. Unique flip

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=false → true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED=false (companion unchanged)
SOURCE_002_ROW_LEVEL_READ=false (unchanged)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and authorization pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §114 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` Live paragraph immediately before ## 12
- `docs/v0-3/s3/s3-accepted-s2-train-val-source-002-row-level-read-contract.md` §14 pointer

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=8ca597ad22b651f369e2d7b4c5667fb2f40c70bce7ac03780b13dbe9d3f1e8ca
~~~

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_EXECUTE_THE_DETERMINISTIC_READER=true
AWAITING_COORDINATOR_REVIEW=true
~~~
