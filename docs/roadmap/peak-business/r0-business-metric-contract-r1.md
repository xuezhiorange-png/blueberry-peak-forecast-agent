# Peak Business R0 — 业务指标合同候选 R1

状态：Owner 授权的设计候选；尚未获得业务口径最终签署，也不是生产接口或计算实现。

临时工作流标识 `PEAK_BUSINESS` 不是版本号。V0.18 的版本名、范围和 S0–S6 均保持原样；未来版本编号/名称待 Owner 决定。本文不授权访问历史行数据、actual、数据库或执行评分。

## 1. 适用范围与权威顺序

任何指标都必须绑定单一且已通过 canonical integrity verification 的 saved forecast authority：

```text
source_kind + forecast_family + run_id
+ hierarchy_level + entity_id + target_season + origin_date
+ baseline_id + policy_version + source_result_hash
+ target date range + metric_contract_version
```

`run_id` 单独不够；创建时间不能替代预测签发时间；source/result/projection hash 含义不可互换。读服务返回的日曲线及服务端权威汇总是唯一输入。浏览器不计算权威总量、峰值、窗口、比例或分配。

当前可复用的权威：V0.17 Operational Peak 已保存日曲线、D1–D7/D1–D15 前缀汇总、从同一条曲线导出的单日峰和描述性排序；V0.16 BASE→REGION→COMPANY 的合法保存层级曲线。若 aggregate 保存曲线为 `INCOMPLETE_CHILD_COVERAGE`，不得作为完整峰值或下游模拟输入。

禁止跨 `forecast_family`、run、产季、origin、baseline、policy、层级快照或不同 source hash 拼接。Operational Peak 不得借用 Core Forecast/M1 的数学结果或身份。

## 2. 日期、单位与完整性共同规则

* 指标日期是权威曲线中的业务日历 `date`，不是浏览器按 UTC 时间戳换算的日期。已保存日期不得二次移时区。
* Operational Peak 当前代码声明 `Asia/Shanghai` 本地时区及自然日业务日期；建议继续以该业务日为候选口径，但 DECISION-01 未签署前不能声称所有来源都采用同一时区。
* 所有数量以 kg/day 或指定窗口 kg 表示，保留服务端 Decimal 字符串；任何显示格式不回流至计算。
* 计算前要求日期唯一、按自然日连续、范围明确，身份/hash 一致。缺日、重复日、损坏 source 或 scope 混合不得补 0、插值、外推或跨 run 补齐。
* 对声明的完整范围，有任一日期缺失时，完整范围指标为 `PARTIAL` / `NOT_COMPUTABLE_INCOMPLETE_DATE_SET`。可另行说明已观察子段，但不能把子段极值称为整个预测期的峰值。
* 层级汇总须使用一个已保存且同一快照的 aggregate 曲线；若未来服务要从 child 日曲线构建 aggregate，必须先证明预期 child 集、同季/同 origin/同 baseline/policy 与覆盖完整，并仅按日精确相加后再计算指标。绝不相加 child 的峰值。

## 3. R0-A — 单日峰值

候选名称：`DAILY_PEAK_DATE`、`DAILY_PEAK_QUANTITY_KG`。

1. 对完整、指定的目标日期范围 `D_start..D_end`，在同一权威曲线上取 `max(daily_quantity_kg)`。窗口边界应随输出记录；Operational Peak 通常是 origin 后 D1–D15 可用范围，不能把保存曲线短窗称为完整 15 日。
2. 多个日期同为最大值时，沿用现有 `EARLIEST_DATE` tie-break，选择最早业务日期。
3. 无行/无目标日期为 `EMPTY`；范围缺日或身份异常为 `PARTIAL` / `AUTHORITY_MISMATCH`，不产出完整范围峰值。
4. 全范围都是 0 时，数值最大值仍为 `0 kg`，最早日期按 tie-break 确定，但 `peak_event_status=NO_POSITIVE_DEMAND`，业务文案不得暗示当日发生真实采收高峰。若 Owner 选择返回 null 日期，此项需另签口径；当前建议保留数学最大值与事件状态的区别。
5. Base、Region、Company 各自只能用其被授权的同源保存日曲线。不得对各 Base 的 `DAILY_PEAK_QUANTITY_KG` 求和得到 Region/Company 峰量。

该合同是未来服务投影候选。现有 S1 Overview 已有保存曲线峰日/峰量，不意味着本轮新增服务或已验证运行精度。

## 4. R0-B1 — Rolling-7 连续七日峰值

候选名称：`ROLLING_7DAY_PEAK`，与 `H7_PREFIX_TOTAL` 分字段、分文案、分 hash 语义。

* 对已声明且完整的连续日历范围内每一个合法起点 `s`，计算 `sum(q[s..s+6])`，取最大窗口总量及其 start/end 日期；end=`start+6 days`。完整 D1–D15 恰有 9 个候选窗口。
* 并列窗口取最早 `start_date`（与 Core Forecast 已有 `EARLIEST_START_DATE` 合同一致，但跨家族仅复用规则，不复用其结果或 authority）。
* `H7_PREFIX_TOTAL` 明确为 D1–D7 总和；它不是 15 日范围内最大滚动七日窗口。不得把两者互为别名。
* 有至少一个完整七日子窗但声明的全范围缺日时，允许报告窗口完整性/候选数，整体 rolling peak 标为 `PARTIAL_NOT_GLOBAL`，不能选一个可见子窗冒充全期最大。
* 声明范围少于连续 7 日，或没有完整 7 日子窗，返回 `NOT_COMPUTABLE_NO_COMPLETE_7DAY_WINDOW`。不补零、不把相邻观测日误当连续自然日。
* 全部为 0 时 quantity 为 0，最早完整窗为数学 tie-break，但 `peak_event_status=NO_POSITIVE_DEMAND`。
* 输入日期、source result hash、范围、窗口长度、政策版本和结果均应绑定 metric projection hash。数值窗口和累计均由服务端 Decimal 权威计算。

