# 五页信息架构与内容优先级

业务路径：FORECAST → RISK → WHY → WHAT_IF。只允许总览、预测、影响因素、产能模拟、预测质量五项导航。技术信息位于 disclosure/dialog，不新增管理入口。旧 /trial/forecast 与 /trial/quality 完全保留，不复用其分位数或质量窗口语义。

## 总览 OVERVIEW

第一屏四 KPI，严格依次为：预测起点后 7 日累计量、预测起点后 15 日累计量、保存曲线高峰日期、高峰日预测量。全部取 S1 overview；H7=D1..D7，H15=D1..D15。不是相对今天的未来 7/15 日。空窗口无高峰，短窗口不假装完整。日期高峰按原有保存曲线最早并列峰规则，不累加子实体峰值。

其后：逐日 POINT 曲线 → 规划上界不可用说明 → 区域/基地贡献 → 较高预测量日期 → 简洁能力/完整性。贡献接口当前不存在，保留 NOT_AVAILABLE 解释，不绘制假比例。高量列表沿用服务端描述性顺序，无报警红线。核心曲线占主内容全宽，不放狭窄侧栏。

## 预测 FORECAST

显示完整保存身份、COMPANY/REGION/BASE、起点、H1/H3/H7/H15、可用日期数、POINT 曲线、上界状态、日表、来源详情。日期按钮与日表行同步选中同一日期。Horizon 只改变显示上下文/服务端已有摘要；不在浏览器计算窗口总量。短窗口缺日断线，不补零或插值。层级切换必须取得新的已验证完整身份，不由客户端聚合。

## 影响因素 ATTRIBUTION

当前主状态 NOT_AVAILABLE。先显示预测身份与 authority 绑定，再说明 Operational Peak 不具备 M1 模型/特征/封存预测的精确绑定。当前没有真实贡献排名或柱状图。未来合法 READY 布局：有符号贡献按服务端输出顺序，零基线，组/项明细，intercept/clip/serialization adjustment 独立展示，不擅自分摊。只有模型归因，不是因果解释。

## 产能模拟 CAPACITY_SIMULATOR

使用 S2 /api/v1/decision-support/simulate-capacity 与 compare-capacity-scenarios。完整保存身份/来源 hash 在上下文中固定，选择 POINT，显式选择合成成本，用户创建 A/B/C。DIRECT 与 WORKFORCE_DERIVED 互斥；人数严格整数，人效显式；buffer 为当日额外处理能力，不是库存。初始 backlog 固定 0、不可编辑。上界未绑定时禁用并说明，不回退 POINT。

先编辑再手动提交。输入变更立即标记旧结果过期，隐藏有效排名。请求处理中仍可取消/切换；按 request generation 与输入 revision 拒绝迟到响应。结果六项：处理量不足天数、累计日不足量、最大积压、期末积压、总处理利用率、合成规划缺口损失。需求/能力图与日末积压图独立。比较只在同 forecast/planning/cost/date set 下显示服务端 rank，称“给定条件下的情景排序”。不优化、不调度、不推荐人数。

## 预测质量 QUALITY

独立历史证据，不随全局 Operational Peak 选择重标。身份固定 M1 Ridge / EXPOSED_OOT / 2025–2026 / BASE_COHORT_AGGREGATE；STRICT_PIT=false。H1/H3/H7/H15 点指标按冻结证据；区间覆盖只 H7/H15，H1/H3 明确不可用。展示 PI80/PI90 与 Upper80/Upper90 观察值、nominal、候选/可计算/不可计算/覆盖数。低于名义水平用中性关注色与文字，不用绿色成功。

原型所有数字是设计合成样本；S5 应保留真实冻结观察：H7 PI80 约53.9%、PI90约74.5%；H15 PI80约50.6%、PI90约71.1%，均低于名义。不能宣称未来覆盖保证。当前产季固定“当前产季暂无可用于正式评分的实际采收数据。”无导入、上传或创建质量报告。

## 八状态

五页 × 八状态详见 dashboard-contract-r1.json.state_matrix。每项包含 copy、recovery、data_rule；不允许全页一个 READY 覆盖所有模块。原型评审状态控件在设计辅助区，不属于产品主导航。READY 样本仍保留上界/归因/贡献不可用；PARTIAL 保留已合法部分，缺失不补；ERROR/MISMATCH 隐藏受影响结果；NO_CURRENT_ACTUAL 不阻断无 actual 依赖的预测页。
