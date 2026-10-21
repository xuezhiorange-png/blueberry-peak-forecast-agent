# V0.19 S3：历史回放协议及 C0 准入审批包 R1（待批准）

TASK_ID=V0_19_S3_RETROSPECTIVE_PROTOCOL_AND_C0_APPROVAL_PACKAGE_R1

审查基线：`3298b9c8daefc3dbc51b99954baaaa713353271c`；PR #745 已合并，
对应 main CI [39606948456](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/39606948456)
为 completed/success。本包仅新增协议、审批合同和离线一致性测试，不执行研究。
完整交付 HEAD 和本 PR exact-head CI 在 GitHub 回执中记录，不用旧 main CI 替代。

## 1. Owner 本次需要决定什么

以下每一项目前均为 **NOT_APPROVED**。本任务的开发授权、文档合并、文件 Hash
匹配或 CI 通过，都不构成以下决定。决定须记录 Owner 身份、时间、精确包版本、
成员及输入 Hash、范围、限制接受和可核验的 GitHub/受控私有决定来源。
后续批准应建立新版本记录，不回写本提案或历史 R1/R2。

| 决定 ID | 需批准的内容 | 本次状态 |
| --- | --- | --- |
| PROTOCOL | 仅限本季/来源/Fold B 的跨来源事后条件研究；明确接受非严格 PIT、训练标签口径未等价及面积 known_at 未证明 | 待决定 |
| FORMAL_C0 | 审核精确 H7/H15 私有成员清单、39 Base 的 80 农场边界、完整性规则、排除及输入/成员 seal；批准实际成员数而不是结构上限 | 待决定；正式 C0=0 |
| A_INPUT_READ | 指定只读 Profile、Registry、候选清单及不含重量的成员/面积/日期 metadata；限定路径和版本，不开放标签 | 待决定；既有核验权限不等于执行权限 |
| A_EXECUTION | 在指定隔离环境执行固定代码、参数和完整 support，保存真实重算时间，零标签访问 | 待决定；当前入口无条件拒绝 |
| A_SEAL_REVIEW | 独立复核完整预测封存、失败清单、权限及运行审计，确认阶段 B 可使用的唯一封存版本 | 尚未生成，无法批准 |
| B_LABEL_READ | 阶段 A 封存复审后，另行授权精确 SOURCE_002 标签快照、成员、日期、用途和留存 | 待决定；本包不读标签 |
| B_SCORING | 独立授权十指标、共同 Cm、不可计算处理和全部结果公开规则，不选赢家/不调参 | 待决定；本包不评分 |
| INDEPENDENT_REVIEWED_RESEARCH_IMPLEMENTATION | 若研究协议获批，未来单独审查可执行研究路径；不能靠 JSON 布尔值或改名绕过严格评分器 | 尚未批准或实施 |

阶段 B 不因阶段 A 成功自动获批；任何一步均不包含训练、模型晋级、生产部署或 S3 完成。

## 2. 实验身份与现行协议的关系

`RETROSPECTIVE_REPLAY`、`EXPOSED_HISTORICAL_BENCHMARK`、`STRICT_PIT=false`、
`PRODUCTION_ELIGIBLE=false`。比较问题仅为：**同一冻结历史 profile 下，两种日曲线
处理方法相对于 SOURCE_002 商品果净重标签的条件表现**。不是历史提前签发的准确率。

现行 `v019_synthetic_validation.py` 要求签发及 cutoff 早于目标开始，并仅开放合成
执行。事后重算不能满足历史签发证据，本提案不修改、关闭或调用其真实评分旁路。
原严格路径继续拒绝晚签发；真实研究路径仍不存在可获本包启用的开关。
未来即使 Owner 接受研究限制，仍须单独实施/审核合法的独立研究路径后才能执行。
不得将协议批准当作已修改门禁，不得将回放成绩贴到 AS_ISSUED_FORECAST 对照上。

## 3. 成员边界及固定输入

范围版本 `V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1`；2025–2026，目标日期
2025-08-05—2026-04-15。39 Base、80 个纳入来源农场、4 个研究排除、研究内未解决=0。
这是已合并适配器的研究映射状态，不更改 V0.8 全局身份权威。

| Owner 精确追加归属 | Registry 身份 |
| --- | --- |
| 文山古木农场、文山喜古农场、文山马塘农场 | `base_ffdc1ebe359436aa3f0fa834` / 砚山盘龙基地 |
| 大理巍山农场（WRM) | `base_f10df3ac242e4dbbf6c20b98` / 大理巍山基地 |
| 弥勒朋普农场（MYM） | `base_c51783e2ec7c16bba447d64e` / 弥勒朋普基地 |

`盘龙基地` 不是可替代的模糊身份。其余 75 个农场必须逐条依已封存精确映射，
不根据名称猜测。嘉果莓森、曲靖师宗农场、格莱莓农场、老挝巴松一场仅排除本次研究；
不删数据、不改变其公司归属或全局未解决身份、不把排除行重量分摊到其他 Base。

