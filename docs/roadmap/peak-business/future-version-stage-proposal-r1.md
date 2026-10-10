# PEAK_BUSINESS — 未来版本阶段建议 R1（未冻结）

状态：建议稿；Owner 尚未批准新版本、编号、名称、阶段或任一实施。`PEAK_BUSINESS` 仅为临时工作流标签。

## 1. 版本治理建议

**推荐：保留 V0.18 原目标和已冻结 S0–S6，不通过本任务新增 V0.18 范围修订。** V0.18 的正式名称 `BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION`、身份/资源授权与安全试运行目标仍是原合同；其 S1 实施当前暂停。峰值业务分析、加工厂匹配和业务报表是新增产品方向，直接塞入 V0.18 会混淆安全可用性与新的经营决策能力，也会弱化已经冻结的阶段依赖。

建议将 Peak Business 作为**另立待批准的版本方向**提交 Owner 决策，但不填写版本号或正式名称：

```text
FUTURE_VERSION_NUMBER=PENDING_OWNER_DECISION
FUTURE_VERSION_NAME=PENDING_OWNER_DECISION
PEAK_BUSINESS_IS_FORMAL_VERSION=false
V0_18_SCOPE_AMENDED=false
V0_18_S0_TO_S6_SUPERSEDED=false
```

若未来版本需要身份/授权，必须另行决定是解除 V0.18 身份实现暂停，还是在正式批准的新范围中明确依赖/承接；不能悄悄改写 V0.18 S1 状态或把本 R0 设计当成授权。

## 2. 推荐优先顺序

1. **本次 R0 业务口径和 authority 合同**：定义 peak、rolling-7、阈值、浓度、工厂关系/能力、报告追溯；Owner 决策未定的值保留 pending。
2. **未来版本范围批准 + 访问基础**：解决 V0.18 身份授权暂停状态及跨版本归属，再授权可信 Principal/grants 和 saved-run discovery。身份和授权必须先于业务列表/详情读取。
3. **Saved-run selection 与服务端 peak 指标**：只使用一个已授权的完整 Operational Peak run；服务端输出每日峰、rolling-7、approved high-period/concentration（仅当 Owner 已选择）。
4. **Factory mapping 和处理能力权威**：只有正式主数据发布者与工厂处理能力发布者到位才做业务匹配；两者缺一仍 NOT_AVAILABLE。
5. **Scenario 与 Dashboard/报表**：先继续支持已明确标记的 S2 手动输入假设情景；真实工厂情景仅在 mapping + same-basis capacity authority 合法存在后开放。报告复用服务端输出。
6. **隔离合成验收与安全试运行准备**：证明 permission-before-read、不可用状态、hash/provenance、取消/撤销和回滚设计；合成通过不等于生产部署。
7. **质量研究独立推进**：不阻塞无需 actual 的业务定义/服务端 projection 设计，但任何历史重评分和实验仍要单独授权；prospective 只能等待真正可访问且已成熟的实际标签及签发证据。

## 3. 候选后续产品阶段

下列 `PB-S0..PB-S6` 是候选阶段编号，不是正式 V0.x/S 阶段，也不覆盖 V0.18 原 S0–S6。每一阶段需 Owner 单独授权、独立精确 HEAD 审查/CI 和治理门禁；上一阶段 PASS 不自动授权下一阶段。

### PB-S0 — Peak Business 范围和业务决策冻结

* **目标：** Owner 定义未来版本边界并决定 DECISION-01..08。
* **现有/缺口：** R0 已给出候选指标和 authority schema；阈值、timezone/date contract、厂能力 basis、publisher、report audience、version identity 尚 pending。
* **输入 authority：** V0.17/V0.16/V0.18 公共冻结材料和指定业务 Owner 决策，不读业务行/actual。
* **交付：** 经 Owner 批准的版本 scope、词典、日期/单位/窗口/阈值和数据 Owner roster。
* **依赖：** 当前 R0 独立评审完成；Owner 明确新版本编号/名称或其它治理路径。
* **验收：** 每个业务词有唯一含义、单位、层级、时间窗、缺失/零口径、阈值审批人和数据 publisher；不再有隐式默认值。
* **授权：** 本阶段仅设计文件；实际 source access 仍另批。
* **预计模块：** `docs/roadmap/peak-business/`、machine contract tests。
* **非目标/边界：** 不改 V0.18 冻结 scope、不实现算法、无预测或评分，不启动正式新版本。

