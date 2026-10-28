# 蓝莓产量与加工峰值预测 Agent

Blueberry Yield & Processing Peak Forecast Agent

本项目提供确定性的预测计算、历史研究、数据准备和受控 Shadow 业务流程。
当前正式工程版本是 [v0.21.0](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/releases/tag/v0.21.0)，
发布提交为 `3bf2e172822f8b375cf30a0e2c0fcb96ebade722`。当前 main 包含发布后的技术债修复，
不能与该 Tag 的源码等同；实际身份请记录 Git SHA 和工作树状态。

Python、前端和 FastAPI 保留的 `0.2.0` 是组件兼容元数据，不是“当前工程只到 V0.2”。
版本来源、锁文件和更新规则见 [VERSIONING.md](VERSIONING.md) 与
[机器清单](version-manifest.json)。本次没有发布新组件包或新的工程版本。

## 已实现什么，证明到哪一步

| 能力 | 已实现范围 | 证据边界 |
| --- | --- | --- |
| 既有 Core Forecast、Area Forecast、Operational Peak 等模型族 | 确定性日曲线、对应峰值、不可变保存与读取、各自 API 和质量流程 | 每个族有独立日历、模型、物理口径和权限；字段/接口存在不证明真实未来精度 |
| V0.19 曲线与历史研究 | 冻结基线/唯一日曲线候选、限定历史回放、训练与跨季研究、独立评分和失败保留 | 既有获授权历史研究已经执行；已暴露样本和跨来源限制仍保留，不是盲测或前瞻验收 |
| V0.19 S7–S9 滚动工程 | 冻结 M0/M1、H7/H15、逐日曲线、高峰、PostgreSQL保存/重载、Origin查询比较、Dashboard、独立标签评价及来源准备 CLI | CONTROLLED_RESEARCH_SHADOW；真实来源需逐项授权并证明身份/时间/口径，工程测试不晋级模型 |
| 电子表格准备与演示 | 浏览器本地 CSV/XLSX、多表/表头/人工映射、质量预览；固定合成样本绑定既有预测与报告导出 | 任意用户文件为未验证预览，不自动上传、导入、登记来源或触发预测；合成演示不是实际产量 |
| V0.20 农事历史基础 | 面积、管理事件、物候规范化，身份/修订/有效期/来源时点检查，版本化 JSON/CSV/HTML | 本地数据准备及合成验收；普通开花不自动变成 BLOOM_10/50/90，未知促早不推断为加温 |
| V0.21 研究准备 | 跨季生产周期、面积/品种/换苗/密度结构描述，完整/剩余产季及 H7/H15 合成评价，离线研究就绪报告 | S0–S4 已合并并随 v0.21.0 发布；39 个合成数据集不是39个实际基地，也不证明农艺预测增益 |

来源导航：[V0.19 范围](docs/v0-19/v0.19.0-version-plan-and-scope-freeze.md)、
[历史回放边界](docs/v0-19/s3/owner-controlled-replay-r1.md)、
[S7 运行流程](docs/v0-19/s7/rolling-forecast-integration-r1.md)、
[S8 入库快照](docs/v0-19/s8/target-aligned-inbound-source-r1.md)、
[S9 准备工具](docs/v0-19/s9/inbound-source-readiness-r1.md)、
[V0.20](docs/v0-20/v0.20.0-version-plan.md)、
[V0.21](docs/v0-21/v0.21.0-version-plan.md)、
[S4 报告与运行说明](docs/v0-21/s4/research-readiness-and-closeout-r1.md)。
各文档保留交付当时的授权与验收快照；后续合并/发布事实以 GitHub 记录为准，不回写历史状态。

## 预测的范围和数量不能混用

完整产季高峰与任意预测起点未来7/15日是两个独立且同等优先级目标。

| 范围 | 日期与解释 |
| --- | --- |
| 完整产季 | 事前冻结 season_start…season_end；产季内单日、最大连续7/15日累计及峰窗日量 |
| 声明剩余产季 | 事前冻结 remaining_start…season_end，起点至少 D+1；不能冒称完整产季 |
| Origin H7/H15 | D+1…D+7/15；H7 为同一完整 H15 曲线的前七日；局部峰不是全季峰 |

单日峰、旧3日持续峰、rolling7、rolling15 各有自己的公式。单一候选峰窗的零起点误差不代表
预测峰时能力。日误差与窗口累计误差分别报告，不能用正负抵消掩盖日量偏差。

既有 Core Forecast 的 P50/P80/P90 字段按其冻结合同保留；有字段不等于已完成真实校准。
M0/M1 的 Point 及规划上界不能改名为已验证分位数，也不能凭页面展示宣称覆盖率。

田间采摘 `FARM_PICK`、入库登记重量 `RECORDED_INBOUND_WEIGHT`、SOURCE_002 入库称重净重、
自然成熟量和商品果量是不同物理量。S6 冻结训练目标为入库登记重量；特征、训练目标、预测目标、
评价标签分别记录，无等价证明不能执行伪同口径评价。重量显示默认 kg，吨只作展示换算。

## 尚未验证与未来工作

- 真实农事数据的完整权威、可信历史可见时点及对应成熟标签仍未完整验证。
- 业务日期、事后历史回放和合成时钟不能证明 STRICT_PIT；真实签发与事后重算必须分开。
- 已暴露历史结果、工程 CI 和合成改善不证明未来精度、农艺因果增益或生产可用性。
- V0.21 未训练/晋级新的农艺增强生产模型；剪枝、促早、开花和密度不能直接变成产量倍率或峰日偏移。
- 真实数据验证、受控前瞻研究、模型晋级和生产部署是后续独立授权工作，不由本 README 自动启动。

## 数据与开发入口

原始业务数据不随当前 checkout 提供。TD-01 已取消两份历史 XLS 的追踪；旧工具需明确授权原件，
文件缺失应失败，不能自动寻找替身或补零。历史提交及旧 Tag/Release 仍可能引用这些文件，
取消追踪不代表历史公开风险已消除。数据保管/研究许可不等于公开发布许可。

开发从 [AGENTS.md](AGENTS.md)、[当前 Codex 模板](CODEX_MASTER_PROMPT.md) 与
[任务及历史路线](CODEX_TASKS.md) 开始；测试命令见 [版本检查](VERSIONING.md#可执行检查)，
发布导航见 [CHANGELOG](CHANGELOG.md)。修改模型族前阅读其具体合同，禁止按早期 Task 0–14
重新开发或无条件套用1—4月、3日峰与置信区间默认项。

本仓库提供规划、研究和受控工程能力，不替代业务负责人或农业专家判断；没有对应证据和授权，
不得将研究候选视为生产默认模型，也不得自行 Ready、Merge、Tag、Release 或 Deploy。
