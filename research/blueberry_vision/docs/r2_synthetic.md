# R2 合成图像与参考标注

`synthetic.py` 的 `generate_dataset(output_dir, seed=20261013, images_per_split=14)`
实际生成 RGB PNG、逐果检测框、训练用像素 mask 和 `dataset_manifest.json`。
默认 train、validation、test、out_of_domain 各 14 图，共 56 图；普通图 256×192，
压力场景 320×256。全部资产和记录保持 `SYNTHETIC=true`，有真实 PNG 字节不改变
它们的模拟来源。没有真实果园图像、生理成熟等级、重量或业务基地身份。

14 场景为 sparse、dense、touching、partial_occlusion、high_occlusion、
leaf_branch_background、shadow、glare、mixed_sizes、color_appearance、edge_crop、
empty、distractors、pressure。每图有独立强弱照明，背景含叶片、枝条和噪声；果实
包含明暗纹理、蜡粉候选外观、反光和深色花萼图案。候选绿色/粉色/蓝色均是模拟
外观，不解释为已经批准的成熟分级。负样本保留背景；蓝色干扰物不属于果实 GT。
压力场景实际绘制并参考标注 120 个可见果实，没有检测结果上限截断。

每个 split、场景及图序号通过 SHA256 从总 seed 派生独立生成 seed；不使用 Python
进程的随机 hash。几何位置、大小、背景、颜色及纹理实际独立采样。pressure、
edge_crop、touching 和 distractors 的果实几何也随 seed 变化；模板身份不是只把
相同几何改名。每图保存 `template_geometry_parameters` 和其内容 hash，包含果实
中心/椭圆半径、干扰物和背景几何；此 hash 不含 seed、图片 ID 或 split 字符串。
会话、样本单位、近重复分组和模板组分别限定在对应 split；没有源图跨 split 增强。

共享的通用渲染程序、场景类别、部分叶片遮挡原型及候选形状族仍是共同生成机制，
**不是对未见生成器或真实田间分布的模板族留出验证**。OOD 只模拟背景、色彩、
果实椭圆形变的分布变化。即使独立 seed 的工程 test 成绩很好，也不能证明真实
泛化。真实图像近重复检测尚需未来独立授权和实施。

## 可见参考口径

渲染时维护逐像素 instance ownership。后绘制果实及前景叶片会覆盖旧 ownership；
参考由最终 ownership 计算，不由请求绘制数量决定。每个对象保存原始图内轮廓
像素数、最终可见像素数、比例、候选外观、边缘裁切和参考状态。

- 完全隐藏：最终可见像素为 0，不进入 reference。
- 低可见：可见比例小于 0.15 或可见像素少于 12，不进入 reference，输出 ignore 区域。
- 包含：满足两条阈值，输出最终可见像素紧致 `xyxy` 框，右/下边界采用 half-open。
- 边缘裁切：比例的分母是**图内未遮挡轮廓**，不假定图外轮廓可被观察；裁切单独记录。
- 真正零果：empty 未绘制任何目标，objects=[]、visible_count=0。

因此 drawn_object_count = visible_count + hidden_object_count + ignored_object_count。
high_occlusion 明确保留完全隐藏及低可见例子，不隐去困难形态。可见框可能较小，
计数仍是 `visible_fruit_per_image`；不能推导全株果数、采收重量或 kg。

训练 mask 为单通道 PNG：0=背景、255=最终可见且包含的果实、128=低可见忽略。
每图保存 mask 真实字节 SHA256。mask 和逐果参考只供训练/评价；推理算法不得读取
它们、渲染对象布局、生成 seed 或数量来查答案。遮挡叶片是背景，完全隐藏果实
没有可见像素标注。用于评价的 ignore bbox 是可见 ignore 区域的紧框，简化框式
忽略与精确实例 mask 的语义边界须在评价规范中说明。

## 版本与复现

数据契约 `blueberry-vision-dataset/2.0.0` 通过独立 R2 适配层保存资产及检测参考，
不修改 R1 `blueberry-vision-observation/1.0.0`。标签版本为
`synthetic-visible-fruit/2.0.0`，标注版本为 `synthetic-render-reference/2.0.0`。
record hash 直接复用 R1 `canonical_record_hash`；manifest/split hash 使用公共
canonical JSON convention。原始文件 SHA256 和规范化 RGB 预处理 hash 由资产
加载工具计算。固定虚构 2000 年时间戳仅用于模拟时间顺序，不声称实际采集。

PNG 编码固定 `optimize=False, compress_level=9`，不写时间戳、主机或 EXIF 元数据。
生成配置记录 Pillow/NumPy 版本。同 seed、配置和锁定依赖环境可复现相同图片、
mask 和 manifest 字节；跨编码器版本的字节一致性不作保证。输出目录必须为空，
拒绝覆盖历史实验。无需网络、数据库、外部视觉 API 或预训练权重。

运行 generator 的 Python API 示例：

```python
from pathlib import Path
from research.blueberry_vision.synthetic import generate_dataset

manifest = generate_dataset(Path("/tmp/blueberry-r2-demo"))
```

独立回归命令：

```bash
python -m pytest research/blueberry_vision/tests/test_r2_synthetic.py -q
```

测试覆盖 56 图场景、真实 PNG/hash/mask、可见框与 accounting、空图、隐藏与
ignore、120 果压力图、OOD、按 split 的实际几何内容差异、seed 重复生成和拒绝覆盖。
这些是工程验证，不是蓝莓真实识别准确率。
