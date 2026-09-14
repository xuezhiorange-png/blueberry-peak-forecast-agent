# V0.5 验收门槛

关联：[开发计划](development-plan.md)、[天气候选审计](weather-source-evaluation.md)。
状态是规划冻结、待审查；下列门槛**均不是本轮已通过的模型或产品验收**。
本任务只能交付文档/模板；用户确认基地输入已提供，实际导入、海拔核验、天气、实验、集成另行实施。

## 1. 不可越过的门

| Gate | 必备证据 | 不满足时 |
| --- | --- | --- |
| G0 发布边界 | v0.4.0 tag=74293797aad2e057edd484ec6757cc54f4542461；main差异审计；旧路径不变 | tag不符立即BLOCKED；不得自动移动tag |
| G1 身份/位置 | 基地名称/covered_farms/代表坐标/总面积已由用户确认提供；坐标系、海拔来源、provenance/review待导入核验 | S1可启动；海拔PENDING_EXTERNAL_VERIFICATION，不伪造正式zone/weather绑定 |
| G2 业务域 | 每base-season 04-15前后审计、内部缺数检查、完整性/面积资格、新数据版本 | 不以部分累计量作整季标签，不改旧authority |
| G3 气候区 | 长期正常期、样本量、分区依据、稳定性、版本mapping | 不把州市或预设类别数当气候区 |
| G4 天气 PIT | 原issued_at、实际available_at、run/model版本、完整lead、字节hash、合法访问 | 无as-issued证据不能做operational增益声明 |
| G5 评价预注册 | origins、base/zone留出、指标、样本门槛、候选、超参、数值gate先冻结 | 不先看成绩再降阈值/选窗口 |
| G6 选择/no-win | 三类baseline同集比较、分层全量结果、失败/排除记录、总量/shape独立决定 | NO_STABLE_GAIN允许，不能强制weather胜出 |
| G7 运营窗口 | D+1..D+7/15连续整窗、cutoff交互、缺失状态、最早tie-break | NOT_COMPUTABLE_FULL_WINDOW，不把缩短窗冒充整窗 |
| G8 产品/发布 | 版本隔离、持久化/hash、API/MCP/豆包E2E、exact-head CI、独立发布授权 | 不自动Ready/Merge/Release |

## 2. 阶段出口

- S1：四份authority输出（业务域、registry、zone profile、mapping）完整且可审计；
  当前 `BASE_REGISTRY_INPUT_AVAILABLE=true`、`S1_IMPLEMENTATION_CAN_START=true`；
  `ELEVATION_STATUS=PENDING_EXTERNAL_VERIFICATION`，不假装已完成导入/authority。
- S2：四类天气链逐类资格、许可、可得性、版本和缺失策略齐备；7日/15日 PIT 门分开判断，
  “源有15天产品”不证明每个历史origin在当地日界下有完整15天。
- S3：A/B/C定义与各自证据分母、out-of-base结果、选择记录；未知未登记base fail closed。
- S4：S4A亩产/总量、S4B形状/时点分开出具 ablation 与cross-zone结论，允许一胜一不胜或均不胜。
- S5：OPERATIONAL_PEAK_POLICY_V1 与整窗/临界日期用例通过；总量字段和单日峰值不可混淆。
- S6：跨季/跨场/跨区/A-B-C/PIT复验齐备，兼容旧产品、E2E与release qualification通过。

## 3. 十五项最终成功条件

