# 蓝莓视觉研发 R1：现有工程能力审计

TASK_ID=`BLUEBERRY_VISION_FOUNDATION_ENGINEERING_PREPARATION_R1`。
审计基线为研发分支 `research/blueberry-vision-foundation-prep-r0` 的
`60208273be061d891c2cfb5bb4ff952647f6e5f8`；日期为 2026-10-13。

本审计只读取仓库源码、配置和公开规范，不打开历史数据文件、私有工件、真实图像、
正式预测记录或当前 2026–2027 actual，不连接数据库、不执行训练、回测、评分或发报。
“已有”指代码和合同已存在，不证明当前环境、数据许可或生产能力已经验证。
R1 新授权允许独立 research 契约和离线准备工具；它替代 R0 对本任务的
`DOCS_ONLY=true` 限制，不改变旧文件的历史授权快照，也不授予真实数据访问。

## 1. 冻结边界与规范继承

已阅读 `AGENTS.md`、`README.md`、`CODEX_MASTER_PROMPT.md`、`CODEX_TASKS.md`、
[R0 准备记录](blueberry-vision-foundation-preparation-r0.md)，以及下列冻结合同。

| 公开证据 | 对本轮的约束 |
| --- | --- |
| [V0.14 scope](../v0-14/v0.14.0-version-plan-and-prospective-protocol-freeze.md)、[closeout](../v0-14/v0.14.0-closeout.md) | C0/W1 artifact pair、模型、scheduler、registry、issuance policy、seed bytes、metric hash 不变；影子队列不增加视觉特征，不重发或重封存历史预测。 |
| [V0.15 closeout](../v0-15/v0.15.0-closeout.md) | Base10、Harvest State V1 四项特征及固定 A/B 研究冻结；无新 experiment authority 不得 tuning、refit、rescore。`STRICT_PIT=false`，历史 2025–2026 OOT 已暴露。 |
| [V0.16 scope](../v0-16/v0.16.0-version-plan-and-scope-freeze.md)、[closeout](../v0-16/v0.16.0-closeout.md) | hierarchy、uncertainty、attribution、ForecastOps、business loss、what-if 数学不变。Point 不等于已证明 P50；规划上界不等于已校准分位数；贡献不证明因果。 |
| [V0.17 product scope](../v0-17/v0.17.0-version-plan-and-product-scope-freeze.md)、[closeout](../v0-17/v0.17.0-closeout.md) | VISION 与 BLUEBERRY_IMAGE_MODEL 不在其产品范围；五页 Dashboard、八工具、业务 payload 和结果 hash 不改。公开历史质量不能冒充当前准确率。 |
| [V0.18 business scope](../v0-18/v0.18.0-business-usability-scope-freeze.md)、[本地认证补充合同](../v0-18/s0/simplified-local-auth-scope-addendum-r1.md) | 保留身份、资源授权、exact-run binding、历史 Quality 独立授权语义；知道 run ID/hash 不是访问许可，Base/Region/Company 不自动继承彼此权限。独立视觉研究不改安全业务主线。 |

旧 scope/closeout 的 PR、Ready/Merge 和阶段授权描述是对应历史任务的合同与快照。
本 R1 按本轮用户指令只 commit/push 指定研发分支，不创建 PR、不启动后续实验，
不分配正式版本、不发布或部署。`AGENTS.md` 的未来上线回测要求仍适用，
但本轮只需执行新离线校验工具测试，不能为满足上线规范越权运行旧训练或生产测试。

## 2. 历史产量与面积组织

