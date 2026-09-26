# V0.8-S4 用户确认的三产季面积 authority 应用

## 结果

39 个已恢复 Base 面积已按本任务的**明确业务确认**应用到 2023–2024、2024–2025、2025–2026：共 117 行，每季 39 个 Base、每季精确合计 41,335 亩。原始输入仍记录为 `CURRENT/UNSPECIFIED`；新增的产季绑定依据是 `EXPLICIT_BUSINESS_CONFIRMATION`，不是程序推断或跨季复制。

面积 authority overlay 已完整覆盖三季。训练季面积资格 78 行，OOT 季面积资格 39 行，身份绑定 39/39。面积 blocker 已关闭。

与既有 S1 数量 authority 的交集结果：训练季完整季总量资格为 0，OOT 季为 1；严格训练资格仍为 0，严格 OOT 资格为 1。因此当前阻塞训练的是**完整季产量 authority**，不是面积。部分日量和 unknown 没有被提升为完整季总量。

## 冻结决定与来源

- Area authority ID：`V0_8_THREE_SEASON_HISTORICAL_AREA_AUTHORITY_R1`。
- 面积来源：上轮恢复并精确求和为 41,335 亩的 39 Base 用户输入快照；原来源文件哈希和恢复 lineage 哈希见机器证据。
- 本任务的确认记录以任务 ID 标识；没有伪造用户原话或聊天 ID。
- 每条 authority 行保留原始 `CURRENT/UNSPECIFIED` scope，并追加解析后的三季 scope、确认记录 ID、当前 identity authority ID/hash 和原始来源记录 ID/hash。
- 所有面积运算使用 Decimal；每季分别核对 41,335 亩。

## 与旧面积记录的关系

两条既有 2025–2026 业务确认记录均保留原 provenance。完整 Base 粒度的旧值与本次用户确认的 Base snapshot 不一致，故在私有 reconciliation ledger 中标记为 `LEGACY_AREA_EVIDENCE_SUPERSEDED_BY_EXPLICIT_BUSINESS_CONFIRMATION`，旧值和来源仍保留。另一条是 member-grain 记录，数值不超过对应 Base 面积，因此标记为 `MEMBER_AREA_SUPPORTING_DETAIL`，没有被加总覆盖 Base 值，也没有形成 Base 冲突。

## 数量交集及边界

数量资格严格复用冻结质量 authority 的条件：

`business_total_coverage_status=BUSINESS_TOTAL_AUTHORITY_ELIGIBLE AND season_total_complete=true`

结果为：

- 面积合格：117 个 Base-season；训练季 78，OOT 季 39。
- 完整季数量 authority：训练季 0，OOT 季 1。
- 严格训练交集：0；严格 OOT 交集：1。
- `TRAINING_AREA_AUTHORITY_STILL_BLOCKING=false`。
- `QUANTITY_TOTAL_AUTHORITY_STILL_BLOCKING=true`。
- 先前“S2 训练季面积资格为 0”的结论仅在面积侧被本次明确业务确认 supersede；原 S1/S2 evidence、数量完整性、daily score 和 V0.7 指标均未修改。

## 产物与复现

完整 117 行 area authority、quantity eligibility、legacy reconciliation、overlay、业务确认记录及 manifest 保存在权限受限的私有 artifact 目录。仓库仅包含配置、实现、测试及聚合证据，不包含 Base 逐行面积。

两次独立执行产出的私有文件与 manifest 字节完全一致。输出目录权限为 `0700`，文件权限为 `0600`。本任务没有修改 canonical ledger，也没有训练、重拟合、回测或重放预测；不创建 PR，保持本地待审。

最终数量、hash 和边界状态见 [机器证据](../evidence/s4-user-confirmed-three-season-area-authority-application-r1.json)。
