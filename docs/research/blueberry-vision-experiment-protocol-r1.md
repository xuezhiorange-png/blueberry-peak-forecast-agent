# 蓝莓视觉首轮离线实验与验收协议 R1

TASK_ID：`BLUEBERRY_VISION_FOUNDATION_ENGINEERING_PREPARATION_R1`。机器协议：`research/blueberry_vision/experiment_protocol_r1.json`。状态：`PLANNED_NOT_RUN`。`protocol_version=blueberry-vision-experiment-protocol/1.0.0` 仅为独立研究协议版本，不授予正式产品或模型版本。

本轮交付冻结未来实验的操作方法和失败处理；没有真实图像、真实标注、独立测试数据或实测算法准确率。合同校验和 synthetic pytest 通过仅代表离线工程准备可运行。训练器、模型评估器、数据采集管线、可视化审核工具和视觉到重量映射均未实现。不得将本文的未来步骤、命令接口建议或资源规划描述为已执行实验。

依据：`AGENTS.md`、`docs/research/blueberry-vision-foundation-preparation-r0.md`、`docs/v0-15/v0.15.0-closeout.md`、`docs/v0-17/v0.17.0-version-plan-and-product-scope-freeze.md`、V0.18 业务可用性范围冻结；工程复用边界见 `docs/research/blueberry-vision-existing-capabilities-r1.md`。V0.14–V0.16 模型及证据、Harvest State、V0.17–V0.18 业务合同和正式预测记录不变。V0.15 的历史 EXPOSED_OOT 已暴露，不能重新命名为新 blind/pristine/never-seen test；历史 available_at 不足不能用日期隔离冒充 strict PIT。不得读取或评分当前 2026–2027 actual。

## 1. 实验选择与 Owner 决定

建议的首个实验是**单图可见蓝莓果实检测与计数**：在获得采集、标注、算力及实验执行的单独授权后，与人工复核的可见果实计数比较。人工参考值是 ground truth；另用独立标注者第一次计数与复核值之差估计人工一致性基线，不把人工参考本身的零误差称为机器可达到的性能。这个建议不是选定最终模型架构，也不是批准 YOLO、分割或业务成熟分级。

在预注册文件中，Owner 必须逐项确认：观察单位、可见果实定义和最小可标注尺度、部分遮挡计数规则、无果与不可判定的区别、品种身份来源、任务允许用途、数据来源与许可、主指标、独立测试范围、最低样本量/置信精度、精度与偏差门槛、最大标注预算、训练资源预算和目标设备延迟门槛。现在均为 `OWNER_PENDING`，不填任意精度或样本量作为业务验收线。

成熟级别仅为候选标签研究。没有 Owner 批准、证据支持和标签版本前，蓝/红/绿或 synthetic class 不能映射成正式成熟等级、可采等级或商品果等级。路线 D 还必须另行批准独立称重、采样覆盖、重量口径、预测起点、预测窗口和视觉校准实验。

## 2. 数据与任务的最低条件

| 路线 | 输入与参考标签 | 必须先具备的条件 | 首轮推荐状态 |
| --- | --- | --- | --- |
| A 检测/计数 | 已授权图像、逐果框、复核的每图可见果实数、遮挡/小目标标签 | 单图计数定义、标注版本、非重复独立测试 | 有条件推荐；目标和数据确认后才选候选架构 |
| B 实例分割 | 同一批图像的逐果实例 mask 与 object ID | 边界、部分遮挡、不可辨目标和 crowd/ignore 规则；额外标注预算 | A 的拥挤/遮挡误差不能接受时做匹配图像的增量比较 |
| C 成熟分类/分割 | 逐果或像素成熟标签、`UNKNOWN`、裁剪/实例对应关系 | Owner 批准的等级定义、品种/光照/颜色标定及复核规则 | 标签口径和观测可靠性验证后另开实验 |
| D 视觉辅助预测 | PIT 可用的视觉观测、采样覆盖/频率、面积/树龄/品种等独立业务来源、匹配的封存面积驱动预测、独立 kg 参考 | 权威 Base/Season/采样单位、观测到采收映射、独立称重/时间来源、同 scope/unit/time common rowset | 标定和独立重量标签不足，当前不可运行 |

