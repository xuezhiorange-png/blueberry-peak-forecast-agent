# V0.5.0 正式开发计划（规划基线，待 Coordinator review）

TASK_ID=V0_5_0_WEATHER_MULTI_FARM_OPERATIONAL_PEAK_PLAN_BASELINE_R1
CORRECTION_TASK_ID=V0_5_PLAN_BASE_ENTITY_CORRECTION_R2

版本名：云南气候分区、多基地适用性与短周期峰值预测版。
规划业务粒度：Base；原版本名称中的 Multi-Farm 不代表逐农场独立预测。

## 1. 基线与本轮授权

基线为 v0.4.0 / `74293797aad2e057edd484ec6757cc54f4542461`；开始时 main 同 SHA，
`MAIN_MOVED_SINCE_V0_4_RELEASE=false`。分支从 release boundary 创建。
本轮只冻结规划语义、阶段、验收条件和输入模板；所有阶段实施均未启动。
天气研究进入**下一版本规划范围**，不等于本 PR 获准训练、接 API、采购或部署。

R2 用户明确确认已提供基地名称、对应农场、经纬度、基地总种植面积；据此解除原R1位置输入
阻断。本条消息没有展示实际行值，本轮不声称完成逐条数据审计或生成新authority。
`BASE_REGISTRY_INPUT_AVAILABLE=true`、`S1_IMPLEMENTATION_CAN_START=true` 表示输入前置条件
已可启动，**不是本任务执行S1的授权或S1验收通过**。海拔仍为
`ELEVATION_STATUS=PENDING_EXTERNAL_VERIFICATION`，后续联网核验不在本轮执行。

```ini
PREDICTION_ENTITY=BASE
AREA_GRAIN=BASE_TOTAL_PRODUCTIVE_AREA
WEATHER_GRAIN=BASE_REPRESENTATIVE_LOCATION
FARM_MEMBERSHIP=METADATA_ONLY
FARM_AREA_ALLOCATION_REQUIRED=false
```

v0.4.0 的 B1 产品、两农场 authority、即时上一完整产季要求、fail-closed、五个 MCP tools、
immutable history 和 canonical hash 继续有效。参见 [v0.4.0 Release](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/releases/tag/v0.4.0)、
[确定性修复证据](../next-version/area-forecast-canonical-share-p1.md)、
[V0.3 closeout](../v0-3/v0-3-version-closeout-and-acceptance-reconciliation-r1.md)。
README 长期愿景与旧阶段默认规则不是本轮 authority。本次明确的 04-15、7/15 日和分层适用性
决定仅约束未来 v0.5；不回写 v0.4/R1–R7B 的预测、实验结论、旧 hash 或封存 TEST。
v0.5-S4 与历史 V0.3 S4 是不同版本阶段，不能借同名重开旧预算或 TEST。

## 2. 六个一级业务目标

| ID | 冻结目标 |
| --- | --- |
| V0_5_GOAL_1 | 引入合理天气数据源，针对云南典型气候带研究气候影响 |
| V0_5_GOAL_2 | 扩大多基地适用性，不再仅限完整同场历史的少数农场 |
| V0_5_GOAL_3 | 7日/15日峰值定义为对应未来完整窗口中的最大单日产量 |
| V0_5_GOAL_4 | 统一业务有效采收季截至结束年份的04-15，排除尾果/过熟果/晚季非业务量 |
| V0_5_GOAL_5 | 天气增益必须通过 PIT 历史验证，不能用事后未来实际天气证明 |
| V0_5_GOAL_6 | 跨基地、跨气候带、跨产季验证；杨柳 golden 仅作工程回归 |

## 3. 业务有效产季 authority

```ini
BUSINESS_SEASON_CUTOFF_MONTH_DAY=04-15
PREDICTION_LATEST_MONTH_DAY=04-15
ARRIVAL_EQUALS_HARVEST=true
POST_CUTOFF_RECORDS_DELETED=false
```

产季 Y–Y+1 的业务截止日为 **Y+1-04-15，Asia/Shanghai 当地日包含当日**。
先按合法 season identity 归属并确认 season_start，再比较完整日期与该截止日；
不得用月日字符串过滤而误删前一年7–12月属于同一产季的记录。
本次只冻结终点；不根据目标季实际首采日反推预测起点，不虚构全年365日窗口。

