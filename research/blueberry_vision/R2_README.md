# 蓝莓视觉 R2：可运行的离线检测与计数研究链路

TASK_ID=`BLUEBERRY_VISION_R2_OFFLINE_DETECTION_COUNTING_PIPELINE`。
本轮实现 PNG/JPEG 读取、合成 PNG 与逐果参考、两套像素检测基线、CPU 实际训练与重加载、
独立检测/计数评价、COCO detection 转换、可视化报告及候选标注草稿导出。
所有运行样本、参考与训练均为 **SYNTHETIC**。代码可以运行，不代表已经通过真实蓝莓识别验收。

**SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY**

本文件是 R2 说明；原 [README.md](README.md) 与 R1 数据契约、Schema、实验门禁保持原版本。
R1 来源 HEAD 为 `88f052405d98210864d4f4d56b0da4bb62d5bd12`，研发分支为
`research/blueberry-vision-r2-offline-detection-counting`。恢复云端工作先读取
[R2_PROGRESS.md](R2_PROGRESS.md) 并核实远端真实 HEAD，不回退或覆盖已提交成果。

## 环境与一次完整执行

从仓库根目录运行。需要 Python 3.12，核心链路仅依赖 CPU，不需要 GPU、数据库、登录、
外部服务、真实图像数据集或预训练权重。研发依赖独立安装，不更改应用的 `pyproject.toml/uv.lock`。

```bash
python3.12 -m venv /tmp/blueberry-r2-env
/tmp/blueberry-r2-env/bin/python -m pip install -r research/blueberry_vision/requirements-r2.txt
/tmp/blueberry-r2-env/bin/python -m research.blueberry_vision.cli run-demo --output /tmp/blueberry-r2-full-001 --seed 20261013 --images-per-split 14
/tmp/blueberry-r2-env/bin/python -m research.blueberry_vision.cli verify-artifacts --manifest /tmp/blueberry-r2-full-001/artifact_manifest.json
```

`run-demo` 实际生成 56 张 PNG 和训练 mask，验证资产，执行传统像素检测，在训练/评价前固化默认配置与代码 hash，训练 NumPy
轻量模型，保存并重新加载模型，执行 validation 推理，再执行 test/OOD 推理与
独立评价。最后生成双基线比较、COCO 往返、HTML/Markdown/JSON 和 PNG 叠加图。
不存在“发现示例文件后跳过算法”的捷径。打开 `/tmp/blueberry-r2-full-001/report/report.html`
即可审核；HTML 自包含，可在允许 file URL 的浏览器打开。当前云端 Chromium 的 file URL
受管理员策略限制，浏览器验收改用 Playwright 完全截获的内存 localhost 响应；无启动服务
或部署，记录见 `evidence/r2/browser_review.json`。

输出位置必须新建。已有实验、模型、报告和 JSON 不被覆盖；再次运行需指定新目录。
每次产生按 dataset/config/model hash 派生的稳定 run ID，不把主机名、临时路径或时间戳
混入算法的 canonical hash。同 seed、配置与锁定依赖环境可重复生成同样图像及结果；
跨 Pillow 编码器或 NumPy/BLAS 构建的逐字节一致性不作无条件保证。

## 分步 CLI

以下命令独立于上述完整执行，使用另一组新输出路径。`--output` 对生成、训练和报告为
目录，对推理、评价及格式转换为 JSON 文件。`validate-assets` 的 JSON 输出可选。

```bash
python -m research.blueberry_vision.cli generate-demo --output /tmp/blueberry-r2-dataset-001 --seed 20261013 --images-per-split 14
python -m research.blueberry_vision.cli validate-assets --dataset /tmp/blueberry-r2-dataset-001/dataset_manifest.json --data-root /tmp/blueberry-r2-dataset-001 --output /tmp/blueberry-r2-assets-001.json
python -m research.blueberry_vision.cli run-baseline --dataset /tmp/blueberry-r2-dataset-001/dataset_manifest.json --data-root /tmp/blueberry-r2-dataset-001 --splits test out_of_domain --config research/blueberry_vision/evidence/r2/classical_config.json --output /tmp/blueberry-r2-baseline-001.json
python -m research.blueberry_vision.cli train-synthetic --dataset /tmp/blueberry-r2-dataset-001/dataset_manifest.json --data-root /tmp/blueberry-r2-dataset-001 --config research/blueberry_vision/evidence/r2/training_config.json --output /tmp/blueberry-r2-model-001
python -m research.blueberry_vision.cli predict-synthetic --dataset /tmp/blueberry-r2-dataset-001/dataset_manifest.json --data-root /tmp/blueberry-r2-dataset-001 --model /tmp/blueberry-r2-model-001/model.json --config research/blueberry_vision/evidence/r2/trained_inference_config.json --splits test out_of_domain --output /tmp/blueberry-r2-candidate-001.json
python -m research.blueberry_vision.cli evaluate --dataset /tmp/blueberry-r2-dataset-001/dataset_manifest.json --predictions /tmp/blueberry-r2-baseline-001.json --splits test out_of_domain --output /tmp/blueberry-r2-baseline-eval-001.json
python -m research.blueberry_vision.cli evaluate --dataset /tmp/blueberry-r2-dataset-001/dataset_manifest.json --predictions /tmp/blueberry-r2-candidate-001.json --splits test out_of_domain --output /tmp/blueberry-r2-candidate-eval-001.json
python -m research.blueberry_vision.cli render-report --dataset /tmp/blueberry-r2-dataset-001/dataset_manifest.json --data-root /tmp/blueberry-r2-dataset-001 --predictions /tmp/blueberry-r2-baseline-001.json /tmp/blueberry-r2-candidate-001.json --evaluations /tmp/blueberry-r2-baseline-eval-001.json /tmp/blueberry-r2-candidate-eval-001.json --output /tmp/blueberry-r2-review-001
python -m research.blueberry_vision.cli coco-export --input /tmp/blueberry-r2-dataset-001/dataset_manifest.json --output /tmp/blueberry-r2-coco-001.json
python -m research.blueberry_vision.cli coco-import --input /tmp/blueberry-r2-coco-001.json --output /tmp/blueberry-r2-coco-import-001.json
```

