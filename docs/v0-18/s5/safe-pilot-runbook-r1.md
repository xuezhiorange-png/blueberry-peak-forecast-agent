# V0.18 S5 隔离合成安全试运行准备

TASK_ID=V0_18_S5_ISOLATED_SYNTHETIC_SAFE_PILOT_READINESS_R1

本阶段是 **ISOLATED_SYNTHETIC_SAFE_PILOT_READINESS**，不是部署或正式试运行。
基线 `89641834ab7a0bd902a23f9243325da5c163d518`；S4 #725 已合并，
push CI #38673985694 completed/success。正式 Release 仍为 v0.17.0。
Owner 本轮明确授权 S5；历史 S1–S4 的执行快照不回填。
仅新增测试、配置模板、运行手册和证据，不重新开发认证、预测、Dashboard 或 MCP。

## 1. 准备与资源所有权

使用锁定 Python 3.12 环境，PostgreSQL 15/16 客户端与服务器、OpenSSL、Node
及仓库锁定 npm 工具；先执行 `uv sync --frozen --group dev`、`npm ci --prefix frontend`。
如仓库现有安装命令不含 `--group dev`，以 pyproject 实际 dependency groups 为准；
不得为了运行手册修改锁文件。运行前确认 `python --version`、`pg_dump --version`、
`pg_restore --version`。dump 客户端不得低于服务端主版本。

在仓库根目录执行（路径改为新建的、此前不存在的私有目录）：

```sh
python -m backend.tests.safe_pilot.run --output /tmp/SYNTHETIC-s5-unique-run --browser
```

运行器拒绝现有目录，生成随机测试密码、SCRAM PostgreSQL、独立数据目录与空闲
loopback 端口，写出 owned-resources.json 后启动。每个测试另建 UUID 数据库并迁移；
literal SYNTHETIC 保存曲线由既有 repository 写入，不执行真实预测、训练或实际采收。
测试账号、密钥、证书只能在测试进程/私有目录中使用。这里没有真实 bootstrap。

脚本在 finally 中只停止自己 `-D` 指向的新 cluster。数据库清理由生成其 UUID 的
fixture/context manager 执行；不接受任意 DB 名作为删除参数。不操作 Docker，不
删除 volume，不扫描/停止其他进程。保留目录、原始日志和私有 dump，不自动递归删除。
异常终止后先检查 owned-resources.json、postmaster.pid、进程命令和目录，再人工
对本次 cluster 执行 `pg_ctl -D <该目录>/data -m fast -w stop`，不得按端口批量杀进程。

## 2. 可信配置与启动

`SYNTHETIC.env.example` 是不可直接运行的占位模板，不是生产配置。
复用 AppSettings、SimpleAdminCatalog、AuthService、Signer、FilePolicy/PolicyDocument；
无第二认证系统。组织目录和 exact identity/source hash 必须来自本次合成种子。
管理员无默认预测/Quality 权限；普通用户不能扩展目录。无自动 future-run 授权。

测试的 HTTP app 为真实 `create_app`，MCP app 为真实 `create_service_account_app`。
只在测试组合根替换 session factory，使两个入口使用同一 disposable PostgreSQL；
没有 monkeypatch 认证、授权或业务响应。MCP 私有策略由 FilePolicy.publish 发布。
缺 key、目录错误、无授权、错误 Host/Origin 和未可信身份均默认拒绝。

HTTPS 仅在 127.0.0.1 监听，生成短期 SAN=127.0.0.1 自签证书；SDK/HTTP 客户端
显式信任该证书。S4 Chromium harness 的 ignoreHTTPSErrors 仅适用于隔离证书，
**不是**生产证书验收。服务关闭 proxy_headers（CLI 对应 `--no-proxy-headers`），
不信任转发 Header；没有公网反代。
真实代理信任清单、证书签发与续期仍需 Owner 环境决策。

## 3. 验收路径

后端 runner 重跑 S1、S2、S3 及新增 S5：实际 Cookie/CSRF、本地账号、默认拒绝、
独立 Quality、BASE/REGION/COMPANY、请求中撤权、ASGI release、FilePolicy 多进程
轮换/取消/超时、八工具 schema 与完整 HTTP/MCP JSON/Decimal/hash 一致性。
未授权读取/模拟由现有 sentinels 与 SQL 观察断言验证，不以 HTTP 200 代替。

`--browser` 实际运行 S4 HTTPS/PostgreSQL 的 26 个浏览器用例，覆盖真实登录、
scope/list/selection、五页、产能模拟/比较、取消/迟到、退出与六视口。
两种 project 都是桌面 Chromium，窄视口不是 iOS Safari。
PR CI 继续执行原有完整前端 E2E 与 Canary，不改变 workflow 或门禁。

## 4. 旧入口网络边界

新增测试从**真实 loopback TLS socket**请求真实生产 HTTP app，覆盖 Trial list/create、
旧 MCP/SSE、actual-harvest imports、historical run routes、docs/openapi 和未知路由。
请求有效 Content-Type，不借参数错误掩盖入口判断。403/no-store/null data，且 SQL
计数为零。不是只测专属 MCP app 的 404。正式 app 的 ControlledIngress 不放宽。
旧 legacy test app 不部署、不接入此入口；根目录开发 Compose 不是安全部署模板。

此结论只证明本次隔离网络入口与应用默认拒绝。PRODUCTION_NETWORK_ISOLATION=
NOT_VALIDATED；没有修改防火墙、生产负载均衡或真实旧服务监听。

## 5. 密钥轮换与撤权

