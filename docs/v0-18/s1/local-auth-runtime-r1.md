# V0.18 S1 Runtime / R3 隔离入口交付

## 结论与治理

基线 `320f2046e3105b1b55da9cb037892571110b584a`，延续
`task/v0.18-s1-local-auth-runtime-r1`。交付生产认证实现、增量迁移、历史来源测试适配、
当前 Alembic Head 兼容及显式 Legacy 测试入口。不修改冻结预测 Service、数学、MCP
Runtime 或 Dashboard Runtime。不访问生产数据库、不创建真实账号/授权。

**RESULT=PARTIAL**：运行测试成功不代表全部安全审查闭合。A19 依赖审计发现既有
AnyIO 4.14.0 / PyJWT 2.14.0 共 5 项报告；仅新增密码依赖无报告。
未擅自升级无关依赖，待独立审查及定向升级授权。D03 实际管理员、组织 steward、
授权发布/审批责任仍 PENDING；生产 NOT_READY，S1_FORMAL_COMPLETE=false。
本轮只允许 Draft PR；Ready/Merge/Deploy/Tag/Release 和 S2–S6 均未授权。

## 实际实现

- 四表 `auth_account / auth_session / auth_resource_grant / auth_audit_event`；真实 PostgreSQL
  增量 revision `d7766e57d4c8`，直接父版本 `0040_hierarchical_forecast`。
  Principal 不可变、不可硬删除重用，审计追加，FORECAST/QUALITY 强类型绑定。
- Argon2id 19456 KiB / t2 / p1，随机盐、虚拟密码验证、登录时 rehash。
  管理员创建/重置/禁用/角色管理，强制首次改密，最后有效管理员保护。
- Opaque server session：只存 digest，idle 8h / absolute 24h / PREAUTH 300s。
  `__Host-blueberry-session` Secure/HttpOnly/SameSite=Lax，HTTPS/Origin 和 synchronizer CSRF。
  登录限制通过 PostgreSQL advisory lock 与事务内审计跨 worker 原子计数。
- 服务端可信管理边界必须明确配置 Principal、可管理组织/账号/角色及 exact approved grants。
  ADMIN 不获得隐式数据权限；BASE/REGION/COMPANY 不继承，Quality 独立，未知/未授权 run
  在业务读取前相同拒绝。完整身份/hash 核验沿用原服务。
- S1 六读取、S2 模拟/比较/成本 exposure 仅在 HTTP transport 接入认证；无 TrialActor fallback。
  业务结果缓存禁止；最终 ASGI send 前新事务复核账号、会话、revision 与 grant。
  账号 SHARE 锁持有至 send 返回，撤权使用相同账号 UPDATE 锁。撤权先于 release gate
  提交时不发送敏感数据；已经发送的字节不可撤回。取消释放锁。

## Legacy 入口修正

生产 `backend.app.main:app` 和 `create_app` **都**始终启用 ControlledIngress，
移除此前临时 `controlled` 参数。测试环境变量、伪造 actor Header 不改变拒绝规则。
旧 Trial/MCP 及其他未列入受控白名单的路径默认拒绝。

`backend/tests/support/legacy_test_app.py` 独立创建 FastAPI，直接注册原 Router、Service、
异常协议与原 MCP；没有调用可关闭认证的生产 factory，没有替换计算或伪造结果。
内存测试必须显式 `synthetic=True` 并注入隔离 fixture；默认数据库引擎连接增加
loopback / `_test_` 名称验证，不能回落到业务库。live factory 另要求 APP_ENV=test、
明确 synthetic opt-in、隔离 loopback 数据库；网络请求也限 loopback。
生产 main 不导入该模块，测试应用从未被生产自动挂载。

旧成功路径的工厂 import 改到这个显式入口；业务断言、工具名称/schema、凭据检查、
Decimal/Hash、错误脱敏和 CLI/std​io parity 保留。全部实际修改文件及必要性在 JSON
`test_entry_adaptations` 中逐项列出；并非把所有旧成功测试改为 403。
L01/L02/L03 则实际调用生产 app/factory，保留明确拒绝。

Frontend E2E CI 只更改隔离测试后端启动：test-only factory、127.0.0.1 监听、
health 的 SYNTHETIC_LEGACY marker，保留原 Vite 代理、真实 PostgreSQL fixture 和 94
个浏览器断言。always 清理只作用于本任务保存的 PID，并检查监听退出。
可复现本地 runner `backend.tests.local_auth.run_frontend_legacy_acceptance`
复用 CI 原始 seed/XLSX 步骤，独占随机端口/UUID 库，在 finally 清理并检查端口与库。

## 历史与迁移适配

