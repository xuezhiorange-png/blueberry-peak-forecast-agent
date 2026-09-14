# V0.5 plan baseline

云南气候分区、多农场适用性与短周期峰值预测版。
English: Weather-Aware Multi-Farm Forecast & Operational Peak Forecasting.

这是 `V0_5_PLAN_BASELINE`，不是 v0.5.0 已发布或生产就绪声明。
当前正式 release 仍是 [v0.4.0](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/releases/tag/v0.4.0)。

- [开发计划与业务语义](development-plan.md)
- [阶段和最终验收门槛](acceptance-gates.md)
- [天气源候选评估](weather-source-evaluation.md)
- [农场位置输入模板](farm-registry-input-template.csv)

## 本次核验身份

```ini
TASK_ID=V0_5_0_WEATHER_MULTI_FARM_OPERATIONAL_PEAK_PLAN_BASELINE_R1
BASE_RELEASE=v0.4.0
V0_4_0_RELEASE_SHA=74293797aad2e057edd484ec6757cc54f4542461
CURRENT_MAIN_SHA=74293797aad2e057edd484ec6757cc54f4542461
MAIN_MOVED_SINCE_V0_4_RELEASE=false
PLAN_ONLY=true
IMPLEMENTATION_STARTED=false
S1_IMPLEMENTATION_STATUS=WAITING_FOR_FARM_LOCATION_INPUT
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

以上是本规划开始时 fetch 后的真实快照。仅新增本目录五个文档/模板；
不读取原始产量台账、封存 TEST 或私有 authority，不执行天气 API、模型或数据库操作。
本 PR 按当前仓库 CI 执行，包括 full-suite-canary，不做 docs-only 绕过。
提交时 CI 状态由 PR 的 exact-head checks 提供，不复用 v0.4.0 的绿色 CI。

## 如何填写模板

CSV 为 UTF-8、逗号分隔、仅表头，**零条农场记录**，没有示例坐标。
由业务人员逐农场填写，不要把说明文本当成数据行。字段说明：

| 字段 | 填写要求 |
| --- | --- |
| canonical_farm_name | 正式业务全称；alias 必须另附授权证据，不 fuzzy 合并 |
| province / prefecture / county / township | 用户确认的行政位置；不是 climate zone |
| latitude / longitude | 十进制度；USER_OR_AUTHORIZED_SOURCE_REQUIRED；缺失留空 |
| elevation_m | 海拔米；USER_OR_AUTHORIZED_SOURCE_REQUIRED；记录高程基准和来源 |
| productive_area_mu | 投产面积，正且 finite，单位亩；不是规划面积或由产量反推 |
| varieties | 可选来源元数据；多个值用分号；不自动变成品种级模型要求 |
| notes | 来源/确认人/确认日期、坐标参考系、定位精度、高程基准、缺失说明 |

经纬度必须成对，纬度范围 [-90,90]、经度 [-180,180]；坐标参考系和转换必须可审计，
不能把 GCJ-02/BD-09 原值静默标成 WGS84。范围检查通过不等于定位正确。
海拔必须 finite，不用统一正数规则排除合法低于海平面的值；云南适用性另审。
缺失经纬度允许 `LOCATION_STATUS=PENDING`（记入 notes，正式 registry 中单列），
但不得进入需要精确位置的 climate/weather authority。未知值不是 0。

完整 registry 的 provenance/review/status 字段见开发计划；模板只是用户输入层，
不会自动生成 `FARM_REGISTRY_V1`、zone mapping 或登记农场 authority。
下一外部输入是云南农场位置清单；当前仍不得自动生成精确坐标或海拔。

## 规划验证记录

2026-09-14 本地检查：五文件allowlist、11列/零数据行CSV、Markdown引用格式与本地链接、
一个候选YAML块解析、44个阶段任务和15项成功条件覆盖均PASS。官方来源链接已通过浏览工具
打开核对，不代表真实天气数据端点连接成功。未新增JSON或生产Python。
既有tracked文件未修改，`git diff --check` 通过；模板没有公式/数值，无需工作簿重算或图表渲染。
PR创建后执行现行CI，最终状态查看对应HEAD的checks，未完成不得宣称PASS。
