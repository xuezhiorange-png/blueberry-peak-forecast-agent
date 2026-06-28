# Task 11 Phase 3 Design Amendment — Review 4587546667

## Baseline

| Item | Value |
|---|---|
| **Current HEAD** | `68fe416a89f81e9658d1b81b1d5a7dddb90bd96d` |
| **Branch** | `codex/task-11-rolling-backtest-orchestration` |
| **PR** | #22 (OPEN + Draft) |
| **Issue** | #21 (OPEN) |
| **Code changed** | NO |
| **Tests changed** | NO |
| **Migration created** | NO |
| **Commit created** | NO |
| **Push performed** | NO |
| **Working tree** | clean |

---

## Decision 1 — Attempt Ownership: Node-Level Attempt (方案 B)

### Chosen model

Node-level attempt.

### Rationale

1. 当前 `orchestrate_node()` 对每个 node 创建一个 attempt — 代码已经是 node 粒度
2. 所有 stage、blocker、Task 8/9/10 authority、outcome 都是 node 粒度
3. `ResolvedInput`、`AvailabilityAudit`、`DagSnapshot` 的 FK 都指向 `rolling_node_id` — 只有 attempt 表缺少这个 FK
4. 如果用 run-level attempt，需要额外的 child record（node execution record）来表达 node 级别状态，增加一张表的复杂度
5. Node-level 允许独立 retry — node 1 失败只重试 node 1，不重跑整个 run

### Current schema mismatch

```sql
RollingBacktestAttempt.rolling_run_id  -- 存在 ✓
RollingBacktestAttempt.rolling_node_id -- 缺失 ✗
UNIQUE (rolling_run_id, attempt_number) -- 跨 node 共享计数器 ✗
```

`orchestrate_node()` 每次调用 `create_execution_attempt(logical_run_id)`，3 个 node 产生 attempt 1/2/3…第二个 run 产生 attempt 4/5/6…attempt_number 是 run 级别的全局序列，无法区分哪个 attempt 属于哪个 node。

### Proposed schema (0013 migration — `rolling_backtest_attempt` ALTER)

```sql
-- Add node-level ownership
ALTER TABLE rolling_backtest_attempt
ADD COLUMN rolling_node_id BIGINT NOT NULL
  REFERENCES rolling_backtest_node(id) ON DELETE RESTRICT;

-- Change unique constraint from run-level to node-level
ALTER TABLE rolling_backtest_attempt
DROP CONSTRAINT uq_rolling_backtest_attempt_number;

ALTER TABLE rolling_backtest_attempt
ADD CONSTRAINT uq_rolling_backtest_attempt_number
  UNIQUE (rolling_node_id, attempt_number);

-- Add index
CREATE INDEX ix_rolling_backtest_attempt_node_id
  ON rolling_backtest_attempt(rolling_node_id);

-- PostgreSQL does not allow subqueries in CHECK constraints.
-- Instead, consistency is enforced at the repository layer
-- and verified by integrity reload (see § Cross-Column Tamper Tests).
```
**Design rule**: `attempt.rolling_run_id` MUST equal `node.rolling_run_id` at insert time. The repository `create_execution_attempt(node_id, run_id)` enforces this in a single query by loading the node and comparing before INSERT. Integrity reload verifies the invariant: `SELECT ... WHERE attempt.rolling_run_id != node.rolling_run_id` must return zero rows.

### Retain `rolling_run_id` redundant column

**YES** — 用于快速查询 run 下所有 attempts（`WHERE rolling_run_id = X`）和 integrity reload 时跨表 JOIN。一致性由 repository gate + integrity reload 保证。

### Prior-attempt rules

- `prior_attempt_id` 必须指向**同一 `rolling_node_id`** 的上一 attempt
- Integrity check: `prior.rolling_node_id = current.rolling_node_id`
- 跨 node 的 `prior_attempt_id` 被拒绝（`RollingBacktestAttemptConflictError`）

### Concurrency

- `SELECT ... FOR UPDATE` 锁定 `rolling_backtest_node` 行（而非 `rolling_backtest_run`）
- 同一 node 的并发 attempt 创建被 row lock 序列化
- 不同 node 的 attempt 创建可以并行

### Retry semantics

- 读取最后 terminal attempt:
  ```sql
  SELECT * FROM rolling_backtest_attempt
  WHERE rolling_node_id = :id
  ORDER BY attempt_number DESC
  LIMIT 1
  ```
- 检查最后 attempt 的 status 为 `failed` 或 `blocked`
- 创建新 attempt: `attempt_number = last.attempt_number + 1`, `prior_attempt_id = last.id`
- Node-selective retry: 只重试该 node，不影响其他 nodes

### Phase 2 repository impact

- `create_execution_attempt()` 签名需改为接受 `rolling_node_id` 参数
- 所有 attempt chain 验证需检查 `rolling_node_id` 一致性
- `_validate_attempt_chain()` 已检查 `prior.rolling_run_id == current.rolling_run_id`，需增加 `prior.rolling_node_id == current.rolling_node_id`

---

## Decision 2 — Stage History: Full Stage Event Table (方案 2)

### Chosen model

Full stage history — 新增 `rolling_backtest_stage_event` 表。

### Rationale

