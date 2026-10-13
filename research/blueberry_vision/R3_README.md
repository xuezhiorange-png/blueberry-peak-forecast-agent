# R3 真实图像研究链路

工程验收通过；真实准确率 **NOT_EVALUABLE**。本轮合法接入8张公开真实图片，
两套冻结R2算法完成16次推理。公开研究数据的100个候选框来自半自动标注，
全部27份原XML中的675个polygon均为semi-auto，没有可靠人工复核证明。
候选框可编辑、转换、审核；不能作为准确率GT，也不代表公司果园表现。

独立入口 `python -m research.blueberry_vision.r3.cli`。R1/R2所有已有文件保持
原字节；外部benchmark契约独立版本化，不放宽R1真实实验门禁。

## 环境与离线工程验收

Python3.12.14，CPU；独立版本依赖包含Pillow12.3.0、NumPy2.4.6和可选正式
COCO evaluator pycocotools2.0.11。许可证与源文本在evidence/r3/dependency_review.json。
没有训练框架、GPU、预训练权重或生产数据库依赖。

```bash
python -m pip install -r research/blueberry_vision/requirements-r3.txt
python -m research.blueberry_vision.r3.cli run-r3-acceptance --output /tmp/r3-engineering-001 --coco
python -m pytest research/blueberry_vision/tests research/blueberry_vision/newtests -q
ruff check research/blueberry_vision
ruff format --check research/blueberry_vision
mypy --explicit-package-bases research/blueberry_vision
python -m research.blueberry_vision.cli verify-artifacts --manifest research/blueberry_vision/artifact_manifest.json
python -m research.blueberry_vision.r3.cli verify-artifacts --manifest research/blueberry_vision/evidence/r3/artifact_manifest.json --root .
```

实际结果：原R1/R2 271项＋R3 363项＝634项通过，0跳过；Ruff/format/mypy通过；
默认一键验收真实重跑两组测试并完成13项工程检查。其3张夹具明确标为
SYNTHETIC_ENGINEERING，仅用于工程回归；与公开真实试验分开。

## 小规模公开图像复现

以下下载为显式网络操作，CI不执行。使用固定来源和小规模选择，拒绝未知许可、
整包超限、路径越界、无效Range及CRC/尺寸异常。未授权公司图像不进入流程。
每个输出目录必须新建，不覆盖历史试验。

```bash
python -m research.blueberry_vision.r3.cli discover-sources --download-commons /tmp/r3-commons-001 --output /tmp/r3-commons-review.json
python -m research.blueberry_vision.r3.cli discover-sources --download-quality /tmp/r3-quality-001 --output /tmp/r3-quality-review.json
python -m research.blueberry_vision.r3.cli prepare-public-pilot --commons-root /tmp/r3-commons-001 --quality-root /tmp/r3-quality-001 --registry research/blueberry_vision/evidence/r3/data_source_registry.json --supplement research/blueberry_vision/evidence/r3/source_registry_supplement_v2.json --output /tmp/r3-assets-001
python -m research.blueberry_vision.r3.cli import-images --data-root /tmp/r3-assets-001 --source-index /tmp/r3-assets-001/source_index.json --registry /tmp/r3-assets-001/source_registry.json --output /tmp/r3-import-001
python -m research.blueberry_vision.r3.cli audit-images --manifest /tmp/r3-import-001/dataset_manifest.json --data-root /tmp/r3-assets-001 --output /tmp/r3-quality-report.json
python -m research.blueberry_vision.r3.cli find-near-duplicates --manifest /tmp/r3-import-001/dataset_manifest.json --data-root /tmp/r3-assets-001 --threshold 6 --output /tmp/r3-duplicates.json
python -m research.blueberry_vision.r3.cli freeze-baselines --output /tmp/r3-freeze.json
python -m research.blueberry_vision.r3.cli run-real-inference --manifest /tmp/r3-import-001/dataset_manifest.json --data-root /tmp/r3-assets-001 --freeze /tmp/r3-freeze.json --model A --ledger /tmp/r3-ledger-A --output /tmp/r3-prediction-A.json
python -m research.blueberry_vision.r3.cli run-real-inference --manifest /tmp/r3-import-001/dataset_manifest.json --data-root /tmp/r3-assets-001 --freeze /tmp/r3-freeze.json --model B --ledger /tmp/r3-ledger-B --output /tmp/r3-prediction-B.json
```

