# OPTION_B Dashboard 权威冲突与情景输入绑定修复 R1

TASK_ID=V0_18_OPTION_B_CLIENT_AUTHORITY_SCENARIO_BINDING_FIX_R1

**当前 RESULT=BLOCKED，不是已完成修复验收。** 本地156项前端 Unit、Lint、
Typecheck、Format、Build、Ruff/Mypy 通过；历史合同105通过/1失败。未创建提交或PR，
未执行新HEAD CI，真实HTTPS/PostgreSQL完整回归未完成，浏览器阶段尚未运行。
下文实现说明仅描述已保留的工作树代码，不将其升级为正式接受。

## 当前阻断及最小追加授权

`backend/tests/forecast_intelligence/test_v0_18_s4_business_flow_contract.py` 第25行
对当前工作树直接校验历史 source_evidence_sha256，包含本轮必要修改的 client.ts
和 AuthorizedSavedRunSelector.tsx。原预期分别为
22e03d846899a00d52aaf1cb2d9df62f71329afa6f06ce7422d10eba71f51ba8、
c962bdffc8be0c5b19c3feeceadb4463616e884c0f019d2853c27cd862e9c9a0。
修复正确或单元通过不能使这些历史原字节等于新代码。

未修改该后端历史测试、旧预期SHA、冻结JSON或CI。需Owner单独授权仅对这两个
历史来源使用已存在的 historical_bytes 从经核实固定提交读取，保持同样SHA256断言；
其他冻结来源仍检查当前原字节，当前Runtime继续执行真实回归。不能把历史Hash
通过当当前安全通过。建议审查固定基线 ebe50fbe 的这两个原字节及S4原提交来源，
不自动选择新HEAD或重新计算旧expected值。

发现该权限缺口后停止正式验收，最终隔离runner主动SIGTERM并按S5所有权清理；
本轮所有取消记录均不作PASS，不伪造旧CI或旧浏览器结果。工作成果及原失败证据保留。

Owner 本轮单独授权必要前端运行代码、对应测试、Draft PR 和 exact-head CI。
基线为 `ebe50fbe250097a882407604a8482ca9cfdf6d9a`；原阻断工作树不改写。
本次不是 A–G 完整接受、H 风险接受、Closeout 批准或生产启用。

## RED 保留与复现

原阻断报告、原三个探针源码及原 JSON 日志逐字节归档在
`docs/v0-18/evidence/option-b-client-fix-r1/red/`。

| 来源 | 原 SHA256 |
| --- | --- |
| original-blocker-report.txt | 0dc874133452dfd4499c967e8de37f2e72ea1738277038a38a2fd5b75a790a0c |
| original-probe-source.txt | 350a4e4f01bf0059ada70f78772a1aed7616dd71e8714f599d8bc9514f04a3e3 |
| original-probes.json | 0a95616445def5634cfb68d12e4b7f70fad92127ec51dad64f15836c28e0820b |

在新工作树修改生产代码前，再次运行同三个探针，结果 RED，输出保留于
`/tmp/option-b-client-fix-red-r1.json`。这些是合成单元探针，不称为真实服务器泄露。
当前回归保留“旧上下文必须 CLEARED”和“错误模拟必须拒绝”断言；增加 handoff、
完整身份清理和错误保留行为。修复后原 dialog 已被正确卸载，因此 Harness 显示
已有 provider notice，并等待实际“旧结果已清除”文案，不再等待已卸载的旧错误面板。
原始失败源码和断言仍以原字节保留，没有 skip、xfail、删除错误检查或扩大超时。

## F1：统一使用现有 access invalidation

选择器发现 scope/list 的 grant_revision 或 catalog_snapshot 不同，构造的本地409
现在与已有 selection 409 一样调用 invalidateSecurity("access")。
真正 HTTP409 和适用的授权撤销仍由既有 request 边界处理。

复用已有 ForecastProvider/SessionGate：丢弃 verified/ForecastIdentity/handoff/日期，
取消在途请求，重新挂载敏感子树，因此 useResource、产能草稿、模拟及排名一起失效。
没有增加第二份缓存或身份库。普通 Quality403 不发全局预测 invalidation；普通
筛选422和服务503保留上一份合法上下文。重新选择必须走真实授权目录/selection。

## F2：先审查冻结合同，再验证既有哈希承诺

已实际审查并绑定基线字节：decision_schemas.py、decision_service.py、what_if.py、
business_loss.py 及 v015_research_cohort.py 的 canonical/digest。
**不新增 scenario_version 回显字段，不修改后端或 Hash 合同。**

虽然 SimulationResult 不回显 scenario_version，冻结 DecisionScenario.payload()
已将其纳入 scenario_hash。验证所需字段均可取得：

