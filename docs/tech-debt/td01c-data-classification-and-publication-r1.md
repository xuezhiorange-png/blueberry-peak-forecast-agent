# TD-01C：公开代码、私有真实数据与独立合成样本

TASK_ID：`BLUEBERRY_TECH_DEBT_TD01C_DATA_DESENSITIZATION_AND_HISTORY_MIGRATION_PREP_R1`。
本轮 Owner 确认数据权属，选择 `PUBLIC_CODE_PRIVATE_REAL_DATA`；不授权读取或公开
真实 XLS，不授权真实历史重写、强推、Tag/Release/可见性变更、Ready、Merge 或部署。
这项当前决定不是对历史公开发布行为的追溯签名或许可，不回写 TD-01B 历史快照。

基线为 `aeb6cad797d8e45e9520753f5f065311d106c4dd`，PR #776 已合并。
前置 main CI `41185755357` 开始时仍在运行；最终结果在 PR/交付回执中远程核实。
本轮仅新增组件、测试、公开文字的路径级登记及独立合成产物，既有解析器、预测、
标签、权限、数据库、模型和冻结证据保持原字节。

## 字段与两种数据产品

字段依据 [已有导入声明](../04_historical_import.md) 和
`backend/app/etl/history/schemas.py::EXPECTED_HEADERS`，不代表本任务重新核验了
真实 XLS 的 Sheet、表头或单元格。旧 Task2 的月份/品级规则不推广到其他预测族。

| 字段 | 私有真实产品 | 公开合成产品 |
| --- | --- | --- |
| 时间 | 原业务日期及原精度不变 | 虚构 2039–2040 / 2040–2041 产季，业务日为2040/2041年1月 |
| 链路 | 原关联不变 | `SYNTHETIC_LINK_*` |
| 农场 | 原名称、身份与空间关系不变 | `SYNTHETIC_FARM_*` |
| 分场 | 原 farm/subfarm/season 关系不变 | 显式关联到虚构农场的 `SYNTHETIC_FARM_*_SUB_*` |
| 品种 | 原品种及记录关系不变 | `SYNTHETIC_VARIETY_*` |
| 果径 | 原分级及异常不变 | `SYNTHETIC_GRADE_*`，含人工声明的排除等级 |
| 入库公斤数 | 原 Decimal 重量、缺失、零和负量语义不变 | 独立固定种子生成的六位小数 kg，保留合成质量异常 |
| 加工厂 | 原加工厂与供应关系不变 | `SYNTHETIC_FACTORY_*`，只关联虚构农场 |

文件名、Sheet、业务编号、坐标、面积、供应关系、作者、批注、链接、精确总量与
逐日曲线同样是披露面。本公开产品不带坐标/面积/真实业务编号，不从真实曲线
更名、平移日期或乘系数生成。真实数据的脱敏导出不是本组件的第三种模式，未来
须单独评估和授权；伪匿名化不能保证无法重新识别。

私有真实产品仅有保留规则，**本轮没有实现读取、修改或公开它的入口**。其训练、
回测、预测仍各自需要原有来源准入、时点、标签和执行许可。不得为了公开展示
修改正式训练源、原始质量异常或历史可见时间。

## 可执行的合成出口及拦截

```bash
python -m backend.app.etl.history.synthetic_publication generate \
  --seed 41 --output-dir /tmp/SYNTHETIC_ONLY-td01c-new
python -m backend.app.etl.history.synthetic_migration
```

生成器只接收有界整数种子，没有工作簿输入选项。Python 接口对任何 `source_path`
或非生成策略在 `exists/open/hash` 前拒绝：`REAL_SOURCE_READ_NOT_AUTHORIZED`。
将真实来源改名、标成 SYNTHETIC_ONLY 或声称文件已获许可也不会开启读取。

公开 Package 是完整独立生成结果；校验重新从种子生成并逐项相等比较。更改身份、
真实日期、重量、关联、来源身份、质量标记或添加字段，不能靠一个标签放行。
CSV/XLSX 校验还逐单元格绑定同一合成产季，无法展示文件 A 却用其他记录作为证明。
复用原有 `normalize_text`、日期/重量解析和业务指纹；不复用真实别名或成员映射。
使用局部 RNG，不改变其他研究模块的随机数状态。