图像数不是独立样本数；同一会话、植株、样方、连续帧和重拍的相关性必须记录。无图像、无标注、未复核、未知身份、未知授权、空分层或不存在标签都不是零。只有已复核为无果、任务口径完整的真实观测可有合法的 0 个果实。模拟数据必须 `SYNTHETIC=true`，模型预测不得充当人工 ground truth。

采用独立 VisionObservation `blueberry-vision-observation/1.0.0` 和 manifest `blueberry-vision-manifest/1.0.0`。每条观测保留 `observed_at`、`asset_available_at`、`annotation_available_at` 和 `available_at`。`observed_at` 不能代替首次可用证据；完整观测可用时间不得早于其必要来源。预测起点使用的视觉特征必须在 cutoff 已可用。标签后来完成可以用于授权离线参考，但不能倒填成当时可用特征；训练标签和拟合记录也必须与训练截止点匹配。标注目标、模型输出、真实观测分开保存，禁止数量直接乘未经标定的单果重量。

## 3. 必须执行的顺序与产物

所有步骤是未来的执行合同，当前没有启动。任一 gate 失败即停止其依赖步骤并保留失败证据，不通过换 split、删困难样本、改标签或忽略错误获取 PASS。

| 步骤 | 执行动作 | 可审查产物与门禁 |
| --- | --- | --- |
| E0 授权/预注册 | 确认用例、观察单位、标签、许可、身份来源、数据范围、预算、主次指标、阈值、split 与测试曝光历史；指定训练人员和独立测试保管者 | Owner 签署的 experiment authorization、preregistration、许可/用途/留存授权引用。缺任何关键批准则 `BLOCKED_AUTHORITY` |
| E1 采集登记 | 仅采集已批准数据；登记会话、样方、日期、基地/品种、设备/角度/光照/遮挡、采样覆盖与重复关系；资产只写入授权存储 | 原始资产 hash manifest、来源及 available_at 证据、缺失/拒绝清单。禁止下载本轮未授权数据 |
| E2 标注复核 | 按冻结标签做逐对象标注和人工计数，独立二次复核；记录 disagreement、改标、ignore/unknown 和质量状态；复核人员不看模型预测 | label definition、annotation version/hash、annotation QA 和人工一致性报告。不可判定不可强填类别/0 |
| E3 去重、group 与 split 封存 | 在完整资产上做授权的 hash/近重复检测和人工复核；先形成连通分组，再按第 4 节切分；记录训练/验证/测试分布和不可覆盖层 | duplicate review、split manifest/hash、scope/source hashes、泄漏报告、test escrow/exposure log。独立保管者封存测试图像和标签；合格数据不足则 `NOT_EVALUABLE` |
| E4 离线契约校验 | 执行本轮 CLI 的 `--mode experiment --json`，归档原样输出和进程退出码；逐条处理授权、时间、身份、标签版本与 split 错误 | validator output/hash。该工具检查 manifest，不能代替资产字节核验、近重复计算、独立保管或完整实验就绪审核 |
| E5 训练准备与 train 拟合 | 单独批准后选择有限候选；冻结 evaluator、依赖/镜像、设备、seed、特征、模型和预算。预处理/归一化/标定/特征拟合只用 train；增强在 split 后做 | 每次训练配置/日志、代码 SHA、依赖与输入 hash、train-only fitted artifact hash、权重/model hash、资源用量及失败运行记录。预训练权重需另行许可与来源确认 |
| E6 validation 锁定 | 仅用 validation 选候选、置信度、NMS、图像大小、计数聚合/去重、分类 abstention、校准及所有后处理；记录所有比较次数 | model selection log、validation report、final config/hash。完成后训练权重、阈值、输出策略与指标实现全部锁定，不再查看 test 来调参 |
| E7 一次独立测试 | 独立保管者在固定 sealed test scope 用锁定模型生成/封存预测，再释放参考标签计算预注册指标；记录每图预测、失败/缺失及曝光 | prediction seal/hash、reference-label hash、evaluator/config hashes、one-shot test access log、逐行匹配报告。test 后更改必须新实验和新的未曝光测试集；旧集改标评估只能称已曝光再分析 |
| E8 报告与停止 | 报告总体、各分层和未知/失败覆盖率、人工一致性、资源与失败；展示区间和不可评估层，按预注册门槛判定 | metric/resource/error reports、gate decision、复现清单。达标只支持批准范围内研究结论，不自动授权生产接入、新版本、PR/Ready/Merge/Tag/Release/Deploy |