| 已有能力与代码证据 | 视觉研发缺口 | 复用建议 |
| --- | --- | --- |
| [`models/historical_import.py`](../../backend/app/models/historical_import.py)：`IngestFile` 保存 file SHA256、config hash、导入状态；`FactReceiptRaw` 保存原始 payload、来源 sheet/row、行指纹、日期/重量/品种/加工厂及质量状态。重量是 `Numeric(18,6)` kg；来源行指纹唯一。 [`etl/history/fingerprint.py`](../../backend/app/etl/history/fingerprint.py)、[`etl/history/importer.py`](../../backend/app/etl/history/importer.py) 提供去重与导入工程模式。 | 采收到厂重量及原始文字不是图片、bounding box、实例 mask、单果 ID 或成熟标签；历史 grade 也不能直接当果园成熟阶段。 | 复用“来源字节 → 幂等 identity → 显式质量状态”的模式，视觉 manifest 独立存储；本轮不调用导入器、不读 raw 表。 |
| [`analytics/daily_facts.py`](../../backend/app/analytics/daily_facts.py)：按日期×工厂×farm key×subfarm key×品种聚合；版本、来源最大 row ID、规则 config 和节日信息独立记录。 | 到厂粒度与单株、果串、样方或视频帧没有已确认 correspondence；聚合重量不能反推图像覆盖率或单果重量。 | 未来只通过经批准的 season/sampling unit/identity/time 映射关联；先证明粒度一致，不能按名字或同一天直接合并。 |
| [`models/production_plan.py`](../../backend/app/models/production_plan.py)：farm-season-variety 计划含 planted area mu、预计 kg/mu、商品果率、树龄、修剪/花期/首采日期、版本、生效区间、available_at、source version 与 row hash。 [`area_yield/data.py`](../../backend/app/area_yield/data.py)：面积 authority 要求 scope、season、有效期、面积依据和来源，校验 kg 与 mu 范围对应。 | 已有面积和树龄字段不证明真实视觉样方面积、采样概率、相机几何、树株覆盖、历史时点权限或独立称重已可用。 | 将面积/树龄视为未来独立对照的候选非视觉协变量；保持 mu 与 count 单位隔离。无数据不能填零，也不能用面积预测能力宣称视觉训练数据准备完毕。 |
| `area_yield/data.py` 的 `materialize` 区分 `OBSERVED`、`AUTHORIZED_LEDGER_ZERO`、`UNKNOWN_MISSING`； [`base_registry/business.py`](../../backend/app/base_registry/business.py) 对不完整 coverage 输出 null/unknown。 | 账本零语义依赖账本授权，不能继承为“无图片=零果实”。 | 视觉记录必须分别表达未采集、未标注、不可判读与审核确认零目标；有效零需要完整适用标签和明确复核。 |

历史原始表的 append-only 规则来自 `AGENTS.md`，本轮不修改表或原文件。
上述源码检查没有证明任一真实产季数据现可访问，也没有验证记录内容。

## 3. Base、Region、Company 身份体系

[`models/master_data.py`](../../backend/app/models/master_data.py) 有 Season、Farm、Subfarm、
Variety、Factory 等数据库主数据；数据库 Farm ID 和 canonical forecast Base ID 是不同概念。
[`base_registry/registry.py`](../../backend/app/base_registry/registry.py) 构造带 source hash 的
`BASE_REGISTRY_V1`。[`base_registry/business.py`](../../backend/app/base_registry/business.py)
的 `map_farms` 只接受唯一 exact mapping 或带证据的 `AUTHORIZED_ALIAS`；歧义与未映射保留
`AMBIGUOUS` / `UNRESOLVED`。当前源码并不是授权视觉采集单位自动绑定的依据。

[`forecast_intelligence/hierarchy.py`](../../backend/app/forecast_intelligence/hierarchy.py)
从 authority registry 的 `region_scope` 和 active Base 构建 hierarchy snapshot/hash，
没有根据基地名称或坐标推断 Region。Company ID 为 `COMPANY_AGGREGATE_ROOT_V1`，其明确语义是
`TECHNICAL_FORECAST_AGGREGATION_ROOT_NOT_LEGAL_ENTITY_IDENTITY`。
Farm 不是正式预测父层级，Factory 是 routing/allocation，不是产量 ownership hierarchy。

视觉缺口包括：sampling unit→Base 的批准映射、采集会话与地块/树株主数据、品种核验、
映射在 observed_at/available_at 时的有效版本、采集主体组织与访问 authority。
建议复用稳定 ID、显式 unresolved、authority version/hash 和历史 snapshot 模式，
不直接加载当前 registry 推断历史身份，不以技术 Company root 冒充法人或图像所有权。

## 4. 模型训练、验证与隔离工具

