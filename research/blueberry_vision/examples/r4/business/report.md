# R4 真实蓝莓参考与冻结算法评价

结果：NOT_EVALUABLE；合格GT图片0；未评分图片8。

使用R3全部8张合法公开图：4张Commons照片、4张Quality1500×1000派生PNG。
来源/原始与派生hash/许可保留在R3清单；未接入公司果园或当前产季actual。

| 图片 | 许可 | A原始预测数量 | B原始预测数量 | 合格参考数量 | A/B计数误差 |
| --- | --- | ---: | ---: | --- | --- |
| public-commons-15928839 | CC0-1.0 | 1161 | 66 | NOT_EVALUABLE | NOT_EVALUABLE |
| public-commons-4112477 | CC-BY-2.0 | 236 | 185 | NOT_EVALUABLE | NOT_EVALUABLE |
| public-commons-4112528 | CC-BY-2.0 | 9 | 52 | NOT_EVALUABLE | NOT_EVALUABLE |
| public-commons-81047629 | CC-BY-SA-4.0 | 201 | 514 | NOT_EVALUABLE | NOT_EVALUABLE |
| quality-1626757232 | CC-BY-4.0 | 11 | 12 | NOT_EVALUABLE | NOT_EVALUABLE |
| quality-3127978079 | CC-BY-4.0 | 0 | 33 | NOT_EVALUABLE | NOT_EVALUABLE |
| quality-3872104307 | CC-BY-4.0 | 67 | 21 | NOT_EVALUABLE | NOT_EVALUABLE |
| quality-4195390806 | CC-BY-4.0 | 0 | 81 | NOT_EVALUABLE | NOT_EVALUABLE |

真实参考是谁提供和审核：本轮未收到真实人工A/B标注、仲裁或Owner核验批准。
任务A/B/ADJUDICATOR均未分配。Codex/浏览器工程测试不是人类审核。
100个候选框、675个半自动polygon、500个manual损坏区域框均未升级为单果GT。

计数定义：完整图中可区分的单颗可见蓝莓，tight visible bbox；不猜测隐藏果；
接触/遮挡/出画按固定R4指南，极小/不确定果和不可逐果果串需标记并仲裁。
范围是预注册完整图，不是看过模型错误后选择的ROI。原R3合同未改变。

两套算法分别为RGB_threshold_and_4_connected_components_v2和
CPU_NumPy_logistic_pixel_classifier_v2；原R2模型、阈值、后处理和R3预测均未改变。
上表是算法输出，不是准确计数。最大分歧图片A1161/B66；该差异不能说明哪套正确。

漏计/误计在哪里、哪种场景最难：缺合格GT，目前不能判断或排序。
密集、遮挡、反光可作为人工审查重点，当前分层身份未知，不能填造分层零误差。

可计算：8张图片/16次已有推理的数量、模型分歧、来源与hash完整性。
不可计算：真实TP/FP/FN、Precision/Recall/F1、RESEARCH_AP50、CountMAE/Bias、
总漏计/误计、真实COCO_MAP50/50_95：保持null/NOT_EVALUABLE。
官方COCO未跑真实GT；将来实际运行时记录pycocotools2.0.11/maxDets1,10,100。

公开标签和R3结果已曝光，只能EXPOSED_EXTERNAL_EVALUATION，不能称为blind test。
不能代表公司果园：基地/拍摄时间/品种未知；无跨基地、日期、设备验证。
视觉数量不能换算采摘kg；没有生产视觉批准或产量模型改动。

下一步：先由两位真实人员完成这8张图的独立全分辨率逐果标注，第三位仲裁，
保留身份/来源/独立性证据和实际批准记录，再运行冻结预测评价。
或由Owner向BlueberryDCM权利人取得明确公司关联用途许可，再核对逐果方法与样本质量。
新发现BerryMachine CC BY4资源仍待物种/真实人工方法/受控读取核验，不是已准入GT。
后续公司果园试点建议先取得30–50张获准全图，覆盖至少3基地、3日期和2设备/角度，
含负样本、密集和遮挡；这是初步采集建议，正式样本量需依据误差目标重新确定。

代码/工作包：r4/，evidence/r4/human_annotation_package.json、task_A/B/ADJUDICATOR.json。
清洁编辑预览：examples/r4/clean_annotation_preview.html（不是合格标注来源）。
已有模型审核页面：examples/r3/real_review.html（不要交给独立标注者看预测答案）。
本地全分辨率任务由prepare-work命令重建；原图不重复提交Git。

report_hash=c1f5b8f0dd650855f213d10ca3175d2dba22c5cd9d9072f07cfe84614533d152
prediction_lock_hash=799e0800be23b9b8645cee7e489c6e032937629f7e7b40f33ef54c66f587df30

| 模型 | 合格评价图数 | TP/FP/FN | Precision/Recall/F1 | Count MAE/Bias | COCO状态 |
| --- | --- | --- | --- | --- | --- |
| A | 0 | NOT_EVALUABLE/NOT_EVALUABLE/NOT_EVALUABLE | NOT_EVALUABLE/NOT_EVALUABLE/NOT_EVALUABLE | NOT_EVALUABLE/NOT_EVALUABLE | NOT_RUN |
| B | 0 | NOT_EVALUABLE/NOT_EVALUABLE/NOT_EVALUABLE | NOT_EVALUABLE/NOT_EVALUABLE/NOT_EVALUABLE | NOT_EVALUABLE/NOT_EVALUABLE | NOT_RUN |
