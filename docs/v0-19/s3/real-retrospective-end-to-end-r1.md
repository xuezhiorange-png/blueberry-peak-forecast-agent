# V0.19 S3：真实结构历史研究执行引擎 R1

TASK_ID=V0_19_S3_REAL_RETROSPECTIVE_END_TO_END_R1

基线 main：`25af506d2b2f9b6f18c0965351acc9a7ad3db65a`，已合并 #748。
本次新增真实结构文件接口、完整 C0 管理、A/B 引擎和报告生成器；不改原算法、
严格 PIT 评分器、冻结文件、数据库、依赖或 CI。不是又一份审批文档交付。

## 1. 同一计算链路，不再限于四个硬编码基地

```sh
# 项目 Python 3.12 环境、仓库根目录；目录必须不存在。
python -m backend.tests.area_yield.run_v019_real_shape_demo \
  --output /tmp/SYNTHETIC-v019-real-shape-unique
```

该命令生成完全合成但结构等价的 Profile、Registry、Owner scope metadata、
H7/H15 CSV 和独立标签文件，经实际文件适配、精确 C0 审核、合成签名准入、
独立进程 A、独立合成 seal 复核、独立进程 B，输出全基地 JSON/Markdown/HTML。
程序以真实 UTC 记录计算/评分完成时间；不回填历史签发时间。

| 模块 | 实现 |
| --- | --- |
| `v019_research_authorization.py` | Ed25519 决定校验；类型、角色、代码、阶段、对象 Hash、有效期和限制绑定 |
| `v019_research_cohort.py` | 显式路径及原始文件 Hash、原 Owner Scope Adapter 全结构校验、完整候选审核及正式 seal |
| `v019_research_execution.py` | 一基地一次完整 support、旧 Operational Peak 基线、唯一 S2 候选、窗口索引/峰值、完整输入及失败封存 |
| `v019_research_evaluation.py` | 验证 A 后才打开标签、S1 十指标共同集合、逐基地对照和完整报告 |
| `v019_research_cli.py` | prepare / formalize / stage-a / stage-b 独立进程入口 |

原 `v019_owner_scope_adapter` 的五个冻结文件身份与 `_review` 原样复用；
原 `v019_real_phase_a_adapter` 的限定文件读取、JSON/CSV 拒绝规则原样复用。
数值复用 Operational Peak 的 profile 加载及 `_daily_row`、S2 的 `generate_candidate`，
及既有 `v019_retrospective_scoring` / `v019_synthetic_validation` 的峰值与误差算术。
独立流式汇总器测试与既有数值引擎的十指标值、分子分母、覆盖和不可计算原因对照。
原 `v019_retrospective_engine` 的合成安全文件写入器继续用于合成输出。

## 2. 真正的文件与成员校验

输入 manifest 明确指定五份文件的绝对路径和 SHA256，不扫描目录、不自动选择版本。
REAL 使用原 Owner Scope Adapter 的固定 Hash；SYNTHETIC 使用独立合成身份和密钥域，
不修改全局常量，不把合成 Hash 冒充真实 Hash。

SYNTHETIC 只接受源码明确登记的五个虚构夹具字节身份，以及两个虚构标签版本
（完整、缺少末日）。五个输入必须与显式 manifest 同目录；标签必须处于该输入目录。
整个身份集合在数据文件读取前校验，A seal 快照重验也采用同一限制。
普通调用者不能把真实或重新编码的业务输入标为 SYNTHETIC 绕过真实执行门禁。
这不是针对任意本地恶意 Python 程序的系统沙箱；纯数学函数不是权限控制入口。

初始提交 `541748eaafc2331f45dbb3edc07f95d67fde00b4` 的自检发现该隔离不足：
伪造 SYNTHETIC manifest 填入真实固定 Hash 后，会尝试打开不存在的测试路径。
原始 RED 只使用虚构路径，没有读取私有文件或生成真实预测。
原始 JUnit SHA256 为 `febe3642bc3a76f856c175b853d46c346fad4dd9d53f693e14ef73749ea2ba43`。
初始 CI `39720815102` 保留，但不能代替此修正代码的验收。

复核 39 Base、80 纳入/4 排除、9,906 Base×日、6,416 observed/3,490 authorized zero，
以及三基地 17/14/14 的零转有记录变更。原身份、来源、亩面积、日期、授权零、
成员 Hash、窗口 Hash、缺失/重复/多余成员、标签字段注入等验证全部沿用。
不模糊匹配、不补零；元数据结构损坏直接拒绝整个输入，不悄悄抽取“好”子集。

完整 support=2025-07-01—2026-04-15；目标=2025-08-05—2026-04-15。
H7=9,672，H15=9,360 只是原始候选集，不是批准。C0 每个成员必须有 ADMIT 或
带原因的 REJECT；Owner 决定签署完整 review Hash。H7/H15 分别保留批准成员集合，
整体成员集合 Hash 和 review Hash 一并绑定，
未准入成员仍在审核和失败清单中。指标分母使用已准入 C0，并独立保留原始候选数及
非准入清单，不能把审核排除伪装成计算成功或隐去失败。

