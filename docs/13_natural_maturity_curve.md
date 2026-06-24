# Task 8：自然成熟曲线模型

## 目标

Task 8 只建模 `season × farm/subfarm × variety` 粒度的自然成熟代理曲线，不建模采摘能力、成熟积压、到厂实现或加工厂峰值。训练标签必须明确记录为：

`smoothed_arrival_proxy_for_natural_maturity`

该标签来自 Task 3 `fact_receipt_daily` 的平滑代理构造，表示“平滑后的到厂量代理自然成熟过程”，不是生理成熟真值。

## 范围边界

Task 8 负责：

- 训练 manifest 与样本选择；
- `climate_zone × variety` 共享平滑曲线；
- 显式 partial pooling；
- 可解释的物候/海拔/设施偏移；
- P50/P80/P90 自然成熟曲线；
- 训练/预测 run、artifact 与 daily prediction 持久化；
- API、CLI、报告与审计；
- 防未来泄漏与回放可复现。

Task 8 不负责：

- Task 9 采摘能力、人效、春节用工、积压释放；
- 最终到厂量状态方程；
- 加工厂峰值预测；
- Task 10 残差模型；
- Task 11 滚动预测；
- Task 12 前端；
- Task 13 Agent。

## 样本粒度与上游依赖

基础样本粒度：

`season × farm/subfarm × variety`

训练和预测依赖的上游版本必须显式保存：

- Task 3 `analytics_build_run_id`
- Task 6 `production_plan_id` 与 `plan_version`
- Task 7 `location_weather_mapping_id`
- Task 7 `base_temperature_search_run_id`
- Task 7 实际选中天气 observation fingerprint
- `training_cutoff`
- `as_of_date`
- `config_hash`
- `model_version`
- `code_version`
- `random_seed`

## 训练 manifest 合同

CSV 模板：

`data/templates/maturity_curve_training_manifest.csv`

最小字段：

- `season_id`
- `analytics_build_run_id`
- `farm_key`
- `farm_id`
- `subfarm_key`
- `subfarm_id`
- `variety_id`
- `location_reference_id`
- `production_plan_id`
- `base_temperature_search_run_id`
- `anchor_event`
- `facility_type`
- `include`
- `sample_weight`
- `exclusion_reason`

语义：

- `include=false` 行仍进入 source signature 与审计快照；
- 缺少计划、位置、天气映射或基温 run 的样本必须返回 blocker；
- `facility_type` 不得猜测；未知值保存为显式 `unknown`；
- manifest 行顺序不得影响签名、artifact 或结果。

## 代理标签语义

训练标签：

`smoothed_arrival_proxy_for_natural_maturity`

构造约束：

- 保留 1—4 月分析窗口；
- 保留春节和其他扰动日；
- 不得从原始事实层删除春节行；
- 训练时可配置为保留、降权或从损失中排除；
- 报告必须列出原始日数、使用日数、降权日数、排除日数、原因代码和重量占比。

## 模型结构

### 1. 共享平滑曲线

主层级：

`climate_zone × variety`

使用确定性样条基函数，例如：

- `SplineTransformer`
- B-spline basis
- 正则化线性模型

约束：

- 每日 density/share 非负；
- 支持区间内归一化；
- P50 每日量总和严格对账到 `expected_marketable_total_kg`；
- 不产生负成熟量。

### 2. partial pooling

显式回退层级：

1. `climate_zone × variety`
2. `province × variety`
3. `variety_global`
4. `unavailable`

稀疏组必须：

- 保存父模型 ID；
- 保存收缩强度；
- 扩大区间；
- 降低可信度；
- 记录 fallback 原因。

### 3. 可解释偏移模型

偏移 `δ(x)` 可使用：

- 海拔
- 设施类型
- 树龄
- 修剪偏移
- 花期偏移
- 首采偏移
- 计划物候相对区域基准偏移

偏移模型要求：

- 系数和单位可解释；
- 类别 reference category 可追溯；
- 缺失规则配置化；
- 数据不足时回退到零偏移并标低可信度；
- 偏移受配置边界限制。

### 4. 建议公式

