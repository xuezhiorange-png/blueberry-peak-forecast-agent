# V0.5 plan baseline

云南气候分区、多基地适用性与短周期峰值预测规划。
R2明确以基地为预测实体；原R1的 Multi-Farm 名称/任务ID仅用于追溯。

这是 `V0_5_PLAN_BASELINE`，不是 v0.5.0 已发布或生产就绪声明。
当前正式 release 仍是 [v0.4.0](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/releases/tag/v0.4.0)。

- [开发计划与业务语义](development-plan.md)
- [阶段和最终验收门槛](acceptance-gates.md)
- [天气源候选评估](weather-source-evaluation.md)
- [基地位置输入模板](base-registry-input-template.csv)

## 本次核验身份

```ini
TASK_ID=V0_5_0_WEATHER_MULTI_FARM_OPERATIONAL_PEAK_PLAN_BASELINE_R1
CORRECTION_TASK_ID=V0_5_PLAN_BASE_ENTITY_CORRECTION_R2
BASE_RELEASE=v0.4.0
V0_4_0_RELEASE_SHA=74293797aad2e057edd484ec6757cc54f4542461
CURRENT_MAIN_SHA=74293797aad2e057edd484ec6757cc54f4542461
MAIN_MOVED_SINCE_V0_4_RELEASE=false
PLAN_ONLY=true
IMPLEMENTATION_STARTED=false
PREDICTION_ENTITY=BASE
AREA_GRAIN=BASE_TOTAL_PRODUCTIVE_AREA
WEATHER_GRAIN=BASE_REPRESENTATIVE_LOCATION
FARM_MEMBERSHIP=METADATA_ONLY
FARM_AREA_ALLOCATION_REQUIRED=false
BASE_REGISTRY_INPUT_AVAILABLE=true
S1_IMPLEMENTATION_CAN_START=true
S1_IMPLEMENTATION_STATUS=INPUT_AVAILABLE_NOT_STARTED
ELEVATION_STATUS=PENDING_EXTERNAL_VERIFICATION
WEATHER_SOURCE_AUTHORITY_FROZEN=false
WEATHER_MODEL_SELECTED=false
MODEL_CHANGED=false
AUTHORITY_CHANGED=false
DB_SCHEMA_CHANGED=false
MCP_CHANGED=false
READY_ELIGIBLE=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```

Git SHA为R1规划开始时fetch后的快照；实体/输入状态由本次R2用户确认更新。
本PR相对发布基线仅新增本目录五个文档/模板；
不读取原始产量台账、封存 TEST 或私有 authority，不执行天气 API、模型或数据库操作。
本 PR 按当前仓库 CI 执行，包括 full-suite-canary，不做 docs-only 绕过。
提交时 CI 状态由 PR 的 exact-head checks 提供，不复用 v0.4.0 的绿色 CI。

## 如何填写模板

CSV 为 UTF-8、逗号分隔、仅表头，**零条基地记录**，没有示例坐标。
由业务人员逐基地填写或从已提供资料对应，不要把说明文本当成数据行。字段说明：

| 字段 | 填写要求 |
| --- | --- |
| base_id | 稳定基地ID；未分配可暂空，后续登记赋值而非由农场名猜ID |
| canonical_base_name | 正式基地全称；alias 必须另附授权证据，不 fuzzy 合并 |
| covered_farms | 成员名称用分号分隔；仅历史归属/追溯/基地日量汇总，不用于面积分摊或独立预测 |
| province / prefecture / county / township | 用户确认的行政位置；不是 climate zone |
| latitude / longitude | 基地代表位置，十进制度；USER_OR_AUTHORIZED_SOURCE_REQUIRED；不要求各成员位置 |
| elevation_m | 基地代表海拔米，PENDING_EXTERNAL_VERIFICATION；记录高程基准和来源，未核验留空 |
| productive_area_mu | 基地总投产面积，正且finite，单位亩；保留原始总种植面积字段及对应确认，不分配到农场 |
| varieties | 可选来源元数据；多个值用分号；不自动变成品种级模型要求 |
| notes | 来源/确认人/确认日期、坐标参考系、定位精度、高程基准、缺失说明 |

经纬度必须成对，纬度范围 [-90,90]、经度 [-180,180]；坐标参考系和转换必须可审计，
不能把 GCJ-02/BD-09 原值静默标成 WGS84。范围检查通过不等于定位正确。
海拔必须 finite，不用统一正数规则排除合法低于海平面的值；云南适用性另审。
缺失经纬度允许 `LOCATION_STATUS=PENDING`（记入 notes，正式 registry 中单列），
但不得进入需要精确位置的 climate/weather authority。未知值不是 0。

完整 registry 的 provenance/review/status 字段见开发计划；模板只是用户输入层，
不会自动生成 `BASE_REGISTRY_V1`、zone mapping 或登记基地 authority。
用户已明确确认基地名称、对应农场、经纬度及基地总种植面积已提供；原R1位置输入阻断已解除。
本次确认是输入可用性的业务来源，不等于本轮已读取原始输入行、核验海拔或导入authority。
S1可以启动但本任务不实施；不得因未分摊成员面积或未逐农场采天气而继续阻塞。
海拔后续联网核验，本轮不调用外部数据服务。原R1模板由本次基地模板替代，旧内容保留于Git历史。

## 规划验证记录

R1本地检查记录：五文件allowlist、11列/零数据行CSV、Markdown引用格式与本地链接、
一个候选YAML块解析、44个阶段任务和15项成功条件覆盖均PASS。官方来源链接已通过浏览工具
打开核对，不代表真实天气数据端点连接成功。未新增JSON或生产Python。
既有tracked文件未修改，`git diff --check` 通过；模板没有公式/数值，无需工作簿重算或图表渲染。
PR创建后执行现行CI，最终状态查看对应HEAD的checks，未完成不得宣称PASS。

R2本地验证PASS：基地模板13列/零数据行、21个引用格式及本地目标/一个YAML块、成员元数据/聚合定义、
BY_BASE和cross-base评价一致性；04-15规则、7/15日整窗语义、PIT/天气增益要求保持不变。
7/15日语义章节与R1提交逐字一致；44个阶段任务、15项成功条件均保留。
只修改本目录规划与模板；不改变生产代码、authority、模型、数据库、MCP或CI配置。