历史 SHA256 预期未改。冻结文档/证据读取当前字节；被明确授权变更的历史代码/测试
读取固定完整 Git commit `320f2046e3105b1b55da9cb037892571110b584a` 对应 blob，
逐项先证明与原 pin 相等。缺提交/缺 blob/越界/错误 digest 均 FAIL，无当前 HEAD 回落。
当前 Runtime 使用当前代码执行独立安全测试，不能用旧 blob 替代。
执行这些历史检查的 golden/canary/frontend-unit job 最小补充 fetch-depth 0 与对象检查。

只修正“upgrade head 后当前版本”与“当前迁移图 head”的断言，使用 Alembic 官方
ScriptDirectory 唯一 head + 0040 祖先验证；固定历史 revision/down_revision/downgrade
目标和数据/约束断言保留。M09 多 head 负向与 M10 将来合法新 head 均实际执行。
M06/M07 用真实 PostgreSQL downgrade 0040 / upgrade head，历史 saved-run hash/记录不变。
M08 使用原 Quality 持久化禁止降级测试，不改历史迁移。

## 运行结果与已保留失败

详见 canonical JSON 和测试映射。实测本地 PostgreSQL 15.18，非生产、合成身份。
旧 MCP/Trial 专项 115 passed；历史合同专项 88 passed；旧迁移/持久化/MCP PostgreSQL
140 passed；后端非 PostgreSQL/集成全量 9060 passed / 21 既有 skipped / 815 deselected。
新安全/入口/迁移测试最终运行记录在 JSON，不把测试数量等同于 A 项数量。
Frontend Unit 122 passed；完整浏览器 94 passed；typecheck/lint/format/build 成功。
Ruff / Format / Mypy（CI 实际目标 backend/app，573 文件）通过。

本地 llvm-openmp 23.1.3 已安装到既有隔离 PostgreSQL 工具环境，用 DYLD_LIBRARY_PATH
恢复 LightGBM 链接；两个原 libomp 失败及相关 4 项 library smoke/replay 复测成功。
不改冻结模型，不新增实验；现有 synthetic regression 内的库 smoke 不证明业务精度。

首次完整 E2E 84 pass / 10 fail 的 Trial 请求 cutoff 为
`2026-02-27T16:00:00Z`，与 seed 的 UTC cutoff 不同。原 Trace 已复制保留在独立临时
证据目录并在 JSON 记录 hashes。按 CI 的 UTC 环境重新执行 94/94；未修改生产页面或断言。
扩展测试曾有两类 fixture 错误（过期时间早于 issued_at、层级 seed 未 commit），
保留初次 JUnit 后只修正 synthetic setup；复测成功，不放宽数据库约束或业务检查。

Argon2id 合成成本 10 次：hash mean 23.181ms / max 25.200ms；verify mean 22.759ms /
max 24.207ms。仅本机数据，不代表部署性能批准或生产吞吐保证。

## 安全矩阵与剩余事项

A01–A18/A20 的实际测试函数逐项绑定于 JSON；A19 的经营 DML guard、审计脱敏与成本
已测，但整个依赖审查仍 BLOCKED。安全 PASS 必须区分已测范围与未闭合范围。
真实 iOS、软键盘、屏幕阅读器、生产入口网络隔离及真实组织/权限审批未验收。
S3 MCP Runtime 与最终用户委托未修改；S2 发现/S4 登录界面未提前实施。

`runtime-resume-r1-blocked.*`、`runtime-resume-r2-blocked.*` 原诊断文件字节保留；其中
未提交代码的当时 source hashes 是诊断快照，不改写为本次 Runtime 的新绑定。
260 个已提交 V0.16–V0.18 历史来源逐字节与基线核对无变化。
PR 中另报告最终 HEAD CI，不拿旧 CI 或本地结果冒充远端验收。

STOP：等待独立代码/安全复审。即使 CI 全绿，也不自动消除 A19/D03 或授权后续阶段。

## 首轮 PR CI 的测试库隔离修正

PR #717 首轮 HEAD `acc6038c4b42d25a23c434a74a1ce5864169da6e` 的
Run `38146985676` 在 postgres-task11 分片实际报错：
`Legacy tests cannot connect to a nonisolated database`。隔离保护正确拒绝
容器内仍沿用 `blueberry_peak` 名称的测试库；不删除或豁免该保护。
只将 postgres-task11 / postgres-domain-2 两个受影响任务的容器初始库、
health、upgrade 和 pytest 配置同步为明确的 `blueberry_test_*` 名称。
其他任务、测试集合、断言及生产入口不改变。新增离线检查锁定配置一致性。
全新独占 PostgreSQL 的同一 Task11 集合复测 510 passed / 5 deselected。
首轮远端失败记录保留，新 HEAD 必须重新取得完整 CI，不继承旧 HEAD 绿色分片。
