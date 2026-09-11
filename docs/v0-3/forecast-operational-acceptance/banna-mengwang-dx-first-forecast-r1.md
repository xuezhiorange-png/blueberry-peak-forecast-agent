# 版纳勐旺 / Dx / 736亩：首次真实范围执行 R1

## 当前结果

固定范围 `BANNA_MENGWANG_DX_736MU_R1` 的三个外部事实已经由 coordinator 授权：版纳勐旺加工厂、Dx、736.000000亩。外部事实门槛 PASS，不能再报位置、品种或面积未提供。

本次已通过现有主数据服务创建真实 Dx（id=1），并用新会话回读确认。正常位置解析器在已有验收库返回 `unresolved / address_unresolved`，候选数为0。第一个断点是 `AUTHORIZED_LOCATION_LABEL_TO_CANONICAL_SCOPE_MAPPING_UNAVAILABLE`。因此没有发起 Task5 或 Forecast，也未构造参数库。

基线：`68ed5691b5ee1163cc18e1ad1208146e3ebf82f3`。

## 已执行的身份绑定

数据库为既有非生产验收库 `blueberry_v03_acceptance_r2`，127.0.0.1:55437。只读检查时 LocationReference、Farm、Subfarm、Factory、Variety、ParameterLibraryVersion、ParameterObservation、计划和商品化策略表均为0行。之后仅通过 `backend.app.services.master_data.create_master_data` 创建 Dx，未直接插入预测或 authority 表。没有把旧 V0.2 demo 应用作为验收应用。

`backend/app/s3_daily_rowset/source_002_variety_master_identity.py` 明确映射蓝莓原果Dx到Dx，映射哈希为 `3ccc6f2cd352e746c4e45952a7a0008f4ad2819d81c879a96dd3481fc3e31897`。2024–2025源中该品种名称有62268条身份记录；这里只检查身份列，没有读取入库公斤数。

2024–2025源（SHA-256 `a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5`）包含：

| 源身份 | 记录数 |
| --- | ---: |
| 农场：版纳勐旺农场 | 3420 |
| 分场：版纳勐旺农场一分场 | 1271 |
| 分场：版纳勐旺农场二分场 | 1159 |
| 分场：版纳勐旺农场三分场 | 990 |
| 加工厂：勐旺加工厂 | 3420 |

源中的相关名称不足以声明 coordinator 的位置标签已经具有合法位置参考、坐标、气候区及736亩对应分场。仓库 factory_aliases 仅有巴松映射；正常位置解析依赖有效 LocationReference，并不把工厂表自动视为农场表。本次没有创建 Farm、Subfarm、Factory 或虚假坐标。位置名称仅作为一次正常 resolver probe 输入，没有作为成功的永久地址绑定。

2025–2026 XLS 存在性沿用 #606 已合并资产证据，本次没有打开其内容，也没有读取任何 S1 TEST 分区。

## 参数来源与等价性门槛

`docs/07_minimal_input_parameter_inference.md` 及 `backend/app/planning/importers.py::import_parameter_library_csv` 要求版本化 observation。七项分析如下；方法栏描述所需语义，不表示本次已计算或建立新算法。全部尚不能安全推导，语义等价性及 observation 可见性未证明，因此 PIT_SAFE=false（未生成 observation，不代表已发生泄漏）。

| 参数 | 必要字段/方法 | 当前不能物化的原因 |
| --- | --- | --- |
| yield_kg_per_mu | same-scope complete-season production kg / historical planted mu | Receipt kg is delivered quantity; historical area and production coverage are not supplied. Current 736 mu is not a historical denominator. |
| marketable_rate | marketable kg / total production kg at the same governed stage | Receipts and grade labels do not establish the total production denominator or loss stage. |
| first_harvest_offset_days | first harvest date minus canonical phenology anchor date | Receipt date is not proved to be first harvest; phenology anchor is unavailable. |
| maturity_peak_offset_days | natural maturity peak date minus canonical anchor date | Receipt peak is affected by harvest and logistics; no natural maturity or anchor authority. |
| maturity_width_days | existing canonical curve width parameter, fitted to authorized natural maturity evidence | Observed receipt spread is not semantically equivalent to a natural maturity width. |
| maturity_skewness | existing canonical natural-maturity shape parameter under its fitted model | Receipt skewness cannot substitute for the maturity-model shape parameter. |
| harvest_realization_rate | harvested kg / harvestable mature kg in the same window | No harvestable-mature denominator or governed backlog evidence. |

现有五级 fallback 已逐项检查：SAME_FARM_VARIETY、SAME_TOWNSHIP_ALTITUDE_VARIETY、SAME_COUNTY_CLIMATE_ZONE_VARIETY、SAME_PROVINCE_VARIETY、LITERATURE_VARIETY_PRIOR。验收库 observation 为0；parameter_observations 模板只有表头；parameter_inference.yaml 提供回退阈值而非Dx文献先验值；maturity_curve.yaml 是模型超参数，不能冒充七类经验 observation。已提供 CSV 的 schema-only 事实保留。没有合法的 row-bearing fallback 能在当前已核对来源中启用。此结论限于仓库和当前验收库，不声称其他位置不存在数据。

## 正常业务链与停止位置

| 阶段 | 实现/绑定状态 | 本次状态 |
| --- | --- | --- |
| 固定 scope 授权 | location + Dx + 736亩 已提供 | PASS |
| Dx 主数据 | canonical source mapping + master-data service | 已创建且回读 |
| 位置/范围解析 | normal resolve_location_input | BLOCKED：无合法位置参考及范围绑定 |
| Task5 parameter inference | importer、分层推断、版本化结果均已实现 | 未调用；位置门槛未通过且无参数库 |
| Task5→FarmSeasonVarietyPlan | 尚无自动 provenance-preserving adapter | 上游未就绪，未实现/调用 |
| Marketable policy | schema/read存在；无已确认 retention-rate authority | 未写入；不能以Task5商品率替代两类retention |
| Task8 / Task9 | 已有服务入口，依赖各自完整业务 authority | 上游未就绪，未调用 |
| Trial/Core/capture/PIT | 已有正常业务路径 | 未调用，无预测结果 |

Task8/Task9 run ID 是未来由系统产生的结果，不是本次用户缺失字段。本次只报告最早位置身份断点；不把下游未执行状态列成新的外部数据索取清单。PARAMETER_AUTHORITY_UNAVAILABLE 列明七项当前不可用状态，但没有伪造数值、日期、面积分摊或数据可见时间。

## 保护与复现

S4 已终局完成，不重开；未训练/选择候选、未运行 VALIDATION、未读取 TEST、未访问预算库。预算只引用 LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT：8 consumed / 24 remaining，本任务增量0。正常验收库唯一写入为源证实的 Dx 主数据。没有生产代码、模型、迁移或原始XLS变更。

验证范围：固定scope/来源证据一致性，正常位置失败语义、五级回退、主数据及源品种映射回归，JSON和差异检查；最终CI以PR最终SHA核对，CI测试夹具不等于真实Forecast证据。

RESULT=INTERNAL_PATH_BLOCKER_AND_PUSHED
MISSING_EXTERNAL_BUSINESS_FACTS=NONE
CURRENT_REAL_FORECAST_CAPABILITY=BLOCKED_INTERNAL_PATH
V0_3_CLOSEOUT_FORECAST_CAPABILITY_GATE=FAIL
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_FIRST_REAL_SCOPE_FORECAST_REVIEW
