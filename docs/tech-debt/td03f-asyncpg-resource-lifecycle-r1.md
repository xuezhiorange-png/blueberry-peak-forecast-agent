# TD-03F — asyncpg 资源所有权修复与剩余跨循环问题

任务：`BLUEBERRY_TECH_DEBT_TD03F_ASYNCPG_RESOURCE_LIFECYCLE_R1`。
基线：`748321e56ba15973af1c2bef1fd7e7c8c965650c`，PR #773 已合并；
该提交的 main push CI [41159759053](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/41159759053)
已实查为 completed / success。本轮只使用隔离 PostgreSQL 16 和合成数据库记录。

本次结果为 **PARTIAL**：修复了一处已证明的 Session 所有权缺陷；另外确认
默认同步探针跨事件循环使用异步连接池的调用链，但没有将所有取消协程警告宣称为已修复。
最终 exact-head CI 及实际 Warning After 另在本 PR 验收回执记录，不从本地绿灯推定。

## 基线与根因 A：退出上下文后再次使用 Session

[对照 CI 41089726587](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/41089726587)
四个 Canary 分片共 301 条 warning，其中 SAWarning 12、
`Connection._cancel` 未 await 的 RuntimeWarning 54、Unraisable 0。
这三个数字是历史 CI 的观测值，不是每次运行的确定性数量。

未修改源码时，单独运行原有
`test_real_authority_exact_load_reuse_and_snapshot`，实际得到 1 passed、1 SAWarning。
追踪记录了 `_build_real_orchestration_command` 创建的 Session：

```text
AsyncSessionMaker -> 第一次事务 -> checkin -> Session.close
                 -> 后续 daily-row Session.get -> 第二次事务 -> 未归还连接
```

后半段 `MaturityDailyPredictionModel` 查询使用了已经退出前一个 `async with`
的变量。SQLAlchemy 的 Session 关闭后允许再次使用，因此该查询重新 checkout，
并非前一个 `__aexit__` 没有运行。原始 orchestration + S3 回归中，追踪到
9 个原测试共 12 次此类关闭后重用。GC 报错位置可能在 Pydantic、stdlib 或
其他测试，不能据此认定它们是连接创建者。

新增资源退出回归在修复前实际得到 **3 failed、4 passed**：正常、查询异常及
任务取消三条路径均在辅助函数返回后仍有活动事务。失败断言之后才进行测试自有
引擎的安全清理，未把泄漏清理隐藏在断言之前，也没有强制 GC。

最小修复只给后半段查询循环增加新的 `async with AsyncSessionMaker()`。
查询、参数、原始断言、输入、持久化结果和业务事务的提交规则均未改动；退出时
正常归还只读事务连接，异常和取消仍向上传播。

## 独立问题 B：同步探针和 pooled asyncpg 的事件循环所有权

同一次未修改源码的真实驱动追踪还记录到 112 次 `_cancel_current_command`
调用，全部发生在与底层连接所属循环不同的循环上，其中 108 次连接所属循环
已经关闭。88 次调用来自 `s3_a2_default_catalog_live_origin_construction`
的 `_load_fresh_bundle`，其余来自相关 `accepted_s2_*` 默认同步探针。
这些是原生驱动调用次数，不能当作 112 条 warning。

上述路径复用应用的 `AsyncSessionMaker` / AsyncEngine，却通过 `asyncio.run`
创建短生命周期循环。前一个循环保留在池中的连接不能在另一个循环安全复用。
[SQLAlchemy 对跨循环使用 AsyncEngine 的要求](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-multiple-asyncio-event-loops)
也明确要求相应所有权处理。实际驱动追踪证明了这条问题链，但没有记录历史 CI
每一个未 await coroutine 的精确分配与终结时刻，因此仍不宣称 54 条警告逐条闭环。

新增 `CONTROLLED_TOPOLOGY_DIAGNOSTIC` 在真实 PostgreSQL 上预热池，调用原公共
探针，用 Session 诊断边界记录调用循环、真实驱动循环及原 bind，在错误循环
实际发送 SQL 前明确阻断，最后回到所属循环 dispose。它证明默认路径会尝试跨
循环使用同一个 bind，**不是**模拟真实驱动异常成功，也不是问题 B 的修复。
最初直接触发错误驱动调用的诊断原型发生了协议清理错误；失败日志保留，不计作
通过的资源退出证明。未修改源码的 before-suite 原生驱动轨迹独立保留。

