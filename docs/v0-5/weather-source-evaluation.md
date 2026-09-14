# 天气数据源候选评估框架（非 authority）

审阅日期：2026-09-14。仅查官方公开文档，**未请求真实天气数据、未登录采购、未测试API性能**。
`WEATHER_SOURCE_AUTHORITY_FROZEN=false`，所有来源是CANDIDATE。
表中DOCUMENTED指官网描述，不等于已通过本项目验证；NOT_VERIFIED为后续S2待验证。

## 1. 四类数据不可互换

| 类别 | 业务用途 | 不可替代的边界 |
| --- | --- | --- |
| LONG_TERM_CLIMATOLOGY | 农场/气候带长期同期正常值及anomaly参照 | 正常期、版本、origin可得性需冻结 |
| HISTORICAL_ACTUAL_WEATHER | 历史关系/机理研究与天气误差评价 | 重分析是估计，不是田间实测，也不自动PIT |
| HISTORICAL_FORECAST_ARCHIVE | 按当时发布的完整forecast运行operational回测 | 必须as-issued；禁止事后actual、拼接近时效或后算hindcast冒充 |
| LIVE_FORECAST | 未来完整7日/15日运营窗口 | lead、发布时间、延迟、缺失及版本需与archive可比 |

长气候序列不能提供as-issued未来天气。live与archive来自同机构也不证明历史参数/版本/可得性相同。

## 2. 官方候选事实与初步判断

### C1 ERA5-Land / Copernicus

官方目录描述：全球陆地重分析，1950年至今、小时，分发网格0.1°、原生9km，GRIB，CC-BY。
其高程修正在驱动网格层面，不是对某农场实测海拔的保证。
**候选用途**是长期画像/历史关联，不满足as-issued operational预报门。
变量、最终版/临时版延迟及重处理政策须S2逐项核对。
[官方数据目录](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview)

### C2 ECMWF operational forecast + archive

Open Data官网列示免费子集、CC-BY-4.0及使用条款、GRIB2 0.25°；00/12UTC控制预报可至360小时，
06/18UTC该产品较短。公开滚动窗口只保留最近12次run（约2–3天），**不能据此宣称拥有历史多季档案**。
公开目录列有温度、湿度、降水等参数，但具体变量/时效组合必须锁定。
[Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data)

