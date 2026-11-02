# TD-01 已清理历史兼容修复 R1

任务：`TD01_CLEAN_HISTORY_COMPATIBILITY_FIX_R1`。

正常 main 基线：`768f7f6b54f51797a9a8cfec6191c84e69f9687b`。
复用的既有清理图基线：`0f04035b54fc9fb96a2578beeb562e4ad4150faa`。
没有再次运行 git-filter-repo，没有替换远端历史，没有处理 GitHub PR 历史引用或缓存。

**结果 PARTIAL：原 12 FAIL、9 ERROR 及三处 CI 的身份定位阻断已修复；另外发现的独立身份审核缺口保持 BLOCKED。**
本次提交仅包含代码、CI、回归测试和技术身份元数据，不包含 XLS、模型、数据包或原始 Git 副本。

## 根因归并

原 21 个报错不是 21 个独立缺陷。按需要独立修改的合同边界归并为四个实现根因：

| 根因 | 表现 | 修复 |
| --- | --- | --- |
| R1：历史文件定位依赖旧 Commit 存在 | 已批准 65 项代码、3 项技术文件及 fixture 的重复失败；S1 包身份和旧认证技术回执不能读取 | 复用原 Blob/独立 SHA256 验证链，加入封闭的精确改写定位；修正 fixture 读取入口 |
| R2：CI 将旧 Commit 存在当作源码身份验收 | 三个 Job、7 条 Git 对象预检查失败 | 三处 stdlib-only preflight 校验原 main/read/decision 三项 Blob 和原独立 SHA256，不再要求旧 Commit 对象存在 |
| R3：公开增量门禁基线仅能通过旧 Commit 定位 | `REVIEW_BASE_UNAVAILABLE_OR_INVALID` | 保留原 BASELINE 常量，只有原/新整个文件树 OID 相同的封闭定位才可解析 |
| R4：V1 保留检查直接访问旧基线 | V1/原 CI 版本定位失败 | 使用同一完整文件树身份定位；保留原 V1 文件检查和原 CI 冻结版本 Blob 身份 |

另有独立的 R5 身份依据缺口，不属于可通过定位算法自行修复的错误：原指定未准入测试，以及扩展回归中 TD-03G 的额外历史源码。
因此共有四类实现根因已修复、一类审核依据缺口未解决；GitHub 平台侧事项另列，不混算成代码失败。

## 封闭定位及原身份要求

`identity-locators.json` 只含既有预演中九个需要的精确 Commit 定位，不发布完整 Git 副本或全部引用。
组件固定该文件的完整性 Hash；这是定位表的代码评审信任根，不是重新批准源文件的 expected Hash。

源文件仍逐项核验原 Commit/Path 的登记、普通 Blob 类型、原 Blob OID 和原 SHA256。
TD-01E 原 65 项清单、PR #786 原三项技术清单及其 Hash 均不改，独立冻结字段仍检查。
不搜索“相同内容”，不使用当前同名文件，不接受 JSON 自报批准，不把任意仓库注册为受控隔离图。

清理图必须具有指定清理基线的真实祖先关系；拒绝旧原始历史或目标 Blob 的对象污染，拒绝 shallow、alternate、graft、promisor pack 和 replace ref。
只查精确对象的类型及 Git 元数据，不读 XLS 正文，也不把本检查当作全历史公开审核。
原正常历史仍使用其原 Commit，不改变原工作方式。

`current_code_fixture` 从源图复制已经验证的代码和解析后的 Commit/Tree 元数据。
清理图使用映射后的元数据，临时 fixture 不恢复旧 Commit；该 fixture 也不能取得 Blob-only rehearsal 能力。
旧/映射历史元数据污染真正的代码隔离演练时仍拒绝，负向测试保留实际 Git 对象注入。

## 两项有独立依据的技术材料

原失败合同还读取以下对象，现分别使用已存在的冻结字段及原 Commit 绑定，未用新算 Hash 自行批准：

| 精确对象 | 独立原依据 |
| --- | --- |
| `frontend/package.json@52b5a80f89c59130917b29c9097d63076eab4acb` | S1 preflight 原 JSON 的 `source_evidence_sha256` 与 `base_main_sha` |
| `docs/v0-18/s1/local-auth-runtime-r1.json@e92507f5213058e07515ef7f7efc2d71edf4488d` | 当前冻结技术回执中 `r4_correction.previous_r3_snapshot.evidence_sha256/head_sha` |

