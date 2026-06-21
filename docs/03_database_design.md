# 数据库与主数据设计

本文档定义任务1范围内的主数据模型。任务1只建立主数据表、ORM、迁移和 CRUD API，不创建历史事实表、预测表、天气表、人员表或模型运行表。

任务2增加历史 XLS 导入所需的 `ingest_file` 与 `fact_receipt_raw`。任务2不创建 `fact_receipt_daily`，不做峰值计算。

## 设计原则

- PostgreSQL 是约束来源，所有主键、唯一约束、外键和检查约束必须由 Alembic 迁移真实创建。
- SQLAlchemy ORM、Alembic 迁移和 `sql/schema.sql` 必须保持同一字段语义、数据类型和约束名称。修改任一层时必须同步另外两层。
- API 只返回 Pydantic schema，不直接暴露 SQLAlchemy 对象内部状态。
- 删除策略保守：外键默认限制删除，不使用级联删除清除未来事实数据。
- `factory` 和 `holiday` 支持 `active` 软停用；其他主数据允许 DELETE，但只有未被其他记录引用时才能删除。

## 表结构

### dim_season

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 非空，唯一 |
| start_date | DATE | 非空 |
| end_date | DATE | 非空，`end_date >= start_date` |

### dim_factory

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 唯一，可空 |
| name | TEXT | 非空，唯一 |
| region_name | TEXT | 可空 |
| latitude | NUMERIC(9,6) | 可空，`-90 <= latitude <= 90` |
| longitude | NUMERIC(9,6) | 可空，`-180 <= longitude <= 180` |
| altitude_m | NUMERIC(8,2) | 可空 |
| active | BOOLEAN | 非空，默认 true |

索引：`ix_dim_factory_active` 支持 `active` 列表过滤。

### dim_farm

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| name | TEXT | 非空，唯一 |
| latitude | NUMERIC(9,6) | 可空，`-90 <= latitude <= 90` |
| longitude | NUMERIC(9,6) | 可空，`-180 <= longitude <= 180` |
| altitude_m | NUMERIC(8,2) | 可空 |

### dim_subfarm

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| farm_id | BIGINT | 非空，外键到 `dim_farm.id`，限制删除 |
| name | TEXT | 非空 |
| altitude_m | NUMERIC(8,2) | 可空 |

唯一约束：`UNIQUE(farm_id, name)`。删除仍被分场引用的农场必须返回 409。

索引：`ix_dim_subfarm_farm_id` 支持按农场过滤分场。

### dim_variety

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 非空，唯一 |
| name | TEXT | 非空 |

任务1不插入正式品种清单。

### dim_grade

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 非空，唯一 |
| is_analysis_eligible_default | BOOLEAN | 非空，默认 true |

任务1不把“普鲜、普青、普冻、废果”等生产规则硬编码进迁移；后续导入规则通过配置和 curated 层处理。

### dim_holiday

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| season_id | BIGINT | 非空，外键到 `dim_season.id`，限制删除 |
| code | TEXT | 非空 |
| name | TEXT | 非空 |
| start_date | DATE | 非空 |
| end_date | DATE | 非空，`end_date >= start_date` |
| region_name | TEXT | 可空；空值表示全局节假日 |
| active | BOOLEAN | 非空，默认 true |
| created_at | TIMESTAMPTZ | 非空，默认 now() |
| updated_at | TIMESTAMPTZ | 非空，默认 now() |

唯一约束：`UNIQUE(season_id, code)`。

`dim_holiday` 只维护节假日时间窗口。春节采摘能力、积压释放和预测影响属于后续任务，不在任务1实现。

索引：`ix_dim_holiday_season_id`、`ix_dim_holiday_region_name`、`ix_dim_holiday_active` 支持节假日列表过滤。

## API

统一前缀：`/api/v1/master-data`

| 资源 | 路径 |
|---|---|
| seasons | `/api/v1/master-data/seasons` |
| factories | `/api/v1/master-data/factories` |
| farms | `/api/v1/master-data/farms` |
| subfarms | `/api/v1/master-data/subfarms` |
| varieties | `/api/v1/master-data/varieties` |
| grades | `/api/v1/master-data/grades` |
| holidays | `/api/v1/master-data/holidays` |

