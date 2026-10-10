# Peak Business R0 — 既有能力与权威清单 R1

审查基线：`b7ae7b4d35f182d5505ff3ea3750c5de403b2b81`。范围为已提交公共代码/文档/机器证据；未连接业务数据库、读取实际行、运行预测或评分。

## 1. 按产品线/数据族盘点

| Capability / family | 已实现或已冻结 | 可复用部分 | 不可直接复用 / 缺口 | 当前输入 authority 与后续权限 |
| --- | --- | --- | --- | --- |
| V0.14 as-issued / prospective lane | 已冻结 forecast origin、weather as-issued、snapshot/seal、shadow协议等工程流程。 | 时间戳、封存、可追溯协议可指导未来 evidence。 | 协议建立不等于 prospective accuracy；当前没有合法新产季评分。 | 只读 frozen docs/evidence；新数据访问和任何 prospective scoring另行授权。 |
| V0.15 M1 Ridge | `V0_15_S5_M1_RIDGE`、2025–2026、`EXPOSED_OOT` 的 retrospective summaries；冻结点误差和峰值误差。 | 仅能作为同一历史 cohort、同一 M1 identity 的背景事实；未来对比先做样本/rowset可比性。 | 不代表 Operational Peak 的运行表现；不严格 PIT；不代表当前季或生产；不能直接给 M1/Operational Peak混合排名。 | 当前只可复用已提交 public aggregate summary；底层 labels/rows、rescoring另需 data/scoring authorization。 |
| Operational Peak | 独立确定性 family `OPERATIONAL_PEAK_FORECAST_RUN_V1`，baseline `AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`、policy `OPERATIONAL_PEAK_POLICY_V1`；saved BASE daily rows；origin后 7/15 日 prefix totals、remaining business window summary；单曲线 earliest-date peak/high-load ordering。 | S1 完整 identity/hash/canonical read；同一 run 上的服务端 saved curve 投影；既有单日峰/前缀字段。 | 无 Operational Peak run-bound uncertainty/attribution；没有跨15日 rolling-7最大、批准的连续高产阈值、concentration authority；normal business run discovery缺失。 | 必须由 exact saved-run identity/source result hash+授权访问；无 global latest、无客户端曲线。历史创建需要当时配置 authority，不能依赖当前 registry重建。 |
| V0.16 hierarchy | BASE→REGION→COMPANY，bottom-up exact-sum，missing child非零值；有saved aggregate/hierarchy authority。 | 同一 saved hierarchy curve/coverage 和源 hash可作为 aggregate metric输入。 | 不可将每个Base峰值求和；现有层级是 forecast hierarchy，不是 factory routing。 | 必须复用原 hierarchy snapshot、origin/season/baseline/policy与完整 child coverage。 |
| V0.16 S2/S5/S6 decision support | 已冻结 Business Loss 公式、三种 synthetic contracts、显式 DIRECT/WORKFORCE capacity输入、scenario simulation/comparison、固定排序和 utilization数值例外。 | 手动假设capacity情景、服务端engine结果、排序/hash/state semantics可继续复用。 | synthetic loss不是货币/公司成本；用户输入不是已核实工厂能力；没有Optimizer/自动动作/真实ROI。 | 只用明确选定的 saved forecast + explicit scenario/cost contract；生产厂能力需新 authority。 |
| V0.17 HTTP / MCP / Dashboard | 6 forecast GET abilities、S2 decision APIs、8 MCP tools、React五页Dashboard、同一业务服务以及 isolated SYNTHETIC cross-surface acceptance。 | typed response、hash、状态、请求取消/迟到响应保护、历史Quality分层、五页交互。 | no authorized normal saved-run discovery/handoff、HTTP end-user resource ACL 未验证、MCP production user delegation/credentials未配置；factory mapping/throughput不存在；当前 child contribution与Upper/attribution仍NOT_AVAILABLE。 | 完整来源身份仍是选择参数而非授权；通过现有 coarse actor 不能宣称用户/基地隔离。 |
| Core Forecast metrics lane | 独立 schema/domain接受 factory-scoped request，包括 `destination_factory_id`；curve row有 P50/P80/P90字段、`effective_harvest_capacity_kg`、effective marketable qty 与 task8/task9 artifacts/hash；`compute_core_forecast_metrics`对该完整曲线生成 earliest-tie single day和strict calendar rolling-seven peak。 | Rolling-7的数学/契约表达（最早 start tie、连续七个自然日、源 curve hash绑定）可作为设计参考。 | 是另一 family/另一 run input/provenance/quantile contract。`effective_harvest_capacity_kg`是harvest capacity，不能认作processing throughput。不能贴到Operational Peak run或M1；有 P50/P80/P90 schema不证明校准。 | 必须使用Core自己的完整权限身份和验证过的source curve。不得从它的destination factory反推Operational Peak BASE归属。 |
| Historical analytics daily fact/peak | 旧 `factory_season_peak_metric` 对分析日历上的实际收货事实做单日峰、3日中位/均值峰、3日峰浓度、farm/subfarm/variety HHI；配置月份外过滤且dense calendar中没有事实的日期补0。 | 仅可作为历史事实分析的词汇/分组思路参考；source_max_raw_id、build/config hash可作追溯设计参考。 | 不是预测指标，也不是V0.17 Operational Peak metric；3日 median/mean与rolling-7不同。该分析日历的“缺事实=0”只在它的已定义事实构建协议内合法，不能移植到未完整预测 curve。其 factory-season事实不建立forecast BASE→factory关系。 | 相关 raw actual data本轮未读；任何重新运行、历史重建或事实访问需单独授权。 |
| Forecast quality roadmap | Q1–Q6设计了样本可比、峰误差、coverage可靠性、available_at/PIT、A/B泄漏和prospective admission；冻结M1与interval summaries。 | 作为独立研究审批和label/time-seal门禁。 | 不构成新实验/训练/评分许可；under-nominal coverage不能隐藏。 | 只复用冻结公共汇总；历史原始rows/actual scoring/新校准各自需要明确数据/实验授权。 |
| General report/export | 有若干不相关 residual-model report endpoints；Dashboard显示S1/S2 typed response。 | 可借用普通导出技术模式，但每项报告仍应保留本身authority/hashes。 | 没有通用Operational Peak/decision-support traceable report schema；现有residual报告不代表预测峰值或工厂容量报告。 | 未来必须基于授权服务端投影，不能由浏览器重新算。 |

