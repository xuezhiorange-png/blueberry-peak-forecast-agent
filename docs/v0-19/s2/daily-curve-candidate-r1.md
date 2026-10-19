# V0.19 S2：每日曲线时间分辨率候选 R1

TASK_ID=V0_19_S2_DAILY_CURVE_TEMPORAL_RESOLUTION_CANDIDATE_R1

## 身份、唯一方法与授权

起点为 S1 合并 main `a95d5596e7c25d485414fd540b17ca13920724a9`。
Owner 授权独立本地开发；提交、Push、Draft PR 必须等待 main push CI
[39251108327](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/39251108327)
最终 SUCCESS。实际门禁与 exact-head CI 在 PR 回执绑定，不预填未来结果。

唯一候选：`BIN_CENTER_LINEAR_PER_BIN_MASS_V1`，即
BIN_CENTER_LINEAR_INTERPOLATION + PER_BIN_MASS_CONSERVING_NORMALIZATION。
基线仍是 `AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`。没有选第二种方法、训练、
参数扫描、固定峰日平移或标签访问。配置在任何真实评价结果读取之前按 Owner
指定的结构方法冻结于 `daily-curve-method-config-r1.json`；合成曲线不是精度评价。

研究源码位于 `backend/research/v019_daily_curve.py`，无生产注册、文件/网络/数据库
读取、HTTP/MCP 依赖，也不导入 `backend/app`。既有 Operational Peak、数学、
Hash/ForecastIdentity、S0/S1 文档证据、前端、依赖、CI 和数据库均不修改。

## 输入与日期合同

纯函数 `generate_candidate(CurveInput) -> CandidateResult`。
输入包含原 season_start、显式 support_start/support_end、连续有序的
`tuple[DailyKg(date, Decimal)]`、baseline_policy、baseline_source_sha256 和时区。
日期必须已经是 Asia/Shanghai 本地业务 date；拒绝 datetime，不自行把 UTC 日期
截断/转换。source hash 必须是完整小写 SHA256，但格式正确不等于来源已获授权；
未来 S3 必须另验 profile、面积、模型、完整身份、物理量、发行及数据可用时点。

不补缺日，不合并重复日，不排序纠错，不改 season_start，不生成 support 外日期。
数量必须是有限非负 Decimal，并精确落在整数微 kg；超出六位有效小数拒绝，
不静默舍入改变输入质量。不同小数显示尺度和负零 canonical 化为六位非负 kg。
每个原始分箱内部基线必须平坦，否则不是本候选所声明的冻结基线，直接拒绝。
support 是事先声明的完整计算支持域，可以是合法的部分产季，但不能冒充完整产季。

## 数学定义与边界

令日坐标 t=(date-season_start).days，原 bin b=floor(t/7)，保持原编号。
I_b 为该 bin 与声明 support 的交集，n_b=|I_b|，基线日微 kg 为 m_t。
目标质量 M_b=Σ(t∈I_b)m_t；基线平坦，所以日均锚值 a_b=M_b/n_b=m_t。
中心 c_b=(min I_b + max I_b)/2。完整 bin 中心是 season_start+7b+3；
首尾短 bin 中心是其实际有效日期中点，不补足七天，也不移动原产季分箱。

相邻中心之间 r_t=a_b+(a_next-a_b)(t-c_b)/(c_next-c_b)。
support 内、首中心之前/末中心之后使用最近端点锚值；这不是线性外推，且绝不
输出 support 外质量。单 bin 只有一个常量锚。零质量 bin 最终全部为零。

正质量 bin：q_t=M_b*r_t/Σ(t∈I_b)r_t，为理想微 kg。
先取 floor(q_t)，再将 R=M_b-Σfloor(q_t) 个微 kg 分给小数余数最大的 R 日；
并列取最早日期。每日至多补一个微 kg。分母必须正，余数必须满足 0≤R<n_b；
否则失败，不改用其他算法或兜底预测。

