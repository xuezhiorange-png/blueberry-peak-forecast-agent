# TD-01I：公开候选核心 V2 增量门禁

TASK_ID=`BLUEBERRY_TD01I_PUBLIC_CORE_V2_INCREMENTAL_SECURITY_GATE_R1`。
开发基线为 `fe494971c92f1d951f5acfeb6a70b85a4aff23ac`，PR #781 已合并。
前置 Main CI #41293572114 首次核验为运行中，后续独立核验为 push / completed / success，
head_sha 与基线一致。最终 PR exact-head 结论单独记录在 PR 回执，不能用前置 CI 替代。

## 新增能力

V1 仅接受一个根提交。V2 增加多提交、功能分支、准确 Merge Base、经模拟独立审查的 Merge、
合并后第二个 PR 及 Checkout 中 Base/Head/测试 Merge 的区分。所有 Git 写入只发生在自建隔离库。
原项目的工作流、依赖、预测数学、来源、历史证据和 V1 清单/测试均不修改。

| 组件 | 用途 |
| --- | --- |
| `backend/app/core/public_core_incremental_gate.py` | 独立 stdlib 只读门禁及 CLI |
| `public_core_incremental_rehearsal.py` | 受控合成 Git 图、独立预期字节审核及两轮 PR 演练 |
| `public_core_incremental_ci.py` | 独立执行器的离线调用适配 |
| `public_core/td01i_v2/` | 可信 Base 的 CI 执行器、公开负例、事件上下文和未来 Actions 模板 |
| `backend/tests/ci/test_public_core_incremental_gate.py` | 正反例、身份、来源及完整安装回归 |

## 信任边界

启动身份固定为 V1 Root `04457546f5577d4e44effb808154a6aa08b45846` 和 Manifest SHA256
`4fa783f4bbccab468f7de6ac8a8b4cd2807503f206e1ea510e435ed296f82cc0`。
根源码按既有 Manifest 核对 Blob 及 SHA256，保留原验证器 seal 字面量的既定归一化规则。

TRUSTED_BASE 是可信调用方指定的 Base；PROPOSED_HEAD 和逐提交 PROPOSED_DIFF 是待审内容。
独立合成审查在仓库外声明预期代码字节，独立计算预期 Tree，再核对实际 Commit、Parents、Tree、
完整变更和文件身份。读取 Head 新 Hash 再自称批准不是审查方法。
合成审核文件必须在候选库外、由调用方固定内容 Hash；Head 内文件、软链和自报 APPROVED 均无权限。

PASS 仅表示指定图和身份范围内没有未批准增量，不代表真实经营资料已获公开许可。
正常代码无独立审查时为 REVIEW_REQUIRED；未知数据/二进制、禁止身份、伪造权限和历史污染为 BLOCKED。
新依赖闭包即使提交了审查字段仍需独立版本化安装合同，R1 保持 REVIEW_REQUIRED。
一般代码可能含经营字面量，程序不自动宣称语义保密审查通过。

## 对象及时间顺序

1. 先检查本地 Git 配置、对象存储、Alternates/Grafts/Shallow、远端、Ref、工作树类型和模式。
   外部 include 在 Git 加载前被拒绝；不跟随私有目录或网络。
2. 枚举完整对象集合，并逐提交检查 Tree。已知禁止 Blob 在任何 Blob 正文读取之前被拒绝。
3. 指定 Base、Head、测试 Merge 的祖先闭包必须等于整个对象集合；悬空/未知对象和额外 Ref/Tag 阻断。
   根只能是固定 V1 Root，不能夹带其他根或原项目历史。
4. 核对准确 Merge Base、每个 Parent/Tree、逐 Parent 变更、删除和新增。相同 Blob 的改名显式关联；
   修改后改名保留为删除+新增，不用内容相似度猜测。中间提交的内容不会因最后删除而逃过检查。
5. 对审核来源、固定生成器闭包及完整合成产物逐字节核对，检查 Manifest 的 seed、来源及四份导出 Hash。
   真实文件不能改名或贴合成标签后准入。最后核对工作树及 `git fsck --full --strict --no-reflogs`。

