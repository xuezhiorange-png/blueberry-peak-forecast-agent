# PREAUTH 并发重复消费：最小修复与隔离验收

TASK_ID=V0_18_PREAUTH_CONCURRENT_LOGIN_FIX_R1

基线 `816d8299f007eab7da140fc5c7547d941c026f8f`。本任务只修复同一个 PREAUTH
被两个合法密码登录请求重复消费的问题，不修改预测、Schema、MCP、Dashboard、
依赖、CI、PR #728 或冻结历史记录。

## 原始 RED 和不可变探针

原报告及实际源码、JUnit、事务时间线仍保留在
`/tmp/SYNTHETIC-v018-preauth-repro-20261018-verified-observer/`。先逐一核验原
evidence.json 中13项 SHA256，再复制关键 RED 产物到本次独立证据目录；不覆盖原件。
原探针 SHA256 为 `35d4c982c39c8737d8f43b949f2228a7c0cc9ddb08cffdd350aedbffaf9bafdb`，
本PR中的探针原字节相同，保留“最多一次成功”的失败断言，没有 skip/xfail 或重试。

原RED：A、B均HTTP200，两份不同END_USER Cookie各自/me200，数据库两份Session、
两条LOGIN_SUCCESS。A在首次PREAUTH校验后暂停；B真实提交并撤销PREAUTH后，
A恢复使用旧ORM快照，继续成功。PREAUTH最后被撤销并不等于只消费一次。
最早一次xid8观测参数类型错误为INCONCLUSIVE，原日志和源码亦保留，不能冒称RED。

## 唯一生产修改

仅 `backend/app/local_auth/service.py`。保持现有锁顺序：

`桶 advisory locks → 账号 FOR UPDATE → PREAUTH FOR UPDATE → 签发/审计 → commit`。

在密码成功分支、签发END_USER之前，按原Session ID及实际Cookie的token digest
查询目标AuthSession，明确使用`SELECT ... FOR UPDATE`，并设置
`populate_existing=True`。没有目标行则401；持锁后重新调用现有`load(preauth=True,
csrf=True)`，核验kind、revoked、idle/absolute expiry及当前CSRF digest，并确认
Session ID没有替换。由此复用原401/403语义，不复制或放宽认证规则。

PREAUTH没有account_id，`load(shared_lock=True)`原本只锁账号，不能解决该漏洞。
本修复没有以该参数代替PREAUTH行锁；`sessions.py`无改动。

最终校验、撤销PREAUTH、END_USER签发和LOGIN_SUCCESS仍在同一数据库事务内。
第二请求在签发前失败；不是先创建再补撤销。数据库行锁持有到commit/rollback，
正确性不依赖浏览器或新增进程内锁。原桶锁、密码、Argon2id、限流、Cookie、CSRF
及其他认证路径不变。异常/取消会整体回滚，不留下幽灵Session或成功审计。

## 实际测试和证据层级

保留原始A锁前读取、B提交、A恢复的确定性屏障，真实SQLAlchemy/READ COMMITTED
事务、不同PostgreSQL连接PID、xid、advisory/账号锁和实际HTTP结果。使用正式
create_app及真实ASGI路由（HTTPX ASGITransport），不是模拟认证或网络TLS证明。
独立观测事务可复用已归还连接池的物理连接，不把它误称为第三个不同PID。

修复后原始探针：B=200，A=401，B提交、A回滚，1份认证Session、1条成功审计，
获胜/me200、失败请求/me401；PREAUTH保持REVOKED/LOGIN_ROTATION。

两轮全新隔离实例的专项测试各13项通过，另外先单独重跑原探针2项通过。
专项覆盖：

- 正常单次、已消费Cookie顺序重放及原始并发RED→GREEN；
- 不同PREAUTH合法并发，观察真实AuthSession FOR UPDATE SQL；
- 在初次校验后改变idle expiry、absolute expiry、撤销、真实CSRF轮换或token digest，
  分别以原合同401/403拒绝，零新Session/成功审计；
