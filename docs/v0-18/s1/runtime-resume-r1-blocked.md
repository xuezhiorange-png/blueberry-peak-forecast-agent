# S1 Runtime 恢复执行：迁移回归门禁阻断

任务：V0_18_S1_HISTORICAL_HASH_ADAPTATION_AND_RUNTIME_RESUME_R1。
基线：320f2046e3105b1b55da9cb037892571110b584a；#716 已合并，push CI
38133854011 completed/success；最新正式 Release v0.17.0。

## 已完成与未完成

历史来源适配及回归：137 passed。仅允许变动的来源代码/已适配测试通过固定
#716 合并提交读取；所有冻结文档、JSON、manifest、截图和数学来源仍校验当前
工作树。原始预期 SHA256 未改。负向用例包括错误 digest、非法 revision、缺失
commit/blob、路径越界、合法当前代码变化和冻结文档篡改。

CI 仅为 unit-contract-golden/full-suite-canary 加 fetch-depth: 0 和显式
cat-file 检查，测试选择器和断言没有删减。尚未推送或运行本次 exact-head CI。

已加入未验收的运行开发成果：四表模型、Argon2id 25.1.0 依赖、认证/管理入口、
会话/CSRF、资源判定、响应释放 gate、受控入口和迁移草稿。这些代码尚未完成
A01–A20，不能被称为安全验收通过或完整 S1 实现。当前默认导出的 ASGI app
使用受控入口；旧 create_app 工厂保留在单独 legacy trust domain，网络隔离
尚未验证。当前代码需要后续完整安全审查和运行测试。

Ruff lint、format check 通过；backend/app Mypy：573 source files 通过。
既有 S1 HTTP、S2 Decision 和 S3 read-access 回归：163 passed，36 个既有
Pydantic deprecation warnings，67.20 秒。这些 legacy-domain 回归不能代替
新受控入口的 A01–A20。后者仍 NOT_EXECUTED。
迁移审计时唯一 head 为 0040_hierarchical_forecast，Alembic revision 命令
生成 ID d7766e57d4c8，但仓库缺失 script.py.mako，未生成模板文件；使用该
实际生成 ID 创建了独立迁移脚本，没有修改旧迁移或补建模板。

## 真实 PostgreSQL 失败证据

环境：独立临时 PostgreSQL 15.18 集群，loopback 端口 55439，数据库
blueberry_test_local_auth，合成测试数据库角色。没有连接生产数据库。
upgrade head 成功；新的 auth_account/auth_session/auth_resource_grant/
auth_audit_event 表已在此隔离库创建。未创建账号、密码、Session 或业务 grant。

实际执行 backend/tests/test_historical_backtest_alembic.py 的
test_historical_backtest_migration_round_trip_preserves_legacy_rows：

```text
backend/tests/test_historical_backtest_alembic.py:46
AssertionError: assert 'd7766e57d4c8' == '0040_hierarchical_forecast'
1 failed in 0.11s
```

该测试在第 46–48 行、第 163–165 行把当前数据库 head 写死为旧 revision。
新的合法认证迁移与此假设冲突。失败发生于写入 legacy fixture 之前，没有删减
历史业务保留断言，也没有执行该测试后续 downgrade。

## 所需定向授权

本次新增授权仅覆盖历史哈希来源读取和相关 CI 获取配置，不涵盖非哈希的旧迁移
运行验收断言。需要明确批准仅适配上述测试的两处“当前 head”断言：从实际
Alembic ScriptDirectory 唯一 head 取得当前期望值，并继续独立验证本次迁移
down_revision=0040_hierarchical_forecast。保留所有 legacy 表、列、记录、
upgrade/downgrade 和数据保留断言；不 skip/xfail，不更新旧 evidence/hash。

在该授权到位前暂停。全部开发成果在原独立工作树保存，未 commit/push/PR。
历史哈希适配 PASS 不等于 Runtime PASS；A01–A20 尚未执行；S1 正式完成 false。
D03 真实管理员及组织权威仍 PENDING；部署/Ready/Merge/Tag/Release 均未执行。