本包**不复制私有逐行清单、不重新验证私有文件、不打开原始重量**。机器合同引用
现有清单/metadata 的完整 SHA256；实际 39 Base 名册及 80 农场逐条连接保留在受控
metadata，不能由本包的计数重建或冒充。正式 C0 审批必须读取获准的精确清单并核对
其所有成员身份、成员 Hash、面积行 Hash 和日级完整性，而不是只批准下表总数。

| 对象 | 文件/身份 SHA256（对象身份，不是许可） |
| --- | --- |
| SOURCE_002 原件身份，仅引用、不作为 A 输入 | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| reference-B.json | `a0a5cbc3c3ca5bd2b0b8860328eee73840499b38da89c11a104f83d02fd77c5b` |
| base-registry-v1.json | `502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904` |
| Registry payload | `d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293` |
| Owner 研究决定 | `7d15f85752bc57e3facc4d912aa1d89e3c1ce7e61ee85c52b432cfc8af952bf2` |
| owner-scope-metadata-r2.json | `bc1248835055c2488f9d5fa29351ef3d3605f3c91b36539f4c236f1ca584e572` |
| h7-candidates.csv | `fc047941cda320d12f5b4bc913cf5585ccbcae508f73e976b557c83a8892abea` |
| h15-candidates.csv | `699f75d7543bbe2ef9bd0c8c991ada3bf2d61bc0c9cea2fed02790f35b5e281f` |

## 4. C0 候选清单、日历和阻断项

| 分层 | origin 本地日期闭区间 | target 规则 | 候选数 | 当前准入 |
| --- | --- | --- | ---: | --- |
| H7_PREFIX | 2025-08-04—2026-04-08 | D1..D7 | 39×248=9,672 | C0_CANDIDATE_ONLY |
| H15_LOCAL | 2025-08-04—2026-03-31 | D1..D15 | 39×240=9,360 | C0_CANDIDATE_ONLY |
| FULL_SEASON | 不登记 | 不外推、不拼接 origin | 0 | 不准入 |

origin+1 天是 target_start，origin+horizon 是 target_end；连续本地业务日，
`Asia/Shanghai`。254 个目标日构成 9,906 Base×日；既有审查记录为 6,416 observed、
3,490 authorized zero。三个基地的 17/14/14 个零转有记录变化已由新适配器逐项验证，
不能套用旧 75/9 metadata 或旧零值结论。此处引用既有来源，不声称本轮重新查验。
业务规则完整不证明每次田间采收都被扫码；无记录不是天然为零。04-16 不纳入。

精确候选 CSV 字段沿用适配器：candidate_id、base_id、season、window、origin_date、
target_start/end、target_dates_sha256、day_authority_sha256、status。
candidate_id 再绑定 Source、Owner 决定、Base 成员、历史面积行 Hash；排序按
base_id/origin_date，拒绝重复/缺失/额外成员。H7/H15 分开封存，不合并计算覆盖率。

正式审批清单须检查：五个文件身份、39 Base 精确身份与亩面积版本、80 农场的逐 Base
成员完整性、研究排除边界、日历/零值来源、原始候选 CSV Hash 和规范化成员 Hash、
全部缺失/失败/排除理由、比较 family/source/train/evaluation scope，最后批准专属
正式 C0 seal。原候选对象保持原字节；正式审批建立关联的新 seal，不改旧文件 status。
本包未生成该正式 seal，其值为 null，正式 C0=0。

| 阻断/限制 | 本次状态与处理 |
| --- | --- |
| 私有成员精确名册审批 | 引用已封存对象；尚无本包正式 C0 决定，计数不能替代成员审核 |
| 训练来源与 SOURCE_002 物理口径等价 | NOT_PROVEN；仅可申请跨来源条件研究，不变成同口径精度证据 |
| 历史面积 known_at、预测真实发行时点 | NOT_PROVEN；保留回溯确认身份，不改为严格 PIT |
| origin 时刻及 cutoff | 现有清单仅日期，NOT_REGISTERED；执行前审批 timezone-aware 研究截止语义，不能推断历史发行 |
| 产季全量完整性 | 未申请；SEASON_TOTAL_WAPE 不可计算 |
| A/B 执行与输入读取权限 | 分别待批准；既有只读核验授权不自动扩大为预测或评分 |
| 可执行真实研究实现及封存复审 | 尚未批准；既有无条件拒绝保持不变 |

## 5. 阶段 A：生成与封存（未来另行授权）

仅允许显式路径上的 Profile、Registry、C0 和无标签 metadata。禁止文件自动发现、
SOURCE_002 原始表、重量列、标签 reader、业务数据库和跨阶段共享标签缓存。
适配器先验证 Hash、Schema、scope、日期、亩面积和成员版本；任何漂移停止，
不能自动换文件、补零、删失败成员或换 profile。