1. `current_stage` 只能证明当前（或最终）阶段，不能证明 8 个阶段是否全部执行
2. Phase 3 需要证明完整执行顺序的合规性（resolve → visibility → authority chain → task8 → task9 → task10 → finalize → integrity reload）
3. 审计需求：如果 attempt 在 stage 5 被 blocked，需要知道 stages 1-4 都成功完成
4. Retry 需要知道上次执行到哪个 stage 被阻断

### Proposed schema (0013 migration — NEW TABLE)

```sql
CREATE TABLE rolling_backtest_stage_event (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    attempt_id BIGINT NOT NULL,
    rolling_node_id BIGINT NOT NULL,
    sequence_number INTEGER NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    structured_error_code TEXT NULL,
    sanitized_diagnostics JSONB NULL,
    entered_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Foreign keys
    FOREIGN KEY (attempt_id)
      REFERENCES rolling_backtest_attempt(id) ON DELETE RESTRICT,
    FOREIGN KEY (rolling_node_id)
      REFERENCES rolling_backtest_node(id) ON DELETE RESTRICT,

    -- Uniqueness
    UNIQUE (attempt_id, sequence_number),
    UNIQUE (attempt_id, stage),

    -- Semantic constraints
    CHECK (sequence_number >= 1),
    CHECK (stage IN (
      'resolve_historical_inputs',
      'validate_visibility',
      'validate_authority_chain',
      'resolve_or_replay_task8',
      'resolve_or_replay_task9',
      'resolve_or_train_task10',
      'execute_task10_prediction',
      'finalize_orchestration_snapshot'
    )),
    CHECK (status IN ('running', 'completed', 'blocked', 'failed')),
    CHECK ((status = 'running') = (finished_at IS NULL)),
    CHECK ((status IN ('blocked', 'failed')) = (structured_error_code IS NOT NULL)),
    CHECK (status != 'running' OR structured_error_code IS NULL)
);

-- Indexes
CREATE INDEX ix_rolling_backtest_stage_event_attempt_id
  ON rolling_backtest_stage_event(attempt_id);
CREATE INDEX ix_rolling_backtest_stage_event_node_id
  ON rolling_backtest_stage_event(rolling_node_id);
```

### Sequence rules

- 每个 stage 有固定的 ordinal（1-8），不依赖数据库 `MAX()`:
  ```
  resolve_historical_inputs       → ordinal 1
  validate_visibility             → ordinal 2
  validate_authority_chain        → ordinal 3
  resolve_or_replay_task8         → ordinal 4
  resolve_or_replay_task9         → ordinal 5
  resolve_or_train_task10         → ordinal 6
  execute_task10_prediction       → ordinal 7
  finalize_orchestration_snapshot → ordinal 8
  ```
- `sequence_number = stage_ordinal` — 固定映射，并发安全，无需 row lock 计数。
- 每个 stage **在进入时插入**（status='running', entered_at=NOW(), finished_at=NULL）
- 每个 stage **在完成/失败时 UPDATE**（status='completed'/'blocked'/'failed', finished_at=NOW()）
- 失败 stage 只有一条 terminal event（status='blocked'/'failed'）

### Retry behavior

- 每次 attempt 创建全新的 event chain（sequence 从 1 开始）
- 旧 attempt 的 stage events 保留不修改
- 同一 attempt 内不可重复进入同一 stage（UNIQUE (attempt_id, stage) 约束）

### Concurrency

- 使用 `INSERT ... ON CONFLICT (attempt_id, stage) DO NOTHING` 防止重复插入
- `sequence_number` 由固定 stage ordinal 决定 — 无竞态条件
- 同一 attempt 的不同 stage 可并发写入（ordinal 互不冲突），每个 stage 之间通过 `ON CONFLICT` 保证幂等

### No-gap validation (integrity reload)

`UNIQUE (attempt_id, stage)` 只能证明**每个 stage 至多一条 record**，不能证明 stage 之间无 gap。

Integrity reload 必须实施 no-gap check:

```python
async def _validate_stage_continuity(
    session: AsyncSession,
    attempt_id: int,
    terminal_stage: str,
) -> None:
    """Verify no gaps in stage history for a given attempt."""
    rows = await session.execute(
        select(RollingBacktestStageEvent)
        .where(RollingBacktestStageEvent.attempt_id == attempt_id)
        .order_by(RollingBacktestStageEvent.sequence_number)
    )
    events = rows.scalars().all()

    if not events:
        raise RollingBacktestStageIntegrityError(
            f"attempt {attempt_id} has no stage events"
        )

    # Rule 1: sequence must start at 1
    if events[0].sequence_number != 1:
        raise RollingBacktestStageIntegrityError(
            f"attempt {attempt_id} first sequence is {events[0].sequence_number}, expected 1"
        )

    # Rule 2: sequence must be consecutive (1, 2, 3, ..., N)
    for i, event in enumerate(events):
        if event.sequence_number != i + 1:
            raise RollingBacktestStageIntegrityError(
                f"attempt {attempt_id} stage gap: expected seq {i+1} got {event.sequence_number}"
            )

    # Rule 3: all stages before terminal_stage must be non-running
    terminal_ordinal = STAGE_ORDINAL[terminal_stage]
    for event in events:
        if event.sequence_number < terminal_ordinal and event.status == "running":
            raise RollingBacktestStageIntegrityError(
                f"attempt {attempt_id} seq {event.sequence_number} still running "
                f"but terminal stage is {terminal_stage}"
            )

    # Rule 4: stages after terminal ordinal must not exist
    if any(e.sequence_number > terminal_ordinal for e in events):
        raise RollingBacktestStageIntegrityError(
            f"attempt {attempt_id} has stages beyond terminal {terminal_stage}"
        )
```

