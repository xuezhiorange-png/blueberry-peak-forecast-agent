# TD-01H — 合成 PostgreSQL 恢复失败根因与最小修复

`TASK_ID=BLUEBERRY_TD01H_SAFE_PILOT_POSTGRES_RESTORE_ROOT_CAUSE_R1`

## 根因与证据边界

基线 main `d070331756a83e9a0247157298204a34271fe3f0`。CI
`41265226227` 与 PR #781 的 `41268116287` 均在原
`test_full_backup_restore_reapproval_and_fail_closed_rollback` 的恢复阶段失败。
两份日志的 PostgreSQL 16.15 服务端均明确拒绝 `transaction_timeout` 参数。
旧日志没有记录客户端精确版本，因此不把两次失败的表面相同当作二进制身份相同的证明。
本轮没有重跑这些 CI，也没有修改 PR #781。

已证明的机制是：未按目标服务端主版本绑定的恢复客户端，在初始化恢复会话时使用了
PostgreSQL 16 不支持的设置。不是备份 Hash 损坏，也不是已存在业务表导致的冲突。
PostgreSQL 17 才引入该参数，且官方不保证较新客户端的输出可向旧服务端恢复：
[17 release notes](https://www.postgresql.org/docs/17/release-17.html)、
[pg_dump compatibility](https://www.postgresql.org/docs/18/app-pgdump.html)。

## 实际受控复现

仅由现有 `backend.tests.safe_pilot.run` 创建本机临时 PostgreSQL 16.15。
使用同一个合成源库、相同权限及数据，分别创建新空目标库；恢复均保留
`--exit-on-error`、`--no-owner`、`--no-privileges`。

| 备份客户端 | 恢复客户端 | 服务端 | 实际结果 |
| --- | --- | --- | --- |
| 16.15 | 16.15 | 16.15 | exit 0；六类源快照逐字段 Hash 完全相等 |
| 18.1 | 18.1 | 16.15 | exit 1；明确的不支持参数错误 |
| 16.15 | 18.1 | 16.15 | exit 1；同一不支持参数错误 |

三组归档均通过元数据列表检查，恢复前后文件 Hash 不变，目标库预先确认为空。
源库快照未改变，所有新建数据库随后删除。第三组直接证明该设置可由恢复客户端自身发出，
并非必须来自较新备份客户端。官方 18.1 源码的固定恢复会话初始化也提供独立佐证。
归档列表成功仅证明元数据可读；文件完整性与数据一致性另由 Hash 及成功恢复快照验证。

另一次完整执行未经修改的原测试：仅增加诊断、尚未修复客户端选择时，18.1 默认客户端
实际在恢复阶段失败；修复后即使 PATH 仍先提供 18.1，原测试也成功。其原测试文件原字节保留。

18.1 客户端仅从官方源码在任务自有临时目录构建，不安装服务、不变更项目依赖：
源码 SHA256 `ff86675c336c46e98ac991ebb306d1b67621ece1d06787beaade312c2c915d54`。
版本对照使用不压缩的合成归档，避免这个精简本地客户端构建缺少压缩支持这一额外变量。
外部探针首次缺少 pytest 异步配置及首次压缩归档对照失败的原记录均保留；不作为根因 PASS。

## 最小修改

- `operations.pg_command` 在既有测试身份校验后读取真实服务端主版本，选择同主版本
  `pg_dump` / `pg_restore`。只检查 PATH、现有本机服务器工具的同目录和精确的 Debian
  版本目录，不扫描私有目录；缺少匹配客户端明确失败，不退回不兼容客户端。
- 所有原恢复参数、非零退出失败、备份 Hash、隔离、撤销、重新批准和旧密码失效逻辑不变。
  不修改正式应用、数据库迁移、预测或 CI 工作流。
- 失败仅导出受限诊断字段，原退出码保留。未匹配明确证据时返回
  `UNKNOWN_UNCLASSIFIED`；默认 stderr 没有可靠 SQLSTATE，记录 null，不猜测。
- 原始 stderr/SQL/路径/连接参数不进入异常或报告；返回失败前同时清理 traceback 帧内
  参数、环境及 CompletedProcess 内容。负例包含合成密码、Cookie、Token、路径和业务字面量。
- 缺少同版本客户端的预检异常也有 RED→GREEN 脱敏负例。版本探针只接收 PATH 与
  LC_MESSAGES，不接收数据库凭据；失败前清理选择器输入和捕获输出，并移除携带私有路径的
  worker traceback。继续抛出固定的 MATCHING_CLIENT_REQUIRED，不执行恢复、不忽略错误。
- 仅设置客户端 `LC_MESSAGES=C`，不设置 `LC_ALL`、`PGCLIENTENCODING`、`PGOPTIONS` 或
  时区，不修改服务端区域设置。实际对照证明：本地化消息会使坏归档分类成为 UNKNOWN，
  固定消息语言后归类 INVALID_ARCHIVE；两者均以非零码拒绝恢复。

## 历史源码与断言

S5/S6 原证据的 operations.py SHA256 保持
`4e2b8805d4c1fc6adc621d2ac75818b40a2f058bd27603a55269f786c9762caa`。
已独立核对原 `97eb4417344f5950927cd65cf77ea3fdfa6f7d44` 与
`2b890d8e68a47ca506e7cf6b04bd187472138b2d` 的精确代码字节。
两处既有历史源码读取白名单仅增加这个路径，保留所有原 expected Hash 和比较断言；
S6 既有 wrong-commit/wrong-hash 负例也实际覆盖新增路径。
原恢复测试、Local Auth fixture、Runner 和 CI 工作流字节不变；原断言 AST 不变。
当前运行能力由新增 PostgreSQL 回归证明，不继承旧历史验收 PASS。

## 验证及停止边界

实际结果见同目录 `td01h-sanitized-diagnostic-evidence-r1.json` 与
`td01h-before-after-regression-r1.json`。本地验证使用已提交代码
`5b444af08a9117f6f5076786ca731abacee78bf1`；后续提交仅登记本轮脱敏证据。
完整 exact-head CI 必须在最终 HEAD 独立验收，本文不预填成功，终态记录在 PR 回执。

预检脱敏补充前的完整安全回归为 **266 PASS / 0 FAIL / 0 SKIP**，包含原完整恢复测试、三个新增真实
PostgreSQL 回归和八项原 Runner 清理场景。TD-03G 实驱动生命周期 **8 PASS**，
历史与诊断专项 **34 PASS**；另有 Local Auth / MCP / Forecast Intelligence 相关
非 PostgreSQL 合同 **1345 PASS / 70 DESELECTED**。全仓 Ruff、Format 与
app/research strict Mypy（643 个源文件）通过。最终源码的追加结果见机器回执。
上述本地结果不替代远端整仓 CI。

预检脱敏补齐后的最终源码重新完整执行：安全链路 **268 PASS / 0 FAIL / 0 SKIP**，
历史与诊断专项 **36 PASS**，TD-03G **8 PASS**；十次自有 Runner 的进程和端口均已清理。
旧成功与失败记录各自保留，没有把被取消 CI 或先前结果重新标为最终 HEAD 成功。

旧 HEAD `1110c40958053489a0a347b82977d5effc010b5f` 的 CI `41277279697`
在证明预检 traceback 脱敏缺口后取消并保留，未重跑该 SHA。新测试与修复提交后，
重新固定源码和最终 HEAD 验收；这不是反复重试偶发失败，也不修改两次原失败 CI。

报告是运行诊断元数据，不是可登记的数据集或业务来源：不含数量行，不申请合成来源登记或
公开数据许可。初次把报告标成 dataset `data_class=SYNTHETIC_ONLY` 被原公开增量门禁拒绝；
现明确使用 evidence_kind，保留实际测试范围和失败记录，门禁、基线、验证规则均未修改。

首次扩展安全回归为 261 PASS / 1 FAIL / 0 SKIP，失败是本轮新增坏归档分类负例；
独立消息语言对照后修复为仅固定 LC_MESSAGES，失败 JUnit 与清理证据保留。
最终源码的完整安全回归、既有 SIGTERM/失败中断/其他实例保护、TD-03G 实驱动生命周期、
历史合同、Ruff/Format/strict Mypy 均单独记录，不以单节点成功代替整仓 CI。

所有诊断均为独立合成测试。未访问真实业务库、真实工作簿或 SOURCE_002，未修改历史证据、
Tag、Release 或真实数据。旧 CI 的精确客户端版本仍不可追溯；本轮也不宣称修复其另一个
前端故障。PR #781 保持原 Draft/HEAD，只有本修复独立审核合并后才能另行同步与验收。
不执行 Ready、Merge、部署、重写历史或后续版本开发。
