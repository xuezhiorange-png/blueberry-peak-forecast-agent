# R4 用户确认面积后的真实总量训练

## 结果

RESULT=SAME_FARM_PRIOR_YIELD_BEST。SELECTED_TOTAL_MODEL=SAME_FARM_PRIOR_SEASON_YIELD。
两个确认农场、四个STRICT_ELIGIBLE farm-season，真实fit两个简单基线并完成一次跨季比较。
EVIDENCE_STRENGTH=LIMITED_TWO_FARM_CROSS_SEASON；不是普遍适用模型、业务批准或面积外推验证。
旧[面积阻断证据](evidence/total-yield-r4.json)保留历史；本文件为用户确认后的新状态。

## 面积和身份授权

[新配置](../../configs/confirmed_total_r4.json)绑定用户明确确认：杨柳393.4亩、南庄152.35亩，basis=BUSINESS_CONFIRMED。
南庄基地与南庄农场的等价来自用户授权，不是字符串相似度；旧S3area package和mapping未修改。
旧source area package SHA256=02fe4b00e35589578fa7fd7a7cc6550bf34c9bfb6cb4a8926770878bce2a66df。
新增确认层保留original_source_label、source_reference、source hash与用户confirmation，未向其他农场推广。
HISTORICAL_AREA_GRAIN=FARM，两个季节共用面积，不需要逐季面积表。华兴未知面积继续排除，不等待。

## 总量资格与时间隔离

复用R3A源hash和资格表；两农场两季strict=true、边界buffer合格、active-span global unknown=0。
不放宽任何规则，没有补造标签或用shape补产季总量。
这里的总量采用此前获准的STRICT_ELIGIBLE工程账本口径；未证明所有未覆盖/全源UNKNOWN日期的生物学总量。
用户已确认到厂=采摘。面积新确认不更改旧日期标签，也不把全源未知日变成零。
MULTI_SEASON_TOTAL_YIELD_VALIDATED=true仅表示上述限定口径跨季比较真实执行，非严格历史修订可得性PIT或泛化已证明。

|农场|面积亩|23–24总量kg|23–24亩产|24–25总量kg|24–25亩产|
|---|---:|---:|---:|---:|---:|
|保山杨柳农场|393.4|514540.070|1307.931037|448751.251|1140.699672|
|建水南庄基地|152.35|123993.044|813.869669|87732.981|575.864660|

真实fit仅使用两个23–24样本。GLOBAL_MEDIAN=1060.900353kg/亩，prior保留各自23–24亩产。
输入预检解析总量资格表含两季行，但fit只接受过滤后的23–24；不将24–25数据用于训练、系数、调整或选择前预测。
配置hash=c082688b794c31dca316d6b1fc6340d66535192b2302c0ccdb2b865b4d1849f5，先于实际运行冻结。
独立进程加载模型冻结四条预测后才启动评价，prediction hash=4b7f219afbb78d389dfb08144ad1d86c6ba270f1a378df375174152b08dae1c0。
（以私有predictions_before_scoring.json及其canonical hash为精确机器依据。）
无MODEL_C、复杂搜索、24–25重拟合、shape重评或自动重试。模型fit阶段一次，两种模型在同一两农场上四项比较。

## 完整逐农场比较

相对误差为绝对误差/actual；kg与kg/亩six decimals HALF_EVEN，单农场比例先落盘6位后宏聚合。
P90为排序后位置0.9×(n−1)线性插值，所有farm等权。kg weighted WAPE独立业务诊断，不用于替换宏选择。

|farm|模型|实际亩产|预测亩产|亩产绝对误差|亩产相对误差|实际总量kg|预测总量kg|总量绝对误差kg|总量相对误差|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|保山杨柳农场|global|1140.699672|1060.900353|79.799319|0.069956|448751.251|417358.198870|31393.052130|0.069956|
|保山杨柳农场|prior|1140.699672|1307.931037|167.231365|0.146604|448751.251|514540.069956|65788.818956|0.146604|
|建水南庄基地|global|575.864660|1060.900353|485.035693|0.842274|87732.981|161628.168780|73895.187780|0.842274|
|建水南庄基地|prior|575.864660|813.869669|238.005009|0.413300|87732.981|123993.044072|36260.063072|0.413300|

