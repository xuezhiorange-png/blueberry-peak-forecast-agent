# V0.21 S3：高峰与滚动预测评价准备

TASK_ID=V0_21_S3_PEAK_AND_ROLLING_EVALUATION_READINESS_R1

本阶段交付可执行的离线合成评价器，输入为已声明的预测向量，而非新模型。所有示例均为 `SYNTHETIC_TEST_FIXTURE`、`RECORDED_INBOUND_WEIGHT`、kg；没有读取真实农事、入库标签、私有模型或业务数据库，没有训练、生产预测变更或 S4 实现。合成差异不证明农艺增益或真实精度。

## 输入与复用

`backend/research/v021_evaluation_readiness.py` 直接消费 S1 周期结果和 S2 结构结果，先调用原 S2 `prepare()` 独立重算其 S1/V0.20 关联。完整来源账本仅作为独立核验材料；预测输入只采用原 S1/S2 已筛选的 origin 快照，不把完整事后账本当作当时特征。源包、面积、完整七维成员、修订、时区及来源关系原样保留。

V0.19 的 `_calendar_reason`、`_peak`、`_errors`、`_fraction` 和研究评价 `_accumulator` / `_finish` 原样复用。原 `_add` 只认识 H7/H15，不能用于任意长度产季；本适配器按真实 scope 长度填充相同 accumulator，继续调用原 finalizer。没有改写十指标公式，也没有把入库重量改名为旧评分器要求的采收物理量来通过门禁；不调用或放宽原真实执行权限接口。

原封存模块限定真实历史 C0/授权及具体历史日历，不能直接接收本版任意合成周期。S3 沿用 S1 已有确定性规范化/Hash，增加最薄的合成 registration 和 prediction seal。封存后独立重算并逐字段比对，未封存或发生修改时先拒绝，再读取标签。

## 三个独立步骤

1. `register(s1_result, s2_result, protocol)` 无预测数值或标签参数。冻结 comparison family、C0 全集、split、成员、产季/品种/制度、面积口径、origin/cutoff、scope/calendar、来源/训练范围、两个模型/fit/config/version 和独立标签 authority/version。完整产季每 Base/Season/split 只允许一个事先选择的发行版本。未知边界和非法成员保留原因，不能缩小 C0。
2. `seal_predictions(registration, predictions)` 不接受标签。绑定 origin 特征 Hash、模型/fit、六位 kg 曲线及预注册支持范围，同一 member/origin/model 只允许一个版本；H7/H15 从同一向量取值。发行时间必须等于本例已冻结快照 cutoff：较晚发行拒绝，较早发行也因快照可能使用其后输入而拒绝。来源可见/入库时间不得晚于 cutoff 或发行时间；训练截止日早于 origin。声明失败、缺预测或残缺日历全部保留。
3. `score(seal, labels, as_of=...)` 先独立重建 registration 和预测 seal，再接受单独标签接口。核验 source/version、成熟/完整证明、可见时间、成员、面积、单位、物理口径及逐日支持。重叠 scope 中同一 member/date 的标签相互矛盾时拒绝所有受影响成员，不选择有利版本。标签业务成熟是来源数据完成的证明，与蓝莓生物物候成熟无关。

CLI 只打开明确指定的文件；禁止真实类别、未知字段、重复 JSON 键、符号链接和超限输入。输出目录必须新建，0700；文件0600，不覆盖旧结果。机器 UTC 时间、源码和文件 Hash 写独立 manifest，不进入业务 Hash。合成身份是执行边界，不构成真实来源权威。

## 四个不同的评价范围

| 评价族 | 日期边界 | 能回答的问题 |
|---|---|---|
| FULL_SEASON_PEAK | 预先注册的 season_start…season_end | 本完整产季的单日、最大连续7日/15日峰及其每日向量 |
| DECLARED_REMAINING_SEASON_PEAK | 声明 remaining_start…同一个 season_end，start≥D+1 | 本声明剩余产季内的峰，名称始终保留“声明剩余产季” |
| ORIGIN_H7_PREFIX | D+1…D+7，必须来自完整 H15 预测支持的前缀 | 未来7日每日与累计误差及局部峰 |
| ORIGIN_H15_LOCAL | D+1…D+15 | 未来15日每日与累计误差及局部峰 |

