# 蓝莓视觉独立数据契约与采集规范 R1

TASK_ID=`BLUEBERRY_VISION_FOUNDATION_ENGINEERING_PREPARATION_R1`。状态为研发准备，
不建立生产表、Alembic migration、API 或预测输入，不批准实际采集/图像访问。
R1 的离线工具授权来自本次任务；R0 文档中的 DOCS_ONLY 保留为历史快照。

## 1. 身份、版本与用途

`VisionObservation` 是一张图像在一个版本下的一条观测记录，不是采收事实。
`schema_version=blueberry-vision-observation/1.0.0` 与
manifest 的 `schema_version=blueberry-vision-manifest/1.0.0` 是独立 research 契约版本，
不是正式产品版本。字段、标签、标注及算法版本分别管理，不共用一个模糊版本号。
单一 manifest 内 image_id 唯一；同图重标注保留旧 manifest，创建新版本，不覆盖旧记录。

| 字段 | 含义与规则 |
| --- | --- |
| observation_id / image_id | 非空稳定记录/资产身份；manifest 中各自唯一；不得用文件名或基地名称代替 |
| asset_hash | SHA256；真实获授权资产以后按原始字节计算，变换/裁切资产另记来源关系 |
| capture_session_id | 一次采集过程/连续视频会话，整个会话作为 split 分组 |
| observed_at / asset_available_at / available_at | 拍摄时刻、资产首次可用时刻、该版本观测首次可用时刻；RFC3339 带时区 |
| annotation_available_at | 此标注版本首次可用时刻；未标注显式 null，不倒填拍摄时间 |
| base_identity | resolved 时含 base_id 与 authority_ref；unresolved 时保留未绑定原因，base_id/authority_ref 为 null |
| season_id / sampling_unit_id | 明确产季及稳定样方/植株/行等采样单位；ID 须带命名空间全局唯一，候选单位口径须 Owner 确认 |
| variety_id / occlusion / device / image_dimensions | 品种、遮挡与设备/角度/光照分层、宽高像素；未知可选参数显式 null 或 schema 定义的 unknown，不猜设备校准结果 |
| annotation_version / label_definition_version | 标注版本及对应标签定义注册项；nullable 字段仍必须出现 |
| annotation_quality_status | 未标注、草稿、复核或拒绝状态；实验训练/评估要求 reviewed |
| task_kind / object_count / count_unit | 候选任务、可见果实数、fruit_count 单位；无数据显式 null 加原因 |
| class_labels / objects | 逐对象的标签序列（长度等于已提供 count）与对象引用；标签必须来自本 manifest 注册的定义，边界框不得越界 |
| source_authority | 所有者/来源声明、授权状态、证据引用、允许用途及有效期；hash 不授予访问权限 |
| record_kind / SYNTHETIC | real_observation、synthetic_observation、model_prediction 三者明确区分 |
| model_provenance | 模型预测必须有模型版本/hash、生成及可用时间；不能充当训练或独立测试真值 |
| near_duplicate_group_id | 经未来真实图像审查建立的近重复组；不可跨 split |
| schema_version / record_hash | 契约版本与记录内容摘要；记录改动后必须形成新的可追溯版本 |

Schema 是字段与枚举的机器权威，工具 README 是接口说明。本表不隐式增加已经实现的
COCO 标注转换、实例 mask 训练适配、样方面积标定或业务成熟度标准。

`record_hash` 对输入记录移除自身 record_hash 字段后的 JSON 计算：UTF-8、
`sort_keys=True`、`ensure_ascii=False`、`separators=(',', ':')`，SHA256 小写 hex。
基于原始显式字段计算，校验器不补值、不修正、不重写。禁止 duplicate JSON keys、
NaN/Infinity；重新排序对象键不会改变 hash，修改内容会改变 hash。

## 2. 时间与 point-in-time