Decimal 输入通过精确整数比转成整数微 kg，中心采用双倍整数日期，插值权重保存
为整数分子/分母，各 bin 用最小公倍数消去分母；归一化使用整数 divmod 比较
精确余数。因此无 float、无有限精度除法导致的伪并列，也不受调用方 Decimal
context 影响。这是相同插值公式的精确实现，不是第二候选或参数变体。
最终 Decimal 日 kg 恰为六位；逐 bin 和全 support 在整数微 kg 下严格守恒。

逐 bin 缩放和零量约束可能保留边界跳变，不承诺全局单调、C1 光滑或处处非平坦。
常量/全零/单 bin 可保持原样；升降合成例的同 bin 内具有真实逐日变化。
结构变化既可能改变峰日，也可能改变峰量，不代表时间或数量精度改善。

## 输出、查询与可追溯身份

输出是不可变日期/Decimal 序列、逐 bin 的基线与候选整数质量证明、
input_sha256、config_sha256、canonical_bytes 和 result_sha256。
canonical UTF-8 JSON：排序键、两空格、禁止 NaN、末尾换行；日 kg 六位字符串，
包括原始输入、完整方法配置、候选日值和守恒证明，不包含时钟或随机运行 ID。
Hash 绑定数据/方法，不冒充生产 source_result_hash、projection_hash 或业务 authority。

`select_window(result, origin, horizon=7|15)` 仅切出本地 D1..D7/D15 原有日值。
越界拒绝，不重新计算锚点或按 H7/H15 重新归一化。计算 support 变更是不同输入，
不能用新的短 support 结果冒充原结果的子查询。原 baseline tuple 不修改。

合成结构归档独立记录输入、输出、bin 质量与确定性 Hash。方法配置、实验输入和
结果身份分开。机器证据中的历史源码使用固定 Git commit 原始字节；冻结文档仍
检查当前原字节。候选源码封存在交付 Git 提交，独立于以后可合法修改的测试源码；
不将历史测试源码的 SHA256 绑定到未来工作树。最终 HEAD/CI 由 PR 回执绑定。

## 合成验证与非目标

覆盖常量、上升、下降、中间零、全零、首尾短 bin、剧烈交替、微小量、真正的
部分并列余数、缺日/重复/非法值、重复运行、Decimal context、独立 Fraction
数学 oracle、每 bin/总量守恒、H7/H15 切片和 baseline 不变。没有任何真实标签。
Fraction 仅为独立测试 oracle；候选运行使用 Decimal 与整数，不使用 float。
初始测试在候选模块尚未创建时因 import 缺失 RED；其后运行结果在机器证据/PR
区分记录。S0/S1 与 V0.18 历史合同、Ruff、Format、Mypy 和完整 CI 另行验证。

本阶段不计算新的真实 WAPE 或峰时 MAE，不做 A/B、历史重评分、拟合、调参、
校准或模型晋级，不读取私有标签、当前 2026–2027 actual、模型 artifact 或业务库。
STRICT_PIT=false，PROSPECTIVE_ACCURACY_VALIDATED=false，PRODUCTION_READY=false。

## S3 前提与停止

S3 需要 S1/S2 正式完成、Owner 单独实施及数据/评分授权、合法 profile/area/label/
schema/available_at/physical-basis、共同 cohort seal、方法配置与预测 seal 先于开标签。
历史 exposed benchmark 不是 blind OOT；无完整季节则整季指标不可计算。
数量、峰时、覆盖、退化均按 S1 十指标协议报告；允许 MIXED/NO_STABLE_GAIN。
缺少数据权威即 BLOCKED，不从本次纯合成成功推断精度或生产准入。

S2_FORMAL_COMPLETE=false；S3/S4_IMPLEMENTATION_AUTHORIZED=false。
只交付独立 Draft PR 与 exact-head CI，等待独立审核；不 Ready/Merge/Release/Deploy。
