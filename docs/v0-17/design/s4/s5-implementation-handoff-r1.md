# S5 Implementation Handoff — 尚未授权

## 1. 顺序与路由

Owner 另行授权后按 AppShell/身份选择 → 预测 → 总览 → 质量 → 影响因素不可用 → 产能编辑/模拟/比较实施。候选 /dashboard/overview、forecast、attribution、capacity、quality 路由留待 S5 核对现有 router。旧 Trial 两路径、组件、P50/P80/P90 历史合同独立保留，不迁入新语义，不改默认重定向而不测试。

## 2. Saved-run P0 依赖

BUSINESS_RUN_SELECTOR_BACKEND_READY=false。正常业务保存记录发现/授权交接无现有完整 API。S5 开始前 Owner 必须决定可信服务器上下文来源及访问隔离范围；不能用旧无授权 LIST 或 fake latest 代替。高级身份输入只供技术核验，不视为业务选择体验完成。BASE/REGION/COMPANY 每次须完整身份+hash，不推断聚合授权。

## 3. 子实体贡献 P0 依赖

S1 没有合法 child list/contribution ratio response。模块保持 NOT_AVAILABLE；若要上线比例，须单独授权服务端同源合同与权限。不由客户端计算贡献，不读当前 registry 改历史 snapshot。

## 4. API Client 和类型

复用 S1 六 GET 与 S2 /api/v1/decision-support 两 POST；独立于旧 Trial client。以现有 Pydantic response/schema 对应 TypeScript discriminated union，Decimal 全部 string，原始hash保留。ReadResponse<OverviewData/CurveData/HierarchyData/QualityData>、DecisionResponse<SimulationData/ComparisonData> 映射不可丢 reason/status。空值、partial、unavailable 不转 0。区间/归因 READY 新payload当前没有：本轮不虚构未来schema。

GET overview 的累计/峰值、高量排序全部服务端；曲线只绘图。S2 daily rows/aggregate/utilization exact pair与derived decimal全部透传；禁止重算 backlog/loss/rank。展示舍入不回流计算。精度工具可在 S5 授权内选择，但不改变权威字符串。

## 5. 请求与编辑状态

取消旧请求 + generation/context key检查，迟到响应不能覆盖新选择。模拟 input revision 改变立即 stale，旧有效排名隐藏；用户手动提交。成本无默认；三合成合同显式ID/hash。上界无绑定禁用，不 POINT fallback。initial backlog只读0，buffer非库存。最多20情景×15日、人数≤1000000、Decimal输入≤64字符、body≤131072bytes；超限可诊断不截断。

## 6. 图表/组件/移动端

按机器合同29组件与Tokens实施；Recharts仅候选，S4未安装，S5应核验库的键盘/缺失断线/辅助表兼容再决定。画布坐标数字不能参与业务运算。手机KPI2×2、单情景、纵向rank卡片；44px目标、焦点、data table替代。真实iOS Safari/Android软键盘仍须另测；本轮Chromium窄视口不替代。

## 7. 客观验收

五页×八状态模块独立；三层身份、H1/H3/H7/H15、短窗口、child incomplete、无记录、hash mismatch、权限和503恢复。组件tests + API contract + browser E2E：服务→HTTP→显示字符串/hash相同；无client业务数学；模拟修改后过期；取消和迟到竞态；无上界/归因伪造；coverage低于nominal；当前actual空态。截图回归按六视口、五页、状态样本，检查scrollWidth、遮挡、文本截断、键盘路径、200%字体与reduced-motion。

## 8. 隔离与仍需授权

不在浏览器嵌MCP凭据；S3真实生产凭据/grants/旧入口网络隔离未验。S5不是生产批准、真实ROI或当前季评分。冻结数学、S0–S3历史证据、Trial不变。Owner仍需最终视觉签字、S4独立review/Ready/Merge授权、S5实施授权，并解决上述保存记录与贡献依赖。设计候选通过不自动解除任何gate。
