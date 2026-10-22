# V0.19 S3 可执行合成历史回放引擎 R1

TASK_ID=V0_19_S3_END_TO_END_RETROSPECTIVE_ENGINE_R1

本次在原 Draft PR #748 内交付实际计算，不以协议文档代替执行。
`FULL_SYNTHETIC_END_TO_END=PASS` 是合成程序及数值测试的结果，
不是正式 C0、真实预测执行、真实评分或 S3 正式完成。

## 直接运行

在仓库根目录、已安装项目依赖的 Python 3.12 环境执行。输出目录必须不存在；
程序新建目录为 0700、文件为 0600，不覆盖旧运行。

```sh
python -m backend.research.v019_retrospective_engine demo --output /tmp/SYNTHETIC-engine-demo-new

# A、B 也可分别在独立进程执行。B 必须收到完整、可复算的 A seal。
python -m backend.research.v019_retrospective_engine stage-a --output /tmp/SYNTHETIC-engine-a-new
python -m backend.research.v019_retrospective_engine stage-b \
  --seal /tmp/SYNTHETIC-engine-a-new/phase-a.json --output /tmp/SYNTHETIC-engine-b-new
```

支持 `--fixture DEFAULT|CLEAN|ZERO_ACTUAL|MISSING_LABEL|INVALID_LABEL|INVALID_PROFILE`。
这些均为内置、明确标识的 SYNTHETIC 场景；没有真实输入路径、标签路径、
Owner 批准布尔值或真实执行开关。外部 seal 只能是闭合合成登记的精确产物，
不是可注入任意真实数据的反序列化接口。

## 实际流水线与产物

| 阶段 | 计算与验证 | 输出 |
| --- | --- | --- |
| C0 候选 | 固定合成成员、Base/面积、日期、来源身份、输入可用性、方法与代码 Hash；此时不计算预测、不打开标签 | `c0-candidates.json` |
| 合成准入 | 独立 C0 permit 必须匹配候选 Hash；重建全部成员，不允许截掉失败样本 | `synthetic-c0-admission.json` |
| A | 独立 A permit；现有 Operational Peak 纯计算函数生成完整基线，唯一 S2 算法转换同一 support，然后裁剪 H7/H15；失败原样保留 | `phase-a.json` |
| 封存 | 输入、成员、算法、源代码、完整曲线、窗口预测、计算时钟、失败均进入规范化 Hash | A payload/seal Hash |
| B | 独立 B permit；先重建并核对完整 A，再打开独立合成标签模块，校验标签身份；按共同可计算集合评分 | `report.json` |
| 展示 | 只格式化 B 已算出的数值，不在页面重算业务量 | `report.md`、`report.html` |
| 运行清单 | 各文件 SHA256、实际进程完成 UTC 时间、真实执行=false | `manifest.json` |

算法及算术复用：

- 基线复用 `backend/app/forecast_quality/operational_peak.py` 的冻结 profile 加载和日量计算；
  正向测试与既有正式 `forecast_operational_peak` 输出逐日相等。
- 候选复用 `v019_daily_curve.generate_candidate`，不新增第二候选，不重新训练或调参。
- 数值误差、峰值、分数、日历检查及诊断复用 `v019_synthetic_validation` 的既有算术。
- 独立 B 只增加合成 retrospective 的时间准入与聚合编排。原严格签发门禁及
  原 `evaluate_synthetic` 不变；测试证明它仍拒绝本次晚计算样本。
- 十指标及诊断与另一组**测试专用、虚构的合法早签发正向对照**逐项相等；
  该测试不改变实际回放样本的时钟、不将它们重新命名为早签发。

## 实际运行的完整样例

提交的 [样例 Manifest](examples/retrospective-engine-r1/manifest.json) 对应本次真实程序运行；
完整 [C0](examples/retrospective-engine-r1/c0-candidates.json)、
[A seal](examples/retrospective-engine-r1/phase-a.json)、
[JSON](examples/retrospective-engine-r1/report.json)、
[Markdown](examples/retrospective-engine-r1/report.md)、
[HTML](examples/retrospective-engine-r1/report.html) 可独立核对。

这些是公开提交的虚构输入，不是私有 reference-B、Registry、SOURCE_002 或真实采收。
四个 SYNTHETIC Base 的面积为 10、20、5、10 亩；
虚构完整 support=2000-07-01—2000-07-21，三个七日分箱日均量为 1、3、0.5 kg/亩。
同一 Base 仅计算一次完整曲线，窗口不重归一化。

登记 20 个样本：每 Base 两个 origin×H7/H15，加一个隔离的完整虚构日历算术对照。
DEFAULT 中 D 的缺失输入在 C0 预先登记，5 项生成失败全部保留；其余 15 对预测完成。
H7、H15 各 8 项：每日数量共同集合各 6 项，覆盖率 0.75；全零实际量的 C
不能产生虚假的峰日期命中，峰日期共同集合各 4 项。不是删掉 C 或 D 后声称全覆盖。

### 输入到逐日预测、峰值

以 A（10 亩）、origin=2000-07-03 的 H15 为例：