### Acceptance wording 修正

- **不再声称** "All 8 stages persisted" as a database claim
- **改为**: "All executed stages are documented in `rolling_backtest_stage_event`; stage continuity is verified by integrity reload (consecutive ordinals 1..N, no gaps); the `terminal_stage` ordinal defines the last executed stage; stages beyond that ordinal must not exist"

---

## Decision 3 — Task 9 Authority Path: Through Envelope Output

### Loader

```python
from backend.app.harvest_state.application import get_harvest_state_run_by_id

envelope: HarvestStateRunEnvelope = await get_harvest_state_run_by_id(
    session, run_id=task9_run_id
)
```

### Return type

`HarvestStateRunEnvelope` (`backend/app/schemas/harvest_state.py:11`)

```python
class HarvestStateRunEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    status: Literal["completed", "blocked"]
    result_hash: str
    config_hash: str
    created_at: datetime
    output: Task9ACompletedOutput | Task9ABlockedOutput
```

### Output path

`envelope.output` — discriminated union:
- `Task9ACompletedOutput` — has `source_ref_catalog`, `daily_pool_state_rows`, `daily_member_state_rows`, `cohort_transition_rows`, `future_arrival_schedule`, `mass_balance_result`, `continuity_result`, `resolved_parameter_snapshot`
- `Task9ABlockedOutput` — empty rows, `blockers` non-empty, `resolved_parameter_snapshot` may be None

### Source catalog path

```
envelope.output.source_ref_catalog: list[SourceRefCatalogEntry]
```

**NOT** `HarvestStateRun.source_ref_catalog` (ORM column — raw JSONB, may be stale)

**NOT** `envelope.source_ref_catalog` (not a direct field on envelope)

### Verification snapshot path

**NOT** `HarvestStateRun.verification_snapshot` — 该字段不存在于 ORM

**Path**: `Task9ARequest.task8_daily_predictions[].verification_snapshot`

```python
# Task 9 service encodes task8 daily predictions as source_ref_catalog entries
# Each Task8DailyPredictionInput has:
#   .source_ref: Task8PredictionSourceRef  — maturity IDs and hashes
#   .verification_snapshot: Task8PredictionVerificationSnapshot — per-row audit
```

**`Task8PredictionSourceRef`** (`backend/app/harvest_state/schemas.py:114`):

| Field | Type |
|---|---|
| `source_ref_type` | `Literal["TASK8_DAILY_PREDICTION"]` |
| `source_ref_schema_version` | `Literal["task9a-source-ref-v1"]` |
| `maturity_model_run_id` | `int` |
| `maturity_model_version` | `str` |
| `maturity_model_config_hash` | `str` |
| `maturity_model_source_signature` | `str` |
| `maturity_model_artifact_id` | `int` |
| `maturity_model_artifact_hash` | `str` |
| `maturity_forecast_run_id` | `int` |
| `maturity_forecast_source_signature` | `str` |
| `maturity_forecast_as_of_date` | `date` |
| `maturity_daily_prediction_id` | `int` |
| `prediction_date` | `date` |
| `forecast_quantile` | `ForecastQuantile` |
| `source_quantity_kg` | `NonNegativeBusinessDecimal` |
| `plan_id` | `int` |
| `location_reference_id` | `int` |
| `weather_mapping_id` | `int \| None` |
| `base_temperature_search_run_id` | `int \| None` |

**`Task8PredictionVerificationSnapshot`** (`backend/app/harvest_state/schemas.py:136`):

| Field | Type |
|---|---|
| `maturity_model_run_id` | `int` |
| `maturity_model_version` | `str` |
| `maturity_model_config_hash` | `str` |
| `maturity_model_source_signature` | `str` |
| `maturity_model_artifact_id` | `int` |
| `maturity_model_artifact_run_id` | `int` |
| `maturity_model_artifact_hash` | `str` |
| `maturity_forecast_run_id` | `int` |
| `maturity_forecast_run_status` | `Literal["completed","running","failed","unavailable"]` |
| `maturity_forecast_model_run_id` | `int` |
| `maturity_forecast_artifact_id` | `int` |
| `maturity_forecast_source_signature` | `str` |
| `maturity_forecast_as_of_date` | `date` |
| `maturity_forecast_prediction_start_date` | `date` |
| `maturity_forecast_prediction_end_date` | `date` |
| `maturity_daily_prediction_id` | `int` |
| `maturity_daily_prediction_forecast_run_id` | `int` |
| `prediction_date` | `date` |
| `farm_id` | `int` |
| `subfarm_id` | `int \| None` |
| `variety_id` | `int` |
| `plan_id` | `int` |
| `location_reference_id` | `int` |
| `p50_kg` | `NonNegativeBusinessDecimal` |
| `p80_kg` | `NonNegativeBusinessDecimal` |
| `p90_kg` | `NonNegativeBusinessDecimal` |

### Comparison sequence (完整逐项比对流程)

