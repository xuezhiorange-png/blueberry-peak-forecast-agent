# TD01 最终定向历史兼容：14 项准入，28 项继续 BLOCKED

任务：`BLUEBERRY_TD01_CLEAN_HISTORY_FINAL_COMPATIBILITY_R1`。
基线：`3b292767f798424e53cc44ec6d6855ead35ba0b6`（已合并 PR #787）。
结果：**PARTIAL，原 4 个失败解决 1 个，仍有 3 个失败**。

## 实际修复及独立依据

只检查原 [42 项清单](../td01-clean-history-compatibility-r1/blocked-identities.json)
指定的 Commit+Path，没有重新清理历史、扫描数据或改写旧记录。

14 项运行源码在 `0124371b433d1b3c34e5e59a2a9a5e621a570f3b` 的完整字节
SHA256，逐项匹配既有
[`v0.18.0-version-closeout-r1.json`](../../v0-18/evidence/v0.18.0-version-closeout-r1.json)
的 `frozen_model_and_math_sha256[原路径]`。同样的修改前 Hash 也存在于 TD-03G
已封存的 `source-before-manifest.json`；该清单字节 SHA256 与 TD-03G 冻结记录的
`artifact_sha256` 字段完全匹配。TD-03G 修改后的 15 个 Hash 仍不是所需旧版本的依据。

新增 [封闭的 14 项登记](runtime-identities.json)，运行时只引用已有、已版本化的
V0.18 closeout 技术记录。目录 seal 只保护登记字节；每次读取还必须核对原有独立字段。
沿用 `historical_code_identity` 的原 Blob/类型/SHA256 校验及 `rewritten_history`
已封存的版本定位，不改变原 65 项登记、3 项技术文件登记或清理映射。
未修改这 14 个应用模块本身，也未改变任何模型、数学、数据或业务断言。

## 四个原失败测试的实际结果

所有 nodeid 均保持原样，未修改其函数、断言或预期 Hash。

| nodeid | 清理图修复前 | 清理图修复后 | 身份依赖 |
| --- | --- | --- | --- |
| `backend/tests/local_auth/test_historical_source.py::test_reviewed_fixed_commit_exists_and_blobs_match` | FAIL | FAIL / BLOCKED | 指定的 S2 decision-service 历史测试 1 项 |
| `backend/tests/test_td03g_historical_compatibility.py::test_historical_reader_adaptation_preserves_every_original_test_body_and_hash` | FAIL | FAIL / BLOCKED | 39 项循环中的 26 项尚未取得独立身份依据 |
| `backend/tests/test_td03g_historical_compatibility.py::test_td03f_controlled_diagnostic_keeps_assertions_on_its_exact_old_source` | FAIL | FAIL / BLOCKED | 原受控诊断测试源码 1 项 |
| `backend/tests/test_td03g_historical_compatibility.py::test_runtime_queries_models_payloads_and_authority_logic_are_unchanged` | FAIL | **PASS** | 16 项循环中的 14 项新增准入；原 2 项登记不变 |

正常历史的上述四项在修复前、后均为 **4 PASS**。
新增 14 个精确源码回归在清理图先得到 **14 FAIL**，修复后连同 7 个拒绝/保留检查，
两种历史均为 **21 PASS**。覆盖登记篡改、自报 Hash、冻结记录修改、错版本、
Blob 字节损坏，以及其余 28 项仍不获准入。

本轮没有重跑此前已通过的 274 项测试，也没有推算新的全套通过数。
Ruff、Format 和修改模块的 Mypy 检查通过；既有身份 preflight、公开增量门禁及
工作簿分发保护另在实际提交图核验，实际 CI 身份及状态记录在任务回执中。

## 剩余 28 项及停止边界

- 原 S2 历史测试：现有 S1 技术记录的 Hash 对应另一个版本，与指定旧版本不匹配。
  changed-files 列表只证明曾涉及该路径，不能作为完整源码身份依据。
- 26 项 TD-03G 历史测试：本轮检查的同族冻结合同、授权及 workpaper 中没有匹配所需旧完整源码
  Hash/Blob 的依据；既有 13 项 transitive-test 登记不覆盖它们。
- 受控诊断源码：TD-03G 的现存测试 Hash 属于修改后版本；TD-03F 的更早 fixture
  记录也不等同于所需 `0124371b…` 完整测试文件。

这三项消费者仍实际失败于
`Required historical source unavailable: independent identity required`，
尚未进入后续 AST/断言比较，不能记为通过。后续需要匹配精确旧 Commit+Path 的独立
完整源码 SHA256/Blob 证据及其可信版本绑定；本轮不使用新算 Hash、当前版本或逆向
改写源码生成替代依据，不扩大搜索。

旧清单的 BLOCKED 状态保留为历史证据，新登记只覆盖明确核实的 14 项。
没有 skip/xfail、断言放宽、P35 发布或公开数据准入。
原仓库 Public；不修改远端历史、既有 Branch/Tag/Release/PR、服务器或冻结证据。
平台引用/缓存与真实历史实施不在本轮范围内；只创建独立 Draft PR，不执行后续发布操作。
