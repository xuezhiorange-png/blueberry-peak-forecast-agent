# 导航与已保存预测上下文

## 正常业务路径 A：可信授权交接

候选 AuthorizedSavedForecastContext 包含 source_kind、forecast_family、run_id、hierarchy_level、entity_id、target_season、origin_date、baseline_id、policy_version、expected_source_result_hash。来源必须是未来受信任的服务端授权上下文；这是界面候选输入合同，不是已存在的发现 API。

业务界面只展示实体名称、层级、起点、保存记录标识及完整性。S1 当前没有正常业务发现/交接接口，BUSINESS_RUN_SELECTOR_BACKEND_READY=false。静态原型的实体与保存记录明确为合成设计上下文，不伪装成数据库下拉。不得使用旧 MCP LIST、猜 run ID 或自动 latest 绕过授权。无 context 显示“请选择已保存预测”。

## 高级路径 B：完整身份核验

技术人员手动输入上述十项字段，经 S1 显式查询与 canonical verification 后才提交 context。输入不是权限证明。错误维持原已验证 context，不把未核验字段变成页面来源。hash 校验与访问授权不同；S1 HTTP 仍仅粗粒度 actor 权限，不能声称具备逐基地/最终用户隔离。业务入口就绪还需 Owner 明确授权安全交接来源。

## 交互状态机

打开 selector → 选择可信交接 / 高级核验 → 请求核验 → READY/PARTIAL → 原子提交完整 context → 取消旧页请求并清除旧日期/模拟结果 → 各模块独立加载。

核验失败 → 可诊断状态 → 更正身份或取消返回。MISMATCH 不保留错误数值；取消不改变原 context。层级、实体、保存记录切换都走同一完整核验过程，不能单改 entity_id。Quality 固定历史身份，顶栏显示其不依赖保存记录。

对话框打开移入首字段/说明，Tab 被原生 dialog 限定，Escape/关闭后焦点回触发按钮。手机使用单层可滚动 sheet，不建立嵌套弹窗，底部按钮随内容布局且留键盘安全区。日期联动：按钮/图点/日表行共享 selected target_date，切 run 清空，不把样本日期复制至其他 run。

## API 与请求生命周期

S5 使用现有 S1 六 GET 与 S2 两 POST，MCP 不是浏览器凭据通道。相同完整 identity/result hash 不变；source/projection/adapter/engine/scenario/comparison hashes 各自保留。AbortController 取消旧请求，并以 generation/context key/input revision 双重拦截迟到响应。503 可手动重试，401走既有认证，403不枚举资源，409重新核验，422字段错误，413提示技术上限。网络失败不能显示旧结果为新成功。
