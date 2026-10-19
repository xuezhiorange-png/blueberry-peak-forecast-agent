# V0.19 S1：模型基线与历史证据对照 R1

TASK_ID=V0_19_S1_MODEL_BASELINE_AND_PEAK_ERROR_PROTOCOL_R1

## 1. 身份、权限和来源

本阶段只交付只读源码审查、公共冻结证据对照、数学协议与 SYNTHETIC 离线测试。
Owner 已授权 S1 及门禁前并行本地准备；提交、Push、Draft PR 必须等待
S0_POSTMERGE_CI=SUCCESS。S0 #734 合并为
`47f774bfa823af9849cda7d56668ab81c73548c5`，对应 main push CI 为
[39215132754](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/39215132754)。
最终门禁结果、提交 HEAD 和本轮 CI 在 GitHub PR/执行回执绑定，不预填未来成功。

审查基线就是上述 merge SHA。机器合同列出逐文件 SHA256：历史源码取该固定提交
Git 原始字节；冻结文档/证据仍核对工作树原始字节。没有打开文档引用的私有数据、
特征、标签、系数或模型 artifact，没有访问业务数据库、训练、拟合或重新评分。
旧结论是引用，不是 V0.19 新实验。原 S0 授权快照保持原样；本阶段权限另行记录。

## 2. 五类模型，不是一条可直接排名的赛道

| 模型家族 | 实际代码与计算身份 | 输入/拟合状态与输出 | 可比性缺口与限制 |
|---|---|---|---|
| AREA_FORECAST_PRODUCT | `area_yield/base_product.py::forecast_base_area`、`base_product_authority.py`：AREA_FORECAST_PRODUCT_V1，BASE_AWARE_BASELINE_R1 + AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE。另有 `product.py::forecast_by_area` 经 `run_application.py` 持久化的 AREA_DRIVEN_B1 路径，必须登记 subpolicy，不能混为同一结果 | 前一年明确授权亩产×目标面积为总量；BASE 产品在参考面积上计算冻结十特征时间 Ridge，裁剪非负后归一化；B1 使用冻结四系数双年谐波形状。服务只推理，不在请求时训练。BASE 默认 July 1–April 15，B1 默认 July–June；六位 kg、十五位公开 share 不能反向替代未量化内部值 | 历史量是 ACCEPTED_MAPPED_FARM_SUBTOTAL_NOT_COMPLETE_FULL_SEASON_TOTAL，不自动成为完整真实采收总量。BASE 请求短窗口会重归一化；B1 显式窗口是新的业务季节定义。必须记录窗口及 policy，不能与 Operational Peak 的子查询直接比峰量；未知 origin/issued_at/available_at 不猜测 |
| OPERATIONAL_PEAK | `forecast_quality/operational_peak.py::forecast_operational_peak`、`_daily_row`、`summarize_window`；OPERATIONAL_PEAK_POLICY_V1 / AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1 | 已登记基地面积×产季起点锚定的七日分箱日亩产；缺 bin 取最近训练 bin、等距较早；六位 ROUND_HALF_EVEN kg。D1–D15、H7/H15 前缀和 remaining-business-window 各有完整性状态；不拟合、不重建整季总量 | 日形状在 bin 内平坦，最早并列可能机械落在边界。remaining-window 不等于完整产季。H7 是 D1..D7，不是 rolling7 最大值。运行实例 profile/area/hash/发行时点仍须未来合法授权逐项验证。无本轮精度证据 |
| V0_15_BASE10_RIDGE | `area_yield/v015_base10_benchmark.py`、`weather_aware_backtest.py::fit_ridge_artifact`；RIDGE_LEAST_SQUARES，alpha=10，十特征 | 历史训练阶段拟合 population-standardization，零标准差置1、截距不惩罚、numpy.linalg.solve；非负输出、12dp。滚动 origin 的 D1–D15，TRAIN/VALIDATION/EXPOSED_OOT 独立；服务请求路径不等于该研究拟合路径 | S3 origins 4125/6028/9867；后续 S5 common rowset 不同，不能拿 S3 Ridge 和 S5 M1 直接排名。已暴露 OOT 非盲测。列清单、artifact/fit hash 未获得合法运行数据前为 NOT_VERIFIED，不新生成系数 |
| V0_15_HARVEST_STATE_RIDGE | `area_yield/v015_harvest_incremental.py::target_rows/fit_predict`、`v015_harvest_state.py`；V0_15_S5_M1_RIDGE | 同一固定 Ridge，Base10 + past_7d/14d/28d/season_to_date_harvest_kg 四列。17:00 Asia/Shanghai origin，只取 business_date 小于 origin 当天；历史 refit 后封存预测再开标签；本轮不重跑 | S5 M0/M1 common origins 3705/5412/8775。日期滞后不证明当时系统可得；STRICT_PIT=false。M1 数量改善不证明峰时改善，更不等于 Operational Peak 精度 |
| CORE_FORECAST | `core_forecast/service.py::compose_complete_daily_marketable_curve`、`metrics.py::compute_core_forecast_metrics`、`schemas.py`；Task8/Task9 组合权威 | Task8 自然成熟供给 + Task9 成熟库存、采摘能力状态 + retention policy；farm/subfarm/variety 和 destination_factory_id；三条既有 P50/P80/P90 命名输入，六位 Decimal/整数微 kg、row/curve/metrics hash；不在该组合模块拟合预测器 | 不是独立单一拟合算法，不与 M1/Operational Peak 强制同义。effective_harvest_capacity 是采收能力，不是工厂吞吐；effective_marketable_quantity 是其指定物理口径。不可推断 Operational Peak 基地→工厂映射。字段命名不证明分位数已校准 |

