# TD-01D：保密边界、增量门禁与历史处置依赖

TASK_ID：`BLUEBERRY_TECH_DEBT_TD01D_PRIVACY_BOUNDARY_AND_HISTORY_DISPOSITION_GATE_R1`。
Owner 策略为 `PUBLIC_CODE_PRIVATE_REAL_DATA`，公开演示为独立 `SYNTHETIC_ONLY`。
本轮没有原件/来源分区读取、真实历史重写、强推、Tag/Release/可见性修改或部署许可。

基线为 `e2d0ffa233483821e4fed3d429e317510dfcfcc1`，PR #777 已合并。
前置 main CI `41192763302` 起初为 PENDING，随后远程核实同 SHA / push /
completed / success。它与本 PR 的最终 exact-head CI 分别记录，不互相替代。

## 四份正式输入与身份保持

唯一正式候选输入为原 TD-01C CSV、对应审查摘要、TD-01B 的742行 Ref 清单及
TD-01C 历史合同迁移方案。代码固定它们在本基线的 Git Blob 身份；再验证原
register SHA256、1658行及418/1121/107/7/5的原分类数量。原行的全部字段、路径、
引用、建议和来源身份完整保留，新增 `ORIGINAL_ROW_SHA256` 用于追踪，不更改旧文件。
当前公开文本结构核对是补充证据，不新增、删除或重排正式候选身份。

分级机器清单见 [完整登记](td01d-classified-register.csv)，汇总/优先路径及当前
公开结构标记见 [summary](td01d-classification-summary.json)。分类器可运行：

```bash
python -m backend.app.etl.history.privacy_boundary \
  --repo . --output-dir /tmp/TD01D-new-review-package
python scripts/ci/check_public_increment.py --repo .
```

当前主分类为418个 PUBLIC_CODE、1128个 FROZEN_HISTORICAL_EVIDENCE、4个
POSSIBLE_REAL_BUSINESS_INFORMATION、103个 NEEDS_OWNER_DECISION、5个
COMPRESSED_CONTENT_NOT_INSPECTED。七个大文本继承冻结证据角色，不因此认定敏感。

所有1658条的经营保密判断仍是 `UNVERIFIED`，公开许可为 `NOT_ESTABLISHED`。
PUBLIC_CODE 只说明代码角色和一般公开策略，不证明其中任意业务字面量已获准公开。
原候选的 PUBLIC_SYNTHETIC 数为0：不能把文件名、关键词或自行声明的标签当作独立
生成证明；这不表示所有冻结合成研究结果都变成真实数据。现有 TD-01C 五个产物
不在该旧候选快照中，增量门禁另外按可信生成器完整复算处理。

## 内容核对与精简决策

明确核对公开的 factory aliases、两个 Base registry、生产计划和面积/成员配置的
字段形状；只输出“身份字段/映射结构/精确量或面积字段/地理字段/来源字段存在”
等通用标记，不输出名称、关系、坐标或经营数值。结构存在不证明是真实数据，
更不等于泄露确认或公开许可。生产计划为指定补充核对，不偷偷加入旧1658条。

V0.8/V0.15/V0.19 各从原登记的数量/曲线类 JSON 中按稳定路径排序选取代表；
大于2MB时只保留元数据状态，不重新打开大文本。其他冻结研究证据按角色保留
并复核，不能自动宣布全部敏感或全部安全。五个压缩资产重新比对 HEAD Tree 的
Blob ID；本轮不读取、不下载、不解压其内容，也不将其视为 Legacy XLS。

Owner 只看一份 [九项决策总表](td01d-owner-decisions-r1.md)。默认值是建议，
不是删除、公开、脱敏或历史改写许可。技术优先路径为16个：指定配置、全部压缩
资产及三个版本的固定代表；选择不依赖模型误差、产量大小或有利结果。完整1658行
供技术追踪，不要求 Owner 逐行批准。

## 增量保护如何执行

保留 TD-01B 脚本及全部路径/已知 Blob 阻断，不改 .gitignore、打包或原有 CI 判据。
新增 unit/contract 测试在既有 Golden 和全量 Canary 中调用本门禁；出现需要复核
的增量时断言失败，CLI 返回非零。没有新增 Job、路径跳过、warning ignore 或重试。

门禁用两个 Git Tree 的路径/对象身份比较，默认与本次已核验基线 e2d0ffa 比较。
它不以1658个旧候选使当前 CI 永久失败，也不把它们登记为已批准公开。原冻结/
配置候选变化须复核；普通代码角色仍按新增内容检查，字段类型、Schema 与计算
表达式本身不会被当成经营数据。四份正式输入被改动或删除也不能静默换成新基线。

