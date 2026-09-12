# 面积驱动模型：隔离训练与时间回测 R1

任务：`NEXT_VERSION_AREA_BASED_YIELD_MODEL_TRAINING_AND_BACKTEST_R1`。
用户本轮明确授权新实验训练和回测；supersedes #610 的 API 发现/CSV 下载优先建议。
#610 不作为前置，不修改、关闭或合并它；不替换 v0.3.1，不开放旧 S4/TEST。

## 训练前冻结

配置：[experiment_config](../../configs/area_yield_experiment_r1.json)。
主路线 A：预测每日 kg/mu，再乘输入亩数。品种不是调用必填项；但目前可用
面积分母只对应原版纳/Dx范围，模型适用范围仍严格限于该参考范围，不能改称全农场模型。
预测面积不等于未来生产计划；到厂量等于采摘量，不重复折减。

唯一已对应的合法子集是 2024–2025 版纳/Dx 的 736 亩
`ACCEPTANCE_CALIBRATION_DENOMINATOR`。这是用户授权校准，不是实测全农场面积。
其他范围没有在现有授权路径找到可用面积对应表；2025–2026 原始 XLS 不读取，
以避免旧 sealed TEST 字节，也没有匹配面积的独立非封存切片。模板/默认值不作标签。

完整账本零日规则只限原已批准的 2024-10-15 至 2025-05-09 窗口。
窗口外没有标签，不填零。产季预测日历单独定义为 10 月 1 日至次年 9 月 30 日，
在拟合前冻结，非依据验证实际首采、末采或峰日推断。只有一个部分产季，
无法给出产季前独立整季验证成绩；本轮真实回测明确是季内按采摘日期截断的回溯实验。
源已用于旧 R5 校准，不声称全球未见盲测；旧 S4 选模数据不作为新盲测。
没有历史修订/入库可得时间，严格 PIT 未证明。

划分：训练 2024-10-15..2025-01-31；开发 2025-02-01..2025-03-15；
最终留出 2025-03-16..2025-05-09。训练过程不打开最终标签；最终预测落盘后才读标签。
全部模型使用同一集合，不根据预测好坏排除行。

一个基线：训练日 kg/mu 均值、恒定日密度。
一个候选：年度二阶 sin/cos 特征，训练折内 StandardScaler + Ridge(alpha=10, solver=svd)，
非负截断。没有搜索；种子 0；只使用日历特征。
开发选择规则：候选 WAPE 严格低于基线且 MAE 不高于基线，否则选基线（含平局）。
比较用 6 位 Decimal 指标，零容忍。选择后两模型在训练+开发上按相同固定配置拟合，
模型/选择清单冻结，再一次性评价最终窗口，不依据最终成绩修改选择或调参。

主指标 WAPE，次指标 MAE；另报相同完整窗口总量误差、单日峰值/日期误差、
严格七自然日累计峰值/窗口偏移。调用既有 canonical 七日函数，最早日期破平局。
只有一个 scope，其聚合权重为 1；不同窗口分报，不将日数当独立产季数。
缺标签不计算完整窗口指标；WAPE 分母 0 不可计算。没有已批准绝对业务门槛。

## 执行与产物保管

入口 `python -m scripts.run_area_yield_experiment`：`prepare`、`train`、`final`、`predict`。
数据和模型在用户本地受控目录保存，目录 0700、文件 0600，不提交公开 GitHub。
排除清单、split/source hash、模型系数与标准化配置、逐点回测、指标、预测 CSV 都实际落盘。
每阶段排他创建记录，已有训练/最终评价不覆盖、不静默重跑。
JSON 模型可在新进程直接加载；不会访问 DB、Task5/8/9、旧预算或封存数据。
ML 内部浮点允许；面积/数量与落盘使用 Decimal，kg 六位 HALF_EVEN，非负截断后舍入。
每行舍入上界 0.0000005 kg，总量直接相加落盘日行，无独立总量重新缩放。

## 边界与验收

工程运行、独立整季证据、候选胜出、业务批准分别判断。
仅改变面积的比例测试是结构测试，不证明真实面积外推精度。
本轮不输出伪 P80/P90，只有未校准点预测。
完整未来日历预测是可加载模型示例，未覆盖季节位置明确标记外推，不作为已批准种植计划。
旧 207 日基线与哈希保持不变。新版本未编号；Draft PR，不 Ready/Merge/Release。

实际结果与命令在执行后追加，不预先宣称成功。

## 实际执行结果（不是预写结论）

执行代码 SHA：`3022a7d750dc8edc0119f349de70c0dfe62401e9`。
3420 条已授权收货记录 → 181 个有记录日 + 26 个该范围授权零日 = 207 行。
训练/开发/最终 = 109 / 43 / 55；一个范围、一个部分产季。没有其他合法面积对应子集。
数据表技能的核对规则用于区分单位、来源、重复汇总和未知缺数；没有生成 Excel 作为模型权威。

实际调用 4 次 fit（基线 2、Ridge 2），4 个模型×窗口回测记录（两模型×两窗口），
其中最终评价阶段只有一次。不是旧 S4 预算的调用。开发集选择 Ridge，随后冻结后再评价最终集；
最终成绩没有参与重新选型，没有后续拟合。保存模型使用 152 行训练+开发，截止 2025-03-15。

