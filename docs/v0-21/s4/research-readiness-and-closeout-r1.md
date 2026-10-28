# V0.21 S4：研究就绪报告与工程收口

任务：`V0_21_S4_RESEARCH_READINESS_REPORT_AND_CLOSEOUT_R1`。

S4 新增离线报告生成器，把已合并的 S1 生产周期、S2 结构变化和 S3 四族评价结果串联为可阅读、可复算的合成研究准备报告。本阶段不生成农事增强预测、不训练模型，也不读取真实农事或入库标签。

基线为 `c32a060b03355c3f5da82f94ee992c4ff245a274`；其 main CI `40612205554` 已成功。S0–S3 的 PR、合并 SHA、历史源码与输入配方身份记录在独立的 [S4 证据](../evidence/v0.21-s4-readiness-closeout-r1.json) 中，原证据未改写。当前 S4 实施授权来自本次用户任务；它不授予 Ready、Merge、真实实验或发布许可。

## 复用与执行顺序

| 阶段 | 直接调用的现有接口 | S4 所做工作 |
| --- | --- | --- |
| S1 | `v021_cycle_features.prepare` | 重算声明周期、完整成员、合法 origin 特征与不可见原因；不把完整原始事实账本当作时点特征 |
| S2 | `v021_structure_scenarios.prepare` | 保留连续性、三个面积口径、品种进出、换苗、密度及独立 origin 结构快照 |
| S3 注册 | `v021_evaluation_readiness.register` | 冻结成员、日历、模型/fit、来源、范围和物理量 |
| S3 封存 | `seal_predictions` | 先验证并封存独立预测；沿用 R2 的 H7 所依赖的实际完整 H15 向量检查 |
| S3 评分 | `score` | 仅在封存后打开合成标签，沿用原十指标和 V0.21 四项附加指标 |
| S4 | `prepare_case` → `seal_case` → `finish_case` → `build_report` | 分数据集投影实际数量、覆盖、失败、Hash与独立状态；生成 JSON、Markdown、HTML |

纯计算模块不访问文件、网络或数据库。CLI 只读取显式 catalog 的相对路径，校验同一份读取字节的 SHA256 后解析；拒绝真实类别、重复键、浮点/NaN、越界/符号链接路径、未知 schema、Hash 漂移和已有输出目录。每文件上限沿用 S1 的 16 MiB，catalog 最多 64 个数据集。输出目录 `0700`，文件 `0600`。

阶段接口不接收标签到预测阶段。CLI 在 S3 注册或封存失败时不打开标签文件；拒绝输入仍保留数据集和原因，不伪造评分。它不自动发现私有文件、不读取模型参数、不修改上游准备包。

## 运行方法

使用项目已安装依赖的 Python 3.12，在仓库根目录运行。输入和输出目录均须新建，不能覆盖已有结果。

```bash
python -m backend.tests.agronomic_history.v0_21_readiness_fixture \
  --full-matrix \
  --evidence docs/v0-21/evidence/v0.21-s4-readiness-closeout-r1.json \
  --output /tmp/SYNTHETIC-v021-s4-inputs

python -m backend.research.v021_readiness_cli \
  --catalog /tmp/SYNTHETIC-v021-s4-inputs/SYNTHETIC-catalog.json \
  --output /tmp/SYNTHETIC-v021-s4-first

python -m backend.research.v021_readiness_cli \
  --catalog /tmp/SYNTHETIC-v021-s4-inputs/SYNTHETIC-catalog.json \
  --output /tmp/SYNTHETIC-v021-s4-second
```

逐字节比较两次的 `research-readiness.json`、`report.md`、`report.html`。`manifest.json` 分别保留真实 UTC、Python/平台、实际 Git SHA、dirty 状态、源码字节 Hash、原始输入文件 Hash 和结果文件 Hash；执行时间不应相等，也不参与业务结果 Hash。合成 `as_of` 是评价夹具时钟，不能冒充实际执行时间。

catalog 明确声明 `SYNTHETIC_TEST_FIXTURE`、数据集 ID/阶段/场景、每种输入的精确路径及 Hash、评价 `as_of`，可附公开历史证据。缺少公开证据时只报告历史交付身份未证明；提供时必须通过固定 Git 字节和祖先关系验证。历史算法源码还必须与当前执行文件一致。

## 实际合成输出

[完整机器结果](examples/research-readiness.json)、[完整 Markdown](examples/report.md)、[离线 HTML](examples/report.html) 与 [执行 Manifest](examples/manifest.json) 来自实际运行，不是预填结果。

本次完整输入共 **39 个独立示例数据集**：1 个 S1、15 个 S2、22 个 S3，另有 1 个 S3 R2 缺 D+8 回归。39 不是基地数，不能将重叠示例相加作为真实覆盖率。每个数据集各自保留计数、来源身份、失败账本和 Cm。