工程命令接口：`python -m research.blueberry_vision.validate_manifest research/blueberry_vision/fixtures/synthetic_manifest.json --mode contract --json`；有授权的真实实验 manifest 使用 `python -m research.blueberry_vision.validate_manifest <authorized-real-manifest-path> --mode experiment --json`。synthetic fixture 只允许 contract 成功；experiment 必须拒绝 synthetic、预测作为 GT 和未批准标签。真实路径参数须替换为已授权文件。机器 schema 位于 `research/blueberry_vision/schemas/vision_observation.schema.json` 和 `schemas/vision_manifest.schema.json`。CLI 在本轮实现，训练/evaluation runner 和 E1/E2/E3/E7 的资产处理能力未实现；不能声称仅一条 validator 命令就完成完整实验。Polygon 契约的简单边界校验不构成完整实例分割标注或训练支持，路线 B 适配须另行授权实现。

## 4. split 与独立验证冻结方法

先按 asset SHA256 相同、近重复审查分组、同一 capture_session、同一长期 sampling_unit、同一原始视频/重拍关系的任一连接，生成连通分组。对多日同植株样本，用整个纵向 sampling unit 分组，避免同一果实反复出现到不同 split。即使这减少可用样本，也不能拆开连通组求更好成绩。近重复算法/阈值/人工复核办法在分割前预注册，只存 group ID 并不能证明已执行去重。

禁止相邻帧或相邻日期随机拆分作为主要评估。split ID 和所有留出范围在看模型结果前封存，具体基地和日期须由获授权盘点决定，不在本文猜测基地 ID。

1. **时间主测试 T**：在训练基地上的不同采样单元组取连续较早时段 train、随后时段 validation、最后时段 independent test，切点由采集日历预注册。跨切点组整体隔离或隔离到 quarantine，不分拆；train/validation 不含 test 组。无法形成足够独立单位则时间泛化不可评估。
2. **基地外测试 B**：事先指定完全不出现在 train/validation 的 canonical base_id（不少于一个只是设计需要，样本充分性另经 Owner 决定），其所有会话/样方组进入独立 base holdout。基地缺权威 identity 时隔离，不按名称猜测。B 与 T 都一次性封存，不能在看 T 后选择 B。
3. **范围外挑战 O**：指定从未用于 train/validation 的品种、设备或角度类别，形成 independent challenge 子集。与 B/T 按互斥优先规则 B→O→T 分配，每行只计一次总体指标，同时保留全部属性供分层；无法收集某类别则明确 `NOT_EVALUABLE`，不宣称范围外鲁棒。
4. **未来 cross-season/rolling-time/base leaveout**：若与正式产量任务联动，另经授权设计跨产季、滚动时间和基地留出；不绕过 AGENTS 的预测模型验证要求。Leave-one-base-out 仅在非测试开发数据运行，不能把多次看过的 holdout fold 再称盲测。历史 V0.15 EXPOSED_OOT 只可能在新授权下做 exposed comparison，不能用于本次未授权读取或新盲测。

全部 split 必须记录 canonical base/season/date/variety、遮挡（按批准定义）、光照、设备、角度、in/out-of-training-support 分层的候选数、已复核数、可计算数、失败数和样本独立组数。主指标总体之外，逐层报告同一指标和覆盖率；空层、未知层和缺标签层的状态为 `NOT_EVALUABLE`，数值 null，不删除它们掩盖范围不足。最低层样本数、区间精度及允许的 unknown 比例由 Owner 预注册，未决定不得宣称验收达标。

## 5. 指标定义、匹配与报告

### A 检测与计数

检测使用同一图片、同一批准 class 的预测框与 GT 框做一对一匹配，按置信度降序，以 evaluator 规定的 IoU 和 ignore/crowd 规则匹配尚未占用的 GT；重复检出为 FP，漏检为 FN。操作点 Precision=`TP/(TP+FP)`、Recall=`TP/(TP+FN)`，置信阈值、NMS 和匹配 IoU（操作点先固定为 0.50）在 validation 锁定后用于 test。无预测时 precision 分母为零必须为 null；有 GT 的 recall 可为 0。无 GT 时 recall 为 null，另外报告空图误检数。

