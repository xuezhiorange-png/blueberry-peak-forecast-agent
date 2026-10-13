# R3 真实蓝莓图像来源与许可核验

TASK_ID：`BLUEBERRY_VISION_R3_REAL_IMAGE_PILOT_AND_VALIDATION`

M1 首次检查点实际检索了公开来源，核验了 9 个来源条目，下载并用 R2 安全图片读取器解码了 4 张真实蓝莓照片，总计 **6,371,007 bytes**。照片属于 `PUBLIC_EXTERNAL_BENCHMARK`，不是公司基地数据，也不是 synthetic。它们没有合格逐果人工参考标注，因此可以运行真实像素推理，**不能计算真实识别准确率**。

版本化核验记录是 [data_source_registry.json](../../research/blueberry_vision/evidence/r3/data_source_registry.json)。该记录保存官方 API/页面、许可原文摘要、官方许可页 SHA256、检索结果摘要、Commons 修订号和实际图片 hash；不保存搜索结果中的图片，不把文章开放许可传递给原始数据。

## 实际检索及选择

检索入口包括 Zenodo 的三个蓝莓图像/检测查询、OpenAlex 的论文/数据索引、Figshare 公共检索、Mendeley Data 公共检索页面和 Wikimedia Commons 文件 API。OpenAlex 只用于发现正式来源；Figshare 本次前 15 条结果没有建立逐果图像资源；Mendeley 页面未提供可核验的逐果数据许可，尝试的公共 API 返回 404。它们均未触发图片下载。一个来源不适用不会阻断其他离线工程。

