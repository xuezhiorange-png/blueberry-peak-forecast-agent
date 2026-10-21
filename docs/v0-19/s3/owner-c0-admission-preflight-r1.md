# V0.19 S3 精确 C0 准入审核准备包 R1

状态：`C0_CANDIDATE_ONLY` / `PENDING_OWNER_C0_REVIEW`；正式 C0=0，正式 seal=null。
协议的受限 Owner 决定见 [登记 R1](owner-protocol-decision-r1.md)。本包不是正式成员批准。

## 1. 证据层级与对象清单

本轮仅使用已合并代码和已封存证据的身份、统计与校验规则；不重新打开私有清单、
Profile、Registry、采收重量或标签，不重新作数据对账。下列计数是 #745 已封存的
核验结果，不冒充本次重新逐成员查验。精确原件仅可在已获授权的受控 Manifest 中
按显式路径读取；缺路径、缺成员或 Hash 不符应 BLOCKED，不能扫描寻找或换版本。

| 审核对象 | 固定身份 / SHA256 | 下次所需验证 |
| --- | --- | --- |
| SOURCE_002，仅来源引用、不作为阶段 A 输入 | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` | 来源与批准研究范围一致，不打开重量来筛样本 |
| Fold B `reference-B.json` | `a0a5cbc3c3ca5bd2b0b8860328eee73840499b38da89c11a104f83d02fd77c5b` | profile/训练行集合/业务窗口，冻结不改 |
| `base-registry-v1.json` | `502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904` | 39 个精确 Base、版本、active 和亩面积 |
| Registry payload | `d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293` | 规范 payload 身份，不能用文件名代替 |
| `owner-scope-metadata-r2.json` | `bc1248835055c2488f9d5fa29351ef3d3605f3c91b36539f4c236f1ca584e572` | 80 成员逐 Base 连接、四排除、面积行 Hash、9,906 日级元数据 |
| H7 `h7-candidates.csv` | `fc047941cda320d12f5b4bc913cf5585ccbcae508f73e976b557c83a8892abea` | 精确 9,672 行及每行身份，不以计数代替 |
| H15 `h15-candidates.csv` | `699f75d7543bbe2ef9bd0c8c991ada3bf2d61bc0c9cea2fed02790f35b5e281f` | 精确 9,360 行及每行身份，独立于 H7 审核 |

父对账 Manifest：`0111ab23c3c1fbe33d96b738f2755ce79874319c9a54ef82b8b9c3b170bece05`。
既有私有正向核验报告：`b63ab8a69d10f9d64d7f9d8bef4cf63bb5581135b4816061d07c1c880a96c798`；
只能作为已有来源，不宣称它就是本轮 C0 批准或重新核验报告。

## 2. 精确成员与 Registry 绑定

完整 39 Base/80 农场名册留在上述私有 metadata，不将业务逐行数据复制进 Git。
需审核所有原精确身份（其余 75 个来源农场按原封存逐条核对）及以下五项 Owner 研究绑定：

| 来源原名 | 唯一 Registry Base |
| --- | --- |
| 文山古木农场 | `base_ffdc1ebe359436aa3f0fa834` / 砚山盘龙基地 |
| 文山喜古农场 | `base_ffdc1ebe359436aa3f0fa834` / 砚山盘龙基地 |
| 文山马塘农场 | `base_ffdc1ebe359436aa3f0fa834` / 砚山盘龙基地 |
| 大理巍山农场（WRM) | `base_f10df3ac242e4dbbf6c20b98` / 大理巍山基地 |
| 弥勒朋普农场（MYM） | `base_c51783e2ec7c16bba447d64e` / 弥勒朋普基地 |

不接受简写“盘龙基地”或模糊名称。嘉果莓森、曲靖师宗农场、格莱莓农场、老挝巴松一场
仅排除本研究，保留原始记录及全局身份；不分摊其重量，不把研究范围已解决改写为
全局历史身份全部解决。必须核对 source_identity/member Hash、原状态与研究状态分列。

## 3. 日历、面积、零值和每窗口全量审核

目标范围仅 2025-08-05—2026-04-15，共 254 日。9,906 Base×日是
6,416 observed + 3,490 authorized-zero；三个追加成员基地有 17/14/14 个原零转有记录日。
须逐 Base×日核对新成员后的零值证明，不沿用旧 75/9 状态；缺记录不可自动填零。
原件 04-16 独立在范围外。记录口径完整不保证所有田间实物采收均被扫码。

面积须逐 Base 连接历史面积行身份、mu 单位、来源/版本及 Registry；历史确认不证明
预测当时可知。物理口径等价、历史面积 known_at、历史签发证据继续 NOT_PROVEN，
Owner 接受其为研究限制，不把它们改成 PASS，也不继承严格 PIT 合格身份。

| 分层 | origin 本地日期 | 目标规则 | 候选计数 | 当前状态 |
| --- | --- | --- | ---: | --- |
| H7_PREFIX | 2025-08-04—2026-04-08 | D1..D7 | 9,672 | 待逐成员审核 |
| H15_LOCAL | 2025-08-04—2026-03-31 | D1..D15 | 9,360 | 待逐成员审核 |
| FULL_SEASON | 不登记 | 不拼接、不外推 | 0 | 不准入 |

每个窗口独立核对完整成员：candidate_id、base_id、season、window、origin_date、
target_start/end、target_dates_sha256、day_authority_sha256、status。
candidate_id 必须绑定 Source、Owner 研究决定、Base 成员和历史面积行 Hash。
按 base_id/origin_date 排序；集合必须恰为相应 Base×origin，无重复、缺失或额外行。
未来执行可以复用 `validate_owner_scope_inputs` 检查，但本包不调用私有文件路径。

逐窗口另须形成全成员审核台账：candidate_id、Base、origin、窗口、审核 disposition、
主要原因及证据 Hash。缺输入/成员/零值/日期/来源异常均保留，不按重量或误差筛掉。
本轮尚未生成实际失败台账：失败数、台账 Hash、审核 rowset Hash 均为 null，
**不能将“未重新审核”写成“0 失败”**。H7 与 H15 互不替代；计数齐全不代表正式准入。

## 4. origin/cutoff 研究时间语义建议（尚待批准）

- timezone 固定 Asia/Shanghai。D0 为候选 CSV 的 origin_date。
- 建议 research_origin_at = D0 23:59:59+08:00，research_cutoff_at 同值；
  target_start = D0+1 日 00:00:00+08:00，D1..DH 连续本地日。
- 这是事前登记的**研究模拟截止语义**，不证明该时刻已有真实预测或所有输入可用。
  日期字段不能反推真实 available_at、known_at 或 issued_at。
- historical_issued_at=null；未来 actual_executed_at 必须为真实带时区 UTC 时间，
  不能填 origin。两者分列；原严格评分器继续拒绝不合格的真实历史签发。
- 完整 support 2025-07-01—2026-04-15、产季锚点 07-01 仍是 C0 审核提案。
  后续若执行，必须同完整 support 生成两条曲线再截 H7/H15，不对窗口重新归一化。

## 5. C0 seal 的生成及批准边界

1. 先生成**候选审核 body**：研究范围版本和决定 Hash、全部输入文件/Registry payload
   Hash、完整 H7/H15 成员/日期 rowset Hash、日级/面积/成员权威、全部审核失败与原因、
   研究时间语义、完整 support、比较 family、固定算法/Fold B、限制和协议登记记录 Hash。
   两个窗口分别列数及成员 Hash；禁止用标签重量或误差决定成员。
2. UTF-8 JSON、sort_keys、indent=2、ensure_ascii=false、allow_nan=false、末尾 LF，
   Decimal 为字符串、日期 ISO；逐行规范化并确定排序，SHA256 得 candidate_review_body_hash。
   原 CSV 字节 Hash 与规范 rowset Hash 分开保存，不能相互冒充。
3. Owner 的独立 FORMAL_C0 决定必须指向这个精确 body Hash、每窗口实际批准计数、
   原成员/排除/失败边界、时间语义和限制。缺项、Hash 漂移或仅批准总数均不得升级。
4. 再新增 formal C0 seal，引用候选 body Hash 和正式 Owner 决定记录 Hash，不做自引用
   Hash 循环，不覆盖原候选 CSV/历史 metadata/status。没有正式决定则 formal seal=null。
5. Hash 是完整性标识，不是授权、签名或可信时间；同时保存可验证决定来源和真实记录时间。
   即使 FORMAL_C0 以后获批，也不自动批准 A_INPUT_READ/A_EXECUTION 或 B_LABEL_READ/B_SCORING。

本轮仅在合成台账上验证排序、重复成员拒绝和失败保留会影响 Hash；没有生成真实 C0
seal、真实预测或真实误差。既有阶段 A 真实入口继续无条件 PermissionError。
当前协议登记需审核，`RETROSPECTIVE_PROTOCOL_EFFECTIVE=false`；其余七项决定未批，
`FORMALLY_ADMITTED_C0_COUNT=0`，真实执行与评分 BLOCKED，`S3_FORMAL_COMPLETE=false`。
