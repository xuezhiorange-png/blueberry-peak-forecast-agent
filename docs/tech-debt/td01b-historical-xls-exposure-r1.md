# TD-01B：历史 XLS 公开引用与防再引入

TASK_ID：`BLUEBERRY_TECH_DEBT_TD01B_HISTORICAL_XLS_EXPOSURE_R1`。
Owner 本轮授权元数据核验、非破坏性保护及一个 Draft PR；未授权历史重写、
强推、Tag/Release/可见性修改、Ready、Merge 或部署。

## 核验结论与边界

基线 main 为 `1086c5f8ae983e16cef7c09f78ea68c25a73db48`。
前置 main CI [41179040429](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/41179040429)
起初仍在运行，随后远程核实为同一 SHA 的 push / completed / success。
仓库为 Public。当前 main 的 Tree 已不含两个工作簿，但历史公开风险仍然存在。

| 路径 | Git Blob ID（不是训练行集合 SHA256） | 对象大小 bytes |
| --- | --- | ---: |
| `data/raw/2024_2025_receipts.xls` | `3413dbbc284312e75a2df98992a6ab66cfa87dbd` | 27,880,960 |
| `data/raw/2025_2026_receipts.xls` | `a045348c4c72507ae367b4e30f267fcf19c490c1` | 33,155,072 |

合计 **61,036,032 bytes**。数据保管、历史研究读取与公开发布是不同权限；本轮
没有取得逐对象公开许可证明，状态为 `PUBLICATION_AUTHORITY_NOT_PROVEN`，
不据此断言已经确认未经授权泄露。

2026-10-31 07:34:18 UTC 的开发前快照包含 719 个公开 Branch、23 个 Tag：

- 709 个 Branch 的当前 Tree 仍含两个工作簿；10 个 Tree 已不含，包括 main。
- 全部 23 个 Tag 的 Tree 仍含两个工作簿，对应全部 23 个 Release。
- 23 个 Release 的独立 assets 数量为 0；自动生成的源码归档不属于独立 assets。
- 742 个已观察 Branch/Tag 的祖先历史均可达文件引入提交，包括当前干净 main。
- 观察到的 Tree 中，这两个已知 Blob 只出现在表列原路径；没有观察到其他路径别名。

逐 Ref 的对象、Commit、Tree、Blob 及历史可达状态见
[确定性 CSV](td01b-public-ref-exposure-r1.csv)；
[JSON 摘要](td01b-historical-xls-exposure-r1.json)包含清单 Hash、23 个 Release
的 ID/Tag/解析后 Commit/附件数。清单是本分支开发前的远程快照，不包含随后
创建的 TD-01B 分支，也不推断隐藏 PR Ref、Fork、历史克隆、缓存或第三方副本。

## 最早引入与已发布版本

同一对 Blob 有两个公开可达的初始引入提交，父提交均为
`c8543965f67136c27b7502eed9510f0be845f426`：

| 提交 | Git 记录的 committer 时间 | 是当前 main 祖先 |
| --- | --- | --- |
| `6f9912f36a29aca6fef0de028cc3c9fd7caceaae` | 2026-06-20 02:00:53 +08:00 | 否 |
| `2dfddc1eaa41d81cc249cae1358e5db7167fd318` | 2026-06-20 02:22:51 +08:00 | 是 |

第一项是本次可核实的最早**Git 记录引入**，第二项是 main 祖先链引入；
提交时间不证明实际首次公开上传时间。

`v0.21.0` 注释 Tag 对象 `95a495c53e62d25cc8764a1fcb18a2195fe0caa1`，
解引用至 `3bf2e172822f8b375cf30a0e2c0fcb96ebade722`，Tree 为
`3970c4e3fbde7d2d34c2f0eb609b48a1d82cc722`，仍引用上述两 Blob。
本任务没有修改任何旧 Ref 或 Release。

## 现有保护、已证明的差额与最小修复

保留 `.gitignore` 的 `data/raw/*.xls` / `*.xlsx` 和原有
`test_legacy_workbooks_remain_untracked` 两路径索引断言。
忽略规则不能阻止强制加入索引，也不会改变历史 Tree。
现有 Docker 构建上下文只允许源码，已排除根目录 `data/raw`；
但同名文件若误放到允许的 `backend/` 中仍可能进入构建上下文。
原配置下，实际 Git 归档与 setuptools sdist/wheel 的两个合成保护测试先失败，
另两个故意撤掉保护的对照通过：**RED 为 2 failed / 2 passed**。

本轮仅补充：

1. 元数据脚本检查当前 Tree 的保留文件名及两个已知 Blob ID，别名路径也拒绝。
   `GIT_NO_LAZY_FETCH=1`，只执行 Tree 解析和 `ls-tree`，不读取 Blob 正文。
2. 在既有 static Job 中运行上述检查；Golden/完整 Canary 同时保留原路径断言
   并运行新增测试，不增加跳过规则或新 Job。
3. `.gitattributes` 的 `export-ignore` 排除后续提交源码归档中的两个保留文件名。
   `MANIFEST.in` 的全局排除规则保护后续 sdist/wheel，实际构建验证包成员。
   `pyproject.toml` 保持原字节，避免改动已有历史合同绑定。
4. `.dockerignore` 增加两个保留文件名的嵌套路径排除；原有合法合成 XLS/XLSX
   不受影响。既有 compose-smoke Job 真实构建 `FROM scratch` 合成上下文，
   同时证明正常排除和故意放行后被检测；不启动业务容器或数据库。

运行：`python scripts/ci/check_workbook_distribution.py --repo . --tree HEAD`。
违规返回非零退出码；不忽略错误。该脚本不解析工作簿，不是新的数据审计平台。

## 验证与证据保管

隔离工作树不物化 `data/raw`；实际工作簿未打开、解析、下载或重算内容 Hash。
Git 核验限于 Ref、提交关联、`ls-tree`、对象大小等元数据。
测试中名称相同的文件均为新建纯文本 `SYNTHETIC_ONLY`，不是业务工作簿。
已知 Blob 的别名负例只在无远程的临时 Git Tree 中引用缺失对象 ID，正文始终不存在。

新增测试覆盖路径索引拒绝、已知 Blob 别名拒绝、无正文/无懒加载、源码归档、
sdist/wheel、合法合成文件保留以及 CI 错误传播。Docker 证明使用 GitHub
compose-smoke 的真实 Docker；本机没有 Docker，不能把本地静态检查称作构建通过。
最终测试数量、完整 exact-head CI 和 Docker 合成回执在 PR 及交付回执中记录。
本地原始日志、JUnit、备份和远程元数据快照保留于仓库外受控目录；公开清单
仅含路径、Git 身份、大小、状态和公开 Ref/Release 元数据。

这些保护针对当前/未来源码与标准打包路径；不清除旧 Tag 的归档，不撤回
既往下载，也不证明未知改名、改内容的未追踪文件安全。已知 Blob 的 Tree
阻断不依赖读取正文；本轮不扩张为私有磁盘内容扫描。

历史处置须另获明确授权，见
[Owner 决策方案](td01b-historical-disposition-decision-r1.md)。
**取消追踪与本轮防再引入均不代表历史公开风险已消除。**
