# 蓝莓视觉 R1 最小离线工程

本目录只完成版本化元数据契约、模拟 fixture 与校验工程准备。没有真实图像、训练标签、独立测试集、算法准确率或重量标定。本工具没有图像、视频、网络、数据库或模型调用，不会修改生产预测与输入 manifest。

`fixtures/synthetic_manifest.json` 顶层和每条记录均明确 `SYNTHETIC=true`。它包含 train、validation、test、out_of_domain 与 unassigned 各一条，最后一条缺失数量，保留 `object_count=null` 与原因。所有名称、身份、标签、相机、标注、审核与权限引用均为虚构。`asset_hash` 是生成脚本中的虚构说明文本的 SHA256，**不是图像字节 hash**；`image_files_present=false`。没有生成或读取图片。候选标签 `SYNTHETIC_candidate_fruit` 不是业务成熟等级标准。

## 运行

从仓库根目录，使用已有 Python 3.12 与 Pydantic v2：

```bash
python -m research.blueberry_vision.validate_manifest research/blueberry_vision/fixtures/synthetic_manifest.json --json
python -m research.blueberry_vision.validate_manifest research/blueberry_vision/fixtures/synthetic_manifest.json --mode experiment --json
python -m pytest research/blueberry_vision/tests -q
ruff check research/blueberry_vision
ruff format --check research/blueberry_vision
mypy --explicit-package-bases research/blueberry_vision
```

第一条应退出 0；第二条应退出 2 并报告 synthetic 不能用于真实实验。这是预期门禁结果，不能写成真实算法失败或准确率。测试只使用虚构 JSON 与内存 mutation；其中模拟 `approved` 的负向/准入案例也是 fabricated metadata，没有真实图像或授权证据。

`--mode contract` 为默认：检查完整性、版本、时间、权限声明、重复与 split 隔离，允许 unassigned 显式缺标注。`--mode experiment` 在相同规则上要求真实观测、图像存在声明、三个主要 split、已批准标签定义、reviewed 标注与已解析身份。它只是未来实验的**元数据准入检查**；退出 0 不等于授权已经核实、训练已经获准、图像可读、覆盖充分或实验验收通过。当前 synthetic 永远无法通过 experiment 模式。

一个 experiment manifest 对应一个任务与 run：train/validation/test/out_of_domain 的 `task_kind` 和 `label_definition_version` 必须一致；不同 annotation version 可以使用，但均需绑定同一 label definition。混用任务或标签定义分别返回 `EXPERIMENT_MULTIPLE_TASKS` / `EXPERIMENT_MULTIPLE_LABEL_DEFINITIONS`，不能用检测训练集加成熟分类测试集满足三个 split。不同候选任务分开 manifest；contract 模式仍保留多任务、多版本的元数据表达能力。

有效输入退出 0；I/O、UTF-8、JSON、契约与语义错误退出 2。`--json` 输出 `valid/mode/errors/summary`，错误只包含稳定 `code` 和 JSON Pointer `path`，不输出输入行、值或异常详情。JSON 拒绝重复键、NaN 与 Infinity；严格类型拒绝字符串数字和将 bool 当数量。CLI 只读取显式传入的 JSON 文件。

## 契约与字段语义

`contracts.py` 的 Pydantic 模型是契约唯一生成源，`schemas/vision_observation.schema.json` 与 `schemas/vision_manifest.schema.json` 是机器可读 JSON Schema。测试核对两者完全一致。CLI 使用固定版本 Pydantic 模型及下列语义规则，**不是任意 JSON Schema 的通用验证器**；仅使用外部 Schema 引擎不会自动执行 split、授权、hash 与时间关系等跨字段规则。需要再生成时运行：

```bash
python -m research.blueberry_vision.generate_artifacts
```

生成脚本仅更新本目录两个 Schema 与 synthetic manifest；它不生成图片、不计算真实图像 hash、不接触业务数据。当前版本为 `blueberry-vision-observation/1.0.0` 与 `blueberry-vision-manifest/1.0.0`，不是正式产品版本。

所有 observation 字段均 required，包括可为 null 的字段；漏字段不能与显式 null 等同。所有层级禁止额外字段。以下约束由 CLI 执行：

