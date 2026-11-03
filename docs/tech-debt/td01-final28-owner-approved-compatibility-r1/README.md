# TD01 — 本次Owner批准的28项历史代码身份

TASK_ID=`BLUEBERRY_TD01_FINAL28_COMPATIBILITY_IMPLEMENTATION_R1`。

Owner 在本次正式指令中批准集合 **TD01-FINAL28-BDCFD0B86A85B454** 的28项精确
Commit、Path、Blob OID和SHA256，允许接入现有身份工具、修复原3个兼容测试、
创建独立Draft PR并执行完整验证。该决定从本次指令生效，不追溯声明过去已获批准。

[机器可读的新Owner决定](owner-decision.json) 使用
`NEW_OWNER_APPROVED_CODE_BASELINE`，不把本次批准伪装成原有独立冻结证明。
原本地审核包和其中的PENDING记录保持不变。

## 精确批准集合与校验链

[reviewed-set.json](reviewed-set.json) 是原审批集合文件的逐字节副本，SHA256为：

`bdcfd0b86a85b4548a92d0010c6be9d6eef858cb18aea2e40ea3b1942279368a`

它仍保留审核时的 `NEW_OWNER_APPROVAL_REQUIRED` 字段，作为历史快照。
当前准入由本次独立Owner决定及其封存Hash授权，不靠修改原快照获得许可。
28项包括原S2历史测试1项、pre-TD03G历史测试26项及旧受控诊断测试1项。

实现逐次检查Owner决定、集合完整Hash、28项数量/身份及既有清理定位，随后复用
`historical_code_identity` 的精确版本、Path、类型、Blob和原始字节SHA256校验。
`rewritten_history` 的封闭映射不改动；不搜索同名当前文件或其他匹配版本。
PENDING决定、篡改集合、其他版本、额外源码、伪造JSON或损坏字节继续拒绝。

原65项代码、3项技术文件、14项运行源码的清单、Hash与独立依据均保持不变。
本PR只提交批准集合的身份元数据，没有提交完整审核压缩包或28份历史源码副本。

## 原三个消费者及回归范围

以下测试文件、业务断言、AST比较规则、计数及原预期Hash保持原样：

1. `backend/tests/local_auth/test_historical_source.py::test_reviewed_fixed_commit_exists_and_blobs_match`
2. `backend/tests/test_td03g_historical_compatibility.py::test_historical_reader_adaptation_preserves_every_original_test_body_and_hash`
3. `backend/tests/test_td03g_historical_compatibility.py::test_td03f_controlled_diagnostic_keeps_assertions_on_its_exact_old_source`

修复前重新运行：正常历史3 PASS，清理图3 FAIL；新增28项读取测试在清理图为28 FAIL。
首次修复后两图定向验证均49 PASS，包含原3项与新身份/拒绝回归。
没有修改三个消费者、增加skip/xfail或放宽Hash验证。

三项既有“未授权来源”负例显式使用PENDING Owner决定fixture，保持原断言和拒绝原因。
fixture只更换测试用授权状态，不模拟成功结果；新回归同时检查真实Owner记录封存、
集合绑定、无追溯批准、错版本/额外文件、原Blob/SHA256、无元数据图及非所有者模式拒绝。

本轮在正常历史与既有清理图完整重跑身份、预检、历史合同、V1/V2公开代码演练、
增量保护和TD03G相关测试，包含原65/3/14项与新28项；不以往轮通过记录代替。
另核验原CI身份preflight、固定基线公开增量门禁、工作簿分发保护、Ruff、Format、
以及既有 `mypy backend/app backend/research`。实际结果与HEAD/Run以任务回执及本PR CI为准。

## 未扩大的权限

代码身份批准不开放真实XLS、SOURCE_002正文或业务数据发布，不批准引用的其他
配置、证据、fixture实现、模型或训练数据。没有重新运行filter-repo、恢复旧Git对象、
改写远端历史、修改既有Branch/Tag/Release/PR或服务器。
原仓库继续Public；只创建独立Draft PR，不执行Ready、Merge、Release、Deploy或P35发布。
