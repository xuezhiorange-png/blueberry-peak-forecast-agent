# TD-01C：冻结历史合同迁移准备与合成预演

Owner 本轮选择公开代码、私有真实数据；本文件不授予真实历史改写、Tag/Release
变更、强推、可见性修改、原件读取或复制许可。仅合成仓库的预演已经执行。

## 已知真实范围与快照增量

复用 TD-01B [742行 Ref 清单](td01b-public-ref-exposure-r1.csv)，其 SHA256 为
`2ee716764c8a67d27447bb018eb0e02c88cf73743f9dfa42abc71c881621eeb6`，不回写它。
[本轮增量](td01c-ref-inventory-delta.json)记录743个执行前公开 Branch/Tag：
新增 TD-01B 分支，main 因 PR #776 正常合并推进至 aeb6cad；23个旧 Tag 未变。
这不是新的一次742树审计，不包括隐藏 PR refs、Fork、克隆和缓存的完整证明。

旧清单中709个 Branch 当前树及全部23个 Tag/Release仍引用两个业务 Blob；
干净 main 的祖先也仍可达引入提交。本轮的新分支和普通提交同样不清除祖先。
来源分区和衍生公开文字须独立决定处置范围，不能把 SOURCE_002 与 Legacy 混为一源。

## 实际运行的独立合成 Git 仓库

`backend.app.etl.history.synthetic_migration` 没有 repo、remote、任意 Commit 输入，
只在本进程创建的 `SYNTHETIC_ONLY_TD01C_*` 临时目录中构造 source/clean 两库。
Git 操作有命令及目录边界，禁用全局 Git 配置，库无远端。没有对真实仓库执行
filter-repo、清除、GC、强推、Tag 删除或 Release 操作。

预演构造三次提交、两个分支和两个注释 Tag：

1. 原始合成 CSV 位于祖先；合成源码 VALUE=1。
2. 修改源码为 VALUE=2，旧 CSV 仍在分支和 Tag 所指树内。
3. 当前 main 树取消 CSV，但祖先仍可达它。

在另一个空库重放同一合成源码和消息，只去掉合成 CSV。三个 Commit ID 均改变；
最后一个提交的树可以相同，但父身份变化使 Commit 不同。保留源码 Blob 和内容
SHA256完全相同，新库连旧合成 CSV 的对象都没有。两个注释 Tag 对象也改变。
旧 Commit 定位在新库失效；可信 old→new 定位加上**独立原 Hash**可核验相同源码。
错误的新定位及试图同时替换 expected Hash 的负例均拒绝。

实际结果及映射见 [合成运行结果](td01c-synthetic-migration-result.json)。结果没有
临时路径、运行 nonce 或当前时钟；两个独立进程的规范化结果相同。Git 时间是
明确虚构的合成元数据，不是 Owner 审批、真实迁移时间或历史签名。
这个三提交线性样例不模拟完整项目所有合并拓扑/平台缓存，不是通用迁移工具，
更不是已经批准的真实 Commit 映射。

## 真实合同的兼容矩阵

| 真实对象 | 可保留的身份 | 必须另外迁移或确认的部分 | 当前结论 |
| --- | --- | --- | --- |
| 预测/导入/评分源码、模型参数、原数据文件 | 字节不变时的内容 Hash / Blob ID | 私有存储定位及运行许可 | 本轮全部保持，不能用合成样本替代 |
| `backend/tests/historical_source.py` | 原源码内容校验、断言与原 expected Hash | 固定 `320f2046e3105b1b55da9cb037892571110b584a` 的定位 | 实际迁移尚未批准 |
| V0.18 local-auth/MCP/revoke/preauth 证据测试 | 旧证据和源字节/Hash | `e9812e82067dceae444ff0707ceeb2f560c1018e` 等固定 Commit 定位 | 不改旧证据；需逐项审查新定位来源 |
| `backend/tests/td03g_historical_source.py` | 固定源码 Blob 与业务安全断言 | `0124371b433d1b3c34e5e59a2a9a5e621a570f3b` 及其父身份 | 本轮保持原样 |
| `.github/workflows/ci.yml` 的历史对象检查 | 必须验证原历史源码的含义 | `git cat-file -e` 的固定 Commit 可用性 | 真实清除前需获准的替代定位方案，不能删除检查 |
| 研究 JSON/报告、Registry、Fold、数据及 fit manifest | 原实验事实、原成员、来源及物理口径 | 私有数据/公开脱敏表达的存放和链接 | Owner 决定，不重新计算或编造原结果 |
| 23个 Tag / 对应 Release | 原始发布事实与受控记录 | 新 Commit 引用、签名、源码归档及发布访问 | 未授权变更，禁止直接移动旧 Tag |

仅把 expected Hash 改成新结果不构成兼容。保留污染旧 Commit 在公开 ref 上可达
以使老 CI 通过，同样不构成清除。真实准备方案须提供经批准的源码字节保管方式、
原 Hash 的独立校验及版本化定位映射；不能让待验证映射自行宣布其 expected Hash。
若冻结合同禁止必要的定位变更，必须先停在 BLOCKED 并请求精确差额授权。
本轮仅证明该机制可在合成仓库成立，未改接真实 resolver 或测试。

## 如未来获批准，执行顺序与停止条件

1. Owner 决定哪些名称、映射、面积、曲线、统计及来源身份应保持私有，逐项区分
   真实数据、纯 Schema、代码规则和独立合成示例；不能按文本关键词批量删除。
2. 分别批准真实原件读取/私有备份、代码历史保管、原 Hash 校验及兼容迁移范围。
   私有原数据不更名、不改量、不改日期/PIT。Legacy 与 SOURCE_002 的保管与身份分开。
3. 冻结维护窗口中的写入，重核全部 Ref、开放 PR、23个 Tag/Release、CI、复算和
   其他固定 SHA 消费者。协调开放 PR；实际拓扑和隐藏引用仍须新一轮平台核验。
4. 在获准隔离副本中模拟实际完整拓扑，建立全量 Commit/Tree/Tag 与原内容 Hash
   映射；验证源码字节、原始模型结果、Golden、Canary、PIT与来源门禁。出现未知
   依赖、范围外修改、错误 Hash、缺失证据或业务结果变化即停止。
5. Owner 审查精确不可逆操作清单后，才分别批准历史发布/强推、Tag/Release及可见性
   处置。即使代码兼容测试通过，也不能自动越过这些门禁。
6. 清除后由独立读取重新验证平台 Ref、对象可达性、源码定位、CI及公开分发；
   协作者避免将旧历史推回。平台缓存/PR引用须与 GitHub 协调，Fork、克隆及既往
   下载不能靠本地删除撤回。支持资格不能预先保证。

Commit/签名、PR差异及第三方副本影响依据
[GitHub 官方历史清理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。
临时 Private 需要另外授权，公开 Fork 不会因此变私有；访问和功能影响须按账户
条件核对，见 [GitHub 可见性说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)。

普通提交及受控私有备份可保留恢复材料；把污染旧 Ref 恢复公开会再次暴露对象，
不能作为自动回滚。恢复操作也需明确授权。当前真实历史仍未清理，既有 Tag、
Release、研究证据和 source authority 均未改变。
