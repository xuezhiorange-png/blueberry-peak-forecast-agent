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
| source_max_raw_id | BIGINT | 非空，当前 `season_id` 下的 `fact_receipt_raw.id` 最大值 |
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
- 当前产季有新 raw 数据进入后，`source_max_raw_id` 变化，必须形成新的 build run；
- 其他产季新增 raw 数据不得改变当前产季的幂等键。

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

## 任务4静态基线回测表

任务4基于任务3已持久化的 `factory_season_peak_metric` 做静态历史复现，不直接从 raw 或 daily 重新计算峰值、集中度或 HHI。

### baseline_backtest_run

记录一次基线回测运行。

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| model_version | TEXT | 非空 |
| config_hash | TEXT | 非空 |
| config_snapshot | JSONB | 非空 |
| source_signature | TEXT | 非空 |
| source_build_runs | JSONB | 非空 |
| evaluation_scheme | TEXT | 非空 |
| status | TEXT | 非空，`running/completed/failed` |
| random_seed | BIGINT | 非空 |
| result_row_count | BIGINT | 非空，默认 0 |
| started_at | TIMESTAMPTZ | 非空，默认 now() |
| finished_at | TIMESTAMPTZ | 可空 |
| error_message | TEXT | 可空，必须脱敏 |

索引与唯一约束：

- `ix_baseline_backtest_run_status`
- `ix_baseline_backtest_run_evaluation_scheme`
- 对 `(model_version, config_hash, source_signature, evaluation_scheme)` 建立 `running/completed` 部分唯一索引，保证同一幂等键最多一条活动或完成运行，同时允许 `failed` 重试。

### baseline_backtest_result

粒度：

`run × baseline_name × target_season × factory × fold_key`

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| run_id | BIGINT | 非空，外键到 `baseline_backtest_run.id`，限制删除 |
| baseline_name | TEXT | 非空，限制为 `previous_season_peak`、`volume_previous_concentration`、`ridge_structure`、`ridge_structure_factory_holdout` |
| target_season_id | BIGINT | 非空，外键到 `dim_season.id`，限制删除 |
| factory_id | BIGINT | 非空，外键到 `dim_factory.id`，限制删除 |
| previous_season_id | BIGINT | 可空，外键到 `dim_season.id`，限制删除 |
| fold_key | TEXT | 非空 |
| status | TEXT | 非空，`evaluated/excluded` |
| actual_stable_peak_kg | NUMERIC(18,6) | 可空 |
| predicted_stable_peak_kg | NUMERIC(18,6) | 可空 |
| absolute_error_kg | NUMERIC(18,6) | 可空 |
| signed_error_kg | NUMERIC(18,6) | 可空 |
| ape | NUMERIC(12,10) | 可空 |
| input_features | JSONB | 非空 |
| training_season_codes | JSONB | 非空 |
| model_metadata | JSONB | 非空 |
| exclusion_reason | TEXT | 可空 |
| created_at | TIMESTAMPTZ | 非空，默认 now() |

唯一约束：

- `UNIQUE(run_id, baseline_name, target_season_id, factory_id, fold_key)`

索引：

- `ix_baseline_backtest_result_run_id`
- `ix_baseline_backtest_result_baseline_name`
- `ix_baseline_backtest_result_target_season_id`
- `ix_baseline_backtest_result_factory_id`

## 任务5极简输入、位置解析与自动参数库

Task 5 新增位置参考、农业气候区、参数库版本、参数 observation、最小规划任务、参数推断运行和参数推断结果。

### dim_agro_climate_zone

- 主键：`id`
- 唯一约束：`(code, zone_version)`
- 检查约束：经纬度范围、海拔上下界、有效期合法
- 用途：位置解析后的农业气候区归属，不包含天气历史特征。

### climate_zone_import_run

- 主键：`id`
- 字段：`file_name`、`file_sha256`、`zone_version`、`source_name`、`source_version`
- 状态：`running`、`completed`、`failed`
- 统计：`row_count`、`valid_row_count`、`invalid_row_count`、`inserted_count`、`skipped_count`、`conflict_count`
- 审计：`report_json`、`error_message`、`started_at`、`finished_at`
- 用途：农业气候区 CSV 导入审计。失败导入保留审计，不覆盖已存在气候区。

