# R3B 同农场上一季 shape 对照

## 决策

RESULT=NO_CLEAR_WINNER。继续保留全局 Ridge，不替换现用模型。
杨柳与南庄均改善，但华兴预测峰日2025-05-28超出文件覆盖，七日窗口2025-05-24至05-30也不完整。
不能将其删除后用两农场平均宣布三农场获胜。FARM_HISTORY_IS_MATERIAL_SHAPE_SIGNAL=NOT_ESTABLISHED。
AREA_ONLY_IS_SUFFICIENT_FOR_PEAK_TIMING=NOT_ESTABLISHED；本试验没有面积变异，不能证明亩数足以决定时点。
现有两农场结果支持继续关注农场历史，但尚不能宣称普遍必要/充分。

## 冻结方法与来源

基于PR612 head 0440426f6c480586c99b2864a645831d3bb097c5，仅新增R3B文件。
[配置](../../configs/shape_r3b.json)在预测/评分前冻结：e0678cdf6ae49ddf3c6c97dded67f9db3f034c99f1c3286ebc96c272f1be0bdf。
两个全局预测直接复用R3A原始full-calendar输出，不refit、不变值。
carry-forward是对每个同名农场调用R3A单农场经验shape：训练已记录量归一化，
July1为0，日index/该季总日数（366→365）线性位置映射，未知位置预测线性插值、边缘常数延伸。
PREDICTION_INTERPOLATION_NOT_LABEL_IMPUTATION；UNKNOWN标签没有更改为零，未按24–25峰日或首采日对齐。
不搜索shift、Spline、Boosting或其他模型，不采用面积/品种/天气特征。
R3A全产物hash在运行前后核验；R1/R2/R3A旧路径和产物未写入。
验证为CROSS_SEASON_OUT_OF_TIME_RETROSPECTIVE / NOT_BLIND，非新的盲测。

## 评价与选择

预测仍为365日非负归一化曲线，预测hash 93dba7516d7a65cfdfbdf42e1a0d05e145e2241151ee46b9790487f388096715 在独立评价进程前冻结。
实际已知支持323日，42日unknown/未覆盖，完整七自然日窗口294个。
FULL_CALENDAR_DIAGNOSTIC保留未知预测质量和全日历预测峰值。
KNOWN_SUPPORT_CONDITIONAL仅评价时将actual和prediction分别按同一K内sum归一，绝不回写预测。
预测峰未知或预测七日窗不完整则对应误差null=NOT_COMPUTABLE。
实际峰是已知账本峰，不声称未观测日期不存在更大峰。
三农场等权；每项宏指标输出computable_farms，不能悄悄改变分母。
选择在结果前冻结为：三农场四项均可算，平均峰日和七日偏移严格改善，平均MAE/WAPE均不增加。
“没有明显恶化”采用零容差保守解释，不根据成绩另定容差。

|模型|峰差均值/中位数(有效农场)|七日偏移均值/中位数(有效农场)|条件MAE|条件WAPE|未知预测质量均值|
|---|---|---|---:|---:|---:|
|Ridge|18.333333 / 19 (3)|17.666667 / 19 (3)|0.004021667073|1.298998464725|0.100221951621|
|全局经验mean|93.333333 / 94 (3)|10.666667 / 12 (3)|0.003755069315|1.212887388828|0.018413758816|
|同农场上一季|7.5 / 7.5 (2)|6 / 6 (2)|0.003093325941|0.999144278810|0.021663551045|

峰差/七日平均的3与2不可直接比较。仅杨柳+南庄共同可评价子集：Ridge峰差12.5天、七日13天；prior为7.5天、6天。仅诊断，不重新选子集发胜者。
三农场条件WAPE仍约99.91%，没有业务精度批准。

|农场|模型|实际峰日|预测峰日|峰差天|实际七日起日|预测七日起日|窗口偏移天|条件WAPE|未知预测质量|
|---|---|---|---|---:|---|---|---:|---:|---:|
|保山华兴农场|ridge|2025-05-09|2025-04-09|30|2025-05-03|2025-04-06|27|1.224997|0.100222|
|保山华兴农场|empirical|2025-05-09|2025-01-24|105|2025-05-03|2025-04-13|20|1.131970|0.018414|
|保山华兴农场|prior|2025-05-09|2025-05-28|NOT_COMPUTABLE|2025-05-03|2025-05-24|NOT_COMPUTABLE|1.167801|0.064991|
|保山杨柳农场|ridge|2025-04-15|2025-04-09|6|2025-04-13|2025-04-06|7|1.220819|0.100222|
|保山杨柳农场|empirical|2025-04-15|2025-01-24|81|2025-04-13|2025-04-13|0|1.122019|0.018414|
|保山杨柳农场|prior|2025-04-15|2025-04-17|2|2025-04-13|2025-04-15|2|0.805342|0.000000|
|建水南庄基地|ridge|2025-04-28|2025-04-09|19|2025-04-25|2025-04-06|19|1.451179|0.100222|
|建水南庄基地|empirical|2025-04-28|2025-01-24|94|2025-04-25|2025-04-13|12|1.384673|0.018414|
|建水南庄基地|prior|2025-04-28|2025-04-15|13|2025-04-25|2025-04-15|10|1.024290|0.000000|

## 业务回答

1. 在两个峰值可评价农场，同农场上一季曲线更接近；第三个无法评价，整体没有明确胜者。
2. 农场历史有初步shape信号，但三个范围不足以确立其普遍重要性，不恢复任何S4选模结论。
3. 本次不能证明仅面积足以预测峰日，也不能把面积线性scale假设等同于timing能力。
总亩产仍WAITING_FOR_HISTORICAL_AREA_DATA，MULTI_SEASON_TOTAL_YIELD_VALIDATED=false，AREA_SCALING_VALIDATED=false。

## 可复现产物与验证

私有目录：/Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3b。
包含预测、配置/源hash冻结、一次评价标记、逐农场metrics、3285日行CSV、metrics.json及artifact_manifest.json。
不提交原始XLS、逐日业务数据、模型曲线。公开[聚合证据](evidence/same-farm-shape-r3b.json)。

```bash
.venv/bin/python -m scripts.run_prior_shape_r3b prepare --source /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed --output /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3b
.venv/bin/python -m scripts.run_prior_shape_r3b evaluate --source /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed --output /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3b
```

已执行一次，不可覆盖原目录重跑。prepare校验所有源文件bytes hash，但不解析24–25标签构建预测。
测试覆盖未知保留、预测归一、非法日期/农场/数值、条件评价不修改预测、峰值不可算、七日完整窗、并列最早、缺证据不发胜者。
本地418项相关测试PASS（含R1/R2/R3A回归），Ruff、format、Mypy 420文件、JSON及diff检查PASS。
本地测试和静态检查完成后才最终push；CI只作exact-head验证，未结束不能宣称PASS。
不改旧模型、旧S4预算、sealed TEST、天气、V0.3基线、R1/R2/R3A。
FINAL_STOP_GATE=COORDINATOR_R3B_SAME_FARM_SHAPE_REVIEW。保持Draft，不Ready/Merge/Release。