**合成示例（仅解释合同，不是生产数据）**：15 日曲线 `[10,10,10,10,10,10,10,100,100,0,0,0,0,0,0] kg` 的 D1–D7 前缀是 70 kg；最大滚动 7 日为 D3–D9，共 250 kg。两者不是同一指标。

## 5. R0-B2 — 连续高产期

`CONSECUTIVE_HIGH_HARVEST_PERIOD` 是按连续自然日识别的一段日期集合，不等同于 rolling-7 峰值，也不自动构成告警。

候选判定可选：

| 方案 | 日级判定候选 | 必需权威/主要限制 |
| --- | --- | --- |
| 绝对日量 | `forecast_kg >= approved_threshold_kg_per_day` | Owner 事前批准绝对阈值、单位、适用层级/产季与最短持续天数；没有阈值不得分类。 |
| 相对基准 | 预测日量相对某个版本化基线达到批准比例 | 必须选定同层级/同季节位置/同口径的基准曲线和可比性规则；不得事后用当前曲线分位数自造“高”。 |
| 产能负荷 | 预测需求相对同日有效处理能力达到批准负荷比例 | 需要合法 BASE→FACTORY 分配、日期级有效处理能力和已批准分母；S2 用户手填/合成能力只产生 scenario-specific 负荷，不是事实高产告警。零能力不可除。 |

Owner 尚未选择方案、阈值、边界比较符（`>`/`>=`）、最短持续日数及缺失日断段规则：

```text
HIGH_PERIOD_THRESHOLD=PENDING_OWNER_DECISION
HIGH_PERIOD_METHOD=PENDING_OWNER_DECISION
MIN_CONSECUTIVE_DAYS=PENDING_OWNER_DECISION
```

未批准时仅可返回 `NOT_AVAILABLE_THRESHOLD_UNAPPROVED`，不得默认 3 日/7 日、百分位数、历史最大值或红黄绿状态。任何缺日都会断开连续段；若完整性不足，整体范围标 PARTIAL。

## 6. R0-C — 产量集中度候选

候选指标都以同一完整曲线和完全相同的分母范围为基础，输出比值及 numerator/denominator 原始量，不能仅显示百分比。

| 候选 | 定义 | 必须由 Owner 确认 |
| --- | --- | --- |
| `N_DAY_PREFIX_SHARE` | 指定起始 N 个连续业务日之预测 kg ÷ 声明全期预测 kg | N、D1/其他窗口锚点、是否适用于不同 forecast horizon。不是“最高的 N 天”。 |
| `MAX_ROLLING_7_SHARE` | 完整范围内最大 rolling-7 kg ÷ 同范围总 kg | 与 rolling-7 的 range 和完整性共用；若滚动峰不可计算则不可计算。 |
| `DAILY_PEAK_TO_MEAN_RATIO` | 单日峰 kg ÷ 同范围日均量（全期总量/完整日数） | 若 0 总量或空范围则 `NOT_COMPUTABLE_ZERO_DENOMINATOR`。 |

缺日、child coverage 不完整、分母为 0 或跨 run 时，返回明确 `PARTIAL` / `NOT_AVAILABLE`，不补零或跨期凑分母。比值权威值须用 Decimal/rational-safe 服务端政策并绑定 metric contract version；浏览器只能格式化。

```text
CONCENTRATION_N=PENDING_OWNER_DECISION
CONCENTRATION_RANGE=PENDING_OWNER_DECISION
CONCENTRATION_THRESHOLD=PENDING_OWNER_DECISION
CONCENTRATION_RISK_BANDS=NOT_DEFINED
```

不设风险阈值或颜色等级。跨运行比较至少要求 family、scope、target season、date range、baseline/policy、metric version、完整性及授权都可比；否则分别呈现，不排名。

## 7. 失败/状态与审计

每个 metric 独立状态：`READY`、`PARTIAL`、`EMPTY`、`NOT_AVAILABLE`、`AUTHORITY_MISMATCH`。一项 READY 不推导其他指标 READY。建议 reason 码包括缺失阈值、短窗、日历缺失、child coverage、零分母、不可兼容 family、源 hash 漂移。

每一项结果应含：定义版本、family/run 完整身份、hierarchy scope、origin、target date range、business date basis、quantity unit、source result hash、projection hash、完整日数/候选窗口数/有效窗口数、状态与不可用原因。预测指标不得与 actual 误差指标共用字段名；actual-scoring 使用独立 evidence mode，需单独授权。

## 8. 合成合同检查清单

离线测试可使用 `SYNTHETIC=true` 的手算 fixture，覆盖最早同值、全零、H7 与 rolling-7 区别、15 日 9 个窗、缺日、短于 7 日、aggregate 同日求和后取峰、不完整 child、零分母、未批准阈值及不同 family/hash 拒绝。测试不得导入 actual/生产 DB 或调用 forecast/training/scoring/calibration 服务。