已知历史 XLS 或压缩对象改名后仍先按对象身份拒绝，未知工作簿/压缩/二进制仅
按元数据提出复核，不打开它们。新增表格、经营量/面积字面值、身份映射字面量、
真实来源路径或被改名为代码/文本的表格会产生明确原因；日志只含路径和原因，
不回显实际值。`REVIEW_REQUIRED` 是人工判断请求，不是确认泄露或自动删除命令。

复用 TD-01C 的封闭生成器和整个容器绑定：先验证生成器、父包及规范化依赖的
既有源字节，才执行它；修改生产者不能顺便批准自己的新样本。默认已登记种子
可直接复算；其他种子须有与原生成器字节完全一致的完整 Manifest。只改名、
加入 SYNTHETIC 标签、伪造 Hash/Manifest 或沿用真实重量都不构成通行依据。
已验证 CSV/XLSX/Manifest 按 Git Blob 身份匹配，可改展示文件名，不读取未知工作簿。
新增分级 CSV 也必须与本分类器的元数据输出字节完全一致。

这是公开增量的有限静态/身份检查，不是通用 DLP、OCR、任意编码反混淆或公开
安全认证。它不撤回历史内容，不证明漏检文件安全，也不替代 Owner 对真实经营
信息的判断。没有普通 JSON 审批开关或自动真实来源准入。

## 真实历史处置依赖与停止门禁

[技术依赖矩阵](td01d-disposition-dependency-matrix.json)覆盖53条依赖：两份
Legacy XLS、固定代码定位、五个压缩资产、23个 Tag/Release、13个开放 PR，
以及配置/冻结研究/代码/合成/私有访问类别。数据身份来自四份正式材料和只读
Git/GitHub 元数据，不从原件提取内容。

[开放 PR 元数据](td01d-open-pr-impact-metadata.json)为本任务 PR 创建前快照。
13个开放 PR 的 Head 均可达两次已知引入之一；这说明历史变更需要协调其 SHA/
基线/CI，不表示已逐个认定业务影响。未复制 PR 正文或业务细节，不修改其他 PR。

依赖顺序必须满足：

1. Owner 决定真实精确关联、经营统计和衍生资料的分级；Legacy XLS 按当前策略
   建议为 PRIVATE_REAL。压缩资产、未知来源与冻结证据先保留并复核，不能批量删除。
2. 分别授权私有保管/备份、读取和审计；正式训练/回测保留原日期、重量、空间/
   品种/产季关系、来源版本和 PIT，不为脱敏修改正式源，不补缺失为0。
3. 对固定320f2046/e9812e82/0124371b等 Commit 定位准备经审查的版本化兼容迁移，
   保持原源字节、原 expected Hash、旧评价事实和断言。不能保留污染旧 Commit
   公开可达以规避清理，也不能删除检查、换成合成标签或重新评分恢复 CI。
4. 重核全部 Ref、23个 Tag/Release、开放 PR、回测与模型/fit的代码身份消费者；
   审查实际拓扑、旧→新定位和回滚保管材料，未知依赖或任意原 Hash 不符即停止。
5. 普通 PR 可实现新元数据报告、代码定位适配和非破坏性保护；真实历史发布、
   强推、旧 Tag/Release、仓库可见性及其他远端不可逆操作分别需要新授权。
   本任务不提供这些执行入口，不移动或重新签发已发布 Tag。
6. 真正处置后再独立核对远端可达性、源码归档、权限、来源与完整 CI，协调协作者
   防止旧历史重新推回。缓存、PR引用与外部副本另行核验，不能宣称自动全网清除。

Git SHA/签名、开放 PR 和外部副本的影响见
[GitHub 官方历史清理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。
临时 Private 也不使已有公开 Fork 自动变私有，功能/访问影响需另外核对，见
[GitHub 可见性说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)。

原真实回测、SOURCE_002 与 Legacy 身份隔离、as-issued 天气/再分析、PIT、模型
及预测服务保持不变。本轮只到 Draft PR 与实际验证结果，不执行历史清理或 V0.22。

## 本地验收

36项新增定向用例与相关 ETL、CI、版本和历史合同回归合计177项通过；没有新增
skip/xfail或修改旧断言。包含独立进程输出一致性、生成报告精确复算、已知 XLS/
压缩 Blob 改名且禁止正文读取、伪合成标签/Manifest、数字字符串经营量及历史
候选删除的负向用例。原有3条重复 OpenAPI Operation ID诊断保留，不在本轮修复。
Ruff、Format以及应用/研究目录和新增脚本的严格 Mypy均通过（642个源码文件）。
提交前的完整暂存 Tree 增量检查为 PASS；最终 HEAD 的完整 CI另以实际运行记录
报告，不能用本地结果或前置 main CI替代。