报告 COCO bbox mAP@0.50 和 mAP@0.50:0.95（IoU=0.50 至 0.95、步长 0.05，101 个 recall 位置插值；category 平均只包括预定义且有可评估 GT 的类别，并列出不可评估类）。mAP 是置信度排序的 PR 曲线积分/插值，不能只拿已阈值化 P/R 代替；AP evaluator 的最低保留 score 与上述操作点阈值分开登记，并在 test 前锁定，不能按测试结果裁掉低分预测。标准报告固定 `maxDets=100` 的 COCO 口径；密集果串另报告 >100 GT 图像数量与截断率，若另用更大 maxDets 必须预注册并单独命名，不能冒称标准 COCO 指标。evaluator 实现/版本、标注坐标口径、尺度和 ignore 规则需绑定 hash；本轮未安装或运行 COCO evaluator。

每图计数 `c_i` 为人工复核可见果实数，预测 `ĉ_i` 为锁定框/实例策略产生的同范围个数。`MAE=sum(|ĉ_i-c_i|)/n`，`Bias=sum(ĉ_i-c_i)/n`，单位为 `visible_fruit_per_image`；正 Bias 表示过计。记录 signed error、遮挡/小目标/高密度分层误差、空图 FP 与无法计数比例。n=0 返回 `NOT_EVALUABLE/null`；缺标注/推理失败不默认为 0，另报排除原因及成功覆盖率。可另报每 session 聚合，但无跨视角对应和重识别时不得汇总成植株实际果数或 kg。

### B 实例分割

同一批准图像/label scope 比较 A 和 B，报告 COCO mask mAP@0.50、mAP@0.50:0.95（mask IoU、一对一同 class 匹配，保留标准 maxDets 口径）、上述可见计数 MAE/Bias 和遮挡/密度分层。报告额外 mask 标注工时、复核 disagreement、训练/推理资源、无法界定实例边界比例。分割不能推断完全遮挡果实；精度收益必须来自 matched holdout 的成对误差和完整失败分母，不能比较两份不同难度测试集。

### C 成熟分类/分割

在批准 label version 下输出混淆矩阵：行是真实批准成熟类别与 `UNKNOWN`，列是预测类别、`UNKNOWN` 与独立 `ABSTAIN`。`UNKNOWN` 表示参考无法归类，`ABSTAIN` 表示模型拒判；二者不能悄悄分配到成熟类别。每类 Recall=`TP/(TP+FN)`，其中 ABSTAIN/UNKNOWN 预测在已知 GT 类计入 FN；报告每类支持数、macro recall 可计算类列表、unknown/abstain 率及按品种/光照/设备的矩阵。无某类 GT 支持时该类 recall=null。

逐果分类分别报告人工 GT crop 上的分类表现，以及从检测到分级的端到端表现（漏检属于端到端失败）；不以 GT crop 结果冒充可部署结果。成熟像素分割另需预注册 pixel IoU/Dice、像素 ignore 规则和目标实例归属；它不自动代表成熟果数或采摘重量。未知标签比例过高/人工一致性不足按 Owner 门槛停止，不通过合并类别制造高分。

### D 视觉观测的独立增益

比较角色仅为本研究协议的本地角色，不复用 V0.15 冻结 M1 的模型身份。冻结 AREA_COMPARATOR 为原面积驱动预测的已保存、已授权只读快照，保留 run/source/model/input/result hashes；VISION_CANDIDATE 是未来独立 research 实验的视觉辅助候选，不覆盖 AREA_COMPARATOR 或生产 run、不改 Harvest State。两者必须匹配完全相同的 canonical base/season、forecast origin/cutoff、D1..DH target dates、scope 和 `kg` 单位，使用同一独立参考 rowset。按 VisionObservation available_at 过滤视觉特征；采样面积/覆盖率、拍摄频率、品种/树龄、称重口径和延迟必须有独立 authority，训练中的 count→weight 映射仅在 train 校准，validation 选策略，test 不拟合。

独立参考 kg 必须来自已授权称重来源、经复核的计量/采收边界和来源可用时间；不能来自 AREA_COMPARATOR/VISION_CANDIDATE 输出、检测数量或假设单果重量。各 reference row 有 measured_at/available_at/source hash，标签可在未来目标结束后得到，但两组预测须先 seal，再由独立保管者释放标签评分。不能用现有 source hash 自动宣称真实称重或 strict PIT 已证实。