XLSX 从空工作簿建立，只允许一个可见 `SYNTHETIC_ONLY` Sheet 和九个预期 ZIP
成员；拒绝隐藏 Sheet、批注、公式、超链接、外部关系、宏、额外成员及额外文档
属性。作者与最后修改者固定为 SYNTHETIC_ONLY；文件属性的2000年时间仅是虚构
打包常量，绝不是业务 recorded_at / available_at / 历史签发时间。
ZIP 顺序/时间、XML 属性时间和六位 kg 确定化，不复制原工作簿的容器、Sheet 或属性。

同目录输出两个产季各自的 CSV/XLSX 及 `SYNTHETIC_ONLY-manifest.json`。
CSV保留原声明的八列表头，产季、数据类、生成来源、逐行质量原因和文件 Hash 由
Manifest 绑定；缺失为空，不补0。文件只写到新目录，默认目录0700/文件0600，
已有目录拒绝覆盖。可复算样例在 [独立合成目录](td01c-synthetic-example/)。

`require_usage` 只允许 TEST/DEMO，拒绝 TRAINING / FORMAL_FORECAST /
REAL_SCORING / AUTHORITY。它没有接入现有来源 Catalog、导入数据库或正式预测
入口；样本不具备 SOURCE_002 或 Legacy 权威身份。将来增加连接也不能跳过原有
真实来源门禁。此限制是本产品的准入边界，不是对任意外部程序的通用防篡改保证。

## 公开衍生披露面的登记

本次审查当前已追踪公开文字，不读真实原始工作簿，不解压来源分区。
[登记表](td01c-public-derived-risk-register.csv)覆盖 Base/Farm/Factory 相关身份、
坐标/成员关系、重量/面积/商业统计、逐日曲线以及来源校验/链路等候选披露面。
[审查摘要](td01c-public-derived-audit-summary.json)记录扫描范围、清单 Hash 和限制。

共审查2,768个公开文本文件，形成1,658个候选路径（含5个只核对 Git 元数据的
压缩资产）。七个大文本采用流式检查，不输出原始文本。字段名命中可能只是
Schema、代码或合成夹具，**不是确认存在真实业务数据或确认泄露**；未命中也不是
公开安全证明。历史 Hash 是定位元数据，不自动构成发布授权。

优先由 Owner 确认以下对象，而非批量删改：

- `configs/factory_aliases.yaml`、`configs/base_registry_s1.json`、
  `configs/v0_5_base_reference_registry_v1.json`：业务名称、地理与关联的公开边界。
- `configs/production_plan.yaml`、V0.8 面积/训练来源配置：面积、成员与源身份的边界。
- `docs/v0-8/`、`docs/v0-15/`、`docs/v0-19/` 中研究结果与 JSON：精确统计、曲线、
  公开成员与私有产物关系；已有实验事实不能编造或重新计算以隐藏信息。
- `backend/tests/fixtures/s3_a2_official_s2_partitions/*.content.gz`：只核对路径和
  Blob ID，未解压，需分别确认来源身份和公开许可；不能当成两份 Legacy XLS。

原有文件及已冻结结果均未修改。若未来需调整公开披露，应保留私有原证据，
另建版本化公开表达并单独批准历史/Tag/Release处置，不能修改旧评分成绩或 Hash。

## 预测基座与验收边界

Legacy 声明的到厂/入库 kg、田间采收量、SOURCE_002 称重净重不自动等价。
公开样例的 `SYNTHETIC_DECLARED_LEGACY_RECEIPT_KG` 只描述合成字段，不能用于
证明任意真实来源的物理口径。训练/验证/封存测试边界、未知面积、业务零与缺失、
as-issued 天气和事后再分析、cutoff/PIT、原模型参数和历史评分全部保留。
本轮不训练、不调参、不评分、不启动 V0.22，`STRICT_PIT_VALIDATED=false`。

专项测试实际验证跨进程字节一致性、敏感内容与伪来源拦截、工作簿元数据、
质量异常及合成历史迁移。Ruff/Format/strict Mypy、Golden、四分片 Canary、
PostgreSQL、frontend 和 exact-head CI 的真实结果以最终 PR/交付回执为准。
合成验证不证明真实数据已脱敏、历史已清除或真实预测精度改善。