## 2. 历史研究数值应如何引用

公开冻结的 M1 history：`V0_15_S5_M1_RIDGE / EXPOSED_OOT / 2025-2026 / BASE_COHORT_AGGREGATE`；H7 daily WAPE `0.4249224042811489...`，H15 daily WAPE `0.4506174628427471...`。相同历史 authority 中 single-day peak date MAE约 `6.128433` days、quantity MAE约 `3185.2563 kg`；rolling-7 start MAE约 `3.537664` days、quantity MAE约 `15081.7600 kg`。这些是暴露 retrospective cohort 的既有事实，不是对Operational Peak的预测误差，也不是将来容忍阈值或生产验收 pass。

冻结区间历史 H7 PI80/PI90 coverage约 `0.5389277/0.7453047`，H15约 `0.5057534/0.7109212`，均低于名义覆盖；对应Upper80/90结果也有under-nominal事实。候选/可计算/不可计算/覆盖样本数必须一并保留，不能以删除not-computable改善展示。

```text
STRICT_PIT=false
RETROSPECTIVE_AUTHORITY_USED=true
HISTORICAL_ACTUAL_AVAILABLE_AT_PROVEN=false
PROSPECTIVE_ACCURACY_VALIDATED=false
CURRENT_SEASON_ACTUAL_AVAILABLE=false
```

## 3. 复用决策原则

* **可复用计算输出：** 仅当 identity、family、scope、源 hash、date basis 和完整性均相同，且目标指标本就属于该 authority。
* **只复用定义、不能复用结果：** Core Forecast rolling-7规则可以借鉴为合同语言，但其数值、hash和forecast identity不能附到Operational Peak。
* **只复用事实口径、不能移植缺失处理：** historical analytics dense calendar补零仅适用于它自己的 actual fact builder，不是saved forecast缺日策略。
* **只复用显式 scenario语义：** S2手动capacity是用户假设，不是厂数据；S2 synthetic business loss不是财务结果。
* **必须等授权/数据：** 用户可见 run list需身份/grant；factory匹配需正式关系publisher；processing capacity需工厂业务/设备容量publisher；actual对比需 data/scoring authorization和 label maturity。

## 4. 边界结论

当前可以继续做：公共设计、合同、canonical hash绑定、显式 unavailable状态和只含 `SYNTHETIC=true` 的离线示例。不能从“有同名字段”推导跨家族兼容；不能从 `destination_factory_id` 断定Operational Peak run已分配工厂；不能从 `effective_harvest_capacity_kg` 断定工厂 throughput；不能将历史 M1 WAPE/peak error称为Operational Peak accuracy。任何生产算法、数据访问、模型实验、rescoring、current actual、migration和部署均不在R0权限内。