分步命令中的 `python` 应指向上面的独立 venv。`run-baseline` 和 `predict-synthetic` 的默认
split 为 test+out_of_domain；也支持 train/validation 独立推理。推理只消费图像字节和
冻结配置/模型，不能读取 GT、训练 mask、seed、文件编号或参考数量查答案。
`train-synthetic` 自动且仅消费 train；传入真实来源会拒绝。
`evaluate` 默认评价 test+out_of_domain，`--config` 可指定版本化 evaluator 配置。
`render-report` 的 predictions/evaluations 必须一一对应并绑定同一个 dataset、配置与评价范围。

## 实际模块结构

| 文件 | 实际职责 |
| --- | --- |
| `r2_common.py` | 复用 R1 canonical JSON/hash 规则，strict JSON 读取、新建制品、split hash |
| `r2_contracts.py`、`schemas/r2_dataset.schema.json` | 版本化 synthetic 资产/参考契约及几何、时间、来源和 split 校验 |
| `assets.py` | bounded 原始 PNG/JPEG 读取、SHA256、EXIF orientation、RGB 预处理与真实尺寸核验 |
| `synthetic.py` | 真实 PNG、ownership-based 可见参考、ignore 区域、训练 mask、独立 seed 与 manifest |
| `classical.py` | RGB 颜色区域、4 连通区域、面积/填充率过滤、bbox 与实际计数 |
| `trainable.py` | 十维颜色特征、NumPy logistic 参数拟合、JSON 模型保存/重加载、像素推理及组件计数 |
| `evaluator.py` | 独立 IoU/匹配、Precision/Recall/F1、research AP50、计数/分层/失败结果和对照 |
| `annotations.py` | 受控 COCO detection、R1 几何适配、候选导入版本与来源保留 |
| `report.py`、`review_ui.html` | 来源绑定与指标复算、真正叠加图、纯离线审核和新候选草稿导出 |
| `cli.py` | 统一命令、完整闭环、稳定 run ID、制品清单及 hash 验证 |
| `tests/` | R1 回归、资产/算法/拟合/格式/指标/隔离/边界、手工 Golden、完整 CLI 与报告检查 |

## 图像契约、可见真值与隔离

R2 schema 为 `blueberry-vision-dataset/2.0.0`，不改写 R1
`blueberry-vision-observation/1.0.0` 的物理含义。每张图保存原始本地 asset ref、原始文件
SHA256、实际尺寸、EXIF/RGB preprocessing version/hash、observed_at/asset_available_at、
session、sampling unit、unresolved base identity、来源、annotation/label version 和 record hash。
路径仅是授权 data-root 内的研究引用，不成为公开 Web URL。loader 拒绝目录越界、symlink、
损坏图片、非 PNG/JPEG、异常文件体积、过大尺寸/像素及解压炸弹；原始图像不被改写。
默认资产限制 20 MB、25M decoded pixels、单边 8192；算法另限 4M input pixels。

生成器覆盖 14 类场景，train/validation/test/OOD 各 14 图，普通图 256×192，压力图
320×256。场景含稀疏/密集/接触、部分/高遮挡、叶枝、阴影/反光、不同大小/候选颜色、
边缘裁切、真正空图、蓝色非目标干扰和 120 果压力场景。
参考由最终逐像素 ownership 决定：完全隐藏的果实不计入；可见比例不足 0.15 或可见像素
少于 12 的对象进入 ignore 区域；符合阈值的对象有最终可见像素紧框和可见计数。
绘制数量、可见参考数量、隐藏数量与 ignored 数量分别保存。空图为真实合成零目标；
missing GT 仍为 null。完整语义见 [docs/r2_synthetic.md](docs/r2_synthetic.md)。