审查包含计算调用链及边界，而非只看模块名。BASE 产品与 B1 子路径特别分开，
避免把一个默认日历或归一化规则赋给另一个。所有 family 的训练截止日、输入版本、
profile/fit/hash、组织/实体、面积单位、物理量、origin/时区、签发与可用时点均是未来
run 级必填登记。静态源码只能证明计算规则，不能证明某条私有 run 的来源或精度。

## 3. 已冻结历史误差证据矩阵（不重新计算）

| 来源 | 样本和指标范围 | 已知结果 | 不能推出 |
|---|---|---|---|
| V0.8 S9 | full39 与 common30 分开；冻结 2025–2026 benchmark | full39 season WAPE：baseline 0.3429935582924604063039679242、V0.8 0.3925893218351959883557945280；shape-only daily 0.5851588537121282064362044141、scale-only 0.3925893218351959883557945264、combined 0.6292132974633544144280801218。共享日 share hash；shape-only 日峰日期 MAE约30.5128天、rolling7起日约23.1538天 | 非线性绝对误差反事实不能相加为贡献百分比；common30 不能并入 full39；旧 StageA/B 诊断不成为当前五类模型总排名 |
| V0.13 closeout | 两 fold 合计3964个完整 H15 origins，1043+2921；past-observed weather | Weather 数量 SUPPORTED；简单7°C GDD与联合互补性 NOT_SUPPORTED。Weather 日峰日期 MAE delta +0.073158425832492431886982846天、rolling7 +0.096871846619576185671039354天，峰时 NOT_SUPPORTED。Oracle mixed | 不代表天气无价值，也不等于 as-issued天气改善当前峰时。Oracle future realized不是可用的发行时天气 |
| V0.15 S3 | 三 split origins 4125/6028/9867；target rows61875/90420/148005；十特征三模型研究 | Validation H15 WAPE：Ridge75.5212%、CB69.1307%、LGB70.2513%；exposed OOT：62.9438%/64.1767%/65.7429%，NO_CLEAR_LEADER | 树模型稳定优于 Ridge；与不同 S5 rowset 直接 A/B；这些显示百分比不是机器 ratio 的新精度 |
| V0.15 S5 / V0.18质量路线图 | common origins3705/5412/8775；rows55575/81180/131625；M0与M1固定 Ridge | M1 exposed H7 daily WAPE=0.42492240428114891228797259913152412125067904816858；H15=0.45061746284274714676741860562477726865031957501063；短期数量 SUPPORTED。OOT rolling7起日 MAE 3.4735042735042735042735042735042735042735042735043→3.5376638176638176638176638176638176638176638176638天，退化 +0.0641595441595441595441595441595441595441595441595 | 用数量改善掩盖峰时退化；把历史M1 WAPE复制为运行Operational Peak精度；本轮新增重评分 |
| V0.18路线图与工程交付 | 已有权威保存预测和 HTTP/MCP/Dashboard；质量路线图引用旧 M1/S2 聚合 | 工程一致性不证明精度。历史PI80/90 H7 coverage约0.53893/0.74530、H15约0.50575/0.71092，低于名义目标；保留不可计算数量及 retrospective 限制 | Point已证明P50、planning bounds已校准P80/90、归因是农业因果、实际ROI成立 |

完整公开来源 hash 见 S1 JSON。没有读取私有 manifest 成员来复算上述数字；
不声称重新验证 private prediction/label bytes 或原实验环境。历史指标定义保持原样，
即使新协议对全零峰时采用更保守的 NOT_COMPUTABLE，也不能重写历史均值。

## 4. 正式基线与下一步决策

S2 的唯一主要结构对照基线选定为冻结 Operational Peak 七日分箱规则，
因为本版本首先研究其时间分辨率；不是因为五类模型的历史排行榜。
候选及基线必须用相同合法 profile、面积、calendar、origin 和物理量，比较只在
同一个预注册 comparison family 内进行。其他四类作为身份/机制/历史证据对照，
不得凭不同来源历史分数称赢家。未来跨 family 的共同评价须另行批准比较合同。

S1 不选择具体候选算法、不实现 S2、不选择或调试拟合参数；
配套指标/实验协议冻结选择规则、质量守恒作用域及停止条件。
任何 artifact、label 或时点证据不足均 BLOCKED，不得以源码规则填补来源缺失。

STRICT_PIT=false；PROSPECTIVE_ACCURACY_VALIDATED=false。
S1_FORMAL_COMPLETE=false；VERSION_RESEARCH_COMPLETE=false。
不晋级模型、不访问当前季实际采收、不启动 S2–S4、不 Ready/Merge/Tag/Release/Deploy。
