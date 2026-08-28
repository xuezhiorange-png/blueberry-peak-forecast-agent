# Accepted S2 train/val source-002 row-level read live-async-session-query contract (S3 | v0-3)

**Contract-only.** This document freezes the **already-obtained live `AsyncSession` queryability** slice for accepted S2 train/val source-002 row-level read. It does **not** authorize implementation, does **not** grant live authority, and does **not** assert `SOURCE_002_ROW_LEVEL_READ=true`.

**Analog:** after live-obtain R1 fail-closed `FAIL_CLOSED_SESSION_UNREADABLE`, freeze **live-session-query** (#422) froze queryability of the **bound live `Session`** (not obtain). After live-async-obtain R1 #441 fail-closed `FAIL_CLOSED_ASYNC_SESSION_UNREADABLE`, **this** freeze defines queryability of the **already-obtained live `AsyncSession`** (not obtain, not session-from-maker alone).

**Base pin:** `origin/main` @ `f844204efe32868540050c2e31ff252c32ac41c4` (tree `4ff6ae899d17d3a8d157dba396aae68c0679cb94`). **Coordinator run:** `bc-01a02307-c032-7da6-8a02-00d9b3518794`.

**Evidence:** `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-source-002-row-level-read-live-async-session-query-contract.json`

---

## 1. Scope

| Field | Value |
|---|---|
| `TASK_CLASS` | `CONTRACT_DEFINITION_ONLY` |
| `CONTRACT_ONLY` | `true` |
| `THIS_PR_IS_NOT_A_GRANT` | `true` |
| `THIS_PR_IS_NOT_R1` | `true` |
| `THIS_PR_IS_NOT_LIVE_AUTHORITY` | `true` |
| `DEVELOPMENT_PLAN_UNCHANGED` | `true` |
| `LIVE_SECTION_4_4_INSERT_NOT_IN_THIS_PR` | `true` |
| `FORBIDDEN_EDIT_P0` | `true` |
| `FORBIDDEN_TOUCH_PYTHON` | `true` |
| `USER_GATE` | `授权` |
| `STANDING_OVERRIDE_NO_FURTHER_USER_GATES` | `true` |

This family is **not** live-async-obtain (#438 / live-auth #439 / grant #440 / R1 #441), **not** live-session-query (#422), **not** live-async-session (#434 / #435 / #436 / #437), **not** live-obtain, **not** live-connection, and **not** live-async-connection.

---

## 2. Uniqueness (do not invert)

| Boolean | Value |
|---|---|
| `THIS_FAMILY_IS_THE_ALREADY_OBTAINED_LIVE_ASYNC_SESSION_QUERYABLE_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_LIVE_ASYNC_OBTAIN_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_BOUND_LIVE_SESSION_QUERYABLE_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_LIVE_ASYNC_SESSION_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_LIVE_ASYNC_ENGINE_CONNECTION_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_LIVE_OBTAIN_SLICE_FOR_TRAIN_VAL_CONTENT_BYTES` | `true` |
| `THIS_FAMILY_MUST_NOT_CLOSE_LIVE_ASYNC_OBTAIN_UNIQUE_REMAINING_GAP` | `true` |
| `THIS_FAMILY_MUST_NOT_FLIP_LIVE_ASYNC_OBTAIN_IMPLEMENTED` | `true` |
| `THIS_FAMILY_MUST_NOT_REOPEN_LIVE_ASYNC_SESSION_UNIQUE_REMAINING_GAP` | `true` |
| `THIS_FAMILY_MUST_NOT_FLIP_LIVE_ASYNC_SESSION_IMPLEMENTED` | `true` |
| `THIS_FAMILY_MUST_NOT_CLOSE_LIVE_SESSION_QUERY_UNIQUE_REMAINING_GAP` | `true` |
| `THIS_FAMILY_MUST_NOT_FLIP_LIVE_SESSION_QUERY_IMPLEMENTED` | `true` |
| `THIS_FAMILY_MUST_NOT_CLOSE_LIVE_OBTAIN_UNIQUE_REMAINING_GAP` | `true` |
| `THIS_FAMILY_MUST_NOT_FLIP_LIVE_OBTAIN_IMPLEMENTED` | `true` |
| `THIS_FAMILY_MUST_NOT_UNIQUELY_FLIP_SOURCE_002_ROW_LEVEL_READ` | `true` |
| `PARENT_FAMILY_HOLDS_UNIQUE_LIVE_FLIP_OF_SOURCE_002_ROW_LEVEL_READ` | `true` |

**Unique remaining gap (this family):** `_already_obtained_live_async_session_is_not_asynchronously_queryable`

**Named fail-closed (this family):** `FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE`

Distinct from:
- live-session-query: `FAIL_CLOSED_SESSION_NOT_SYNCHRONOUSLY_QUERYABLE`
- live-async-obtain: `FAIL_CLOSED_ASYNC_SESSION_UNREADABLE` (obtain path; not this family's unique gap)
- live-obtain: `FAIL_CLOSED_SESSION_UNREADABLE`

---

## 3. Fence (this contract file only)

| Gate | Value |
|---|---|
| `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_SESSION_QUERY_CONTRACT_AUTHORIZED` | `true` |
| `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED` | `false` |
| `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_SESSION_QUERY_IMPLEMENTED` | `false` |

`DEVELOPMENT_PLAN_UNCHANGED=true` — live §4.4 is **not** inserted in this PR.

---

## 4. Future R1 probe (WHAT/HOW only — no Python in this PR)

**Function:** `probe_accepted_s2_train_val_already_obtained_live_async_session_queryability`

**Session source:**
- Import `AsyncSessionMaker` from `backend.app.db.session` (`SESSION_PY` blob `49845a077d252af2a7a246fa25616d7595535037`).
- `async with live_async_session_maker() as session` inside `asyncio.run`.
- Through **that** already-obtained `AsyncSession`, probe whether it is **asynchronously queryable**.

**Forbidden paths:**
- Do **not** use `bound_source_002_row_level_read_session_provider`.
- Do **not** use `engine.connect()`, `session.connection()`, `bind.connect()`, `get_bind()`, or synchronous bridge helpers.
- Do **not** invent a DSN or call `create_engine` / `create_async_engine` / `async_sessionmaker` in probe code.

**Envelope field:** `queryable: bool` (**not** `obtained`).

**Always false at envelope root:**
- `source_002_row_level_read=false`
- `official_hashes_attested_from_a_live_read=false`
- `accepted_s2_train_val_content_bytes_obtained_from_bound_live_session=false`
- `accepted_s2_train_val_content_bytes_obtained_from_the_already_obtained_live_async_session=false`

**Reason codes (closed set):**
- `QUERYABLE`
- `FAIL_CLOSED_NO_ASYNC_SESSION_MAKER`
- `FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER`
- `FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE` (this family's unique remaining-gap reason)
- `FAIL_CLOSED_ASYNC_SESSION_UNREADABLE` (analog to live-session-query `FAIL_CLOSED_SESSION_UNREADABLE` during queryability probe — **not** this family's unique gap)

**TEST:** remains sealed (`row_count=0`, `byte_count=240`, hash `bd3d846a300c70a638bc169a095c3b02cb9e20c2c2aa6a96af0990d85a1fb1bd`).

**Semantic separation:**
- Queryable `AsyncSession` ≠ TRAIN/VAL `content_bytes` obtained
- Queryable `AsyncSession` ≠ `SOURCE_002_ROW_LEVEL_READ`
- `AsyncSession` from `AsyncSessionMaker` ≠ queryable already-obtained live `AsyncSession` ≠ content_bytes from that `AsyncSession`

---

## 5. Sibling honesty at base (copy; do not smash)

| Field | Value |
|---|---|
| `LIVE_SESSION_PROVIDER_BOUND` | `true` |
| `DEFAULT_SESSION_PROVIDER_UNSET` | `false` |
| `LIVE_SESSION_FAMILY_UNIQUE_REMAINING_GAP_CLOSED` | `true` |
| `LIVE_ASYNC_SESSION_FAMILY_UNIQUE_REMAINING_GAP_CLOSED` | `true` |
| `ASYNC_SESSION_OBTAINED_FROM_THE_ALREADY_CONFIGURED_LIVE_ASYNC_SESSION_MAKER` | `true` |
| `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_SESSION_IMPLEMENTED` | `true` |
| `LIVE_ASYNC_OBTAIN_SERVICE_LANDED` | `true` |
| `ACCEPTED_S2_TRAIN_VAL_CONTENT_BYTES_OBTAINED_FROM_THE_ALREADY_OBTAINED_LIVE_ASYNC_SESSION` | `false` |
| `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_OBTAIN_IMPLEMENTED` | `false` |
| `LIVE_ASYNC_OBTAIN_FAMILY_IS_NOT_CLOSED` | `true` |
| `LIVE_ASYNC_OBTAIN_UNIQUE_REMAINING_GAP` | `_accepted_s2_train_val_content_bytes_not_obtained_from_the_already_obtained_live_async_session` |
| `LIVE_ASYNC_OBTAIN_THROUGH_ALREADY_OBTAINED_ASYNC_SESSION_REASON_CODE` | `FAIL_CLOSED_ASYNC_SESSION_UNREADABLE` |
| `SYNTHETIC_OBTAINED_UNIT_PATH_IS_NOT_OFFICIAL_LIVE_ASYNC_OBTAIN` | `true` |
| `LIVE_OBTAIN_UNIQUE_REMAINING_GAP` | `_accepted_s2_train_val_content_bytes_not_obtained_from_the_bound_live_session` |
| `LIVE_SESSION_QUERY_UNIQUE_REMAINING_GAP` | `_bound_live_session_is_not_synchronously_queryable` |
| `LIVE_CONNECTION_UNIQUE_REMAINING_GAP` | `_sync_connection_not_obtained_from_the_bound_live_session_bind` |
| `LIVE_ASYNC_CONNECTION_UNIQUE_REMAINING_GAP` | `_async_connection_not_obtained_from_the_already_configured_live_async_engine` |
| `SOURCE_002_ROW_LEVEL_READ` | `false` |
| `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED` | `false` |

**Sibling R1 merges (historical pins):**
- `LIVE_CONNECTION_R1_MERGE` = `7f2011cb8c6b8ff2bcf6a41c3591426698ba9b52`
- `LIVE_ASYNC_CONNECTION_R1_MERGE` = `cee1111da505cf6969c1c2b9b29410da7dbc779b`
- `LIVE_ASYNC_SESSION_R1_MERGE` = `30ee96a018ea12ebc80ec38fc15d664bb341bdac`
- `LIVE_SESSION_QUERY_R1_MERGE` = `7a1047b2f9ea2d8ad9f6fc46e79cb2bf2f7768a4`
- `LIVE_ASYNC_OBTAIN_R1_MERGE` = `f844204efe32868540050c2e31ff252c32ac41c4`

---

## 6. Base blob pins (copy; do not recompute)

| Artifact | Git blob SHA |
|---|---|
| `CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA` | `e1d669ecd7f2c5c13a9e76af081eed437716f261` |
| `CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA` | `5974641706f6591c3386197c5d54e1f742afc45f` |
| `CURRENT_P0_CONTRACT_GIT_BLOB_SHA` | `ee3992c70722573e559f38406447b4ea83052578` |
| `C0` | `e59f8a2d255df392116c65d535ae22ae3854ae98` |
| `CURRENT_LIVE_ASYNC_OBTAIN_CONTRACT` | `cbb9003d2abafc702cf5357fe1417b0bf25d1f98` |
| `CURRENT_LIVE_ASYNC_SESSION_CONTRACT` | `12c9ab7fc7593a70e080bbdb97eb00a5d7b0e7d8` |
| `CURRENT_LIVE_SESSION_QUERY_CONTRACT` | `82bc9f2f8816c7ed0813c095d8ebf79703476a8e` |
| `LIVE_ASYNC_OBTAIN_PY` | `01f0e6e75f527514c5a08208f91eaec99a0154d1` |
| `LIVE_ASYNC_OBTAIN_TEST` | `b40cba70f8947954d95557523f9573cf5bc6d357` |
| `LIVE_ASYNC_SESSION_PY` | `40afc94dacb2208accd4903b12ae46152a750b41` |
| `LIVE_SESSION_QUERY_PY` | `d6a082dcabd7fbd1db324fd8ba6153ea2240fe39` |
| `SESSION_PY` | `49845a077d252af2a7a246fa25616d7595535037` |
| `LANDED_ASYNC_SESSION_MAKER_MODULE` | `backend/app/db/session.py` |
| `LANDED_ASYNC_SESSION_MAKER` | `AsyncSessionMaker` |

**Official hashes (TRAIN / VAL / dataset):**
- TRAIN: `row_count=16224`, hash `be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2`, `byte_count=9087071`
- VAL: `row_count=8006`, hash `4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06`, `byte_count=4484905`
- dataset source-002 / e5-live-v1: `f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785`

**Sibling evidence SHA256 (do not replace):**
- live-async-obtain freeze: `6d08f1ab5a12694fd1dba2e13d244b1ff5faf87a1a5db598397b4c4439cdd547`
- live-async-obtain live-auth: `1528c97699005595acbcd96996d85ecf107938e346a6930dbd74e261e0ec8aa3`
- live-async-obtain grant: `b68bf69bb9122146a611bd0a4630a591bf6094ac037fd8d1972f3d718a0f8f80`
- live-async-obtain R1: `ac4b203fe772f5d560127691bf3fce174b8ea457f01ab0ddd2cb91e210b6ec37`

**H7 fixture** `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18` is **not** live evidence.

---

## 7. Forbidden rewrites

| Flag | Value |
|---|---|
| `FORBIDDEN_REWRITE_LIVE_ASYNC_OBTAIN_FREEZE_IDENTITY` | `true` |
| `FORBIDDEN_REWRITE_LIVE_ASYNC_OBTAIN_FREEZE_FENCE` | `true` |

live-async-obtain freeze #438 historical `BASE_MAIN_SHA=30ee96a018ea12ebc80ec38fc15d664bb341bdac` remains unchanged.