必须满足 `observed_at <= asset_available_at <= available_at`；存在标注时
`asset_available_at <= annotation_available_at <= available_at`。预测生成及版本可用
时间也纳入检查。所有比较按时区换算到同一 UTC 时刻，不能按字符串字典序比较。
manifest 的 as_of_cutoff 与 split_cutoffs 阻止消费截止时间后才可用的观测。
不接受非法时区偏移或 RFC3339 中代表未知本地偏移的 `-00:00`；UTC 换算超界须拒绝。

未来训练 origin 只能使用该时点可用的资产、标注及特征；称重标签的 available_at
独立记录，不能把观测可用时间当作称重可用时间。最终成熟度/全季总量不能回填成
旧 origin 的特征。离线工具检查时间声明是否自洽，无法证明声明在历史上真实存在；
未来须依赖采集日志、入库凭据、签名/不可变 manifest 和授权证据审查。
现有历史预测 `STRICT_PIT=false` 的边界不因本契约而改变。

## 3. 零、缺失与标注语义

- 明确完成复核的空图可以有 object_count=0；未拍摄、无法分辨、未完成标注不能是零。
- 模型预测可以输出 0 个目标，但必须保留 model_prediction/provenance 且处于 unassigned；
  它表达推理结果，不能解释为人工确认无果或训练/测试真值。
- 模型预测可以输出 0 个目标，但必须保留 model_prediction/provenance，且不进入真值
  train/validation/test。该零仅是模型输出，不证明实地无果或人工审核确认的零。
- object_count 缺失必须写 null 与 missing_count_reason；字段缺失本身是 schema 错误。
- 每图统计是所定义可见目标计数，不是全株果数、总商品果数或 kg。count_unit 仅为 fruit_count。
- 遮挡边界、极小目标、出画目标、可见部分比例、是否包含青果等必须在未来标签手册冻结。
- 成熟度候选如颜色阶段不等于糖度、风味或可采收标准。颜色标签需专家定义与复核，
  保留 unknown/不可判断，不能根据现有商品等级名字自动建立视觉标签。
- 本轮模拟标签均为占位定义，不是业务成熟等级，模拟数值不能用于准确率、重量或 ROI 报告。

未来真实标注过程：标注者按已批准手册独立标注 → 抽样双标 → 统计一致性/计数差异 →
争议仲裁 → 标注者与复核者身份/完成时间/版本留存 → reviewed 发布。
双标抽样比例、目标可见阈值、最小像素大小、成熟标签、错误上限由 Owner 在真实实验前
确认，当前为待决。审核失败保留 rejected 和原因，不能静默删除困难样本改善指标。

## 4. 采集与采样规范（设计，未采集）

1. 先批准数据所有者、用途、设备、样本单位、定位敏感级别、访问人员和保存期限。
2. 按基地/品种/日期建立采样框；记录总可采样单位数、抽样概率、采样覆盖面积或株数、
   未覆盖和拒拍原因。方便取景的果串不能当作无偏基地样本。
3. 对每个会话记录设备型号/镜头、分辨率、距离/角度、曝光/白平衡设置、照明和遮挡分层。
   记录现场色卡/尺度标定是否存在；未知参数显式缺失，不生成虚假精度。
4. 对视频保存 frame_index、原视频身份及重复关系；转码、增强、裁切都继承原 split。
   多视角同果/同植株跨帧重复需要 tracking/空间关联或固定拍摄协议，单图检测无法解决。
5. 采样频率按目标冻结；记录采前/采后、修剪/疏果、落果及未采积压等事件，用于以后解释
   可见果变化。频率不足时不得插值为实际观测或将缺拍当作成熟量为零。
6. 如未来研究重量，独立配对样方采摘与校准秤称重，记录果实数量、质量分布、商品果率、
   秤/测量者/时间/批次、覆盖率和独立 authority。采摘量与到厂量也需区分。

此规范不是实际图像采集或当前产季 actual 访问授权。本轮未访问任何真实图像或数据库，
也不执行目前 2026–2027 actual 的查询、导入或评分。

