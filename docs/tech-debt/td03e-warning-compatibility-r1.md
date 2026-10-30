# TD-03E — Warning 根因与序列化兼容性

任务：`BLUEBERRY_TECH_DEBT_TD03E_WARNING_COMPATIBILITY_CLEANUP_R1`。
基线：`a3d0ea9b7a0faac273cd9f6504257c90f429ccc1`。
PR #770、#771、#772 已合并；main push CI #41071330963 已在该 SHA 成功。
本轮只处理 Warning 与兼容性，不启动 V0.22。

## 实测基线与归因

main push 按既有规则不运行 Golden，因此本轮没有将它写成 Golden 验收。
使用 [PR #772 exact-head Golden 日志](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/41060495299/job/124078707580)：
HEAD `5e8be627de1919d18d04e37f909197a1cbdb9767` 与本轮 main 的 Git Tree
同为 `5f7d285502c05de73020b15270c7a8dbe126027d`。
实际为 **10,485 passed、21 skipped、1,033 deselected、406 warnings**。
TD-03B 原来的 aiosqlite 线程异常已不在本次基线中，旧证据保持原样。

| 类别 | Before | 本轮处理的根因 | 有意保留 | 未安全修复 |
| --- | ---: | --- | ---: | ---: |
| PydanticDeprecatedSince20 | 276 | ProductionPlan 继承的 json_encoders 在重复 Schema 构建中触发弃用 | 0 | 0 |
| UserWarning | 104 | 101 条非法序列化诊断；3 条重复 Operation ID | 101 | 3 |
| PytestWarning | 15 | 同步测试继承模块级 asyncio 标记 | 0 | 0 |
| DeprecationWarning | 7 | 3 个旧 DB shim 导入；4 次 SQLite 默认 datetime adapter 调用 | 0 | 3 |
| StarletteDeprecationWarning | 3 | 旧 HTTP 422 常量别名 | 0 | 0 |
| PytestAssertRewriteWarning | 1 | fixture 在注册断言重写前已被普通导入 | 0 | 0 |

本表登记已定位的 299 次可安全修复的警告及保留原因；实际 After 必须从最终
exact-head Golden 日志核对，并附在本 PR 回执中，不能由表格预填 CI 成功。
日志对部分警告只提供模块聚合数量，本轮不补造缺失的单个 nodeid。
机器可读归因与本地验收见 [TD-03E 记录](td03e-warning-compatibility-r1.json)。

## 最小修改与兼容性证明

1. `production_plans.py` 使用 JSON-only `PlainSerializer`，仍调用原
   `canonical_decimal_string`。`WithJsonSchema` 取自同版本 Decimal 的原始
   serialization schema，保留字符串 pattern、nullable、default 等合同。
   Python-mode dump 仍为 Decimal，不改变行 Hash 使用的 scale。
   未改变字段的 Decimal 类型、校验器、canonical helper、数据库或预测数学。
   这是 [Pydantic V2 支持的序列化机制](https://docs.pydantic.dev/latest/concepts/serialization/)。
2. 三个测试模块只去除模块级 asyncio 标记。原有 `asyncio_mode=auto` 与
   session 事件循环策略不变。前后实际收集的原有 11,536 个本地 nodeid、
   skip/xfail 标记一致；2,529 个 Coroutine item 不变；只有 15 个同步
   Function item 不再继承 asyncio 标记。原测试业务断言不变。
3. 未被冻结的 DB 工具消费者改用 `backend.tests.db.profile/migration/concurrency`。
   CI 仅更换七处嵌入 Python 的导入路径，event、job、matrix、selector、
   通过条件均不变。旧 shim 保留；独立进程验证所有公开转发对象仍为同一
   对象，且旧路径仍发出明确的弃用诊断。
4. trial 的 SQLite 原始 SQL 测试显式绑定 `datetime.isoformat(" ")` 文本。
   与 Python 3.12 的旧 adapter 实际返回文本逐字对照，涵盖 naive、UTC、
   `+08:00`、微秒。不注册全局 adapter，不调整日期时区或精度。
5. 六个 API 模块共 30 处旧常量换为 `HTTP_422_UNPROCESSABLE_CONTENT`，值仍为
   422。除这一属性名替换外，每个模块的 AST 与基线完全相同。PostgreSQL
   回归另外复现了 production-plan API 的同类警告，修改后在 warning-as-error
   模式下通过。响应内容与权限逻辑不变。
6. 根 conftest 提前登记 authority fixture 的断言重写。保留原局部 plugin
   声明和作用域，不将 fixture 全局注册。实际 loader 必须为
   `AssertionRewritingHook`；未修复时该回归得到 `SourceFileLoader` 并失败。

## 有意保留与兼容性风险

全量回归发现 V0.18 的 `local-auth-runtime-r1.json` 还直接冻结了
`test_dev_db_protection.py` 和
`test_incumbent_forecast_replay_identity_persistence_schema.py` 的源码 Hash。
已经撤回这两个文件的修改，最终原字节与原 Hash 完全保留：前者仍有一条
migration shim 弃用诊断，后者仍有两条 SQLite adapter 诊断。新增回归核实原
Hash 和这些诊断；没有更改旧合同的读取范围、Hash、JSON 或断言。
它们属于本轮不能安全关闭的三条兼容性债务，不计为已修复，也不移到其他分片。


`backend/tests/core_forecast/test_metrics.py` 用 `model_construct` 故意绕过校验，
将非法字段送入服务的 fail-closed 边界。101 条 serializer UserWarning 来自
这些负面测试。原测试、原始诊断和阻断断言均保留，没有移动分片或过滤警告。

三个重复 OpenAPI Operation ID 来自 `local_auth.py` 与 `local_auth_admin.py`
的多方法路由：一个 session route、两个 admin route。默认生成器给同一路由
的多个 HTTP method 使用同一 ID；简单重命名函数或换 ID 会改变现有 OpenAPI
客户端合同，本轮没有足够的客户端迁移兼容性证据，故保留三条警告。
这仍是明确的 OpenAPI 兼容性风险，不能称为已修复。
两组固定 `PYTHONHASHSEED` 的独立进程对照要求完整 OpenAPI 前后一致，并验证
三条重复 ID 诊断仍在；不将不同 seed 之间的 ID 声称为稳定。

## 已执行的本地验证与最终验收边界

- 修改前新增回归实际复现编码器、错误 asyncio 作用域、datetime adapter、
  fixture 导入顺序及旧 422 别名问题，保留失败日志。
- 最终新增兼容性测试 **49 passed**：Create/Read/List 的 Python/JSON dump、
  默认/null/排除选项、正负零/指数 Decimal、canonical payload/row hash、
  validation/serialization schema、验证错误、完整 OpenAPI 及上述生命周期合同。
- 完整相关回归 **449 passed**，保留上述三条被冻结的诊断；其中不含这两个
  冻结探针的严格子集 **406 passed**，将 DeprecationWarning、PytestWarning、
  assert-rewrite warning 作为错误。原测试的 460 个业务 assert AST 保持一致。
- 独立新建 PostgreSQL **16.15** 临时集群，迁移到现有 head，API 与事务/隔离
  回归 **26 passed**，弃用警告视为错误；所有数据均为合成。仅停止本轮创建
  的 postmaster，未连接或清理用户数据库。
- Ruff、Format、strict Mypy `backend/app backend/research` 通过，Mypy 检查
  **637** 个源码文件。最终 Golden、四分片 Canary、PostgreSQL、前端和 Docker
  结果须以本 PR 最终 HEAD 的真实完整 CI 为准；本说明不预宣称 CI 成功。

新测试对旧实现的读取固定到上述已合并的完整 Git SHA，仅执行该版本受信任的
schema 源码；不查找其他版本，不回写旧证据。首轮本地全量 Golden 的失败日志和 JUnit 保留：宿主机磁盘耗尽导致 SQLite
和临时目录失败，调用 `pytest` 的子进程还缺少可执行路径；其中另行确认的两处
冻结源码冲突按上文还原，未冒称全为环境原因。只清理了本轮创建且已停止的
合成 PostgreSQL 临时集群，没有删除用户资料，也不把该轮结果写成 PASS。
资源与 PATH 恢复、冻结文件还原后，对该轮受影响的 **226** 个测试进行一次
定向复核，全部通过。最终全量验收仍使用固定代码在独立 CI 环境中的真实结果。

最终 CI 的 JUnit 会与基线
Golden/Canary JUnit 对照原测试身份和旧 skip 原因。

没有新增全局 warning ignore、skip、xfail、retry，没有改 Golden 预期、历史
Hash、模型参数、评分、来源权限、TD-03A/03B 机制、依赖版本或数据库结构。
TD-01 两份 XLS 继续不被追踪；没有读取真实业务数据。
仅交付 Draft PR，不 Ready、Merge、Tag、Release、Deploy。
