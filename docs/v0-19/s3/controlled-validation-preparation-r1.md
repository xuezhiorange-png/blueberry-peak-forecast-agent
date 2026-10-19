# V0.19 S3 受控对照：仅本地离线准备 R1

TASK_ID=V0_19_S3_CONTROLLED_VALIDATION_PARALLEL_PREPARATION_R1

## 状态与权限

准备基线 `822f453d130ff1ff1b1f5aeaf8fdcf1c87e2da94`，为 S2 #737 合并提交。
启动时 main push CI [39267331822](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/39267331822)
尚在运行。最新观测单列于本次机器记录，不回填历史 S0/S1/S2 状态。
本轮只授权独立工作树内的源码、合成测试与公共合同审阅；**不 commit、push 或创建 S3 PR**。
即使 S2 CI 成功，真实数据、实验、评分及正式 S3 PR 也没有自动获准。
S3_FORMAL_COMPLETE=false；S3_REAL_SCORING=BLOCKED。

## 固定对照与模块

基线 `OPERATIONAL_PEAK:AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`；唯一候选
`BIN_CENTER_LINEAR_PER_BIN_MASS_V1`，不修改 S2 参数与方法。
`backend/research/v019_synthetic_validation.py` 是无文件、网络、DB、HTTP/MCP 读取的
纯研究模块，不导入 backend/app，不注册为生产业务权威，不接收真实数据入口。
它复用现有 S2 `generate_candidate`；没有重新开发模型或第二候选。

`generate_synthetic_predictions(C0, requests)` 使用已登记的相同输入，核对 input/profile
身份，生成完整 support 上的候选，再按事前声明日期切片。基线从相同输入取值；
H7/H15 不重归一化。缺失输入或生成失败保留 C0 单元和失败原因，不删除困难 origin。
测试中的任意手写预测只用于算术与反例 oracle，不冒充 S2 算法输出。
另外有直接调用冻结 S2 算法的端到端合成测试。

## 两阶段与身份

A：`freeze_predictions` 不接受 labels 参数。C0 是按 sample_id 排序的不可变登记集合，
包含组织、基地、子农场、品种、面积及生效日、产季、时区化 origin/issued_at/cutoff、
输入 available_at/ingested_at、window/完整日期、物理口径及单位、profile/input hash、
label authority 身份、训练范围 hash、split 和权威证明清单。
记录双方各自 model/fit/source 身份、预测日值、独立预测 hash、C0 hash、S2 配置 hash。
重复比较单元、额外输入、缺失但无失败原因的预测及同基地同季多个 FULL_SEASON 发行点拒绝。
封存记录可以包含预先登记的标签来源身份，但没有标签内容。

B：`evaluate_synthetic` 先确认 SYNTHETIC 权限及标识，再重建和校验 prediction seal，
然后才访问标签序列。标签必须绑定相同 sample identity / authority，成熟且在 scoring
as_of 时可用；预测输入必须在 cutoff 可用。未登记、重复标签拒绝；缺失标签保留不可计算。
scoring 输出另含 label content hash、as_of、预测 seal、结果 canonical hash。

SHA256 仅证明字节内容绑定，**不是数字签名、数据授权或真实签发时间证明**。
将真实数据改名 SYNTHETIC 不能变成合法授权；本模块不是对恶意调用者的数据防泄漏系统。
合成 fixture 的 AVAILABLE 仅是人工构造的测试前提，不代表任何真实来源已核验。
未来真实执行须另建经过 Owner 授权的可信来源适配和独立保管流程；本次不实现它们。

## 十指标、共同集合与边界

严格继承 `s1/peak-metrics-and-experiment-protocol-r1.md`，不改分母、权重或峰定义。
每个 split、H7_PREFIX/H15_LOCAL/FULL_SEASON 单独输出，不混汇。
全部指标运算使用独立 Decimal context：precision 50、ROUND_HALF_EVEN；不经过 float。

| 指标 | 当前离线实现 |
|---|---|
| SEASON_TOTAL_WAPE | 仅完整预注册单一整季发行；Σ绝对总量差 / Σ实际总量 |
| DAILY_WAPE | 共同 origin-target 实例 micro pooled；零实际行仍进入分子 |
| DAILY_MAE | Σ逐日绝对误差 / 共同 origin-target 行数；重叠 origin 不去重 |
| SINGLE_DAY_PEAK_DATE_MAE | 双方各自最早最大日；正实际完整窗口等权日期绝对差 |
| SINGLE_DAY_PEAK_QUANTITY_MAE | 各自最大日量差；全零实际仍保留数量误差 |
| ROLLING_7DAY_PEAK_START_MAE | 连续完整七日起点；并列最早；H15 恰九个候选窗口 |
| ROLLING_7DAY_PEAK_QUANTITY_MAE | 各自最大七日累计 kg 差，不是单日或 kg/day |
| BASE_BREADTH | 共同 daily MAE 样本按基地合并绝对误差；改善/持平/退化数及改善基地实际量占比 |
| SAMPLE_COVERAGE | 对七项误差指标分别报告 common/C0；另列基地、target-row 覆盖及成员 hash |
| NOT_COMPUTABLE_COUNT | 各指标 C0−common，按冻结优先顺序每单元一个主因，不重复计数 |