| ID | 成功条件 | 可审计完成证据 |
| --- | --- | --- |
| SUCCESS_1 | 所有登记基地进入统一Base Registry | 云南版本范围内用户确认的基地清单、逐条登记/排除/待补清单、对账分母 |
| SUCCESS_2 | 所有模型基地具有可审计Climate Zone | 已审zone版本、位置溯源、mapping覆盖与例外记录 |
| SUCCESS_3 | 训练/预测统一04-15边界 | 每季边界审计、错误请求fail-closed、尾果未删未补0 |
| SUCCESS_4 | 登记基地不再普遍因缺完整同场历史不可预测 | 各等级可预测/不可预测数量及原因；覆盖门槛S1/S2后冻结 |
| SUCCESS_5 | 每次输出Applicability Level | A/B/C、evidence level、history count、fallback、limitations合同测试 |
| SUCCESS_6 | 天气可PIT回放 | as-issued/available时间、快照hash、lead覆盖、重放一致性 |
| SUCCESS_7 | 天气采用由验证增益决定 | 预先冻结的增益规则、ablation、采用或no-win理由 |
| SUCCESS_8 | 未来完整7日最大单日产量及日期 | D+1..D+7最大值/最早tie-break/整窗total独立测试 |
| SUCCESS_9 | 未来完整15日最大单日产量及日期 | D+1..D+15相同合同及边界用例 |
| SUCCESS_10 | 跨基地验证 | 整base留出、全base结果、共同可比集与覆盖扩展集 |
| SUCCESS_11 | 跨气候带验证 | 整zone留出、样本分母、无泄漏normal/分区处理 |
| SUCCESS_12 | 跨产季验证 | 时间顺序origins、训练截止、预测冻结先于评分 |
| SUCCESS_13 | A/B/C分层评价 | 等级逐指标/不可计算/退化及样本量，不只给总macro |
| SUCCESS_14 | API/MCP/Doubao E2E | 共享service、schema/hash/error parity、真实E2E留证 |
| SUCCESS_15 | v0.5.0 release qualification | 最终exact-head CI、业务review、显式tag/release授权 |

这些是目标，不代表必定在当前数据条件下都可达到。缺证据写NOT_ESTABLISHED，不能更改分母
隐藏未覆盖基地、把LEVEL_C当A，或把工程CI绿色当预测精度合格。
**本规划不设WAPE<10%、peak error<3天等数值阈值**。S1/S2完成后按真实基地/zone/季节/lead
覆盖另行冻结最小样本数、主次指标、稳定性/退化容忍、置信区间处理及release数值门槛，
必须在正式候选评分前批准。杨柳golden仅工程回归，不是SUCCESS_10–13的替代。

## 4. 必须规划的负向/边界测试

1. 产季2025–2026中2025-10-15仍是业务域；2026-04-15包含，04-16只audit。
2. 请求season_end=2026-04-16返回SEASON_END_EXCEEDS_BUSINESS_CUTOFF，无silent truncation。
3. D=04-08七日完整；04-09不足；03-31十五日完整；04-01不足；04-10只剩五天。
4. 整窗中间缺一天，不跳日凑数；末端不足、季前/季后不误报COMPUTABLE。
5. 最大单日与窗口累计分离；并列最早；全0完整预测可算，未知标签不得替换为0。
6. source-active缺farm记录只有既有授权可zero；全源无记录保持UNKNOWN。
7. 基地代表位置与成员归属分别审计；海拔未核验不造值。模板说明、空行不能导入成真实base。
8. 当天晚上发布的预报不能用于当天早上origin；只有model init、缺availability不算严格PIT。
9. 重分析、拼接短lead序列、后生成hindcast不能替代真实as-issued15日档案。
10. weather forecast在截止前覆盖不足也不能借事后actual补齐；许可/服务失败与缺数透明。
11. 总量不变而峰位改变允许；weather未胜时维持no-weather模型是有效决策。
12. v0.4旧杨柳日期窗口、持久化share_text/result_hash不重写；不把04-15新语义回写旧结果。
13. 同一基地两个成员的完整日量只汇总一次；汇总行和明细不重复计量；未知成员标签不可当0。
14. 有基地总投产面积即可建立基地分母，不要求成员面积；多个相邻农场共享基地代表天气点。
15. out-of-base必须留出基地全部成员；成员诊断不扩大独立base样本分母。
16. 未有显著海拔/气候带/地理跨度证据，不默认MULTI_POINT_BASE_WEATHER。

## 5. 本规划 PR 的验证与停止

只校验文档引用、CSV表头/零数据行、嵌入YAML语法、任务/阶段覆盖及git diff --check；
不添加生产Python，不调用天气数据端点，不跑新模型评价，不改CI。
仓库现行PR门禁包括full-suite-canary；如尚在运行如实标PENDING，不以文档任务绕过。
本轮 `READY_ELIGIBLE=false`，即使CI通过也保持Draft等待Coordinator规划review。
不自动启动S1–S6，不发v0.5.0 tag/release。