| 已有源码能力 | 实际限制 | 可复用部分 |
| --- | --- | --- |
| [`area_yield/v015_research_cohort.py`](../../backend/app/area_yield/v015_research_cohort.py) 有 cohort admission、时区 cutoff、season split、future-row filter、common rowset 检查。冻结角色为 TRAIN=2023–2024、VALIDATION=2024–2025、EXPOSED_OOT=2025–2026。 | 这是历史数量研究合同，EXPOSED_OOT 不能称全新盲测；这些产季角色不可直接移作视觉 split。 | 复用按时间/身份 admission、相同对照 rowset、特征先过滤再读取数值的模式；为视觉另建按采集会话、相似帧组和样方的 split。 |
| [`area_yield/v015_base10_benchmark.py`](../../backend/app/area_yield/v015_base10_benchmark.py) 有固定 Ridge/CatBoost/LightGBM 候选、随机种子、train-only scaler、phase/split label 访问规则。 [`area_yield/v015_benchmark_custody.py`](../../backend/app/area_yield/v015_benchmark_custody.py) 核验 feature/label 文件与行 hash，先封存预测再解锁标签。 | 都是冻结数值模型工具；不包括 YOLO、实例分割、成熟视觉模型、图像增强、图像标注或独立图像测试集。冻结模型不能 refit。 | 复用配置/随机种子、标签保管与 seal-before-test 的治理模式；视觉未来训练必须在新授权的独立 pipeline，不能调用旧 benchmark 重跑成绩。 |
| [`rolling_backtest/availability.py`](../../backend/app/rolling_backtest/availability.py)、[`rolling_backtest/config.py`](../../backend/app/rolling_backtest/config.py)、[`rolling_backtest/verify.py`](../../backend/app/rolling_backtest/verify.py) 提供可用性 authority 与审计/验证结构。 [`baseline/metrics.py`](../../backend/app/baseline/metrics.py)、[`forecast_intelligence/forecast_ops.py`](../../backend/app/forecast_intelligence/forecast_ops.py) 提供数量误差和 completeness 模式。 | 工程结构不等于视觉检测指标实现；mAP/IoU、实例匹配、分类混淆矩阵、近重复帧检测和标注一致性尚未由本轮审计验证。 | 未来同 scope/unit/time 的非视觉对照可参考 MAE/Bias 与 completeness；本轮只设计检测/计数/成熟度及视觉增量实验协议，不计算真实准确率。 |

## 5. 数据、来源与模型 hash

已有文件 SHA256、行指纹、config hash、dataset/feature/label hash、model artifact hash、
request/result hash 与 record hash 模式。证据包括：

- `models/historical_import.py` 的 file_sha256 / source_row_fingerprint；
- `area_yield/v015_materialization.py` 的 feature/label zone 分离、来源 lineage 与 row hash；
- [`residual_model/artifact.py`](../../backend/app/residual_model/artifact.py) 的 binary SHA256、model family、feature schema、config、manifest metadata 校验；
- [`area_yield/research_records.py`](../../backend/app/area_yield/research_records.py) 的 model registry/file hash、training cutoff、request snapshot、record seal、不可覆盖创建；
- [`models/operational_peak.py`](../../backend/app/models/operational_peak.py) 的 execution/request/authority/result hash 与 saved metadata。

视觉缺口是 image bytes hash、near-duplicate/derivation group、annotation revision、
label-definition revision、标注复核来源与许可 revision 的联合 lineage。
R1 应在新契约中明确自己的 canonical JSON/hash 规则，不能只写“沿用 hash”而忽略
现有模块 canonical bytes 是否含末尾换行、数值序列化和 schema version 的差别。
asset hash 证明字节一致性，不证明图片真实、标签正确、权限有效或近似帧互不相同。
本轮 synthetic asset hash 是模拟标识，不证明实体图像文件存在；本轮也不读取图像来验证它。

## 6. Point-in-time / available_at

已有运行逻辑支持可用时间控制：

- [`planning/plan_service.py`](../../backend/app/planning/plan_service.py) 的 `get_effective_plan`
  按 `available_at <= as_of_date` 与 effective interval 选择计划版本；
- [`weather/repository.py`](../../backend/app/weather/repository.py) 的 observations/mapping 查询
  执行 available_at 及适用生效期过滤；
- `rolling_backtest/availability.py` 分别检查记录可用日期、观察日期和 run/artifact authority；
- [`area_yield/v015_harvest_state.py`](../../backend/app/area_yield/v015_harvest_state.py) 在读取重量前
  排除 origin 当日及未来采收，仅有四项冻结 date-bound features。

限制必须同时保留：V0.15/V0.16/V0.17 公开合同明确 `STRICT_PIT=false`、
`HISTORICAL_ACTUAL_AVAILABLE_AT_PROVEN=false`、`RETROSPECTIVE_AUTHORITY_USED=true`。
“日期早于 cutoff”不是“那个时刻系统已经获知”的证据；现有历史 source timestamp 不自动
解决视觉首次上传、标注完成、复核批准或身份修订的 available_at。

视觉设计应保存带时区的 observed_at 和 available_at，并保留资产、标签、预测等各阶段
首次可用来源。未来用视觉特征作 as-of 对照时，要以实际用于计算的最新必要阶段可用时间
为 cutoff gate；不得用事后标注/未来帧或采收重量改善过去预测。真实来源时间证据缺失时，
只能标记 retrospective 或不可评估，不能拿文件 mtime/Git 提交时间作业务可用证明。

## 7. Forecast Intelligence 与预测结果存储

[`forecast_intelligence/read_schemas.py`](../../backend/app/forecast_intelligence/read_schemas.py)
的 `ForecastIdentity` 包括 source_kind、forecast_family、run_id、hierarchy_level、entity_id、
target_season、origin_date、baseline_id、policy_version；读取可另绑定 expected_source_result_hash。
[`forecast_intelligence/read_service.py`](../../backend/app/forecast_intelligence/read_service.py)
校验 exact identity 与 source result hash，区分 saved forecast、retrospective observation 和
NO_CURRENT_ACTUAL；不自动填补 unavailable interval/attribution。