|窗口|模型|行数|MAE kg/日|WAPE|窗口总量绝对误差 kg|总量相对误差|单日峰值误差 kg / 日期差|7日累计峰值误差 kg / 窗口差|
|---|---|---:|---:|---:|---:|---:|---|---|
|development|baseline|43|4767.032546|0.783118|204982.399482|0.783118|7242.606174 / 10天|47850.600218 / 6天|
|development|ridge|43|3921.240334|0.644173|168613.334359|0.644173|6254.982121 / 4天|40948.068786 / 3天|
|final|baseline|55|7573.954420|0.740619|415675.722635|0.739033|12448.251757 / 43天|70075.774299 / 41天|
|final|ridge|55|4368.218298|0.427146|221505.773823|0.393817|8458.126090 / 32天|42172.668106 / 33天|

所有窗口均为**部分产季的完整已知日窗口**，不是独立整季成绩。
逐提前期 1–14 / 15–28 / 29–366 天的结果完整保存在 metrics.json 与公开汇总 evidence；
当前实际最大提前期为开发 43 天、最终 55 天。每个窗口、模型覆盖全部对应日行，
缺标签数 0，无预测结果驱动的排除。不能把 55 天留出称为多产季泛化。
Ridge 两窗口均优于本轮均值基线，但最终峰日仍偏早 32 天；
**工程成功，不等于达到业务标准；没有已批准业务阈值，业务可用性 NOT_ESTABLISHED。**

## 独立进程模型加载与预测

新进程 PID 44169 加载 selected_model.json，没有 fit；参考范围原版纳/Dx，
示例面积 736 亩（非未来业务种植计划）。完整显式日历 2026-10-01 至 2027-09-30，365 行。
合计 1121831.848418 kg；单日峰 2027-03-27、6658.905910 kg；
七日累计峰 2027-03-24..2027-03-30、46584.567894 kg。
与旧版 207 日结果不同是新隔离模型输出，不覆盖旧基线。
完整日历中存在训练未覆盖的位置，已标记外推，不能因为输出完整就声称完整季节验证通过。
保存产物记录 sklearn/numpy/Python 版本、标准化均值/尺度、系数、特征、种子、训练数据身份。

## 可复现命令与持久产物

当前实际产物目录（非 /tmp）：
`/Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1`。
文件权限 0600，目录 0700；只向 Git 提交代码、配置、聚合结果和 hash，
不上传逐行业务 CSV 或模型系数。此目录及同级 tar.gz 归当前用户保管；
迁移/共享须另行授权，不代表已有云端备份。

在仓库根目录执行；下面是**已执行命令**，旧目录排他保护，勿将复现当作追加调参：
```bash
.venv/bin/python -m scripts.run_area_yield_experiment prepare --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1
.venv/bin/python -m scripts.run_area_yield_experiment train --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1
.venv/bin/python -m scripts.run_area_yield_experiment final --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1
.venv/bin/python -m scripts.run_area_yield_experiment predict --output /Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1 --area 736.000000 --season-start-year 2026 --cutoff 2026-09-30 --scope BANNA_MENGWANG_DX_736MU_R1
```

后续经授权复现使用新的独立 output 目录，不能覆盖本次模型或最终成绩。
本轮数据文件清单：data_manifest.json、area_mapping_audit.csv、dataset.csv、
train/development/final.csv、final_targets.csv、split_manifest.json、experiment_config.json、
model_baseline/model_ridge/selected_model.json、selection_freeze.json、
development_predictions.csv、final_predictions_before_labels.json、backtest_predictions.csv、
metrics.json、forecast_example.csv、forecast_example_summary.json。
[公开证据及全部文件 hash](evidence/area-yield-training-backtest-r1.json)。

数据清单 SHA256：`f7f7e2641b20050f34d0675f83efbdd4be475dff5a4314e4cd00db3dd7cd4ce6`。
模型文件 SHA256：`38c4cfd05a0f49a66e7d7d193eeaa20b0b657b240ac911f104c2151c3244fba1`。
模型内容身份与文件字节 SHA 分开，内容版本：
`126be391b8de0eb425b7ac726db1f382c7b68da4d389779316d50fa5161322c0`。

未读取 2025–2026 XLS 或 sealed TEST；未运行旧 S4，也没有数据库访问。
未变更 v0.3 tags、旧预测路径、参数库或历史证据。本轮真实新回测已执行，不写“没有任何验证”。
最终状态：COMPLETED_WITH_EVIDENCE_LIMITS。仅等待 coordinator 审查，不 Ready/Merge/Release。

本地验证：372 passed（含新增 20 项）；Ruff、格式、Mypy 414 个源文件、JSON、引用、
git diff --check 均通过。真实落盘 CSV 日行连续、非负有限、总量相符；模型文件 hash
与冻结清单一致。此只读校验没有重训或再评分。CI 状态以最终 exact-head PR checks 为准，
保留所有现行 full-suite-canary，不修改 workflow。
私有包 SHA256：`ac19bb27eac0a1f2827843a5d0deae9343c8e5c7869f4ad24d2114473384459f`。

逐范围排除明细补件：
`/Users/charles/Documents/blueberry-area-yield-artifacts/area-yield-r1-scope-inventory.csv`，
SHA256 `4408be7da6533f43b0f747c92f6e0f998f8b36ad28a5a5ebf1f15088639a1a69`。
按已核验同一 2024–2025 XLS 的 farm/factory 原始标签分组，记录各组行数和最早/最晚记录日期；
共 201434 行元数据、88 个原始标签组合，**不是 88 个独立 canonical 农场或完整产季**。
未擅自合并“基地/农场”等别名。逐组全农场面积均未对应，原版纳/Dx验收子范围是唯一例外。
此只读元数据补件在训练后整理，未加入训练、修改配置或再评分；它作为私有包旁的独立补件，
不改变已经记录的训练/模型/核心实验包 hash。
