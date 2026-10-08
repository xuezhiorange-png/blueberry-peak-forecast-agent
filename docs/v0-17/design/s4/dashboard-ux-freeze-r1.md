# V0.17 S4 Dashboard UX & Design System Freeze — 候选 R1

## 身份与治理

TASK_ID=V0_17_S4_DASHBOARD_UX_DESIGN_SYSTEM_FREEZE_R1。基线 4c9a29542cef2e0dc10812826d2b7e9333956c0a；PR #702 已合并，post-merge run 37732882094 completed/success，执行时现场核验。已消费已完成的 S4 只读预研，不重复研究。正确目标为 blueberry-peak-forecast-agent；冷库工作区未修改。

方向：A 管理决策型总览 + B 专业分析型工作台。深松绿、温灰白、清晰表格、统一无衬线字体。没有聊天 UI、渐变、炫光或装饰性插画。色值与断点以本候选实际 Chromium 截图为依据；不是 Owner 最终视觉签字。

S4_IMPLEMENTATION_AUTHORIZED=true；OWNER_VISUAL_APPROVAL=false；S4_FORMAL_COMPLETE=false；S5_AUTHORIZED=false；Ready/Merge/Deploy/Tag/Release 均未授权。设计候选完成不等于正式完成。只提交设计资料、静态原型、截图、证据及离线合同测试。

## 阅读入口

- [五页信息架构](five-page-information-architecture-r1.md)
- [上下文与选择流程](navigation-and-saved-run-flow-r1.md)
- [组件与图表合同](component-and-chart-contract-r1.md)
- [响应式与无障碍](responsive-and-accessibility-r1.md)
- [机器可读合同](dashboard-contract-r1.json) / [Tokens](design-tokens-r1.json)
- [静态原型](prototype/index.html) / [视觉报告](visual-qa-report-r1.json)
- [S5 交接](s5-implementation-handoff-r1.md)

## 原型边界

所有示意实体、日期、数量、情景和质量指标均明确标记 SYNTHETIC DESIGN FIXTURE — NOT PRODUCTION DATA。固定结果是预声明视觉样本，不是表单计算；编辑输入使结果失效。原型无网络 API、存储、预测、模拟或评分调用。没有实际采收数据访问。

未来 Dashboard 只能读 S1/S2 的 authoritative result。客户端禁止重算累计量、高峰、贡献比例、积压、损失、排名。绘图坐标转换仅用于画布；原始 Decimal 字符串保留供表格/详情。没有兼容 authority 的区间、归因、贡献模块明确 NOT_AVAILABLE。

## 冻结验收

五页与四 KPI 顺序精确；六视口覆盖；八状态按模块独立；无页面横向溢出；键盘/触摸可达；缺失不变零；历史质量不代表当前表现；合成损失不代表货币或 ROI。最终候选结论以同目录视觉报告及 Draft exact-head CI 为准。S5 必须另获授权。
