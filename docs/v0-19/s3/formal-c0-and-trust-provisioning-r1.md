# 正式 C0 与受控信任根 R1

任务：`V0_19_S3_FORMAL_C0_AND_TRUST_PROVISIONING_R1`。
基线：`2e7797554eb771360ad64f3114f08fa70d7034cd`，main CI `39762704032` 成功。

## 本轮 Owner 决定及实现

本轮直接聊天任务批准全部 19,032 个候选正式准入、真实 Owner/Reviewer 信任根配置、
Asia/Shanghai D0 日末 cutoff、D1 起预测、2025-07-01 至 2026-04-15 完整 support。
不再次申请这些决定，不修改此前候选文件或历史审批快照。

实际登记时间使用运行机器 UTC；没有伪造历史批准时间、GitHub 来源或 Owner 手写签名。
签名表示依本轮明确授权生成的任务委托操作记录，不是 Owner 本人的密码学签名。

研究授权模块新增显式 `Context.real_trust_config`，CLI 对应 `--real-trust-config`。
配置必须为固定 SHA256 的确切 enrollment 字节，绝对路径、无符号链接、有限大小。
配置校验角色、独立公钥、研究范围及有效期。默认 REAL 上下文仍无信任根；
不能由环境变量、合成根、批准布尔值或任意公钥文件启用。

Owner 根本轮仅允许 PROTOCOL、FORMAL_C0、A_INPUT_READ。
Reviewer 根仅允许 IMPLEMENTATION_REVIEW、A_SEAL_REVIEW。
所有决定仍须 Ed25519 签名，并绑定对象、当前代码、角色、限制和有效期。
即使使用本轮 Owner 私钥签署 A_EXECUTION、B_LABEL_READ 或 B_SCORING，也会被拒绝。
未来执行权限需要另行授权及受控更新 enrollment，不能只增加批准字段。

公钥 enrollment 和可复核 Hash 见本轮新增机器证据；不包含任何私钥。
配置有效期至 2026-11-21T11:40:22.466528+00:00，任务决定有效期更短。
信任配置过期后拒绝执行；更新不得覆盖旧 enrollment 和证据。

## 私有 C0 实测

在原受控根目录新建独立目录，所有数据输出以 exclusive-create 写入，目录 0700、文件 0600。
五份固定输入经正式 Owner Scope 适配器重新验证，来源及 Hash 不变。
只读读取 Profile、Registry、范围 sidecar 和两份候选 CSV，没有打开实际评分标签。
本轮不重新读取面积原表，面积关联依赖固定 sidecar 既有权威连接。

新建 input Manifest，精确列出五份输入路径及 Hash。为该 Manifest 签发限定读取决定，
为完整成员决定签发 FORMAL_C0；没有 A 执行或 B 标签/评分许可。
依现有 candidates → review_candidates → formalize 路径生成 C0，未重写算法或评分器。

| 项目 | 实测 |
|---|---:|
| 正式 C0 | 19,032 |
| H7_PREFIX | 9,672 |
| H15_LOCAL | 9,360 |
| Base | 39 |
| 拒绝成员 | 0 |
| 无效成员 | 0 |
| 预测或评分函数调用 | 0 |

每一候选均有显式 ADMIT；没有排除、补造或替换。原四个研究排除农场继续在 Owner Scope 中保留，
不属于待准入候选，不能将其混入“拒绝成员为 0”的统计。
全部成员的 origin/cutoff 为 `23:59:59+08:00`，target_start 是 D1。
无历史签发证据，真实创建时间记录在 receipt 中，不回填到历史 origin。

第二个独立进程重新打开五份输入、重建完整候选和成员决定、验证签名、重新计算正式 seal，
与已保存文件逐项相同。该过程是独立进程技术复算，不是独立人工审核。

- C0 payload SHA256：`d5dc13b119357934ddcbcf3abd5fbef413ffbfecc87035734ba4f2fcf93d4b2a`
- 分窗口准入成员 SHA256：`50a2dd0ae913920fb32515c5a1fb41c0c62cc90217bd66bd5a9686c912a9df13`
- 绑定代码身份：`2d0a15be82064c8f8a7e9ba270ff39cb80f4ae7d727c3c720aaae70097490b8c`

私有目录内保留 input-manifest、candidates、owner-c0-dispositions、c0-grants、formal-c0、
creation-receipt、independent-process-verification。不得提交这些成员清单、私钥或未来标签到 Git。
机器证据保留核验报告 Hash，最终提交 SHA 与 CI 以 PR 对应实际记录为准。

## 独立性及剩余边界

两把密钥由操作系统安全随机源新建，不使用测试密钥，不覆盖既有密钥；权限和公钥不同。
但当前由同一 macOS 用户保管，不能声称独立保管人或独立人工接受已完成。
未签署任何 Reviewer 决定，后续 Reviewer 决策前仍须完成独立保管安排及真实独立复审。
Owner 和 Reviewer 私钥不写入日志、聊天或 Git。

本轮 C0 绑定本 PR 的研究授权代码，不将 main 旧代码或本地 PASS 伪称为已合并验收。
后续代码身份改变须显式重审/重新封存，禁止绕过 code_sha256 校验。
不修改原严格 PIT 门禁，物理口径等价及历史面积 known_at 仍 NOT_PROVEN。

**阶段 A 未获执行许可，阶段 B 未获标签读取及评分许可。没有真实预测、真实评分、训练或部署。**
只交付同一个 Draft PR，等待独立复审，不 Ready、不 Merge。

## 本地验收

- S0/S1/S2、S3 合成评价、历史回放准备、Owner Scope、审批包、现有端到端引擎及
  信任配置相关回归：513 passed，250.11 秒。该次收集包含当时的 20 项配置测试。
- 补充公开 enrollment 字节一致性断言后的信任配置专项：21 passed，0.27 秒。
  两组结果有重叠，不相加宣称独立用例总数。
- Ruff、Format、Mypy：本轮三个 Python 文件均通过。
- 正式 C0 私有真实文件正向检查及独立进程重建：通过，未执行 A/B。
- 最终 exact-head CI 另见本 PR Actions，不能以本地结果代替。
