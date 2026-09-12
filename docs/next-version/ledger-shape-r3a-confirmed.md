# R3A 用户确认后的真实跨季 shape 训练

## 结果与边界

RESULT=CROSS_SEASON_SHAPE_MODEL_TRAINED。真实训练2个固定模型，评价3个严格合格配对。
SELECTED_SHAPE_MODEL=RIDGE_TWO_ANNUAL_HARMONICS；经验shape不满足冻结的替换条件。
训练/预测/评价工程已完成，不代表精度达标，不替换现用模型，不训练总亩产。
原R3A等待确认记录保留为历史，本文件是确认后的当前结果。

用户确认绑定 [配置](../../configs/shape_r3a_confirmed.json) 中的两个原附件SHA256。
仅SOURCE_ACTIVE_DAY且某农场缺行可记0（SOURCE_ACTIVE_LEDGER_ZERO），
GLOBAL_NO_RECORD_DAY仍UNKNOWN。到厂量=采摘量，禁止二次折减。
继续复用R3 hash绑定日聚合与清单；不重复原始附件身份审计，不拼接仓库旧24–25。

## 资格重判

35个精确同名配对中，23–24严格合格27个、24–25严格合格5个，交集3个：
保山华兴农场、保山杨柳农场、建水南庄基地。其余32个配对为DIAGNOSTIC_ONLY。
按14天文件边界、正记录总量、active span无global unknown及精确身份规则重判。
全部源活跃日从全部农场计算，非仅配对农场。
文件覆盖期间全源无记录日仍为44/8；确认没有把它们变成零。

## 训练冻结与时间隔离

在真实fit前冻结配置hash `854a289f5a183de4ef565bb7b9a77e5d122fed1a53e68588eb499d252bf1744e`。
使用全部27个严格合格23–24农场训练，截止2024-06-30；不是只用3个验证农场，也不是kg规模加权。
每天目标是该农场已记录到厂量 / 该农场导出记录总量；source-active缺行0，global unknown不进入fit。
面积不参与，品种不作为特征。每农场等权，StandardScaler只fit训练日历特征。
候选固定：alpha10/SVD Ridge、两组年度sin/cos；经验shape为训练农场逐日share宏平均。
没有Spline第三候选、网格搜索或验证成绩驱动调参。
两组年度谐波/alpha沿用R1算法类别；本轮重新fit **share**，不是加载旧R1的kg/mu系数。

对齐为预先固定July1..June30的归一化日历位置；不以验证首采/峰日/末采对齐。
经验模型在训练未观测的日历位置采用模型预测插值/边缘常数延伸；
这不修改任何UNKNOWN标签，且预测输出单独保存，不冒充实测。
预测固定完整365日日历，非负且sum=1；不得按验证总量或验证标签掩码缩放。
新进程load后预测，不fit、不读取validation_labels；prediction hash在评价前冻结。
模型文件/训练清单/依赖版本/代码文件hash全部保存在私有产物。

## 正式评价的可观察性边界

VALIDATION_TYPE=CROSS_SEASON_OUT_OF_TIME_RETROSPECTIVE，VALIDATION_BLINDNESS=NOT_BLIND。
只评价两季均strict的3农场。每农场323天已知，8天global unknown、34天文件尾部未覆盖。
这42天label保留空值，未补0；日MAE/WAPE仅在相同323已知行计算。
实际share分母是**导出已记录总量**，不是已证明的全农艺产季总量。
候选prediction不按已知日重新归一化；未知/未覆盖日预测概率质量也明确报告：
Ridge 0.100221951621，经验 0.018413758816。
每农场有294个完整七自然日label窗口；跨UNKNOWN的窗口不计算，不当七日均值。
实际峰来自已知账本标签；预测峰来自完整固定预测日历（不删去预测不好的日）。
本次两模型预测峰日/七日峰窗均落在有完整标签处。
未证明UNKNOWN/未覆盖期不存在更大真实峰；不能称完整未知产季真值已验证。
`MULTI_SEASON_SHAPE_VALIDATED=true` 仅指本次限定口径跨季评价已执行，不代表业务精度获批。

## 实际模型比较

| 3农场等权宏统计 | Ridge | 经验mean |
|---|---:|---:|
| 峰日误差中位数/天 |19|94|
| 峰日误差均值/天 |18.333333|93.333333|
| 峰日误差P90/天（linear quantile） |27.8|102.8|
| 七日窗口偏移中位数/天 |19|12|
| 七日窗口偏移均值/天 |17.666667|10.666667|
| daily share MAE |0.003924363177|0.003742039959|
| daily share WAPE |1.267569306252|1.208678906749|
| 峰日误差≤7 / ≤14 / >30农场数 |1 / 1 / 0|0 / 0 / 3|

经验shape虽改善七日窗口及日误差，但峰日大幅变差，不满足“峰日和七日偏移同时改善，MAE/WAPE不恶化”。
保留Ridge为本轮对照选择，不宣称已可部署。WAPE约126.76%表明日分布误差仍大。
不能把本轮18.33天与R1/R2版纳单范围32天直接视作同一数据集提升。

| 农场 | 模型 | 已知账本峰日 | 预测峰日 | 峰日差/天 | 实际七日开始 | 预测七日开始 | 偏移/天 |
|---|---|---|---|---:|---|---|---:|
| 保山华兴农场 |Ridge|2025-05-09|2025-04-09|30|2025-05-03|2025-04-06|27|
| 保山华兴农场 |经验|2025-05-09|2025-01-24|105|2025-05-03|2025-04-13|20|
| 保山杨柳农场 |Ridge|2025-04-15|2025-04-09|6|2025-04-13|2025-04-06|7|
| 保山杨柳农场 |经验|2025-04-15|2025-01-24|81|2025-04-13|2025-04-13|0|
| 建水南庄基地 |Ridge|2025-04-28|2025-04-09|19|2025-04-25|2025-04-06|19|
| 建水南庄基地 |经验|2025-04-28|2025-01-24|94|2025-04-25|2025-04-13|12|

## 执行与产物

私有持久目录：`/Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed`。
其中有资格表、source-active calendars、train_curves、validation_labels（UNKNOWN为空）、模型JSON、
prediction manifest、2190行cross_season_predictions、逐农场metrics、selected model及artifact_manifest。
原始XLS、逐日业务CSV和模型权重不上传Git。公开仅[聚合证据/hash](evidence/ledger-shape-r3a-confirmed.json)。

```bash
.venv/bin/python -m scripts.run_confirmed_shape_r3a train --r3 /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3 --output /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed
.venv/bin/python -m scripts.run_confirmed_shape_r3a predict --output /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed
.venv/bin/python -m scripts.run_confirmed_shape_r3a evaluate --output /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a-confirmed
```

上述已实际执行，各阶段排他创建，不覆写既有结果；fresh-process prediction不fit。
一次评价阶段，2模型×3农场；无重试、后验调参或24–25重拟合。
本地411项相关测试通过，Ruff/format/Mypy通过；R1/R2私有产物hash核对PASS。
只在本地验证与实验冻结后push一次，GitHub负责最终exact-head验证。未完成CI不可称PASS。
无旧S4/TEST、旧验证预算变化、天气、未来计划、旧基线替换或tag变化。
保持#612 Draft。FINAL_STOP_GATE=COORDINATOR_R3A_LEDGER_AND_SHAPE_REVIEW。
