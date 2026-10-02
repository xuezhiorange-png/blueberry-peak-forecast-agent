# 面积驱动模型训练与时间留出回测（2026-10-02 R1）

TASK_ID=NEXT_VERSION_AREA_BASED_YIELD_MODEL_TRAINING_AND_BACKTEST_R1
Execution ID=NEXT_AREA_SIZE_20261002_R1

## 结论

工程链路已完成；科学结论为 RESEARCH_CANDIDATE_NO_STABLE_GAIN。
唯一合法的非封存时间留出上，总量、日量和峰值公斤数有可测改善；形状和峰时未改善。
只有一个且此前已用于研发的测试产季，不能宣称稳定跨折增益、新盲测、前瞻验证或生产可用。
本轮不是重复使用早期同任务号的 736 亩/单产季 Ridge 成绩；输入与模型均由本 execution ID 隔离。

## Preflight 与依赖

从最新 origin/main `8e886b45984a358125d00e80f4f5d662fab3d8e9` 创建
`codex/next-area-yield-training-backtest-20261002-r1`。
原工作树有 3128 个未跟踪文件，已跟踪文件干净；新独立工作树从 main 创建时干净。
原工作树、模型、数据、ZIP 均保留。没有 merge/cherry-pick #658，没有读取或修改其新增实现。
复用 main 上的 area-yield、Decimal、hash、日曲线指标与严格连续七日峰值代码。
不引入天气、未来计划、品种独立模型、接口发现或第二套服务。

## 数据审计与面积匹配

仅打开旧 S8 **训练池**中的两个已封存身份但非测试用途的输入文件：
`v0-8-canonical-training-dataset-r1.csv`、`training-daily-curves-r1.csv`。
它们的准确 hash 见 [聚合证据](evidence/next-area-size-20261002-r1.json)；
运行时校验与已授权训练来源完全一致。2025–26 OOT、旧 sealed TEST、原始新产季 XLS 均未打开。
到厂量作为当前采摘代理；不声称直接观测成熟量。

|检查|结果|
|---|---:|
|可用历史产季|2|
|合法 Base-season|37|
|唯一 Base|26|
|canonical Base-season-day 行|10708|
|日行面积匹配/未匹配|10708 / 0|
|样本面积匹配/未匹配|37 / 0|
|真实/授权零日|5327|
|缺量行（该合法子集）|0|
|已排除旧身份不明确样本|41|

日行不是原始收货行；原始收货行数本轮未重建。
41 个排除数来自已有 S7 权威报告，不是本轮重新读取不安全原始来源的结果。
“未匹配为0”仅针对上述37条合法子集，不能解释成所有历史来源均已匹配。
历史面积依据已有用户明确的三产季业务绑定，不使用未来面积自行回填；
该绑定不是独立实测面积核验。每行核对 season、Base、面积正值、authority ID、严格资格、
完整日期覆盖及日量和总量一致；缺数与未解析身份 fail closed，不转成0。
历史入库/修订可见时间未证明，保留 NOT_PROVEN。

## 冻结问题与唯一 fold

目标总量是现有 **July-01..April-15 冻结业务窗口**，不是全年或未截断自然产季。
请求给出 target area(mu)、season 和 Base 上下文；Base用于适用范围，不作为记忆标签。
日期按现有 month/day 规则；闰日只在训练确有合法覆盖时支持，不补缺日。
训练 2023–24：15样本，4350日；测试2024–25：22样本，6358日。
训练/测试面积范围均为216..2548mu。两模型使用同一22样本、同一6358日评分。
最终工件仍只拟合15训练样本；**不将22个留出样本回混训练，不拟合2025–26**。
训练统计、回归与形状仅来自训练行；生成预测并保存hash后评分。资格覆盖审计不用于选参。
既有测试季已消费；本轮只是一项预固定的有限历史留出，不恢复全球未见测试资格。

## 两个固定模型

Baseline：`Qhat=A_target * sum(Q_train)/sum(A_train)`。
Candidate：`Qhat=A_target * exp(alpha + beta*(log(A_target)-mean(log(A_train))))`。
alpha为训练 log(Q/A) 的均值，beta为闭式L2回归系数，固定惩罚1；
不搜索任何超参数，没有按测试成绩改模型。
该关系是统计面积-亩产关联，不是生理因果或已证实的面积外推规律。
两者共用训练 Base-season 等权平均的 normalized daily share，目标合法窗口内归一化。
这使总量增量与新时间形状增量分开：本轮没有声称形状层优于共享基线。

