# R4 合格真实参考与首次评价

**工程准备完成；核心真实评价未完成，任务PARTIAL。** 8张获准真实公开图仍没有
合格逐果人工参考，GT0、真实Precision/Recall/F1/MAE/Bias/COCO均NOT_EVALUABLE。
没有新训练、阈值修改、重量标定、公司图像、数据库或当前产季actual访问。

优先阅读 [业务报告](examples/r4/business/report.md) 和
[人工标注指南](../../docs/research/blueberry-vision-human-annotation-guide-r4.md)。
R3全部原文件保持字节不变；新代码仅r4/，不改变R1/R2/R3合同或生产模块。

## 实际可运行入口

CPU Python3.12.14；所有依赖继承R3固定版本与许可证，没有新增视觉框架。

```bash
python -m pip install -r research/blueberry_vision/requirements-r4.txt
python -m research.blueberry_vision.r4.cli run-r4-acceptance --output /tmp/r4-acceptance-001
python -m pytest research/blueberry_vision/tests research/blueberry_vision/newtests research/blueberry_vision/r4tests -q
ruff check research/blueberry_vision
ruff format --check research/blueberry_vision
mypy --explicit-package-bases research/blueberry_vision
python -m research.blueberry_vision.r4.cli verify-artifacts --manifest research/blueberry_vision/evidence/r4/artifact_manifest.json --root .
```

一键验收真正重跑回归、恢复原始预测、核验旧制品、执行严格GT准入、生成业务
JSON/Markdown/HTML并核对新输出制品。`--skip-tests`仅供已经单独跑pytest的CI，
回执明确NOT_RUN_IN_THIS_COMMAND；不会伪称该命令跑了测试。
工程PASS与任务PARTIAL/真实评价NOT_EVALUABLE分别记录。

原始8张数据恢复沿用R3_README的受控公开来源获取与prepare-public-pilot命令；
核对evidence/r3/pilot_dataset_manifest.json的实际hash/尺寸/EXIF/来源。
网络临时503/403不能解释为数据许可获准，也不允许放宽源/hash检查。
原图正式来源、版权证据和索引已经GitHub持久化，不重复提交原图或两份20MB页面。
全分辨率clean-editor只消费明确授权本地data-root；不把路径发布成Web图片URL。

```bash
# 已经恢复且hash符合R3索引的8图授权目录（不要使用公司未授权目录）
python -m research.blueberry_vision.r4.cli prepare-work --data-root /tmp/r3-assets-001 --output /tmp/r4-human-work-001
# A/B分别领取其页面；允许loopback静态服务，禁止上传和生产部署
python -m http.server 8765 --bind 127.0.0.1 --directory /tmp/r4-human-work-001
```

公开 [清洁预览](examples/r4/clean_annotation_preview.html) 只有320px，明确不是最终
标注来源，其导出full_resolution=false会被R4导入拒绝。完整原输入字节视图保留
所有细节，可绘/移动/缩放/删除bbox、设置TARGET/IGNORE/UNCERTAIN并导出草稿历史。
R3编辑器复用，不提供模型框/数量、100个半自动框或另一位标注者答案。
A/B角色目前未分配；工具和浏览器工程测试不冒充真实人工复核。
完整图范围[0,0,width,height]、scale[1,1]，没有根据已见模型错误筛选容易ROI。

```bash
# 仅在实际人员独立交付合法文件后运行；以下文件名不是已存在的人类结果
python -m research.blueberry_vision.r4.cli import-human-draft --role A --bundle /authorized/A-human-draft.json --output /tmp/r4-A-qc.json
python -m research.blueberry_vision.r4.cli import-human-draft --role B --bundle /authorized/B-human-draft.json --output /tmp/r4-B-qc.json
python -m research.blueberry_vision.r4.cli compare-human-drafts --a /authorized/A-human-draft.json --b /authorized/B-human-draft.json --output /tmp/r4-differences.json
```

QC检查task/guide/源hash/尺寸/版本/完整性、重复目标、最小可见尺寸和未决目标。
不同ID只能证明声明不同，不会自动认证两个人或独立性。未标注≠真零；空图必须
明确完成全图审查；IGNORE/UNCERTAIN保持原始记录。A/B与仲裁原稿必须保留不可变。

