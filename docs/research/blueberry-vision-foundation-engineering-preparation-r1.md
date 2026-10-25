# 蓝莓视觉算法研发工程准备 R1

TASK_ID=`BLUEBERRY_VISION_FOUNDATION_ENGINEERING_PREPARATION_R1`

交付类型：`ENGINEERING_PREPARATION_ONLY`。正式视觉模型未开发、未训练、未验证精度。
本轮只完成独立研究资料、数据契约、模拟元数据与离线工程准备，不授予下一轮实验权限。

## 仓库基线与隔离

- 仓库：`xuezhiorange-png/blueberry-peak-forecast-agent`。
- 指定分支：`research/blueberry-vision-foundation-prep-r0`。
- fresh fetch 后 `origin/main`：`c35524174865785164fe4529f35067037ccddc2a`。
- fresh fetch 后研发分支/真实起始 HEAD：`60208273be061d891c2cfb5bb4ff952647f6e5f8`，与已知起点一致。
- `/workspace` 开始无已检出仓库，建立独立克隆 `/workspace/blueberry-vision-r1`。
  clone 使用 no-checkout 时的 tracked 删除显示来自未检出；检出指定分支后状态完全干净。
- 该克隆 `git worktree list --porcelain` 仅包含自身；不清理、不覆盖其他目录、任务或 worktree。
- 阅读 AGENTS、研发规范、R0 及 V0.14–V0.18 冻结资料；历史授权快照不回写。
  本次 R1 明确授权离线工程，优先于 R0 的历史 DOCS_ONLY，且禁止创建 PR。

基线之后的新增文件限于 `docs/research/` 和 `research/blueberry_vision/`。
不修改依赖清单、生产 API/MCP/Dashboard、数据库、数学模型、冻结证据或历史预测记录。
本轮无真实图像数据集/权重下载、图像上传、actual 查询、模型训练或部署。

## 交付索引

| 交付 | 内容 |
| --- | --- |
| [现有能力审计](blueberry-vision-existing-capabilities-r1.md) | 历史数量/面积、身份、训练验证、hash、PIT、FI/预测持久化、Python 配置；每项已有/缺失/复用建议和源码证据。 |
| [算法调研](blueberry-vision-algorithm-research-r1.md) | A 检测、B 实例分割、C 成熟分级/分割、D 视觉辅助产量；原理、数据、指标、成本、资源、风险和条件性实验建议。 |
| [数据契约与采集规范](blueberry-vision-data-contract-r1.md) | 资产/观测/身份/标注/许可/版本、缺失与零、时间泄漏、去重、采集及重量标定。 |
| [离线工具说明](../../research/blueberry_vision/README.md) | Schema、无图像的 synthetic manifest、CLI 与 pytest，明确声明校验的能力边界。 |
| [未来实验与验收规范](blueberry-vision-experiment-protocol-r1.md) | 候选路线、授权门禁、独立 split、训练/验证/测试步骤、指标定义、对照设计及待决阈值。 |
| [机器实验协议](../../research/blueberry_vision/experiment_protocol_r1.json) | PLANNED_NOT_RUN 的独立研究协议，不含真实实验结果。 |
| [本轮实际验证证据](../../research/blueberry_vision/evidence/preparation_validation_r1.json) | 离线执行命令、返回值/输出、工具版本、范围与来源完整性检查。 |

## 关键结论

已有的是数值预测的工程与来源治理模式。面积、到厂 kg、商品等级、树龄字段并不构成
图像资产、bounding box、实例 mask 或成熟视觉标签；现有 schema 字段存在也不证明
真实数据授权和历史严格 PIT。Base/Region/Company 身份与权限不能靠名称或 hash 猜测。

建议的首轮候选是“已获授权样方、单幅图像的可见蓝莓检测与计数”，以独立人工复核为
参照，再比较实例分割的额外收益。该建议不冻结业务任务、成熟标签、最终架构或上线阈值。
图像中检出的果实数量不等于实际采摘重量；视觉产量辅助研究须先取得覆盖率、果重、
遮挡/重复校准及独立称重等业务标定数据，并与同一 scope/unit/time 的非视觉预测比较。

