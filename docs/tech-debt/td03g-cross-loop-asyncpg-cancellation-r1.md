# TD-03G — 短生命周期同步探针的 asyncpg 连接所有权

任务：`BLUEBERRY_TECH_DEBT_TD03G_CROSS_LOOP_ASYNCPG_CANCELLATION_R1`。
基线：`0124371b433d1b3c34e5e59a2a9a5e621a570f3b`，PR #774 已合并；
其 main push CI [41166095971](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/41166095971)
已实查为 completed / success。本轮仅使用受现有数据库身份保护的独立 PostgreSQL
16 合成测试库，没有访问 SOURCE_002 原件、业务数据库或用户数据库卷。

## 真实驱动根因与修复前失败

S3 默认同步探针和单循环 materialization 使用应用配置的 `AsyncSessionMaker`
及共享 Engine，外层却通过 `asyncio.run()` 建立短生命周期循环。Session 退出会
归还连接，但默认池仍持有属于前一个循环的 asyncpg driver；下一次调用不能把
该连接移交给新循环。TD-03F 已记录这条调用链，本轮在原生驱动处进一步复现。

在基线的独立 detached checkout 中，只加入最终版本的新测试，应用源码保持
未修改，实际得到 **7 failed**。七条公共能力路径包括 Session query、bind、
connection、bind query、connection query、run-sync query 和直接 Engine
connection。第一次调用成功，循环关闭后第二次真实数据库操作失败；测试没有在
发送 SQL 前人为抛出异常。native cancel 诊断只记录元数据并调用原驱动方法。

实际调用栈为池 pre-ping / terminate → asyncpg close →
`_cancel_current_command()` → 旧循环 `create_task(self._cancel(...))` →
`RuntimeError: Event loop is closed`。原始 stderr 还实际出现
`coroutine 'Connection._cancel' was never awaited`。这是
**CONTROLLED_REPRODUCTION**；它没有复刻历史 CI 的随机回收调度，也不声称将
历史 CI 的 55 条 warning 逐条对应到这七次失败。

该边界也符合
[SQLAlchemy 的跨事件循环约束](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-multiple-asyncio-event-loops)。
实际验证版本为 Python 3.12.13、SQLAlchemy 2.0.51、asyncpg 0.31.0，依赖未修改。

## 最小资源边界

`backend/app/db/loop_resources.py` 为短生命周期调用从**原 Pool 的 creator、
配置和事件**建立局部 Pool。实际 Connection 仍属于完全相同的原 Engine；
原 `AsyncSessionMaker` 创建原 Session 类，保留配置后仅绑定本次持有的连接。
不构造新 Engine、URL 或 session factory，不改变全局默认池，也不采用 NullPool。

局部连接不可在失效后重新连接到共享池。Session、Connection、初始化失败后的
已 checkout lease 和局部 Pool 均在所属循环结束前清理。清理只执行一次；如果
调用方在清理期间取消，先完成清理再传播取消，清理异常亦不会被忽略。查询异常、
rollback、初始化失败、真实查询取消及清理期间重复取消都有回归。

调用方提供的同循环 AsyncConnection 保持原身份与外层事务，探针不关闭该连接，
也不 dispose 调用方 Engine。其他循环的借用连接在实际 I/O 前拒绝，不尝试接管
它的事务。SQLite、既有测试替身和只创建 Session、不做 I/O 的能力探针保留原路径。
多 bind 配置没有唯一的局部资源所有者时明确拒绝，不推断替代数据源。

源身份、同一数据库/用户、server settings、isolation level、Session 类及
factory kwargs 有真实 PostgreSQL 检查。原查询、结果模型、来源 attestation、
payload 和 Hash 计算未修改；19 组失败原因对照保持旧公开 envelope。

## 调用范围及未扩大的边界

修复覆盖 15 个 S3 I/O 适配模块及 train/validation materialization 的异步辅助
模块。`s3_a2_default_catalog_live_origin_construction._load_fresh_bundle` 复用
已修复的 `_bind_and_read_with_session_maker`，不需要改写 construction、缓存或
来源选择。Session-only 探针保持惰性，不因能力检查额外连接数据库。