### location_reference

- 主键：`id`
- 唯一约束：`(source_version, source_row_hash)`
- 外键：`farm_id -> dim_farm.id`、`subfarm_id -> dim_subfarm.id`、`climate_zone_id -> dim_agro_climate_zone.id`
- 检查约束：经纬度范围、有效期合法
- 索引：`address_normalized`、`climate_zone_id`
- 用途：地址、坐标、海拔与气候区解析参考。

### parameter_library_version

- 主键：`id`
- 唯一约束：`version_code`
- 部分唯一索引：`status=active` 时只能存在一个 active 版本
- 状态：`draft`、`active`、`retired`、`failed`

### parameter_observation

- 主键：`id`
- 唯一约束：`(library_version_id, source_row_hash)`
- 外键：`library_version_id`、`variety_id`、`farm_id`、`subfarm_id`、`location_reference_id`、`climate_zone_id`、`season_id`
- 参数类型固定：
  - `yield_kg_per_mu`
  - `marketable_rate`
  - `first_harvest_offset_days`
  - `maturity_peak_offset_days`
  - `maturity_width_days`
  - `maturity_skewness`
  - `harvest_realization_rate`
- 数值约束：
  - `yield_kg_per_mu > 0`
  - `0 <= marketable_rate <= 1`
  - `0 <= harvest_realization_rate <= 1`
  - `maturity_width_days > 0`
  - `sample_weight > 0`

### minimal_forecast_task

- 主键：`id`
- 唯一约束：`(input_hash, as_of_date)`
- 状态：`created`、`resolving_location`、`inferring_parameters`、`parameters_ready`、`failed`
- 保存原始输入与规范化输入，不保存最终预测结果。

### parameter_inference_run

- 主键：`id`
- 外键：`task_id -> minimal_forecast_task.id`、`library_version_id -> parameter_library_version.id`
- 状态：`running`、`completed`、`failed`
- PostgreSQL 部分唯一索引：
  `(input_hash, as_of_date, resolver_version, library_version_id, config_hash)`
  在 `status in ('running', 'completed')` 上唯一。

### parameter_inference_result

- 粒度：`run_id × variety_id × parameter_type`
- 唯一约束：`(run_id, variety_id, parameter_type)`
- 状态：`available`、`unavailable`
- JSONB 字段：`source_observation_ids`、`source_metadata`、`uncertainty_metadata`

### Task 5 API

- `POST /planning/tasks`
- `GET /planning/tasks/{task_id}`

返回状态只允许参数推断相关状态，不返回最终峰值预测。

## 任务6产量计划与物候表

Task 6 单独保存人工计划与物候版本，不覆盖 Task 5 自动参数结果。基础业务键统一为：

- `farm_id`
- `subfarm_id`（可空）
- `season_id`
- `variety_id`

### 有效区间与 as_of_date 语义

Task 6 统一使用半开区间 `[effective_from, effective_to)`。

历史时点查询必须同时满足：

- `available_at <= as_of_date`
- `effective_from <= as_of_date`
- `effective_to is null` 或 `as_of_date < effective_to`

因此未来才录入、未来才生效或已经失效的版本都不会被历史查询读到。

### farm_season_variety_plan

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| farm_id | BIGINT | 非空，外键到 `dim_farm.id`，限制删除 |
| subfarm_id | BIGINT | 可空，外键到 `dim_subfarm.id`，限制删除 |
| season_id | BIGINT | 非空，外键到 `dim_season.id`，限制删除 |
| variety_id | BIGINT | 非空，外键到 `dim_variety.id`，限制删除 |
| planted_area_mu | NUMERIC(18,6) | 非空，`>= 0` |
| expected_yield_kg_per_mu | NUMERIC(18,6) | 非空，`>= 0` |
| marketable_rate | NUMERIC(12,10) | 非空，`0 <= value <= 1` |
| tree_age_years | NUMERIC(8,2) | 可空，`>= 0` |
| pruning_date | DATE | 可空 |
| flowering_start_date | DATE | 可空 |
| flowering_peak_date | DATE | 可空 |
| flowering_end_date | DATE | 可空 |
| first_pick_date | DATE | 可空 |
| expected_total_marketable_kg | NUMERIC(18,6) | 可空，`>= 0` |
| version | INTEGER | 非空，`> 0` |
| effective_from | DATE | 非空 |
| effective_to | DATE | 可空，必须晚于 `effective_from` |
| available_at | DATE | 非空 |
| source_type | TEXT | 非空 |
| source_name | TEXT | 可空 |
| source_version | TEXT | 可空 |
| notes | TEXT | 可空 |
| row_hash | TEXT | 非空，唯一 |
| created_at | TIMESTAMPTZ | 非空，默认 `now()` |
| updated_at | TIMESTAMPTZ | 非空，默认 `now()` |