日历不得从实际峰日或最后收货日反推。改名不能保留原局部日期范围：新的剩余范围需重新事前注册并一直到原 season_end；封存后修改任何边界直接拒绝。各曲线逐日严格对齐，不补零、不拼接 origin。全 scope 缺日时该 scope 不评分；不足7/15日但本身完整的短 scope 允许每日/单日等其他指标独立计算。

预测和实际分别遍历其完整 scope 寻峰，累计重量最高、并列取最早起点，保留各自不同的每日峰窗。不得用实际峰窗指定预测峰窗或将地块峰值相加。全零 actual 的数量有效，峰时没有正峰，返回 `NO_POSITIVE_ACTUAL_PEAK`。仅有一个候选窗口时保留合法的0误差及原分母，同时输出 `candidate_window_count=1`、`timing_skill_interpretable=false`。

## 指标与公平样本

原十指标继续输出，`SEASON_TOTAL_WAPE` 仅完整产季可用；另外三个范围不借用此指标。新增四项独立命名：

| 指标 | 使用范围 | 分子 / 分母 |
|---|---|---|
| V0_21_ROLLING_15DAY_PEAK_START_MAE | 完整、声明剩余分别评价 | 双方各自最大15日峰起点绝对日期差之和 / 共同可计算窗口数 |
| V0_21_ROLLING_15DAY_PEAK_QUANTITY_MAE | 完整、声明剩余分别评价 | 双方各自最大15日累计kg绝对差之和 / 共同完整窗口数；全零实际可参加 |
| V0_21_ORIGIN_WINDOW_TOTAL_MAE | H7、H15分别 | 每 origin 的 abs(Σ预测−Σ实际)之和 / 共同窗口数 |
| V0_21_ORIGIN_WINDOW_TOTAL_WAPE | H7、H15分别 | 每 origin 的 abs(Σ预测−Σ实际)之和 / 共同窗口Σ实际kg |

kg 精确到六位，所有除法 precision=50；不加 epsilon。保留原始分子/分母、ratio、逐成员 signed/absolute 日误差，不从显示舍入值复算。窗口累计误差允许窗口内抵消，不能用它替代 DAILY_MAE / DAILY_WAPE。

每个 comparison family / evaluation family / split / metric 单独形成 Cm。输出 C0 N、Cm ID及Hash、N−Cm、失败/不可计算原因、逐样本/基地/日期覆盖、基线/候选差值。模型缺失或覆盖不同，诊断 `INCONCLUSIVE`，不会因困难成员退出就宣布胜出。指标方向不一致输出 `MIXED`。重叠 origin 仍保留，但明确不是相互独立统计样本，未计算显著性或因果效果。

## 实际执行的合成数值

完整例为 SYN-BASE-0，2024–2025，日历2025-03-02…04-01（31日），完整产季发行 origin=03-01；另外注册03-10和03-11滚动 origin。有效面积50mu，来自显式合成连续性，非真实权威。输入和计算输出见 `examples/`，可用下面命令重建。

| 完整产季结果 | 基线 | 候选 | 实际 |
|---|---:|---:|---:|
| 总量kg | 104 | 101 | 108 |
| 每日绝对误差和kg | 122 | 7 | — |
| 最大连续7日kg | 56 | 63 | 70 |
| 最大连续15日kg | 72 | 85 | 92 |
| 最大15日起点 | 03-09 | 03-02 | 03-02 |

基线15日起点误差7日、峰量误差20kg；候选分别0日、7kg。每日误差改善，但产季总量绝对误差从4kg变7kg，因此完整产季诊断为 MIXED。声明剩余例固定03-12…04-01，实际7日峰52kg、15日峰60kg，不计算 SEASON_TOTAL_WAPE。

