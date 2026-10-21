# V0.19 S3 Owner 受限协议决定登记 R1

TASK_ID=V0_19_S3_OWNER_PROTOCOL_APPROVAL_AND_C0_PREFLIGHT_R1

版本：`V0_19_S3_OWNER_PROTOCOL_DECISION_R1`。本记录新增在 main
`9e84439da7ee27b08448804d87413d9a9af24b41` 之后；main push CI
[39619137769](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/39619137769)
已完成 success。该 CI 不是本次 Draft PR 的验收结果。

## 决定及来源

Owner 在本次任务聊天中明确批准协议，登记为：
`PROTOCOL=OWNER_APPROVED_LIMITED`；对外摘要为 `PROTOCOL_OWNER_DECISION=APPROVED_LIMITED`。
这是已收到的受限决定，不再将本项描述为“等待 Owner 批准”；但决定登记尚待审核，
不等于协议运行生效。原 #747 八项均未批准的快照保持其原时点含义，不回写历史。

本次 Owner 原文节选（仅保存节选，不声称是完整消息或数字签名）：

> 本次唯一已批准决定：
> PROTOCOL=OWNER_APPROVED_LIMITED
> 其余七项独立决定仍为 NOT_APPROVED。

授权来源是当前聊天的本任务，不是 GitHub 评论。没有可验证的原始批准时间、
消息 ID、外部签名或 GitHub 授权链接，因此对应字段均为 null。机器证据的
`recorded_at` 来自实际 UTC 时钟，表示 Codex 建立本记录的时间，**不是 Owner 原批准时间**。
节选 SHA256 只证明所登记节选字节的身份，不能证明签名或补造历史批准来源。
提交/PR/CI 时间同样不得替代原批准时间。

## 唯一获准的研究范围

- 范围版本 `V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1`，39 Base、80 纳入农场、
  4 个仅研究排除、研究范围内未解决=0；不改全局身份权威。
- 2025–2026；目标窗口 2025-08-05—2026-04-15；完整 support 提议为
  2025-07-01—2026-04-15，仍须在正式 C0/执行审核中固定。
- Fold B；固定基线 `AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`；唯一候选
  `BIN_CENTER_LINEAR_PER_BIN_MASS_V1`。先生成同一完整 support，再切 H7/H15，
  不对窗口重归一化、不训练、不调参、不重新选择模型或晋级。
- 仅 `RETROSPECTIVE_REPLAY` / `EXPOSED_HISTORICAL_BENCHMARK` 条件性方法比较。
  Owner 接受 `STRICT_PIT=false`、物理口径等价/历史面积 known_at/历史真实签发证据
  均为 `NOT_PROVEN`。接受研究限制不是证明它们已满足，更不是生产准确率验收。

## 与 #747 的精确关联

原 PR [#747](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/747)：
HEAD `8f80659f7775f7f0c98552da58d156e6584e800c`；合并 SHA 为本次 main 基线。

| 原始对象 | SHA256 | Git Blob |
| --- | --- | --- |
| `retrospective-protocol-and-c0-approval-r1.md` | `918624c6f443404a96b96c7eeaf17515e29b7f5d9a7538c3fc4a0cbf8a3c0158` | `486d46841930a38ab0873e79e6791f206c07e510` |
| `v0.19-s3-retrospective-approval-package-r1.json` | `7d65a7d6787a67c9583fb8c383e996acb47bb289737ae0423a25d7a252027ece` | `bbe51f8f89fa526b0f7448759f123a0dea08a597` |

新机器证据逐项关联原范围、算法、输入身份、H7/H15 以及已封存 Owner 映射决定
`7d15f85752bc57e3facc4d912aa1d89e3c1ce7e61ee85c52b432cfc8af952bf2`。
只新增 PROTOCOL 的决定层，不替换已封存输入，也不修改旧 JSON 中的 NOT_APPROVED。

## 其余七项与生效条件

`FORMAL_C0`、`A_INPUT_READ`、`A_EXECUTION`、`A_SEAL_REVIEW`、`B_LABEL_READ`、
`B_SCORING`、`INDEPENDENT_REVIEWED_RESEARCH_IMPLEMENTATION` 全部 `NOT_APPROVED`。
本次整理既有证据不构成新的输入访问许可；先前限定读取授权也不扩大为执行授权。

本记录及生效条件须独立审核；origin/cutoff 建议、精确成员 seal 和执行代码仍需各自
批准。当前 `RETROSPECTIVE_PROTOCOL_EFFECTIVE=false`；阶段 A 真实入口继续无条件拒绝，
阶段 B 不获授权。不能通过修改机器 JSON 的批准布尔值开启预测或评分。

参见 [C0 审核准备包](owner-c0-admission-preflight-r1.md) 和
[机器决定证据](../evidence/v0.19-s3-owner-protocol-decision-c0-preflight-r1.json)。

`FORMALLY_ADMITTED_C0_COUNT=0`；`REAL_PREDICTION_AUTHORIZED=false`；
`REAL_SCORING_AUTHORIZED=false`；`REAL_PREDICTION_GENERATED=false`；
`REAL_SCORING_PERFORMED=false`；`S3_FORMAL_COMPLETE=false`。
本交付不 Ready、不 Merge、不 Deploy，不启动真实预测、评分或训练。
