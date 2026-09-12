# 跨产季 shape R3：新附件读取与完整性资格结果

## 结论

RESULT=BLOCKED_NO_CROSS_SEASON_MATCHED_SCOPE：**35 个精确同名农场，但 0 个已证明完整产季的合法配对**。
不是没有共同农场、不是缺面积、不是模型训练失败。没有运行真实模型 fit 或跨季评分。
Ridge/经验 shape 的纯函数实现与 synthetic tests 不构成真实训练证据。
本次未达到训练目标，不宣称模型已交付可用；模型/成绩 JSON 是明确 NOT_EXECUTED 状态记录。

基于 #611 head `f16d3a493f395ff019d33e9eb2da17cd5f8eb091` 新分支；
该 head CI 34675078550 已 SUCCESS。R1/R2 原始产物逐文件 hash 核对未变。
本 PR 与 #611 分开，不 Ready、Merge、Release。

## 实际读取新附件

用户提供的两个企业微信本地 XLS 均已完整读取，未用旧 evidence 代替。
仅本地受控处理；原始附件未复制进仓库，未改写原文件。

| 来源 | 数据行，不含各页表头 | 日期范围 | 页数 | 农场/分场/品种标签数 |
|---|---:|---|---:|---|
| 23~24.xls |93761|2023-07-26..2024-06-30|2|56/3/26|
| 24~25.xls |202072|2024-07-01..2025-05-27|4|88/132/25|
| 仓库 2024_2025_receipts.xls |201434|2024-07-01..2025-05-27|4|87/131/23|

新文件字段均为：时间、链路、农场、分场、品种、果径、入库公斤数。
重量字段单位明确为 kg，按本次授权到厂量=采摘量；不做运输或商品率折减。
不按品种建模，不套用旧1–4月/品种/工厂排除规则来制造完整农场总量。
日期、数量空值、负值两份新文件均为 0；七字段相同内容重复均为 0。
旧仓库源七字段重复为 4：不等同有唯一交易ID证明的重复交易，不自动删除。
分页65536行是 XLS 格式上限的连续导出分页，不独立当成产季。

SHA256：

- 23~24：`8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20`
- 新24~25：`f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6`
- 仓库24~25：`a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5`

## 24–25 重叠与 canonical source

UPLOADED_24_25_RELATION_TO_REPO_SOURCE=PARTIAL_OVERLAP。
按共同七字段正规化日期/Decimal/去首尾空格后比较**多重集**，重叠177758行；
新源独有24314、旧源独有23676。旧源加工厂列不在共同字段签名中。
130天日总量不同；农场总量仅一个标签不同：新源格莱莓农场211729.534000kg，旧源没有该标签。
记录差异不能仅由总量相同推断无差异。所有农场总量对照留在私有 manifest。
本次 canonical source 选择新上传24~25；旧文件只做比较，绝不拼接加入训练/评价。

## 完整性与缺日

在模型训练前固定 July01..June30 日历位置；这是对齐/报告日历，不声称每个农场生理产季全年有产量。
不能根据验证期首采/末采/峰日倒推预测窗口。合法更窄产季可以依据独立覆盖证据确定，不能靠选有标签日期产生。
两份 XLS 是逐明细记录，但自身没有农场级导出完整性/无记录即零声明。
只读搜索现有授权证据，只有旧版纳/Dx有限窗口零日授权，不能外推到新整农场或23–24。
因此每个 farm-season 标 UNKNOWN，而非断言业务上确实不完整。
23–24 最少仍有112个日历日没有该农场记录；24–25最少110个。
24–25文件整体止于5月27日，也不能自动断言所有农场都在此之前收季。
不存在负值、null或重复导致的全体淘汰；当前原因明确是完整账本覆盖/未知日状态未证实。

`farm_season_inventory.csv` 保留144条农场-季清单，包含每范围日期、观察/未知日数和排除原因。
`paired_farm_seasons.csv` 采用精确去首尾空格标签匹配，35同名；无模糊别名合并。
这不是把源标签自动升级为主数据业务身份。
`canonical_daily_shape.csv` 保留观察日量及未知日空值，season_total/share 留空。
观察累计量标 observed_partial_total，不冒充整季总量，不对部分曲线归一化后做整季验收。

下一步所需是**指定配对农场的账本覆盖与缺日含义确认**，而非补历史面积。
未获得上述依据前，不以私自补零来启动真实 fit。本次无可报告的峰日误差或WAPE。

## 已实现与未实现

[配置](../../configs/shape_experiment_r3.json) 固定两个计划模型：alpha10两谐波Ridge、等权农场经验mean。
shape 纯函数支持只用2023–2024完整曲线 fit、非负预测、完整日历归一化、hash验证与最早峰窗tie-break。
本轮只验证 synthetic fixtures；真实训练执行集成尚未完成，不能把CLI审计入口称为训练成功。
无第三模型，无大搜索；24–25不是盲测，后续仍须按冻结配置评价一次，不按成绩调参。
shape原语从不使用面积或未来总量，未读取2025_2026_receipts.xls/旧sealed TEST。

## 复现及产物

审计 CLI：`.venv/bin/python -m scripts.run_shape_r3 --train-xls <用户23~24路径> --validation-xls <用户24~25路径> --repo-source data/raw/2024_2025_receipts.xls --output <新的私有目录>`。
真实调用使用用户给定绝对路径，不以占位路径冒充执行；input_manifest绑定实际文件名/hash与sheet结构。
私有持久目录 `/Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3`。
包括 input_manifest、144条inventory、paired scopes、日级聚合、状态记录、R1/R2快照、artifact_manifest。
[公开证据](evidence/multi-season-shape-model-r3.json) 只含汇总、方法和hash；原始XLS/逐日业务CSV均不上传。
表格技能用于字段/单位/重复/缺数检查；不编辑工作簿，CSV由本轮Python程序生成。

46项area-yield测试通过（15新增R3，31既有R1/R2）。Ruff/format/Mypy另行核验。
推送后遵守required CI与full-suite-canary，不修改workflow；尚未终态时准确标PENDING。
