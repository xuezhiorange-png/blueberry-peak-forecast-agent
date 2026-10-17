# V0.18：撤权提交与敏感读取准入的定向修复

TASK_ID=V0_18_BACKEND_REVOKE_READ_RACE_FIX_R1

基线：`4d61e3d64a4ecde2ccf90961bb5afa47ae6f19ec`。本次只修复已经复现的
`INITIAL_AUTH_SNAPSHOT_STALE_BEFORE_BUSINESS_READ`，不是版本收口或新增业务。
独立复审仍待进行；生产状态为 NOT_READY。第二条 PREAUTH 并发线索保持 PENDING。

## 原始 RED 与两次读取

原始复现工作树、报告、源码、JUnit 和事务时间线全部保留。其不可变副本及原始
SHA256 见本次 evidence 的 `original-red/`；本次还在上述新基线上重新复现了同一
失败：禁用提交后两个 SELECT，最终 HTTP 401，未发送敏感响应。

调用链是 `protected_transport → authorize → reader.curve → reader._source →
OperationalPeakRunRepository.get`。最后一个方法先读取
`operational_peak_forecast_run`，再读取 `operational_peak_forecast_daily`。
旧 authenticate 已结束事务；authorize 只依据旧 Principal 查 Grant，所以另一连接
可以先提交禁用，随后该请求仍执行这两次业务读取。最终 GuardedResponse 的复核
能阻止响应泄露，但不能撤回已经完成的读取。

原探针函数的 AST 与原始源码完全一致，仅文件格式及未使用 import 作静态清理。
没有删除零读取断言，没有伪造认证、响应或计算结果。

## 最小生产修改

只修改两个生产文件：

| 文件 | 修改原因 |
| --- | --- |
| `backend/app/local_auth/authorization.py` | 在真实读取前，以相同数据库连接取得账号共享锁，重新加载 Session、Principal revisions 和 exact Grant；覆盖 Canonical SQL、Quality 文件读取及模拟/比较引擎的准入。 |
| `backend/app/api/business_access.py` | S2 scope/list/selection 同样可能使用先前认证快照；将其实际查询放入同一短事务准入。 |

没有修改 Sessions、AuthService、预测/决策服务、Repository、数学、Hash、MCP、
前端、Schema、迁移、依赖或 CI。

### 线性化与锁顺序

读取准入使用 READ COMMITTED 新事务，按现有 `Sessions.load(shared_lock=True)`
协议在账号行取得 FOR SHARE；撤权者仍按原协议在同一账号行取 FOR UPDATE。
新读取路径不获取管理员 advisory lock，因此不引入 advisory/账号行反向锁顺序。
Session 在取得账号锁后重新刷新，Grant 也使用 populate_existing。

* 撤权先提交：新准入看见失效状态/版本，敏感工作计数为零。
* 读取先准入：撤权事务必须等待短读取事务释放锁；这些读取明确记为提交前工作。
* 请求取消：事务回滚并释放共享锁，等待的撤权可以提交。
* 锁等待：数据库 lock_timeout 为 2 秒，statement_timeout 为 5 秒；准入上下文
  另有 5 秒异步截止。超限默认拒绝 503，不修改原测试超时。

不会把共享锁延长到整个 HTTP 请求。保存曲线读取结束即释放；决策服务取得曲线后、
进入其原有无 await 的有界同步计算前，再取得一个新的准入。这样撤权可以在两阶段
之间提交，并阻止引擎执行。不修改或复制计算逻辑。最终 ASGI 发送前的独立复核和
持锁释放协议保持原样；已经发送的网络字节不可撤回。

若同一会话被只读诊断 SQL 自动开启了 AUTOBEGIN，则先 rollback，避免沿用旧快照；
显式事务或含待写 ORM 状态的会话直接拒绝，不擅自提交调用者工作。

## 实际 PostgreSQL 验收

新增 `backend/tests/revoke_read_race/`，直接组合 S5 原有 task-owned runner。
每次新建私有目录和隔离 PostgreSQL，沿用原 SIGTERM/重复信号清理及目录所有权核验。
没有 SQLite、Mock 授权、伪造 HTTP 200、硬编码观测计数或静态替代计算。

49 个运行案例：

* 原始 RED 探针原断言复验。
* 7 个入口 × 5 类撤权：curve、Quality、simulate、compare、scope、saved-runs、
  selection；分别测试禁用、Grant 撤销、Session 撤销、grant_revision 和 auth_revision。
* 2 个决策入口 × 5 类撤权：在 Canonical 曲线完成与模拟/比较开始之间提交撤权。
* 读取先准入及取消两个反向时序，通过不同连接的 pg_blocking_pids 证明实际行锁等待。
* 锁争用有界拒绝与恢复。

每类敏感工作都先做实际合法 HTTP 正向对照。SQL 使用真实连接的执行观察器；Quality
观察固定公共证据文件的实际 read_bytes；模拟和比较包装器只计数并调用原引擎。
JUnit 属性记录实际 PID、事务、隔离级别、事件顺序、工作计数及 ASGI 发送结果。
最终矩阵、回归命令/退出码、清理与来源 Hash 以相邻 canonical JSON 为准。

本轮本地实际结果：并发矩阵两次各 49/49；S1–S6 相关 PostgreSQL/安全回归
251/251；历史合同 112/112；前端 Unit 156/156；真实 HTTPS/PostgreSQL/MCP SDK
浏览器 50/50；完整前端 E2E（包括旧 Trial）144/144。上述运行均无跳过。Ruff、
Format、Mypy、前端 Lint、Typecheck、Format、Build 通过。最终 HEAD 的完整后端
Canary 及全量门禁由后续 exact-head GitHub CI 验证，不能用本地子集替代。

早期候选及夹具失败均保留：只读诊断事务曾触发 503；新增 Quality 夹具曾缺少数据库
强约束字段，随后其可选 Hash 被 HTTP 编码为空串而触发 422。这些不是成功运行，
其日志/退出码在执行历史中独立登记，不用后续 GREEN 覆盖。

## 历史合同兼容

四个直接受影响的离线测试按原有历史 Git 字节方法适配，不修改任何历史期望 Hash：

* S1 runtime evidence：authorization.py 使用 S1 合并提交 `e9812e8…`。
* S2 evidence：business_access.py 使用 S2 合并提交 `3410dd4…`。
* S3 evidence：历史 authorization.py 使用原 S3 base `3410dd4…`；被适配的 S2
  测试使用 S3 合并提交 `08b185b…`。
* S4 evidence：被适配的 S1/S3 测试使用 S4 合并提交 `8964183…`。

每个固定 blob 已先与冻结期望独立比对；Git 对象缺失或字节不匹配仍失败。
其余路径保留原验证方式。基线已有的 721 个 V0.16–V0.18 文档/证据逐字节保持不变。
历史 Hash 验证不替代当前运行测试。

## 重现与治理

```sh
python -m backend.tests.revoke_read_race.run --output /tmp/SYNTHETIC-revoke-read-UNIQUE
```

需要锁定 Python 3.12 环境与 PostgreSQL 16 工具在 PATH；输出路径必须不存在。
不提交证书、密码、Cookie、私钥、dump 或 PostgreSQL data directory。
完整 CI 必须绑定最终 Draft PR HEAD，以 GitHub 回执为准，不能继承基线绿色结果。

BACKEND_LEAD_2=PENDING

VERSION_CLOSEOUT_FORMAL_COMPLETE=false

PRODUCTION_READINESS=NOT_READY

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOY_AUTHORIZED=false