- `[season_start, business_cutoff_date]` 内合格数据属于 `BUSINESS_SCOPE`。
- 截止日之后同季原始记录属于 `OUT_OF_BUSINESS_SCOPE_TAIL_FRUIT`：保留、audit only、
  不删除、不填0、不进入总产、亩产、shape、weather 标签、峰值识别或模型评价。
- `business_season_total_kg` 在基地粒度命名为 `base_business_total_kg`。
- `business_yield_kg_per_mu` 在基地粒度命名为 `base_business_yield_kg_per_mu`，
  分母为基地总投产面积，精确定义见第5节。
  缺面积或业务窗口内部标签不完整时不得把部分累计量叫完整整季亩产。
- 调用 `season_end > target-season cutoff` 返回 `SEASON_END_EXCEEDS_BUSINESS_CUTOFF`，
  fail closed，禁止 silent truncation。旧 v0.4 接口/历史结果不在本 PR 执行这一新规则。
- 已授权 complete source 下，source-active 且 farm 无记录可为 ledger zero；全源无记录仍为
  UNKNOWN，不能用截止日政策掩盖窗口内部缺数。post-cutoff absence 不是零产量或删失缺口。

S1-01 每个 base × season 未来必须产生：`raw_first_harvest_date`、`raw_last_harvest_date`、
`business_cutoff_date`、`pre_cutoff_total_kg`、`post_cutoff_total_kg`、`post_cutoff_ratio`、
`pre_cutoff_peak_date`、`pre_cutoff_peak_kg`、`post_cutoff_peak_date`、`post_cutoff_peak_kg`、
`post_cutoff_peak_exceeds_business_peak`。ratio 分母为该季已记录的 pre+post 总量，
分母0或覆盖不足需标不可计算/覆盖限制；不能将此 ratio 当季节完整性证明。
无正量或未知标签情况下不虚构峰日期。保留源 hash、旧规则版本、新业务域版本及排除行清单。
历史所有产季在未来 v0.5 数据副本中按新规则重算；旧 R7B 仅修改2526的结论保持原样。

## 4. 运营 7日 / 15日峰值语义

D 为 forecast origin/as_of 的 Asia/Shanghai 当地日期；数据可得性以精确 cutoff timestamp 控制。
业务日历日是连续自然日，包含周末/假日，不是工作日。
`W7={D+1,...,D+7}`，`W15={D+1,...,D+15}`；整窗必须落在合法业务季且每一天都有预测。
不能通过跳过未知日或跨季拼接凑满窗口。

| 指标 | 窗口总量 | peak date / peak kg |
| --- | --- | --- |
| FORECAST_7D_PEAK | W7 每日 kg 求和，`forecast_7d_total_kg` | W7 最大单日 kg；并列取最早日期 |
| FORECAST_15D_PEAK | W15 每日 kg 求和，`forecast_15d_total_kg` | W15 最大单日 kg；并列取最早日期 |
| v0.4 max_rolling_7day_total_kg | 全季滑动7日累计的最大值 | 旧指标，不能重命名为上述运营单日峰值 |

输出至少分别包含 `forecast_7d_status/start/end/total_kg/peak_date/peak_kg` 与
`forecast_15d_status/start/end/total_kg/peak_date/peak_kg`（正式 schema 可用嵌套表示）。
成功状态候选为 `COMPUTABLE_FULL_WINDOW`；不足整窗为 `NOT_COMPUTABLE_FULL_WINDOW`，
total/peak 为空而非0，start/end 可保留请求整窗边界便于审计，附原因/实际覆盖天数。
forecast season 已结束、起点未到或窗口数据不全同样不能假称完整指标。

例如 D=04-10，仅04-11..04-15五天，7日和15日均不可计算；D=04-08，7日完整；
D=03-31，15日完整；D=04-01，15日不完整。可另报 `remaining_business_window_peak_date`、
`remaining_business_window_peak_kg`、`remaining_business_days`，不得冒充7/15日。
评价峰值还需实际标签覆盖整窗；只存在预测不代表能评价精度。

## 5. Base Registry 与位置输入