数量采用0.000001kg HALF_EVEN，逐日舍入残差加到最大份额日（最早并列），严格总量守恒。
所有峰值来自同一日曲线，七日是七个连续自然日累计，不是七日日均。

## 实际留出结果

|指标|Baseline|Candidate|变化（候选－基线）|相对变化|
|---|---:|---:|---:|---:|
|窗口总量WAPE|0.450910|0.417458|-0.033452|-7.418775%|
|日WAPE|0.770660|0.731543|-0.039117|-5.075779%|
|shape micro WAPE|0.632252|0.632252|0|0|
|单日峰日期MAE/天|21.818182|21.818182|0|0|
|单日峰量MAE/kg|7233.920555|6572.139398|-661.781157|-9.1483%|
|滑动7日峰起日MAE/天|22.318182|22.318182|0|0|
|滑动7日峰量MAE/kg|48318.586215|45003.802717|-3314.783498|-6.8603%|

总量MAE：405935.417387→375819.915438kg/Base-window。
真实同cohort总量19805668kg。相对变化的精确六位显示见机器证据（表中部分百分比作显示近似）。
单折改善不能提供 fold 间稳定性证据；不存在通过重排/过滤挑出最好子组。
模型保留 RESEARCH_CANDIDATE，不命名为 production、approved、champion 或 best。

## 工件、推理与复算

真实敏感工件和逐行诊断只在受控本地目录保管，不提交Git。
模型包含输入身份、训练范围、面积范围、版本、参数、形状、生成时间及代码hash。
候选文件SHA256：
`5aecb3fbbedfdb3b4eb0db20e444446c1fde65e5c787d1e117f9428c56a2d352`。
内容hash：
`be265f1bce5829350873da871c067c8b44e6af76cf5039a9648bcc34e1391371`。
同metadata下重复拟合两模型均完全一致，共4次fit、2个固定配置，没有搜索。
新进程加载保存的候选并预测，完全一致；另在独立进程加载两工件复现44个留出请求和全部指标，
无fit、无预测CSV查表。封存JSON只供完整性与结果对比，不作为推理输入。

复用既有Python项目入口风格的薄实验调用，不新建CLI框架/API：
```bash
python -m scripts.run_next_area_size_r1 train-backtest --source "$SOURCE" --output "$NEW_PRIVATE_RUN"
python -m scripts.run_next_area_size_r1 predict --artifact "$RUN/candidate-artifact.json" --request "$RUN/example-request.json" --output "$NEW_RESPONSE_JSON"
python -m scripts.run_next_area_size_r1 replay --source "$SOURCE" --output "$RUN"
```
SOURCE仅可指向两项hash已核验的旧训练池目录。输出必须是新路径；已存在目录/文件拒绝覆盖。
本轮实际受控路径见本地回执，不公开私有绝对路径。

## TEST_ONLY 示例及适用性

736mu，2026–27业务窗口2026-07-01..2027-04-15，289个连续日。
总量635015.338054kg；单日峰2027-04-08，12240.367844kg；
七日峰2027-04-08..04-14，累计82455.663078kg。
总量等于日量和；result hash：
`98f60e32241d20ecd5f5a4d087307d863499533fa91af0451ba5fded9b9b3119`。
面积位置INTERPOLATION，Base为明确TEST_ONLY未见Base，因此有范围警示。
这不是未来业务面积确认，也不是真实发报；窗口已开始不影响演示身份，绝不能称产季前发行。
超出216..2548mu会输出 EXTRAPOLATION warning；范围内也没有面积泛化精度保证。

## 检查与后续边界

580项面积相关测试通过，新增18项定向测试复跑通过；全仓库Ruff与1222文件format通过，
Mypy覆盖backend/app的511个源码文件通过，另有两文件限定检查及三文件compile通过。
CLI train-backtest、fresh-process predict、无重训replay真实执行。
全仓库正式CI在Draft PR的exact-head单列，不能由局部测试冒称全绿。
没有改变主模型、#658、旧结果或生产默认；没有联网补数据或生产部署。
只保留单折总量关联的有限增益。下一步需要明确授权的真实未来验证，或含新信息的研究授权；
不自动追加参数/模型搜索，也不以代码或CI通过宣布模型可用。