另外检查了 app CLI 及其 area/core/operational-peak/residual/PIT dispatch、
rolling-backtest CLI、local-auth bootstrap 和 MCP stdio 入口。MCP 是长生命周期
异步应用；常规独立 CLI 是单进程单循环使用。这些入口不作为本轮已证明的默认
S3 探针链进行改写，也不声称其任意嵌入式、多循环重入均已获验证。已有 CLI 的
线程桥接不是本轮修复方案，没有新增阻塞线程或嵌套事件循环。业务事务及输入
验证先后顺序不借本任务调整。

本实现依赖 SQLAlchemy 已固定版本的 Connection 构造和池 lease 接口；将来升级
SQLAlchemy 必须保留这些真实驱动回归，不能只检查 Session 是否退出。

## 历史源码与测试身份

旧文档、JSON、预期 Hash、Golden、TD-03A/TD-03B 源码、TD-03F 原证据和
`backend/app/db/session.py` 全部保留。39 个历史测试仅调整其 `_git_blob` 读取
边界，继续核验基线中的原 `97be63307d002d6878649cd241ff94f5149e0f8a`。
其中 13 个测试文件自身被其他历史合同固定，因而也精确绑定其已核实的原 Blob；
不能搜索另一段恰好匹配的历史，也不把无关源码或文档切到历史版本。

TD-03F 原有受控拓扑诊断故意断言旧不安全路径，继续在原
`4d946c02acff3a257817e714ad824f9b311d42ec` 源码上运行。生产导入不替换；
本轮新测试直接验证当前实际公共路径。六项兼容性测试证明旧测试体、常量、
装饰器及断言未变，并验证非白名单内容保持读取当前字节、历史字节篡改必须失败。
这与修改历史 Hash 或把当前实现错误伪装为旧合同通过不同。

## 验证及证据

最终新测试与 detached 基线 RED 使用完全相同的文件字节。资源测试同时检查
真实 driver 的 `is_closed()`、checkout/checkin、局部 Pool dispose、原 Engine
不被借用者 dispose、pending tasks，以及循环关闭之前的资源状态。

S3、来源绑定、历史合同和 materialization 回归实际为 **1,519 passed、1 个
原有 skip、2 条原有 SQLite datetime 弃用诊断**。Ruff、Format 和 strict
Mypy 同时覆盖 app/research；Mypy 实际检查 638 个文件。
预先限定的三次独立进程结果及完整原始证据 Hash 见
[本地证据摘要](td03g-cross-loop-asyncpg-cancellation-r1.json)。
中间的 Engine 副本原型因不符合旧 `NO_NEW_ENGINE` 要求而放弃，失败与原型日志
原样保留，不计作最终 Pool-only 方案验收。

隔离测试库配置好后按顺序运行，禁止指向开发库或业务库：

```sh
python -m pytest backend/tests/integration/test_asyncpg_cross_loop_probes.py \
  backend/tests/integration/test_asyncpg_resource_lifecycle.py \
  backend/tests/integration/test_rolling_backtest_orchestration.py -q
# 总共启动三个独立 Python 进程；不是失败后不受控重试。
python -m pytest backend/tests/test_td03g_historical_compatibility.py \
  backend/tests/s3_daily_rowset \
  backend/tests/forecast_quality/test_s3_b_single_loop_live_materialization_db_acquisition_r1.py -q
```

[对照 CI 41163593281](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/41163593281)
四分片的取消协程 RuntimeWarning 为 **55**，SAWarning 为 **0**。最终 After 必须
从本 PR exact-head 的真实日志测量，并在 PR 验收回执中绑定 HEAD 和 Run ID；
本地绿灯不代替 CI，更不代表所有其他生命周期路径已完成审计。旧测试身份及
skip 原因另以完整 JUnit 对照。

没有 warning filter、强制 GC、超时放宽、不受控重试、新 skip/xfail、依赖升级、
业务来源变更或预测数学变更。TD-01 两份 XLS 未重新追踪。只交付 Draft PR，
不 Ready、Merge、Tag、Release、Deploy，也不启动 V0.22。
