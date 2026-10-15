# S5 隔离运行验收范围与证据映射

本报告仅对本 PR 新证据中的实际运行范围负责；不将历史 CI 或离线文案当运行结果。
主入口是实际 `create_app`；MCP 是实际 `create_service_account_app`，测试组合根只把
两者的数据库工厂绑定到隔离 PostgreSQL，没有替换认证或计算返回值。

## 验收矩阵

| 项目 | 实际测试来源 | 通过含义 / 限制 |
| --- | --- | --- |
| HTTPS_CONFIGURATION | S5 tls_server + real network tests；S4 HTTPS browser | 证书显式信任、Host/Origin、纯 HTTP 不进入 TLS、禁用不可信代理；非生产证书 |
| SECRET_CONFIGURATION_FAIL_CLOSED | S5 untrusted_host_origin_proxy_and_missing_secrets | 缺 bucket/signing key、坏组织/管理员目录 503；伪 actor、Host/Origin 拒绝；恢复配置可用 |
| LOCAL_AUTH_AND_CSRF | 重跑 backend/tests/local_auth 与 S4 browser | 真正 PREAUTH/session Cookie/Origin/CSRF；不是 mock 身份 |
| EXACT_RESOURCE_GRANTS | 重跑 business_access、local_auth、S3 PostgreSQL | BASE/REGION/COMPANY 不继承，Quality 独立，身份/hash 不变 |
| MCP_SERVICE_ACCOUNT_ROTATION | S5 operational_factory… / repaired_policy…、S3 policy | 真 SDK、旧 key 401、新 key 重新认证、禁用/撤权/修复策略；同机 POSIX 范围 |
| PRE_RESPONSE_REVOCATION | 重跑 local_auth ASGI release、business_access release、S3 cross-process release | 撤权先提交则不得释放敏感结果；已发字节不能撤回 |
| LEGACY_CONTROLLED_INGRESS_DENIAL | S5 real_network_legacy_denial_before_database 11 参数案例 + S1 L 矩阵 | 实际 TLS socket 到正式 HTTP app，403/no-store/null data，零 SQL；不是 MCP app 404 |
| UNAUTHORIZED_BUSINESS_READS_ZERO | S3 capability/exact grant sentinels、S1/S2 before-read tests | 拒绝前敏感业务读为零，不把合法 auth metadata 读算违规 |
| UNAUTHORIZED_SIMULATION_ZERO | S3 latest_policy_capability_denial、revoked_grant_denied_before_postgres_and_simulation | 未授权请求不执行模拟/比较；合法结果仍由原服务计算 |
| LOG_SECRET_REDACTION | S5 caplog 检查、assert_redacted 负向哨兵、runner 原始密码扫描、公开副本脱敏 | 私有原始与公开副本分别 SHA256；失败 traceback 中引用的测试密码也脱敏 |
| SYNTHETIC_BACKUP | S5 full_backup_restore_reapproval… | 真 pg_dump custom，全库备份；备份前后六类关键表 canonical row hash 不变 |
| SYNTHETIC_RESTORE_HASH_PARITY | 同上，JUnit properties | 真 pg_restore 到新 UUID DB，2 BASE/2 层级 run、各30日行、账号/grants Hash 及全 curve JSON 相等 |
| ROLLBACK_FAIL_CLOSED | S5 stop_revoke_restart_verify_then_manual_resume | 先停 admission、封存凭据与授权、同兼容版本重建、Hash 验证、人工恢复；无二进制降级或生产回滚 |

所有项目结论由新 evidence 的 `acceptance`、`local_backend.cases` 和实际输出承载。
代码中的测试名可直接定位断言。离线合同另外检查源字节、原始历史、canonical JSON、
截图唯一来源、Hash 与未授权的后续治理状态，不代替上表运行验收。

## 运行与证据层级

- 新增 S5 运行案例 19 项：整套运行228项后端，另有1项真实双工作进程补充测试。
  完整运行器还重跑 S1/S2/S3，不从前次阶段回执继承 PASS。
- 实际 TLS 浏览器套件 26 项；五页 × 六视口 × 两 Chromium projects，66 张新 PNG。
- 前端 unit 130 项；另行历史冻结合同子集 73 项；lint/typecheck/build、Ruff/format、
  mypy backend/app 都有实际日志。局部通过不等于全量 Canary。
