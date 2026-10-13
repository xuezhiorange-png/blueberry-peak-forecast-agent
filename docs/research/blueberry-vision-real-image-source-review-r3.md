# R3 真实蓝莓图像来源与许可核验

TASK_ID：`BLUEBERRY_VISION_R3_REAL_IMAGE_PILOT_AND_VALIDATION`

本轮实际检索了公开来源，核验了 9 个来源条目，下载并用 R2 安全图片读取器解码了 4 张真实蓝莓照片，总计 **6,371,007 bytes**。照片属于 `PUBLIC_EXTERNAL_BENCHMARK`，不是公司基地数据，也不是 synthetic。它们没有合格逐果人工参考标注，因此可以运行真实像素推理，**不能计算真实识别准确率**。

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
