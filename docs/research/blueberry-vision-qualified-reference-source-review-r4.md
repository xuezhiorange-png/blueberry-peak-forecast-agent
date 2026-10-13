# R4 合格单果参考来源核验

最新官方 BlueberryDCM14002517 记录称140张图、17,955个VIA2.0.12手工框。
数据许可仍为CC BY-NC4.0。官方legalcode第1(i)节将NonCommercial定义为
“not primarily intended for or directed towards commercial advantage or monetary compensation”；
第2(a)(1)节限制材料和衍生材料的复制/共享为非商业用途。
本任务与公司未来模型研发有关，不能仅因现在是离线研究就认定非商业。
没有下载该资源；需要权利人明确授权本项目的公司关联用途。以下请求草稿尚未发送。

代码仓库README的17,809旧数字与Zenodo17,955当前数字不同，尚未取数据核对；
公开论文其他模型的93%mAP也不是本项目的算法成绩。原始manual声明、坐标格式
和项目样本质量验收分别核验，不能自动取得QUALIFIED_GT。

实际8个公开数据资源的当前核验、官方响应hash和失败请求见
research/blueberry_vision/evidence/r4/source_registry.json。
Quality有675个半自动polygon和100个待审框；其500个manual框的
Kaputte Stelle/Stellen标的是损坏区域，不能转为单果计数GT。
AgriVision发布的是二值合并mask；FlexiGroBots为Bush/Pole；CRISP没有逐果
人工方法说明；deepNIR不是蓝莓；新实例分割软件明确不提供原图/私有标注。

新发现BerryMachine为CC BY4、野生欧洲越橘/越橘资料，公开索引有VOC/COCO，
总87.7GB，且含synthetic.zip、预测表和真实资料，必须分开。
本轮只核验元数据/文件清单，没有把模型预测表当GT、没有下载图片或全包；
真实人工方法、物种范围、独立采样和小规模受控获取仍待确认。
它是后续可跟进的来源，不宣称所有公开数据都不可用。

现有8张R3获准图片可继续人工标注；版权/出处与原始hash保留。
本轮选择全部完整图，避免看到模型分歧之后挑选容易ROI。
公开曝光结果仅可EXPOSED_EXTERNAL_EVALUATION，不是blind test或公司果园精度。
