# V0.19 S3 独立历史回放研究入口 R1

TASK_ID=V0_19_S3_RETROSPECTIVE_RESEARCH_ENTRY_R1

## 交付性质

这是可运行的 **SYNTHETIC_ONLY** 研究入口，不是获准的真实回放或真实评分。
基线固定 `AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`，唯一候选固定
`BIN_CENTER_LINEAR_PER_BIN_MASS_V1`，拟用真实 profile 为 Fold B。
`PROTOCOL_STATUS=PROPOSED_NOT_EFFECTIVE`、`STRICT_PIT=false`、
`PRODUCTION_ELIGIBLE=false`、`S3_FORMAL_COMPLETE=false`。

入口为 `backend/research/v019_retrospective_entry.py`；不修改已有三个研究模块、
Operational Peak 生产服务、S1 十指标、严格 PIT 评分器或冻结历史材料。
本轮无私有文件读取、实际预测生成、实际评分、训练、调参或模型晋级。

## 两种身份，不改评分门禁

- `RETROSPECTIVE_REPLAY`：事后重算，真实执行时须保留真实 computed_at/issued_at。
  本入口仅使用明确标记的模拟时钟；晚签发保持晚签发，经原 S3 评分器得到
  `NOT_COMPUTABLE / UNVERIFIED_AUTHORITY`，不回填历史时间。
- `AS_ISSUED_FORECAST`：本入口仅作为单独的 **虚构正向对照**，用于验证十指标与
  改善/退化报告；不是已证明的真实历史签发。不得与回放合并计算或把其成绩转贴给回放。

两种身份分别注册 C0、封存、评分及报告。模拟时钟是 `EXPLICIT_SIMULATED_CLOCK`。
2025–2026 真实样本仍为 `EXPOSED_HISTORICAL_BENCHMARK`；封存不能恢复盲测。
当前入口没有修改时间门禁的开关，也没有“批准真实数据”的布尔开关。

## 真实来源候选登记，不等于正式 C0

`CandidateScope` 保存 Owner 提供的有限非敏感事实，并对每个字段、类型和结构上限
进行验证。它不加载任何实际重量、私有面积值或农场名称：

| 项目 | 冻结的待核验事实 |
|---|---|
| SOURCE_002 | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| 目标日期 | 2025-08-05—2026-04-15；不纳入 04-16 |
| 候选 Base | 39，不自动成为正式样本 |
| 已匹配农场 | 75 |
| 未解决农场 | 9；BLOCKED_NOT_MAPPED_NOT_EXCLUDED，不分摊、不补零、不丢弃 |
| 历史面积 | 39 Base 有历史权威；历史 known_at 尚未证明 |
| 物理口径 | 旧训练来源与 SOURCE_002 等价尚未证明 |
| H7 结构上限 | 39×248=9,672，origin 日期 2025-08-04—2026-04-08 |
| H15 结构上限 | 39×240=9,360，origin 日期 2025-08-04—2026-03-31 |
| 完整产季准入 | 0；不能用局部窗口补出整季 |

其状态始终为 `BLOCKED_NOT_FORMAL_C0`。结构上限、来源 Hash 或阶段 A 开发授权
都不授予真实数据、真实预测生成或评分权限。修改事实不会自动产生新权威。

## 可执行接口与隔离

1. `register_synthetic(Registration(...))`：只接收实验标识、身份和内置夹具选择。
   冻结四个 H7/H15 合成成员、成员身份 Hash、完整输入 Hash、源码及配置 Hash、
   缺输入原因和真实来源阻断清单。没有外部成员、路径或原始曲线参数。
2. `generate_synthetic(c0, permit=SyntheticPermit("A"))`：先重建核验 C0，再复用
   `prepare_predictions`。既有基线日值直接传递，唯一候选调用原 S2 方法。
   同一完整 support 先生成再切 H7/H15，不重新归一化，无标签输入。
3. `score_synthetic(seal, permit=SyntheticPermit("B"))`：独立阶段许可、C0 和预测
   seal 全部核验后才创建内置字面合成标签，委托既有 `evaluate_preparation`。
   许可缺失、阶段错误、seal/输入/源码漂移均在标签打开前拒绝。

`SyntheticPermit` 仅为演练的阶段隔离参数，不是可信签名或 Owner 授权凭证。
即使调用方伪造 permit，入口也没有真实执行路径。修改类别、名称、时间、曲线或
profile 不能把外部数据塞进内置 C0；不存在 `--input`、文件发现或真实 artifact 加载。
这证明封闭演练边界，不声称软件能从任意数值判断其真实来源。

CLI：

```sh
python -m backend.research.v019_retrospective_entry --demo
```

输出 canonical JSON 到 stdout；不写业务文件。输出包括封存摘要、时钟、完整原评价
报告及独立不可计算/覆盖统计。`PAIR` 提供改善与退化的合成对照；`MISSING_INPUT`
保留失败成员；`UNVERIFIED_PHYSICAL_BASIS` 验证物理口径拒绝。
完整产季未登记，因此 SEASON_TOTAL_WAPE 不可计算。H7 只有一个 rolling7 窗口，
不夸大其峰起点区分力。公式、Decimal 精度、并列和零量语义完全来自原评价器。

## 验证与证据身份

测试先运行 RED（新模块尚不存在的 ImportError），随后实施并验证：
确定性、阶段 A 零标签访问、先 seal 后标签、独立许可、真实类别/伪造许可拒绝、
成员/曲线/profile/源码漂移、回填时间拒绝、两种身份隔离、H7/H15、缺输入及物理
口径负向、原十指标和 CLI。没有 skip/xfail/retry。

机器证据为 `../evidence/v0.19-s3-retrospective-research-entry-r1.json`。
已有历史来源固定到 main `f501dc32f803df9ce9a109504a1c3cc47700c7a7` 的 Git blob；
新入口运行时将当前四个执行模块的 SHA256 封入 C0，改变源码会使旧 seal 失效。
这不是要求未来工作树永远等于旧交付；新交付证据不添加此类跨版本断言。
代码摘要不是签名、可信时间证明或数据许可。最终 HEAD/CI 以 PR 的实际结果为准。

本地专项 32 passed（重复执行）；S0/S1/S2/S3 与 V0.18 相关合同合计 511 passed。
全仓 Ruff、1510 文件格式检查及四个研究模块 Mypy 通过。完整 PostgreSQL、浏览器及
Canary 验收交由最终 exact-head CI；不把这些本地合同测试称为真实数据评分。

## 后续仍需独立批准

真实物理口径及成员范围、输入可知时间、正式 C0、独立 retrospective 协议、
真实读取/预测生成/评分以及真实研究适配器实施与验收，均未由本轮授权。
若拟议跨来源研究获准，必须独立 family 和报告，不能改变现行严格 PIT 门禁。
本交付不认定 S3 正式完成，不执行 Ready、Merge、Release 或 Deploy。
