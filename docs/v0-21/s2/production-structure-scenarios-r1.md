# V0.21 S2 — 生产结构变化与合成场景

TASK_ID=V0_21_S2_PRODUCTION_STRUCTURE_CHANGE_AND_SYNTHETIC_SCENARIOS_R1

本次 Owner 只授权 S2。基线 `8376a737443299aae84dec473c8710d93719334a` 已合并 S1 #763；对应 main CI [40519361402](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40519361402) 为 SUCCESS。S0 的原始未授权快照不改，新授权范围登记在 [S2 证据](../evidence/v0.21-s2-structure-scenarios-r1.json)。不实施 S3/S4，不读取真实数据、不训练或调整预测。

## 复用与新增

`backend/research/v021_structure_scenarios.py::prepare(s1_result, declarations)` 是纯 Python 计算入口。它用现有 S1 `prepare()` 独立复现输入结果，验证整个 S1 内容，不只相信其自填 Hash；随后直接读取其中的原始 V020Package 面积记录。完整成员、日期区间、时钟、修订图及规范化 Hash 均复用 S1，无 Excel 解析器、数据库、模型或新事件本体。

已有 V0.20 生产代码导出的原 18/36/36 合成包也在测试中直接消费，不重封包、不改地块权威。业务样例另由公开 synthetic fixture 生成同结构记录：3 Base、2 产季、8 成员、24 面积记录、4 条明确跨季关联。S1 的六个周期和时间特征保持原样。

## 输入及可比性

输入是一个显式 SYNTHETIC_TEST_FIXTURE 的 S1 结果 JSON，以及版本化 `V0_21_S2_DECLARATIONS_R1` 研究侧声明。后者明确业务时区、S1 身份、连续性、评估日、可选换苗/密度记录及场景成员。时区必须与 S1 origin 一致；不能默认 UTC 或用公历固定日期当周期起点。

- 连续性须提供前后成员、前后物理实体身份、来源和版本。成员继承完整 Base/Farm/Subfarm/Plot/Variety/Season/Production System 身份。相同名称不证明同一实体；实体变化、跨基地/地块/制度或无证据关系不产生正式变化率。
- CONTINUING_MEMBER 在同品种、同单位、同面积口径内比较。VARIETY_REPLACEMENT 输出退出、进入；ENTRY/EXIT 必须明确声明，不通过缺行推断，不以不同品种面积差冒充趋势。
- 各季用明确评估日选择合法有效区间；不自动选最后一条、最大值或最有利记录。非重叠有效期可以正常变化，重叠/多来源冲突、修订分叉、缺前序和上游 ERROR 保留并阻断。原始 `AREA_INTERVAL_CONFLICT`、`AREA_BASIS_CONFLICT`、日期精度、单位、来源及修订均不改。
- 不自动求多个地块、不同评估日或不完整成员的“基地总面积”。输出逐成员、逐季明细，避免重复面积和缺口被总数遮蔽。

三个轴分别报告状态：面积与连续性、密度、换苗。`COMPARABLE` 是对应轴的合成结构可比性；`NOT_COMPARABLE` 表示已识别的身份/口径冲突，`NOT_PROVEN` 表示材料不足。面积比较的 `status_scope` 明确为 `AREA_COMPARISON_AND_MEMBER_CONTINUITY_ONLY`。密度或换苗缺失不会伪造结果，也不会抹掉独立合法的面积描述；场景汇总按轴列数，不能当作统一授权或模型就绪结论。

## 数量计算

PLANTED、PRODUCTIVE、EFFECTIVE 分开：`delta_mu=next_mu-previous_mu`，`relative_change_ratio=delta_mu/previous_mu`。前值为明确 0 时保留绝对差，比例为 null、原因为 ZERO_PREVIOUS_AREA；缺失不是 0。只计算显式 mu，不猜换算未知单位。

密度仅使用明确同一成员/株群的植株数量、对应测量面积、面积口径、单位、方法、有效日期和来源。`plants_per_mu=plant_count/measured_area_mu`，分母必须正数；跨季密度还要求株群、方法、测量面积口径一致。株群或方法不同保留不可比原因。未知换苗不等于未换苗，PLANNED/OBSERVED/UNKNOWN 保持分离。