### PB-S1 — 可信身份、资源授权与 saved-run discovery

* **目标：** 业务人员只能发现并选择有权访问的保存 run；未经授权不泄露 run 存在性。
* **现有/缺口：** V0.17 接受显式完整 identity，但没有正常授权的业务发现路径；TrialActor/MCP service account 不等同 end-user resource ACL；V0.18 S1 实施暂停。
* **输入 authority：** Owner 核验的 issuer/Principal source、业务 grant publisher、组织/Base/Region/Company 权威目录、canonical saved-run repositories。
* **交付：** 经批准的 BFF/session、共享 authorization facade、独立 BASE/REGION/COMPANY/Quality grants、授权前列表过滤、稳定分页/选择 handoff、撤销/审计合同。
* **依赖：** Owner 解决 S1 identity/grant 决策并明确是否解除暂停/授权，以及 PB-S0 冻结的身份和组织发布责任。
* **验收：** 未授权或未知 identity 固定拒绝且业务 repository read/quality read/simulation 为 0；principal/org/entity 交叉测试；分页/hash/handoff 与 grant revision 绑定；V0.17 业务 payload/hash 不变。
* **授权/模块：** 单独生产代码、必要 schema/migration、真实 IdP/secret 皆需独立授权；未来 `business_access` / identity adapter / HTTP authorization tests / Dashboard context adapter，MCP 只在已验证 delegation 时做用户上下文。
* **非目标/边界：** 不采用全局 latest、不全库读取后过滤、不以显示名或创建人猜 grant、不默认部署。

### PB-S2 — Operational Peak saved-curve 指标投影

* **目标：** 在同一权威 saved curve 上输出单日峰、完整 rolling-7、coverage 状态及 Owner 批准的高产/集中指标。
* **现有/缺口：** S1 Overview 已有单日 peak 和 high-load 描述；D1–D7 prefix 已有。无 Operational Peak run-bound rolling-7/max high period/concentration service/API。Core Forecast rolling-7 只属于独立 authority。
* **输入 authority：** PB-S1 授权选择后 canonical Operational Peak run、保存日行及完整 source/result hash。
* **交付：** typed metric projection、metric policy version、expected/available day/window counts、hash binding、短窗/缺 child/zero/pending threshold 状态。
* **依赖：** PB-S0 定义批准；PB-S1 identity/run discovery 完成。跨层 aggregate 只能沿用已保存层级 authority。
* **验收：** D1–D7 prefix 不等于 max rolling-7；9 个 15 日窗可追溯；最早同值 tie；缺日/不完整 child 不补零；cross-family/hash/run 混用 fail closed；API 返回 hash 由服务端生成。
* **授权/模块：** 单独实现授权；未来 `backend/app/forecast_intelligence/` read projection/schemas/API，Dashboard Overview/Forecast 和离线合同测试。
* **非目标/边界：** 不训练/重评分、不引入 P50/P80/P90、无 actual error metric、无红黄绿告警、无浏览器业务数学。

### PB-S3 — BASE→FACTORY 映射与 processing-capacity 数据权威

* **目标：** 以版本化有效期关系将预测 BASE 明确映射到一个或多个工厂，并获取同一 kg/time basis 的权威加工能力。
* **现有/缺口：** Core Forecast 可绑定 `destination_factory_id` 并暴露自身 harvest capacity；该模型身份和 harvest capacity 不能代表 Operational Peak 的 factory assignment/processing throughput。当前两项 authority 均 NOT_AVAILABLE。
* **输入 authority：** DECISION-04/05/06 指定的主数据 owner、容量 publisher、审批/修订/撤销记录、实际能力 source schema。
* **交付：** 受治理 mapping/capacity contracts、multi-factory allocation/conservation、temporary transfer、downtime overlay、revision history、NOT_AVAILABLE/PARTIAL/Error semantics。
* **依赖：** PB-S0 owner 决策；可与 PB-S2 服务开发并行设计，但 factory-facing implementation 需 PB-S1 权限和正式 publisher/source。
* **验收：** 稳定 ID；无重叠有效区间；share/quantity conservation；来源/责任/hash可审计；历史按当时版本回放；不把 harvest capacity relabel 成 processing capacity。
* **授权/模块：** 新 data source/database/migration 必须额外批准；未来 domain schema、authorized mapping/capacity adapters、owner-controlled persistence/tests。
* **非目标/边界：** 不推断 mapping、不读 actual、不做跨厂 routing、LP/MILP/优化或调度、不生产部署。