BASE_BREADTH 的基地分母与实际质量分母分开；零质量占比为 null，没有共同基地不可计算。
coverage/count 是逐误差指标的诊断映射，不把它们递归纳入自身分母。
完整空 C0 明确 EMPTY_COHORT、count=0、value=null，不发布零误差。
零 actual：峰日期/rolling 起日不可计算；峰量/MAE 可计算；整个 WAPE 池为零才不可计算。
缺日、重复、乱序、负值、非有限值不修复、不填零。短于七日不算 rolling7；
FULL_SEASON 需要预登记完整日历，不能将 H15 命名为整季或拼接多 origin。
分层聚合不在本准备器实现：未来必须先证明成员完整性和物理口径，再逐日聚合，不可相加峰值。

每项主配对结果在相同 Cm 上计算；保留双方预测存在数、全 C0、排除原因、成员及 hash。
所有结论都限定 CONDITIONAL_ON_COMMON_COMPUTABLE_COHORT，没有自动 winner。
保留 signed bias、逐 lead 误差、早/晚/同日、基地 paired delta；H15 按绝对误差降低量
排序（并列基地 ID）移除完整 top1/top2 基地重算日 MAE/WAPE，仅是敏感性诊断，不替换主结果。
未建模 origin 相关性，不做逐行 bootstrap 或显著性宣称，不发明业务容忍带。

## 十二类真实权威预检（不探测私有路径）

| 项 | 必须提供的未来证据 | 本次真实状态 |
|---|---|---|
| 基地/子农场/品种 | 合法版本化 ID 及成员映射 | NOT_VERIFIED |
| 面积/生效日 | 权威面积、单位、适用时间 | NOT_VERIFIED |
| run/发行时间 | 不可变 run identity、issued_at | NOT_VERIFIED |
| model/profile/fit | 明确版本与原始 hash | NOT_VERIFIED |
| 采收日/单位 | 本地业务日期、真实采收 vs 到厂代理 | NOT_VERIFIED |
| 标签权威 | 批准来源、原字节/行集 hash | NOT_VERIFIED |
| available_at/ingested_at | 实际系统可用时间证明 | NOT_VERIFIED |
| 输入 cutoff | 输入均在 cutoff 前合法可用 | NOT_VERIFIED |
| 标签成熟/完整性 | 成熟 as_of 与完整日历证明 | NOT_VERIFIED |
| Train/Validation/Exposed OOT | 事前登记划分，不随机切相邻日期 | NOT_VERIFIED |
| C0/Cm 成员 | 固定共同候选行集与成员 hash | NOT_VERIFIED |
| 预测/标签 seals | 独立保管、签发时间及内容完整性 | NOT_VERIFIED |

允许状态 AVAILABLE / NOT_VERIFIED / MISSING / BLOCKED。没有打开私有内容，故不凭空
把未知来源写成物理缺失 MISSING；可用性不等于读取许可，文件可能存在也不等于授权。
真实读取及实验授权分别 BLOCKED，预测/评分隔离还须独立实施授权。
需要 Owner 后续明确数据集、允许字段、来源/时间证明、实验执行和评分范围，以及正式 S3 交付。

## 可复现与交付

新测试：`backend/tests/area_yield/test_v0_19_s3_synthetic_validation.py`。
执行 `.venv/bin/pytest -q backend/tests/area_yield/test_v0_19_s3_synthetic_validation.py`；
另运行 S0/S1/S2、选定 V0.8/V0.13/V0.15/V0.18 历史及 core metrics 合同，
Ruff check/format、Mypy backend/app backend/research、Git diff/白名单检查。
机器记录提供实际命令/退出码、固定来源 SHA256、合成覆盖矩阵及本地源文件 hash。
新源文件尚未提交，无虚构 Git source commit；将来正式封存须绑定真实不可变提交。
已有历史代码取固定 `822f...` Git bytes，冻结文档/JSON仍检查当前原字节；
本准备器的新测试不将未来工作树测试源码当成历史冻结对象。

仅证明合成框架结构/算术与封存检查。STRICT_PIT=false，真实精度未评价；
2025–2026 已暴露不是 blind OOT，M1 WAPE 不是 Operational Peak 精度。
未读取当前 2026–2027 采收、模型 artifact 或业务库，无训练/拟合/调参/真实评分。
无真实 WAPE、峰时 MAE、改善百分比、基地显著性、模型晋级或生产准入结论。
本地通过不等于 S3 正式完成，也不替代独立评审或 CI。准备完成即 STOP。