固定 Fold B，基线 `AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`，唯一候选
`BIN_CENTER_LINEAR_PER_BIN_MASS_V1`。每 Base 使用相同完整 support：
2025-07-01—2026-04-15，产季锚点 07-01；先生成完整确定性日曲线，再截 H7/H15。
按原始季节锚定分箱严格保持整数微 kg 质量，非负、六位 kg、最大余数并列最早日期，
不得对局部窗口重归一化。baseline/candidate 共享 Base、面积、profile、origin、
cutoff、support 和来源，只允许已冻结曲线处理方法不同。不训练、不拟合、不调参。

实际 executed_at 用带时区 UTC 真实时间；origin/cutoff 是待批准的研究模拟时间语义，
与执行时间分列，历史 issued_at 证据未知则保持未知，禁止倒填。相同输入的预测
内容 Hash 应一致；包含真实 executed_at 的每次运行封存 Hash 可以不同，不伪造
时钟来制造整份报告相同。重跑不能按较好结果挑版本，失败运行同样登记。

输出合同（提案，不是已生成产物）：注册 C0 的每个成员均有成功/失败记录、完整身份、
原始输入/源码 commit 与 Blob SHA256、方法配置、完整 support 曲线及窗口切片、
日期/单位/Decimal 字符串、实际时间、权限来源、日志摘要及 Hash。失败保留原原因，
不抹去分母。先写新私有目录（0700、文件0600），不覆盖旧文件、不提交业务行；
独立复核完成后才开放 B。意外标签访问必须中止并保留事件，不继续评分。

## 6. 阶段 B：独立标签读取与评分（未来另行授权）

在 A seal 已复审且 B_LABEL_READ/B_SCORING 独立获批后，验证真实封存和精确 C0，
再在隔离评分环境打开指定 Source 标签。核对标签来源、成熟/完整性、单位、Base、
日期和日级零值权威。任何 seal/成员漂移、缺权限、来源不明、未批准物理口径或时间
限制直接 BLOCKED；不靠数值相似推断权威，不悄悄转成严格 PIT 或 AS_ISSUED。
当前程序没有这条获准的真实评分路径，本包不能作为调用许可。

严格复用 S1 十指标定义、分子分母、Decimal precision=50、最早并列、全零和缺日规则。
机器合同逐字保存原 S1 metrics 对象并用固定历史 Git 字节比对；不重写评分器。
SEASON_TOTAL_WAPE 保持 NOT_COMPUTABLE_NOT_ADMITTED。H7/H15 分别报告；H7
只有一个 rolling7 窗口，峰起点不具有 H15 的区分力；H15 只有 D1..D9 共九个起点。

逐指标固定共同可计算 Cm，双方使用同一 Cm，报告 C0→Cm 成员 Hash、候选/有效/失败
计数、原因、Base/日期覆盖、分子分母、改善/持平/退化。零 actual 不从数量误差删去；
全零 actual 的峰日期不可计算；缺日不补零。重叠 origin 不当成独立样本，不跨窗口、
产季、来源、训练范围或 comparison_family 静默汇总。可保留合法跨 Base 配对报告，
但物理/来源/成员范围必须预注册。完整保留不改善和 MIXED 结果，不定自动 winner。
沿用 S1 预注册诊断，不事后搜参数、选最优 Base 或修改 C0。

## 7. 封存合同、测试和交付边界

UTF-8 canonical JSON：sort_keys、indent=2、ensure_ascii=false、allow_nan=false、末尾 LF；
所有 Decimal 用字符串、日期用 ISO。SHA256 仅证明字节身份，不是签名、可信时间或授权。
正式审批和执行时须保存决定来源及审查者；Codex 自测不等于独立接受。

本轮离线测试检查协议/Markdown Hash、固定历史来源 Git Blob、候选数量和 origin、
八项独立未批决定、严格门禁及 S1 十指标；负向覆盖授权伪造、C0 自动提升、物理/PIT
漂白、按重量/误差筛选、窗口重归一化、历史对象缺失/Hash 漂移等。测试不打开私有文件、
不生成曲线、不计算任何真实误差。最初 test-first RED 是新 JSON 尚不存在，不是生产缺陷。
当前源码历史证明固定到本包基线提交，不把未来合法工作树变化误判为历史篡改；
未来执行时仍须另核对实际运行代码身份，不能拿旧代码 Hash 代替新执行验收。

`RETROSPECTIVE_PROTOCOL_EFFECTIVE=false`；`FORMALLY_ADMITTED_C0_COUNT=0`；
`REAL_PREDICTION_AUTHORIZED=false`；`REAL_SCORING_AUTHORIZED=false`；
`REAL_PREDICTION_GENERATED=false`；`REAL_SCORING_PERFORMED=false`；
`S3_FORMAL_COMPLETE=false`。不 Ready、Merge、Deploy，不宣布生产准确率或模型升级。
