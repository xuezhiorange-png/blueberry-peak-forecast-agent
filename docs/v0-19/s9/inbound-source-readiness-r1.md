# V0.19 S9：入库来源接入准备与质量验收

## 能力与边界

这是离线、只读的来源验收工具，不是 ERP 连接器、导入器、运行时登记器或预测调度器。
它回答指定 Base、产季、Origin 的来源是否满足四项 Harvest State 特征所需的数据条件。
CLI 不签发预测、不加载模型参数、不读取评价标签；真实来源日重量执行始终拒绝。
本阶段不接触真实业务记录，不证明严格 PIT、前瞻准确率或生产就绪。

输入与解析复用 S8 `CONTROLLED_RECORDED_INBOUND_V1` 的 `InboundSnapshot`、`Index`、
`DayReference`、`Day`、`Record`、`PhysicalDefinition`、`TargetBinding`。
`inbound.inspect_days()` 是原运行时解析路径的逐日诊断接口；运行时 `load()` 仍在首个硬错误处拒绝，
离线工具保留全部不合格日期及原因。没有新增另一套数量解析器。
特征可计算性直接复用 S7 `engine.harvest_features()` 与冻结 V0.15 窗口计算，
报告窗口数量与该计算的缺失审计逐项核对。

`fact_receipt_raw` 的日期、重量、文件及去重身份可以提供部分来源线索，
但不能单独证明 Base 映射、每日成员完整性、零值或当时可见性；本工具不查询该表。
现有 I5/I7 FARM_PICK / OBSERVED_WEIGHT / KG 路径保留，不改成入库重量。
没有新表、Migration、HTTP API、Dashboard 或权限体系。

## 接入材料模板

`inbound-source-requirements-v1.json` 对应 `SourceRequirements` 的版本化合同，列出十类材料：
来源负责人及版本、事件/重量/单位、日期与跨日、精确成员键、品级、修订 Winner、
可见时间证明、每日完整性与零值、冻结 Fit 与目标口径、独立标签与成熟及权限。

负责人、证明引用和说明可留空；缺少证明显示 `PENDING_SOURCE_AUTHORITY`。
填写完整只表示材料已提交，仍是 `SUPPLIED_NOT_VERIFIED`。
程序没有“填写模板即批准来源”的状态转换。模板也不能赋予真实读取或登记权限。
报告不刊出填写者姓名、私有引用或自由文本，以防材料包含业务重量、路径或敏感信息。

## 可直接运行的合成样例

从仓库根目录，使用已安装项目依赖的 Python 3.12：

```sh
python -m backend.tests.rolling_forecast.source_readiness_package \
  --scenario complete --output-dir /tmp/SYNTHETIC-s9-package

python -m backend.app.rolling_forecast.source_readiness inspect \
  --catalog /tmp/SYNTHETIC-s9-package/SYNTHETIC-catalog.json \
  --context SYNTHETIC-INBOUND-CONTEXT \
  --source SYNTHETIC-INBOUND-SNAPSHOT --model SYNTHETIC \
  --origin 2026-11-05 --cutoff 2026-11-05T17:00:00+08:00 \
  --mode metadata --output-dir /tmp/SYNTHETIC-s9-metadata

python -m backend.app.rolling_forecast.source_readiness inspect \
  --catalog /tmp/SYNTHETIC-s9-package/SYNTHETIC-catalog.json \
  --context SYNTHETIC-INBOUND-CONTEXT \
  --source SYNTHETIC-INBOUND-SNAPSHOT --model SYNTHETIC \
  --origin 2026-11-05 --cutoff 2026-11-05T17:00:00+08:00 \
  --mode synthetic-full --output-dir /tmp/SYNTHETIC-s9-full
```

所有输出目录必须是新目录，不能覆盖旧证据。目录 0700，文件 0600；路径不能借助任意符号链接指向无关位置。
`--requirements` 可指定填写后的模板。Catalog、模板、来源索引均是明确指定、大小受限的对象，
不会发现或扫描其他目录。建议将 Catalog 与模板也设置为 0600。
退出码：结构有效的元数据报告或完整合成校验为 0；不完整或阻断为 2；不能把非零退出码当作成功。

每次检查生成：

* `readiness-report.json`：确定性的业务状态、窗口日期、原因及身份 Hash。
* `daily-readiness.csv`：逐日条数、成员覆盖、脱敏缺失成员、原因代码及中文说明。
* `readiness-report.html`：无网络请求或脚本的本地业务报告，可直接打开。

默认不输出原始重量、完整成员业务键、私有路径、模型参数、密钥或标签。
相同来源、Origin、截止点和模式得到相同业务摘要与文件；机器当前时间和输出目录不参与摘要。
源身份、日文件 Hash 或 cutoff 改变会保留其身份变化，而非伪装成相同快照。

## 两种模式

| 模式 | 读取范围 | 可以说明什么 | 不可以说明什么 |
| --- | --- | --- | --- |
| metadata（默认） | Catalog/要求模板/量无关 Index | 字段、来源/模型声明、成员、日期索引、品级互斥、完整性声明及截止点 | 不读 Day 或模型文件；M1 固定 NOT_PROVEN；索引完整不等于日记录已验收 |
| synthetic-full | 上述元数据 + 显式登记 SYNTHETIC_TEST_FIXTURE 的 D 之前 Day | S8 真正解析日记录、Hash/路径/身份/Decimal/修订/品级/时间/零值；S7 特征可计算性 | 不读取真实来源日重量；不证明真实物理等价性、真实授权或 STRICT_PIT |