规划 registry（未创建表、未导入真实 records）：

| 字段组 | 字段与约束 |
| --- | --- |
| 身份 | base_id, canonical_base_name, aliases；稳定ID，exact/授权alias，禁止 fuzzy 自动合并 |
| 成员 | covered_farms；只用于历史归属、身份追溯、基地日量汇总，保留来源与归属有效期间 |
| 行政位置 | province, prefecture, county, township；不直接充当气候带 |
| 地理 | latitude, longitude为基地代表位置；elevation_m待外部核验；附坐标系、精度、高程基准 |
| 业务规模 | productive_area_mu为基地总投产面积，正finite亩数及来源；varieties可选metadata，不强制拆模 |
| 历史 | historical_seasons, historical_season_count；由合格季清单派生，不把每日行数当季数 |
| 分区 | climate_zone_id, climate_zone_version；仅经审计mapping，不按州市填充 |
| 适用性 | data_completeness_level, applicability_level；资格与置信声明分开 |
| 生效与溯源 | active, effective_from, effective_to, provenance, review_status；变更可追溯 |

位置输入规则和字段模板见 [README](README.md) 与 [CSV](base-registry-input-template.csv)。
`latitude/longitude/elevation_m=USER_OR_AUTHORIZED_SOURCE_REQUIRED`。不从名称推断精确坐标。
面积来源字段“基地总种植面积”的原始名称应保留；导入时记录其与本轮基地总投产面积业务口径
的对应确认，不臆造数值或分摊。分母只绑定基地一次，不要求农场级面积、独立天气或独立预测。
历史量与基地面积必须属于同一归属范围和有效期间；成员变更要留证，不能把不一致的历史范围
静默并入。不得推导、跨基地复制或把 PREVIOUS_SEASON_PROXY 自动升级；未来请求亩数不自动
继承历史面积。这里不改变v0.4历史同农场面积authority。
只在未来授权实施时形成真实 registry；本 PR 的模板零数据行。

基地聚合定义（同一日、同一业务季、合法成员有效范围）：

```text
base_daily_harvest_kg = sum(all BUSINESS_SCOPE farm daily harvest rows belonging to the base)
base_business_total_kg = sum(base_daily_harvest_kg from season_start through Apr-15)
base_business_yield_kg_per_mu = base_business_total_kg / base productive_area_mu
```

`covered_farms` 是归属元数据，不是逐农场模型输入。先按可追溯grain去重、确认覆盖完整再汇总；
基地已有汇总行与成员明细不可重复相加，同条历史记录不得重复归属两个基地。
成员未知日不能被部分求和抹去；业务窗口内部UNKNOWN/不完整保持资格状态，不能用面积比例补量。
成员明细可作诊断，不作为正式预测、面积分配或独立样本粒度。

`WEATHER_LOCATION_POLICY=BASE_REPRESENTATIVE_LOCATION`：相邻成员农场统一使用用户提供且
经审核的基地代表经纬度/海拔气候画像，不要求逐farm天气。只有后续实际证据显示明显海拔跨度、
气候带差异或地理跨度，才可另行审查升级 `MULTI_POINT_BASE_WEATHER`；首版不默认多点，
不现在设置任意距离/海拔阈值，也不自动生成代表点。

## 6. 云南气候画像和候选分区

`YUNNAN_CLIMATE_ZONE_COUNT=TO_BE_DETERMINED_FROM_DATA`。
INITIAL_CANDIDATE_ZONES 可讨论低海拔暖热、中低海拔亚热、中海拔高原温和、中高海拔凉爽、
高海拔冷凉，但这些是概念，不是已确定的五个zone、边界或实测基地归属。
最终数量/边界由真实基地位置、长期气候画像、样本规模、区域代表性及稳定性审查决定。
样本不足可保留未分配状态，不能硬凑类别或直接使用州市行政区。

候选画像特征：latitude, longitude, elevation_m, Tmean/Tmin/Tmax climatology, GDD,
chilling, diurnal_temperature_range, rainfall, rainfall_seasonality, relative_humidity,
VPD, solar_radiation, ET0。长期正常期及每日/季节汇总规则需独立版本；PIT 中正常期也不能
偷用预测起点之后才形成的数据/修订。未来输出 `CLIMATE_ZONE_PROFILE_V1` 与
`BASE_CLIMATE_ZONE_MAPPING_V1`，本轮不生成真实画像或分区结果。