每类资源支持：

- `POST /` 创建，成功返回 201；
- `GET /` 列表，成功返回 200；
- `GET /{id}` 按 ID 查询，成功返回 200；
- `PATCH /{id}` 部分更新，成功返回 200；
- `DELETE /{id}` 删除，成功返回 204。

列表参数：

- `limit` 默认 50，最大 100；
- `offset` 默认 0；
- 默认按 `id ASC` 稳定排序；
- `factories` 支持 `active`；
- `subfarms` 支持 `farm_id`；
- `holidays` 支持 `season_id`、`region_name`、`active`。

错误返回：

- 资源不存在：404；
- 唯一约束冲突：409；
- 外键冲突或删除被引用数据：409；
- 输入校验失败：422；
- 不返回 SQL、连接串、密码或数据库异常原文。

创建不存在的 `farm_id`、`season_id` 等外键引用统一返回 409。

## ORM、Alembic 与 schema.sql 一致性

- ORM 模型位于 `backend/app/models/`，使用 SQLAlchemy 2 typed declarative API。
- Alembic 迁移位于 `backend/alembic/versions/`，是数据库结构的发布记录。
- `sql/schema.sql` 是面向评审和后续任务的参考 SQL，必须与当前 ORM 和最新 migration 保持一致。
- 新字段或约束必须同时更新 ORM、migration 和 `sql/schema.sql`，并用 PostgreSQL 集成测试验证。

## 任务2历史导入表

### ingest_file

记录源文件导入状态、文件 SHA、配置哈希、配置快照和质量报告。`file_sha256` 唯一，用于同一内容文件的正式导入幂等。`status` 限制为 `running`、`completed`、`failed`、`skipped`。`season_id` 可关联 `dim_season.id`，外键限制删除。

### fact_receipt_raw

append-only raw 层，保存每个源行的定位信息、原始字段、解析字段、归一化字段、主数据映射结果、质量标记、排除原因、解析错误和两类指纹。

- `source_row_fingerprint` 基于 `file_sha256|sheet_name|source_row_number`，唯一约束用于技术幂等。
- `business_fingerprint` 基于 `season|receipt_date|normalized_factory|normalized_farm|normalized_subfarm|normalized_variety|normalized_grade|round(weight_kg,6)`，只建立普通索引用于疑似业务重复识别。
- raw 层允许非法日期、未知工厂、未知品种、空重量、零重量和负重量入库；这些问题通过质量字段和 `is_analysis_eligible` 表达，不用数据库检查约束阻止。
- `fact_receipt_daily` 聚合延期到任务3。

## 任务3每日事实与峰值分析表

任务3从 `fact_receipt_raw` 的 curated 资格结果构建版本化每日事实，并计算按加工厂汇总的历史峰值指标。任务3不实现预测模型，只提供确定性的历史分析基座。

### analytics_build_run

记录一次按产季构建每日事实与峰值指标的运行。

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| season_id | BIGINT | 非空，外键到 `dim_season.id`，限制删除 |
| aggregation_version | TEXT | 非空 |
| source_max_raw_id | BIGINT | 非空 |
| config_hash | TEXT | 非空 |
| config_snapshot | JSONB | 非空 |
| status | TEXT | 非空，`running/completed/failed` |
| source_eligible_row_count | BIGINT | 非空，默认 0 |
| source_eligible_weight_kg | NUMERIC(18,6) | 非空，默认 0 |
| daily_fact_row_count | BIGINT | 非空，默认 0 |
| started_at | TIMESTAMPTZ | 非空，默认 now() |
| finished_at | TIMESTAMPTZ | 可空 |
| error_message | TEXT | 可空，必须脱敏 |

约束与索引：

- `ck_analytics_build_run_status`
- `ix_analytics_build_run_season_id`
- `ix_analytics_build_run_status`
- `ix_analytics_build_run_source_max_raw_id`
- 对 `(season_id, aggregation_version, source_max_raw_id, config_hash)` 建立运行态与完成态的 PostgreSQL 部分唯一索引，避免并发重复构建，同时允许 `failed` 记录重试。

