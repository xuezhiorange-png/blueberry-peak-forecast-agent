# OPTION_B 后端 PostgreSQL 并发复现：RED 后停止

TASK_ID=V0_18_OPTION_B_BACKEND_CONCURRENCY_POSTGRES_REPRO_R1

基线 `ebe50fbe250097a882407604a8482ca9cfdf6d9a`，独立分支
`codex/v0.18-option-b-backend-pg-repro-r1`。只新增测试及证据，backend/app、迁移、
Schema、已有测试和生产数据库均未修改。本次不是后端修复，也不是 A–G 独立接受。

## 原始线索及实际结果

线索 1：authenticate 返回 Principal 后，到 authorize/业务读取前，如果账号/会话
已被另一事务撤销，旧 Principal 是否仍能进入敏感读取。

**REPRODUCED。** 使用真实 PostgreSQL 16、正式 create_app、实际登录、实际
Canonical Repository 保存的 SYNTHETIC run 和独立事务。测试包装器仅在原
authenticate 返回后设置事件屏障，并观察原 curve；没有伪造认证、授权或返回值。

实际顺序：

1. 合法登录并读取相同保存曲线，HTTP 200，SQL 观察器记录 2 次业务 SELECT，证明
   观察器有效且实际保存记录可读取。
2. 新请求正常 authenticate 完成后暂停，尚未进入资源授权/业务读取。
3. 独立连接 PID 88676、事务 748、READ COMMITTED，对账号取排他行锁，设置
   DISABLED、递增 auth_revision、实际 revoke_all，事务提交。
4. 屏障开放后，另一个物理连接 PID 88677、事务 749、READ COMMITTED 进入真实
   Canonical curve，并执行 2 次敏感业务 SELECT。
5. 最终响应释放门禁再次认证，返回 401/null data，不包含 source hash/daily_rows；
   同一 Cookie 请求 auth/me 也为 401。没有证明敏感响应泄露。

失败断言是 `business_reads_after_disable_commit == 0`，实际为 2。
这复现的是“账号禁用提交后，后续资源/读取准入仍使用旧 Principal”的窗口，**不是**
密码绕过，也不能忽略已生效的最终响应保护。请求的初始身份认证发生在撤销前；
资源授权及 Canonical 读取发生在撤销后。审查者必须依据冻结的先授权后读取合同
独立评估这一时序，不把已发字节称为可撤回。

线索 2：同一 PREAUTH 在 advisory lock 前被两个登录读取，等待锁后不刷新会话，
是否可能成功消费两次。**NOT_EXECUTED_STOP_ON_CONFIRMED_LEAD_1**：按照 Owner 的
“确定性后端缺陷立即 STOP”指令，没有继续第二条测试，不宣称不存在、不报 GREEN。

## 复现与保留

```sh
PATH=/opt/homebrew/opt/postgresql@16/bin:$PATH python -m backend.tests.option_b_pg.run --output /tmp/SYNTHETIC-option-b-backend-pg-repro-NEW
```

wrapper 只把 S5 原 runner 的测试列表改为 `-x backend/tests/option_b_pg`；所有
PostgreSQL 创建、所有权确认、SIGTERM/重复信号处理、关闭及日志保留由原 S5 runner
执行。每次路径必须全新。pytest 在第一个 RED 退出，runner 正常 finally 清理。

实际命令使用私有目录 `/tmp/SYNTHETIC-option-b-backend-pg-repro-20261016-r1`。
1 failed，退出码 1；不是夹具/迁移/连接失败。JUnit 的 OPTION_B_PG_LEAD_1 保留了
正向读取、不同 PID/事务、提交顺序和真实响应状态。
shutdown_exit=0、STOPPED、postmaster_absent=true、listener_closed=true、
execution_secret_scan=PASS。没有停止其他实例，私有目录及原始日志不删除。

公开证据只包含 JUnit、所有权清理记录、测试源码、观察记录及其 SHA256。
不提交密码、Session、证书 key、dump 或数据目录。原始执行日志绑定 SHA256，
保留于本机私有目录，不为制造 GREEN 重跑、skip/xfail 或修改失败断言。

## 后续最小授权建议

如 Owner 决定修复线索 1，需单独授权审查 `local_auth/authorization.py` 的读取准入
与相关 session/subject lock 边界，以及 business_access 的同类路径；应先界定准入
线性化点，再增加真实 PostgreSQL/ASGI/HTTPS 回归。此处不提供或实施运行修复。
线索 2 尚需独立授权恢复其真实并发复现，不能从线索 1 推断其结论。

BACKEND_PRODUCTION_CODE_CHANGED=false

A_G_INDEPENDENT_ACCEPTANCE=PENDING

H_OWNER_RISK_ACCEPTANCE=false

GOVERNANCE_EXCEPTION_APPROVED=false

VERSION_CLOSEOUT_FORMAL_COMPLETE=false

PRODUCTION_READINESS=NOT_READY

READY_AUTHORIZED=false

MERGE_AUTHORIZED=false

DEPLOY_AUTHORIZED=false

TAG_AUTHORIZED=false

RELEASE_AUTHORIZED=false

STOP=true