## 7. 天气研究与 PIT

四类数据、候选矩阵和待验点见 [天气源评估](weather-source-evaluation.md)。
研究绝对值及相对于 base/zone 同期正常值的 anomaly，但不假设云南所有zone共享阈值。
候选：Tmin/Tmax/Tmean, rainfall, relative_humidity, VPD, solar_radiation, ET0, GDD,
chilling_hours, frost_hours, heat_stress_hours, consecutive_rain_days；以及
Tmean_anomaly, GDD_anomaly, rainfall_anomaly, VPD_anomaly, radiation_anomaly。
GDD基温、chilling模型、霜冻/热胁迫/连续雨阈值是待验证参数，不能现在写农学常数。

```ini
FUTURE_WEATHER_LEAKAGE_ALLOWED=false
HISTORICAL_BACKTEST_REQUIRES_AS_ISSUED_FORECAST=true
WEATHER_MUST_BE_USED=false
WEATHER_MUST_PROVE_INCREMENTAL_VALUE=true
```

origin=2025-03-01 验证03-02..03-16：只能使用起点前实际可得的历史与当时发布的预报；
不能拿03-02..03-16事后实际天气作预测特征。现时重分析允许关联研究，不冒充实时可得天气。
先冻结来源资格、时点、候选/超参/权重/分层/阈值，再训练并冻结预测hash，之后打开评价标签。
跨基地训练也不能带入任何起点之后的记录；归一化、插值策略、气候normal、特征选择在训练折内。
旧已看过窗口声明 retrospective/not blind，新留出只评一次；新数据授权不等于解除旧封存TEST。

## 8. 多基地 Applicability 与两个天气问题

LEVEL_A/B/C 统一按BASE判定；history_season_count是基地完整业务季数，不是成员农场数量。
正式业务评价为BY_BASE/cross-base/out-of-base；农场级输出仅可另列诊断，不替代基地模型结果。

| 等级 | 主要候选信息 | 限制 |
| --- | --- | --- |
| LEVEL_A | 充分base history + climate zone + weather | 充分的数值定义在样本审计后冻结，不能仅按1季天数认定 |
| LEVEL_B | climate-zone prior + limited base calibration + weather | 需独立验证有限历史迁移，不保证同A证据 |
| LEVEL_C | climate-zone prior + geographic/agronomic metadata + weather | 不是LEVEL_A_CONFIDENCE；无位置/zone/authority仍可不支持 |

每次披露 applicability_level, evidence_level, history_season_count, climate_zone,
fallback_level, limitations。目标是登记基地进入统一体系，不等于任意名称或所有登记条目立刻能出量。
`UNKNOWN_UNREGISTERED_BASE_FAIL_CLOSED=true`；禁止 unknown base → company global mean。
未来分层prior需单独版本和审查，不能改变当前 AREA_YIELD_B1_V1 的无fallback合同。

仅规划比较：Global baseline、Climate-zone baseline、Climate-zone + base effect、
Hierarchical/partial pooling、Mixed-effects、Regional ML + base calibration。历史充分时
base-specific证据权重可更高、历史少时pooled证据可更多，具体权重不得本轮预定或据已看标签调整。

S4A WEATHER-AWARE YIELD：研究 baseline yield + zone + base effect + weather anomaly
是否改善 kg/亩及总kg；无稳定增益允许 `KEEP_BASE_TOTAL_MODEL=true`。
S4B WEATHER-AWARE PHENOLOGY / DAILY SHAPE：研究天气→成熟节奏→share→daily kg→峰值，
可提前/延后、集中/分散。允许 TOTAL_KG_UNCHANGED 且 DAILY_SHAPE_CHANGED/PEAK_DATE_SHIFTED。
`WEATHER_TOTAL_MODEL_RESULT=NO_STABLE_GAIN` 与 `WEATHER_SHORT_HORIZON_RESULT=STABLE_GAIN`
可以并存；总量和形状独立判定，不强造天气胜出。

## 9. 六阶段与交付物（全部为未来任务）