- 最终 HEAD 的完整 GitHub CI、Canary、旧 Trial/前端全量回归，在提交后的独立 PR
  回执中记录；新 JSON 提交快照保留 PENDING，不能递归绑定自己未来的提交和 CI。
- 最终归档运行有开始/结束 UTC、实际 Python、所有权目录/端口、测试源 SHA256、
  subprocess exit 和 PostgreSQL shutdown 状态。生成器复核这些源字节。
- 原始私有 dump/证书 key/密码文件不进入 Git。恢复库在开放监听前封存旧密码、
  会话与 grants；测试专用显式密码重置只接受生成的隔离 DB 与 SYNTHETIC 账号。
- 所有冻结历史文档原字节不改；S5 不改生产 app、MCP、Dashboard、Schema、数学、
  API/工具输入输出、依赖或 workflow。

## 本轮自查失败的保留与纠正

1. 一次旧入口 POST 请求没有 JSON Content-Type，先被既有 middleware 拒绝为415；
   修正测试请求为合法 JSON，再证明真正的入口403。没有放宽生产拒绝。
2. 测试曾在 END_USER session 上尝试直接登录另一个账号，真实服务正确401；
   测试现在先 logout，再取得 PREAUTH，不绕过 CSRF。
3. 纯 HTTP 负向客户端最初继承环境代理，不能证明实际 TLS socket；现在该客户端
   trust_env=False，实际 loopback 握手失败，不能用转发 Header 升级连接。
4. 补强旧密码封存测试时漏了 SQL select 导入，已修复测试 import 并重新整套执行。

这些不是新生产安全缺陷；不删失败、不 skip、不降低断言，也不把早期阶段结果当
最终源版本证据。原始文件保留本地，公开脱敏副本与其原始 SHA256 同时归档。

发布工具随后发现中文截图文件名的 Git 转义解析问题，已改为 NUL 分隔清单；
首次发布工具源快照保存在 `23f2384517fc24badaa130a20d137b81260e7f7d`。
最终运行重新捕获全部当前源字节，不借旧源代替运行代码或离线发布工具。
离线文案测试还发现手册未写出等价 CLI 参数，已补充 `--no-proxy-headers`，
没有修改实际 TLS 配置（运行时已为 proxy_headers=False）。

提交后进一步自查发现表级 row JSON 解析可能把 NUMERIC 末位转换成浮点而丢失。
新 Hash helper 直接保留 PostgreSQL row JSON 原文，新增末位差异、行顺序和重复行
回归。仅修改 S5 新测试，不改业务 Decimal、ForecastIdentity、source/result hash。
初始 HEAD `2769de5cddeffaf53ac3c28f1ec5ca29f998543f` 与 CI #38681553305
及原 archive 保留，但不作为最终 HEAD 验收；新归档在 s5-safe-pilot-r1-r2。

最终覆盖核对另补双 MCP 工作进程验收：两个独立 PID、同一 PostgreSQL 和私有
FilePolicy，两账号分别在两个 TLS 端口并发访问自身记录并拒绝对方记录；合法读取
开始前，两个进程的敏感 SQL 计数均为0。一次策略轮换后两个进程都拒绝旧 key，
新 key 仍只可读取自身记录。进程与 socket 都由本用例关闭。仅新增测试文件，
不是跨主机/NFS 验收。补充 JUnit 绑定了该测试源码 SHA256；原整套运行源字节不变。
第一次补充测试误用 ORM 的 run_id 字段，实际主键为 id；修正测试字段后真实运行
通过，不改生产模型。HEAD `d75918fe95f0cc54f19be3c46876ba10b6c74ecc` 及其 CI
#38682829208 因补齐此验收而成为前序，不作最终 CI。最后以新 HEAD 完整 CI 为准。

## 风险和未验证项

前端依赖扫描仍有7个受影响包，详见独立审计报告；RSC-only 高危触发条件在当前
静态 SPA 未发现，不扩大为无漏洞或生产就绪承诺。工具链告警未修复。

生产网络隔离、多主机/NFS/Windows 撤权、真实证书/管理员/目录/服务账号、iOS
Safari/软键盘/屏幕阅读器、RPO/RTO/留存/容量/运维责任与升级阈值仍未闭合。
没有创建真实账号/grant，没有生产数据库操作、部署或当前采收数据访问。

S5_FORMAL_COMPLETE=false；PRODUCTION_READINESS=NOT_READY；S6_AUTHORIZED=false。
保持 Draft；独立评审、Ready/Merge、Deploy、Tag/Release 仍需 Owner 后续授权。