- S1 主示例：3 个合成 Base、2 个产季、6 个声明周期、8 个 origin 特征快照。
- S2 BUSINESS_EXAMPLE：同一连续成员的 PLANTED 从 100 到 120 亩，变化 +20；PRODUCTIVE 从 60 到 50 亩，变化 −10；EFFECTIVE 从 50 到 45 亩，变化 −5。其他成员、密度和换苗证据按实际状态分别保留，不以总 PASS 掩盖缺失。
- S3 COMPLETE 的完整产季实际 rolling15 为 92 kg（2025-03-02 至 03-16）；基线 72 kg、候选 85 kg，各自独立选峰。声明剩余产季实际 rolling7 为 52 kg、rolling15 为 60 kg；不能改称完整产季高峰。
- COMPLETE 的 H7：2 个 C0、2 个共同可算成员；逐日 MAE 为基线 `109/14`、候选 `11/14` kg/day；累计量 MAE 为基线 `67/2`、候选 `11/2` kg/window。H15 的逐日 MAE 为 `191/30` 与 `11/30`，累计量 MAE 为 `15/2` 与 `11/2`。分子、分母、50位精度结果均保留。
- R2 缺 D+8：前 7 日仍有数据，但对应 H7/H15 的 DAILY_MAE 均保留 C0=2、Cm=1、不可计算=1，未用短前缀放行 H7。
- 全零实际、未成熟标签、未知连续性、冲突面积、缺日/缺预测仍在各自账本。`PREFIX_MISMATCH` 在注册阶段拒绝，未打开标签。

以上改善、退化或 `MIXED` 均为 **SYNTHETIC_ARITHMETIC_DEMONSTRATION**。没有真实农艺效果、因果增益或生产准确率结论。

## 两个同优先级目标与报告阅读

目标 A 分开呈现完整产季和事前声明剩余产季的单日、连续 7/15 日高峰、双方各自峰窗和逐日向量。目标 B 单独呈现 origin D+1 开始的 H7/H15 每日重量及累计误差。H7 的 rolling7、H15 的 rolling15 等只有一个候选峰窗时，保留合法数值与原分母，但显示 `timing_skill_interpretable=false`。

HTML 无脚本、CDN或在线资源。六章导航、按数据集折叠的详情、独立表格横向滚动支持桌面与手机阅读；外部文本统一转义。完整指标、共同成员身份及 Hash、失败原因、每天 signed/absolute error 和各自峰窗仍在报告内可展开。不同示例不合并总体，逐指标失败不能从 C0 删除。

## 真实证据缺口与工程边界

报告逐项列出 11 类缺口，全部为 `NOT_PROVEN`：真实完整成员权威、跨季连续性、面积口径和有效期、周期与事件来源、换苗株数密度、独立来源时钟、origin/cutoff及发行身份、入库物理量、成熟完整逐日标签、模型与训练范围、真实读取及独立实验授权。合成来源、字段非空、Hash或模拟时钟均不能补足这些证据。

未来公平研究需事前冻结 C0/日历/版本，同物理量同日期且双方使用同一 Cm，按时间顺序训练与跨季验证，必要时基地留出；预测封存后才读取独立成熟标签，保留退化、失败与不稳定收益。本次不执行这些真实实验。

当前状态分开记录：代码已实现；合成链路实际执行；真实证据未证明；S4 PR 待独立复审；Owner 未授权 Merge；S4 合并后 main CI 尚未执行；Release/Deploy 未授权。因此：

```ini
REAL_DATA_READ=false
MODEL_TRAINING=false
REAL_ACCURACY_VALIDATED=false
STRICT_PIT_VALIDATED=false
PRODUCTION_FORECAST_CHANGE=false
V0_21_FORMAL_COMPLETE=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYED=false
```

Manifest 中的基线 Git SHA + dirty 状态如实表示提交前的示例执行，不伪造为未来提交。正式提交后应再用同一 catalog 生成新目录，核验业务文件相同且执行源码字节与最终 HEAD 一致。PR CI 属于该最终 HEAD 的独立验收，不能用基线 CI 代替，也不能用 PR CI 代替 S4 合并后 main CI。

## 本地验收记录

本次 S4 专项 45 项通过，相关既有回归 472 项通过，未新增 skip/xfail/retry。相关范围包括 V0.20/S1/S2/S3、V0.19 冻结指标及合成日曲线、来源准备和 PIT 可见性规则。Ruff、全仓 Format 检查及 `mypy backend/app backend/research`（637 个源码文件）通过。

完整 39 数据集在两次独立进程中执行，JSON、Markdown、HTML 字节及各自 SHA256 一致，业务结果 Hash 为 `213b910f340d9e87f18a56c3faff146b2a51eb08275b8cc49dc874d56cb9ed43`；真实 UTC 和原始文件字节身份独立记录在各次 Manifest。保存 JSON 后再读取渲染仍与落盘文本一致。

实际浏览器验收使用 1440×1000 和 390×844 视口，章节导航、数据集详情和指标展开可操作，页面无横向溢出、脚本错误或外部 HTTP 请求。表格内部允许横向滚动以保留完整指标。此验收只证明离线报告可阅读，不证明真实数据、农艺效果或生产能力。

最终 PR Exact-head CI 应以 GitHub 实际记录为准，不在提交前预填成功。全部 S0–S3 源码、历史文档/样例/证据及 V0.19 评分器保持原字节不变。
