# TD-01 技术文件历史定位兼容闭环 R1

任务：`TD01_HISTORY_TECHNICAL_COMPATIBILITY_CLOSEOUT_R1`。
基线 main：`76c93841d7173a6949ddf3bb980bbac7589bf537`，已合并 PR #785。

**实际修复3项精确历史身份，1项继续BLOCKED；结果PARTIAL。**
本轮未重扫222项依赖，也未调用TD-01E的65项总验证或原65项隔离预演。
只从[原未准入登记](td01e-unresolved-historical-dependencies-r1.json)取四个目标；不回写旧记录。

## 独立身份依据与实际准入

| 对象及原Commit | 原Blob OID | 既有独立依据 | 结果 |
| --- | --- | --- | --- |
| .github/workflows/ci.yml @ e9812e82067dceae444ff0707ceeb2f560c1018e | ba39349668d7db5f3f2893455357b8b993d3bf08 | [Local Auth原记录](../v0-18/s1/local-auth-runtime-r1.json)的source_evidence_sha256同路径字段 | RESOLVED |
| pyproject.toml @ 320f2046e3105b1b55da9cb037892571110b584a | df672f11a28e0a49ceed46454d496cdebe8f0612 | [S1 preflight原记录](../v0-18/evidence/s1-identity-and-grant-preflight-r1.json)的source_evidence_sha256同路径字段 | RESOLVED |
| uv.lock @ 320f2046e3105b1b55da9cb037892571110b584a | 8f97a9557ea1bc2e41863a3efb3e917c658f9c84 | 同上 | RESOLVED |
| backend/tests/forecast_intelligence/test_v0_17_s2_decision_service.py @ 320f2046e3105b1b55da9cb037892571110b584a | c43f842038ee8e35f5f9e8d77774c3d57a85806b | 已定位的S1记录值与该原版本不匹配；原S2记录未登记该路径的匹配Hash | BLOCKED |

三个已有expected SHA256分别为：

- workflow：696c72eeee06046d761d76a919b21ac374eb7f86e22d6639c21e97f660120fab。
- pyproject：3fa58e6bfb946b9714a29f6263d92acc659f2d871155ee542aba85c52ab8f764。
- uv.lock：91cd8c9d1678e8b505c4ff10c6275ca630e026c45c2210b0879ed4fc34ec0218。

这些值来自既有冻结技术记录；本次计算仅用于逐字节对照，没有用新算Hash自行批准原对象。
[新技术清单](td01-technical-identities-r1.json)记录这三条精确映射并由组件固定Hash封闭，原65项代码清单及其信任根不变。
读取时仍核对独立字段、原Commit/Path（当前历史模式）、普通Blob类型、Blob OID和原SHA256。

技术内容核对限于基础设施/依赖配置：旧CI无私有本机路径或SOURCE_002标记，依赖清单为程序/构建配置，
旧锁文件的registry和wheel域为pypi.org/files.pythonhosted.org及本项目editable根。
三份字节均通过原公开文本边界检查。没有执行旧workflow、安装旧依赖，或把其内容当作业务数据公开许可。
本公开提交只增加定位元数据，不重新上传历史工作流或锁文件副本。

指定测试代码原版本的实际SHA256为0a8492c97640ef3113aa88a872be1b6e754c8c96ffcc5c07468c3a9b00e3d1cf；
已定位的Local Auth记录值为4f206ec6a9569c5e099d1485897eba0f712dc1a4c6c7e73bbe5134b2e99df95a。
二者不同。没有搜索其他Revision来代替原版本，没有把该实际Hash加入准入清单；
其隔离读取继续失败，后续须提供能匹配指定Commit+Path的独立既有依据再审核。

## 工程修复及范围

现有backend.app.core.historical_code_identity复用同一Git/Blob/SHA验证链，增加封闭的技术身份读取接口；
backend/tests/historical_source.py只将这三个精确版本转给该接口，既有消费者和原业务断言不改。

普通仓库仍必须存在原Commit；丢失历史不会自动选择Blob回退。
仅现有组件本进程创建并登记的隔离图可按固定映射读取；JSON批准标签和任意仓库都不能获得该资格。
错误原Commit、非登记路径、清单/独立Hash篡改、错误Blob及污染旧Commit均失败。
原read_code接口仍拒绝这三个非代码路径，不把一般配置扩大为代码准入。

这关闭的是上述三条具体版本的字节定位依赖，不声称同路径所有旧版本都可迁移。
其他Commit、直接Git差异/祖先操作和完整项目历史图兼容继续按原规则处理。
独立Hash依据仍读取原技术元数据字段，未把209项研究证据或原件导入隔离图。

## 实际验证

修复前先建立原historical_bytes消费者的真实回归：隔离图已有三个独立核准Blob，原Commit不存在；
原实现3项均报Required historical commit unavailable，RED日志保留在本地证据目录。
修复后同一回归通过。定向技术/安全测试覆盖原消费者、普通仓库拒绝回退、篡改、非技术路径、
原Commit污染、精确对象集合、无Remote/Alternates/Grafts及原代码接口边界。

[机器回执](td01-technical-compatibility-closeout-r1.json)记录实际测试数量和证据Hash。
受影响原S1 preflight及Local Auth runtime合同按原断言通过；没有修改其冻结内容、Hash或失败条件。
三项65总验证/预演用例及一项无关的CURRENT代码fixture用例按本任务范围在本地DESELECTED，
未添加skip/xfail或修改CI工作流。
原合同自身的绑定断言照常执行，不能用本次结果替代完整项目迁移验收。

8项业务配置、209项冻结研究证据、真实XLS、五个压缩资产、SOURCE_002正文、预测模型、P35和
真实Git历史/Tag/Release均不进入本次修复范围。原仓库保持Public，不执行Ready/Merge/Deploy。