真实来源即使本地存在、字段相同或 Hash 匹配，完整模式也返回
`REAL_SOURCE_EXECUTION_NOT_AUTHORIZED`，发生在来源数量读取之前。
使用者不得把真实文件重标记为 synthetic；此工具没有赋予其读取权限。
运行时 Catalog 的现有当前产季真实数据禁用限制继续生效。

### 状态解释

`METADATA_VALID` 只表示本次结构预检有效，窗口显示“声明完整”与“已验证完整”两栏，后者恒为 0。
`SYNTHETIC_FULL_VALIDATED` 只表示合成日记录与特征检查通过。
`INCOMPLETE` 表示缺日、部分成员、晚到或未知；M1 为 `NOT_COMPUTABLE`。
`BLOCKED` 表示身份/口径/Fit/Hash/路径/修订等硬错误。
所有报告仍保留 `PENDING_SOURCE_AUTHORITY`，`real_business_use_authorized=false`。
没有用元数据或报告替代 S7 的独立模型加载校验、运行权限及合法标签评价。

## 日期、物理口径与完整性

业务时区 Asia/Shanghai。D 为 origin 业务日，特征严格使用产季起点至 D−1；
预测目标为 D+1…D+15。CLI 要求显式带时区 cutoff，不自行猜测可见时间。
最近 7/14/28 日及产季累计分别给出要求日数、已验证完整日数、缺失、晚到、
时间未证明、部分成员、冲突及全部未验证日期。窗口早于产季起点时保留缺失，不补零。

入库来源复用名称为 `past_7d_harvest_kg`、`past_14d_harvest_kg`、
`past_28d_harvest_kg`、`season_to_date_harvest_kg` 的冻结特征，实际口径仍为
`RECORDED_INBOUND_WEIGHT`，不能宣称田间采摘量。
S8 的原始记录重量定义不自动等于净重、毛重、商品果或 SOURCE_002。
Fit 绑定与物理定义 Hash 是独立声明；合成证明不升级为真实来源权威。

只接受显式登记的 immutable revision winner 集合；重复 Logical ID 或 Revision ID 失败，
不自行挑选最大版本。跨日重复标出两个受影响日期。被排除品级不累计入特征，条数仍在报告中；
未经登记品级失败。没有记录且没有零值权威的日期保持缺失；确认零值与非零记录冲突失败。
来源时间、服务器接收、完整性可知时间必须满足 cutoff，缺失证明为未知，晚到为不合格。
真实来源历史无可靠 available_at 时，不能据此宣布严格 PIT。

## 九类合成场景及业务流程验收

包生成器支持 `complete`、`missing-day`、`partial-member`、`confirmed-zero`、
`late-record`、`duplicate-revision`、`basis-conflict`、`fit-mismatch`、`metadata-only`。
每个包显式标记 `SYNTHETIC_TEST_FIXTURE`，不创建真实 SOURCE_AUTHORITY，
生成的 Catalog 默认无 capabilities，且不会安装到运行时配置。
使用已冻结的公开合成 S8 模型字节，不训练或修改模型参数。

`test_source_readiness_postgres.py` 在任务自建 PostgreSQL 上经过正式 ASGI、Session、CSRF、
权限、S8 来源解析、S7 特征及 Ridge、保存/日行独立复算/重新读取、Origin 比较。
合成完整来源 Nov 5 / Nov 6 的 M1 H7/H15 保留既有结果：

| Origin | H7 kg | H15 kg |
| --- | ---: | ---: |
| 2026-11-05 | 538.941049 | 1031.362335 |
| 2026-11-06 | 526.137595 | 1002.702182 |

共同目标日期 14 日。不同窗口的总量变化与共同日期逐日修正由已有 compare 分开报告。
缺日、部分成员或晚到时 M1 不可计算；仍可独立计算的 M0 明确保留对照身份。
S9 不自动签发任何预测。上述 API 调用只由明确的合成集成测试执行。

### 本地验收

```sh
pytest -q backend/tests/rolling_forecast/test_source_readiness.py \
  backend/tests/rolling_forecast/test_source_readiness_cli.py
python -m backend.tests.rolling_forecast.run \
  --output /tmp/SYNTHETIC-s9-pg-browser-new --browser
ruff check .
ruff format --check .
mypy backend/app
```

PostgreSQL/HTTPS 使用现有 S5 自有资源协议，核验身份后关闭并等待退出；不停止其他服务。
S7/S8 前端、权限、独立评分与 FARM_PICK 回归沿用原测试，不改其断言或冻结 Hash。
当前真实业务数据、当前产季导入/评分、重新训练、来源转换、模型晋级及部署均未执行。

## 真实接入前仍需责任人提供

精确来源系统/负责人/版本；入库事件与重量字段（毛/净/原始值）的业务证明；
日期跨日及时区规则；逐成员精确 Base 映射及每日覆盖；品级/修订/撤销权威；
零值与缺失依据；来源、接收及可见时间证明；与冻结 S6 目标的等价性及 Fit 绑定；
独立标签成熟与评价许可。真实读取、受控登记、预测执行和评分仍是分别批准的操作。
本工具输出接入缺口，不自动创设这些证明或权限。