|宏指标|global|prior|
|---|---:|---:|
|YIELD_MAE kg/亩|282.417506|202.618187|
|YIELD_MAPE|0.456115|0.279952|
|YIELD_WAPE|0.329050|0.236074|
|TOTAL_REL_ERROR median/mean|0.456115|0.279952|
|TOTAL_REL_ERROR P90|0.765042|0.386630|
|kg-weighted WAPE诊断|0.196256|0.190218|

冻结规则是prior同时严格改善宏yield MAE、yield MAPE、total relative mean才选prior；本次符合。
杨柳单独是global更好，宏提升主要来自南庄；不是每个农场都获胜。
固定面积下yield相对误差和total相对误差代数上等价（除舍入），不能当两份独立精度证据。
没有正式批准的绝对业务误差门槛，业务可用性仅LIMITED_CROSS_SEASON_EVIDENCE。

## 真实加载与按面积示例

模型hash=a2fc23b668e002e123418a5a028ffa823198ea64a969caff92cc8d7f4287bc0c。
选定模型文件hash=d7d8b91ea728b51647676fa6b262bec3686b454f839bc6035d0393ee07d3b853。
新进程load、不fit，用各自确认面积输出：杨柳514540.069956kg；南庄123993.044072kg。
亩产分别1307.931037及813.869669。它们是23–24模型的结构调用示例，不是新产季业务计划。
和23–24总量的微小差异源于亩产6位舍入后乘回面积，差分别−0.000044kg、+0.000072kg，不人为改总量以强制回放。
同一杨柳亩产按100/500/1000亩得到130793.103700 / 653965.518500 / 1307931.037000kg，缩放检查PASS。
LINEAR_AREA_SCALING_IMPLEMENTED=true，AREA_SCALING_VALIDATED=false。prior未知农场fail closed，无静默global fallback。
本轮未执行可选shape组合：COMPOSITE_FORECAST_EXAMPLE_ONLY=false；不借组合暗示业务已验收。

## 私有产物和实际命令

新目录 /Users/charles/Documents/blueberry-area-yield-artifacts/total-yield-r4-confirmed；不覆盖total-yield-r4旧阻断目录。
包含确认binding、四行yield样本、training manifest、两个模型JSON、预测冻结、一次评价标记、逐farm预测CSV、metrics、selected model、两个预测示例及artifact manifest。
Git仅代码/配置/授权值/聚合结果/hash，不提交原始XLS、模型系数文件或日业务明细。

```bash
.venv/bin/python -m scripts.run_confirmed_total_r4 train --source /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed --output /Users/charles/Documents/blueberry-area-yield-artifacts/total-yield-r4-confirmed
.venv/bin/python -m scripts.run_confirmed_total_r4 predict --source /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed --output /Users/charles/Documents/blueberry-area-yield-artifacts/total-yield-r4-confirmed
.venv/bin/python -m scripts.run_confirmed_total_r4 evaluate --source /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed --output /Users/charles/Documents/blueberry-area-yield-artifacts/total-yield-r4-confirmed
.venv/bin/python -m scripts.run_confirmed_total_r4 examples --source /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed --output /Users/charles/Documents/blueberry-area-yield-artifacts/total-yield-r4-confirmed
```

全部已成功执行，排他文件防止覆盖，代码hash绑定期间未改训练/评价代码。
本地438项相关回归PASS，Ruff/format/Mypy（423源文件）/JSON/diff PASS。旧R3A/R3B/R3C及R4阻断产物hash parity PASS。
旧S4/TEST/预算、V0.3、R1/R2/R3均未改，无天气/未来计划/部署/模型替换。
[机器证据](evidence/confirmed-total-yield-r4.json)。保持#613 Draft，GitHub最终exact-head验证未完成不得写PASS。
FINAL_STOP_GATE=COORDINATOR_TOTAL_YIELD_R4_CONFIRMED_AREA_REVIEW。