花期约束：

- `flowering_start_date <= flowering_peak_date`
- `flowering_peak_date <= flowering_end_date`

索引与唯一约束：

- `uq_farm_season_variety_plan_row_hash`
- `uq_farm_season_variety_plan_version_null_subfarm`
- `uq_farm_season_variety_plan_version_with_subfarm`
- `ix_farm_season_variety_plan_business_key`
- `ix_farm_season_variety_plan_subfarm_id`
- `ix_farm_season_variety_plan_effective_from`
- `ix_farm_season_variety_plan_effective_to`
- `ix_farm_season_variety_plan_available_at`
- `ix_farm_season_variety_plan_row_hash`

说明：

- `row_hash` 用于幂等写入；
- 同一业务键、同一版本号但内容不同返回 `version_conflict`；
- 同一业务键区间重叠返回 `effective_interval_conflict`；
- 派生总量使用 `面积 × 预计亩产 × 商品果率`，响应同时返回显式总量、派生总量和差异。

### production_plan_import_run

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| file_name | TEXT | 非空 |
| file_sha256 | TEXT | 非空 |
| source_version | TEXT | 可空 |
| status | TEXT | 非空，`running/completed/failed` |
| row_count | BIGINT | 非空，默认 0 |
| inserted_count | BIGINT | 非空，默认 0 |
| skipped_count | BIGINT | 非空，默认 0 |
| rejected_count | BIGINT | 非空，默认 0 |
| duplicate_count | BIGINT | 非空，默认 0 |
| unknown_farm_count | BIGINT | 非空，默认 0 |
| unknown_subfarm_count | BIGINT | 非空，默认 0 |
| unknown_season_count | BIGINT | 非空，默认 0 |
| unknown_variety_count | BIGINT | 非空，默认 0 |
| invalid_date_count | BIGINT | 非空，默认 0 |
| invalid_numeric_count | BIGINT | 非空，默认 0 |
| overlap_conflict_count | BIGINT | 非空，默认 0 |
| version_conflict_count | BIGINT | 非空，默认 0 |
| report_json | JSONB | 非空 |
| error_message | TEXT | 可空 |
| started_at | TIMESTAMPTZ | 非空，默认 `now()` |
| finished_at | TIMESTAMPTZ | 可空 |

用途：

- 记录 Task 6 CSV 导入审计；
- dry-run 不写该表；
- 正式导入采用明确的逐行拒绝策略，并保留全量统计。

## 任务7天气与物候时间轴表

任务7增加天气源、天气观测、农场到天气源映射、天气特征运行和基温搜索运行。Task 7 只提供确定性的天气与物候特征，不训练自然成熟曲线。

### weather_source_location

- 粒度：`provider_code × external_location_id × source_version`
- 字段：`provider_code`、`external_location_id`、`location_type(station/grid)`、`latitude`、`longitude`、`altitude_m`、`timezone_name`、`grid_resolution`、`valid_from`、`valid_to`、`row_hash`
- 约束：坐标范围校验、`valid_to >= valid_from`、`row_hash` 唯一、同一 provider/business key/source_version 唯一

### weather_daily_observation

- append-only，每条记录代表一个天气源在一个自然日的一次可见版本
- 字段：`observation_date`、`temperature_min_c`、`temperature_max_c`、`temperature_mean_c`、`temperature_mean_source`、`precipitation_mm`、`solar_radiation_mj_m2`、`available_at`、`quality_code`、`quality_flags`、`source_version`、`row_hash`
- 约束：`temperature_max_c >= temperature_min_c`、显式 mean 必须位于 min/max 之间、降雨和辐射不得为负
- 历史查询必须同时满足：
  - `available_at <= as_of_date`
  - `observation_date <= feature_date`