这两条精确技术内容读取不能推广为一般配置、研究证据或业务数据准入。

## 本次允许修改的 CI 与冻结证据的区别

本 Owner 任务明确授权修复 CI 硬编码存在性检查，因此当前 CI 程序可以在本范围内更新。
三处 preflight 均位于固定 Python 3.12 配置之后、业务测试之前，不增加依赖或放宽失败条件。
它们验证同一个原 Commit 的原源码身份，涵盖原 7 条预检查的源码要求，并同时检查三项源码的 Blob/SHA256。

V1 保留检查不再把当前 CI 程序当成不可演进的旧版本副本；原 CI 冻结版本仍必须匹配
`a664eba14ca40f18cebbf5ca952f53ebd549f719`，原 V1 文件的内容/工作树断言保留。
新增回归检查当前三个 Job 必须运行身份 preflight，不允许 continue-on-error。
没有修改旧 CI 记录、业务断言指纹、Golden、原 expected Hash、预测模型或冻结研究结果。

## 实际修复前后验证

| 检查 | 正常历史 | 已有 XLS 清理图 |
| --- | --- | --- |
| 修复前：原 21 个失败用例 | 21 PASS | 12 FAIL、9 ERROR |
| 首轮修复后：原用例加 12 项安全回归 | 33 PASS | 33 PASS |
| 扩展相关回归，含 V2 完整安装/等价验证 | 278 PASS | 273 PASS、5 FAIL |
| 最后诊断修正的定向复核，含原断言指纹 | 21 PASS | 17 PASS、4 FAIL；均为未准入源码 |
| 按唯一用例最终状态合并 | 278 PASS、0 FAIL/ERROR/SKIP | 274 PASS、4 FAIL、0 ERROR/SKIP |
| 三个 CI Job 的身份 preflight 原命令 | 全部 PASS | 全部 PASS |
| 原公开增量基线门禁 | PASS | PASS |

完整相关回归中的 V2 等价测试在两种历史均通过，仍验证原 38 项 V1、24 项 active-head 功能、15 项安全及15项 reviewed-head 测试。
没有再次执行历史清理、模型训练或真实数据复算。

最后定向复核修正了未准入路径的错误分类：已知精确逻辑版本但路径没有准入依据时，仍拒绝读取，并报告 source unavailable；
不再错误地报告逻辑 Commit 未定位。这没有使未准入对象获得读取权限。
各轮日志和 XML 全部保留；合并状态不冒称一次全绿运行，四个剩余失败也不转成 skip/xfail。

全仓 Ruff/Format 通过；CI 规定的 Mypy 范围 `backend/app backend/research` 通过，修改的门禁脚本另外通过定向类型检查。
额外扩展到全部 scripts 的检查在未改基线和本分支均出现 129 项错误，未修改无关脚本或据此放宽 CI 范围。

## 保持 BLOCKED 的对象

1. `backend/tests/forecast_intelligence/test_v0_17_s2_decision_service.py@320f2046e3105b1b55da9cb037892571110b584a`：
   继续缺少匹配的独立既有身份依据，没有加入原 65 项或新技术材料清单。
2. TD-03G 三个扩展历史核对用例涉及的额外 41 个旧版本代码身份：26 个测试源码、14 个运行源码和1个受控诊断源码。
   它们不在原封闭身份清单内。对其中15项有现存 TD-03G Hash 字段的精确对象，已核对请求的旧版本，匹配数为 **0/15**；
   这些字段对应修改后的版本，不能替代所请求的旧版本。其他26项在本轮复用的审核记录中未取得独立匹配的旧源码字段。

精确 Commit/Path 清单见 `blocked-identities.json`；这些是针对失败消费者的代码范围核对，不是重扫历史数据。
相关源码消费者的断言、数量和失败条件都保留。因此清理图中四个测试继续实际失败，而非被绕过。
后续须取得匹配旧版本的独立依据并单独审核，不能把本次计算出的实际 Hash 当作新批准依据。

## 仍需平台侧处理的事项

GitHub 管理的 PR 历史引用、缓存及服务端对象清除仍需后续独立授权和平台流程；本轮没有处理原760个PR引用。
Tag/Release、分支保护、生产服务器、P35 和真实远端历史均未修改。
正常仓库的 Draft PR CI 结果不等于 GitHub 端已完成清理，也不等于剩余四项身份缺口已关闭。
本轮仅提交兼容修复和审核材料，到 Draft PR 后停止，不自动 Ready/Merge/Deploy。
