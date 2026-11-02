# 历史代码定位兼容性与隔离预演准备

任务：`TD01_HISTORY_DISPOSITION_DECISIONS_AND_COMPATIBILITY_R1`。
只复用 TD-01E 现有工具和原清单，不新增模型、迁移执行器或替代准入规则。

## 基线与验证次序

PR #783（TD-01I）已合并；Head 为 `ca195a1899d7e99b9966a468b6141f99c39f499d`，
Merge/main 为 `0118d82c8a0aa14f17fb37f56faeb6ed134698cf`。
合并后 [main CI 41375181391](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/41375181391)
已独立读取为 push、Attempt 1、completed/success：8 SUCCESS、8 SKIPPED、0 FAILED。
这不是本 Draft PR 的 exact-head CI；新 PR 状态另行报告。

先用原 `backend.app.core.historical_code_identity verify` 校验65项当前历史身份；退出0后，
再用原 `rehearse` 创建、验证并清理工具自有的代码隔离图。没有调用真实历史清除或保管操作。
完整命令和结果见 [validation.json](validation.json)。

## 可验证的代码范围

65项身份继续绑定原 Commit、精确Path、Blob及原SHA256。清单SHA256仍为
`80c60fe1b35204a8f3a819e3b84dd1ca3f2c469b7a71811b282c45ca3cbd6193`。
50项独立冻结Hash字段及15项既有Git Blob pin仍由原工具校验，不新增“批准Hash”或 JSON 旁路。

| 原提交 | 身份数 | 典型依赖 | 本轮代码检查 |
| --- | ---: | --- | --- |
| 320f2046e3105b1b55da9cb037892571110b584a | 31 | 旧Main/API、Forecast Intelligence、前端证据、CI预检 | CURRENT_HISTORY与代码隔离图通过 |
| e9812e82067dceae444ff0707ceeb2f560c1018e | 16 | Local Auth历史运行时合同与原配置定位 | 登记代码通过；旧workflow身份仍BLOCKED |
| 0124371b433d1b3c34e5e59a2a9a5e621a570f3b | 15 | TD-03G、S3 Daily Rowset历史代码 | 登记代码通过；SOURCE_002数据权限未变化 |
| 89641834ab7a0bd902a23f9243325da5c163d518 | 2 | 原交付辅助代码 | 登记代码通过 |
| f151f0e6aca3577c5ee959a220c16e9756179649 | 1 | 原交付辅助代码 | 登记代码通过 |

代码隔离图中原Commit为0，只有登记代码Blob及新合成Tree/根；原内容身份不变。
本轮没有将冻结报告、配置、锁文件、工作簿或压缩资产复制进该隔离图。
工具会读取既有技术Hash依据以验证独立绑定，但不会把这些依据材料作为非代码迁移产物。

## 仍需逐项解决的定位与正式验证

以下清单按原TD-01E [消费者登记](../td01e-historical-consumers-r1.json)复用：原快照174个身份消费者，
其中112个历史源码消费者。它不是对当前main新增代码重新认证的全量消费者数量。
[机器检查清单](compatibility-checklist.json)绑定原输入身份、提交组及阻断状态，不复制原业务材料。

| 检查项/既有入口 | 依赖及影响 | 当前状态与实施条件 |
| --- | --- | --- |
| CI unit-contract-golden、full-suite-canary-shard、frontend-unit | 三处要求原320f2046 Commit存在；前端另要求原API源码 | BLOCKED真实图适配：保留预检与原断言，需先审查版本化定位合同 |
| backend/tests/historical_source.py、Local Auth、MCP、Forecast Intelligence | 精确旧源码、原辅助器以及冻结JSON/配置 | 65项登记代码读取通过；未登记/动态身份仍需独立pin与审查 |
| TD-03F/G历史兼容及S3 Daily Rowset | 原异步实现、辅助器与Source_002查询代码 | 相关原测试实际执行；不得据此读取或替代SOURCE_002正文 |
| frontend/src/test/dashboardGovernance.test.ts、S6/Option-B相关验收 | 历史前端/API/SDK及证据定位 | 本轮不声称完整前端/SDK迁移通过；保持原Hash和业务断言后另验 |
| V0.8面积模型、V0.13/V0.15回放审计、V0.16归因、V0.19/V0.21研究入口 | 固定版本、祖先关系、配置、来源和运行时git_sha | BLOCKED完整正式复算：原模型/fit、源行集合、物理量、日历、PIT及评价事实均保留，不在本轮训练/评分 |
| TD-01D e2d0ffa增量基线及TD-01F/G/I图门禁 | 旧基线、审计元数据、清单及可信执行器的来源绑定 | 本轮不静默替换基线或信任根；业务原则批准不等于新图适配已实现 |
| CURRENT_HISTORY真实仓库读取 | 仍要求原Commit+Path | 缺失应失败，不能启用任意Blob回退 |
| CLEAN_GRAPH_REHEARSAL | 仅组件自己创建并拥有的临时图可用 | PASS代码身份演练；不是完整应用运行、真实历史清理或生产回退入口 |

保留原Commit在公开图中可达会保留其祖先历史；后续应保持原代码字节并审核定位映射，
不能为维持CI而整体保留待处置旧图。未解决依赖不能换同名文件、合成业务源或新的expected Hash来消除。

## 非代码与范围阻断

| 原登记范围 | 数量 | 本轮实际处理 |
| --- | ---: | --- |
| CONFIGURATION_NOT_ADMITTED | 11 | 现有读取工具拒绝准入，BLOCKED |
| FROZEN_REPORT_OR_EVIDENCE_NOT_ADMITTED | 209 | 原件/Hash保留，未迁入代码隔离图，BLOCKED |
| ORIGINAL_DATA_DO_NOT_READ | 2 | 真实XLS不读，不授予公开许可，BLOCKED |

总计222个路径依赖仍未完成非代码迁移。另有1项缺少独立匹配Hash的代码身份，及pyproject.toml、uv.lock、旧workflow三项显式非代码身份；后三项与原非代码清单有重叠，不另加成225项。
本轮用原接口实际确认222条路径、4项显式身份和D07五个资产均被相应范围规则拒绝，没有访问其正文。
这些预期拒绝是有效的安全检查结果；相应依赖的迁移状态仍为BLOCKED，不能列为迁移通过。

D02/D03/D06已批准的业务边界继续有效，D01/D07/D08/D09现已批准原则；原PENDING记录不回写。
P35不重建、不上传；其既有逐文件结果不能替代非代码历史兼容或真实历史处置授权。

## 后续隔离预演入口条件与停止点

1. 完成[Owner记录](owner-decisions.md)中的D09具体保管人、位置、权限、期限、恢复及日志责任。
2. 对222项依赖、D07资产和未登记代码分别确认准入/保管与定位方案；真实材料读取及备份须单独明确范围。
3. 复用现有工具准备受控副本和版本化定位映射；原字节、Hash、模型及原断言不变。真实图适配未实现前保持BLOCKED。
4. 获准后再执行完整历史图预演、正式合同/CI、归档与恢复验证；本次代码图通过不覆盖这一阶段。
5. 实际Git历史调整、Tag和Release处理分别提交精确动作与身份清单，另获授权后才可实施。

本轮没有真实数据备份或恢复演练。后续预演失败时仅处理工具自有副本；不能把含真实历史数据的旧Ref重新公开作为自动回退。
当前 `REAL_HISTORY_REWRITE_READY=false`；原仓库始终Public，本次交付到独立Draft PR后停止。