| 阶段 | 冻结任务清单 | 输出与入口 |
| --- | --- | --- |
| V0.5-S1 BUSINESS_SEASON_BOUNDARY_AND_BASE_CLIMATE_FOUNDATION | S1-01 历史04-15基地聚合审计；S1-02 Base Registry contract；S1-03 基地位置导入/校验设计；S1-04 代表位置长期画像生成设计；S1-05 云南候选分区；S1-06 base→zone mapping freeze | BUSINESS_SEASON_SCOPE_AUTHORITY_V1 / BASE_REGISTRY_V1 / CLIMATE_ZONE_PROFILE_V1 / BASE_CLIMATE_ZONE_MAPPING_V1；INPUT_AVAILABLE_NOT_STARTED，海拔待核验 |
| V0.5-S2 WEATHER_DATA_AUTHORITY_AND_POINT_IN_TIME_PIPELINE | S2-01 源候选审计；S2-02 climatology链；S2-03 historical actual链；S2-04 as-issued链；S2-05 live链；S2-06 snapshot/version/hash；S2-07 缺失/延迟/fail-closed | WEATHER_SOURCE_AUTHORITY_V1 / BASE_WEATHER_SNAPSHOT_V1；需合法位置和来源许可 |
| V0.5-S3 MULTI_BASE_APPLICABILITY_BASELINE | S3-01 v0.4算法在04-15域新基线；S3-02 global pooled；S3-03 zone baseline；S3-04 partial pooling候选；S3-05 A/B/C定义；S3-06 out-of-base验证；S3-07 selection | MULTI_BASE_APPLICABILITY_POLICY_V1 / MULTI_BASE_BASELINE_V1；需S1、合法数据与冻结评估设计 |
| V0.5-S4 WEATHER_AWARE_YIELD_AND_PHENOLOGY | S4-01 weather feature authority；S4-02 yield候选；S4-03 phenology候选；S4-04 daily-shape候选；S4-05 weather/no-weather ablation；S4-06 cross-zone验证；S4-07 selection/no-win | S4A总量与S4B形状分别出具结论；依赖S2/PIT和S3 |
| V0.5-S5 OPERATIONAL_7D_15D_PEAK_FORECAST | S5-01 7日整窗；S5-02 15日整窗；S5-03 cutoff交互；S5-04 weather snapshot；S5-05 7日total/date/kg；S5-06 15日total/date/kg；S5-07 remaining window | OPERATIONAL_PEAK_POLICY_V1；需S3/S4选择结果，允许无天气稳定基线 |
| V0.5-S6 CROSS_BASE_VALIDATION_PRODUCTIZATION_MCP_RELEASE | S6-01 cross-season；S6-02 cross-base；S6-03 cross-zone；S6-04 A/B/C；S6-05 PIT replay；S6-06 API；S6-07 persistence；S6-08 MCP；S6-09 豆包E2E；S6-10 release资格 | 版本化产品、独立验收包、release review；无自动发版权限 |

S1输入已由用户确认提供，可启动基地归属/面积/坐标校验；本规划修正不执行导入或海拔联网核验。
S2桌面评估可并行，真实基地天气采集须待位置资格、许可及实施授权；阶段完成不自动授权下一阶段。

## 10. 评价设计与模型选择

必须按 BY_BASE / BY_CLIMATE_ZONE / BY_APPLICABILITY_LEVEL / BY_SEASON 分层；
报告可算/排除数量、完整季数和不同origin，不把重叠日窗当独立基地样本。
主表base等权macro，kg加权WAPE另列诊断；分层分母、零分母不可算、缺数/censor状态透明。

| 目标 | 必报指标 |
| --- | --- |
| 总量 | Yield MAE、Yield WAPE、Total kg error |
| 日量 | Daily MAE、Daily WAPE |
| 季节峰值 | Peak date error、Peak kg error |
| 未来7日 | 7d peak date error、7d peak kg error、7d total error |
| 未来15日 | 15d peak date error、15d peak kg error、15d total error |

同一合格集合必须并列 V0_4_NO_WEATHER_BASELINE、V0_5_MULTI_BASE_NO_WEATHER、
V0_5_MULTI_BASE_WEATHER_AWARE；不隐藏失利候选。v0.4算法在04-15域的复算是新实验数据，
不得冒充原v0.4已接受结果；不支持的新基地显示unsupported，不用复制别场输出填满基线。
定义共同可比集与扩展覆盖集分别报告，避免仅删掉困难基地宣称增益。

