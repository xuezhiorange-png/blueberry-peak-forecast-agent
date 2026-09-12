# 单产季单位面积曲线改进 R2

任务 `NEXT_VERSION_SINGLE_SEASON_AREA_CURVE_MODEL_IMPROVEMENT_R2`。
继续 Draft #611，R1 head `9a09263977cf37f8bc49ec09c102fcefaeeddcbf` 是有效基础。
R1 代码、配置、证据、私有产物保持不变；不替换现用模型，不重开旧 S4/TEST。

## 拟合前冻结

[配置](../../configs/area_yield_experiment_r2.json) 固定唯一新候选 SPLINE_RIDGE：
6 knots、degree 3、alpha 10、include_bias=false、uniform knots、linear extrapolation、
训练折内 StandardScaler、Ridge(solver=svd)、random_state=0。
结点位置只由训练期日历位置最小/最大值决定，不根据目标峰日选结点。
使用 sklearn SplineTransformer，保存实际 BSpline knots/coefficient matrix 与回归/标准化参数，
新进程使用 scipy BSpline 恢复，测试要求与 sklearn 线性边界行为一致。
不增加树模型，不开展网格搜索或任何候选结果驱动的后续试验。

继续使用原 736 亩 AUTHORIZED_CALIBRATION、原 207 行 CSV 及 hash。
这是约定的同一版纳/Dx范围面积分母，不是实测全农场面积。
仅用日历位置预测 kg/mu/day × 输入面积；不使用滚动实际采摘量或目标总量/首采/峰日。
沿用原 181 观察日、26 授权零日，不读取原始新产季 XLS 或旧 sealed TEST。

三个开发 cutoff：2024-12-01 / 2025-01-01 / 2025-02-01。
每个 cutoff 含当日及以前标签拟合，预测下一日起 14、28、42 天，共 9 个窗口，
全止于 2025-03-15。不同窗口有重叠，不当成独立产季。
每个 origin 分别拟合均值、R1 原配置 Ridge、Spline 三个模型一次，供三种窗口共享。
三个模型在完全相同日行上比较，不排除预测不好的行。

选择对每个模型取 9 窗口等权宏平均，按下列顺序字典序比较：
七日累计峰窗口偏移、单日峰日期差、WAPE、MAE、单日峰量误差。
候选必须同时满足宏平均 WAPE、MAE、窗口总量绝对误差不高于 R1 Ridge；否则不进入选择。
完全平局优先 Ridge、均值、Spline，避免无收益复杂化。这不是新增绝对业务验收阈值。
最终比较不是再次选型：选择文件先冻结，之后仅一次比较原 R1 2025-03-16..05-09 窗口，
它是已看过的 regression benchmark，不是 blind holdout。两个基线重算必须逐字段复现 R1。
只有已选候选在该已知窗口同时改善两项峰时误差、且 WAPE/MAE/总量误差不恶化，
才报告 SINGLE_SEASON_BACKTEST_IMPROVED；否则如实报告基线保留或无实质改善。
14 天不是硬阈值。本次结果不能证明再换任意模型都无效。

## 全历史模型与输出边界

冻结比较完成后，选中的模型类型在全部 207 行上重新拟合一次，保存 FINAL_MODEL_R2。
这一步和 full_history_fit_predictions.csv 都不是独立评价，不用其拟合成绩冒充回测。
主输出限定到已授权账本覆盖的 month/day 窗口 10-15..05-09，未来示例为
2026-10-15..2027-05-09，不在其外生成无依据的全年正产量，也不把未预测日写成零。
模型输出标记季节位置 SUPPORTED/EXTRAPOLATED；支持区间只表示训练覆盖，不表示准确率保证。
面积 368/736/1104 的比例测试分别使用 0.0000015 kg 和 0.00000125 kg 的逐行舍入上界。
AREA_SCALING_POLICY=LINEAR_BUSINESS_ASSUMPTION，AREA_SCALING_VALIDATED=false。
到厂量=采摘量；不附加商品率、实现率或天气折减。

## 产物和执行入口

`python -m scripts.run_area_curve_r2` 分别执行 rolling / benchmark / refit / forecast。
私有输出目录与 R1 分开，逐阶段排他创建；失败不静默覆盖/重跑。
旧 R1 文件在执行前后做只读 SHA256 快照核对。
代码只新增 R2 模块，重用 R1 的两个基线和 canonical 日峰/七日累计峰实现。
逐点 CSV、模型权重和全历史拟合行留在用户本地受控目录，不上传公开仓库。
读表技能用于来源/单位/缺数核对，实际 CSV 由本轮要求的 Python 实验程序生成。

实际运行结果将在下方追加，不预先填写改善或通过。