| 来源 | 发布者 / 许可 | 实际可核实内容 | 本轮处理 |
| --- | --- | --- | --- |
| [BlueberryDCM](https://zenodo.org/records/14002517) | Yuzhen Lu，Michigan State University；[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | 140 张 2022 年田间 RGB JPG；发布者说明 17,955 个人工 bbox，Blue/Unblue 与 visible/occluded，VIA/VOC/YOLO；107,267,412-byte archive | 许可声明已核实，用途受限。商业关联任务不能自行认定为非商业；**未下载**。需要确认本次用途符合 NC，或取得权利人许可。独立测试分组和本地标注质量仍未验证。 |
| [FlexiGroBots RGB Bush Detection](https://zenodo.org/records/7813238) | BioSense Institute 等；[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 2,000 张 1920×1080 PNG，塞尔维亚果园，Bush/Pole 标签；发布者按序列分 train 1490 / validation 200 / test 310 | 许可可核实，但目标是植株基部/杆，不能作为单果 GT。Images.zip 9,597,990,932 bytes，超过 pilot 上限；未下载。 |
| [Robust Object Detection… Experiments Code & Results](https://zenodo.org/records/14205417) | Kallol Roy，University of Tartu；Nesma Talaat Abbas Mahmoud；CC BY 4.0 | 请求原 record 10522314 后官方重定向到 14205417；47,212,026-byte 实验代码/results archive，描述链接外部 Roboflow 蓝莓数据 | **代码与结果 deposit 许可不能推定原图许可**。未下载 archive，原图 `LICENSE_UNVERIFIED`。 |
| [CRISP Fruit-Picking Teleoperated Dataset: BlueBerry](https://zenodo.org/records/6450413) | Claudio Coppola，Queen Mary University of London；CC BY 4.0 | RGB、触觉、运动学的采摘演示；两个 archive 分别约 10.6 GB、7.3 GB | 无可核实逐果 GT，超 pilot 范围；未下载。 |
| [Roboflow BlueBerryDetection v1](https://universe.roboflow.com/blueberrydetection/blueberrydetection/dataset/1) | 项目上传者 BlueberryDetection / Roboflow Universe | 页面描述 118 images and annotations，公开 train/validation/test；未找到明确图片许可证 | `LICENSE_UNVERIFIED`，未下载。页面写 open source 不等于许可允许本研究。 |
| [Blueberries-In-Pack.jpg](https://commons.wikimedia.org/wiki/File:Blueberries-In-Pack.jpg) | Evan-Amos；[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | 作者 own-work、self CC0；3200×2760；包装蓝莓 | 下载并解码；4,970,305 bytes；无 GT。 |
| [Blueberries on branch.jpg](https://commons.wikimedia.org/wiki/File:Blueberries_on_branch.jpg) | Jim Clark；[CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) | 枝上果串；Commons 保留 Flickr 来源及 2008 年许可复核；2043×2301 | 下载并解码；858,751 bytes；无 GT。 |
| [Blueberries ripening on branch.jpg](https://commons.wikimedia.org/wiki/File:Blueberries_ripening_on_branch.jpg) | mike epp；CC BY 2.0 | 枝上不同颜色外观；Commons 保留 Flickr 来源及许可复核；1600×1063 | 下载并解码；261,907 bytes；无 GT。颜色不是已批准成熟度标签。 |
| [Blueberries on the branches of a bush.jpg](https://commons.wikimedia.org/wiki/File:Blueberries_on_the_branches_of_a_bush.jpg) | Oleg Bor；[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 作者 own-work、self CC BY-SA；768×1024 | 下载并解码；280,044 bytes；无 GT。衍生图片需保留 BY-SA。 |

表格中的图片量及标注说明来自发布者，并不表示本轮已下载或逐图审核那些学术数据集。记录分开保留 `license_status`、`image_license_status` 和 `download_admission`，防止“元数据有许可”被误写成“所有图像已获准使用”。9 条记录中 8 条的元数据许可声明可核实；其中 NC 数据用途待决，代码许可不覆盖外部原图。**只有 4 个 Commons 单图条目被本轮准入并下载**。

## 许可与本轮数据边界

CC0 允许复制、修改与分发，包括商业目的；CC BY 允许共享和改编，包括商业目的，要求作者署名、许可链接及修改说明；CC BY-SA 还要求衍生图片遵循相同许可。以上是可核验的版权许可条件，不是公司生产数据授权、作者背书、法律意见，也不直接确定训练后的模型许可。

本轮下载目录限制为本地 pilot；所有下载总量低于 100 张/500 MB 授权范围。每张图同时保存来源页、下载 URL、原始 bytes SHA256、实际尺寸、许可与署名。公开 GitHub 可以保存来源/许可/hash 索引和符合许可的少量样例或衍生图；发布 CC BY/BY-SA 图及 overlay/HTML 内嵌图必须保留逐图署名、来源、许可、修改说明，BY-SA 衍生图使用 BY-SA。许可不明或不允许重新分发的图不能内嵌公开报告。

来源页面提供的拍摄日期原文只作为 `source_provided_capture_date`。未核实完整时区和实际拍摄时间时，`observed_at=null`、`capture_time_status=UNKNOWN_NO_VERIFIED_TIMEZONE`；绝不拿文件创建/下载时间冒充拍摄时间。所有 `base_identity` 保持 `UNRESOLVED`，品种未知，不关联公司真实基地。`GT_status=MISSING`、`annotations=null` 保留缺失，不转换成零果。

## 可运行来源工具

实现位于 `research/blueberry_vision/r3/sources.py`。`discover_sources(online=True)` 执行有上限的官方 metadata/许可页 HTTP 请求，输出实际成功、失败与 hash，不隐式下载图片；`online=False` 读取已提交的历史核验记录，并显示 `OFFLINE_PERSISTED_REVIEW` 和 `fresh_network_verification=false`，适合无网络 CI。

`download_public_pilot` 只接受已核验且允许小规模研究的单图条目；拒绝不明确、NC 待决及代码授权范围不匹配的来源。它检查 HTTPS/provider allowlist、重定向目标、来源 ID、单图 byte 上限、累计 byte 上限、原始尺寸并调用 R2 安全解码。目录必须新建，不覆盖历史下载，生成 `source_index.json`。它不下载权重、训练模型、访问业务数据库或上传图片。

复现本轮 4 张照片的下载到新本地目录：

```python
from pathlib import Path
from research.blueberry_vision.r3.sources import discover_sources, download_public_pilot

registry = discover_sources(online=True)
index = download_public_pilot(
    registry,
    Path("/tmp/blueberry-r3-public-pilot-new"),
    ["commons-4112477", "commons-4112528", "commons-15928839", "commons-81047629"],
)
```

来源可能变更或不可用；复现后应对照版本化记录中 `download_evidence.asset_sha256`，变化应建立新数据版本，不覆盖旧事实。网络抓取时间保留为 operational provenance，不应成为算法预测的 canonical hash 输入。

实际离线测试：

```sh
python -m pytest -q research/blueberry_vision/tests/test_r3_sources.py
ruff check research/blueberry_vision/r3/sources.py research/blueberry_vision/tests/test_r3_sources.py
mypy --explicit-package-bases research/blueberry_vision/r3/sources.py research/blueberry_vision/tests/test_r3_sources.py
```

本阶段执行结果：**22 tests passed**；Ruff、mypy 通过。测试覆盖许可 URL/名称对账、受限许可、代码许可范围、离线不联网、下载权限门禁、限量、目录穿越 ID、HTTPS/host 安全、重定向检查、真实测试夹具解码/hash、未知时间和缺 GT 保留；测试图明确是工程夹具，不是真实 benchmark。

## 首轮真实实验仍需条件

当前 4 张照片只能建立外部真实像素推理与域差异检查。需要两个真实独立人工标注版本、候选可见果定义、ignore/uncertain 规则、仲裁和封存，才能形成可评分参考。不能用模型框或本 agent 猜测的数量当 GT。

BlueberryDCM 是最相关的公开逐果候选，但需要明确 NC 用途或取得授权，下载后还应核实来源标注、可见定义、图像/标注身份、近重复和分组。其公开标签属于 `EXPOSED_PUBLIC_BENCHMARK`，不能宣称此前未见的盲测。公司果园试验另需数据所有者授权与 canonical 身份；这些公开来源不证明公司基地准确率。果数到 kg 映射不在本轮实验范围。


## M1 后续补充：更多公开真实照片和参考质量审计

M1 首次检查点后继续检索 DataCite、OpenAlex、Figshare、Kaggle 公共 metadata 和 Dryad。新增 5 个来源记录写入 [source_registry_supplement.json](../../research/blueberry_vision/evidence/r3/source_registry_supplement.json)，与原 9 条历史记录分开保留。**最终取得 8 张不同的合法公开真实照片**：4 张 Commons，以及 4 张 Blueberry Quality 实验台架照片。没有以增加 synthetic 数量替代真实图像接入，也没有访问公司或当前产季 actual。

### AgriVision

[AgriVision Figshare 29222462](https://api.figshare.com/v2/articles/29222462) 的 DB-1 数据集由 Muhammad Owais 等发布，dataset API 明确给出 CC BY 4.0。正式 [Scientific Data 论文](https://www.nature.com/articles/s41597-025-06263-3) 描述 1,195 张真实图像，由三位 trained annotators 标注、cross-validation 与 consensus 处理困难对象。**该论文自身的 CC BY-NC-ND 许可与 dataset API 的 CC BY 许可属于不同对象**；本轮未下载/再发布论文图版，没有把文章许可推定成数据许可。

DB-1.zip 约 6.02 GB，整包超过 pilot 上限。本轮仅使用官方 ndownloader 的标准 `Range` 请求。服务器返回了 `206` 和准确 `Content-Range`；读取 ZIP64 尾部和目录累计约 276 KB，目录包含 1,195 个 BMP RGB 原图、1,195 个 PNG masks，**没有实例 ID、bbox 或原 polygon JSON**。再仅取一张 mask，实际像素只有黑/白。虽然 publisher 描述人工逐果 polygon 标注，release 中二值语义 mask 不能证明接触果实各自的身份。**不能把连通域计数当作可靠逐果 GT**，因此没有运行其检测/计数准确率。没有下载 6 GB 整包或其 RGB 图像。

### Blueberry Quality release 2.0.0

[Zenodo 22148787](https://zenodo.org/records/22148787) 发布者为 Lando Maximilian Garbe。API 与官方 `DATASET_README.md` 均明确数据许可 CC BY 4.0。最初 concept record 20479052 会指向当前 release；复现固定使用实际核实的版本 **22148787 / 2.0.0**。

官方 release 包含 114 JPEG、87 CR3、34 XML，以及多种重叠 crop/mask 表示。metadata 和 README 说明 27 张 polygon 标注图、675 objects、另 7 个 bbox XML 共 500 boxes。当前 27 张 segmentation 图在 CV folds 中复用，**不是新增独立盲测**。本轮没有下载 CR3、训练 crop corpus、Lab* 测量表或完整 3.59 GB source / 1.30 GB curated archives。

受控 ZIP Range 读取只取了固定字母序的 4 张源图、对应 4 个 XML，以及用于身份对账的 publisher COCO metadata。选择规则是 `FIRST_N_SORTED_RAW_COCO_IMAGE_FILENAME_NO_MODEL_OUTCOMES`，不是按算法成功样本选择。4 张原图总计 **35,446,503 bytes**；完整该次 acquisition 的已记录网络传输 **36,402,648 bytes**，包括 archive 目录/成员、official record、license terms 和 README。其余补充 source metadata、另一次源格式失败尝试、一个 mask 和全部 XML 质量检查也远低于 500 MB；最初失败尝试没有清除，保存了失败原因。全过程仅 8 张不同真实照片准入，本轮未做大批下载。

原文件扩展名是 `.JPG`，其 JPEG bytes 内含 Canon MPO 多图元数据，Pillow 12.3.0 将它识别为 `MPO`。R2 的 PNG/JPEG 解码 gate 正确拒绝，**没有修改或放宽 R2 合同**。独立 R3 preprocessing adapter 检查原 bytes、25 MP/8192 dimension、最多 4 个 frames、EXIF orientation，并明确选 frame 0。首批 4 张的 orientation 为 1，6000×4000 的图创建新的 lossless PNG 派生图，长边 1500，尺寸 1500×1000；原图不改写。元数据保存 original SHA、derived SHA、frame index、尺寸、scale_x=scale_y=0.25、编码配置、版本和 preprocessing hash。非 1 orientation 会阻断并要求单独几何转换，不静默错配参考框。R2 loader 实际读取并校验了派生 PNG。Pillow 依赖固定为 12.3.0，wheel SPDX 为 MIT-CMU；没有增加视觉训练框架。

图片 preprocessing 仅描述像素与几何，不据此判定 synthetic/real。数据来源类型来自核实的 source authority。公开真实照片的派生 PNG 仍是 `PUBLIC_EXTERNAL_BENCHMARK`；synthetic 工程夹具即使能生成 PNG，也不能因此升级为真实观测。

### 参考候选不能自动升级成 GT

质量检查读取并核查了全部 27 个源 XML，**675 个 polygon 全部标记 `source="semi-auto"`，没有 `manual` 条目**。原 release 描述的 `manual train/validation/test splits` 是人工切分，不是人工审核所有标注的证明；未找到人工作业修正/复核说明。审计为 [publisher_annotation_provenance_audit.json](../../research/blueberry_vision/evidence/r3/publisher_annotation_provenance_audit.json)，保存逐 XML 的 SHA、对象数量和 source method，不把文件中的 self-declared annotator ID 当认证身份。

选中的 4 张图片共 **100 个 publisher 候选框，0 个合格人工 GT**。来源候选保留 `PUB_REFERENCE_PENDING_QUALITY`、`annotation_origin=UNVERIFIED`、`evidence_status=PENDING_QUALITY_REVIEW`，真实准确率仍为 `NOT_EVALUABLE`。

Publisher COCO category name 是源图片名，并不是成熟度类别。转换创建新的 bbox-only candidate draft：原 polygon 保留在源 artifact，显式按 x/y scale 0.25 转换 bbox，采用新的 1-based image/object IDs，保留 original category IDs/names、源 image IDs、object IDs、原 bbox、原 COCO SHA/member 和 source index hash。统一目标是 **`CANDIDATE_VISIBLE_BLUEBERRY`**，这是外部候选单果标签，不是正式业务已批准等级。转换本身不产生 reviewed/approved、人工作业背书或真实评分。

### 复现和文件索引

最终获取结果的持久索引是 [public_quality_source_index.json](../../research/blueberry_vision/evidence/r3/public_quality_source_index.json)。它记录原图、派生图、annotation hash、固定 selection rule、官方来源与许可、Range receipts。全部原图、大 COCO 和 XML 留在本地授权目录；GitHub 只保存小型 index 与质量审计，避免重复大规模 JSON/图片证据。

使用当前代码重新执行实际官方小样本下载，不需要登录、数据库或模型下载：

```python
from pathlib import Path
from research.blueberry_vision.r3.sources import (
    download_blueberry_quality_sample,
    make_quality_bbox_draft,
)

output = Path("/tmp/blueberry-r3-quality-new-run")
index = download_blueberry_quality_sample(output, image_count=4)
candidate = make_quality_bbox_draft(output)
```

函数不允许覆盖已有目录，Range 响应不支持 `206` 或 byte identity 改变时停止，不回退整包下载。只读取选定成员，核验每个 member CRC 并保存 SHA256；**没有声称验证完整 archive MD5**。模型推理只消费 source index 中的派生 image bytes，不消费 publisher 参考框。候选标注先经过正式几何/hash 校验，再进入人工标注工作台；在质量门禁完成前不得被评分。

Sources 模块最终新增测试结果：**30 passed**；Ruff lint/format、mypy 通过。补充测试实际生成小型 MPO 工程夹具，验证第 0 帧/原图不改写、缩放、orientation/frame/pixel/byte 策略、损坏拒绝、公开 archive Range 预算与路径控制、独立手工可复算 bbox scale `[4,8,12,16] × 0.25 = [1,2,3,4]`。这些测试不宣称真实模型准确率。

后续建议是对这 8 张合法照片完成独立真实人工单果标注、仲裁与封存，或者取得 BlueberryDCM 明确用途/商业许可后核验其可靠人工 reference。真实生产果园试验仍需公司数据所有者授权、canonical 身份、跨日期/设备/基地样本。数量到 kg 不属于本轮已验证能力。
