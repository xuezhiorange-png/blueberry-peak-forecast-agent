# R4 农场固定面积总量模型

## 实际结果

RESULT=BLOCKED_MISSING_PRODUCTIVE_AREA_VALUES。
AREA_BOUND_FARM_COUNT=0，AREA_BOUND_COMPLETE_FARM_SEASON_COUNT=0，CROSS_SEASON_AREA_BOUND_FARM_COUNT=0。
这不是缺逐产季面积表；农场固定面积、跨季共用已经确认。
缺的是能合法绑定到对应农场的投产面积值，或已有候选代理值作为投产面积的依据。
真实训练、跨季总量评价、预测示例均未执行。没有选定模型或伪造模型文件。
shape搜索停止，R3C结论不变。

## 搜索结果与来源

检查仓库data/templates、configs、相关生产面积authority及导入代码、V0.3/S3和经营验收证据、新实验私有清单、授权attachments文件名。
data/templates/farm_location_master.csv、season_variety_planting.csv仅表头，无业务行。
旧area-yield-r1/area_mapping_audit.csv仅有版纳Dx736亩校准分母，不是全农场或其他农场面积。
原始2324/2425已核验字段没有面积；本轮不重复解析，不读旧2025_2026或sealedTEST。

发现真实row-bearing [S3面积package](../v0-3/s3/authority/farm_total_area_authority_package.json)，
通过生产load_area_authority_package验证内部row/set/canonical hashes。
文件hash=02fe4b00e35589578fa7fd7a7cc6550bf34c9bfb6cb4a8926770878bce2a66df。
来源由[历史workpaper](../v0-3/s3/workpapers/s3-farm-total-baseline-validation-scoring-r1.md)明确为
光筑25产季加工布局规划方案.xlsx / 25产季产量预测汇总表 / rows2:640，source hash
4d2ab255886e302236fa7490b0beb9a339d3896ef2f417e9164ef888090bafb6。
正式area_authority_class=PREVIOUS_SEASON_PROXY。授权固定跨季不自动将规划代理面积变成productive_area。
本轮不将其改称MEASURED/BUSINESS_REPORTED/AUTHORIZED_CALIBRATION。
31组旧package中有多farm聚合项，不能拆分分配给下属农场。

109个历史farm union完成binding表：36个有exact-key代理候选，标AMBIGUOUS，其余MISSING；BOUND=0。
候选数值及source/scope/hash保存在私有farm_area_authority_r4.csv，不新增公开业务面积明细。

|当前完整跨季农场|已有资料|精确剩余缺口|
|---|---|---|
|保山华兴农场|未找到exact farm面积row|该农场productive_area_mu值及来源|
|保山杨柳农场|旧package存在exact-key代理面积|该数值能否作为本轮实际投产面积的依据/授权|
|建水南庄基地|旧package有建水南庄农场，不是exact label|合法身份等价依据及面积投产语义，不能靠相似名称合并|

其他27个严格训练farm及5个严格validationfarm的名单在[证据](evidence/total-yield-r4.json)。
不要求补齐全部农场；上述任一完整配对取得合法binding即可进入后续真实训练，不需第二产季面积表。
不据量反推面积，不推广736亩，不按面积比例修复未知产季累计量。

## 已实现的独立模型基础代码（尚无真实模型产物）

Area显式绑定farm、正有限Decimal面积、允许basis、source引用/hash、FARM scope及投产语义确认。
sample仅接纳COMPLETE/STRICT_ELIGIBLE，两个季节共用同一个Area对象；kg/mu采用6位HALF_EVEN。
fit仅接纳23~24单farm单季样本，拒绝重复及24~25；提供global median和same-farm prior两个确定性基线。
predict_total按输入亩数乘亩产，prior未知农场fail closed；global是显式选择，无隐式fallback。
100/500/1000缩放与新进程JSON加载只通过synthetic软件测试，不构成真实面积外推验证或训练交付。
LINEAR_AREA_SCALING_IMPLEMENTED=true，AREA_SCALING_VALIDATED=false。
未实现MODEL_C或复杂ML、shape重评、组合示例、服务部署或现用模型替换。

## 私有产物与复现

目录：/Users/charles/Documents/blueberry-area-yield-artifacts/total-yield-r4/。
farm_area_authority_r4.csv有109行；farm_season_yield_r4.csv仅schema表头、0合法样本。
training_manifest/model_comparison/cross_season_total_metrics均显式NOT_EXECUTED/无真实模型；artifact_manifest绑定文件hash。
没有创建空模型冒充已训练模型，没有对不合格面积进行亩产计算。

```bash
.venv/bin/python -m scripts.audit_total_area_r4 --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /Users/charles/Documents/blueberry-area-yield-artifacts/total-yield-r4
```

该命令已实际执行，输出目录排他创建。它是当前面积审计路径，不声称是已完成真实训练的runner。
如果以后提供合法BOUND sources，需要绑定到sample/fit并完成冻结评价与报告；本轮按zero-cross-pair门槛不越过执行。

## 保护与验证

R3A原artifact所有manifest hashes运行前后验证；R1/R2/R3B/R3C未写入，#612无新commit。
纯单元测试覆盖跨季同面积、非法面积/basis、scope错误、partial拒绝、kg/mu、训练隔离、hash/序列化、未知farm、线性缩放、新进程加载。
本地435项相关回归PASS，Ruff/format/Mypy（422源文件）/JSON/diff通过后一次push；GitHub保持required full-suite-canary，仅最终exact-head验证。
未执行总量或shape真实评分，无旧S4/TEST、天气、未来计划、旧baseline变化。
新Draft PR堆叠于#612 head6632e850488f168453b58fe1a10392e9a6cfbb94，保持不Ready/Merge/Release。
FINAL_STOP_GATE=COORDINATOR_TOTAL_YIELD_MODEL_R4_REVIEW。
