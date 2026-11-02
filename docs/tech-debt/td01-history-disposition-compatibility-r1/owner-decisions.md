# TD-01 历史处置 Owner 原则决定 R1

任务：`TD01_HISTORY_DISPOSITION_DECISIONS_AND_COMPATIBILITY_R1`。
依据本次明确 Owner 指令，自 2026-11-02（Asia/Shanghai，日精度）起生效；不回写旧审核记录。
基线 main：`0118d82c8a0aa14f17fb37f56faeb6ed134698cf`。

| 决定 | 正式 Owner 原则 | 状态 |
| --- | --- | --- |
| D01 | 两份历史 XLS 按真实业务数据管理，不授予公开发布许可。 | OWNER_POLICY_APPROVED |
| D07 | 五份未确认来源的压缩资产继续排除在公开交付范围之外，等待独立来源核实。 | OWNER_POLICY_APPROVED |
| D08 | 先验证历史代码身份兼容性，再开展隔离预演。真实 Git 历史调整、Tag/Release 处理必须分别获得后续授权。 | OWNER_POLICY_APPROVED |
| D09 | 建立真实数据独立保管、权限控制、操作记录和恢复机制。具体保管人、保管位置、访问范围、保存期限仍需确认。 | OWNER_POLICY_APPROVED |

这是处理原则批准，不是逐文件公开、真实数据移动或远端实施许可。
[机器记录与待填字段](owner-decisions.json)保留未确认值为 null；本记录不被现有准入工具当作放行开关。

原 [D02/D03/D06 决定](../td01-owner-decisions-p35-review-r1/owner-decisions.md)继续有效。
原 TD-01B/D/E/F 的 PENDING、失败和 Hash 仍是当时快照，原文件不改。
原 [65 项代码身份](../td01e-code-identities-r1.json)、[222 项未解决非代码依赖](../td01e-unresolved-historical-dependencies-r1.json)及其信任根不改。

## D09 具体保管记录仍待完成

| 必填内容 | 本轮状态 | 生效前要求 |
| --- | --- | --- |
| 保管人 | UNCONFIRMED | 明确承担原件完整性、权限与保留责任的人 |
| 保管位置 | UNCONFIRMED | 明确独立受控存储及备份位置；不把真实私有路径或凭据写入公开仓库 |
| 访问范围 | UNCONFIRMED | 分别明确允许的对象、人员、目的及保管/读取/审计/恢复权限 |
| 保存期限 | UNCONFIRMED | 明确保留期限、到期审查与处置责任；不自动删除 |
| 恢复责任 | UNCONFIRMED | 指定恢复执行与验收责任，先在隔离环境验证，禁止覆盖原件 |
| 操作记录责任与位置 | UNCONFIRMED | 明确日志保管人和受控位置，记录授权依据、操作者、对象身份、动作、时间和结果 |

待确认的具体值应进入受控保管记录；公开材料仅记录其状态和必要的审查定位。
原则上的保管流程为：核准对象和权限 → 验证原件/备份身份 → 执行经授权的单项操作 → 留存操作记录 → 按责任与期限验证恢复。
当前没有保管位置、复制/备份权限或恢复验收记录，因此没有建立或声称已验收真实数据保管系统。
这些缺口阻断真实数据移动、备份和完整历史预演，不阻断不含真实数据的代码身份验证。

本轮只验证获准代码和合成 Git 图，见[兼容检查清单](compatibility-checklist.md)及[实际验证元数据](validation.json)。
原仓库继续 Public；原模型、历史研究及冻结 Hash 保留；不读真实 XLS/SOURCE_002 正文。
不调整真实历史、既有 Branch/Tag/Release，不上传 P35，不创建新远端，不执行 Ready/Merge/Release/Deploy。
