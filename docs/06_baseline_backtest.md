# 基线模型与历史复现规范

Task 4 实现三类静态历史基线，并以 Task 3 已持久化的 `factory_season_peak_metric` 为唯一特征来源完成跨产季回测。

## Oracle benchmark

- `benchmark_mode = historical_oracle`
- `production_eligible = false`

Task 4 允许使用目标产季最终的：

- `total_weight_kg`
- `variety_hhi`
- `farm_hhi`
- `subfarm_hhi`

这些输入仅用于历史复现和静态能力上限评估，不代表真实预测时可提前获得。

## 三个基线

1. `previous_season_peak`
2. `volume_previous_concentration`
3. `ridge_structure`

另含一个加工厂留出诊断模型：

4. `ridge_structure_factory_holdout`

主目标固定为：

`stable_median_3d_peak_kg`

## 防泄漏规则

Ridge 只允许四项特征：

- `total_weight_kg`
- `variety_hhi`
- `farm_hhi`
- `subfarm_hhi`

禁止使用：

- `stable_median_3d_peak_kg`
- `stable_median_3d_peak_date`
- `single_day_peak_kg`
- `single_day_peak_date`
- `mean_3d_peak_kg`
- `mean_3d_peak_date`
- `peak_concentration`

## 回测方法

- 主方案：Leave-One-Season-Out
- 诊断方案：Leave-One-Factory-Out
- `rolling_time_backtest = deferred_to_task_11`

## 报告

Task 4 输出：

- JSON 汇总报告
- Markdown 业务摘要
- CSV 逐工厂误差表

默认输出目录：

- `reports/baseline/`