后续真正收到人工资料后，Owner核实身份/来源/独立性与方法，按R3已有
create_draft/transition_review/adjudicate_annotations/save_snapshot显式创建新版本、
保留原始hash和实际人类证据，再SEALED。R4不提供自动填写HUMAN/VERIFIED的转换。
公开手工标注也需方法证据和项目质量审核，不能仅凭manual字段取得资格。
`human_approval_template.json`未填写，**不是批准**；真实批准文件需approval_hash。
Owner手工核验实际材料后才能用R2_common.seal记录其完整性，不能因seal自洽推定真实身份。
需要批准记录绑定图片、scope、guide、reference、来源A/B版本、实际批准时间/人员、
独立真实人员及identity/independence/project-quality证据文件ref和SHA256。
外部已发布人工标注还需PUBLISHER_HUMAN_METHOD证据。工具检查文件/hash/必要字段，
不认证人类、验证内容真伪或提供生产级独立保管；不得由Codex补造这些材料。

```bash
python -m research.blueberry_vision.r4.cli check-reference --snapshot /authorized/sealed-reference.json --approval /authorized/owner-approval.json --evidence-root /authorized/evidence --output /tmp/r4-reference-admission.json
# 当前没有GT时可以直接执行，真实指标保持null
python -m research.blueberry_vision.r4.cli evaluate-frozen --coco --output /tmp/r4-unscorable-001.json
# 未来批准完成后：references为R3annotation bundle，approvals根对象为{approvals:{image_id:receipt}}
python -m research.blueberry_vision.r4.cli evaluate-frozen --references /authorized/references.json --approvals /authorized/approvals.json --evidence-root /authorized/evidence --coco --output /tmp/r4-qualified-evaluation-001.json
python -m research.blueberry_vision.r4.cli render-business-report --evaluation /tmp/r4-unscorable-001.json --output /tmp/r4-business-report-001
python -m research.blueberry_vision.r4.cli recover-predictions --output /tmp/r4-restored-predictions-001
```

每个输出使用新路径，不覆盖历史。恢复命令读取R3已提交HTML中的框/score/id，
仅补齐原预测缺少的2649个component-area标量；A/B恢复后canonical与原始JSON文件
SHA都与R3发布值一致。它不是重新推理，不消费GT，不查文件名答案。
真实像素推理仍为原R3安全资产适配→R2两个算法，可由原R3命令复现；不调参。

## 评价与当前阻断

原冻结A=RGB阈值/4连通域，B=CPU NumPy logistic像素分类；模型/配置/后处理未变化。
评分先锁定原预测，再读取GT；合格参考和同一固定完整图范围才可一对一IoU.5匹配。
复用R3的matching、count、VOC-all-points RESEARCH_AP50与可选官方pycocotools2.0.11
适配。官方COCO maxDets1,10,100与无上限研究AP不同；未运行官方数据不能报标准mAP。
忽略区域用于匹配；原始计数仍含ignored预测（沿用R3冻结口径，报告明确说明）。
未决果串/不确定果阻断完整单果计数，不能静默排除后把全图精度报得好看。
缺GT图片保留null和具体reason code；逐图失败/未评分和负面结果不删。
部分合格范围仅报告其真实覆盖，未评分图片不能补零、不能称整个8图验证通过。

BlueberryDCM当前CC BY-NC4研究用途不等于公司关联用途授权，未下载该受限资源。
权利人请求草稿在docs/research/blueberry-vision-blueberrydcm-permission-request-r4.md，
**尚未发送**，Owner须核实合法主体/联系方式和明确许可范围。
8个公开资源实际来源核验见source_registry；BerryMachine CC BY4为新的跟进候选，
其野生欧洲越橘/越橘物种、人工方法、来源采样和受控小样本仍待核验，未计入GT。
500个manual损坏区域框不是500个果实；675半自动polygon也不能填补人工准入。

R3结果和公开标签已曝光，本任务只能EXPOSED_EXTERNAL_EVALUATION，不能blind。
公司果园准确率/正式成熟标签/视觉公斤数/生产批准均未验证。完成实际A/B独立人类
标注、第三人仲裁与Owner证据后，下一任务才能取得首轮可计算的真实外部评价。
本任务结束只创建stacked Draft PR，base=R3；不修改父PR720/719，不Ready/Merge/部署。