当前只校验 JSON 元数据、已声明的重复分组、时间和权限状态，不读取图像、计算图像
相似度、验证外部授权文件真伪或计算真实算法指标。没有真实标注/封存独立测试集时，
只能报告工程准备完成，不能报告 Precision、Recall、mAP、MAE 或真实增量收益。

## 本轮实际离线验证

实际输出已保存在上述 JSON 证据，不是未来计划或人工填写的预期结果：

| 检查 | 实际结果 |
| --- | --- |
| 显式 research pytest 路径 | `69 passed in 1.40s`，exit 0 |
| ruff check | `All checks passed!`，exit 0 |
| ruff format --check | `5 files already formatted`，exit 0 |
| mypy --explicit-package-bases | `Success: no issues found in 5 source files`，exit 0 |
| synthetic contract CLI | valid=true，exit 0；5 条虚构记录，其中 1 条显式缺失数量 |
| synthetic experiment CLI | valid=false，exit 2，按设计拒绝 synthetic/未批准候选标签/不存在真实图像 |
| 冻结来源完整性 | 13 个读取的公共规范 SHA256 保持一致；机器实验协议绑定的 5 个来源也保持一致 |

工具在 `/tmp` 隔离环境运行，所选版本与仓库原有 uv.lock 相同：Python 3.12.14、
Pydantic 2.13.4、pytest 9.1.1、pytest-asyncio 1.4.0、ruff 0.15.18、mypy 2.1.0。
根依赖清单及 lock 未改变，没有安装视觉训练框架。

测试包括 strict schema/nullable 必填、UTC 时序和截止点、非法时区/极端日期、ID/hash
重复、同图/会话/样方及经过 unassigned 的连通组泄漏、标注/标签注册与对象几何、
来源用途/到期/证据声明、预测与观测分离、零与缺失、JSON 解析失败和 CLI 退出码。
另一次内部合成元数据审查复验了连通组/预测零及单任务/单标签版本准入修复；此审查
不替代任务完成后的独立 Owner 审核，也不证明真实授权或视觉性能。

仅运行本轮离线准备检查。没有运行生产/数据库/历史回测，也没有创建 PR 或声称远端
CI、生产安全、模型精度或正式版本验收通过。

## 研发阶段清单

| 状态 | 本轮/后续项目 |
| --- | --- |
| 已具备 | 现有 Python/Pydantic/pytest 工程、hash/版本/可用时间/身份/保存预测模式；本轮独立 JSON Schema、synthetic fixture、离线 validator、真实可运行负向测试。 |
| 已设计但未实现 | 实际采集流程、视觉标注平台与 mask/COCO 适配、真实图像近重复计算、视觉训练/指标 runner、图像到样方/称重标定、与保存预测的只读关联、生产集成。 |
| 缺少真实数据 | 经授权图像/视频、人工复核真值、封存独立测试集、各分层/OOD 覆盖、采样覆盖/抽样概率、单果重量与独立称重；存在性与访问性未盘点私有来源。 |
| 需要业务确认 | 首任务/观察单位、可见果/遮挡/边缘规则、成熟度定义及 unknown、Base/品种 authority、设备/频率/采样预算、数据 owner/许可/保存期限、主要指标和验收阈值。 |
| 后续单独开发授权 | 真实数据访问/采集/上传/标注/称重、框架/权重、训练调参、独立测试解封与评分、预测对照数据读取、适配服务/数据库/生产上线。 |

本轮提交和推送只完成研发准备交付。PR_CREATED=false、READY_AUTHORIZED=false、
MERGE_AUTHORIZED=false；无正式版本、Tag、Release、Deploy。最终 commit/push SHA 与结果
见任务回执，文件内执行证据采用提交前快照，避免用未发生的 CI 或循环自引用伪造证明。
完成后停止，等待下一次独立审核与授权。
