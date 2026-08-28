# Workpaper: accepted S2 train/val source-002 row-level read live-async-session-query contract freeze

**Branch:** `cursor/v03-s3-a2-accepted-s2-train-val-source-002-row-level-read-live-async-session-query-contract-8794`

**Task class:** `CONTRACT_DEFINITION_ONLY` — three new documentation files only.

---

## 1. Intent

Freeze the **already-obtained live `AsyncSession` queryability** slice after live-async-obtain R1 #441 merged with official path `obtained=false` / `FAIL_CLOSED_ASYNC_SESSION_UNREADABLE`.

**Analog chain:**
1. live-obtain R1 fail-closed → live-session-query freeze #422 (bound `Session` queryability)
2. live-async-obtain R1 fail-closed → **this** freeze (already-obtained `AsyncSession` queryability)

This is a **new family** — not live-async-obtain (#438–#441), not live-session-query (#422), not live-async-session (#434–#437).

---

## 2. Base pin

| Field | Value |
|---|---|
| `BASE_REF` | `origin/main` |
| `BASE_MAIN_SHA` | `f844204efe32868540050c2e31ff252c32ac41c4` |
| `BASE_MAIN_TREE_SHA` | `4ff6ae899d17d3a8d157dba396aae68c0679cb94` |
| `COORDINATOR_RUN` | `bc-01a02307-c032-7da6-8a02-00d9b3518794` |
| `LIVE_ASYNC_OBTAIN_R1_MERGE` | `f844204efe32868540050c2e31ff252c32ac41c4` |

---

## 3. Files delivered (exactly 3)

| # | Path |
|---|---|
| 1 | `docs/v0-3/s3/s3-accepted-s2-train-val-source-002-row-level-read-live-async-session-query-contract.md` |
| 2 | `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-source-002-row-level-read-live-async-session-query-contract.md` |
| 3 | `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-source-002-row-level-read-live-async-session-query-contract.json` |

**Not edited:** development-plan, amendment, P0, C0, Python, sibling contracts.

---

## 4. Uniqueness verification

| Boolean | Expected |
|---|---|
| `THIS_FAMILY_IS_THE_ALREADY_OBTAINED_LIVE_ASYNC_SESSION_QUERYABLE_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_LIVE_ASYNC_OBTAIN_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_BOUND_LIVE_SESSION_QUERYABLE_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_LIVE_ASYNC_SESSION_SLICE` | `true` |
| `THIS_FAMILY_IS_NOT_THE_LIVE_ASYNC_ENGINE_CONNECTION_SLICE` | `true` |
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

**Unique remaining gap:** `_already_obtained_live_async_session_is_not_asynchronously_queryable`

**Named fail-closed:** `FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE`

---

## 5. Fence (contract file)

| Gate | Value |
|---|---|
| `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_SESSION_QUERY_CONTRACT_AUTHORIZED` | `true` |
| `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED` | `false` |
| `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_ASYNC_SESSION_QUERY_IMPLEMENTED` | `false` |
| `DEVELOPMENT_PLAN_UNCHANGED` | `true` |

---

## 6. Future R1 sketch (not implemented)

**Probe:** `probe_accepted_s2_train_val_already_obtained_live_async_session_queryability`

1. Import `AsyncSessionMaker` from `backend.app.db.session`.
2. `async with live_async_session_maker() as session` inside `asyncio.run`.
3. Probe asynchronous queryability through that session.
4. Return envelope with `queryable: bool`.
5. Reason codes: `QUERYABLE`, `FAIL_CLOSED_NO_ASYNC_SESSION_MAKER`, `FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER`, `FAIL_CLOSED_ASYNC_SESSION_NOT_ASYNCHRONOUSLY_QUERYABLE`, `FAIL_CLOSED_ASYNC_SESSION_UNREADABLE`.

**Does not:** obtain content bytes, flip `SOURCE_002_ROW_LEVEL_READ`, use bound session provider, or use engine/connection escape hatches.

---

## 7. Sibling state at base

- live-async-obtain R1 landed service; `IMPLEMENTED=false`; gap `_accepted_s2_train_val_content_bytes_not_obtained_from_the_already_obtained_live_async_session`
- live-async-session R1 `IMPLEMENTED=true`; family gap closed
- live-session-query R1 `IMPLEMENTED=true` at `7a1047b2f9ea2d8ad9f6fc46e79cb2bf2f7768a4`
- `ASYNC_SESSION_OBTAINED_FROM_THE_ALREADY_CONFIGURED_LIVE_ASYNC_SESSION_MAKER=true` (not flipped false)

---

## 8. Evidence

Canonical JSON: `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-source-002-row-level-read-live-async-session-query-contract.json`

SHA256 computed per rule: `json.dumps(..., ensure_ascii=False, indent=2)+'\n'` excluding `evidence_json_sha256`, then field appended last.

**Evidence SHA256:** `be22789dd1c08c1f7aac77b43bc77e96ae3ff74d49846c39634a6700d121cc4c`