- 同一天多个可见版本按 `available_at DESC, source_version DESC, id DESC` 选择；若同优先级内容冲突，则返回 version conflict

### weather_import_run

- 审计天气位置、天气观测和显式映射的 CSV 导入
- `import_type` 限定为 `location / observation / mapping`
- `status` 限定为 `running / completed / failed`
- dry-run 零写入；正式导入保留文件 SHA、统计计数和质量报告

### location_weather_mapping

- 粒度：`location_reference × weather_source_location × mapping_version × available_at × valid_from`
- 字段：`mapping_method(explicit/nearest_station/nearest_grid)`、`distance_km`、`altitude_difference_m`、`mapping_score`、`confidence_level`、`config_hash`、`row_hash`
- 优先级：显式映射优先；自动映射再按 station/grid 配置优先级和评分选择
- 缺失海拔不得按 0 处理，只能返回 `NULL` 并降低可信度

### weather_feature_run

- 粒度：`plan_id × as_of_date × feature_date × mapping_row_hash × base_temperature_search_run_id × feature_version × config_hash`
- 字段：`input_snapshot`、`window_features`、`timeline_payload`、`weather_observation_ids`、`warnings`、`blockers`
- PostgreSQL 部分唯一索引保护 `running/completed/unavailable` 的幂等 source signature
- 相同输入和数据版本必须返回同一 run 或 skipped 结果

### base_temperature_search_run

- 粒度：`training_cutoff × scope_type × variety_id? × climate_zone_id? × anchor_event × target_event × config_hash × feature_version × training_sample_ids`
- 持久化候选基温集合、选中基温、评分方法、候选分数、样本数、distinct season 数和输入快照
- 数据不足时返回 `unavailable`，不得静默采用默认基温

## 任务8自然成熟曲线表

任务8新增自然成熟代理曲线训练、artifact 持久化和逐日预测结果。Task 8 只输出自然成熟量曲线，不引入 Task 9 的采摘能力、积压或到厂状态方程。

### maturity_model_run

- 粒度：`training_cutoff × source_signature × model_version × config_hash`
- 状态：`running / completed / failed / unavailable`
- 关键字段：
  - `config_snapshot`
  - `training_cutoff`
  - `source_signature`
  - `model_family`
  - `scope`
  - `sample_count`
  - `distinct_season_count`
  - `distinct_farm_count`
  - `distinct_subfarm_count`
  - `training_metrics`
  - `calibration_metrics`
  - `warnings`
  - `blockers`
  - `input_snapshot`
- PostgreSQL 部分唯一索引保护 `running/completed/unavailable` 的幂等训练 run。

### maturity_model_artifact

- 与 `maturity_model_run` 一对一
- 保存：
  - `artifact_hash`
  - `support_min_day`
  - `support_max_day`
  - `artifact_payload`
- `artifact_payload` 只允许 canonical JSON 类型，Decimal 以稳定字符串持久化，禁止写入原生 `Decimal`、`date`、`datetime` 或 dataclass。

### maturity_forecast_run

- 粒度：`plan_id × as_of_date × prediction date range × source_signature`
- 状态：`running / completed / failed / unavailable`
- 关键字段：
  - `model_run_id`
  - `artifact_id`
  - `location_reference_id`
  - `weather_mapping_id`
  - `base_temperature_search_run_id`
  - `expected_marketable_total_kg`
  - `expected_total_source`
  - `axis_mode`
  - `warnings`
  - `blockers`
  - `input_snapshot`
- `axis_mode` 限定为：
  - `observed_phenology_axis`
  - `calendar_proxy_axis`
- PostgreSQL 部分唯一索引保护 `running/completed/unavailable` 的幂等预测 run。

### maturity_daily_prediction

- 粒度：`forecast_run_id × prediction_date`
- 字段：
  - `phenology_coordinate_day`
  - `p50_kg`
  - `p80_kg`
  - `p90_kg`
  - `cumulative_p50_kg`
  - `cumulative_p80_kg`
  - `cumulative_p90_kg`
  - `curve_share`
  - `confidence_level`
  - `quality_flags`
- 约束：
  - `forecast_run_id + prediction_date` 唯一
  - 重量字段使用 `NUMERIC`
  - `quality_flags` 使用 JSONB 持久化稳定 flag 集
