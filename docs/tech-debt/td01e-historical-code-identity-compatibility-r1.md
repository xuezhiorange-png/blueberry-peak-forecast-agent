# TD-01E：历史代码身份兼容与干净 Git 图前置验证

TASK_ID：`BLUEBERRY_TECH_DEBT_TD01E_HISTORICAL_CODE_IDENTITY_COMPATIBILITY_R1`。
基线 `38df347543c37315d5802e168afdc2eb9db4486b`，前置 PR #778 已合并；
main CI #41208866823 初始为进行中，随后已核实同 SHA / push / completed / success。
本任务只处理核准代码，不授予数据读取、公开、真实历史改写、Tag/Release、可见性或部署权限。

## 实际交付与范围

可运行组件为 `backend/app/core/historical_code_identity.py`，不加载数据库、模型或网络客户端。
[代码身份清单](td01e-code-identities-r1.json)登记65个精确 Commit + Path + Blob + SHA256 身份，
覆盖320f2046、e9812e82、0124371b以及两处原交付 f151f0e6、89641834的必要辅助代码版本。
其中50个身份对照既有冻结证据的 SHA256 字段，15个对照 TD-03G 原测试的 Git Blob 常量。
新增 SHA256 不是唯一信任依据：TD-03G 先核对既有 Blob pin，再记录该同一代码对象的 SHA256。
没有搜索其他版本来匹配 Hash，没有按同名文件替换源码。

清单只含应用、前端样式/脚本和测试源码。原始数据、配置、锁文件、冻结报告及 JSON 不作为
源对象迁入；清单中的证据文档路径仅指向既有 Hash 字段，不归档其内容或取得其公开许可。
`backend/tests/forecast_intelligence/test_v0_17_s2_decision_service.py` 在320f2046下未找到匹配的
独立既有 SHA256，保持 `BLOCKED_NO_INDEPENDENT_MATCHING_HASH`，没有用相似名称的 API 测试替代。

清单自身由组件内固定 SHA256 校验，调用者不能传入新的“信任 Hash”或 JSON 审批开关。
改映射、Blob、原始 Hash或批准标签，即使同时修改也不能通过未变的清单信任根。
这属于代码评审信任边界，不声称抵御能够任意改写已信任 Python 实现的攻击者。

## 两种模式严格分开

`CURRENT_HISTORY` 仍要求原 Commit 对象存在、原 Path 精确存在、普通代码 Blob 类型正确，
再依次核对独立清单中的 Blob OID、Git Blob 内容身份和原始 SHA256。缺失不恢复、不联网，
不改读当前工作树，也不尝试另一 SHA。已登记代码的 Python 历史辅助器与前端证据读取
接入该路径；未登记或非代码对象仍使用原来的严格当前历史机制，不获得 Blob 回退资格。

`CLEAN_GRAPH_REHEARSAL` 只允许在组件本进程创建、登记并负责清理的独立临时 Git 库执行。
普通仓库、JSON模式标签或环境变量不能取得该资格。先在当前历史独立验证代码，然后只把
这些代码 Blob 放入新库，创建无父提交的新合成根，明确检查原 Commit 不存在、无远端、
无 alternates、无无关 Blob/旧 Commit。读取时仍绑定原 Commit + Path 的可信映射和原 Hash。
真实仓库不会改写；此模式没有对真实清理后仓库自动启用的入口。

CLI（项目 Python 3.12；输出为验证元数据，不打印源码）：

```sh
python -m backend.app.core.historical_code_identity verify
python -m backend.app.core.historical_code_identity rehearse
```

`read --commit <精确SHA> --path <核准代码路径>` 是前端测试共用的二进制源码通道，
只有全部校验通过后才向调用者返回原字节。前端单测因此显式使用 Python 3.12；
CI 仅补足该解释器，不修改事件、Job、矩阵、测试范围或失败判据。

Git 子进程禁用惰性抓取、所有传输协议、交互及外部 hooks，不接受任意 Git 参数。
所有权和模式拒绝发生在读取对象之前；数据路径、配置路径、路径穿越、Revision 表达式、
错误原 Commit、Blob、Hash、版本及被篡改清单均有负例。

## 原断言与当前历史测试

原 `test_current_runtime_edit_does_not_rewrite_historical_hash` 使用完整本地 fetch，可能连带
取得与代码无关的历史对象。本轮将测试准备改为仅复制核准代码及所需 Commit/Tree 元数据，
不复制父历史或业务 Blob；保留原测试身份、原断言和原 Hash。该不完整 CURRENT_HISTORY
测试库不属于 CLEAN_GRAPH_REHEARSAL，不能被用于未来公开图方案。

两处冻结合同仍钉住历史辅助文件的原字节，故将各自读取点绑定回自己的原交付 Commit。
不改任何旧 JSON、expected Hash、安全结论、Golden、skip/xfail或模型代码。
[原断言指纹](td01e-original-assertions-r1.json)用于自动核对原 Assert、测试签名/装饰器与
既有 SHA 字面量不变；该指纹不作为新源码准入依据，也不依赖旧 Commit 在未来继续存在。
原 CI 三处 `git cat-file -e <原Commit>^{commit}` 及各代码 Path 预检全部保留。

## 全量定位与仍未迁移的依赖

[消费者清单](td01e-historical-consumers-r1.json)检查基线的1754个公开代码/CI路径，
结合 Python AST、跨行 Git 命令、Node/CI 引用和包装调用核对：174个 Git 身份相关消费者，
其中112个历史源码消费者、61个当前工作树 Hash/运行时 Git 元数据消费者、1个既有合成预演。
记录代码路径、位置、操作和固定身份 token，不复制业务文本、名称或重量。
动态构建的路径明确保留未解决状态，不因出现在搜索结果中就自动加入代码清单。

[未解决依赖](td01e-unresolved-historical-dependencies-r1.json)保留222个非代码路径级依赖，
包括冻结报告/JSON、配置及两份仅按已有元数据登记的 Legacy XLS；另列1个独立 Hash 不足的
代码身份、pyproject/uv.lock/旧 workflow 的非代码身份，以及其他 Commit 的未登记调用。
这些对象没有被下载为源码、没有进入65项代码清单，也没有获得公开或迁移批准。
SOURCE_002 身份和来源门禁不变，本轮不读取其原件或分区内容。

公开增量保护的 e2d0ffa 基线保持原样：

```text
PUBLIC_INCREMENT_BASELINE_MIGRATION=BLOCKED_PENDING_OWNER_SCOPE
REQUIRED_OWNER_SCOPE=D02,D03,D06
REAL_HISTORY_REWRITE_READY=false
```

旧 Main Tree 含尚未完成保密决策的对象，不能整体保留到未来公开 Git 图来维持 CI。
代码兼容证明不等于完整历史清理就绪；冻结 JSON、报告、配置、增量基线、开放 Ref、
Tag/Release及其他旧 Commit消费者均需逐项兼容/授权，本轮不改变任何已发布身份。

## 合成验收证据

[当前历史验证](td01e-current-history-verification-r1.json)和
[干净合成图验证](td01e-clean-graph-verification-r1.json)由上述 CLI 实际生成。
后者只包含65项核准代码的 Blob及新合成树/根提交，原 Commit数量为0。
跨独立进程比较完整业务输出及结果 Hash；机器目录、运行时间不进入业务摘要。
负面场景与旧 ETL、Forecast、Local Auth、MCP、TD-03G合同回归分别执行；
最新 HEAD 的真实 CI、Job及测试数量在 Draft PR 回执中记录，不预填成功。

本轮不训练、不评分、不读取真实工作簿或业务原件，不清理真实历史，不启动 V0.22。
