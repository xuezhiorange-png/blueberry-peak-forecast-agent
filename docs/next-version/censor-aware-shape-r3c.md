# R3C 身份与删失感知评价

## 当前结论

RESULT=EVIDENCE_STILL_INSUFFICIENT。MODEL_SEARCH_STOPPED=true。
NEXT_EVIDENCE_NEED=MORE_COMPLETE_CROSS_SEASON_FARM_PAIRS。
不搜索模型、不调参、不重新训练、不修改旧预测。等待更完整24–25后段、另行授权的25–26完整历史或更多合法配对。
现有sealed TEST不因此获得读取授权。

## 身份纠偏：另外两个农场并非名称不匹配

24–25严格5个：保山仁和农场、保山华兴农场、保山杨柳农场、建水南庄基地、砚山平远街一场。
五者在23–24均有完全同名记录。复核hash绑定R3A资格表及source-active calendar，身份依据为EXACT，而非fuzzy或alias。
configs/backend/app/docs/next-version/data/templates检索未发现仁和/平远街的新旧名称授权映射；已有配置是factory/variety aliases，不能升级为farm alias。
存在同名历史实体时，不能用另一个相似名称农场替换其不完整历史。无需再次用字符串相似度寻找“更完整”的替代主体。

|23–24 label|24–25 label|match_status|训练季资格/原因|
|---|---|---|---|
|保山仁和农场|保山仁和农场|EXACT|排除：ACTIVE_SPAN_GLOBAL_UNKNOWN，8日|
|保山华兴农场|保山华兴农场|EXACT|严格合格|
|保山杨柳农场|保山杨柳农场|EXACT|严格合格|
|建水南庄基地|建水南庄基地|EXACT|严格合格|
|砚山平远街一场|砚山平远街一场|EXACT|排除：ACTIVE_SPAN_GLOBAL_UNKNOWN，6日|

仁和未知日：2023-09-19、09-21、09-27、09-29、09-30、10-01、10-02、10-04。
平远街一场未知日：2023-09-27、09-29、09-30、10-01、10-02、10-04。
原35个exact identity pairs保持；严格validation集合中exact identity pairs=5，但两季严格eligible pairs=3。
AUTHORIZED_ALIAS_PAIR_COUNT=0；无原始身份改写、无新mapping、无训练标签补造。

## 删失合同

覆盖边界来自既有hash绑定资格表，不从最后非零日推断覆盖终点。
预测峰/窗口超出右边界：RIGHT_CENSORED；早于左边界：LEFT_CENSORED。
内部UNKNOWN：NOT_COMPUTABLE_OTHER；边界齐全且所需标签齐全：EXACT_COMPUTABLE。
跨越左右两边或边界缺失：NOT_COMPUTABLE_OTHER。删失不是模型失败，也不等于证明真实峰在覆盖外。
误差使用null=NOT_COMPUTABLE，绝不对覆盖外补零或按趋势估计峰日。

华兴prior：预测峰2025-05-28、coverage_end=2025-05-27、days_beyond_coverage=1。
预测七日2025-05-24..05-30跨边界，两项均RIGHT_CENSORED。
last_observed_positive_date=2025-05-09；observed_max_date=2025-05-09。
覆盖最后14日中前7日与后7日均记录0kg，差值0。该描述不能证明未来真实峰日，更不能撤销删失。
RIGHT_CENSORED_FARM_COUNT=1，RIGHT_CENSORED_MODEL_PREDICTIONS=华兴/prior（一个模型预测，两项删失）。
华兴仍保留在3农场总体及known-support记录中，不静默删除。

## 冻结预测与共同评价集

完整复用R3A全局Ridge、R3B same-farm预测及其既有指标，不调用fit/predict，不产生新模型。
R3B prediction hash：93dba7516d7a65cfdfbdf42e1a0d05e145e2241151ee46b9790487f388096715。
COMMON_EXACT_COMPUTABLE_SET=保山杨柳农场、建水南庄基地。
两个模型峰日及七日都可算才进入；以下所有macro均在相同这两个农场等权计算。

|指标|Ridge|同农场上一季|
|---|---:|---:|
|平均/中位峰日误差 天|12.5 / 12.5|7.5 / 7.5|
|平均/中位七日窗口偏移 天|13 / 13|6 / 6|
|KNOWN_SUPPORT_WAPE|1.335998983664|0.914815994278|
|KNOWN_SUPPORT_MAE|0.004136219764|0.002832247660|
|full-calendar未知预测质量均值|0.100221951621|0|

华兴未纳入上述共同macro，但完整单独报告：prior未知预测质量0.064990653134、条件WAPE1.167800847873；Ridge分别0.100221951621、1.224997426847。
条件归一仅评价，不改变full-calendar输出。实际峰仍为已知账本峰，不声称整个未知产季最大峰被观察。
在共同集合上两项timing和shape均改善，但count=2<3，不能宣布FARM_HISTORY_IS_MATERIAL_SHAPE_SIGNAL=true。
AREA_ONLY_IS_SUFFICIENT_FOR_PEAK_TIMING=NOT_ESTABLISHED；本任务未检验亩数外推。
总亩产仍WAITING_FOR_HISTORICAL_AREA_DATA，MULTI_SEASON_TOTAL_YIELD_VALIDATED=false，AREA_SCALING_VALIDATED=false。

## 产物、复现与保护

私有结果：/Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3c/results.json。
同目录artifact_manifest.json记录结果hash。公开[聚合证据](evidence/censor-aware-shape-r3c.json)保存身份依据、删失记录、逐农场结果和源产物hash。
没有原始XLS、逐日业务数据或模型权重上传。

```bash
.venv/bin/python -m scripts.run_censor_r3c --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3c
```

已执行一次，排他输出目录；R3A/R3B全部manifest文件运行前后hash核验通过。
R1/R2路径未写入，历史代码和证据未改。仅新增R3C文件，不更改CI。
本地423项targeted及R3A/R3B/R1/R2相关回归PASS，Ruff/format/Mypy（421源文件）/JSON/diff检查PASS后一次最终push。
GitHub仅最终exact-head验证，未结束报告PENDING。无旧TEST、S4重开、天气、面积、现用模型替换或预算变化。
保持#612 Draft，不Ready/Merge/Release。
FINAL_STOP_GATE=COORDINATOR_R3C_IDENTITY_AND_CENSOR_REVIEW。