| Origin / 目标 | 基线累计kg | 候选累计kg | 实际累计kg |
|---|---:|---:|---:|
| 03-10 / H7 | 20 | 55 | 61 |
| 03-10 / H15 | 72 | 63 | 69 |
| 03-11 / H7 | 26 | 47 | 52 |
| 03-11 / H15 | 72 | 55 | 60 |

两个 H7 共同窗口的实际量分母113kg。DAILY_WAPE 分子为基线109、候选11；累计量WAPE分子为基线67、候选11；累计MAE为33.5、5.5kg/window。两个 H15 的相应分母129kg，每日分子191/11，累计分子15/11。不能混报两种 WAPE。

误差抵消专例：03-10 H7 前两日为+10、−10kg，单窗口累计绝对误差0，逐日绝对误差和20kg、DAILY_MAE=20/7。保留下一 origin 后，该 origin 少了+10日，仅剩−10，两个窗口累计 MAE=5kg，DAILY_MAE=30/14；没有为展示抵消而删除另一个 origin。

COMMON_COHORT_FAILURES 例给 H7/H15 各3个候选，候选模型缺第二基地预测，各指标保留N=3、共同2、失败1，覆盖2/3，INCONCLUSIVE。22类执行结果含短窗口、非法日期/数量、零值、晚到、不同口径、不同成员、标签冲突、改善/退化等，见 `executed-scenarios.json`，不能将其中“被拒绝”误报为评分通过。

## 运行方法

从仓库根目录，使用项目 Python3.12 环境，以下目录均须不存在：

```sh
python -m backend.tests.agronomic_history.v0_21_evaluation_fixture --output /tmp/SYNTHETIC-v021-s3-input
python -m backend.research.v021_evaluation_readiness register --s1 /tmp/SYNTHETIC-v021-s3-input/s1.json --s2 /tmp/SYNTHETIC-v021-s3-input/s2.json --protocol /tmp/SYNTHETIC-v021-s3-input/protocol.json --output /tmp/SYNTHETIC-v021-s3-registration
python -m backend.research.v021_evaluation_readiness seal --registration /tmp/SYNTHETIC-v021-s3-registration/registration.json --predictions /tmp/SYNTHETIC-v021-s3-input/predictions.json --output /tmp/SYNTHETIC-v021-s3-prediction
python -m backend.research.v021_evaluation_readiness score --seal /tmp/SYNTHETIC-v021-s3-prediction/prediction-seal.json --labels /tmp/SYNTHETIC-v021-s3-input/labels.json --as-of 2025-04-04T08:00:00+08:00 --output /tmp/SYNTHETIC-v021-s3-score
python -m backend.tests.agronomic_history.v0_21_evaluation_fixture --suite --output /tmp/SYNTHETIC-v021-s3-scenarios
```

输出为 registration、prediction-seal、evaluation JSON，以及逐日误差CSV和各阶段运行manifest。重复独立进程的业务结果及Hash一致，执行时间留在独立manifest。本版不开发S4综合HTML报告、数据库、Dashboard、MCP或审批平台。

## 授权与未完成边界

本次聊天 Owner 授予S3实现、合成测试、Commit/Push和独立Draft PR；新授权记录见 `../evidence/v0.21-s3-evaluation-readiness-r1.json`。S0中的旧授权快照不改写。本记录不是签名、真实数据授权或后续阶段许可。

`STRICT_PIT_VALIDATED=false`、`REAL_DATA_READ=false`、`MODEL_TRAINING=false`、`PRODUCTION_FORECAST_CHANGE=false`、`S4_IMPLEMENTED=false`。代码、合成验证、独立评审、Owner合并许可及合并后main CI是不同状态。本交付不Ready、不Merge、不Tag/Release/Deploy，S4仍需另行授权。

本地验证：S3专项59项全部通过，相关回归总449项全部通过、无跳过；全仓Ruff与格式检查通过，Mypy检查604个源码文件通过。最终HEAD的GitHub CI结果在PR交付回执单独记录，不能用这些本地结果替代。