Operational Archive另有MARS/Archive目录，产品随运行实践变化；历史年份、访问权、价格及
当时实际dissemination证据仍未核实。适合作为as-issued主候选审计，未批准为authority。
[Operational Archive](https://www.ecmwf.int/en/forecasts/datasets/operational-archive)

### C3 Open-Meteo（工程聚合层，非唯一authority）

Historical Forecast文档明确使用每次run的前几小时拼接连续序列；**不能直接代表某origin完整15日预报**。
[Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api)

Single Runs支持指定run，但文档将早期IFS覆盖标为从2024-03-14的49R1 hindcasts，并列10日时效；
多数其他模型从2026-04-02。必须查清是否真实当时发布、对应版本和可得性，不能只因有run时间即PIT PASS。
尤其现有2324窗口及完整15日并未由这份说明解决。
[Single Runs](https://open-meteo.com/en/docs/single-runs-api)

Forecast API支持经纬度、海拔/网格选择及多种变量，最大时效取决于模型，聚合服务声称up to16日
不保证选定模型每一历史run覆盖15个完整当地日。应固定provider/model，避免best-match静默切换。
[Forecast API](https://open-meteo.com/en/docs)

免费API限非商业、无uptime保证；当前页面列600/min、5000/hour、10000/day及300000/month。
商业/历史访问套餐、费用需按实际用量与条款复核，本PR不采购。
[Pricing](https://open-meteo.com/en/pricing)

## 3. 候选矩阵：覆盖、许可和运行版本

下列字段是S2审计记录的最小键；当前未知项不填true。C2必须分别审archive和live，
C3必须记录上游owner与聚合处理链，不能仅用“Open-Meteo”作为模型版本。

| Dimension | C1 ERA5-Land | C2 ECMWF operational/archive | C3 Open-Meteo |
| --- | --- | --- | --- |
| DATA_OWNER | Copernicus/C3S，ECMWF生产 | ECMWF | 聚合服务+各上游机构须逐model列明 |
| DATA_LICENSE | 目录CC-BY，归档许可文本待S2 | open子集CC-BY-4.0；archive访问条款单审 | 数据许可与服务商业条款分开审 |
| HISTORICAL_COVERAGE | 官网1950至今；实际变量版本待核 | 按archive产品/年/周期审，NOT_VERIFIED | 因API/model而异，非全季一律可用 |
| ARCHIVED_FORECAST_AVAILABLE | NOT_APPLICABLE，重分析不是as-issued | 目录存在；本项目访问和PIT未验证 | 有Single Runs产品；PIT/历史覆盖未验证 |
| LIVE_FORECAST_AVAILABLE | NO，此产品不承担live | DOCUMENTED，待运行审核 | DOCUMENTED，需固定model/商业资格 |
| TEMPORAL_RESOLUTION | 小时 | 分cycle/step变化；日聚合不得假装原生小时 | 因model变化，API小时输出不等于小时原生 |
| SPATIAL_RESOLUTION | 0.1°分发/9km原生 | open子集0.25°；archive随版本 | 原生model及重采样分别记录 |
| LAT_LON_QUERY_SUPPORT | 网格选择/区域提取策略待定 | GRIB网格采样，非farm点API | DOCUMENTED坐标请求；实际映射待核 |
| ELEVATION_HANDLING | 网格驱动高程修正，不是farm测量 | 网格orography与farm高差待评 | elevation/降尺度选项需固定并留证 |
| FORECAST_HORIZON | N/A | cycle-dependent；360h不自动等于15个当地日 | model-dependent；早期IFS档案10日不能冒充15日 |
| ISSUE_TIME_TRACEABILITY | 数据版本/发布延迟，不是预报issue | init、release/availability、lead须同时保留 | run字段存在，真实as-issued仍待证 |
| REPRODUCIBILITY | 保存原文件及精确提取/版本 | 固定产品、cycle、网格、成员、step | 固定API/model、run、后处理及返回快照 |
| DATA_VERSIONING | dataset/version/revision/提取规则 | IFS cycle、archive class/stream/type | 上游版本+聚合服务版本/选择规则 |
| HASHABILITY | 原字节hash+规范化payload hash | 原GRIB及转换结果分别hash | 原响应字节及解析结果分别hash |
| RATE_LIMIT | 账户/队列约束NOT_VERIFIED | 官网连接上限；项目配额/吞吐待测 | 公布免费配额；商业套餐单审 |
| COST | 数据/计算/存储/流量成本待核 | open免费不等于archive服务零成本 | 商业服务费用待用量评估，不采购 |
| API_RELIABILITY | NOT_TESTED | NOT_TESTED | NOT_TESTED；免费无SLA |
| CHINA/YUNNAN_COVERAGE | 全球陆地覆盖概念成立；山地代表性未验证 | 全球产品；云南站点/海拔误差未验证 | 选定全球model可覆盖；中国访问与本地误差未验证 |

上述DOCUMENTED事实对应第2节官方引用；提取、hash、版本钉住等为本项目**拟议要求**，不是已实现能力。

## 4. 变量审计矩阵

每一变量均需记录source variable id、单位、height/depth、原生step、累计起点、转换公式版本、
是否实测/模式输出/派生/插值和PIT覆盖。下面是取证方向，不是已下载字段清单。

| Dimension | C1 核验目标 | C2 核验目标 | C3 核验目标 |
| --- | --- | --- | --- |
| PRECIPITATION | 累计降水及日界/单位 | tp累计step、重置与run切换 | precipitation来源/累计与补插政策 |
| TEMPERATURE | 2m温度，派生Tmin/max/mean | 2m与extrema采样差异 | hourly/daily聚合与时区 |
| RELATIVE_HUMIDITY | 是否派生及T/Td同时效 | 2m/pressure level不可混用 | RH的model可用性 |
| DEWPOINT_OR_VPD_INPUT | T/Td同支持集，派生公式待批准 | dewpoint/pressure等所需变量 | VPD直接字段与重算语义对账 |
| SOLAR_RADIATION | 辐射累计J/m²与通量区分 | step间累计转换 | shortwave平均/instant区别 |
| ET0 | 不把实际蒸散当ET0，必要输入待核 | 是否原生/派生、风速/辐射/湿度完整性 | 标注FAO或其他算法及版本，不能只看字段名 |
| SOIL_MOISTURE_IF_AVAILABLE | 层厚/深度/体积单位 | model土层版本 | 各model支持与插值；非第一版必需特征 |

这些变量组合尚未通过项目schema、覆盖或精度资格。若必要变量缺失，不自动替代为0；
降雨事件、GDD/chilling/frost/heat与anomaly特征须在S4-01分别冻结单位、日界、阈值来源。

## 5. PIT 硬门：S2-04验收流程

1. 对各验证origin保留 `forecast_origin_at`、时区、`model_initialization_at`、`issued_at`、
   `available_at`、`valid_time`、lead、model cycle、source revision、retrieved_at、raw hash。
2. 必须 `issued_at <= origin` 且有证据 `available_at <= origin`；init不等于公开时间，
   retrieved_at（今日下载）不等于当年可得时间。不能证明则PIT_NOT_ESTABLISHED。
3. 精确验证D+1..D+7/15所有当地日对应的预报step可得；15日末尾可能超出360h预报，
   此时完整15日weather operational评价不可算，不能拼后发run或用真实天气补完。
4. 检查historical hindcast是否后算、seamless是否混run、reanalysis是否含未来修订。
   含后验数据只可作为明确标注的研究诊断，不能进入严格operational增益证据。
5. 固定模型/特征/处理、预测快照与hash后才评分；对相同origin重复下载检查版本漂移，
   保存原版不覆盖。若档案缺失，该origin排除并报告，不能用未来actual替代。
6. 分别给7日、15日、farm/zone/season可用数量与比例；无可靠archived forecast不得
   声称 weather operational backtest 通过，不阻止诚实交付基础数据平台/no-weather路径。

## 6. 选择框架与下一步

优先桌面评估路径：C1长期画像 + C2真实operational/archive；C3可作为简化访问候选，
只有逐run lineage、权限、变量和时效审计通过才可冻结，不选定唯一authority。
当前四类数据平台整体没有候选通过全部PIT硬门。
如后来引入中国/亚洲站点或其他全球源，应按同一全矩阵审计；不能用行政区/站点名称相近替代
农场代表性证据。本轮不需要为尚未核对的机构伪填价格、档案或可用字段。

位置清单到位后，S2样本审计应覆盖山地高差与候选区域，比较原生网格、点采样与合法海拔处理，
记录时延/可用率/失败语义和许可快照；具体稳定性阈值与采购权限另行批准。
live延迟/缺变量时：天气路径显式不可用；若后续已批准无天气baseline策略可显式降级，
不得静默造天气或改变v0.4无农场fallback合同。

本报告只完成候选评价框架和已公开文档初审，未冻结 WEATHER_SOURCE_AUTHORITY_V1。