时间顺序多origin；out-of-base整base留出，cross-zone整zone留出；正常期、特征与模型选择
只用训练数据。一个基地全部covered_farms一起划入同一折，不跨训练/验证拆分成员制造独立样本。
新基地迁移不能见其留出标签。实验样本不足就明确证据不足，不随机拆相邻日。
S1/S2完成后、看最终评分之前，由Coordinator另行批准指标优先级、样本量门槛、数值阈值、
波动/退化容忍及稳定增益规则，不能现在承诺WAPE<10%或峰误差<3天。
天气全部无稳定增益时保留天气数据能力，模型继续采用更稳定baseline，诚实no-win。

## 11. 候选结果 contract（不是 API 变更）

```yaml
base_id: registered_base_identity
canonical_base_name: authorized_identity
covered_farms: membership_metadata_only
climate_zone: versioned_zone
applicability_level: A_or_B_or_C
business_season_end: authorized_cutoff_date
predicted_yield_kg_per_mu: decimal_string
predicted_total_kg: decimal_string
forecast_7d:
  status: COMPUTABLE_FULL_WINDOW_or_NOT_COMPUTABLE_FULL_WINDOW
  start_date: requested_D_plus_1
  end_date: requested_D_plus_7
  total_kg: decimal_string_or_null
  peak_date: date_or_null
  peak_kg: decimal_string_or_null
forecast_15d:
  status: COMPUTABLE_FULL_WINDOW_or_NOT_COMPUTABLE_FULL_WINDOW
  start_date: requested_D_plus_1
  end_date: requested_D_plus_15
  total_kg: decimal_string_or_null
  peak_date: date_or_null
  peak_kg: decimal_string_or_null
season_peak:
  date: date_or_null
  kg: decimal_string_or_null
weather:
  source: source_or_null
  model: weather_model_or_null
  issued_at: timestamp_or_null
  horizon: horizon_or_null
  snapshot_hash: hash_or_null
evidence:
  history_season_count: integer
  applicability_level: A_or_B_or_C
  climate_zone: versioned_zone
  weather_used: boolean
  limitations: list
```

不使用天气时weather字段可空并披露原因，不能伪造snapshot。正式schema等待S3/S4/S5 authority。
复用现有唯一product service及持久化/MCP入口理念，不在transport重新计算峰值。
版本隔离、历史可读和旧golden兼容是S6前提；本轮不做migration/API/tool修改。

## 12. 范围与停止门槛

V0.5 in scope：云南分区、Base Registry、04-15边界、多基地适用性、weather authority及
weather-aware研究、7/15日运营峰值、PIT、API/MCP/豆包产品化。
另行授权才可进入：自动采摘调度、用工排班、车辆/冷库调度、生产排产、其他省份/全球泛化、
卫星遥感、病虫害视觉模型、天气商业采购合同执行。

用户已确认提供基地名称、对应农场、基地经纬度及总种植面积；不再把位置清单未到标为S1 blocker。
后续从已提供资料导入并保留来源/面积口径，海拔等待外部核验。不得要求逐农场面积分摊才能启动。
本 PR 不创建v0.5.0 tag/release，不改变服务器、authority、模型、数据库或MCP。
阶段验收和15项成功条件见 [acceptance-gates.md](acceptance-gates.md)。

```ini
BASE_REGISTRY_INPUT_AVAILABLE=true
S1_IMPLEMENTATION_CAN_START=true
S1_IMPLEMENTATION_STATUS=INPUT_AVAILABLE_NOT_STARTED
ELEVATION_STATUS=PENDING_EXTERNAL_VERIFICATION
WEATHER_SOURCE_AUTHORITY_FROZEN=false
WEATHER_MODEL_SELECTED=false
MODEL_TRAINING_EXECUTED=false
REAL_WEATHER_API_CONNECTED=false
LEGACY_TEST_ACCESSED=false
READY_ELIGIBLE=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_V0_5_PLAN_BASELINE_R1_REVIEW
```