## 3. A/B 和签名决定边界

权限不是普通 `approved=true`：每份决定签署 kind、subject Hash、代码身份、
数据类别、时间范围和固定限制。FORMAL_C0 绑定具体完整 review；A_EXECUTION 绑定
formal seal；A_INPUT_READ 绑定精确 manifest 路径及字节 Hash；A_SEAL_REVIEW 绑定
A seal；B_LABEL_READ 绑定 A seal、精确标签路径/Hash；B_SCORING 绑定 A 和标签 Hash。

PROTOCOL、FORMAL_C0、A_INPUT_READ、A_EXECUTION、IMPLEMENTATION_REVIEW 分别验证；
B 还必须验证 A 的全部签名/输入/数值，独立 A_SEAL_REVIEW、B_LABEL_READ、B_SCORING。
Owner 与 Reviewer 信任公钥必须分离。签名过期、角色错误、代码变化、成员或
封存漂移均拒绝。阶段 A 不导入标签生成器、不打开 SOURCE_002；执行前及封存前
检查执行许可。B 在标签读取前和结果释放前检查独立许可。

**真实信任根当前为空。** REAL 模式不读取 CLI 的合成 root，也没有环境变量、
布尔值或复制 JSON 可启用。缺真实信任根时，在输入/C0/seal/标签文件读取前拒绝。
正式真实信任根及其来源、批准/撤销流程仍须另行 Owner 授权和独立审核；
本 PR 不创建真实签名密钥、不为真实成员签署决定。
合成夹具的两个临时密钥只是角色与接口测试，不是 Owner 签名或独立接受。

阶段 A 保存五个无标签文件的精确字节快照、manifest 身份、formal C0、代码/配置、
完整曲线、每个窗口 Hash/峰值、逐成员状态、全部失败和真实 executed_at。
B 无需重新打开原始输入，先从 seal 内复验全部字节 Hash、原适配器结构、C0 和
曲线复算，再打开明确批准的独立标签快照。即使重算普通 SHA256，也不能绕过
已签署的来源身份及独立 seal 复审。

真实标签接口接受有权威映射的独立 Base×日 kg 快照，不直接猜测 XLS 字段或
拼接原始重量。要求源 Hash、物理口径、单位、成熟时间及每行 day authority Hash。
缺行保持缺行；重复、非法量、未成熟/无权威、授权零与非零量冲突均保留不可计算。

## 4. 计算、确定性与报告

每个 Base 只在 289 日完整 support 计算一对曲线，再截 H7/H15；不按 origin 重算，
不对窗口归一化。输出六位 kg，严格季节锚定七日分箱质量守恒，首尾短箱按有效日期。
预测内容 Hash 不含实际执行时间，因此同输入复算相同；包含真实时间的运行 seal
允许不同，不能伪造时钟来制造整份封存相同。

报告保存十指标、各自共同成员及 Hash、分子分母、不可计算原因、39 Base 的
改善/持平/退化、完整逐日预测与实际量、每个窗口的预测/实际日峰及滚动七日峰。
H7/H15 分开；SEASON_TOTAL_WAPE 不可计算，本次不准入 FULL_SEASON。
全零 actual 进入数量误差，但不产生虚假峰日期命中。缺失预测/标签不缩短窗口。
原严格 PIT 路径不变，历史发行未知保持 null，不冒充 AS_ISSUED_FORECAST。

输出为新私有目录（0700）、文件（0600），拒绝覆盖旧目录。
`a/phase-a.json` 可在新进程独立加载；`b/report.json`、`report.md`、`report.html`
包含真实计算结果。HTML 为纯静态、转义后的可折叠表格，不依赖网络或前端计算。
`run-summary.json` 记录实际耗时、子进程峰值 RSS、数值例子和运行 Hash；
它是合成运行报告，不是实际业务准确率。

## 5. 不变的研究限制

2025–2026 仍是 EXPOSED_HISTORICAL_BENCHMARK，RETROSPECTIVE_REPLAY，STRICT_PIT=false。
训练来源与 SOURCE_002 物理口径等价、历史面积 known_at、历史真实发行时点仍未证明。
未来也只能比较冻结 profile 下两种曲线处理方法的条件表现，不证明生产准确率，
不训练、不调参、不晋级、不部署。原无条件拒绝的两个真实入口保持原样。

本次合成数据全部在程序内构造；未读取私有原件、实际采收重量或私有面积。
夹具保留原 Schema 中的公开来源/身份字段用于结构匹配，**不是实际文件来源验证**。
完整运行及数值样例的实际结果见同目录验收补充和本 PR exact-head CI 回执。

`FORMALLY_ADMITTED_C0_COUNT=0`，`REAL_PREDICTION_GENERATED=false`，
`REAL_SCORING_PERFORMED=false`，`MODEL_TRAINING_PERFORMED=false`，
`S3_FORMAL_COMPLETE=false`。保持 Draft，不 Ready、不 Merge、不 Deploy。
