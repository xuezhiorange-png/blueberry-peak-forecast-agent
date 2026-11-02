# TD-01I：未来远端准入与保护条件

**当前状态：仅本地合成演练。没有创建远端仓库，没有配置 GitHub 保护或真实审批。**

| 性质 | 本轮状态 |
| --- | --- |
| V1 固定根、原 38 项合同 | 本地真实执行；原历史记录保留 |
| 多提交、两轮 PR、独立预期字节、普通 Merge、Base 执行器 | 受控合成图实际验证，详见机器报告 |
| 所有对象/中间 Tree、完整闭包及负例 | 本地验证；不以干净 Head 代替历史检查 |
| 新远端 Actions / Owner Review / Branch Protection | NOT_RUN / NOT_CONFIGURED |
| 任意代码语义中不存在经营字面量 | UNVERIFIED，须独立人工审核 |
| 首次公开上传前的保密强制 | UNVERIFIED，CI 不能撤回已上传对象 |
| 原公开历史风险已经消除 | false |

## Owner 后续必须分别决定的配置

1. 确定干净代码的远端身份及公开范围，原仓库的可见性/私有历史处置另行授权。
   模板明确拒绝原项目仓库身份，不抓取旧项目完整历史；创建公开仓库不等于处置原历史。
2. 独立审核首次 V2 Bootstrap。V1 Root 没有 V2 门禁，不允许由该 Bootstrap PR 自己执行 Head
   门禁并宣告通过。合成演练由仓库外可信执行器起步；真实流程需另行建立可信准入。
3. 将执行器 Manifest 的预期身份放在 Head 无权修改的保护配置中；它只是源码定位，不是审批结果。
   模板执行已声明 Base 的验证器、CI runner、事件适配器和安全测试，缺失/不匹配立即失败。
4. 配置真实独立审查传输，绑定 Base、Head、每个 Commit/Tree/Parent、文件、合成生成器及完整字节。
   当前只实现外部固定 Hash 的合成演练文件，模板不启用此参数；不能把模拟文件用于真实 Owner 审批。

## 必须保护的检查与审查

| 对象 | 必须的强制策略 |
| --- | --- |
| Required Check | `public-core-v2-trusted-base` 成功，包含完整图门禁、独立安装、原 38 项、Head 24 项及 V2 负例 |
| 检查来源 | 组织级 Required Workflow 固定受信任来源/Ref，或独立 GitHub App 的受限状态发布者；仅匹配同名 Job 不足以防伪造 |
| main | 必须 PR、严格最新基线、禁止 Force Push/删除，禁止直接绕过 Required Checks |
| Owner/Reviewer | 独立审核，拒绝作者自审，修改后撤销旧批准；管理身份不得以 bypass 绕过同一门禁 |
| CODEOWNERS 范围 | Gate、CI runner、Workflow、事件上下文、执行器清单、依赖锁、合成生成器及来源规则 |
| 权限 | Actions `contents: read`，checkout 不保留凭据，不传部署密钥或业务数据库/数据目录 |
| 新依赖 | 单独审核完整依赖及制品锁闭包；R1 不根据一个 APPROVED 字段自动改安装合同 |
| 增量数据 | 未知二进制、真实身份关系和经营统计拒绝；合成数据须固定生成器和完整字节证明 |

以上全部是待配置要求，不是已生效的保护。Workflow 是 PR 可修改文件；在真实 Required Workflow、
Owner 保护及受限检查来源未生效前，模板本身无法证明恶意 PR 不会伪造同名成功结果。
不使用能携带高权限执行未经信任代码的事件；模板只声明 pull_request、main push 和 workflow_dispatch。

## Checkout 与执行分离

模板单独取得声明 Base 的执行器快照，固定其身份；候选对象库用 git init 建立，仅请求显式
Base/Head 祖先，不 Mirror/Fork，也不 Fetch 所有 Branch/Tag。候选必须完整，不能 Shallow/Alternates。
模板中的浅 Base 代码快照仅作外部执行器载体，不能充当候选对象集合的验收证据。
本地模拟另验证了 readonly Origin 与测试 Merge；Base、Head 和测试 Merge 三个身份各自保留，
测试 Merge 不能自行变成受信任 Base。

未来真实网络接入、初始 Bootstrap、保护规则防绕过以及真实审查传输尚未运行，全部 UNVERIFIED。
在这些配置完成独立验收之前，真实新增内容不会因此模板取得公开许可。

本轮到一个 Draft PR 和原仓库 exact-head CI 为止；不配置上述远端项目，不 Ready/Merge/部署。

当前图和对象库能够检测 ref 回退后留下的悬空污染。若对象已在外部被改写并 GC 移除，且没有
可信的历史登记，当前图无法证明它从未出现；该性质 UNVERIFIED，需要远端禁止改写及独立记录。