保护范围接受普通 100644 Blob，不接受 Symlink、Submodule、LFS Pointer 或特殊文件模式。
R1 限制单 Blob 2 MiB、总对象 20,000；超限失败，不默默省略检查。
报告不含时间戳、用户目录、源正文或经营数值；不同进程可复核相同业务结果 Hash。

## 实际演练与独立 CI

机器结果在 [td01i-v2-r1/](td01i-v2-r1/)：信任边界、提交图、PR 审查矩阵、负向测试和 CI 等价报告。
这些是实际合成执行结果和技术身份，不是新的真实来源或审批证书。

演练先准入 V1 根，新增并分别审核两个代码提交，普通 Merge 后建立第二个 PR，再审核和 Merge。
另有 Base 已前进但 Feature 仍从旧 Base 分叉、测试 Merge/readonly Origin、删除中间未知数据、
删除中间禁止对象身份、错误 Base、错误审查、未知依赖和配置/存储负例。

完整 CI 演练先将 V2 执行器作独立合成 Bootstrap 审查并 Merge，然后对第二个 PR 运行：
从**已核验 Base 的固定 Blob**导出执行器到仓库外，Head 不提供执行器或审查权限。
入口门禁通过后，重新构建同一 V1 根，真实安装完整锁定依赖，执行原 38 项；再安装实际 Head，
比对所有已安装 backend 源码与 Head 字节，并执行原 24 项功能合同、可信 Base 的新安全负例及静态检查。
运行前后图门禁结果必须一致。

开发期的失败证据保留：初次独立链路因新增合成代码格式未符合 Ruff 失败；修正格式后，出口复检
发现命令变量覆盖导致错误执行，已更正变量所有权。没有删除断言、增加 skip/xfail 或放宽判据。
两类失败都保留在私有本地日志；公开结果不输出源正文或私有路径。

本地最终实测：48 项完整专项 PASS；相关旧防护、V1、历史代码、合成来源合同及新增执行器清单
合同共 182 PASS、1 个 integration 按选择器 DESELECTED（完整新环境集成已单独实际运行）。
28 个负向场景全部 BLOCKED；两轮 PR 审核/合并检查 PASS，最后图含 6 个提交。
完整独立 CI 为 22 条顶层命令退出 0；其中嵌套原 V1 的 11 条命令及 38 项合同真实执行。
已安装 Head 的 24 项功能、可信 Base 的 12 项安全测试和已审核 Head 的 12 项测试全部 PASS。
同图两次独立验证进程、两次独立构图进程的结果均逐字节一致。
Ruff/Format 全仓通过；strict Mypy 覆盖 648 个 app/research 源码，另显式核查两个独立公开脚本。

TD-01F 原 24 PASS / 1 BLOCKED 与 V1 28 文件、42 对象、38 项旧合同保持原样。
原仓库完整 Golden/Canary/PostgreSQL/Frontend 的 CI 与新的本地公开核心验收分别报告。

## 明确未验证的性质

真实远端尚不存在，真实 Review Authority/Required Workflow/Branch Protection/CODEOWNERS
未配置；全部远端执行和审批强制性质均为 UNVERIFIED / NOT_RUN。
当前的合成审查不能替代真实 Owner 决定，也不代表私有数据已经允许公开。
初始 V1 Root 没有 V2 执行器，必须先经过独立 Bootstrap 准入；模板遇到缺失会阻断，不改用 Head。

本轮不验证任意代码的语义保密性、OS 沙箱或远端首次上传前的数据外泄防护。
公开 PR 上传本身已经使 Git 对象可见，事后 CI 只能阻止准入受保护基线，不能撤回已经上传的内容。
因此真实远端准入前需要私有准备区和明确发布范围；不能把模板通过当成历史暴露已经消除。
真实 XLS、SOURCE_002、旧 Hash/模型/评分、PIT、Tag/Release 与真实 Git 历史均未改动。