- authority() 的保存曲线/来源/层级/成本/日期/规划/初始积压/策略身份由原响应提供。
- scenario_id/version 和逐日原始 capacity_rows 来自本次请求的 Zod 深拷贝。
- DIRECT 输入量、WORKFORCE 人数和原始人效、buffer 的显式存在性，按冻结
  CapacityDay.payload() 序列化；WORKFORCE 输入的 direct 字段为 null，不自行计算。
- 三项 payload policy version 与响应 engine_policy_versions 对照固定冻结版本。
- Python canonical 为排序键、无多余空格、UTF-8、末尾换行，SHA256。

新 scenarioBinding 只做身份/原始输入与字节哈希核验：Decimal 保留字符串，去除
无意义前导/末尾零以匹配已有 decimal_text()，不使用浮点近似、不重算经营数量。
先逐日核对 mode、日期、人数/人效、direct/buffer，再核对请求重建的 scenario_hash。
同时复核 row_hash、result_hash、response projection_hash；Compare 保留原成员、
rank→result/scenario hash 关联与顺序检查，并复核 comparison authority/hash。
只采用服务端排名，不按损失重新排序。

WebCrypto 验证跨 await 时仍受 request revision/AbortSignal 约束。取消、撤权或
账号切换后的旧验证不能交付或再次清理新账号结果。已有409错误合同保持，不被本次
自身 invalidation 错换成取消错误。缺 WebCrypto、未知策略或不能验证的合同默认拒绝；
对应不充分条件为 BLOCKED_API_CONTRACT_INSUFFICIENT，不伪造字段或 Hash 通过。

## 验证层级与隔离环境

单元测试使用明确 SYNTHETIC DTO；新增 workforce fixture 由未修改的 Python
DecisionSupportService 对既有合成 curve 生成，用于独立核验 canonical 兼容。
该 fixture 不进入生产 bundle，也不替代真实 HTTPS/PostgreSQL 验收。
jsdom 无 SubtleCrypto 时只注入 Node 原生 WebCrypto，没有假实现/固定哈希。

运行入口：

```sh
python -m frontend.e2e.support.run_option_b_client --output /tmp/SYNTHETIC-client-NEW --browser
```

入口只为既有 S6/S5 runner 增加独立浏览器 spec；沿用原私有 PostgreSQL 创建、
所有权校验、SIGTERM 安全关闭。旧 S4/S5/S6 测试、runner、历史 JSON 原字节不变。
新增测试 wrapper 复用真实应用和同一隔离数据库。新浏览器场景只在真实 scope 响应
完成后变更等价的可信目录 JSON 配置字节；真实 saved-runs 再生成新 snapshot。
没有替换 HTTP 响应、伪造认证或写预测数据。验证旧模拟/草稿消失和重新显式选择。

当前轮本地输出与退出码由 evidence.json 及 green/ 实际 JUnit、浏览器 JSON、
unit JSON、工具版本和 owned-cleanup 记录承载。源码在浏览器构建前记录并再次核对。
最终 Git HEAD 及 CI 只能由提交后的独立回执绑定，不在提交文件中预造未来绿色结果。

研发过程中的失败/取消不隐藏：新增测试曾错误假设旧 comparison fixture 含 workforce，
现改为由原 Python 服务实际生成相应夹具；两个保留上下文测试曾等待错误的 UI role，
现核对实际错误文案。最初给旧 S4 spec 增加用例触发三个历史哈希合同；已恢复该文件
原字节，新增测试完全独立，不修改历史预期哈希。前两次本地 runner 因准备期测试
来源变更主动取消，其私有原始日志及 STOPPED 清理记录保留，不计作最终 PASS。

## 与后端复现分开

独立后端任务在其独立分支复现了禁用提交后仍进入读取、但最终401不释放敏感字节
的窗口，随后按 Owner 指令停止；本 PR 不含该后端测试/修复，不声称消除了该风险。
客户端 GREEN 不代表后端复现 GREEN，也不代表 A–G 审查接受。后端线索2未执行。

真实 iOS Safari、软键盘、屏幕阅读器、多主机/NFS/Windows 和生产环境仍未验证。
不访问真实采收，不创建真实账号/grant，不运行生产迁移、部署或版本操作。

A_G_INDEPENDENT_ACCEPTANCE=PENDING

H_OWNER_RISK_ACCEPTANCE=false

GOVERNANCE_EXCEPTION_APPROVED=false

VERSION_CLOSEOUT_FORMAL_COMPLETE=false

PRODUCTION_READINESS=NOT_READY

READY_AUTHORIZED=false

MERGE_AUTHORIZED=false

TAG_AUTHORIZED=false

RELEASE_AUTHORIZED=false

DEPLOY_AUTHORIZED=false

STOP=true