### PB-S4 — 有边界的 capacity scenario composition

* **目标：** 先复用 V0.17 S2 手工显式 capacity scenario；授权 factory 数据存在后增加清晰的来源选择，不更改已冻结 S2 math。
* **现有/缺口：** S2 只支持显式 DIRECT/WORKFORCE_DERIVED 输入、synthetic loss 和描述性情景排序；不拥有真实厂能力来源或业务 cost。
* **输入 authority：** PB-S1 saved-run grant、PB-S2 server metric projection、PB-S3 factory mapping/available capacity（若用于真实厂情景）及冻结 cost contract。
* **交付：** scenario 输入来源字段（用户假设 vs publisher capacity）、date/basis compatibility、服务端结果；显式保留 S2 synthetic mode。
* **依赖：** PB-S0–S3；真实能力情景必须等 PB-S3 完成；对任意 cost/field contract 扩展另行批准。
* **验收：** 同一 family/run/hierarchy/date/capacity/cost 才可比；无 POINT fallback；capacity/hash source可追溯；不得显示真实损失/ROI；变更输入使旧结果 stale。
* **授权/模块：** 单独 API/service/Dashboard 授权；尽可能复用 `decision_service.py`，不得复制/修改冻结 math，无 migration 除非明批。
* **非目标/边界：** 不自动排产/推荐/优化，不改变预测，不执行任何工厂动作。

### PB-S5 — 高峰分析 Dashboard 与可追溯报告

* **目标：** 将 PB-S2/S4 服务端数值以业务可读方式呈现在既有 Dashboard 五页，并可导出带 provenance 的结果。
* **现有/缺口：** V0.17 已有五页、server point curve、单日峰、capacity scenario；无 rolling-7/concentration pane、factory authority view 或通用报告 schema；正常 run discovery 尚缺。
* **输入 authority：** 已授权选择的 saved run、PB-S2 metric response、PB-S3 factory authority（仅有时）、PB-S4 response；所有 fields由服务器提供。
* **交付：** peak/high-period view、精确状态、报告/manifest、hash and metric version、输入与 output lineage、可访问图表/辅助表格。
* **依赖：** PB-S1/S2；factory view 依赖 PB-S3；scenario claims 依赖 PB-S4。
* **验收：** 前端不算业务数；同源数值/hash parity；缺失原因可见；报告输出可重放；旧 Trial 隔离；八状态/响应式/可访问性。
* **授权/模块：** 单独 frontend/API/export task；未来 `frontend/src/dashboard/` 与 authorized report projection/service。
* **非目标/边界：** 不改主导航未经 Owner 设计批准，不添加 current actual、ROI、生产报警、model admin 或 factory scheduling 页面。

### PB-S6 — 隔离验收和安全试运行 readiness evidence

* **目标：** 在显式 SYNTHETIC 隔离环境证明 access order、身份/映射/指标/报告、场景与故障恢复。
* **现有/缺口：** V0.17 已有 synthetic 三端验收；生产 IdP、用户 grants、mapping/capacity publisher、旧入口网络隔离与运维 runbook 未验收。
* **输入 authority：** synthetic seeded saved runs/grants/mappings/capacities；真实 secret/infra 绝不写入 repo。
* **交付：** authorization-before-read counters、cross-principal tests、HTTP/MCP/Dashboard parity、hash/report replay、revocation、backup/restore/rollback receipts。
* **依赖：** PB-S1–S5 中适用的 formal stages，安全/运营负责人，独立 Owner safe-pilot authorization。
* **验收：** 未授权读/模拟=0；无 source mixing、DML/business actions、private-data leak；历史/合成样例清楚分层；未验证项仍 NOT_VALIDATED。
* **授权/模块：** 仅隔离 test/evidence 可按阶段授权；生产 deployment/real account/真实数据另需专项批准。
* **非目标/边界：** 此阶段 PASS 不自动表示生产 READY、部署、正式版本 closeout、tag/release。

## 4. 独立 Forecast Quality 研究优先级（不属于产品阶段）