```
1. envelope = await get_harvest_state_run_by_id(session, run_id)

2. 验证 envelope.status == "completed"
   （blocked 输出只做 minimal 验证 — 验证 blocker codes non-empty）

3. 验证 envelope.result_hash — 从 envelope.output 的 canonical JSON 重新计算 SHA-256

4. 遍历 envelope.output.source_ref_catalog:
   a. Filter source_ref_type == "TASK8_DAILY_PREDICTION"
   b. 从 source_ref_payload 解析 Task8PredictionSourceRef

5. 对每个 TASK8_DAILY_PREDICTION catalog entry:
   a. 提取 maturity_model_run_id
      → 比对 Task 11 resolved Task 8 model run identity
   b. 提取 maturity_model_config_hash
      → 比对数据库 MaturityModelRun.config_hash（真实值）
   c. 提取 maturity_model_source_signature
      → 比对 MaturityModelRun.source_signature
   d. 提取 maturity_model_artifact_hash
      → 比对 MaturityModelArtifact.artifact_hash
   e. 提取 maturity_forecast_run_id
      → 比对 Task 11 resolved forecast run identity
   f. 提取 maturity_forecast_source_signature
      → 比对 MaturityForecastRun.source_signature

6. 从 envelope.output.input_snapshot 中恢复 Task8DailyPredictionInput 列表:
   a. 读取每个 verification_snapshot 中的 p50_kg, p80_kg, p90_kg
   b. 比对数据库 MaturityDailyPredictionModel rows 中的实际值
   c. 验证 prediction_date 匹配
   d. 验证 farm_id, subfarm_id, variety_id (scope)

7. 比对 Task 6 plan authority:
   a. 从 source_ref_catalog 找到 source_ref_type == "PARAMETER_SOURCE_REF" 条目
   b. 提取 plan_id → 比对 Task 11 resolved plan identity
   c. 比对 FarmSeasonVarietyPlan.row_hash vs catalog payload hash

8. 比对 Task 7 weather authority:
   a. 从 source_ref_catalog 找到 weather 相关条目
   b. 比对 WeatherFeatureRun.source_signature + config_hash

9. 比对 base-temperature/config authority:
   a. 从 source_ref_catalog 找到 base_temperature_search_run_id
   b. 比对 BaseTemperatureSearchRun.source_signature

10. 任一不一致返回 task9_task8_authority_mismatch blocker
```

### Child-count validation

- Completed output:
  - `len(daily_pool_state_rows) > 0`
  - `len(daily_member_state_rows) > 0`
  - `len(cohort_transition_rows) > 0`
  - `len(future_arrival_schedule) > 0`
- 比对 `HarvestStateRun` ORM 中的 counter 字段:
  - `pool_row_count`, `member_row_count`, `cohort_row_count`, `future_arrival_row_count`

### Hash validation helpers (复用现有)

```python
from backend.app.harvest_state.canonical import (
    canonical_decimal_string,    # Decimal → canonical string
    canonical_json_value,        # Any → JSON-serializable value
)
from backend.app.rolling_backtest.canonical import (
    sha256_payload,              # dict → SHA-256 hex
)
```

### Blocker codes

| Condition | Blocker Code |
|---|---|
| `envelope.status == "blocked"` | `task9_reuse_blocked_output` |
| `source_ref_catalog` 中缺少 TASK8_DAILY_PREDICTION 条目 | `task9_missing_task8_source_ref` |
| `maturity_model_config_hash` ≠ DB 真实值 | `task9_task8_model_config_mismatch` |
| `artifact_hash` ≠ DB 真实值 | `task9_task8_artifact_mismatch` |
| `forecast_source_signature` ≠ DB 真实值 | `task9_task8_forecast_mismatch` |
| `p50/p80/p90_kg` ≠ DB daily row 值 | `task9_task8_daily_prediction_mismatch` |
| `plan_id` 或 `row_hash` 不匹配 | `task9_task6_plan_authority_mismatch` |
| `weather source_signature` 不匹配 | `task9_task7_weather_authority_mismatch` |
| `base_temperature source_signature` 不匹配 | `task9_base_temperature_authority_mismatch` |
| `result_hash` 重算不匹配 | `task9_result_hash_mismatch` |

---

## Decision 4 — Minimal 0013 Migration

### Existing 0012 six-table capabilities

| Capability | Covered by | Status |
|---|---|---|
| Run canonical payload/hash | `rolling_backtest_run.canonical_payload(_hash)` | ✓ |
| Run status + execution mode | `rolling_backtest_run.{status,execution_mode}` | ✓ |
| Node canonical payload/hash | `rolling_backtest_node.canonical_payload(_hash)` | ✓ |
| Node scope/cutoff/season | `rolling_backtest_node.{scope,as_of_local_date,forecast_cutoff_at,season_id}` | ✓ |
| Attempt lifecycle (number, prior, status, stage) | `rolling_backtest_attempt.{attempt_number,prior_attempt_id,status,current_stage}` | ✓ |
| Blocker code + diagnostics | `rolling_backtest_attempt.{structured_error_code,sanitized_diagnostics}` | ✓ |
| Resolved input (source role/type, signature, hashes, ref) | `rolling_backtest_resolved_input` | ✓ |
| Availability audit (allowed/blocker, canonical payload, hash) | `rolling_backtest_availability_audit` | ✓ |
| DAG snapshot (immutable payload/hash) | `rolling_backtest_dag_snapshot` | ✓ |
| **Node-level attempt ownership** | — | ✗ |
| **Stage execution history** | — | ✗ |
| **Terminal orchestration outcome snapshot** | — | ✗ |

### What 0013 must add

