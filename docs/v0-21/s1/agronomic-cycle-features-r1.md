# V0.21 S1 — 合成生产周期特征准备器

TASK_ID=V0_21_S1_AGRONOMIC_CYCLE_FEATURES_R1

本次 Owner 已明确授权 IMPLEMENT_S1_ONLY。执行基线 `0fe06ca320724d4067f573535f2b6be25ffafbc1` 已合并 S0；main push CI [40474901080](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40474901080) SUCCESS。新授权记在 [S1 证据](../evidence/v0.21-s1-cycle-features-r1.json)，S0 历史授权快照保持原样。

## 实际能力与输入

`backend/research/v021_cycle_features.py::prepare(package, declarations)` 是纯函数，不访问文件、网络、数据库或模型。模块的最小 CLI 仅打开两个显式指定的 JSON；没有路径发现、Excel 解析、真实数据读取或模型入口。

输入消费 V0.20 `V020Package` 核心结构，兼容其 `agronomic-preparation.json` 导出 envelope。校验 schema、包规范化 Hash、mapping Hash、固定 V0.20 vocabulary Hash、记录与独立合成时钟证明的 Hash 绑定；保留完整原包、record_id、scope、行/表/列、时间原文和精度、类型、状态、revision/supersedes 以及原始问题。未提供的 CSV/HTML 附件和原始 Excel 字节不会被打开；保留它们的声明身份，不声称这些未读取附件已独立复核。

只接受 `SYNTHETIC_TEST_FIXTURE`。这一离线测试合同不是来源鉴真、真实来源登记或执行授权；Hash 匹配和类型标签本身都不能证明真实数据权威。任意用户预览包不获准作为真实研究来源，真实接口/模型能力未接入。

合成 declarations 明确包含：

- `cycles`：每个 Base×season 的显式主周期及起点日期区间、独立合成时钟。两个不同主周期同时声明时不选一个，保留 AMBIGUOUS_PRIMARY_CYCLE。
- `members`：完整 Base/Farm/Subfarm/Plot/Variety/Season/Production System、cycle_id、关系可见时间、主剪枝 record 引用和已完成阶段的显式前后事实引用。缺失或 UNKNOWN 身份不合并。V0.20 的 `plot_authority_id=null` 保持 null，关系只属于合成演练。
- `origins`：显式 base、season、业务日期、业务时区和带时区 cutoff；cutoff 本地日必须等于 origin。没有成员的请求也留在 origin_requests，不静默消失。
- `record_clocks`：逐记录 Hash 绑定的三个独立时钟及 SYNTHETIC 证明引用。它们是额外的合成见证，不回填、改写原 V0.20 字段，更不将 source authority/PIT 状态升级为 true。

三个生产制度在成员明细与事实 family 中隔离。同一 Base 周期如含不同制度的显式成员，各成员分别计算，绝不合并它们的事件日、主剪枝或物候阶段。无促早记录不构成周期异常，未知促早方式不推断加温或休眠解除。

## 计算、修订与时点

周期起点按逐季声明使用，不固定年内日期、不选择第一条剪枝。每次剪枝均保留；唯一显式主剪枝引用才能形成 `days_since_primary_pruning`，缺失/多义时该特征 null。其他合法事件的时间特征可以独立保留。阶段间隔只来自显式同成员的 OBSERVED 事实对，不用计划或相同事实的两个版本凑成阶段。

已知日区间 `[a,b]` 的经过日范围为 `[D-b,D-a]`；阶段 A→B 为 `[B.lower-A.upper,B.upper-A.lower]`。使用实际 civil date 差，支持跨年和闰日。日精度单值、月/年合法区间分别输出；下上界相同且可见时才有 `value`。缺失和未知用 null+reason；次序反转或区间重叠导致阶段次序不明确时不伪造完成间隔。无时区本地时钟不假装可信时刻；timestamp 的业务日转换使用所声明时区。

OBSERVED 事实业务日或业务区间必须结束于 D 之前；D 当日及之后事实排除。观测、记录、可见三时钟分别验证为带时区、来源不冲突且顺序成立，不互相代填；然后调用现有 `pit.visibility.record_visible_at()`。成员关系、周期声明和修订同样需要在 cutoff 前可见。单纯日级 known_at 没有独立可信时刻证明时不可用；合成额外见证也只支持模拟 as-of，不证明真实历史 PIT。

修订按完整 scope、kind、source_reference、logical_id、宽表 slot 分组。先确定历史可见记录，再验证修订图，避免晚到修订反向污染旧 origin。重复版本、断链、循环、fork、可见状态冲突及可见坏 head 均保留并阻断，不悄悄回退旧值。主引用指向的同一事实有合法可见新版本时使用该版本；没有使用任意日期排序选 winner。

