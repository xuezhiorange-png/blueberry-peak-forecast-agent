# V0.19 S1：十项指标与受控研究协议 R1

## 1. 比较对象、时间与登记

协议只在字面 SYNTHETIC 输入上验证算术，不评分历史或当前业务数据。
本文件是未来执行的预注册约束，不是实验已执行或精度已达标的证明。

每个比较单元 c 的键为：comparison_family、模型/subpolicy/fit hash、组织和实体、
面积口径、产季、timezone-aware origin、发行时间、窗口定义及完整日期集合、
forecast source/profile/input hash、物理量/单位、label_authority_hash和成熟状态。
同一配对的模型/fit身份各自保留，其他公共键、来源、训练与评价范围必须一致。
不可用字段记录 NOT_VERIFIED，不能推断。原始run_id及结果Hash同时保留。
kg是数量，mu是面积，kg/day是日率；采收、可售到果/到厂代理分层，不自动转换。
相邻/重叠 origins 不是独立生物样本。预测日期 Dk=origin本地日+k，不按 UTC日期截断。
来源 available_at、ingested_at≤cutoff 及签发 seal 才能支持 PIT；单纯业务日期不足。

冻结输入候选集合 C0 在看任何评价结果前产生 rowset/hash，固定实体、season、origin、
lead、日期、label/completeness及排除理由。模型故障、缺预测不允许缩小 C0 隐藏；
按每项指标记录共同可计算集合 Cm、候选数、有效数、不可计算数和原因。
主配对比较使用双方相同 Cm，并报告各方在 C0 的缺失。覆盖不同不得宣称总体胜出；
可计算子集只能标记 CONDITIONAL_ON_COMMON_COMPUTABLE_COHORT。
未授权行从不读取。数据权限不足停止，而不是当作零标签。

## 2. 窗口、峰值和缺失规则

FULL_SEASON 使用事前批准的完整季节日历及单一发行预测，不拼接 origins。
完整季节总量不可从 H15 外推或用 remaining-window 代替。
H7_PREFIX 是同一 origin 的 D1..D7；H15_LOCAL 是 D1..D15。
H15 内 rolling7起点只有D1..D9；window_end=start+6天。
任意缺日、重复日、不连续、非有限数或负量使对应完整窗口指标不可计算；不补零、
不插值标签、不悄悄缩成短窗口。已权威确认的真实零日可以使用。
预测或actual的峰均从同一完整曲线各自求最大值，并列取最早日/起日。
峰量误差比较各自最大量，不是在actual峰日抽取预测量。
全零actual的峰量仍合法为零，但日期/rolling起日为
NOT_COMPUTABLE(NO_POSITIVE_ACTUAL_PEAK)，防止把最早并列日期当成命中。
actual有正峰而预测全零时预测最早并列日期仍计入日期误差，不能排除模型失败。
历史S5沿用其旧全零处理，本协议不得回填旧报告或直接声称新旧均值可比。

## 3. 十项数学定义

记 a(c,d)、p(c,d) 为同一合法 kg 日量，e=|p−a|；
T(c)=Σd a、P(c)=Σd p；t_a/t_p 为日峰日期，q_a/q_p为日峰量；
s_a/s_p为完整rolling7最大窗口起日，r_a/r_p为该窗口累计kg。
所有除法使用 Decimal precision=50，不经过float或显示值中间舍入。
ratio不是百分比；输出展示可转百分比，但保存原ratio及分子分母。

| 指标 | 公式与分母 | 单位、权重、不可计算 |
|---|---|---|
| SEASON_TOTAL_WAPE | Σc |P(c)−T(c)| / Σc T(c) | ratio；只FULL_SEASON，完整单次发行季节单元；总actual=0则NOT_COMPUTABLE，不加epsilon |
| DAILY_WAPE | Σ(c,d) e(c,d) / Σ(c,d) a(c,d) | ratio；micro pooled，H7/H15/FULL_SEASON分别报，不是每日百分误差平均；分母0不可计算 |
| DAILY_MAE | Σ(c,d) e(c,d) / N_daily_rows | kg/target-row；每个origin-target实例等权，分母0不可计算；零actual照常保留 |
| SINGLE_DAY_PEAK_DATE_MAE | Σc |t_p(c)−t_a(c)| / N_positive_actual_complete_windows | calendar days；每完整窗口等权，全零actual单列不可计算 |
| SINGLE_DAY_PEAK_QUANTITY_MAE | Σc |q_p(c)−q_a(c)| / N_complete_windows | kg/window；各自峰值相减，零actual保留；分母0不可计算 |
| ROLLING_7DAY_PEAK_START_MAE | Σc |s_p(c)−s_a(c)| / N_positive_actual_complete_windows | calendar days；每完整窗口等权，无完整7日或全零actual不可计算 |
| ROLLING_7DAY_PEAK_QUANTITY_MAE | Σc |r_p(c)−r_a(c)| / N_complete_windows | kg/7day-window；不是kg/day；零actual保留，分母0不可计算 |
| BASE_BREADTH | 对每基地 b，Δb=Σe_candidate−Σe_baseline；分别count(Δ<0/=0/>0)，并报 n_base、Σactual_improved/Σactual_all | count和ratio分开；同共同样本；没有可比基地则NOT_COMPUTABLE，零质量时量占比null，不丢零量基地；不以行数冒充基地数 |
| SAMPLE_COVERAGE | N_computable_metric_common / N_candidate_metric | ratio；逐指标逐窗口逐split，另报n_base和target-row覆盖，不能把不同分母汇成一个“覆盖率”；空候选不可计算 |
| NOT_COMPUTABLE_COUNT | N_candidate_metric − N_computable_metric_common | count；每个候选指标单元仅计一次，优先原因按下一段顺序；可另列多因标签但不能重复累计 |