所有权威算术用 Decimal，独立 precision=50、ROUND_HALF_EVEN，不受调用方全局 Decimal 配置影响。数值展示六位；密度差和比例使用展示舍入之前的计算值。原始数值和精度完整保留；不以显示字符串再计算。比例是 ratio，不是百分数；例如 0.2 表示 20%。不生成产量系数、峰日偏移或预测优劣。

## 时间和来源

`comparisons` 是事后历史描述，不是 origin 特征。`origin_snapshots` 另行检查成员关系、连续性证明、面积、密度、换苗和修订在 cutoff 前的可见性；观测业务区间必须结束于 D 前，评估日也需早于 D。observed_at、recorded_at、known_at 各自验证，不代填。仅有业务日或无来源时钟证明不能通过 as-of 检查。

已证明晚到的修订，以及 D 当日/未来事实，在历史快照计算前排除；已可见坏修订会阻断，不能退回有利旧值。原始账本不会整体充当特征。面积时间判定逐条记入 `visibility_ledger`，不混入快照业务 Hash；完整输入/账本身份另行保留。未来数据变化可以改变完整审计 Hash，但不能改变过去合法快照的特征 Hash。

SYNTHETIC 时钟和来源声明不是真实业务权威。所有输出始终 STRICT_PIT_VALIDATED=false、REAL_SOURCE_AUTHORITY_PROVEN=false、MODEL_USE_AUTHORIZED=false；不得据此启动真实读取、模型或评分。

## 独立运行

在仓库根目录使用 Python 3.12；以下目录必须尚不存在，输入和旧输出不覆盖。

```sh
python -m backend.tests.agronomic_history.v0_21_structure_fixture \
  --scenario BUSINESS_EXAMPLE --output /tmp/SYNTHETIC-v021-s2-input-new
python -m backend.research.v021_structure_scenarios \
  --s1 /tmp/SYNTHETIC-v021-s2-input-new/s1-cycle-features.json \
  --declarations /tmp/SYNTHETIC-v021-s2-input-new/structure-declarations.json \
  --output /tmp/SYNTHETIC-v021-s2-output-new
```

输出 `structure-scenarios.json`（全量结果和原因）、`area-changes.csv`（面积业务表）、`manifest.json`（实际运行时间、源码和显式输入文件 Hash）。业务结果不含机器时间或临时路径，重复进程一致；运行时间单独记录。输出目录0700、文件0600。CLI 不自动找输入，真实类别在读取 S1 文件之前拒绝；不联网、不查库、不执行预测。CSV 的文本列防公式注入，负面积差仍是正常数字。

## 实际合成算例

[完整输入和结果](examples/business-r1/) 已由上述程序生成，没有硬编码结果返回。

| 成员/面积口径 | 2023–2024 | 2024–2025 | 差量 | 比例 |
| --- | ---: | ---: | ---: | ---: |
| SYN-LINK-0 / PLANTED | 100亩 | 120亩 | +20亩 | 0.2 |
| SYN-LINK-0 / PRODUCTIVE | 60亩 | 50亩 | −10亩 | −1/6 |
| SYN-LINK-0 / EFFECTIVE | 50亩 | 45亩 | −5亩 | −0.1 |

SYN-LINK-1 声明 2024-08-05 从 SYN-OLD-COHORT 换为 SYN-NEW-COHORT。SYN-LINK-2 的完整计数从10000株/50亩变为15000株/50亩，即200→300株/亩，差100株/亩、比例0.5。四成员面积可比；只有一个成员具备密度证明、一个具备换苗证明，其余对应轴为 NOT_PROVEN，而非“确认没有变化”。

预定15场景：不变、面积增/减、三口径不同步、品种替换、换苗、密度变化、制度不同、连续性未知、有效期冲突、零前值、缺面积、单位不符、同名不同实体和组合业务样例。输入事实在 fixture 中固定，预期值在正反测试中直接声明，不看计算或预测成绩再选情景。

测试还覆盖：D/未来扰动、合法D−1修订、晚到修订、密度舍入、跨午夜时区、月/年精度、计划换苗、原包互操作及跨独立进程确定性。新授权只到 S2；S3/S4、真实数据、模型训练/晋级、Ready/Merge/Tag/Release/Deploy 均未授权。
