# PREAUTH 并发登录定向复现：RED_CONFIRMED

TASK_ID=V0_18_PREAUTH_CONCURRENT_LOGIN_REPRO_R1

MAIN_SHA=816d8299f007eab7da140fc5c7547d941c026f8f

## 实际运行与结果

使用未修改的 production create_app、正式 /api/v1/auth 登录/CSRF/me 路由、真实
AuthService、SQLAlchemy AsyncSession、Argon2id 和 task-owned PostgreSQL 16.15。
HTTPX ASGITransport 调用真实 ASGI 应用；未使用 mock 响应，没有建立网络 TLS
连接，因此不把本次范围描述为网络/证书验收。应用注入的是隔离数据库的真实
AuthService，沿用现有 S5 application(auth) 测试基础。

实际命令：

```sh
PATH=/Users/charles/blueberry-simple-admin-r1/.venv/bin:/opt/homebrew/opt/postgresql@16/bin:$PATH \
python -m backend.tests.preauth_repro_r1.run \
  --output /tmp/SYNTHETIC-v018-preauth-repro-20261018-verified-observer
```

pytest：1 passed / 1 failed / 0 skipped / 0 errors，退出码1。失败是安全不变量
`successful_login_count <= 1` 的真实 `assert 2 <= 1`，不是跳过、重试、期望改成
“允许两次成功”或环境超时。JUnit 的两个实际 proof property 和完整日志均保留。

实际数据库/HTTP交叉观测：A=200，B=200；两份独立 END_USER Session；两条
LOGIN_SUCCESS；分别携带两个响应 Cookie 访问真实 /auth/me 均为200。数据库
Session主键不同，Cookie映射至各自已提交的真实记录。证据不存raw Cookie、CSRF
token、密码或token digest；只保留合成记录ID和安全状态。

PREAUTH最终仍是revoked/LOGIN_ROTATION；旧PREAUTH /auth/me=401，没有被恢复有效。
漏洞是两个请求复用撤销前的校验结果，各自签发有效认证Session，不是PREAUTH最终
状态重新激活。

## 确定性时序（实际记录，不是预期值）

1. A：PID12490，事务746，READ COMMITTED；真实load/CSRF通过后暂停，尚无登录锁。
2. B：PID12491，事务747，READ COMMITTED；相同PREAUTH/CSRF及正确密码，通过
   三把真实advisory locks、账号FOR UPDATE和密码验证；撤销PREAUTH、创建Session、
   写入LOGIN_SUCCESS并完成生产事务/HTTP响应。
3. 独立观测事务读取到PREAUTH已撤销、Session和审计各1条，并用
   pg_xact_status(747)=committed确认B提交；随后才释放A屏障。
4. A恢复时原ORM对象cached_revoked=false，继续取得三把advisory locks和账号行锁，
   再次创建独立Session和LOGIN_SUCCESS，HTTP200；pg_xact_status(746)=committed。
5. 最终数据库和两个真实 /me 响应证明两份认证均有效。

连接说明：A/B在目标登录事务中使用不同实际物理PID。独立观测使用新的数据库
Session/事务；连接池可复用B已释放的物理连接（本次activity中PID12491是observer
的新事务），不宣称出现第三个不同物理PID。它不是B原事务的未提交读。

锁观测：A屏障时pg_stat_activity为idle in transaction/ClientRead，双方
pg_blocking_pids均空；这是测试事件等待，不是PostgreSQL锁等待。B和A签发前均
实际持有3把granted advisory ExclusiveLock。B锁调用耗时0.262/0.122/0.138ms；
A为0.217/0.093/0.087ms。没有锁超时；目标时序是B提交并释放锁后A继续。

## 正/负向对照

单次正常登录200、真实/me200；同一已消费PREAUTH顺序重放401、旧PREAUTH/me401；
数据库只生成1份END_USER和1条LOGIN_SUCCESS。错误CSRF和错误Origin均403。
这说明测试没有绕过真实会话、Cookie、CSRF、Origin或密码验证。

## 根因与最小修复位置（仅建议，未实施）

service.py:151在advisory lock前load PREAUTH；sessions.py:131的该次读取没有锁定
PREAUTH行。锁后至service.py:200–203消费/签发路径未重新校验该会话；ORM持有
过时的revoked_at=None，账号行锁和桶锁只串行化后续步骤，不能使旧判断自动失效。

最小修复候选是AuthService.login中已有桶锁之后、签发认证Session之前，对
PREAUTH按统一锁顺序锁定并重新读取、校验有效期/撤销/kind/CSRF，再原子消费；
或者采用带有效性条件且必须成功返回一行的原子消费更新。消费失败必须拒绝并
回滚，不创建END_USER或LOGIN_SUCCESS。不得只看最终401、无条件重复UPDATE或
修改测试允许两个成功。是否提取Sessions辅助方法须在后续修复授权中决定。

后续修复回归应保留本次RED断言、顺序重放、合法单次登录、事务提交顺序和
数据库/审计/实际Cookie有效性核验。本轮不修改生产代码或开始修复。

## 首次观测器错误与资源保留

首次输出 `/tmp/SYNTHETIC-v018-preauth-repro-20261018-r1/` 保持不变：对照通过，
并发观测向asyncpg的xid8参数传入字符串，DataError。该次是INCONCLUSIVE，不能
作为RED或GREEN。原日志/JUnit/执行源码SHA256均保留。仅将两处观测SQL参数转换
为整数后，在新实例运行；安全不变量没有改动。不是用重试掩盖生产失败。

两次owned-resources.json均证明目录身份核验通过、STOPPED、postmaster_absent、
listener_closed；只停止任务自建实例，保留私有证据目录，没有按端口或进程名杀进程。
原始源码、JUnit、日志、观察JSON及SHA256清单由相邻evidence.json绑定。

PR#728仍OPEN/Draft，HEAD=772503823320c48c6920fc66c5164d8a30844fd9，未更改。
本地新增测试未提交/推送；原有tracked文件零差异，无生产数据库或真实账号操作。

PRODUCTION_CODE_CHANGED=false
PR_728_CHANGED=false
VERSION_CLOSEOUT_FORMAL_COMPLETE=false
PRODUCTION_READINESS=NOT_READY
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOY_AUTHORIZED=false
STOP=true
