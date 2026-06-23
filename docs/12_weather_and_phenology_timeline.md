# Task 7：天气数据与物候时间轴

## 目标

Task 7 在 Task 6 的有效生产计划版本之上，构建确定性的天气窗口特征、物候时间轴和基温搜索结果。它不训练自然成熟曲线，不输出每日成熟量，也不进入 Task 8。

## Provider 抽象

天气源通过 `WeatherProvider` 抽象接入。当前实现：

- `CsvWeatherProvider`
- 测试可用 fake / in-memory provider

Provider 必须输出统一的：

- `WeatherSourceLocationRecord`
- `DailyWeatherRecord`

并显式记录：

- `provider_code`
- `provider_version`
- `dataset_version`
- `location_type`
- `available_at`
- 质量标记

Task 7 不接第三方在线天气 API，不持有任何供应商密钥。

## Canonical 单位

- 温度：`°C`
- 降雨：`mm/day`
- 太阳辐射：`MJ/m²/day`
- 海拔：`m`
- 距离：`km`
- 有效积温：`°C·day`
- 日期：天气源所在时区的本地自然日

持久化业务数值使用 `Decimal / NUMERIC`。Haversine 内部可使用 `float`，但结果必须确定性量化后再参与排序、哈希和返回。

## 天气源与观测模型

### weather_source_location

支持两类位置：

- `station`
- `grid`

业务键：

- `provider_code`
- `external_location_id`
- `source_version`

每条记录还保存 `valid_from / valid_to` 与 `row_hash`。

### weather_daily_observation

append-only。允许同一位置、同一自然日存在多个修订版本，但历史读取必须遵守：

- `available_at <= as_of_date`
- `observation_date <= feature_date`

然后在可见版本中确定性选择最新记录。若最高优先级记录内容冲突，则返回 `data_version_conflict`。

## 农场到天气源映射

Task 7 使用 Task 5 的 `LocationReference` 作为农场位置来源。

映射优先级：

1. `explicit`
2. `nearest_station`
3. `nearest_grid`

评分至少考虑：

- Haversine 水平距离
- 海拔差（若双方均有值）
- provider priority
- station / grid priority

候选排序固定为：

1. `mapping_score`
2. `distance_km`
3. provider priority
4. `external_location_id`
5. `id`

缺失海拔时不允许按 0 计算海拔差。

## 历史天气修订语义

Task 7 明确防止 future leakage：

- 旧预测只能看到旧 `available_at` 可见的数据
- 今天新增的天气修订不能回写到过去的特征运行中
- 同一输入和同一数据版本必须可复现

## 7 / 14 / 21 天窗口

窗口定义统一为：

`[feature_date - window_days + 1, feature_date]`

即包含 `feature_date`。

每个窗口输出：

- `effective_temperature_sum`
- `solar_radiation_sum`
- `precipitation_sum`
- `minimum_temperature`
- `mean_diurnal_temperature_range`
- `maximum_consecutive_rainy_days`
- `observed_day_count`
- `expected_day_count`
- `coverage_ratio`
- `missing_dates`
- `quality_flags`
- `source_observation_ids`

### 日有效积温

`max(daily_mean_temperature - base_temperature, 0)`

第一版不做上限温度截断。

### 昼夜温差

日昼夜温差：

`temperature_max_c - temperature_min_c`

窗口特征输出窗口内日昼夜温差的平均值，不是总和。

### 连续阴雨

雨日由配置中的 `rainy_day_threshold_mm` 定义。窗口指标取该窗口内最长连续雨日长度。缺失天气日不会被当作无雨日。

## 缺失天气处理

缺失的温度、降雨和辐射不得用 0 填充。

每个窗口都记录：

- `expected_day_count`
- `observed_day_count`
- `coverage_ratio`
- `missing_dates`

若 `coverage_ratio` 低于阈值，则窗口返回 `unavailable`。

## 物候时间轴

Task 7 通过 Task 6 的 `get_effective_plan()` 读取给定 `as_of_date` 当时可见的计划版本，不能直接读取“当前最新计划”。

时间轴至少包含：

- `plan_id`
- `plan_version`
- 修剪、花期和首采日期
- `days_since_*`
- `days_until_first_pick`
- `selected_weather_mapping_id`
- `weather_feature_version`

若事件日期缺失，对应特征返回 `null + warning`。

## 锚点累计积温

支持从明确锚点起算，例如：

- `flowering_start_date`
- `flowering_peak_date`

只在锚点存在且天气覆盖满足要求时返回累计积温。

## 基温训练搜索

Task 7 不允许把某一个固定基温写死为最终业务值。

流程：

1. 从配置读取候选基温集合
2. 从训练 manifest 读取显式样本
3. 对每个候选基温计算样本在 `anchor_event -> target_event` 区间的累计有效积温
4. 使用 `season_loso_mae_days` 做 leave-one-season-out 评分
5. 按 `MAE → base_temperature` 确定性选优

若样本数或 distinct season 数不足，返回 `unavailable`。

## 防未来泄漏

Task 7 的 leakage 防护主要包括：

- 天气读取受 `available_at` 截断
- 天气日期不得晚于 `feature_date`
- 计划版本通过 `available_at <= as_of_date` 读取
- 基温训练样本只能使用 `training_cutoff` 当时可见的计划和天气版本

## Task 7 与 Task 8 边界

Task 7 只形成：

- 天气历史导入
- 位置映射
- 窗口天气特征
- 物候时间轴
- 基温搜索

Task 8 才开始训练自然成熟曲线。Task 7 不输出：

- 每日成熟量
- 每日到果量预测
- 峰值吨数预测
- 成熟曲线 P50/P80/P90