训练 mask 0=背景、255=计入参考的可见果实、128=ignore。训练消费 mask；推理接口没有
mask 或 GT 参数。来源在 manifest 和每条记录都保留 SYNTHETIC=true、synthetic_only。
会话、样本单位、模板组、近重复组、图片 hash 和独立生成 seed 不跨 split；不把增强图拆入
独立测试。通用渲染器、形状族与部分遮挡原型共享，OOD 只是模拟分布变化，不能宣称真实
基地/设备泛化或未见模板族留出。真实近重复识别仍是下一轮授权任务。

## 两套基线与实际拟合

Baseline A `rgb-connected-components/2.0.0` 计算 RGB 色差、blue-over-green、饱和度和
亮度区域，再进行 4 连通提取、面积及填充率过滤。每个区域产生一个 bbox，候选分数明确
为非概率颜色/形状分数。相接/重叠果实可能合成一个组件，真实漏计保留，不用 GT 修正计数。
这套轻量方法没有实现分水岭、实例分割或跟踪，不声称解决完全隐藏果实。

Baseline B `numpy-logistic-pixel/2.0.0` 从 synthetic train 图像和 mask 提取 RGB、通道
差值、乘积与 channel-range 共十维特征。每图分层采样上限 1200 像素，忽略 mask=128，
标准化后实际执行 80 次 logistic 梯度更新，L2=0.001、learning-rate=0.15。
权重、标准化参数、特征版本、训练身份与日志写入小型 JSON 模型，而不是 pickle 或固定
阈值伪模型。加载时验证 hash 和参数形态；未参与训练的图像独立进行像素推理，阈值 0.5
后使用相同连通区域后处理。像素概率未经真实田间校准，不应作为业务置信概率。
训练采样 seed 由配置记录，完整运行把该 seed 固定为 CLI seed；训练资源上限 250k 样本。

本轮参数使用 test 前预注册默认值，保留 validation 输出与 config/source/model hash。
没有按 test 误差调参或选模型。修改训练样本、标签或参数会改变拟合模型/输出，回归测试
同时验证损失变化、保存重加载和未见像素推理。没有 YOLO 训练、预训练权重或生产注册。

## 评价定义与本轮合成结果

相同图片、相同类别按照分数降序进行 IoU 一对一匹配，同一个 GT 最多匹配一次；重复预测
计 FP。默认 operating IoU=0.5。Precision/Recall/F1 按 TP/FP/FN 计算。
`bbox_ap50_research_all_points` 为固定 IoU=0.5 的 VOC all-points precision envelope
积分，**不是标准 COCO mAP，也没有 mAP50:95**。所有预测保留，maxDets=null，不截断压力图。
零分母和无可评价数据返回 null 与 reason，而不是假零误差。

计数单位为 `visible_fruit_per_image`；signed error=pred−GT，MAE=平均绝对误差，Bias=平均
signed error。忽略区域中 unmatched 预测可不计 detection FP，但仍进入原始预测数量与
计数误差。missing/failed 保留覆盖行及原因，不能当作 zero。分层按 density、occlusion、
lighting、size、domain、empty、scene type 从实际逐图结果重算；无样本分层为 NOT_EVALUABLE。
评价 hash 绑定 dataset/split/model/config/evaluator source/predictions；手工 Golden 独立
证明 IoU=1/3、AP=5/6、MAE=1/Bias=0 等。见 [docs/r2_evaluation.md](docs/r2_evaluation.md)。

以下摘要来自 `evidence/r2/` 固定 seed=20261013 的 56 图执行；评价范围为 test+OOD 共
28 图。每个 split 的全部原始曲线、逐图错误、分层与失败保存在 JSON 中。

| Synthetic-only metric | Baseline A | Baseline B |
| --- | ---: | ---: |
| Precision | 0.960699 | 0.959052 |
| Recall | 0.778761 | 0.787611 |
| F1 | 0.860215 | 0.864917 |
| Research bbox AP50 | 0.750849 | 0.762992 |
| Count MAE | 4.142857 | 3.928571 |
| Count Bias | −3.714286 | −3.500000 |
| TP / FP / FN | 440 / 18 / 125 | 445 / 19 / 120 |

B 在本组合成样例的总体 MAE 略低，precision 略低；OOD recall 相同且 B 增加一个 FP。
两者都明显漏计，不能据此选择真实生产模型。没有真实图像准确率、经营收益或 kg 标定证据。

## 报告、COCO 与候选标注