1. ✅ `rolling_backtest_attempt.rolling_node_id` — 解决 attempt 归属模糊（Decision 1）
2. ✅ `rolling_backtest_stage_event` — 保存完整阶段历史（Decision 2）
3. ✅ `rolling_backtest_orchestration_snapshot` — 保存 terminal outcome snapshot

### What 0013 must NOT add

- ❌ New resolved-input table — 现有 `rolling_backtest_resolved_input` 已足够
- ❌ New audit table — 现有 `rolling_backtest_availability_audit` 已足够
- ❌ New DAG table — 现有 `rolling_backtest_dag_snapshot` 已足够
- ❌ New node table — 现有 `rolling_backtest_node` 已足够（identity 不变，outcome 不应修改 identity）

### Proposed NEW TABLE: `rolling_backtest_orchestration_snapshot`

```sql
CREATE TABLE rolling_backtest_orchestration_snapshot (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    attempt_id BIGINT NOT NULL,
    rolling_node_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    terminal_stage TEXT NOT NULL,
    fallback_mode TEXT NULL,
    blocker_code TEXT NULL,
    canonical_payload JSONB NOT NULL,
    canonical_payload_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Foreign keys
    FOREIGN KEY (attempt_id)
      REFERENCES rolling_backtest_attempt(id) ON DELETE RESTRICT,
    FOREIGN KEY (rolling_node_id)
      REFERENCES rolling_backtest_node(id) ON DELETE RESTRICT,

    -- Uniqueness
    UNIQUE (attempt_id),

    -- Semantic constraints
    CHECK (
      canonical_payload_hash ~ '^[0-9a-f]{64}$'
      AND canonical_payload_hash = lower(canonical_payload_hash)
    ),
    CHECK (
      status IN (
        'forecast_completed',
        'partially_completed',
        'completed',
        'blocked',
        'failed'
      )
    ),
    CHECK (
      terminal_stage IN (
        'resolve_historical_inputs',
        'validate_visibility',
        'validate_authority_chain',
        'resolve_or_replay_task8',
        'resolve_or_replay_task9',
        'resolve_or_train_task10',
        'execute_task10_prediction',
        'finalize_orchestration_snapshot'
      )
    ),
    CHECK ((status = 'blocked') = (blocker_code IS NOT NULL)),
    CHECK (status != 'blocked' OR blocker_code IS NOT NULL)
);

-- Indexes
CREATE INDEX ix_rolling_backtest_orch_snap_attempt_id
  ON rolling_backtest_orchestration_snapshot(attempt_id);
CREATE INDEX ix_rolling_backtest_orch_snap_node_id
  ON rolling_backtest_orchestration_snapshot(rolling_node_id);
```

### Redundant `rolling_node_id` design decision

`rolling_node_id` 同时出现在 `rolling_backtest_stage_event` 和 `rolling_backtest_orchestration_snapshot` 中，这是有意为之的**受控冗余**（controlled denormalization）：

- **保留理由**: 避免每次查询「某 node 的所有 stage events」时都需要 `JOIN rolling_backtest_attempt`；两个冗余列都可通过 FK 回推到 `rolling_backtest_node`。
- **一致性保证**: repository 在 INSERT 时显式传入 `rolling_node_id`（由 `attempt.rolling_node_id` 读取），与 `attempt_id` 同源。
- **Integrity reload 验证**: 加载后执行跨表校验:
  ```sql
  -- stage_event consistency
  SELECT se.id FROM rolling_backtest_stage_event se
  JOIN rolling_backtest_attempt a ON a.id = se.attempt_id
  WHERE se.rolling_node_id != a.rolling_node_id

  -- orchestration_snapshot consistency
  SELECT os.id FROM rolling_backtest_orchestration_snapshot os
  JOIN rolling_backtest_attempt a ON a.id = os.attempt_id
  WHERE os.rolling_node_id != a.rolling_node_id
  ```
  任一返回非空行 → `RollingBacktestAuthorityBindingError`。
- **Tamper test**: 直接 UPDATE `stage_event.rolling_node_id` 使其与 `attempt.rolling_node_id` 不一致 → integrity reload 必须检测并阻断。

### `terminal_stage` 不得与 stage history 双写漂移

`orchestration_snapshot.terminal_stage` 必须与 stage_event 中的 terminal 保持一致:

**设计**: `terminal_stage` 由最后一次 `stage_event` 的 `stage` 列推导，不得独立赋值。

Repository 在写入 orchestration_snapshot 时:
```python
# 1. 读取该 attempt 的最后一条 stage_event
last_event = await session.execute(
    select(RollingBacktestStageEvent)
    .where(RollingBacktestStageEvent.attempt_id == attempt_id)
    .order_by(RollingBacktestStageEvent.sequence_number.desc())
    .limit(1)
)
terminal_from_events = last_event.scalar_one().stage

# 2. 校验一致性
assert terminal_stage == terminal_from_events, (
    f"terminal_stage drift: snapshot says {terminal_stage}, "
    f"stage_event says {terminal_from_events}"
)

# 3. 写入时 terminal_stage 与 stage_event 同源
```

**Integrity reload** 交叉校验:
```python
snapshot_terminal = snapshot.terminal_stage
last_stage_event = events[-1].stage
if snapshot_terminal != last_stage_event:
    raise RollingBacktestStageIntegrityError(
        f"terminal_stage mismatch: snapshot={snapshot_terminal}, "
        f"stage_event={last_stage_event}"
    )
```

