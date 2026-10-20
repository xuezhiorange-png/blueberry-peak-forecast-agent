# V0.19 S3：历史回放合成准备 R1

TASK_ID=V0_19_S3_RETROSPECTIVE_REPLAY_PREPARATION_R1

## 结论与边界

本交付为可运行的 SYNTHETIC 演练，不是实际历史回放、数据准入或正式 S3 完成。
起点 `32602ac7f111a6ad49fd40467d012cc56acf106e`；对应 main push CI
[39433791985](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/39433791985)
已实时核验 completed/success、head 一致后才提交。最终 PR exact-head CI 单独验收。
真实读取、真实评分、真实回放、训练、调参、晋级及生产部署均未授权且未执行。

## 两种预测身份与不生效的协议提案

| 身份 | 含义 | 本演练与现行合同的处理 |
|---|---|---|
| AS_ISSUED_FORECAST | 有证据证明目标开始前真实签发的原预测 | 这里只提供虚构时钟、虚构权威和字面合成曲线的正向对照，绝不证明真实历史签发 |
| RETROSPECTIVE_REPLAY | 后来使用历史输入重新计算的研究预测 | 保留原 origin/cutoff 和后来 computed_at；issued_at 等于 computed_at，不回填为 origin；现有 S3 时间门禁继续排除晚签发样本 |

两类必须分别封存、分别报告，禁止合并指标。所有 demo 时钟均为虚构实验时钟，
不是本机真实执行时间或历史签发凭证；Hash 也不等于签名、可信时间或读取许可。

**关键限制**：当前 S3 要求签发及输入截止时间早于目标开始，本交付不更改该规则。
因此“晚生成的回放”虽可生成及封存合成曲线，其误差在现行评分器中必须为
NOT_COMPUTABLE / UNVERIFIED_AUTHORITY，不能靠改名 AS_ISSUED 或回填时间转为可计算。
可计算的十指标来自单独的、合法虚拟时间正向对照，不冒充回放精度结果。

未来真实 retrospective replay 若要在明确的研究边界下评分，需要 Owner 单独审查：
适用来源/季节/实体/字段、当时输入可知证据、训练污染与 exposed 状态、回放实际时间、
标签隔离、允许的指标和共同样本，以及与当前目标前签发约束不同之处。
状态为 PROPOSED_NOT_EFFECTIVE；该提案不修改 S1/S3，批准数据读取也不自动批准评分，
更不自动豁免 PIT。未获得正式协议授权不得启用真实回放路径；本程序没有该路径。
2025–2026 即使未来获准仍是 EXPOSED_HISTORICAL_BENCHMARK，不是 blind OOT。

## 可运行流程与复用

入口：`python -m backend.research.v019_replay_preparation --demo`，输出 canonical JSON
到 stdout。没有文件、数据库、网络、artifact 加载参数，也不写业务或研究资产。
输出重定向如有需要仅限操作者指定的 SYNTHETIC 隔离目录；不提交秘密或私有数据。

1. 注册独立 C0：固定 sample、base/plot/variety、season、面积、origin/cutoff、来源、
   物理口径、训练/评价范围、comparison_family、H7/H15/FULL_SEASON 日历。
2. Phase A `prepare_predictions` 不能接收标签；冻结原曲线及输入身份，直接复用
   `v019_synthetic_validation.generate_synthetic_predictions`。原算法是该路径保留的
   Operational Peak 冻结日值输入；唯一候选调用 `v019_daily_curve.generate_candidate`。
   不另写基线生成器、不重训 Operational Peak、不更改任何算法参数。
3. 先封存 C0、输入、两组预测及 preparation seal；保留缺输入和生成失败 origin。
4. Phase B `evaluate_preparation` 在触碰标签 iterable 之前重建并核验双层 seal、
   输入与计算时钟；随后才接受字面合成标签，并委托原 `evaluate_synthetic` 评分。
5. 原评价器的十指标、分子分母、每项 Cm、覆盖/不可计算原因、基地改善/持平/退化
   全部原样保留；H7、H15、FULL_SEASON 按原分组分开。额外只展示 candidate−baseline
   误差差值，不新增 winner/支持阈值，不把局部改善包装为总体胜出。
6. 输出封存日曲线、单日峰、rolling-7 峰及现有评价结果；峰的展示复用原评价器
   `_peak`，不重写业务计算。零实际峰日期为 null；无完整日历不输出伪造标签峰。

合成输入使用 2000 年虚构日期、两座 SYNTHETIC 基地、21 日 support、原七日平坦分箱。
H7/H15 只取既有 support，不重新归一化。字面合成标签在 Phase A 后才建立：A 基地
展示改善、B 展示退化；只是管道测试，不是未来真实数据分布或算法优越性证据。
所有 AVAILABLE 权威均为合成夹具；真实十二项权威继续 NOT_VERIFIED。

## 验证及来源策略

新增测试覆盖：十指标逐字段等同原评价器、两身份隔离与晚签发拒绝、回填时间拒绝、
标签打开前拒绝四类 seal 损坏、缺输入/标签保留、零量、错误/不成熟/迟到标签、
重复 C0、不兼容总体、时区、空窗口、Decimal 上下文、顺序与重复 Hash、可运行 CLI。
测试没有 skip/xfail/retry，无实际数据读取。S0/S1/S2/S3 与 V0.18 历史合同另行回归。

机器记录：`../evidence/v0.19-s3-replay-preparation-r1.json`。
历史源码和既有合同绑定本任务固定 base commit，使用原 Git blob 验证。
本次新增源码 Hash 是当前交付接收凭证，不新增“未来工作树必须永远不变”的历史断言；
未来若审计本次源码，必须绑定本 PR 实际固定提交，而非动态 HEAD 或重算旧预期值。
新合成实验的预期输出 Hash 与方法/夹具身份单独记录，不冒充历史来源证明。

## 尚未授权

REAL_DATA_ACCESS_AUTHORIZED=false；REAL_SCORING_AUTHORIZED=false；
RETROSPECTIVE_REAL_REPLAY_AUTHORIZED=false；MODEL_TRAINING_AUTHORIZED=false；
MODEL_PROMOTION_AUTHORIZED=false；S3_FORMAL_COMPLETE=false。
READY_AUTHORIZED=false；MERGE_AUTHORIZED=false；RELEASE_AUTHORIZED=false；
DEPLOY_AUTHORIZED=false。Draft CI 通过也不改变这些状态。
