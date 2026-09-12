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

## 实际结果：保留 Ridge，不宣称峰时改善

执行代码 commit `989a6bc00a420c703298e284b3ad6b828f76b11d` 在真实拟合前冻结。
共 9 个开发窗口、9 次开发拟合、3 次已知 benchmark 拟合、1 次全历史重拟合。
模型-窗口评价 30 次；均为本轮隔离实验，不使用旧 S4 台账。

| 开发九窗口等权宏平均 | 均值 | 固定 R1 Ridge | Spline |
|---|---:|---:|---:|
| 七日峰窗偏移/天 |14.222222|12.888889|9.888889|
| 峰日误差/天 |18.111111|14.777778|13.777778|
| WAPE |0.795067|0.724534|0.749385|
| MAE kg/日 |2678.327466|2318.801526|2593.023862|
| 窗口总量绝对误差 kg |68495.668878|57431.293041|64991.558453|

Spline 未通过预先冻结的数量误差非恶化约束；只有 Ridge 合格，先冻结选择再读 benchmark 标签。

| 已知 R1 final 窗口 | 均值 | 固定 R1 Ridge | Spline |
|---|---:|---:|---:|
| WAPE |0.740619|0.427146|0.521958|
| MAE kg/日 |7573.954420|4368.218298|5337.816579|
| 峰日误差/天 |43|32|43|
| 七日峰窗偏移/天 |41|33|41|

RESULT=BASELINE_REMAINS_BEST。两个旧基线逐字段复现 R1；未针对 final 再调参。
这只表明本次唯一冻结 Spline 未改善，不证明所有模型都无法改善。

全 207 行重拟合选中的 Ridge，模型文件 SHA256
`40c659b56406a791a2505c3817534c85d7543f77c70b9d776b988370b8919d9b`。
新进程 PID 53029 加载不 fit，未来例子 2026-10-15..2027-05-09，每档面积 207 行。
736亩总量 968113.233005kg；峰日 2027-04-28，10488.041609kg；
七日累计峰 2027-04-25..05-01，73380.619109kg。368/736/1104亩比例检查 PASS。
训练覆盖外行数 0；训练覆盖不代表多产季泛化或面积外推精度已验证。
全历史拟合后的峰日与历史接近不是独立回测成绩；总量也不是硬编码旧校准总量。

私有持久目录：`/Users/charles/Documents/blueberry-area-yield-artifacts/area-curve-r2`。
其中逐窗口 CSV/metrics、模型、训练清单、预测和 artifact_manifest.json 均已产生；
[公开汇总与文件 hashes](evidence/area-yield-single-season-model-r2.json) 不包含逐条业务数据或模型权重。
旧 R1 文件 hashes 执行后核对未变。

运行命令（依次执行，各阶段排他写入新目录，不重跑既有目录）：

```bash
.venv/bin/python -m scripts.run_area_curve_r2 rolling --r1 /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1 --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-curve-r2
.venv/bin/python -m scripts.run_area_curve_r2 benchmark --r1 /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1 --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-curve-r2
.venv/bin/python -m scripts.run_area_curve_r2 refit --r1 /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1 --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-curve-r2
.venv/bin/python -m scripts.run_area_curve_r2 forecast --r1 /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1 --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-curve-r2
```

本地 area-yield/planning/maturity/core-forecast 非 PostgreSQL 回归 383 passed。
Ruff、format、Mypy 通过；真实精度评价与软件测试分别报告。
推送后 exact-head required CI 仍需独立验证，不以本地测试代替 full-suite-canary。
