# R2 离线标注适配与人工审核

本轮处理的图像、参考框、训练与结果均为 synthetic。页面醒目标记
`SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY`。
这些是工程链路与错误检查结果，不是真实蓝莓准确率、业务成熟等级或 kg 标定。
本工具不连接生产 API、数据库、外部字体、云视觉服务，也不上传图片。

## 受控 COCO detection 适配

`annotations.export_coco(manifest)` 将 R2 `images` 参考记录转换为 COCO detection JSON：

- 原坐标采用半开区间 xyxy；COCO 使用 xywh，area 为框面积。
- class label 按字典序生成稳定 category ID；图片顺序对应独立 integer ID 映射。
- object ID、原始 source、annotation/label version、record hash 及其他研究元数据保留。
- 明确完成的空图保持 `objects=[]/visible_count=0`；missing GT 保持 null，不补零。
- model_prediction 不能充当 GT；重复 identity、非整数 ID、损坏几何、越界、缺失来源、
  segmentation/RLE/crowd 等不支持形式抛出 `AnnotationError.code`。
- 标签保持 candidate，不借格式转换声明业务批准。转换器不读取图片、不验证授权真实性。

`annotations.import_coco(coco)` 要求 `research_provenance` 和每张图的
`research_record`。裸外部 COCO 需要经过授权 steward 明确补全来源、版本和 hash，不能
凭文件名推断身份。导入输出是 `blueberry-vision-reference-adapter/2.0.0`，
`is_validated_dataset=false`，不是冒充完整 R2 dataset 或 R1 观测。
原样往返保留对象位置、数量、类别及 record hash。若修改框/类别/数量，则产生新的
`candidate-import/...` annotation version、`annotation_quality_status=draft`、
`original_record_hash` 与新 hash；后续必须独立验证及审核，不能直接成为训练真值。

`annotations.export_r1_coco(r1_manifest)` 仅适配 R1 的 detection 几何；其他任务保留
`NON_DETECTION_TASK` 排除原因。只有数量而没有目标框会返回 `GEOMETRY_UNAVAILABLE`。
R1 fixture 仍为 `image_files_present=false`、`synthetic_descriptor_sha256`；
转换没有创造任何图像字节，也不将 descriptor hash 伪装为资产 hash。
所有转换均保留 `asset_bytes_verified_by_converter=false`。

## 报告与图像导出

`report.render_report(manifest, data_root, prediction_bundles, evaluation_reports, output_dir)`
需要新的 output directory，拒绝覆盖既有实验。先检查 dataset/prediction/evaluation seals、
source/model/config 绑定与共同评估范围，再通过独立 evaluator 重算报告，拒绝旧指标与新框
拼接。仅打开 `SYNTHETIC=true` 的记录，使用授权根目录内的 bounded PNG/JPEG loader
核对真实字节 hash 和解码尺寸，不将本地路径作为 Web URL。

输出包括：

- `report.json`：逐图 GT、实际预测、评估结果、模型/配置 hash、分层指标及来源。
- `report.md`：实际 metrics 和限制；`report.html`：可直接本地打开的内嵌数据页面。
- `evaluation_model-N.json`：原输入完整 evaluator artifact，包括 AP 曲线、分层和所有失败；
  Markdown 仅显示 scalar metrics、覆盖/失败摘要并链接这些 JSON，不裁剪负面原始结果。
- `overlays/`：所有评估图片的每个模型 GT/Prediction 对照；框编号、可见数量与误差。
- `prediction_overlays/`：原图与预测框叠加，不绘制 GT；计数 caption 保留比较信息。
- `errors_collection/`：所有 FP/FN、计数错误、missing/failed 图像，保留负面结果。
- `scene_collage.png`：实际场景分类图；`metrics_summary.png`：由真实评估 JSON 绘制。

HTML 将图像编码为 data URL，数据嵌入且转义 `</script>` 等输入。CSP 禁止网络连接；
无 fetch、外部脚本/字体或依赖登录。相同输入不将系统时间、主机名和临时目录写入结果 hash。
报告复算不反向影响模型参数或训练/test 标签隔离。

## 页面使用及候选标注草稿

1. 本地打开生成的 `report.html`，选择 Baseline A/B，查看逐图来源、场景与模型/配置摘要。
2. 切换 GT/Prediction overlay；按 FP、FN、高计数误差、失败/missing、空图筛选。
3. 点击 `Start draft from reference` 建立独立候选副本；鼠标拖动绘框。
4. 点击 draft 框选中，删除或修改 candidate class；页面显示当前草稿可见目标数。
5. 点击 `Export new draft JSON` 下载新版本；没有任何文件或服务器自动写入。

导出的 `blueberry-vision-annotation-draft/2.0.0` 保留 asset hash、parent annotation/label
version、source authority 和 SYNTHETIC 标记，状态仅为 draft/candidate，没有 reviewer
身份、reviewed 或 approved。原 GT 内存和文件不被覆盖。草稿不是训练/评估 GT；
没有已批准业务标签映射时，自定义类名仅为候选文字。
零面积框无法加入或导出。浏览器若缺少 `crypto.subtle` 或摘要生成失败，会明确显示
`EXPORT_BLOCKED`，不下载缺少独立内容版本身份的草稿；不会共用伪造的 fallback version。

限制：本轮没有生产标注平台、多人审核、登录、持久化编辑、mask/RLE、真实数据授权核验、
自动标签升级或生产模型注册。页面用途是本地错误检查与候选标注导出。真实图像实验前仍需
独立数据许可、身份映射、冻结标签手册、采样方案和人工审核；视觉数量到重量还需独立称重标定。
