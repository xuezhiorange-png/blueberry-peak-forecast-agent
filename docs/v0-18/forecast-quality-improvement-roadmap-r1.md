# 独立预测质量改进路线图 R1 — 规划，不执行实验

本路线图独立于 V0.18 业务可用性 S0–S6。Owner 仅授权编制文档。
没有真实数据读取、训练、预测、评分、校准或调参授权。下面 Q1–Q6 均
EXECUTION_AUTHORIZED=false，每条必须单独获得数据/实验/输出发布授权。
文档不设新精度目标，业务验收阈值须未来 Owner 在评分前决策。

## 冻结基准与证据身份

V0.15 S5 M1 = V0_15_S5_M1_RIDGE；split EXPOSED_OOT，season 2025–2026，
8,775 origins / 131,625 D1..D15 rows。标签/该产季此前已暴露，不是盲测。
V0.16 S4点汇总同源，不构成新的独立评估或独立样本。

| 指标 | 冻结值（完整 Decimal 在 JSON） | 含义 |
| --- | --- | --- |
| H7 daily WAPE | 约 0.4249224043 | D1..D7 daily errors / daily actual sum，不是 D7 |
| H15 daily WAPE | 约 0.4506174628 | D1..D15 daily errors / daily actual sum |
| H7 cumulative WAPE | 约 0.3519563865 | 每个origin累计量误差，非 daily WAPE |
| H15 cumulative WAPE | 约 0.3491109598 | 每个origin累计量误差，非日均误差 |

历史 PI80/PI90 H7 coverage约0.5389277389/0.7453046953，H15约
0.5057534030/0.7109211776；全部低于名义0.8/0.9。Upper80/90也低于nominal。
H7 candidates61,425、computable60,060、not-computable1,365；H15为
131,625/126,360/5,265。Coverage按daily target rows，不是累计区间coverage。
不得丢掉不可计算样本让指标“更好看”，也不将undercoverage改成成功绿色。

STRICT_PIT=false，historical available_at证明不完整，RETROSPECTIVE_AUTHORITY_USED=true。
日期先后不等于真实信息可得时点。Operational Peak family
OPERATIONAL_PEAK_FORECAST_RUN_V1 / AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1
不是M1；不能附M1指标、区间或sealed attribution到Operational Peak任意run。
Point不是已证明P50、Upper不是已校准quantile、model contribution不是因果。
当前模型没有生产精度合格证明；生产可用性工程验收不能替代该证明。

## Q1 历史误差分析与样本可比性

入口：Owner单独批准只读研究数据、label/prediction seal和比较合同，缺一停止。
先核验model family/fit state/config、特征schema、origin/base/lead/target日期、
scope、标签版本、单位、过滤规则、common rowset/hash及排除计数。
主比较必须配对同一rowset，family/fit state不兼容时分面报告，不能称A/B胜者。
跨模型适用的比较family需另行事前批准，不把两种family身份强制视为相等。

按Base、lead、season position、产量级别、峰前/峰后等维度预声明误差分层；
不能见结果后切桶寻赢家。报告WAPE、MAE、signed Bias、cumulative WAPE及
coverage/completeness、零实际/零预测、极端误差。WAPE denominator=0返回
NOT_COMPUTABLE，不加epsilon；零实际仍进入合法MAE/Bias，不任删outlier。
重叠窗口使误差相关，区间/显著性分析以origin/time/base成组而非逐行独立抽样。
分布、量占比、leave-top-bases敏感性与macro/micro口径分别列出；不伪装为新实际结果。
输出：source绑定误差切片计划、配对/不可比矩阵、分母/缺失协议，不在此轮评分。

## Q2 峰值专项评价

未来专项协议在评分前冻结，不能改写S5历史metric定义。比较窗口为同一完整
D1..D15，峰值日期按最早同值日tie；预测与actual均同单位同entity同scope。
缺日期则整个对应峰metric NOT_COMPUTABLE，短窗口可单独报SHORT_WINDOW，
不可混进完整窗口均值。aggregate峰从同源日曲线得出，不求和各Base peak。

候选日峰指标：signed date shift（pred_date−actual_date）、absolute date MAE、
早/晚比例、quantity signed error、quantity MAE。峰量相对误差在actual峰=0
时不可计算，必须另报数量/样本，不自选epsilon。全零actual日期的“峰日”在
未来协议标记NO_POSITIVE_ACTUAL_PEAK并独立计数，不能因earliest tie假称命中。
历史S5原值保持原定义；未来新口径不能直接比较成“改善”。

Rolling-7定义连续完整7日之和、窗口起点最早tie。在D1..D15内只有9个合法
起点；报告start-date signed/absolute error、rolling7 peak quantity MAE、
量偏差及可计算数。H7前缀累计 != rolling7最大窗口。3日持续峰可作为独立
预声明补充，不换主指标。Owner可定义日期容忍带命中率，但容忍带目前null，
不得自行提出“±N天达标”。峰值专项和daily WAPE并列，不能只凭WAPE选型。

