# R4 独立人工标注工作说明

本轮工作包包含R3的全部8张公开图像，不删减模型分歧大或困难图片。
范围预注册为每幅完整规范化RGB图片：[0,0,width,height]、缩放[1,1]。
Quality输入是R3已固定的1500×1000 frame0派生PNG；不是6000×4000原始双帧文件。
原图/派生hash、来源许可、坐标及标签规则hash在human_annotation_package.json。
没有新挑选局部ROI，完整图幅的参考才可与已有完整图预测比较。

计数对象：能够观察并区分的单颗可见蓝莓，候选颜色均可；颜色不是正式成熟等级。
紧包围**可见部分**，半开xyxy坐标，不能推断全隐藏果实或损坏区域的整果数。
接触果实仅在边界可分辨时分别标框；可确认的出画部分算一颗，框裁到图片边界。
可见尺寸任一方向不足3原始输入像素，不猜测，标UNCERTAIN。
不可逐果区分的果串标UNRESOLVED_FRUIT_CLUSTER/IGNORE；身份不确定标UNCERTAIN；
非目标干扰标NON_TARGET_DISTRACTOR/IGNORE。完整逐果计数含未决果串/不确定果时
仍不可计算，必须仲裁或明确缩小经预注册的研究目标，不能静默当零。

保持R3 snapshot的candidate-visible-blueberry/3.0.0合同；额外R4指南版本是
r4-visible-single-berry-research/1.0.0，通过work_package_binding绑定，不擅改旧标签物理意义。
此定义是本轮研究候选规则，尚无Owner正式业务标签批准。

## 分配、标注和交付

1. Owner指派两位真实标注者A/B及第三位仲裁者，记录真实身份核验依据。
   Git中的A/B/ADJUDICATOR是**未分配角色**，不是已存在的人员。
2. 单独提供A、B的全分辨率clean-editor页面及同一指南。不能提供预测叠加、
   预测数量、R3半自动候选框或另一位的答案；记录各人的已有曝光情况。
   Public预测已曝光，所以整个实验始终是EXPOSED_EXTERNAL_EVALUATION。
3. 分别New empty draft，按实际全图逐果绘框，可移动/缩放/删除/改候选类别和disposition。
   逐图检查全部区域后选择COMPLETE；真正空图才显式EMPTY_VERIFIED。
   不完整图仍UNANNOTATED；不得由导入工具补零。
4. 使用1:1 / Fit inspection查看完整分辨率细节；完成每张图后先导出，再切换图片。
   没有云端自动保存，不能把低分辨率预览当作完成全图审查。
5. 输入真实操作人员ID只代表self-asserted，工具没有账号认证。Export new draft + history
   保存新文件；编辑不覆盖原GT。COCO可候选导出，主交付是含task/guide绑定的snapshot bundle。
6. A/B独立提交；Owner保留原文件hash、时间、任务来源和独立性证据，再调用R4导入/QC。
   不要把机器模拟的测试文件、Codex/LLM绘框或browser工程检查当真实人工结果。
7. 仲裁者复核分歧；R3原状态机DRAFT→SUBMITTED→REVIEW_PENDING→ADJUDICATED→SEALED。
   原A/B不可变；新参考版本需绑定两份来源hash、身份/方法核验、实际批准依据。

Git公开clean_annotation_preview.html仅320px**预览**，不是有效标注来源；它的导出
full_resolution=false，R4导入会拒绝。完整页面在本地由代码和版本化来源清单重建，
不需要把两份20MB重复页面提交Git。完整图片不得因公开HTML而失去CC署名/BY-SA条件。
R3页面代码被复用；没有新生产服务、外部视觉API或自动上传。

## 评分口径与人工准入

冻结R2两套模型不重训不调参。IoU0.5、同类置信分数排序一对一匹配；ignore重叠阈值0.5。
沿用R3原始输出计数（包括落入ignore的模型候选），报告中需说明检测ignore与原始计数
口径的差别。不能为了看起来好修改预测或仅展示成功样本。没有合格GT时P/R/F1/MAE/Bias
均为null/NOT_EVALUABLE；候选标注数量不是已批准真实参考数量。

需要Owner提供真实来源/身份/独立性核验和批准记录。离线hash只能核验完整性，
不能认证人或证明其确实观察了图片。工具不能自动将manual、两个不同ID或SEALED状态
升级为QUALIFIED_GT；公开手工数据也必须补足项目范围/质量审核依据。
公司果园泛化、跨基地日期设备、正式成熟标准和计数→kg均仍未获验收。
