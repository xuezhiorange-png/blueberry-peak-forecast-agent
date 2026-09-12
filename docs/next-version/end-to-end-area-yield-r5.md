# R5 冻结总量 × shape 的端到端回溯比较

## 结果

RESULT=FARM_HETEROGENEITY_OBSERVED。
宏观CURRENT_BEST_LIMITED_EVIDENCE_COMPOSITE=B2，南庄最佳B2；杨柳NO_CLEAR_WINNER（A2总量更好，B2日误差更好）。
不是生产模型、业务批准或跨地区泛化证明；只包含两个面积已确认农场及一次非盲跨季回溯。
本轮没有新fit、模型搜索、日期shift、验证总量校正、shape重训练或旧模型替换。

## 固定组件与方法

基于#613 head caf011687773fb75d943d6336c2f4916e60eef80，已包含#612 shape代码；独立R5分支，不更改两PR证据。
总量load R4 model_global_median.json / model_same_farm_prior.json并调用predict_total。
shape直接load R3B冻结完整365日share数组（全局ridge另与R3A字节相同的数组核对），不调用carry_forward.fit。
杨柳393.4亩、南庄152.35亩；面积仍BUSINESS_CONFIRMED，跨季固定，不扩展农场。
[配置](../../configs/composite_r5.json)hash 69166c143042903b88756e315782a1b5c2a07198d50bc6aa70b5410116a5266b 先于本轮评分冻结。
预测hash d9879fa63af299ef857c2060a6c64d4aaf64e6487dbf7df84a0784bc0c4c57f3；新进程组件load，预测冻结后另进程评分。
训练来源23–24，评价24–25，VALIDATION_BLINDNESS=NOT_BLIND。没有24–25标签驱动参数选择。

|组合|总量|shape|
|---|---|---|
|A1|global median yield|global Ridge|
|A2|global median yield|same-farm prior shape|
|B1|same-farm prior yield|global Ridge|
|B2|same-farm prior yield|same-farm prior shape|

选择在评分前冻结为唯一Pareto占优：总量相对误差、daily WAPE、峰日差、七日偏移均不大于其他组合，且对每个竞争组合至少一项更优。否则NO_CLEAR_WINNER。
不因两农场而设计生产路由；该比较规则只用于本次报告，不替换原R4选择/原R3C暂停结论。

## 数量和标签边界

daily_kg=冻结total×冻结share，Decimal六位HALF_EVEN，不做残差回填、不用actual校正。
share非负、sum误差≤1e−12；mass tolerance=日数×0.0000005kg + total×1e−12。
八组实际mass error绝对值≤0.000005kg，全PASS。同total两shape的总量误差严格相同（按冻结total计），日行sum另报告舍入差。
两农场每组323 known days、42 unknown/未覆盖；UNKNOWN不补零。日MAE/WAPE只用相同known行。
known-support conditional WAPE只用于评价，不能回写预测或改变总量。
总量采用既有STRICT_ELIGIBLE工程账本资格，未证明未知时段生物学总量为零。
预测峰值用现有core_forecast compute_point_series_metrics，EARLIEST_DATE、严格七自然日累计、EARLIEST_START_DATE。
实际峰来自已知账本；实际七日只能取完整窗口。沿用R3C删失状态，本次八组峰/七日全EXACT_COMPUTABLE。
这不等于未观察产季时段的真实全局峰已经证明。

## 两农场八组合实际结果

|farm|组合|预测总量kg|总量相对误差|daily MAE kg|daily WAPE|conditional WAPE|预测峰日|峰差天|预测七日起日|七日差天|
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
|保山杨柳农场|A1|417358.198870|0.069956|1646.053920|1.184789|1.220819|2025-04-09|6|2025-04-06|7|
|保山杨柳农场|A2|417358.198870|0.069956|1135.989806|0.817657|0.805342|2025-04-17|2|2025-04-15|2|
|保山杨柳农场|B1|514540.069956|0.146604|1705.833780|1.227817|1.220819|2025-04-09|6|2025-04-06|7|
|保山杨柳农场|B2|514540.069956|0.146604|1095.415494|0.788453|0.805342|2025-04-17|2|2025-04-15|2|
|建水南庄基地|A1|161628.168780|0.842274|481.251614|1.771788|1.451179|2025-04-09|19|2025-04-06|19|
|建水南庄基地|A2|161628.168780|0.842274|404.290866|1.488448|1.024290|2025-04-15|13|2025-04-15|10|
|建水南庄基地|B1|123993.044072|0.413300|429.687508|1.581949|1.451179|2025-04-09|19|2025-04-06|19|
|建水南庄基地|B2|123993.044072|0.413300|325.263108|1.197497|1.024290|2025-04-15|13|2025-04-15|10|