已有S5 M1日峰date MAE约6.1284330484天、quantity MAE约3185.2562525668kg；
rolling7起点MAE约3.5376638177天、quantity MAE约15081.7599517052kg。
这是旧EXPOSED_OOT原定义的历史观察，不是未来容忍阈值或生产通过结论。

## Q3 区间覆盖率与可靠性

保留S2所有UNDER_NOMINAL和candidate/computable/not-computable/covered计数。
区分双侧PI与单侧planning bound，endpoint inclusion、width/expansion、nominal
及coverage gap明确，零/不可计算不能补point。评价是daily target-row层面，
不宣称aggregate或cumulative coverage。Region/Company须另有合法校准协议。
按lead/scale/season/base预声明诊断并报告小样本；重复目标/重叠窗口需成组
不确定性评估，覆盖接近nominal仍不能证明稳定未来coverage或conditional quantile。

未来候选可研究归一化残差、有限数据分层、滑动窗口等，但须预注册pool、
时间成熟、rank、零值处理及calibration与evaluation严格隔离。不得本轮改S2
池或重校准；方法比较需统一rowset和冻结预测，保留宽度与不可计算率，不能
以无限变宽换“成功”。独立reliability曲线/WIS/interval score如新增，也要
先定义量纲、分母和不可用规则，Owner决定utility阈值，无新分数冒充已测结果。

## Q4 预测时点与数据可用协议

至少记录 timezone-aware forecast_origin、source_available_at、ingested_at、
as_issued_at、model/input/prediction seal、actual_available_at和scoring_cutoff。
业务date、文件mtime、DB created_at、S2日期成熟或S2上海午夜anchor不能替代
真实签发/available_at证据。数据更正append-only，保留版本及首次可用/更正时点。

可用于某origin特征的数据必须source_available_at与ingestion证据不晚于
其cutoff；缺证明标记retrospective或NOT_PROVEN，不宣称strict PIT。
标签只在目标成熟且actual_available_at≤scoring cutoff后评分，不作为此前
模型feature输入。weather as-issued cycle、Harvest State lag和来源publication
必须独立核验。预测在label reader打开前签发、sealed并产生值无关custody receipt。
损坏或缺失receipt停止，不能用重建快照覆盖历史签发事实。

## Q5 未来模型A/B与防标签泄漏

单独Owner批准候选、comparison family、training cutoff、feature/policy、
目标、权重、数据范围和实验次数。沿用跨产季/滚动时间/基地或加工厂留出
作为适用验证轴，留出定义与forecast entity不同需明确映射；不能随机拆相邻日。
scaler/feature fit只用训练部分，calibration不混用evaluation residual；
成熟标签若作为lag feature必须有cutoff可用证据。target-zone隔离，manifest
字段白名单，未知列fail closed，不让target/未来actual/后验状态进入feature。

TRAIN/VALIDATION/OOT分开；先seal prediction再由独立scorer读label。
2025–2026已EXPOSED_OOT，不回溯改称blind。未来未暴露holdout也须访问记录证明。
预注册主/次指标、成组比较、停止与失败保留规则；不反复窥视holdout调参、
不结果导向选rowset或feature，不claim未经验证百分比提升。新fit/预测/seal
使用新authority，不覆盖M1/S2旧artifact。模型promotion需要独立批准。

## Q6 真实数据到位后的prospective准入

顺序：真实数据合法获取/隐私Owner批准 → cohort/来源权限与时点协议 → 冻结
模型/完整input authority → 实际签发并sealed预测 → 目标成熟/标签可用证明 →
独立评分授权 → 公共脱敏evidence/review → Owner业务阈值判定与promotion决策。
每一步单独门禁；数据“到了”不自动授权打开或评分。

当前actual_available=false、access_authorized=false。业务验收阈值、容忍
天数/数量、最小样本/覆盖季节、失败处置由Owner未来事前决定，均不填默认目标。
Prospective不足样本、不完整available_at、源不兼容时保持NOT_VALIDATED或BLOCKED；
隔离合成UI/MCP验收不能解除它们。无自动production promotion、优化或执行。

## 本轮证据和治理

配套JSON原样复制冻结M1 H7/H15WAPE、四个peak指标及S2完整coverage summary，
均以source SHA256绑定，不重新评分。独立合同测试验证等值与UNDER_NOMINAL。
此文档不访问private rows、actual、model参数或生产DB。
所有Q1–Q6只设计，精度目标与业务threshold=null，未来Owner决定；路线图完成
不表示V0.18模型研究或当前季评分被授权。Draft + exact-head CI后STOP。