| 日期 | 基线 kg | 候选 kg | 合成标签 kg |
| --- | --- | --- | --- |
| 2000-07-04 | 10.000000 | 8.032787 | 8 |
| 2000-07-05 | 10.000000 | 10.327869 | 11 |
| 2000-07-06 | 10.000000 | 12.622951 | 13 |
| 2000-07-07 | 10.000000 | 14.918032 | 14 |
| 2000-07-08 | 30.000000 | 26.250000 | 20 |
| 2000-07-09 | 30.000000 | 29.750000 | 25 |
| 2000-07-10 | 30.000000 | 33.250000 | 30 |
| 2000-07-11 | 30.000000 | 36.750000 | 35 |
| 2000-07-12 | 30.000000 | 32.375000 | 40 |
| 2000-07-13 | 30.000000 | 28.000000 | 35 |
| 2000-07-14 | 30.000000 | 23.625000 | 25 |
| 2000-07-15 | 5.000000 | 9.746835 | 7 |
| 2000-07-16 | 5.000000 | 7.531645 | 6 |
| 2000-07-17 | 5.000000 | 5.316456 | 5 |
| 2000-07-18 | 5.000000 | 3.101266 | 4 |

基线单日峰=07-08、30 kg；候选=07-11、36.75 kg；合成实际=07-12、40 kg。
该样本峰日期绝对误差 4→1 天，峰数量误差 10→3.25 kg。
三条曲线的 rolling-7 最大累计均为 210 kg，起点均为 07-08、终点 07-14。
并列峰按既有最早日期规则，不由报告器另选峰。

### 十指标输出

以下 H15 汇总小数仅为便于阅读的截断；JSON 保存 Decimal 原值、分子、分母、
共同成员 Hash、覆盖和每个不可计算原因。WAPE 为比值而非百分数。

| 指标 | 基线 | 候选 | 可计算样本 |
| --- | --- | --- | --- |
| SEASON_TOTAL_WAPE | NOT_COMPUTABLE | NOT_COMPUTABLE | 0/8，H15 不是完整产季 |
| DAILY_WAPE | 368.5/1587 = 0.232199… | 530.437322/1587 = 0.334239… | 6/8 |
| DAILY_MAE | 368.5/90 = 4.094444… kg | 530.437322/90 = 5.893748… kg | 6/8 |
| SINGLE_DAY_PEAK_DATE_MAE | 8/4 = 2 天 | 8/4 = 2 天 | 4/8 |
| SINGLE_DAY_PEAK_QUANTITY_MAE | 50/6 = 8.333333… kg | 70.25/6 = 11.708333… kg | 6/8 |
| ROLLING_7DAY_PEAK_START_MAE | 0/4 = 0 天 | 0/4 = 0 天 | 4/8 |
| ROLLING_7DAY_PEAK_QUANTITY_MAE | 210/6 = 35 kg | 210/6 = 35 kg | 6/8 |
| BASE_BREADTH | 3 个共同 Base | 1 改善、2 退化 | D 仍在失败清单 |
| SAMPLE_COVERAGE | 每日数量 0.75；峰日期 0.5 | 相同共同集合 | 逐指标报告 |
| NOT_COMPUTABLE_COUNT | 每日数量 2；峰日期 4；产季 8 | 相同共同集合 | 原因与成员保留 |

A 的 H15 两个 origin 合计绝对日误差降低 24.195895 kg；B 增加 177.875282 kg；
C 增加 8.257935 kg。单个 A 样本的改善不能代表总体胜出；本例 H15 总体每日误差退化。
独立虚构 21 日完整日历对照的 SEASON_TOTAL_WAPE 实算为两者均 157.5/945=1/6，
只证明该指标可执行，**不增加任何真实完整产季准入**。

## 确定性、隔离和负向证据

本次 demo 与独立 A→B 三个进程的六份计算产物逐字节相等。
进程完成时间只记录于运行 Manifest，不混入计算结果 Hash。
模拟计算时钟为 2002-01-01 UTC，评分时钟 2003-01-01 UTC；
`historical_issued_at=null`。真实运行时间另存，不回填为 2000 年的历史签发时间。

负向测试覆盖：独立阶段 permit 缺失/错误、C0 截断、seal/代码/标签漂移、
真实类别注入、非法外部 fixture、无标签阶段 A、缺失及重复标签、零分母、
全零标签、非法 profile、低环境 Decimal 精度、跨进程交接及 HTML 转义。
初次 CLI 阶段 B 暴露的模块身份不一致失败已保留于本地
`/tmp/SYNTHETIC-v019-engine-red-xXgbwp/`；修复未放宽 permit 类型检查。

样例是本次交付的历史运行快照。测试验证其内部 seal 和 Manifest，不用未来工作树
重写样例来源 Hash；当前源码由独立运行测试验证。代码来源 Hash 与最终 PR HEAD 的
CI 共同建立本次可追溯性，不能将未来合法修改误当作历史证据被篡改。

## 不变的真实执行边界与来源纠正

真实正式 C0=0；真实 A/B 未批准；真实路径继续无条件拒绝；不读取私有数据、
不训练、不调参、不改生产服务、原严格 PIT 评分器、既有算法或冻结历史证据。
闭合合成 permit 是测试接口，不是 Owner 签名、真实批准或对新研究资料的信任凭据。
模拟实验可计算不使原受限协议运行生效，也不意味着 S3 正式完成。

原 Owner 决定登记已纠正：直接回复是“可以”；协议范围为助手对前文请求的结构化
解释，不是 Owner 原文。原批准时间、消息 ID、签名和 GitHub 来源仍未知，未伪造。
旧错误提交及错误节选 Hash 保留追溯；#747 历史审批包不变。

`RETROSPECTIVE_PROTOCOL_EFFECTIVE=false`，`FORMALLY_ADMITTED_C0_COUNT=0`，
`REAL_PREDICTION_GENERATED=false`，`REAL_SCORING_PERFORMED=false`，
`S3_FORMAL_COMPLETE=false`；保持 Draft，不 Ready、不 Merge、不 Deploy。