**交易边界**: snapshot INSERT 与 `finalize_attempt_status()` 必须在同一事务中，保证 terminal_stage 对 stage_event 的读取是在该事务快照内一致的。

### Why outcome cannot go in `rolling_backtest_node.canonical_payload`

- `rolling_backtest_node.canonical_payload` 是 **immutable identity** — 代表该 node 的语义合同，创建后不可变
- Outcome 是 **execution result** — 同一个 node 在不同 attempt 中可能产生不同 outcome（different resolved inputs, different Task 9 run, different blocker）
- Retry 需要保留每次 attempt 的独立 outcome — 如果放在 node 上，新 attempt 会覆盖旧 outcome

### Why outcome must be per-attempt

- 每次 retry 产生新 attempt，可能有不同的 resolved inputs、audits、Task 9/10 authority
- `UNIQUE (attempt_id)` 保证每个 attempt 只有一个 outcome snapshot
- 旧 attempt 的 snapshot 保留不修改（immutable once written）

### Retry outcome ownership

- Attempt 1 completed → `rolling_backtest_orchestration_snapshot` row with `attempt_id = 1`
- Attempt 2 (retry) blocked → new row with `attempt_id = 2`
- Both rows coexist, each with its own `canonical_payload_hash`

### Idempotent reload comparison

```python
# Reload: recompute outcome payload from NodeOrchestrationOutcome
recomputed = _compute_outcome_payload(outcome)
# Compare:
if sha256_payload(recomputed) != snapshot.canonical_payload_hash:
    raise RollingBacktestCanonicalParityError(
        "outcome snapshot hash mismatch on reload"
    )
# Match → idempotent
```

### Concurrent snapshot creation

- `INSERT INTO rolling_backtest_orchestration_snapshot (attempt_id, ...) VALUES (...)`
- `UNIQUE (attempt_id)` 约束阻止并发写入同一 attempt 的第二个 snapshot
- Snapshot MUST be written in the **same transaction** as `finalize_attempt_status()` — 避免 dangling snapshot

### Complete 0013 summary

| Change | Type | Table |
|---|---|---|
| ADD `rolling_node_id` column | ALTER | `rolling_backtest_attempt` |
| DROP UNIQUE `(rolling_run_id, attempt_number)` | ALTER | `rolling_backtest_attempt` |
| ADD UNIQUE `(rolling_node_id, attempt_number)` | ALTER | `rolling_backtest_attempt` |
| ADD FK `rolling_node_id` → `rolling_backtest_node.id` | ALTER | `rolling_backtest_attempt` |
| ADD CHECK `rolling_run_id` = node's `rolling_run_id` | ALTER | `rolling_backtest_attempt` |
| ADD INDEX `ix_rolling_backtest_attempt_node_id` | ALTER | `rolling_backtest_attempt` |
| CREATE TABLE | NEW | `rolling_backtest_stage_event` |
| CREATE TABLE | NEW | `rolling_backtest_orchestration_snapshot` |
| **No new resolved-input/audit/DAG tables** | — | — |

---

## Supplementary — Task 8 Derived Hash Schemas

### `task8-artifact-authority-v1` canonical payload

```json
{
    "schema_version": "task8-artifact-authority-v1",
    "model_semantic_identity": {
        "model_version": "<maturity_model_run.model_version>",
        "config_hash": "<maturity_model_run.config_hash>",
        "source_signature": "<maturity_model_run.source_signature>"
    },
    "artifact_hash": "<maturity_artifact.artifact_hash>",
    "support_min_day": "<maturity_artifact.support_min_day>",
    "support_max_day": "<maturity_artifact.support_max_day>",
    "artifact_payload": {}
}
```

**Excluded**: `id`, `run_id`, `created_at`

### `task8-daily-prediction-authority-v1` canonical payload

```json
{
    "schema_version": "task8-daily-prediction-authority-v1",
    "forecast_semantic_identity": {
        "source_signature": "<maturity_forecast.source_signature>"
    },
    "prediction_date": "YYYY-MM-DD",
    "phenology_coordinate_day": "<decimal_str>",
    "p50_kg": "<decimal_str>",
    "p80_kg": "<decimal_str>",
    "p90_kg": "<decimal_str>",
    "cumulative_p50_kg": "<decimal_str>",
    "cumulative_p80_kg": "<decimal_str>",
    "cumulative_p90_kg": "<decimal_str>",
    "curve_share": "<decimal_str>",
    "confidence_level": "<daily.confidence_level>",
    "quality_flags": ["sorted", "list"]
}
```

**Excluded**: `id`, `forecast_run_id`, `created_at`

### Decimal canonical string rules

复用 `backend/app/harvest_state/canonical.py` 中的 `canonical_decimal_string()`:

| Input | Output |
|---|---|
| `0` | `"0"` |
| `1.500` | `"1.5"` |
| `-0` | `"0"` (negative zero normalized) |
| `Decimal("3.14159")` | `"3.14159"` |

Pattern: `^(0|[-]?[1-9][0-9]*)(\.[0-9]+)?$`

### Date serialization

ISO 8601 `"YYYY-MM-DD"` format.

### Quality flags sorting

`sorted(daily.quality_flags)` — 确保确定性序列化。

### Hash helper location

新增于 `backend/app/rolling_backtest/canonical.py`:

