# 每日事实层与峰值指标规范

本文档定义任务3的每日事实构建、峰值指标、节假日标签和幂等重建口径。任务3只做确定性的历史事实聚合与指标提取，不实现任何预测模型、残差模型、成熟曲线或前端页面。

## 1. 数据来源与范围

来源表：`fact_receipt_raw`

仅使用同时满足以下条件的 raw 行：

- `is_analysis_eligible = true`
- `receipt_date IS NOT NULL`
- `weight_kg IS NOT NULL`
- `weight_kg > 0`
- `factory_id IS NOT NULL`
- `variety_id IS NOT NULL`
- `id <= source_max_raw_id`

其中 `source_max_raw_id` 在构建开始时截取，构建全程只读取该快照之前的 raw 行，避免构建过程中新增导入破坏一致性。

如果出现 `is_analysis_eligible = true` 但 `factory_id` 或 `variety_id` 为空，视为 curated 一致性错误，构建必须失败并记录 `failed` 审计。

## 2. 分析月份与日历

任务3的月份范围来自 `configs/analytics_rules.yaml` 的 `analysis_months`，默认 `[1, 2, 3, 4]`。

对每个产季：

1. 先取 `dim_season.start_date .. dim_season.end_date` 的连续自然日；
2. 再保留 `month(date) in analysis_months` 的日期；
3. 对没有任何到果记录的日期显式补零：

```text
Y_t = 0
```

说明：

- 峰值滚动窗口必须建立在连续自然日历上；
- 不能把相隔多天的三个“观测日”当成连续3日；
- `calendar_day_count` 是分析日历天数；
- `observed_day_count` 是 `Y_t > 0` 的日期数量。

## 3. 每日事实粒度

`fact_receipt_daily` 的粒度为：

`build_run × season × receipt_date × factory × farm_key × subfarm_key × variety`

其中：

- `farm_key = normalize_text(farm_raw)`；
- `subfarm_key = normalize_text(subfarm_raw)`；
- 空值时分别替换为配置中的：
  - `unknown_farm_key`
  - `unknown_subfarm_key`

任务3不自动创建或映射 `dim_farm` / `dim_subfarm` 主数据。

## 4. 节假日与春节标签

节假日来源：`dim_holiday`

筛选规则：

- `season_id = 当前产季`
- `active = true`
- `start_date <= receipt_date <= end_date`
- `region_name IS NULL` 或 `region_name = dim_factory.region_name`

每日事实字段：

- `holiday_codes`：确定性的节假日代码列表，按代码排序去重；
- `is_spring_festival`：`holiday_codes` 与配置 `spring_festival_codes` 有交集时为 true。

重要限制：

- 春节日期保留在每日事实和峰值序列中；
- 不因春节标签删除日期；
- 不因春节标签强制将重量改为 0；
- 任务3只打标签，不实现采摘能力或积压释放。

## 5. 峰值序列定义

对每个 `season × factory`，先按分析日历构建稠密日序列：

```text
Y_t = 当日有效商品果到厂重量（kg）
```

### 5.1 单日峰值

```text
single_day_peak_kg = max(Y_t)
```

- 峰值日期：对应 `Y_t` 最大值日期；
- 并列时：取最早日期。

### 5.2 连续3日中位持续峰值

对每个同时存在前后邻日的中心日 `t`：

```text
stable_t = median(Y_(t-1), Y_t, Y_(t+1))
stable_median_3d_peak_kg = max(stable_t)
```

- 峰值日期记录中心日 `t`；
- 并列时取最早中心日；
- 首尾两天不形成完整3日窗口，不参与该指标。

### 5.3 连续3日均值峰值

```text
mean_t = (Y_(t-1) + Y_t + Y_(t+1)) / 3
mean_3d_peak_kg = max(mean_t)
```

- 峰值日期记录中心日 `t`；
- 并列时取最早中心日。

### 5.4 峰值集中度

统一定义为：

```text
peak_concentration = stable_median_3d_peak_kg / total_weight_kg
```

含义：持续峰值日均量占产季有效总量的比例。

只有 `total_weight_kg > 0` 时生成指标行。

## 6. HHI 定义

对每个 `season × factory`，在整个分析窗口内按有效总重量计算：

```text
HHI = Σ (group_weight / total_weight)^2
```

分别输出：

- `variety_hhi`
- `farm_hhi`
- `subfarm_hhi`

校验示例：

- 单一组独占全部重量：`HHI = 1`
- 两组各 50%：`HHI = 0.5`
- 50%、25%、25%：`HHI = 0.375`

`farm_key` / `subfarm_key` 为空时使用 UNKNOWN 键参与 HHI 分组，并同时输出：

- `unknown_farm_weight_share`
- `unknown_subfarm_weight_share`

## 7. 构建运行与版本追溯

每次构建写入 `analytics_build_run`：

- `season_id`
- `aggregation_version`
- `source_max_raw_id`
- `config_hash`
- `config_snapshot`
- `source_eligible_row_count`
- `source_eligible_weight_kg`
- `daily_fact_row_count`
- `status`
- `error_message`

追溯语义：

- 同一 build run 产出的 `fact_receipt_daily` 和 `factory_season_peak_metric` 都通过 `build_run_id` 回溯；
- 配置哈希来自 `analytics_rules.yaml` 的稳定 JSON 序列化；
- `config_snapshot` 只保存任务3分析配置，不复用任务2导入配置快照；
- 错误信息必须脱敏。

## 8. 幂等与重建

构建幂等键：

`season_id + aggregation_version + source_max_raw_id + config_hash`

规则：

- 已有 `completed`：直接返回已有结果；
- 已有 `running`：返回运行中状态；
- `failed`：允许重试；
- 新增 raw 行导致 `source_max_raw_id` 变化时必须创建新的 build run；
- 旧 build run 及其 daily facts / peak metrics 继续保留，支持历史对比。

数据库实现对同一幂等键使用 PostgreSQL 部分唯一索引限制最多一条 `running/completed` 记录，因此并发重复构建会回落到已存在运行态或完成态，而 `failed` 记录仍可保留并重试。

## 9. 事务边界

正式构建必须满足：

- build run 状态可审计；
- daily facts 与 peak metrics 在一个受控事务里完成；
- 失败不留下半套 daily facts / metrics；
- build run 即使失败也保留 `failed` 记录、`finished_at` 和已知摘要。

dry-run 行为：

- 不写 `analytics_build_run`
- 不写 `fact_receipt_daily`
- 不写 `factory_season_peak_metric`
- 仅输出计划构建摘要和峰值预览

## 10. 性能约束

任务3要支持约 40 万级 raw 行。

必须遵守：

- 使用固定批次或流式读取 raw 行；
- 批次大小来自 `stream_batch_size`；
- 不一次性加载全部 ORM 对象；
- 不进行逐行数据库查询；
- 节假日和工厂主数据预加载；
- daily facts 批量写入；
- 不对每一行单独 commit；
- Decimal 累计保持精度，不使用浮点累计。