本轮不把全局连接池换成 NullPool，不在借用者中 dispose 调用方 engine，也不
把同步探针替换为其他数据源。`backend/app/db/session.py` 及多层 live-adapter
源代码有现存 Blob 合同；直接改变共享池策略、来源绑定或这些冻结对象会扩大到
应用连接生命周期兼容性。当前修改保持这些字节不变。取消协程问题仍待关闭，
即使某一次 CI 没有观察到该 warning，也不能因此称全部资源缺陷 FIXED。

## 回归覆盖及历史证据

新增 8 项 PostgreSQL 测试覆盖：原辅助函数正常退出、查询异常、任务取消、
初始化失败；引擎初始化失败的 finally dispose；外部连接和外层事务不被
Session 关闭；真实 `pg_sleep` 查询取消、rollback 和任务排空；上述跨循环诊断。
取消测试通过服务端 PID / wait-event 同步，不读取 SQL 文本或参数。
退出检查包括池的 checkout/checkin、活动事务、pending task、原 pool identity、
同循环 dispose，以及所捕获 asyncpg driver 的 `is_closed()`。

三次独立进程各 **78 passed，0 warning**，没有关闭后重用 Session，也没有
退出时遗留的池记录。完整 S3 回归 **1,491 passed、1 个原有 skip**；其 53 条
pytest warning 包含取消协程 RuntimeWarning 47、Unraisable 4、原 datetime
弃用诊断 2，另保留原始 stderr 中未纳入 pytest 汇总的诊断。该数量不是最终
四分片 CI 的 Warning After，更不能把随机终结时机造成的变化计作协程修复。
历史合同及兼容性回归 **186 passed**，保留一条原有 shim 弃用诊断。

V0.18 的 `local-auth-runtime-r1.json` 固定了被修复测试文件的原源码 SHA256：
`459b82f4e3dff0f19d3f654630930446f2ca6769a0eba8b58578ffe7fd6564b6`。
其历史原件位于既有 `MERGED_S1` 提交
`e9812e82067dceae444ff0707ceeb2f560c1018e`。只在现有历史读取白名单加入这一
被修复的测试路径，继续对固定历史字节核验原 Hash；不更新旧 JSON 或 Hash。
新增合同测试同时验证原 Hash、原测试身份及断言，以及去除唯一新增 Session
上下文后整份测试模块 AST 与原件完全一致。

三次独立进程重复、完整 S3 回归和静态检查的实测数量见同目录
[本地证据摘要](td03f-asyncpg-resource-lifecycle-r1.json)。原始追踪和失败日志仅保留
在本地受控目录，公开摘要不包含数据库凭据、SQL 参数、实际业务行或私有路径。

复算使用项目 Python 3.12 环境及 `backend.tests.db.profile` 允许的独立测试库，
先通过现有 Alembic 迁移建立空的合成数据库，再在同一个测试库上**顺序**执行：

```sh
python -m pytest backend/tests/integration/test_rolling_backtest_orchestration.py \
  backend/tests/integration/test_asyncpg_resource_lifecycle.py -q
python -m pytest backend/tests/integration/test_rolling_backtest_orchestration.py \
  backend/tests/integration/test_asyncpg_resource_lifecycle.py -q
python -m pytest backend/tests/integration/test_rolling_backtest_orchestration.py \
  backend/tests/integration/test_asyncpg_resource_lifecycle.py -q
```

必须显式配置 `APP_ENV=test`、`RUN_POSTGRES_INTEGRATION=1` 和隔离 PostgreSQL
测试身份，不得对开发库或业务库运行该命令。三次分别启动 Python 进程，不能用
同一进程的缓存或不受控重试代替。新的 8 项测试仍参与原全量 Canary，不调整
旧分片、通过标准或 warning 过滤。

TD-03A、TD-03B、应用及研究源码、依赖、CI 门槛、旧 skip/xfail、模型、来源权限
和历史结果均保持不变。TD-01 两份 XLS 未重新追踪；没有读取 SOURCE_002 原件、
连接业务数据库、修改用户卷、训练或部署。仅交付一个 Draft PR，不 Ready、
Merge、Tag、Release，也不启动 V0.22。