幂等语义：

- 已有相同 `(season_id, aggregation_version, source_max_raw_id, config_hash)` 的 `completed` 结果时直接返回已有结果；
- 已有 `running` 结果时返回运行中状态；
- `failed` 结果允许重新构建；
- 新 raw 数据进入后，`source_max_raw_id` 变化，必须形成新的 build run。

### fact_receipt_daily

任务3的每日事实粒度：

`build_run × season × receipt_date × factory × normalized_farm_key × normalized_subfarm_key × variety`

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| build_run_id | BIGINT | 非空，外键到 `analytics_build_run.id`，限制删除 |
| season_id | BIGINT | 非空，外键到 `dim_season.id`，限制删除 |
| receipt_date | DATE | 非空 |
| factory_id | BIGINT | 非空，外键到 `dim_factory.id`，限制删除 |
| farm_key | TEXT | 非空 |
| subfarm_key | TEXT | 非空 |
| variety_id | BIGINT | 非空，外键到 `dim_variety.id`，限制删除 |
| weight_kg | NUMERIC(18,6) | 非空，`weight_kg > 0` |
| source_row_count | INTEGER | 非空，`source_row_count > 0` |
| holiday_codes | JSONB | 非空，有限代码列表 |
| is_spring_festival | BOOLEAN | 非空 |
| created_at | TIMESTAMPTZ | 非空，默认 now() |

唯一约束：

- `UNIQUE(build_run_id, season_id, receipt_date, factory_id, farm_key, subfarm_key, variety_id)`

索引：

- `ix_fact_receipt_daily_build_run_id`
- `ix_fact_receipt_daily_season_id`
- `ix_fact_receipt_daily_factory_id`
- `ix_fact_receipt_daily_receipt_date`
- `ix_fact_receipt_daily_season_factory_date (season_id, factory_id, receipt_date)`

### factory_season_peak_metric

粒度：`build_run × season × factory`

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| build_run_id | BIGINT | 非空，外键到 `analytics_build_run.id`，限制删除 |
| season_id | BIGINT | 非空，外键到 `dim_season.id`，限制删除 |
| factory_id | BIGINT | 非空，外键到 `dim_factory.id`，限制删除 |
| analysis_start_date | DATE | 非空 |
| analysis_end_date | DATE | 非空 |
| calendar_day_count | INTEGER | 非空 |
| observed_day_count | INTEGER | 非空 |
| total_weight_kg | NUMERIC(18,6) | 非空，`total_weight_kg > 0` |
| single_day_peak_kg | NUMERIC(18,6) | 非空 |
| single_day_peak_date | DATE | 非空 |
| stable_median_3d_peak_kg | NUMERIC(18,6) | 非空 |
| stable_median_3d_peak_date | DATE | 可空 |
| mean_3d_peak_kg | NUMERIC(18,6) | 非空 |
| mean_3d_peak_date | DATE | 可空 |
| peak_concentration | NUMERIC(12,10) | 非空，`0 <= value <= 1` |
| variety_hhi | NUMERIC(12,10) | 非空，`0 <= value <= 1` |
| farm_hhi | NUMERIC(12,10) | 非空，`0 <= value <= 1` |
| subfarm_hhi | NUMERIC(12,10) | 非空，`0 <= value <= 1` |
| unknown_farm_weight_share | NUMERIC(12,10) | 非空，`0 <= value <= 1` |
| unknown_subfarm_weight_share | NUMERIC(12,10) | 非空，`0 <= value <= 1` |
| spring_festival_day_count | INTEGER | 非空 |
| computed_at | TIMESTAMPTZ | 非空，默认 now() |

唯一约束：

- `UNIQUE(build_run_id, factory_id)`

说明：

- 只有分析窗口内 `total_weight_kg > 0` 的工厂生成指标行；
- 不为完全无数据的工厂伪造零指标；
- 峰值日期并列时取最早日期；
- 3日指标日期记录窗口中心日。