```python
def task8_artifact_authority_hash(
    model: MaturityModelRun,
    artifact: MaturityModelArtifact,
) -> str:
    """Compute task8-artifact-authority-v1 hash."""
    ...

def task8_daily_prediction_authority_hash(
    forecast: MaturityForecastRun,
    daily: MaturityDailyPredictionModel,
) -> str:
    """Compute task8-daily-prediction-authority-v1 hash."""
    ...
```

---

## Supplementary — Task 6 Authority Rule

### `FarmSeasonVarietyPlan.available_at` is `date`

不得 cast 为 UTC datetime。

### Frozen authority rule

```sql
WHERE available_at <= node.as_of_local_date
  AND effective_from <= node.as_of_local_date
  AND (effective_to IS NULL OR node.as_of_local_date < effective_to)
  AND season_id = node.season_id
```

**验证字段**: `season_id`, `farm_id`, `subfarm_id`, `variety_id`, `version`, `row_hash`, `source_version`

### Multi-plan effective interval handling

| Question | Answer |
|---|---|
| 是否每个 target date 独立解析？ | YES — 每个 target date 独立查询合法 plan |
| 是否要求一个 plan 覆盖整个 forecast window？ | NO — window 内可使用不同 plan |
| 多个合法版本如何 deterministic resolve？ | `ORDER BY version DESC` 取最大 version |
| `available_at == as_of_date` 是否可见？ | YES — `<=` 包含等号 |

### Adapter fix

当前 adapter 使用 `ProductionPlanImportRun.finished_at`（导入时间），Phase 3A 修复为使用 `FarmSeasonVarietyPlan.available_at`（业务可用时间）。

---

## Supplementary — Task 7 JOIN Design

### Real JOIN chain

```sql
SELECT ...
FROM weather_feature_run wfr
JOIN location_reference lr
  ON lr.id = wfr.location_reference_id
JOIN location_weather_mapping lwm
  ON lwm.id = wfr.location_weather_mapping_id
JOIN weather_source_location wsl
  ON wsl.id = wfr.weather_source_location_id
JOIN weather_daily_observation wdo
  ON wdo.weather_source_location_id = wsl.id
WHERE wfr.finished_at <= :cutoff_datetime
  AND wfr.status = 'completed'
  AND lwm.available_at <= node.as_of_local_date
  AND lwm.valid_from <= wdo.observation_date
  AND (lwm.valid_to IS NULL OR wdo.observation_date <= lwm.valid_to)
  AND wdo.observation_date <= node.as_of_local_date
  AND wdo.available_at <= node.as_of_local_date
ORDER BY wfr.finished_at DESC, wfr.source_signature
LIMIT 20
```

### Node scope → location_reference_id 映射

`node.scope` JSONB 中包含 `location_reference_id`（或可推导的 `farm_id` → `LocationReference.farm_id`）

### Multi-observation ordering

同一日期、多个 station/grid:

```sql
ORDER BY wdo.available_at DESC, wdo.quality_code ASC
```

最新可用、最高质量优先。

### Station/grid conflict

不自动消除 — 产生 `ambiguous_weather_source` blocker，要求 caller 明确指定。

### Mapping version conflict

如果同一 `location_reference_id` 有多个 `LocationWeatherMapping`（不同 `mapping_version`）:

```sql
ORDER BY lwm.available_at DESC, lwm.mapping_version DESC
LIMIT 1
```

取最近可用的 mapping。

### Unavailable weather

如果 `WeatherFeatureRun.status == 'unavailable'` → 排除（WHERE clause 中 `status = 'completed'`）。

### Forecast cutoff datetime → local authority date

`node.forecast_cutoff_at` (datetime) → `node.as_of_local_date` (date) — 使用 node 已有的 `as_of_local_date` 字段。

---

## Supplementary — Phase 3B Rollback Strategy

### Forbidden

```
revert _build_task9a_request() to return None
```

### Allowed rollback

**方案 A**: revert 整个 Phase 3B implementation commit（回退到 Phase 3A commit）

**方案 B**: 保留 historical reuse capability，关闭 retrospective replay capability:

- 在 `config.execution_mode == ExecutionMode.RETROSPECTIVE_REPLAY` 时:
  - 不进入 `_build_task9a_request()`
  - 不调用 `execute_harvest_state_run()`
  - 返回稳定 typed blocker: `task9_replay_not_available`
- Attempt 正确终止为 `blocked`
- 不进入 Task 10
- 不产生假 Task 9 authority
- 不返回 `completed` 或 `partially_completed`
- `diagnostics = {"capability": "disabled", "reason": "retrospective_replay_not_implemented"}`

---

## Supplementary — PostgreSQL Migration, Integrity, Tamper, and Concurrency Test Requirements

### 0013 migration round-trip test

| Test | What | Assertion |
|---|---|---|
| `test_0013_migration_upgrade` | Alembic upgrade from 0012→0013 | Tables created, columns added, constraints active |
| `test_0013_migration_downgrade` | Alembic downgrade 0013→0012 | Tables dropped, columns removed, 0012 state restored |
| `test_0013_migration_idempotent_upgrade` | Upgrade twice | Second upgrade is no-op |
| `test_0013_migration_constraints` | Insert violating rows | All CHECK/UNIQUE/FK constraints reject |

### Attempt consistency tamper tests (0013)