本轮原图片共41,817,510bytes；其中Quality获取网络36,402,648bytes（含小型
目录与标注），未取完整GB archive。实际规范化JPEG/PNG输入合计15,012,162bytes。
Quality原JPEG编码包含MPO双帧，独立适配器显式选择frame0/orientation1，输出
1500×1000 PNG，保留原图hash和0.25缩放关系。R2安全解码器没有放宽。

实际manifest、来源索引、许可、原图/派生hash、质量与去重报告、冻结配置、逐图
推理数量和曝光ledger在 `evidence/r3/`。完整原图不提交Git；许可允许的480px
预览与所有逐图预测框保存一次于公开HTML，避免重复提交大JSON。

## 实际架构与审核入口

| 模块 | 已实现职责 |
| --- | --- |
| sources / public_pilot | 正式来源/许可核验、受控Range、原始与派生身份、资产清单 |
| contracts / ingestion | 独立外部契约、受控目录读取、hash/尺寸/EXIF、辅助质量指标 |
| dedup / splits | dHash候选及人工状态、连通组/原图家族隔离、研究seal和曝光日志 |
| annotations | 候选规则、COCO转换、版本历史、双标差异、仲裁；无自动认证 |
| evaluation | 原R2像素检测/NumPy模型、冻结/重加载、独立计数/box/AP/可选COCO |
| report | 实际数据HTML、模型切换、GT/候选/预测图层、编辑/草稿导出及覆盖图 |
| cli / acceptance | 统一命令、CPU端到端夹具和安全artifact校验 |

打开 [real_review.html](examples/r3/real_review.html)。源码不启动生产服务；页面
不上传图片、不访问外部视觉API。来源分为PUBLIC_EXTERNAL_BENCHMARK、
AUTHORIZED_ORCHARD_PILOT、SYNTHETIC_ENGINEERING，禁止混合评分。
25框待审草稿实际复制/导出经Chromium和Python snapshot/hash校验；GT和指标仍为null。

完整标注/split/seal/evaluate/render命令见 [CLI说明](r3/docs/cli.md)。合法导入
必须提供图片ID映射、候选类别映射、版本及来源证据。已知DRAFT、半自动未审、
PENDING来源不会因格式转换升级为可信GT。缺失与真正零目标分开。
EXIF非默认/未知坐标必须提供明确规范化框架证据，不能猜测翻转框。

所有8张图片处于外部TEST试验范围；没有R3真实train/validation或真实模型选择。
公开标签状态EXPOSED_PUBLIC_BENCHMARK；未知基地、日期、品种和场景保持未知。
目前test seal返回NOT_EVALUABLE及具体GT原因。研究seal校验integrity和顺序，
没有独立访问控制；算法配置及预测必须先固定，之后才能记录GT评分读取。

## 结果、CI与后续门禁

两套原R2算法未调参、未重训：RGB阈值＋4连通域；CPU NumPy logistic像素分类。
模型B原artifact SHA256为
`b685ff32fac8542e3f50bbbb5f5a1b09d2319114ce14af17078de06ac9482b10`。
它们的原始候选数量差异很大，不能依据缺失GT的结果选择优胜模型。

正式COCO goldens已实际运行；真实COCO评估未准入。RESEARCH_AP50与
COCO_MAP50/COCO_MAP50_95分开；真实Precision/Recall/MAE/Bias均NOT_EVALUABLE。
参见 [实际验收](evidence/r3/final_acceptance.md)、[限制](evidence/r3/known_limitations.md)
和 [独立工程审查](evidence/r3/independent_review.json)。

新R3研究workflow独立运行634测试、Ruff、mypy、CPU一键工程夹具及新旧artifact
校验，不下载真实资料/权重，不读取私有数据。CI结论必须绑定最终HEAD；最终
远端提交、stacked Draft PR及CI由任务回执与PR记录。R2父PR #719保持不变。

下一步需要实际两名独立人工逐果审核、分歧仲裁与证据，确认候选可见计数定义，
才能封存合格外部参考并评价冻结R2模型。公司果园试验还需数据所有者授权、
采集/品种/采样身份、真实独立留出与预算。计数→kg另需独立称重标定授权。
本轮没有生产部署、经营决策、正式模型批准或Harvest State/预测结果改动。
