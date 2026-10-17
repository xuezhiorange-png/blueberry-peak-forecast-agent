# Blueberry Vision Foundation — R0 云端研究分支准备记录

- TASK_ID: `BLUEBERRY_VISION_FOUNDATION_PREPARATION_R0`
- STATUS: `PREPARATION_ONLY`
- BRANCH: `research/blueberry-vision-foundation-prep-r0`
- BASE_MAIN_SHA: `c35524174865785164fe4529f35067037ccddc2a`
- PREPARATION_DATE: `2026-10-13`
- FORMAL_VERSION_ASSIGNED: `false`
- PRODUCTION_IMPLEMENTATION_AUTHORIZED: `false`
- IMAGE_DATA_ACCESS_AUTHORIZED: `false`
- MODEL_TRAINING_AUTHORIZED: `false`
- READY_MERGE_RELEASE_DEPLOY_AUTHORIZED: `false`

## 1. 依据与隔离边界

`docs/v0-17/v0.17.0-version-plan-and-product-scope-freeze.md` 明确将 `VISION` 和 `BLUEBERRY_IMAGE_MODEL` 排除在 V0.17 实施范围之外，仅将 `BLUEBERRY_VISION_FOUNDATION` 记录为未来候选，且当时未授权、未启动。V0.18 主线是业务可用性与安全试运行基础，不应被本研究分支隐式改写。

本次用户授权 **创建独立云端任务分支，进行视觉算法准备**。它不等于批准训练、生产接入、数据导入、新版本范围、Draft PR、Ready、Merge、Tag、Release 或部署。仅做准备性设计记录；不触碰既有生产模型、历史已冻结数据与 current-season actual。

## 2. 需由 Owner 确认的视觉业务目标

“视觉算法”尚未冻结成单一检测任务。以下均为 **候选用例，不是已批准需求**：

1. **果园观测**：花/幼果/成熟果检测或计数；关联样方、拍摄视角、时点与采样面积，探索成熟度与可采量信息。
2. **产量辅助估计**：由图像观测产生可验证的数量代理或特征，与原有面积驱动预测作离线比较。不得将目标检测计数直接转换成权威千克数。
3. **加工/品质观测**：商品果、尺寸或质量等级的视觉识别，仅在有正式标签口径及业务授权后独立评估。

先确认首个用例、观察单位（单果/果串/植株/行/样方/批次）、主要产出（检测/计数/分级/数量代理）、使用终端（固定摄像头/手机/其他）及是否与当前预测任务有可证明的关联。未经确认，不选择模型架构或定义上线指标。

## 3. 数据与图像采集准备

形成一张版本化数据清单，至少登记：

- 数据来源和使用许可、资料所有者及访问批准记录；
- 图像/视频来源、拍摄设备、分辨率、镜头/距离/角度、光照、天气、遮挡、重复拍摄关系；
- 采集时刻 `observed_at`、首次可用时刻 `available_at`、摄像头/采集会话与批次标识；
- 经批准的 `base_id` 映射、产季、品种、区域/样方；若映射缺少权威来源则标记未绑定，不通过名称猜测；
- 目标标签定义、标注规范、标注者、复核、质量状态与标签版本；
- 对齐的参照测量（若目标是产量，应明确独立计量/称重来源及观察覆盖率）；
- 敏感信息与定位暴露风险、脱敏、数据保存期限、访问控制、数据删除审批。

真实图像、私有业务数据和当前 2026–2027 actual 均 **不在 R0 的读取、采集或上传范围**。

## 4. 候选数据契约（仅设计，不建表）

```text
VisionObservationCandidate
  observation_id
  source_asset_id / source_asset_hash
  source_authority_id / permission_status
  observed_at / available_at
  base_id_or_unresolved / season_id
  capture_session_id / sampling_unit_id
  camera_device_and_view
  target_definition_version / annotation_version
  label_quality_status / review_status
  observation_payload_and_unit
  observation_hash / schema_version
```

图像观测为独立数据域，不能等同于自然成熟量、模型采摘量、实际采摘量或商品果量。若未来允许与预测联动，需单独冻结时间泄漏防护、authority 链路、模型版本、可用性截点与对照实验；不得改写既有预测 run。

## 5. 算法与验证准备

- **先定义任务再选择算法**：检测、分割、计数、成熟分级、产量回归并非同一种任务。
- **建立简单基线**：人工抽样、规则或传统视觉统计、现有非视觉预测作为可比对照；按目标选择恰当基线，不预设深度学习必胜。
- **样本切分**：优先跨日期、采集会话、地块/基地及产季隔离；近重复帧不得跨训练/评估集。特征、标注聚合和预处理参数只从训练部分拟合。
- **独立评估**：检测任务报告 precision/recall 或 mAP；计数报告 MAE、偏差和分层误差；成熟分级报告混淆矩阵与校准；产量估计报告按相同 scope/unit/time 的独立误差。指标随 Owner 冻结的用例选择，不用一种指标冒充全部。
- **覆盖与失败**：按遮挡、光照、设备、品种、地区、时段、未覆盖样方单独统计失败及不可评估样本；不把无图像或缺标注当作零。
- **复现证据**：未来实验必须锁定输入 manifest、split、label version、配置、随机种子、权重和结果 hash，并保留失败试验记录。
- **禁用捷径**：不得使用随机近邻帧分割作为主要泛化证据，不得训练/评分未经批准的历史或当前产季 actual，不得宣称图像代理是实测采收重量。

## 6. 下一阶段的准备交付物与门禁

R0 完成定义仅为 **分支创建并提交本准备说明**；不代表数据已获得或模型可用。

候选下一阶段交付（均需单独授权）：

1. 业务目标与观测单位冻结、可用/不可用场景确认；
2. 数据授权与样本覆盖盘点、采集和标注指南；
3. 可执行离线基线实验合同、独立测试集封存及验收阈值的 Owner 决定；
4. 资源评估（标注工作量、显存/算力、存储、评估成本）；
5. 与现有保存预测结果的只读比较/证据关联设计，不触碰生产服务。

## 7. 本分支硬约束

```ini
VISION_PREPARATION_BRANCH_CREATED=true
DOCS_ONLY=true
V0_17_SCOPE_CHANGED=false
V0_18_SCOPE_CHANGED=false
FROZEN_MODEL_CHANGED=false
CURRENT_SEASON_ACTUAL_READ=false
REAL_IMAGES_READ_OR_UPLOADED=false
DATA_COLLECTION_STARTED=false
MODEL_TRAINING_STARTED=false
PREDICTION_PIPELINE_CHANGED=false
DATABASE_MIGRATION_CREATED=false
API_MCP_DASHBOARD_CHANGED=false
DRAFT_PR_CREATED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_RELEASE_DEPLOY_AUTHORIZED=false
```

结束于 R0 准备状态。后续任何算法实现、数据接入和版本身份均需新的 Owner 决定。
