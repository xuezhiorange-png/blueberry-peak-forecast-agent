# R6 冻结模型复验与样本资格入口

## 结论与最短解锁路径

基于 main `758f96954c4682607267cbbf024b3dd06f52c8d6`。
RESULT=EVIDENCE_EXPANSION_READY：流程已实际执行，新增独立样本为0，不是扩大样本成功。
总量验证仍为2农场，shape共同exact集合仍为2农场。两项研究重启门槛均未达到。
当前有限证据组合B2不变；不是生产批准、泛化证明或面积外推验证。

|农场|2324账本|2425账本|面积|最小新增证据|
|---|---|---|---|---|
|保山杨柳农场|STRICT_ELIGIBLE|STRICT_ELIGIBLE|393.4 BUSINESS_CONFIRMED|已有样本，不计新增|
|建水南庄基地|STRICT_ELIGIBLE|STRICT_ELIGIBLE|152.35 BUSINESS_CONFIRMED|已有样本，不计新增|
|保山华兴农场|STRICT_ELIGIBLE|STRICT_ELIGIBLE|MISSING|真实productive_area_mu及明确确认来源|
|保山仁和农场|GLOBAL_UNKNOWN_BLOCKED|STRICT_ELIGIBLE|未绑定|补充下列8个未知日的合法来源，另需面积才可做总量|
|砚山平远街一场|GLOBAL_UNKNOWN_BLOCKED|STRICT_ELIGIBLE|未绑定|补充下列6个未知日的合法来源，另需面积才可做总量|

华兴总量HUAXING_TOTAL_UNLOCK_STATUS=AREA_REQUIRED。核对当前
`docs/v0-3/s3/authority/farm_total_area_authority_package.json`、R4原面积审计私有CSV、
`configs/confirmed_total_r4.json`及R4确认产物，未找到华兴投产面积；没有按别名/相似名扩大绑定。
EXACT_MISSING_AREA_FARMS=保山华兴农场，指**已完整配对、只缺面积**的最短总量解锁路径。
确认华兴面积后，新配置新增一条Area即可得到第三场总量复验，不改变全局中位数，不等待shape峰值可评价。

仁和未知日：2023-09-19、09-21、09-27、09-29、09-30、10-01、10-02、10-04。
平远街一场未知日：2023-09-27、09-29、09-30、10-01、10-02、10-04。
只有新的合法账本证据可解除，不接受插值、模型补量、邻日推断或默认0。

华兴prior预测峰2025-05-28、预测七日2025-05-24..05-30，覆盖截至2025-05-27，
两项均RIGHT_CENSORED。保留known-support诊断，但exact时点误差为null；不视为模型失败，也不混入共同exact宏指标。

## 资格合同

`backend.app.area_yield.evidence_expansion_r6.FarmSeasonQualification`包含身份、产季、source hash、
覆盖起止、完整导出确认、active-span未知日清单、零日授权、完整性、面积、总量/shape资格、峰/七日状态及排除原因。
复用R3A的14日边界buffer、exact身份和active-span规则，没有放宽旧标准。
SOURCE_INCOMPLETE / GLOBAL_UNKNOWN_BLOCKED / LEFT_CENSORED / RIGHT_CENSORED /
NOT_ELIGIBLE_OTHER / STRICT_ELIGIBLE明确区分。
AREA_MISSING作为正交的总量排除原因保留，不把完整账本改称不完整，也不阻断shape。
资格阶段峰状态为NOT_COMPUTABLE_OTHER（尚未预测）；评分后另存model-specific的evaluated_qualification.json，不覆盖原资格冻结。

144条farm-season资格全部保留，包含不配对和不合格范围；五个严格validation农场名单与R3C一致。
SOURCE_ACTIVE_DAY且该farm缺行，仅在完整导出和零语义均有授权时产生SOURCE_ACTIVE_LEDGER_ZERO。
GLOBAL_NO_RECORD仍为空标签。它不是生物学零产量；STRICT仍是既有工程账本资格，不声称完整生物学产季真值。
面积只接受MEASURED、BUSINESS_REPORTED、BUSINESS_CONFIRMED、AUTHORIZED_CALIBRATION；
拒绝代理面积自动升级、反推、跨farm复制和猜测。面积>0且finite，FARM粒度、跨季固定。

## 三阶段与可执行命令

```bash
.venv/bin/python -m scripts.run_frozen_evidence_expansion_r6 qualify --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/evidence-expansion-r6 --config configs/frozen_evidence_expansion_r6.json
.venv/bin/python -m scripts.run_frozen_evidence_expansion_r6 predict --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/evidence-expansion-r6 --config configs/frozen_evidence_expansion_r6.json
.venv/bin/python -m scripts.run_frozen_evidence_expansion_r6 evaluate --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/evidence-expansion-r6 --config configs/frozen_evidence_expansion_r6.json
```