| Test | Tamper | Expected |
|---|---|---|
| `test_attempt_node_id_run_id_mismatch` | Direct UPDATE `attempt.rolling_run_id` to wrong value | Integrity reload raises `RollingBacktestAuthorityBindingError` |
| `test_attempt_prior_cross_node` | UPDATE `prior_attempt_id` to point to different node | Integrity reload raises `RollingBacktestAttemptConflictError` |
| `test_attempt_duplicate_node_attempt_number` | INSERT same `(rolling_node_id, attempt_number)` | UNIQUE constraint violation |
| `test_attempt_missing_node_id` | INSERT with NULL `rolling_node_id` (if nullable by migration) | NOT NULL constraint violation |

### Stage event tamper tests (0013)

| Test | Tamper | Expected |
|---|---|---|
| `test_stage_event_gap` | DELETE stage_event with sequence=2 | Integrity reload's `_validate_stage_continuity` detects gap |
| `test_stage_event_non_consecutive` | UPDATE sequence_number to skip ordinal | Integrity reload detects non-consecutive sequence |
| `test_stage_event_first_not_one` | INSERT with sequence_number=3 first | Integrity reload detects first != 1 |
| `test_stage_event_beyond_terminal` | INSERT stage_event beyond terminal_stage ordinal | Integrity reload detects excess |
| `test_stage_event_still_running_before_terminal` | stage_event seq < terminal with status='running' | Integrity reload detects unfinished prior stage |
| `test_stage_event_duplicate_stage` | INSERT same (attempt_id, stage) twice | UNIQUE constraint violation |
| `test_stage_event_invalid_status` | INSERT status='invalid' | CHECK constraint violation |
| `test_stage_event_node_id_mismatch` | UPDATE `rolling_node_id` to wrong node | Integrity reload cross-table check detects |
| `test_stage_event_status_time_consistency` | UPDATE status='completed' without finished_at | CHECK `(status='running') = (finished_at IS NULL)` violation |

### Orchestration snapshot tamper tests (0013)

| Test | Tamper | Expected |
|---|---|---|
| `test_snapshot_terminal_stage_drift` | UPDATE `terminal_stage` to mismatch last stage_event | Integrity reload detects drift |
| `test_snapshot_node_id_mismatch` | UPDATE `rolling_node_id` to wrong node | Integrity reload cross-table check detects |
| `test_snapshot_blocker_without_blocked` | UPDATE `blocker_code` when status != 'blocked' | CHECK constraint violation |
| `test_snapshot_blocked_without_blocker` | UPDATE status='blocked', `blocker_code`=NULL | CHECK constraint violation |
| `test_snapshot_duplicate_attempt` | INSERT second snapshot for same attempt_id | UNIQUE constraint violation |
| `test_snapshot_canonical_hash_tamper` | UPDATE `canonical_payload` without updating hash | Integrity reload recomputes hash, detects mismatch |
| `test_snapshot_invalid_hash` | INSERT hash not lowercase SHA-256 | CHECK constraint violation |

### Concurrency tests (0013)

| Test | Scenario | Expected |
|---|---|---|
| `test_concurrent_attempt_creation_same_node` | Two transactions create attempt for same node_id simultaneously | Only one succeeds; `SELECT ... FOR UPDATE` serializes; second either waits then sees first, or fails on UNIQUE |
| `test_concurrent_stage_event_insert` | Two workers insert same stage for same attempt | `ON CONFLICT DO NOTHING` — one wins, other is no-op |
| `test_concurrent_snapshot_insert` | Two workers insert snapshot for same attempt | UNIQUE(attempt_id) blocks second; first succeeds |
| `test_concurrent_attempt_different_nodes` | Two transactions create attempts for different nodes | Both succeed (different `rolling_node_id` — no lock conflict) |
| `test_stage_event_within_same_transaction_as_attempt` | stage_event INSERT outside attempt's transaction | Allowed — but integrity reload verifies stage continuity; no partial-commit dependency |

### Integrity reload full-chain test

| Test | Assertion |
|---|---|
| `test_integrity_reload_all_checks_pass` | Happy path: all checks pass, no error raised |
| `test_integrity_reload_detects_any_tamper` | Run all tamper scenarios above in sequence, verify each is detected |

### 0013 ORM model test

| Test | Assertion |
|---|---|
| `test_stage_event_orm_roundtrip` | Create → commit → reload → all fields match |
| `test_orchestration_snapshot_orm_roundtrip` | Create → commit → reload → all fields match |
| `test_attempt_with_node_id_orm_roundtrip` | Create attempt with node_id → commit → reload → fields match |

---

## Phase Approval Readiness

| Phase | Status | Rationale |
|---|---|---|
| **Phase 3A** | ✅ Ready | 4 adapter placeholders identified, Task 6/7 authority timestamp fixes planned, adapter contract unchanged |
| **Phase 3B** | ✅ Ready | Task 9 authority path fully specified (HarvestStateRunEnvelope → output → source_ref_catalog), comparison sequence detailed, verification snapshot path from Task8DailyPredictionInput, 10 blocker codes defined |
| **Phase 3C** | ✅ Ready | 0013 migration frozen (1 ALTER + 2 NEW tables), outcome ownership per-attempt, stage history per-event, snapshot in same transaction as finalize |

---

## Final State

| Item | Value |
|---|---|
| **Code changed** | NO |
| **Tests changed** | NO |
| **Migration created** | NO |
| **Commit created** | NO |
| **Push performed** | NO |
| **PR marked Ready** | NO |
| **Merged** | NO |
| **Issue closed** | NO |
| **Task 12 started** | NO |
| **Working tree** | clean |
