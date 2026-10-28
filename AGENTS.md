# Codex 当前开发规则

本文件是当前工程入口；版本身份见 [VERSIONING.md](VERSIONING.md)，能力状态见
[README.md](README.md)。它不重定义任何冻结的模型、指标、数据或授权合同。

## 开始工作

1. 读取当前 Owner 任务，核验仓库、fresh fetch 后的基线、分支、tracked/untracked 状态和修改范围；保护其他任务及私有成果。
2. 先确定 Forecast Family、输入/输出物理量、日历、模型/fit、来源版本、评价协议和授权范围，再读取该族已合并合同及源码。根目录概述不能覆盖更具体的冻结合同。
3. 历史文档中的“待审核”“未授权”是当时快照；后来授权以明确的新决定及实际 GitHub 记录为证，不回写旧证据。当前任务未授权的后续阶段不得自行启动。
4. 旧指令与当前任务或对应模型族合同冲突时，指出冲突并按已明确授权的范围工作；不得自行修改冻结 Hash、分母或数学规则来调和冲突。

## 按模型族选择规则

| 对象 | 当前依据与适用边界 |
| --- | --- |
| 早期 Task 0–14 / Core Forecast / Forecast Quality Trial | [历史任务索引](CODEX_TASKS.md)及其具体合同；已有接口和数值语义保留，不能向其他预测族传播默认项 |
| Operational Peak、Area Forecast 及其他已保存预测族 | 使用各自 source_kind、forecast_family、模型/fit、来源、成员、面积、日历和 Saved Run 授权；不能互换身份或回退成另一个族 |
| V0.19 研究与滚动 Shadow | [范围](docs/v0-19/v0.19.0-version-plan-and-scope-freeze.md)、[S7](docs/v0-19/s7/rolling-forecast-integration-r1.md)、[S8](docs/v0-19/s8/target-aligned-inbound-source-r1.md)、[S9](docs/v0-19/s9/inbound-source-readiness-r1.md)；冻结 M0/M1 是点预测，研究身份不等于生产默认模型 |
| V0.20 农事历史准备 | [版本合同](docs/v0-20/v0.20.0-version-plan.md)；本地 Excel 映射和质量检查不授予来源、训练或预测权限 |
| V0.21 周期、结构和评价准备 | [版本合同](docs/v0-21/v0.21.0-version-plan.md)、[阶段计划](docs/v0-21/stage-implementation-plan.md)；合成研究准备，不是农艺增强生产模型 |

## 日期范围、峰值与数量语义

- 完整产季 `FULL_SEASON_PEAK` 使用事前声明的 `[season_start, season_end]`。
- 声明剩余产季 `DECLARED_REMAINING_SEASON_PEAK` 使用事前冻结的 `[remaining_start, season_end]`，起点不得早于 origin D+1。不能根据实际最后采收日或实际峰日选择范围。
- `ORIGIN_H7_PREFIX` 与 `ORIGIN_H15_LOCAL` 是 D+1…D+7/15 局部窗口。H7 来自同一完整 H15 预测的前七日；不能改名为产季峰。完整/剩余产季高峰与任意 origin 滚动预测是独立且同等优先级的目标。
- 单日峰、旧 Task 3 连续3日中位/均值持续峰、rolling7 累计峰、rolling15 累计峰是不同指标。不得相互替代、复用名称或修改既有公式。只有一个候选峰窗产生的零起点误差不代表峰时预测能力。
- 不存在跨模型族通用的“仅1—4月”、品级/基地排除表或默认置信区间；使用相应已冻结的来源与日历规则。保留原始事实，排除条件不能按评分表现选择。
- Core Forecast 中已有的 P50/P80/P90 字段仍按其旧合同解释；字段存在不证明真实校准。Point、规划上界、Upper80/Upper90 不能仅更名为已校准的 P50/P80/P90，不得虚构区间或覆盖率。
- 区分 `FARM_PICK / OBSERVED_WEIGHT / KG`（对应适配层 `FIELD_HARVEST_WEIGHT`）、`RECORDED_INBOUND_WEIGHT`、SOURCE_002 入库称重净重、自然成熟量和商品果量。名称相似或单位同为 kg 不是物理等价证明。
- 分别保留 feature observation、model training target、forecast target、evaluation label 的物理口径；无来源等价证明或正式转换 authority 不得声称同口径评分。

## 数据、时间与授权

- 数据保管、研究读取、预测执行、标签评分、公开发布是不同权限。文件存在、公开可下载、Hash 匹配或合成测试通过不构成实际授权；不得扫描其他私有目录寻找替代数据。
- 原始数据、旧版本合同、历史证据和已发布 Tag/Release 不原地改写。TD-01 已取消两份历史 XLS 的追踪，不能重新添加；缺少授权原件应明确失败，不引入合成替身。取消追踪不消除历史公开风险。
- 业务日期、observed_at、recorded_at、known_at/available_at、入库时间及真实签发时间不得互相代填；日精度不伪造时分秒。仅有业务日期或事后来源只能声明相应 date-bound/replay 身份，不能声明 STRICT_PIT。
- V0.19 滚动与 V0.21 origin 特征遵守业务日期 `<D` 和可信 cutoff 可见性；未来实际、晚到修订、季末总量及峰日不得污染封存输入。预测生成和独立成熟标签评价分开执行。
- 公平评价保留 C0、逐指标共同 Cm、失败及不可计算记录、实际分子/分母、覆盖及物理口径；已暴露历史对照不称盲测，不删除困难成员制造改善。
- 缺失、UNKNOWN、PARTIAL 与有证明的零值不同；不得补零凑完整性。只有对应合同明确允许的先验/回退才能使用，并说明身份与限制；不得将 M0 回退冒称 M1。
- 模型训练、晋级、真实前瞻验收、来源准入和生产部署分别需要其对应证据与授权，不因工程 Release 或 CI 成功自动成立。

## 实施与交付

- 复用已有导入、身份、特征、求解器、评分、保存及报告功能。LLM 不编造重量、系数、区间或改善率；业务数值由确定性代码产生。
- 重量/金额使用对应合同的 Decimal/NUMERIC、单位和舍入规则；展示格式不改变权威结果。加工厂建筑面积不是种植面积或峰值预测特征。
- 数据库变更通过 Alembic；导入保持幂等；敏感业务行、私有路径及密钥不进入公开日志或 PR。
- 实现业务规则时先添加可复现问题的测试。按改动运行专项、相关回归、Ruff、Format、Mypy；不修改 Golden 预期值、增加 skip/xfail 或降低 CI 门槛来换取绿灯。
- 区分本地测试、PR exact-head CI、独立评审、合并后 main CI、正式发布与部署。queued/in_progress 是 PENDING，不是 SUCCESS；报告实际 SHA、失败及限制。
- 当前任务仅授权到 Draft PR 时，到此停止。没有 Owner 对该操作的明确授权，不得 Ready、Merge、Tag、Release、Deploy，也不得自动启动后续版本。无需凭空增加另一套 Reviewer、签名或审批平台。
