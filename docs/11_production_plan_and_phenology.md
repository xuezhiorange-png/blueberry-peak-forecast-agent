# Task 6 产量计划与物候数据

## 目标

Task 6 为后续天气、成熟曲线与峰值预测提供版本化的人工计划与物候输入。当前任务只负责：

- 计划录入；
- 历史版本保存；
- `as_of_date` 查询；
- CSV 批量导入；
- 审计与来源追踪；
- API 与 CLI。

Task 6 不实现天气、成熟曲线训练、逐日预测、峰值预测或 Task 7 以后的编排逻辑。

## 业务粒度

基础业务键：

- `farm_id`
- `subfarm_id`（可空）
- `season_id`
- `variety_id`

同一业务键允许存在多个历史版本，但任一 `as_of_date` 只能解析出一个有效版本。

## 表结构

### farm_season_variety_plan

主字段：

- `planted_area_mu`
- `expected_yield_kg_per_mu`
- `marketable_rate`
- `tree_age_years`
- `pruning_date`
- `flowering_start_date`
- `flowering_peak_date`
- `flowering_end_date`
- `first_pick_date`
- `expected_total_marketable_kg`

版本字段：

- `version`
- `effective_from`
- `effective_to`
- `available_at`
- `source_type`
- `source_name`
- `source_version`
- `row_hash`

审计字段：

- `notes`
- `created_at`
- `updated_at`

### production_plan_import_run

导入审计表，记录：

- 文件名与 SHA256；
- 行数、插入数、跳过数、拒绝数；
- 未知主数据、非法数值、非法日期、版本冲突、区间冲突统计；
- JSON 审计报告；
- `running/completed/failed` 状态。

## 单位与 Decimal 精度

- `planted_area_mu`: `NUMERIC(18,6)`
- `expected_yield_kg_per_mu`: `NUMERIC(18,6)`
- `marketable_rate`: `NUMERIC(12,10)`
- `expected_total_marketable_kg`: `NUMERIC(18,6)`
- `tree_age_years`: `NUMERIC(8,2)`

所有业务计算均使用 `Decimal`，不使用二进制 `float` 参与累计。

## 总商品果量公式

派生总商品果量：

`derived_total_marketable_kg = planted_area_mu × expected_yield_kg_per_mu × marketable_rate`

响应中同时返回：

- 用户显式录入的 `expected_total_marketable_kg`
- 系统派生的 `derived_total_marketable_kg`
- 二者差异 `total_difference_kg`

差异阈值由 `configs/production_plan.yaml` 控制。当前策略为超过容差时返回 warning，不静默覆盖用户显式值。

## 有效区间语义

Task 6 统一采用半开区间：

`[effective_from, effective_to)`

即：

- `effective_from <= as_of_date`
- `effective_to is null` 或 `as_of_date < effective_to`

这样替代版本可用新版本的 `effective_from` 直接关闭旧版本，不产生边界重叠。

## effective_from 与 available_at 的区别

- `effective_from`: 业务上计划何时开始生效
- `available_at`: 系统在何时实际获得该版本

历史查询必须同时满足两者，防止使用预测时点之后才录入或生效的未来版本。

## as_of_date 防未来泄漏

历史时点查询只返回同时满足以下条件的版本：

- `available_at <= as_of_date`
- `effective_from <= as_of_date`
- `effective_to is null` 或 `as_of_date < effective_to`

因此：

- 未来才 available 的版本不可见；
- 未来才 effective 的版本不可见；
- 已在 `as_of_date` 前失效的版本不可见；
- 若脏数据导致多条版本同时可见，服务返回 conflict，不任意挑选。

## 幂等规则

`row_hash` 覆盖：

- 业务键
- 计划字段
- 物候字段
- `version`
- `effective_from`
- `effective_to`
- `available_at`
- 来源字段

行为：

- 同一 `row_hash` 重复提交返回已有记录；
- 同一业务键同一 `version` 但内容不同返回 `version_conflict`；
- 生效区间重叠返回 `effective_interval_conflict`。

## 冲突规则

- 版本号冲突：同一业务键已有相同 `version`
- 区间冲突：同一业务键两个版本的有效区间重叠
- 读取冲突：同一 `as_of_date` 下解析出多个有效版本

## CSV 导入

CLI：

```bash
uv run python scripts/import_production_plans.py \
  --file data/templates/production_plans.csv \
  --dry-run
```

导入器支持：

- dry-run 零写入；
- 文件 SHA256；
- row hash 幂等；
- 未知主数据统计；
- 非法日期与非法数值统计；
- 版本冲突与区间冲突统计；
- 完整 JSON 审计报告。

## API

Task 6 当前暴露：

- `POST /planning/production-plans`
- `GET /planning/production-plans/{plan_id}`
- `GET /planning/production-plans/history`
- `GET /planning/production-plans/effective`
- `POST /planning/production-plans/{plan_id}/replace`

## 与 Task 5 的边界

Task 5 自动参数与 Task 6 人工计划分开保存。Task 6 不会：

- 修改 `ParameterInferenceRun`
- 修改 `ParameterInferenceResult`
- 覆盖 `parameters_ready`
- 自动触发 Task 5 推断

Task 7 和 Task 8 将消费 Task 6 的唯一有效计划版本，但本轮不实现该消费逻辑。