同机 POSIX 私有本地文件系统、稳定 lock inode；FilePolicy 独占锁发布单调 revision，
所有 worker 每次重新读取，响应实际发送期间持共享锁。先完成发布的撤权使旧结果
丢弃，不能撤回已经发出的字节。轮换后旧 key 401，新 key 重新初始化 SDK；删 exact
grant 后 FORBIDDEN；禁用与独立 Quality 由本轮重跑 S3 原运行测试验证。
故意破坏策略文件仅用于错误恢复实验，正常操作绝不能绕过 FilePolicy.publish。
NFS、Windows、多主机、跨节点撤权未验证；不满足拓扑要求即阻断，不关闭锁检查。

## 6. 备份、恢复与权限重新批准

测试对私有目录执行真实 pg_dump custom archive，全库备份含账号/grants/审计及
保存预测；私有备份含密码 hash 和 Session digest，必须按敏感材料保护，禁止提交。
备份期间前后表级 row-to-JSON canonical SHA256 相同。记录 archive SHA256。

创建全新 UUID 数据库、校验 archive hash 后 pg_restore --exit-on-error。**不开放
恢复库 listener**，先比对 Principal、role/status/auth/grant revision、完整 binding、
summary/daily/lineage 表级 hash 及实际 Canonical curve 全 JSON。

历史备份不是当前权限来源：恢复后立即事务性隔离所有 sessions/grants，递增账号
revision、以不保留的随机密码哈希封存旧密码并写恢复审计。旧 Cookie、旧密码、旧
handoff、备份后已撤销的 grant 均不可复活。
此流程仅作用于新恢复库，绝不更改原合成预测。MCP 策略与凭据不从 DB dump 恢复。
验证旧会话 401、重新登录无授权 403、ADMIN 无默认业务权限、无 allow-all。
测试操作员通过只允许 UUID 隔离数据库和 SYNTHETIC 账号的测试专用恢复函数，明确
重置新的测试密码并记录审计；这不是新增生产 bootstrap 或恢复 API，也不绕过登录。
真实灾备的身份核验/重置责任与工具需部署前另批，不能将此测试函数用于真实账号。
只有明确操作的管理员依据**当前可信目录**重新发 grant，重新登录后再次读取并精确
比较原始 source/projection/identity/daily Decimal；Quality 未单独重新授权则仍拒绝。
自动恢复授权不被支持。RPO/RTO 以真实运维需求另批，不虚构 SLA。

## 7. 故障与安全回滚

故障集涵盖真实 DB 连接失败及恢复（S1 A20）、缺认证密钥/错误目录与签名 key、
Host/Origin/HTTP、MCP 失效 key/缺损 policy、删除/Hash 漂移（S3）、请求取消/超时。
S5 独立回滚测试按顺序停止 admission → 撤销 sessions/grants → 保留现场与审计 →
重建同一已核验兼容版本 app → 核对 canonical hash → 人工确认恢复入口 → 重验旧
会话/资源/legacy 拒绝。没有真实二进制版本降级、数据库 down migration 或生产回滚。
换版本必须先确认迁移兼容性；不以关闭认证、默认管理员或 allow-all 回滚。

## 8. 日志、审计与漏洞

关闭 TLS 测试服务 access log；不记录 Cookie/Header/body/SQL parameters。自动扫描
密码、Cookie、CSRF、MCP key、PG 密码及 signing key；扫描器故意泄漏负向测试必须
失败。只发布经过核验的日志副本和 hash，私有 dump/凭据不发布。现有审计字段仍按
原合同使用，恢复事件用既有 auth_audit_event，不引入平台。

运行结束后，对本次私有 PostgreSQL、脚本及浏览器日志执行附加的自动扫描（不回显
凭据或日志原文）；HTTP/MCP Cookie/CSRF 实际值另由运行时 caplog 断言检查：

```sh
python - "$S5_EVIDENCE_ROOT" <<'PY'
import hashlib, json, sys
from pathlib import Path
from backend.tests.safe_pilot.operations import assert_redacted
root = Path(sys.argv[1])
needles = [root.joinpath('private-password').read_text().strip(),
           'SYNTHETIC-password-123', '__Host-blueberry-session=', 'X-CSRF-Token:']
for name in ('execution.log', 'postgres.log', 'browser.log'):
    raw = root.joinpath(name).read_bytes()
    assert_redacted(raw.decode(), needles)
    print(json.dumps({'file': name, 'sha256': hashlib.sha256(raw).hexdigest(),
                      'secret_scan': 'PASS'}))
PY
```

依赖审计报告单列生产包、开发/构建依赖、漏洞触发条件和补丁候选；不做 audit fix
或未经授权升级。CI 绿不消除告警，不可达判断仅适用于当前 SPA/static 部署形态，
未来启用 RSC、公开 Vite/Vitest 或处理不可信构建输入必须重新审计。

## 9. 正式试运行前待决 / STOP

RPO/RTO、日志留存、容量、运维责任人、升级阈值=PENDING_OWNER_DECISION。
真实管理员/组织目录/资源授权/生产凭据、HTTPS/网络配置、备份加密与保管责任、
真实设备与辅助技术、独立评审及部署授权均未完成。
本轮自签证书、合成管理员及临时策略不能沿用为真实 pilot 配置。
Upper80/90、run attribution、child contribution 仍不可用；不证明模型精度或真实 ROI。

S5_FORMAL_COMPLETE=false；PRODUCTION_READINESS=NOT_READY；S6_AUTHORIZED=false。
最终 exact-head CI 由提交后 PR 回执绑定，不回填冻结证据；Draft 后 STOP。
Ready/Merge/Deploy/Tag/Release 均未授权。