以上三个命令已分别在新进程实际执行一次。目录与产物排他创建；同目录不能重复运行或覆盖。
qualify可以解析标签用于来源/资格检查，但不选择参数；history和validation_labels拆开保存。
predict只读冻结资格、历史、组件和配置，不读验证标签（包括不为了验证hash读取它）；先写预测及独立文件hash。
evaluate必须验证qualification和prediction冻结、代码hash，之后才读取标签评分。
没有fit入口，没有模型搜索/selector学习；宏观组合比较沿用R5 Pareto报告规则，不修改组件选择和生产路由。

R4两个模型文件都加载并校验hash。原两场的prior lookup与冻结farm_yields逐值核对。
新增farm或后续historical season的prior仅按冻结规则读取完整已授权历史总量/面积，绑定输入hash；
这是新增历史输入下的固定lookup，不扩充全局中位数、不重训R4或把未知farm静默fallback。
Global Ridge从R3A models.json加载冻结系数。Same-farm沿用R3B固定season-position插值及归一化规则，
不调用旧carry_forward内部fit。未知训练标签保持未知；插值仅为PREDICTION_INTERPOLATION_NOT_LABEL_IMPUTATION。
本轮三场ridge/prior share数组与R3B完全一致，两场八组合daily kg与R5逐值相同。

## 新来源接入合同

本轮没有新XLS，不主动读取2526或任何legacy sealed TEST。
`accepted_r3`模式只用已经审阅、hash绑定的新上传2324/2425聚合，不合并repo旧2425。
未来单独授权新完整XLS后，可在新配置使用`mode=authorized_xls`：
必须指定path、source_hash、season、coverage_start/end、authorization_reference、legacy_sealed_test=false，
以及完整导出和source-active缺行零语义确认。配置声明不能替代真实用户授权。

新XLS复用R3七字段schema及kg解析：先hash，验证所有sheet字段，检查日期/null/负数/重复，再聚合farm-day。
未解决的七字段重复记录、summary/detail叠加或空farm均fail closed，不去重猜测。
来源覆盖必须与声明一致；任一日期越出产季/覆盖拒绝。然后建整个来源active calendar、farm ledger、资格。
补充源应提供已合法去冲突的完整替代导出；本runner不自动拼接重叠原始来源。
本轮仅验证新来源入口的软件边界，未宣称已经验收一个不存在的新XLS。

优先后续以2425作为prior历史、2526作为新out-of-time验证；2324全局组件继续冻结。
当前runner一次处理一个明确historical→later validation配对，不把两个历史季合并学习新模型。
不得提前查看2526成绩调权重、shift、selector或模型。若无合格配对，qualify仍输出缺口；predict拒绝，不写假预测。

## 实际复验结果

这次是已看过标签的同样本复验，VALIDATION_BLINDNESS=NOT_BLIND，不增加独立样本数。

|模型|亩产MAE kg/亩|宏MAPE|总量相对误差P90|kg加权WAPE诊断|
|---|---:|---:|---:|---:|
|Global|282.417506|0.456115|0.765042|0.196256|
|Prior|202.618187|0.279952|0.386630|0.190218|

shape共同exact两场：Ridge峰差12.5天/七日13天，Prior峰差7.5天/七日6天。
条件WAPE分别1.335998983664307与0.9148159942778089；不回写预测、不按kg规模加权。
华兴单列删失记录，未从总体名单消失。
八个组合总量守恒；B2仍为有限证据宏最佳，杨柳NO_CLEAR_WINNER、南庄B2，异质性保留。

## 产物与停止门槛

私有目录 `/Users/charles/Documents/blueberry-area-yield-artifacts/evidence-expansion-r6/`。
包含source_manifest、144行qualification_matrix、area_binding_status、eligible_total/shape_farms、
missing_evidence、history、隔离labels、qualification_freeze、frozen_prediction_manifest、prediction_freeze、
evaluation_manifest、evaluated_qualification和artifact_manifest。Git只含代码、配置、聚合报告/hash。
R1–R5共130个私有文件在前后逐文件hash一致，未覆盖旧证据。无weather/未来计划/legacyTEST/旧S4操作。

TOTAL_RESEARCH_REOPEN_READY仅在总量独立farm>=3时成立；SHAPE_RESEARCH_REOPEN_READY仅在共同exact farm>=3时成立。
门槛达到也只允许提交下一独立研究任务，R6不自动开始研发、部署或发布。
当前两项均false；华兴面积是最快总量扩样路径，shape另需完整后段或其他合法完整跨季范围。
本地479项相关测试PASS（其中R6新增32项）；Ruff、format、Mypy（426源文件）通过。
公开聚合与逐文件hash见[证据](evidence/frozen-evidence-expansion-r6.json)。
GitHub standard CI/full-suite-canary只做最终exact-head验证，不绕过，未结束时报告PENDING。
FINAL_STOP_GATE=COORDINATOR_R6_EVIDENCE_EXPANSION_REVIEW。