|farm|组合|预测单日峰kg|峰量绝对误差kg|预测七日累计kg|七日累计绝对误差kg|
|---|---|---:|---:|---:|---:|
|保山杨柳农场|A1|3569.507528|15374.019472|24966.030085|94673.530915|
|保山杨柳农场|A2|10504.078154|8439.448846|67405.925936|52233.635064|
|保山杨柳农场|B1|4400.667480|14542.859520|30779.371057|88860.189943|
|保山杨柳农场|B2|12949.953117|5993.573883|83101.398128|36538.162872|
|建水南庄基地|A1|1382.344870|4788.453130|9668.466404|18238.974596|
|建水南庄基地|A2|6526.098538|355.300538|33384.159778|5476.718778|
|建水南庄基地|B1|1060.465819|5110.332181|7417.163668|20490.277332|
|建水南庄基地|B2|5006.496267|1164.301733|25610.657015|2296.783985|

## 等farm宏指标

|组合|平均总量相对误差|平均日MAE kg|平均日WAPE|平均峰差天|平均七日偏移天|
|---|---:|---:|---:|---:|---:|
|A1|0.456115|1063.652767|1.478288|12.5|13|
|A2|0.456115|770.140336|1.153052|7.5|6|
|B1|0.279952|1067.760644|1.404883|12.5|13|
|B2|0.279952|710.339301|0.992975|7.5|6|

宏daily MAE是两个farm各自日MAE均值，非跨farm kg规模加权。即使B2最好，其日WAPE仍约99.30%，不能叫高精度。
GLOBAL_SHAPE unknown_prediction_mass两farm均0.100221951621；PRIOR_SHAPE两farm均0。
conditional WAPE全局shape宏1.335999，同农场shape宏0.914816，与total切换无实质变化（仅微舍入）。

## 组件贡献与业务回答

总量模型切换GLOBAL→PRIOR：
- 固定global shape：宏总量相对误差0.456115→0.279952，日WAPE1.478288→1.404883；峰时不变。
- 固定prior shape：同样总量改善，日WAPE1.153052→0.992975；峰时不变。
- 杨柳总量相对误差0.069956→0.146604（变差）；南庄0.842274→0.413300（改善）。

shape切换GLOBAL→PRIOR：
- 固定global total：日WAPE1.478288→1.153052，总量误差不变。
- 固定prior total：日WAPE1.404883→0.992975，总量误差不变。
- 两种total下平均峰差均12.5→7.5天、七日13→6天；杨柳分别改善4/5天，南庄6/9天。

因此：
1. 全日历总量误差来自亩产模型，shape归一化不能修复它；known-support日误差同时受两组件影响。
2. 本次峰日/七日时点改善来自same-farm shape，不是换total带来的。
3. prior×prior并非每farm所有指标都占优：南庄B2占优，杨柳A2与B2有tradeoff。
4. farm-specific异质性存在，不能由两farm宏赢家强制生产统一。
本次shape切换对日WAPE的改善幅度大于total切换，但这只是固定八组结果的描述，不是一般因果贡献定律。

## 单独结构示例

固定选择B1（原R4 prior total + 原R3C保留global Ridge），不是看完R5成绩后更换策略。
杨柳393.4亩，亩产1307.931037；示例期间2026-07-01..2027-06-30，沿固定365日season-position映射，不fit。
冻结total514540.069956kg，日行sum514540.069955kg（−0.000001kg舍入）。
单日峰2027-04-09 / 4400.667480kg；七日2027-04-06..04-12 / 30779.371057kg。
FORECAST_EXAMPLE_ONLY=true。不是未来种植计划或准确率证据；完整365日Ridge支持是原组件合同，不因评价结果缩窗。
点预测，不制造校准P80/P90。

## 产物、命令、测试

私有目录 /Users/charles/Documents/blueberry-area-yield-artifacts/end-to-end-r5。
包含component_manifest、冻结预测、2920条组合日行、八行逐farm指标、组件delta、有限证据比较、365行结构示例和artifact_manifest。
原始XLS、逐日标签及预测文件不提交Git，公开[聚合/hash证据](evidence/end-to-end-area-yield-r5.json)。

```bash
.venv/bin/python -m scripts.run_composite_r5 prepare --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/end-to-end-r5
.venv/bin/python -m scripts.run_composite_r5 score --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/end-to-end-r5
.venv/bin/python -m scripts.run_composite_r5 example --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/end-to-end-r5
```

已成功执行，排他目录与文件防覆盖。prepare校验源文件hash但不解析validation labels；无fit。
本地447项相关测试PASS（R1–R4回归），Ruff/format/Mypy（424源文件）/JSON/diff PASS。
所有源组件manifest多阶段hash校验，无R1–R4写入。没有S4重开/旧TEST/天气/未来计划/旧baseline变更/新训练。
完成本地验证后一次push，GitHub standard/full-suite为最终exact-head验证，未结束报告PENDING。
保持独立Draft PR，不Ready/Merge/Release。FINAL_STOP_GATE=COORDINATOR_END_TO_END_R5_REVIEW。