`models/operational_peak.py` 保存 Base run、请求/authority 快照与 daily predicted_kg。
[`models/hierarchical_forecast.py`](../../backend/app/models/hierarchical_forecast.py) 和
[`forecast_intelligence/persistence.py`](../../backend/app/forecast_intelligence/persistence.py)
保存 append-only Region/Company run、hierarchy snapshot/hash、完整 child 来源 run/hash 和 daily rows；
缺 child 产生 INCOMPLETE_CHILD_COVERAGE，没有正式 aggregate。
[`models/core_forecast.py`](../../backend/app/models/core_forecast.py) 另有版本化 code authority、
engine/build/config hash、可用时间与 forecast/input/result 身份；各 family 不能仅凭 run_id 合并。

目前没有由上述 saved forecast 合同确认的视觉观测 field/table 或视觉增量 family。
建议未来建立单独的离线 comparison manifest，引用经批准的完整 saved-run identity/hash，
以 canonical Base/season、同一可比日期范围和独立真实称重 label authority 比较；
保留视觉缺失及共同样本覆盖率，不修改 saved run、生产预测或现有 FI 接口。
本轮只设计引用方式，不查询 saved records，不重建 aggregate，不新增数据库 migration。

## 8. Python、测试与配置能力

[`pyproject.toml`](../../pyproject.toml) 与 `.python-version` 指定 Python 3.12，
已有 Pydantic 2、NumPy、scikit-learn、PyYAML，dev 环境已有 pytest、ruff、mypy；
`uv.lock` 和 `backend/constraints-ci.txt` 提供依赖版本依据。
项目 pytest 默认 `testpaths=["backend/tests"]`、`pythonpath=["."]`，注册 unit/contract/golden
和 PostgreSQL 等执行 markers；ruff 覆盖 E/F/I/UP/B/ASYNC，mypy strict。
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 有静态检查、单元/合同、隔离数据库与
canary 分片；源码存在不等于本 R1 已运行这些 CI 或任一生产验收。

复用建议是：独立 `research/` 下标准库 JSON/datetime/hashlib/argparse 校验器与 pytest，
按显式新测试路径运行，避免默认 testpaths 漏跑 research 测试；使用新 synthetic fixture，
不导入数据库、模型训练或 forecast application。JSON Schema 所支持关键字及验证方式须写清，
不能因为输出 Schema 文件就宣称所有 JSON Schema 语义已被自动检查。
当前主依赖没有 YOLO/Ultralytics、PyTorch/torchvision 等视觉训练栈；本轮无需新增重量级框架。
future 框架、GPU、权重许可和预训练来源须在单独实验授权后选择与锁定。

## 9. 阶段清单与审计结论

| 状态 | 项目 |
| --- | --- |
| 已具备（代码/合同层） | Python、pytest、配置与类型检查；append-only/幂等导入模式；canonical identity/snapshot/hash；时间可用性过滤；历史数量误差和 completeness；FI exact-run 引用结构。 |
| 已设计但未实现生产接入 | R0 独立视觉数据域、采集与版本化方向；R1 的 VisionObservation、离线 manifest/split 校验与未来实验协议由本轮其他交付给出，不新增生产接口或表。 |
| 缺少真实数据证据 | 已获授权图像/视频、独立人工 box/mask/成熟标签、近重复组复核、完整独立测试集、采样覆盖率、图像与独立称重的标定。此次不盘点私有数据，真实存在性/可访问性=`NOT_VERIFIED_NOT_ACCESSED`。 |
| 需要业务确认 | 首个检测/计数/成熟任务、观察单位、可见果/隐藏果边界、成熟分级口径、权威 Base/品种映射、数据 owner/许可、设备/采样计划、主要指标和上线前阈值。 |
| 后续需要单独授权 | 真实采集/访问/上传、标注服务、独立称重或历史 label 读取、框架/权重下载、训练/调参、独立测试解封、视觉数量代理与面积预测对照、任何生产集成/迁移/部署。 |

结论：仓库具备可复用的数值预测研发工程基础与治理模式，尚不能据此宣称拥有视觉训练标签、
图像许可、视觉模型、视觉准确率或 count→kg 标定。首轮实验建议先围绕已授权样方的
可见蓝莓检测和人工计数建立独立数据链，再用同一封存测试集评估实例分割是否有增益；
成熟分级与重量预测需要分别完成业务标签和独立标定门禁。
本轮成果的准确称谓是“视觉算法工程准备”，不是“视觉模型开发完成”。
