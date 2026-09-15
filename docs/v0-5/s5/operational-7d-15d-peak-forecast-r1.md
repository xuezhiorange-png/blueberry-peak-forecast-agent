# V0.5-S5 运营 7 日 / 15 日峰值预测 R1

## 状态与边界

S5 将 S4 已冻结的简单无天气基线
`AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1` 封装为一个纯、确定性的基地级运营窗口服务。
本任务不重新训练、不调参、不使用天气，也不改变 S4 的混合天气增益结论。

```ini
TASK_ID=V0_5_S5_OPERATIONAL_7D_15D_PEAK_FORECAST_R1
POLICY_VERSION=OPERATIONAL_PEAK_POLICY_V1
SELECTED_BASELINE_ID=AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1
PREDICTION_ENTITY=BASE
WEATHER_USED=false
BUSINESS_CUTOFF=04-15_INCLUSIVE
PEAK_TIE_BREAK=EARLIEST_DATE
```

实现位于 `backend/app/forecast_quality/operational_peak.py`。它只接受已登记的
`base_id`、目标产季和 Asia/Shanghai 本地 `origin_date`，从冻结的基地总投产面积
authority 读取面积，并用冻结的 7 日桶 kg/亩日画像生成未来值。它不接受调用方覆盖面积，
不按农场分摊面积，不使用 climate zone，也没有网络、数据库或天气依赖。

## 业务季窗口

产季 `YYYY-YYYY` 的业务日历是：

- 起点：起始年份 07-01；
- 终点：结束年份 04-15，包含 04-15；
- 日历按连续自然日计算，包含周末；
- 04-16 及以后不属于本次业务预测窗口。

预测 origin `D` 必须位于业务季内。服务返回业务窗口内的 `D+1..D+15` 日量；接近
04-15 时，不生成业务窗口外的日期。另行返回的 `remaining_business_window` 使用
`D+1..04-15`，不能冒充 7 日或 15 日整窗。

## 7 日和 15 日合同

`forecast_7d` 固定表示 `D+1..D+7`，`forecast_15d` 固定表示 `D+1..D+15`。
只有请求整窗全部在业务季内且每个预测日都存在时，状态才是
`COMPUTABLE_FULL_WINDOW`。否则状态为 `NOT_COMPUTABLE_FULL_WINDOW`，总量、峰日和峰值量
均为 `null`，绝不把缩短窗口的合计伪装成完整窗口。

窗口总量是其 daily rows 的精确 Decimal 合计。窗口峰值直接从同一组 daily rows 取最大值；
相同最大值时取最早日期。`remaining_business_window` 没有 W7/W15 的语义，只用于在季末
透明报告剩余业务日。

例如对 `2026-2027`：

| origin D | 7 日状态 | 15 日状态 | 说明 |
| --- | --- | --- | --- |
| 2027-03-31 | `COMPUTABLE_FULL_WINDOW` | `COMPUTABLE_FULL_WINDOW` | D+15 正好是 04-15 |
| 2027-04-01 | `COMPUTABLE_FULL_WINDOW` | `NOT_COMPUTABLE_FULL_WINDOW` | D+15 越过 cutoff |
| 2027-04-08 | `COMPUTABLE_FULL_WINDOW` | `NOT_COMPUTABLE_FULL_WINDOW` | 只有 7 日完整 |
| 2027-04-10 | `NOT_COMPUTABLE_FULL_WINDOW` | `NOT_COMPUTABLE_FULL_WINDOW` | 剩余只有 5 个业务日 |

## 输出与失败闭锁

结果包含基地身份、基地 authority 面积、目标产季、origin、业务窗口、最多 15 行
`daily_forecast`、`forecast_7d`、`forecast_15d`、`remaining_business_window`、基线版本、
天气未使用声明、限制和确定性 `result_hash`。S5 不返回整季总量或整季亩产字段，避免把
短窗口运营预测误称为完整季预测。

未登记或非 active 基地返回机器可识别的 `UNREGISTERED_BASE`；面积 authority 非正、非有限
或 registry 结构不合法时 fail closed。冻结画像缺失、桶非法或数值不合法时返回
`REFERENCE_PROFILE_UNAVAILABLE`。日量缺失、重复或非法时，窗口保持
`NOT_COMPUTABLE_FULL_WINDOW`，不会静默缩短、补零或跨季拼接。

天气字段固定为 `weather_used=false`，其来源和 snapshot hash 为 `null`。这不是天气可用性
证明，也不构成生产准确率批准；S4 的历史 weather/PIT 状态继续按原 evidence 保留。

## 运行与验证

纯函数调用示意：

```python
from datetime import date

from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastRequest,
    forecast_operational_peak,
)

request = OperationalPeakForecastRequest(
    base_id="registered-base-id",
    target_season="2026-2027",
    origin_date=date(2027, 4, 8),
)
result = forecast_operational_peak(request, base_registry, frozen_reference_profile)
```

配置文件为 `configs/v0_5_s5_operational_7d_15d_peak_forecast_r1.json`。该实现是纯业务层，
不接入 HTTP、CLI、MCP、数据库或生产部署；这些是后续明确授权边界，不由 S5 R1 隐式触发。

本 R1 的验收是工程契约和确定性回放，不是跨产季准确率结论。完整天气增益研究已在 S4
停止，S5 只保留无天气业务参考。