```text
density_g(t | x)
  = normalize_nonnegative(
      (1 - λ_g) · shared_parent_g(t - δ(x))
      + λ_g · local_spline_g(t - δ(x))
    )

daily_p50(t)
  = expected_marketable_total_kg · density_g(t | x)
```

其中：

- `g` 为层级组；
- `λ_g` 为组级收缩强度；
- `δ(x)` 为可解释偏移。

## 物候轴模式

支持两种模式：

- `observed_phenology_axis`
- `calendar_proxy_axis`

`observed_phenology_axis`：

- 使用截至 `training_cutoff` / `as_of_date` 可见的历史天气、Task 7 物候时间轴与基温 run。

`calendar_proxy_axis`：

- 用于未来天气不可用场景；
- 使用计划物候日期和截至 `as_of_date` 的已观测相位修正；
- 不得伪造未来天气；
- 必须扩大区间并记录 warning。

## 总量来源

预测必须接收或解析：

`expected_marketable_total_kg`

来源：

- `explicit`
- `derived_from_task6_plan`
- `shape_only_hindsight_total`

其中 `shape_only_hindsight_total` 仅用于历史诊断，不得冒充真实提前预测结果。

## P50 / P80 / P90 语义

- P50：质量守恒中心曲线；
- P80 / P90：确定性校准后的逐日边际分位数；
- 默认语义为 `pointwise_marginal`；
- 不得把 P80/P90 的逐日求和声称为天然守恒；
- 样本不足时必须返回 `uncalibrated_interval` warning。

## 防未来泄漏

所有训练与推理都必须满足：

- Task 6 `available_at <= training_cutoff/as_of_date`
- Task 7 `available_at <= training_cutoff/as_of_date`
- 天气 observation 指纹只包含当时可见修订
- 完整训练样本或输入快照变化必须改变 source signature
- `available_at > cutoff/as_of_date` 的未来修订不得改变历史 run。

## source signature 构成

Task 8 训练和预测 signature 至少包含：

- 规范化 manifest 全量行（包含 `include=false`）
- `sample_weight`
- `exclusion_reason`
- Task 3 build run 与 source cutoff
- Task 6 plan 版本
- Task 7 mapping row hash
- Task 7 weather observation fingerprint
- Task 7 base temperature run / signature
- `training_cutoff`
- `as_of_date`
- `config_hash`
- `model_version`
- `random_seed`

## 持久化

新增 revision：

`0009_natural_maturity_curve`

新增表：

- `maturity_model_run`
- `maturity_model_artifact`
- `maturity_forecast_run`
- `maturity_daily_prediction`

JSONB 只允许 canonical JSON 类型。Decimal 必须按仓库既有 canonical 约定保存并一致 rehydrate。

## 测试矩阵

单元测试至少覆盖：

1. 样条非负；
2. 归一化与 P50 质量守恒；
3. `P50 <= P80 <= P90`；
4. hierarchy fallback；
5. 小样本收缩；
6. 物候/海拔/设施偏移；
7. unknown facility；
8. 样本顺序无关；
9. 固定种子可复现；
10. 无效总量阻断；
11. calendar proxy 扩区间；
12. failed/unavailable 状态保真；
13. artifact JSONB 只含 canonical JSON。

PostgreSQL integration 至少覆盖：

1. migration roundtrip；
2. model run / artifact / forecast / daily rows 持久化；
3. 相同训练输入幂等；
4. manifest 权重变化生成新 run；
5. 可见天气修订生成新 run；
6. 未来不可见天气修订不改变历史 run；
7. 计划版本变化改变 forecast signature；
8. 相同预测输入幂等；
9. P50 每日总和等于 expected total；
10. rehydrate 类型一致；
11. dry-run 零写入；
12. API roundtrip；
13. failed run API 不误报 completed；
14. 春节行保留在审计 manifest；
15. 不存在 Task 9 状态逻辑。

Golden synthetic 至少覆盖：

- 3 个产季；
- 2 个气候区；
- 2 个品种；
- 多个农场/分场；
- 已知成熟峰值方向；
- 已知物候/海拔偏移；
- 少量春节扰动。