不可计算优先原因：UNVERIFIED_AUTHORITY、PHYSICAL_BASIS_MISMATCH、
IDENTITY_OR_SOURCE_HASH_MISMATCH、INVALID_VALUE_OR_DUPLICATE_DATE、
INCOMPLETE_CALENDAR、NO_COMPLETE_7DAY_WINDOW、NO_POSITIVE_ACTUAL_PEAK、ZERO_DENOMINATOR。
无候选记录 EMPTY_COHORT，数值null、count=0；不发布0误差。
Cm按指标分别确定，例如同一个零actual窗口仍进入数量MAE，但不进入日期MAE。
WAPE的分母检查在整个固定共同cohort池上执行，不逐行排除零actual。
若池中存在正量，合法零actual行的误差仍进分子；若整个池分母为零，WAPE值null，
该WAPE的全部候选单元标为不可计算。数据可用覆盖率可另报，但不能冒充指标可计算率。

重复origin-target实例保留，禁止按target_date去重；每origin窗口等权MAE和逐行micro WAPE
分开，不以大基地的更多 origins 冒充跨基地稳健性。FULL_SEASON只选择事前固定的
单一发行点，不能后验挑最好origin。split不混汇；跨实体汇总应先逐日聚合再求峰，
不可相加子实体峰值。聚合需要合法成员完整性及明确的统一物理口径，否则不可计算。

补充诊断事前固定为：signed bias、早/晚/同日计数、逐lead误差、逐基地paired delta，
以及按H15绝对误差降低额排序移除完整top1/top2基地后重算（并列按基地ID）。
不用于选参；样本相关性未建模前不声称显著性，不进行逐行独立bootstrap。
没有新准确率达标线、日期容忍带、自动winner或生产晋级阈值；均待未来Owner决策。

## 4. S2候选与S3实验预注册边界

主要基线：OPERATIONAL_PEAK / AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1。
其他模型只能按自己的来源和可比合同分面报告，不跨family直接排研究名次。

S2尚未授权，本阶段不实现候选。后续最多一个候选，具体方法在S2授权后、打开任何
评价标签/结果之前写入不可变 method/config/source seal。选择只能基于结构和合成
不变量，不得看历史误差选方法、扫描参数或固定平移峰日。参数搜索关闭；若方法需要
数据拟合或可调参数，必须另获明确数据/实验及选参合同授权，不能从S1自动推导。

冻结质量守恒作用域为：事前声明完整support内，每个以产季起点锚定的bin。
基线bin值是**日**kg/mu，不是七日总量；bin目标质量是该bin在support内所有基线
日kg之和。完整bin通常7日，首尾短bin按其实际日数，不补到7日或读取未来标签。
候选每bin日量非负、日期连续，其和必须等于基线相同bin质量；全support守恒由此继承。
禁止改变面积尺度或用本来整季不完整的输入编造season total。
边界不外推、无support外质量；查询H7/H15只取已声明support的子集，不重新归一化。
候选日量输出六位kg；使用整数微kg守恒，量化余数按小数余数降序、并列最早日期
分配单个微kg，零质量bin全零。此为未来结构约束，不表示当前候选已运行。
只守恒总量不保证峰时改善；结构测试成功不能当作精度证据。

未来S3入口必须同时具备：S1/S2正式完成、Owner独立实施授权、数据及评分授权、
合法profile/area/labels/schema/available_at/physical-basis和共同cohort seal。
缺任一来源返回BLOCKED；不自动读取历史路径，更不能打开当前2026–2027 actual。
如历史只有到厂subtotal代理，报告该代理而非真实完整采收；如仅H15，整季指标保持
NOT_COMPUTABLE。实验仅验证来源支持的窗口，不为凑十项指标伪造输入。

顺序：先冻结comparison与方法→仅在批准fit范围生成模型/预处理→固定共同输入生成
baseline/candidate预测→seal预测及配置源码→独立评分路径确认seal后打开成熟标签→
一次评分并保留全部结果、失败和退化。实际模型artifact不得覆盖原冻结模型。
2025–2026标记EXPOSED_HISTORICAL_BENCHMARK而非blind OOT；无真实时点证明时
STRICT_PIT=false。禁止随机相邻日期切分；未来跨季、滚动时点、基地/工厂留出须有
对应合法样本及映射，缺映射不能编造。模型/物理口径不同则先停比较。

评价分别报告十项指标、分子分母、可计算/不可计算原因、共同样本hash、完整季节与
H15局部窗口、H7前缀；每天数量和两个峰时指标并列，不只凭WAPE选型。
未来若仅日误差改善而峰时退化，结论是MIXED，不把它称为峰时提高。
允许NO_STABLE_GAIN；数据不足是BLOCKED/INCONCLUSIVE，未执行不是研究完成。
此处不新增支持门槛，最终业务容忍带与推广决策仍需单独授权。

## 5. 离线测试与停止

新增单一测试文件以纯合成日期、Decimal字面量验证十指标的基本语义、最早并列、
完整15日九个rolling窗口、日期移位总量抵消但日误差不抵消、全零actual、微小量、
缺日/重复/乱序/非法值、coverage及breadth。参考oracle仅在测试模块，不能读取业务文件。
来源hash、canonical JSON、五模型矩阵、历史负面结果和治理约束同测。
不是生产评分器、不是模型训练或真实历史重评分；不扩建预测框架。

本轮只新增两份协议、一份机器合同、一份离线测试。S0文件、历史模型、运行服务、
依赖、CI和数据库不变。本地验证及最终exact-head CI分别在PR/回执记录，
Codex自检不替代独立复审。S1_FORMAL_COMPLETE=false；PRODUCTION_READY=false。
完成Draft PR和当前HEAD CI后STOP，不自动进入S2或发布。