普通开花 `GENERIC_BLOOM:flowering_peak_date` 和 `PERCENT_BLOOM:BLOOM_50` 身份独立。PLANNED 输出在 `planned_events`，不成为观测经过日；UNKNOWN 不混入两者。未来采收、峰日、季末总量和未知原始列都不是特征输入。这里没有物候生物学推进或预测效果推断。

## 输出与两种 Hash

- `cycle_associations`、`association_ledger`：主周期与完整成员关系，含歧义/未匹配原因。
- `origin_snapshots`：成员的合法经过日、已完成阶段间隔、单列计划事件和来源关系。
- `record_ledger`、`origin_decisions`、`origin_requests`：原始事实、未关联、缺日期/方法/时间、未可见、修订冲突及失败请求；不会删除困难事实。
- `feature_sha256`：仅绑定该 origin 的业务特征、范围、cutoff 和独立计划通道。未来实际事实或晚到修订变化不能改变合法历史特征及此 Hash。
- `lineage_sha256`、`result_sha256`：绑定完整输入、原始记录、来源与证明。新的来源包即使只改未来事实，其审计身份仍应改变，不能伪称是同一原件。不是要求不同完整输入拥有同一个完整审计 Hash。

相同输入得到相同规范化业务结果和 result Hash。CLI 的真实执行时间、模块源码 SHA256 和输入文件字节 SHA256 另存 manifest，不回填历史时钟，也不参与确定性业务 Hash。输出要求新目录，已有结果不覆盖；目录 0700、文件 0600。

## 运行与已计算样例

从仓库根目录、已安装项目依赖的 Python 3.12：

```sh
python -m backend.tests.agronomic_history.v0_21_cycle_fixture \
  --output /tmp/SYNTHETIC-v021-s1-new-input
python -m backend.research.v021_cycle_features \
  --package /tmp/SYNTHETIC-v021-s1-new-input/synthetic-v020-package.json \
  --declarations /tmp/SYNTHETIC-v021-s1-new-input/synthetic-declarations.json \
  --output /tmp/SYNTHETIC-v021-s1-new-output
```

也可直接使用本目录 [examples/cycle-features-r1](examples/cycle-features-r1/) 的两个冻结输入；结果 `cycle-features.json` 与运行 `manifest.json` 在新的输出目录生成。测试夹具是明确的规范化结构等价 SYNTHETIC 数据，不冒称来自真实 Excel 或真实时间权威。

实际生成：3 个合成基地、2 个产季、6 个主周期、8 个成员 origin 快照、48 条完整保留的合成事实。一个基地两个地块/品种独立：

| 成员 | origin | 显式起点 | 距周期开始 | 距主剪枝 |
| --- | --- | --- | ---: | ---: |
| SYN-MEMBER-0-0-2023 | 2024-03-01 | 2023-08-20 | 194日 | 168日 |
| SYN-MEMBER-0-0-2024 | 2025-03-01 | 2024-09-10 | 172日 | 167日 |
| SYN-MEMBER-0-1-2023 | 2024-03-01 | 2023-08-20 | 194日 | 167日 |

第一成员普通盛花距 origin 为2日；其显式 BLOOM_50 也为2日，两者同日仅是夹具事实，不是语义等价。主剪枝至普通盛花间隔为166日。月精度起点 `2023-08` 在 `2024-03-01` 得到 `[183,213]` 日区间，value=null。无主剪枝输出 `PRIMARY_PRUNING_MISSING`；多个主引用为 `PRIMARY_PRUNING_AMBIGUOUS`。

另有真实 V0.20 生产代码互操作验收：原公开合成 XLSX 经原 `parsePreview` / `prepareV020` 输出原包 `V0_20-7ca546d45f6ce68f9a18d7ccad5b4c976eaab6e8d648510d2591aacd8d0d9e57`，S1 无需重解析即接收；原 18/36/36 及全部90条记录保留，生成4个主周期、6个成员快照。该静态公开合成包位于 `backend/tests/agronomic_history/fixtures/v0_21_original_v020_package.json`；没有修改旧前端功能或样例。

## 检查与边界

专项覆盖两个周期起点、跨年/闰日、完整成员隔离、三制度、主剪枝歧义、普通/百分比/计划/未知、日/月/年、时区边界、未来/D日/晚到修订扰动不变、合法D−1变化、修订fork/断链/循环、无证明时钟、来源Hash漂移、原包互操作以及两个独立进程输出一致。

S1 只完成合成特征准备；未读取真实农事或产量标签，未训练/重拟合/修改任何模型，未产生峰值评价或跨季面积/换苗/密植比较。S2–S4 未实现；没有新数据库、页面、MCP 或治理平台。STRICT_PIT_VALIDATED=false，AGRONOMIC_EFFECT_VALIDATED=false，PRODUCTION_FORECAST_CHANGE=false。本 Draft 交付不代表独立复审或正式版本收口；Ready/Merge/Tag/Release/Deploy 均未授权。