| 数据部分 | 约束 |
| --- | --- |
| 身份 | `base_identity.status=resolved` 必须同时有 canonical `base_id` 与 `authority_ref`；unresolved 必须无 `base_id/authority_ref` 并有原因。工具只校验声明形态，不查主数据、更不通过名称推断。`sampling_unit_id` 必须在 manifest 范围内使用全局稳定身份。 |
| 时间 | 时区必须明确，按 UTC 比较 `observed_at <= asset_available_at <= available_at`。标注和模型输出也不能晚于 record 可用时间，或早于输入可用时间。record 不能超过 `as_of_cutoff` 或其 split cutoff；split cutoff 不能超过 as-of。时间保留原字符串，不自动改写。拒绝未知偏移 `-00:00`、非法日期/偏移、闰秒以及超出可比较 UTC 范围的值。 |
| 来源 | synthetic 仅能声明 `synthetic_only`；真实观测与模型输出必须声明 `approved`、非空 evidence 引用、用途与有效期。权限必须覆盖 record 可用时刻和 as-of 使用时刻，有效期为 `[granted_at, expires_at)`。pending/denied 拒绝。工具**不能验证批准者、证据内容、法律授权真实性或访问权限**。 |
| 版本 | annotation 与 label definitions 在 manifest 注册、相互绑定，任务类型与所有对象类名匹配；reviewed 必须有版本及标注可用时间。候选类名不自动成为批准标准。 |
| 数量 | 只能使用 `fruit_count`，非负严格整数或明确 null+原因。已知数量要对应逐果 `class_labels`，有 objects 时其长度也一致；观测零需要 completed/reviewed 标注与空列表。预测零可作为模型输出保留，但永不成为 ground truth。数量缺失不能转零；无标注 unassigned 不参与训练/评估。没有 kg 字段或换算。 |
| 类型 | `real_observation`、`synthetic_observation`、`model_prediction` 不得混为一个 cohort；预测必须有 model version/hash、generated time 与 provenance，且只能 unassigned，不能当训练/评估 ground truth。 |
| 去重 | `observation_id/image_id/asset_hash` 全 manifest 唯一；同一 exact hash 即使同 split 也拒绝。near-duplicate group、capture session、sampling unit 构成的连通分组不能跨 train/validation/test/out_of_domain；包括通过 unassigned 记录连接的组。unassigned 本身不参与训练；以后分配 split 时必须重新校验。同基地不同 unit 可以跨 split，基地留出协议需单独执行。 |
| 近重复审核 | 必须声明覆盖 entire_manifest 的 completed review、method/evidence、完成时间，且不能早于所有 asset 可用时间或晚于 as-of。synthetic 审核仅为声明。工具不打开图片、不计算相似度，completed **不证明**实际无近重复帧。 |
| hash | asset/model/record hash 均为小写 64 位 SHA256 hex。record hash 对输入 record 去掉自身 `record_hash` 后，`json.dumps(sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)` 编码为 UTF-8 后计算 SHA256；不自动补 hash 或修正数据。`1` 与 `1.0`、时间字符串差异会改变 hash。此 hash 是完整性检查，不是数字签名或真实性证明。 |

设备、角度/距离、光照、品种与遮挡都有明确元数据字段；未知值使用 null 或 unknown，不猜测。当前 fixture 的多样化值只是门禁演示，不能证明实际跨日期、基地、品种、光照或设备的覆盖。

## 支持范围与未完成工程

`objects` 可携带逐对象 `bbox_xyxy` 和单 polygon。检测框检查长度、有限坐标、顺序、图像边界；object ID 在图内唯一，class labels 与对象顺序一致。contract 可以表达只有人工计数的观测（objects=null）；experiment 中检测任务必须有 objects 和每个目标框。

polygon 仅做有限坐标、至少三个不同顶点及图像边界检查。尚未实现孔洞、多 polygon、RLE、遮挡/可见部分标注语义、自交检测、面积与拓扑、COCO 转换，因此 experiment 模式对 instance_segmentation 明确返回 `EXPERIMENT_SEGMENTATION_ADAPTER_NOT_IMPLEMENTED`。这不是可直接训练的完整分割适配器。成熟任务的 class_labels 表示逐果类别；仅有整图标签的分类任务尚需另立契约或适配器。yield_proxy 仅为候选数量代理，缺少独立称重/覆盖/采样标定，experiment 返回 `EXPERIMENT_WEIGHT_CALIBRATION_NOT_IMPLEMENTED`。

experiment 不计算 Precision/Recall/mAP、计数 MAE/Bias、混淆矩阵或重量预测误差，也不生成训练数据、split 或模型权重。不自动检查基地/日期留出、各分层样本量、标注者一致性、图像实际质量、预测快照对齐与独立称重。它们必须按独立实验规范获得真实授权与证据，另行开发、审查并执行；不得由本工具 PASS 推导出来。

实际离线运行证据与后续数据、业务、训练及独立评估门禁见仓库 R1 研发报告与实验规范。本轮只完成技术准备，不完成视觉模型研发。
