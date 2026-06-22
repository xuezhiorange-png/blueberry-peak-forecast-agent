# Task 5 极简输入、位置解析与自动参数推断

## 目标

Task 5 只负责把“位置 + 品种亩数”转换为可复现、可追溯的参数推断结果：

- 位置标准化；
- 海拔与农业气候区解析；
- 相似历史样本检索；
- 版本化参数库选择；
- “位置 × 品种 × 参数类型”的 P50 / 中央 P80 推断；
- 来源、样本、产季、误差与可信度说明。

Task 5 的完成状态是 `parameters_ready`，不是最终预测完成。

## 最小输入

位置输入三选一：

1. `address`
2. `latitude + longitude`
3. `location_reference_id`

可选校正字段：

- `altitude_m`
- `province`
- `prefecture`
- `county`
- `township`
- `village`
- `farm_name`

品种输入：

- `variety_id` 或 `variety_code` / `variety_name`
- `planted_area_mu`

约束：

- 面积必须大于 0；
- 同一品种不能重复；
- 品种必须解析到主数据；
- 不允许静默创建未知品种。

## 地址标准化

地址解析使用确定性规则：

- Unicode NFKC 规范化；
- 去除首尾和连续空白；
- 常见中英文标点归一；
- 行政区路径和农场名拼接匹配；
- 精确匹配、别名匹配、阈值化模糊匹配依次尝试；
- 最高两个候选分数过近时返回 `ambiguous`；
- 无可靠候选时返回 `unresolved`。

Task 5 不允许在 `unresolved` 时生成虚假坐标。

## 海拔来源

海拔优先级：

1. 用户显式输入；
2. 精确 `location_reference`；
3. 配置半径内最近 `location_reference`；
4. 无可靠来源时保留 `null`。

Task 5 不凭空估计海拔。

## 农业气候区映射

优先级：

1. `location_reference` 已绑定气候区；
2. 行政区匹配；
3. 配置半径内最近气候区参考点；
4. 纬度与海拔联合约束；
5. 无可靠证据时 `unresolved`。

每次映射保存：

- `mapping_method`
- `candidate_count`
- `distance_km`
- `altitude_difference_m`
- `score`
- `zone_version`
- `confidence`

Task 5 不引入天气历史特征；气象增强留到后续任务。

## 参数类型

Task 5 固定支持：

- `yield_kg_per_mu`
- `marketable_rate`
- `first_harvest_offset_days`
- `maturity_peak_offset_days`
- `maturity_width_days`
- `maturity_skewness`
- `harvest_realization_rate`

## 相似度与分层回退

相似样本必须先精确匹配品种，再按位置层级筛选。

分层顺序固定：

1. `SAME_FARM_VARIETY`
2. `SAME_TOWNSHIP_ALTITUDE_VARIETY`
3. `SAME_COUNTY_CLIMATE_ZONE_VARIETY`
4. `SAME_PROVINCE_VARIETY`
5. `LITERATURE_VARIETY_PRIOR`

规则：

- 选择第一个满足最小样本数和最小产季数的层级；
- 不跨层级黑箱混合；
- 若所有层级都不满足最小要求，则使用最高可用层级并标记 `fallback_below_minimum=true`；
- 若没有任何记录，返回 `unavailable`。

## P50 / P80

Task 5 对单参数使用加权经验分位数：

- P50 = weighted median
- P80 下限 = weighted P10
- P80 上限 = weighted P90

低可信度或样本不足时按配置扩大区间。扩大前后的区间都保存到结果元数据。

约束：

- 比率参数裁剪到 `0..1`
- 亩产和宽度参数下限不低于 0
- 不声称当前 P80 已经过联合概率校准

## 可信度

每个参数结果至少返回：

- `confidence_level`
- `confidence_score`
- `source_level`
- `sample_count`
- `season_count`
- `farm_count`
- `distance_range_km`
- `altitude_difference_range_m`
- `historical_mape`
- `date_mae_days`
- `p90_coverage`
- `fallback_below_minimum`
- `missing_evidence`

高 / 中 / 低 的阈值全部配置化。

## as_of_date 防未来泄漏

所有位置与参数记录都必须满足：

- `valid_from <= as_of_date`
- `valid_to is null or valid_to >= as_of_date`

历史 observation 额外满足：

- 对应产季已在 `as_of_date` 前结束；或
- `available_at <= as_of_date`

Task 5 禁止使用未来产季、未来版本或未来才可见的 observation。

## 版本与复现

每次推断保存：

- `resolver_version`
- `library_version`
- `config_hash`
- `input_hash`
- `source_signature`
- `selected_location_version`
- `eligible_observation_ids`

同一输入、同一 `as_of_date`、同一 resolver/library/config 版本必须可复现。

## CLI

### 创建最小任务

```bash
uv run python scripts/create_minimal_planning_task.py \
  --address "云南省 红河州 弥勒市 西三镇" \
  --variety-area Dx=700 \
  --variety-area D12=300 \
  --as-of-date 2026-01-01 \
  --output reports/parameter-inference/task5-preview.json
```

### 导入农业气候区

```bash
uv run python scripts/import_agro_climate_zones.py \
  --file data/templates/agro_climate_zones.csv \
  --zone-version template-v1 \
  --source-name template \
  --source-version template-v1 \
  --dry-run
```

农业气候区导入会生成 `climate_zone_import_run` 审计记录；失败导入保留错误摘要，不覆盖已存在版本。

### 导入位置参考

```bash
uv run python scripts/import_location_references.py \
  --file data/templates/farm_location_master.csv \
  --version template-v1 \
  --dry-run
```

### 导入参数库

```bash
uv run python scripts/import_parameter_library.py \
  --file data/templates/parameter_observations.csv \
  --version synthetic-v1 \
  --dry-run
```

## API

- `POST /planning/tasks`
- `GET /planning/tasks/{task_id}`

Task 5 API 只返回参数推断结果和位置解析状态，不返回逐日预测或峰值预测。

## 与 Task 6—11 的边界

Task 5 不实现：

- 产量计划版本；
- 物候录入；
- 天气接口；
- 逐日成熟曲线训练；
- 采摘能力；
- 春节积压状态；
- 残差模型；
- 峰值预测与最终报告。

这些能力由 Task 6 及以后逐步接入。

## 为什么没有历史时不能伪造默认值

如果本农场、同乡镇、同县/气候区和省级样本都不存在，系统只能返回 `unavailable`。  
Task 5 不允许为了“给出一个答案”而伪造看似精确的亩产、商品果率或成熟参数。