保持 `forecast-quality-improvement-roadmap-r1.md` 原文和授权边界不变。推荐的依赖顺序：

| Lane | 顺序与当前可做之事 | 数据/实验授权门禁 | 输出边界 |
| --- | --- | --- | --- |
| Q1 样本可比性 | 先完善 family/fit state/origin/lead/label/common-rowset 与排除规则；本轮可设计、不读行。 | 任何历史 row/label 访问和评分单独授权。 | 不能把 M1 与 Operational Peak 合并成一个模型比较。 |
| Q2 峰误差 | 同范围完整 horizon 的 daily peak date/quantity、rolling-7 start/quantity误差及 completeness。 | 经批准的冻结预测与 actual rowset、scorer、指标协议和输出发布。 | 旧 M1 暴露数据仅保留历史观察，不能声称 Operational Peak 精度。 |
| Q3 coverage/reliability | 保留 H7/H15 under-nominal、样本候选/可算/不可算/覆盖数；另设计条件可靠性分析。 | 新 calibration、scoring 或 interval evaluation需独立授权。 | 当前 nominal coverage不足；本路线不重校准。 |
| Q4 PIT/签发时点 | 为 source_available_at、ingested_at、as_issued_at、seals、actual_available_at/scoring_cutoff 建制度和证据字段。 | 需要有权威发布/入库时间数据；不能用日期、created_at补证明。 | 现状 `STRICT_PIT=false`；缺证据保持 NOT_PROVEN。 |
| Q5 A/B 与泄漏防护 | 新候选、训练 cutoff、features、rowset、指标、停止规则事前冻结；可先写 protocol。 | 训练/refit/tuning/score均要新 Owner 实验授权。 | 不重复查看 exposed holdout 后调参；不覆盖已冻结 artifacts。 |
| Q6 prospective | 只有合法真实数据、严格 issuance/cutoff、成熟标签、独立 scoring authority 后才启动。 | current-season actual access/scoring 必须单独授权；“数据到位”不构成许可。 | 目前 `PROSPECTIVE_ACCURACY_VALIDATED=false`，不得预先定精度门槛。 |

冻结研究事实：M1 `V0_15_S5_M1_RIDGE` 在 2025–2026 `EXPOSED_OOT`，H7 daily WAPE≈0.4249224043、H15≈0.4506174628；历史 peak errors 属于 M1 的 retrospective cohort。`STRICT_PIT=false`、`RETROSPECTIVE_AUTHORITY_USED=true`，actual available_at 证明不完整。以下区间数值是 V0.16 冻结研究中同一 M1 历史 cohort 的 retrospective observations，不是 Operational Peak run-bound 区间，也不是当前/未来覆盖保证：

| Horizon | Metric | Candidate rows | Computable | Not computable | Covered | Observed coverage | Nominal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H7 | PI80 | 61,425 | 60,060 | 1,365 | 32,368 | 0.5389277389 | 0.80 |
| H7 | PI90 | 61,425 | 60,060 | 1,365 | 44,763 | 0.7453046953 | 0.90 |
| H7 | UPPER80 | 61,425 | 60,060 | 1,365 | 43,325 | 0.7213619714 | 0.80 |
| H7 | UPPER90 | 61,425 | 60,060 | 1,365 | 49,444 | 0.8232434232 | 0.90 |
| H15 | PI80 | 131,625 | 126,360 | 5,265 | 63,907 | 0.5057534030 | 0.80 |
| H15 | PI90 | 131,625 | 126,360 | 5,265 | 89,832 | 0.7109211776 | 0.90 |
| H15 | UPPER80 | 131,625 | 126,360 | 5,265 | 89,084 | 0.7050015828 | 0.80 |
| H15 | UPPER90 | 131,625 | 126,360 | 5,265 | 102,270 | 0.8093542260 | 0.90 |

以上 coverage 均低于 nominal；不得隐藏未计算样本或描述为达标。所有这些历史结果都不能描述为 Operational Peak 生产效果或当前季精度。

## 5. 生产边界

本提案不请求生产代码、数据访问、模型实验、历史 rescoring、实际采收、数据库迁移、准备真实凭据、部署、Ready/Merge 或 Release。所有 PB/Q 阶段仍未授权。Synthetic acceptance 与 production readiness 永远是分开的结论。