## 5. split 与重复隔离

训练/验证/独立测试至少三部分，另外保留 out_of_domain（训练范围外）和 unassigned。
一个 experiment manifest 对应一个已批准任务与 label_definition_version，训练/验证/测试
及范围外记录必须一致；不同候选任务分别封存 manifest。annotation_version 可有不同
复核修订，但必须绑定同一标签定义，不能用不同任务的样本拼成三份 split。
不随机拆相邻帧。exact asset_hash、image_id、observation_id 的重复拒绝；
near_duplicate_group_id、capture_session_id 及稳定 sampling_unit 分组不得跨 split。
所有记录先按声明关系求连通分组，unassigned 也参与关系连接；一个连通组只能归属
一个训练/评估 split，不能用未分配记录间接连接训练与测试来绕过隔离。
同图增强、裁切、重新编码须人工/感知 hash 审查后归同一重复组，不能用新 image_id
规避隔离。split 在训练前封存，测试不用于调阈值、选架构、颜色变换或人工筛样。

manifest 保留 near_duplicate_review 的方法、完成状态和证据引用。**当前工具没有读取
图像或计算感知 hash**，因此只能检查已声明分组的隔离，不能发现未声明的相似图片。
未来真正图像查重、跨设备复拍匹配、基地/品种/日期留出覆盖检查须单独实现和授权。
同基地不同采样单位可在普通分组实验出现，跨基地泛化必须另立完全留出的基地评估，
不能把会话隔离当作已经通过跨基地验证。

## 6. 来源、授权与版本发布

真实数据须有 approved 权限声明、可审查的批准证据、允许 training/evaluation 等用途及
有效期；有效期为 `[granted_at, expires_at)`，到期时刻不再有效，并覆盖本次 manifest 使用
时刻。pending/denied 不得进入可执行训练/评估 manifest。模拟使用 synthetic_only。
数据/标签许可与候选算法实现、模型权重许可分别审查，不能由一种授权替代另一种。
工具只验证声明，未来数据 steward 必须核实授权文件及主体权限，不能将 contract PASS
解释为真实数据访问获准。模型预测的模型 provenance 与标签真值来源分别登记。

真实数据和模拟数据不能混为同一可评估 cohort；model_prediction 永不作独立真值。
真实资产以后存放在经授权隔离位置，公开仓库只存脱敏 manifest/报告；不能把图片、
精确地理位置、个人信息或凭据提交本分支。未来去敏、加密、访问日志、删除与撤权
需明确负责人及期限，尚未实现为生产服务。

Schema 不执行 canonical base registry 查询。resolved ID 的合法性仍需未来获授权的
authority 审查；unresolved 必须如实保留，不能模糊匹配基地名称或通过 Company 汇总
身份替代 Base。Region/Company 属于关联层，不作为本图像 Base 身份捷径。

## 7. 与现有预测的关联（仅设计）

未来只以经批准的 base_id、season_id、sampling_unit_id、variety、origin/as-of 和
目标窗口连接独立研究副本；保存 vision manifest/hash、标签/模型版本、feature schema、
原预测 run/result/model/source hash、面积/树龄 authority 和独立称重 authority。
预测快照必须完整保留，视觉衍生结果创建新 research artifact，不覆盖既有 run。
树龄或采样覆盖率缺失不得默认补零；衍生特征的拟合/标定只使用训练 cohort。

从图像计数到重量至少缺少：抽样覆盖/抽样概率、每果质量分布、遮挡校准、多视角重复
关联、采收/商品率、图像时刻到采摘窗口的关系、独立称重及面积/树龄 authority。
未取得这些标定数据时，只能研究可见果计数及代理信息，不能输出基地采摘 kg。

本轮完成的边界是独立数据契约与模拟元数据校验。采集、真实标签、图像相似度工具、
模型训练、mask适配、重量标定、预测关联读取器及生产数据库均不由本文件授权。