- 两个真实AuthService实例并发7次错误密码：5次401、2次429、零认证Session及
  LOGIN_SUCCESS；原三个限流桶各自审计，不以进程内信号量替代PG限流；
- 实际issue flush后异常、取消，以及成功审计异常：事务全部回滚；同一尚未消费的
  PREAUTH随后合法重试只创建一份Session。故障注入的503不是重复消费GREEN。

测试入口复用未改动的S5 task-owned PostgreSQL/SIGTERM清理，不连接生产数据库。
运行命令、实际退出码、JUnit、原始probe、额外case、清理证明及SHA256以相邻
`docs/v0-18/evidence/preauth-concurrent-login-fix-r1/evidence.json` 为准。
完整相关安全回归、HTTP/MCP/浏览器、静态及exact-head CI结果分开记录；不以
本地专项GREEN替代完整CI或独立审核。既有warnings/skips不隐藏。

```sh
python -m backend.tests.preauth_repro_r1.run_fix_acceptance --output /tmp/SYNTHETIC-NEW-ROUND
python -m backend.tests.preauth_repro_r1.run_fix_acceptance --related --output /tmp/SYNTHETIC-NEW-RELATED
```

需锁定Python3.12环境与PostgreSQL16工具。输出必须是不存在的私有SYNTHETIC目录。
只验证并停止目录/进程所有权已确认的自建实例，保留证据；不提交数据库data、
密码、Cookie、私钥或dump。

## 最小历史测试适配

S1 runtime已有固定历史来源适配，无需修改。S3 `unchanged_business_sources_sha256`
绑定旧service.py，原期望`d1e5e4c531aa948a9c1791888d9c627ae5195deb4ab512930ab669a95ecf167f`
与S3基线`3410dd4426618a7a4b29c08cbf58aaef20196939`原始Git字节已独立匹配。
仅将该路径加入既有历史读取分支，缺失对象或Hash不符仍失败，其他断言不变。
D03亦绑定同一旧service.py期望；其原合并提交`c35524174865785164fe4529f35067037ccddc2a`
原字节已核对，按同样方式适配其历史测试。第一次完整相关回归的该项Hash失败保留，
不改写成从未失败；修正后再执行完整相关运行回归与单独的证据合同验证。
被适配的D03测试还被S2证据绑定，故S2仅对该测试路径读取原S2合并提交
`3410dd4426618a7a4b29c08cbf58aaef20196939`原始字节；原期望同样已独立匹配。
原S4对该S3测试的历史绑定已经固定在其原始交付，不需连锁修改或重算旧Hash。
旧撤权修复证据还绑定S2、S3及其自身证据测试；这三个历史测试源码仅从原修复
合并提交`8c6f8cdb579b97669e7cc27edea3e75ea32090e6`读取，分别核对原预期Hash。
其他来源及所有历史产物仍检查当前字节，不修改旧证据。初次相关回归300通过、
2项历史Hash失败的JUnit完整保留；这些失败不能冒称运行安全缺陷，也不隐藏。
已在收集阶段加载旧合同的中间一轮301通过、1项旧Hash失败，同样保留；最终全量
相关回归从新实例、最终适配源码重新收集执行，不把该失败轮次计为完整通过。
历史字节验证不能替代当前运行安全测试。

## 治理停止点

独立Draft PR和最终HEAD完整CI后停止，不自行合并或复评整个V0.18。
PR#728仍为Draft，原收口证据和PREAUTH当时PENDING快照不改写；本PR另行记录
本次定向修复，不追认历史审批，也不构成完整A–G独立接受或发布授权。

VERSION_CLOSEOUT_FORMAL_COMPLETE=false
PRODUCTION_READINESS=NOT_READY
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOY_AUTHORIZED=false
STOP=true