仓库公开示例位于 `examples/r2/`，完整本地审核页面为
[examples/r2/review/report.html](examples/r2/review/report.html)。页面读取本轮实际预测和
评估，自包含 JSON/dataURL，禁止联网；提供模型切换、GT/Prediction 开关、FP/FN/高误差/
失败/空图筛选及 source/config 摘要。PNG 有 GT+Prediction 对照、prediction-only 叠加、
全部错误图、场景 collage 和 scalar metrics 摘要。Markdown 只显示摘要，完整原始 evaluator
JSON 与 report.json 保留 AP 曲线及所有负面结果。报告在渲染前检查来源绑定并独立重算指标，
拒绝旧指标配新框。

候选编辑可从 immutable GT 建立新 draft，鼠标绘框、选择/删除、修改 candidate class，
导出新的 annotation draft JSON。不能覆盖 GT、伪造 reviewer 或升级 reviewed/approved。
零面积/越界框拒绝；没有 crypto.subtle 时明确 EXPORT_BLOCKED，不共用伪版本。
COCO 使用受控 provenance/source/version/hash 扩展；geometry xyxy↔xywh 往返保留对象数/
位置/类别。model_prediction 禁止作为 GT，mask/RLE/crowd 尚不支持。修改导入几何产生
candidate-import draft，而不是直接可训练数据。详情见 [docs/r2_review.md](docs/r2_review.md)。

## 测试、CI 与 GitHub 证据

```bash
python -m pytest research/blueberry_vision/tests -q
ruff check research/blueberry_vision
ruff format --check research/blueberry_vision
mypy --explicit-package-bases research/blueberry_vision
python -m research.blueberry_vision.validate_manifest research/blueberry_vision/fixtures/synthetic_manifest.json --mode experiment --json
```

最后一条必须退出 2，synthetic 无法通过 R1 真实实验准入；这是预期门禁结果。
`test_validator.py` 原 69 项完整保留并重新执行。研究测试包括机器 schema 一致性、手工
Golden、R1 固定 source hash、生产依赖文件不变、无 production/network imports、真实图像
解码、split 隔离、真实像素检测、实际拟合重加载、COCO 往返、report provenance 与完整 CLI。
模板 JavaScript 辅助函数测试在 Node 可用时执行；浏览器交互验收单独留存证据。

新 `.github/workflows/blueberry-vision-research.yml` 仅由 research 路径及本 workflow
变化触发，独立 Python3.12 CPU job，checkout PR head SHA、安装固定研发 requirements、
执行 research pytest/Ruff/format/mypy、小型完整 run-demo、artifact/hash 验证并上传 synthetic
制品。没有数据库 service、业务秘密、模型下载或生产服务连接。workflow 存在不代表远端
已通过；真实 exact-head run/job 结论以最终证据和 Draft PR 为准。既有主仓库 CI 未改写。

`evidence/r2/` 保存 environment、生成配置与 manifest、固定算法配置、model manifest/
model/log、两套原始 metrics/predictions、test/OOD/validation 明细、comparison 和各阶段
checkpoint。最终验收还记录实际测试/CI/制品 hash 与已知限制，不用文档替代执行证据。
阶段提交已逐步推送；以 GitHub 分支和最终回执 SHA 为持久化成果，临时 workspace 不作唯一来源。

## 依赖许可与下一轮门禁

固定版本见 `requirements-r2.txt`，实际安装包元数据见 `evidence/r2/environment.json`：
Pillow 12.3.0（MIT-CMU），NumPy 2.4.6（BSD-3-Clause/0BSD/MIT/Zlib/CC0-1.0 组合），
Pydantic 2.13.4、pytest 9.1.1、Ruff 0.15.18、mypy 2.1.0（MIT），
pytest-asyncio 1.4.0（Apache-2.0）。包声明不是本工具授予第三方数据/权重许可。
本轮公开图像均由源码生成，不使用下载的数据集、第三方预训练权重或公司私有资料。

真实图像下一轮须另行确认数据所有者及用途授权、保存期限与访问角色、canonical 身份来源、
采样单位/采集 protocol、candidate class/可见口径、人工双标与争议仲裁、近重复/会话隔离、
跨基地/日期/品种/设备的封存测试与业务验收阈值。参数和模型选择只能使用 train/validation。
需要 YOLO/实例分割/跟踪/真实成熟度标签时另立版本化适配和资源/许可审批。

视觉数量不等于采摘重量，颜色不等于业务成熟等级，图像训练不等于产量预测训练。
从数量到 kg 尚缺覆盖率、每果质量、遮挡及多视角重复校准、独立称重与时间/采收映射。
没有访问当前产季 actual；没有修改 Harvest State、冻结 V0.15 或 V0.16/V0.17/V0.18 证据、
正式预测记录、API/MCP/Dashboard 或数据库。Draft PR 供独立复审，未授权 Ready/Merge/
Tag/Release/Deploy。