在 matched common rowset 报告 MAE kg、Bias kg、WAPE=`sum(|prediction-actual|)/sum(actual)`、同 origin/window 累计绝对误差，以及成对 delta `error_VISION_CANDIDATE-error_AREA_COMPARATOR`。WAPE 分母为 0 时 null，不过滤零总量行另算“改善”；逐日/窗口、base/date/variety 误差与排除/缺图覆盖率分开报。common rowset之外 AREA_COMPARATOR 可用而 VISION_CANDIDATE 缺图的情况须列明，防止选择容易样本制造增益。预测对象若没有基地/日期/重量口径对应，则 `NOT_EVALUABLE`。

主增益门槛、容许 Bias、最差分层退化和覆盖率 Owner 待决定；未取得独立 kg/reference 或 matched baseline，不得报告视觉改善产量预测。测量不确定性和合理区间按独立 session/base/date group 成对 bootstrap 或其他预注册 group 方法评估，方法、seed 和重采样次数预注册，不按图像 IID bootstrap 掩盖相关性。区间不是生产精度保证。

## 6. 资源与复现清单

资源只做计划，本轮没有实测耗时/显存/成本。A 的 box 标注、B 的 mask、C 的成熟一致性复核、D 的采样/独立称重均需分别记录人工工时与拒标/改标率。未来训练报告 GPU/CPU 类型、显存/RAM 峰值、图像尺寸、batch、epoch/步数、参数规模、所有搜索次数、总 GPU/CPU 小时、存储字节和费用来源。推理在预注册设备上记录 warmup、batch、分辨率、端到端是否含预处理/后处理、p50/p95 latency、images/sec、内存和失败率；重复测量方法及样本数先冻结。只测单图/单设备不能宣称移动或生产可部署。

最低留存产物：授权与预注册、schema/label/annotation version、原始资产和 manifest source hashes、近重复审查/连通 group/split hashes、PIT cutoff 与 availability 证据、baseline snapshot/run/result/model hashes、reference measurement hashes、代码 SHA、依赖/镜像锁、seed、config hash、train-only fit artifact hash、每次 weight/model hash、validation 选择日志、test prediction seal、曝光/访问日志、evaluator hash、逐记录 errors、分层/资源/负面结果、审批和 gate 决定。缺产物不能补造 hash 或报告 PASS；将真实内容缺失标记为 blocked/pending。

## 7. 停止条件与阶段清单

立即停止依赖实验：权限/来源不能核实、身份无法解析、标签未批准/不可一致复核、duplicate/group 跨 split、时间链不合法或 cutoff 后特征、test 已暴露或被用于调参、人工 GT 与模型输出混淆、资源预算超出、独立测试覆盖不足、无独立 kg/reference、复现产物缺失。保留拒绝、隔离和失败日志，说明哪个 gate 失败。测试数据不足时仅报告 `ENGINEERING_PREPARATION_ONLY`；不得给出真实准确率或模型开发完成结论。

| 阶段 | 本轮状态 |
| --- | --- |
| 独立协议、数据契约、synthetic manifest、离线 validator 与 pytest | 已具备工程准备；实际运行结果由 R1 验证记录报告 |
| 训练器、完整 evaluator、资产近重复检测、独立 test escrow、视觉预测/重量关联 | 已设计但未实现 |
| 获授权真实图像、复核框/mask/成熟标签、未曝光独立测试、采样覆盖与独立称重 | 缺少真实数据，未访问 |
| 业务目标/观察单位/标签等级/指标门槛/分层样本量/设备与预算 | 需要 Owner 确认 |
| 采集/下载/上传、标注操作、预训练权重、训练/微调/真实评分、未来系统接口或数据库接入 | 后续需单独开发与数据授权，本轮未执行 |

结束于技术准备。下一步推荐 Owner 审核单图可见果检测/计数的数据和标签合同，并授权小规模、跨会话/日期/基地的采集与标注盘点；完成后再判断训练候选和足够独立测试条件。本轮不创建 PR、不 Ready、不 Merge、不 Tag、不 Release、不 Deploy，等待独立审核与下一次授权。
