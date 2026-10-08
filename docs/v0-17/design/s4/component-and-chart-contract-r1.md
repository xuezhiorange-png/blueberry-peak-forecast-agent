# 组件与图表合同 R1

机器可读权威：[dashboard-contract-r1.json](dashboard-contract-r1.json)。每组件均有以下十类合同；当前原型仅设计交互，不连接业务服务。

## AppShell

- inputs: page, context, module states
- authority: S1/S2 envelope
- missing: Keep navigation; affected module only
- interaction: Skip link; page heading focus
- desktop: 200px sidebar, content max1440
- mobile: compact header + horizontal single-level nav
- copy: 蓝莓预测智能
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: All five routes reachable without nested menu

## PrimaryNavigation

- inputs: active page
- authority: S0 five-page set
- missing: Never remove destination for missing data
- interaction: Tab/Enter; aria-current
- desktop: vertical five links
- mobile: single horizontal row, short labels
- copy: 总览 / 预测 / 影响因素 / 产能模拟 / 预测质量
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Exactly five semantic links; 44px targets

## GlobalForecastContext

- inputs: verified ForecastIdentity, source hash
- authority: S1 canonical read
- missing: 请选择已保存预测; Quality independent
- interaction: Open selector; focus return
- desktop: entity/origin/run inline
- mobile: two-line context; details collapsed
- copy: 保存预测 · 预测起点
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No relative-to-today wording; no latest guessing

## AuthorizedSavedRunSelector

- inputs: AuthorizedSavedForecastContext candidate or advanced full identity
- authority: Trusted handoff NOT currently implemented; S1 verification
- missing: No backend list means no populated dropdown
- interaction: dialog two explicit paths, Escape and return focus
- desktop: bounded 640px dialog
- mobile: full-width scrollable dialog, keyboard safe
- copy: 选择已保存预测
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Ten identity/hash fields verified server-side before commit

## HierarchySelector

- inputs: level + separately verified entity context
- authority: S1 saved hierarchy snapshot
- missing: No inferred children or client aggregation
- interaction: select COMPANY/REGION/BASE; change requires identity revalidation
- desktop: inline selector
- mobile: 44px full-width control
- copy: 公司 / 区域 / 基地
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: FARM/FACTORY absent; current selection not silently rewritten

## KpiCard

- inputs: server value|null, unit, horizon status
- authority: S1 OverviewData
- missing: — plus explicit reason, never zero
- interaction: label/value read in DOM order
- desktop: 32px tabular value
- mobile: 28px value, wrap long label
- copy: 预测起点后 7 日累计量
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Null and legitimate zero distinct

## KpiGrid

- inputs: four ordered KpiCard inputs
- authority: S1 overview
- missing: Keep four slots with independent states
- interaction: reading order same as visual
- desktop: four columns
- mobile: 2×2
- copy: 7日 / 15日 / 高峰日期 / 高峰日量
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Fixed order and no fifth primary KPI

## DailyForecastChart

- inputs: ordered DailyReadRow + optional legally bound series
- authority: S1 curve; bounds unavailable presently
- missing: Gap breaks line; no extrapolation
- interaction: date buttons + touch point + auxiliary table
- desktop: wide 280px plot
- mobile: full width 220px plot
- copy: 逐日预测 · kg
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Only plotting coordinates use numeric conversion; no business arithmetic

## DailyForecastTable

- inputs: daily rows and source hash
- authority: S1 exact rows
- missing: — not 0; missing date not manufactured
- interaction: row date buttons synchronize details
- desktop: semantic four-column table
- mobile: date/point concise row + details
- copy: 日期 / 预测值 / 规划上界
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Original decimal text preserved in detail; no clipped numbers

## ChartDateDetail

- inputs: selected authoritative daily row
- authority: S1 row
- missing: Clear detail on run change or missing date
- interaction: Arrow keys via date controls; live region
- desktop: adjacent chart detail
- mobile: below chart full width
- copy: 日期详情
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Date/chart/table share selection, not new computation

## HighLoadDateList

- inputs: server-ordered descriptive dates
- authority: S1 overview
- missing: No fallback sorting from browser
- interaction: date link selects curve date
- desktop: compact ranked rows
- mobile: vertical rows
- copy: 较高预测量日期 · 相对关注顺序
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Never production alarm or threshold

## HierarchyCompletenessPanel

- inputs: expected/included/missing children + status
- authority: S1 hierarchy
- missing: INCOMPLETE_CHILD_COVERAGE explicit; block simulation
- interaction: details disclosure
- desktop: inline status + details
- mobile: stack counts, no squashed table
- copy: 子节点覆盖
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Partial aggregate never shown complete

## ContributionPanel

- inputs: optional server-bound child contribution payload
- authority: No current API contract: NOT_AVAILABLE
- missing: Do not render fake proportions
- interaction: explanation and future detail entry only
- desktop: panel reserved under main chart
- mobile: full width unavailable panel
- copy: 区域 / 基地贡献暂不可用
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No client percentage or registry-based inference

## AttributionAuthorityPanel

- inputs: identity + bound authority status
- authority: S1 attribution
- missing: Current NOT_AVAILABLE primary state
- interaction: read reason + authority disclosure
- desktop: clear explanation with future layout text
- mobile: stacked panel
- copy: 本次保存预测尚未绑定合法归因
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No generic importance passed off as run explanation

## ContributionChart

- inputs: future exact contribution payload, not existing API
- authority: Future S1-bound M1 authority only
- missing: No bars in current prototype
- interaction: future keyboard term list + text alternative
- desktop: signed horizontal bars, zero baseline
- mobile: vertical term list + expandable raw values
- copy: 模型中对本次预测贡献较大
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No causal copy; adjustments separate; future schema gap explicit

## ScenarioEditor

- inputs: explicit capacity rows + cost ID/hash + planning level
- authority: S2 schema, server forecast selection
- missing: No default cost or productivity; invalid scenario isolated
- interaction: mode radio/select; errors linked; manual submit
- desktop: A/B/C tabs + form grid
- mobile: one scenario at a time; sticky actions not obscure fields
- copy: 当日额外处理能力
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: DIRECT/workforce exclusive; initial backlog read-only 0

## CapacityDemandChart

- inputs: S6 demand and effective capacity rows
- authority: S2 engine result
- missing: Stale result not current; missing breaks series
- interaction: paired data table and date detail
- desktop: two series, same kg axis
- mobile: full-width plot
- copy: 规划需求与有效处理能力
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No recomputing effective capacity in UI

## BacklogChart

- inputs: S6 closing backlog rows
- authority: S2 engine result
- missing: No substitution of overload; zero valid
- interaction: date controls and data table
- desktop: separate chart from daily gap
- mobile: full-width plot
- copy: 日末积压
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Carry-over vs new-demand deficit explicitly explained

## ScenarioComparison

- inputs: S2 comparison rows and rank/hash
- authority: S6 compare_and_rank via S2
- missing: Mismatch/stale hides ranking
- interaction: sortable presentation must not change engine ranks; keyboard rows
- desktop: wide comparison table
- mobile: stacked rank cards
- copy: 给定条件下的情景排序
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Only same forecast/planning/cost/date set; no optimal recommendation

## QualityMetricPanel

- inputs: H1/H3/H7/H15 frozen point metrics
- authority: S1 quality independent historical evidence
- missing: Missing metric unavailable, not zero
- interaction: horizon tabs + exact value details
- desktop: metric table
- mobile: compact horizon cards
- copy: 历史验证 · 非当前生产表现
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: WAPE/MAE/Bias/cumulative WAPE, no re-scoring

## CoverageComparisonChart

- inputs: H7/H15 candidate/computable/covered counts and coverage
- authority: S1 public S2 observations
- missing: H1/H3 interval NOT_AVAILABLE
- interaction: accessible comparison rows + table
- desktop: observed/nominal bars with text
- mobile: vertical comparison rows
- copy: 历史观察低于名义水平
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Under-nominal not green success; no prospective guarantee

## HistoricalScopeSummary

- inputs: model/split/season/scope/strict PIT flags
- authority: S1 QualityIdentity
- missing: Evidence missing NOT_AVAILABLE
- interaction: details for pins
- desktop: compact scope strip
- mobile: stacked label/value
- copy: M1 Ridge · EXPOSED_OOT · 2025–2026
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Quality not relabeled as selected Operational Peak run

## AuthorityDetails

- inputs: source result/projection/adapter/engine hashes, policies
- authority: Original S1/S2 separate provenance fields
- missing: Absent field omitted with reason
- interaction: native disclosure / dialog; Escape focus return
- desktop: technical details secondary
- mobile: wrap hash; never horizontal page overflow
- copy: 权威来源详情
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Hashes not renamed or recalculated

## StatusPanel

- inputs: status, reason, recovery, module ID
- authority: Corresponding envelope
- missing: No catch-all masking
- interaction: aria-live polite; alert only actionable error
- desktop: panel within affected module
- mobile: full-width readable text
- copy: 数据状态
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Status per module, not blanket page success

## ErrorState

- inputs: sanitized code + retryable flag
- authority: S1/S2 error contract
- missing: Hide failed data, retain valid independent modules
- interaction: retry same identity; focus error heading
- desktop: bounded error panel
- mobile: full width action
- copy: 暂时无法读取，请重试
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No SQL/token/path/stack exposure

## UnavailableState

- inputs: unavailable_reason + scope
- authority: S1/S2 normal NOT_AVAILABLE
- missing: No fabricated chart/value/fallback
- interaction: explanation not disabled dead end
- desktop: neutral panel
- mobile: stack text + authority details
- copy: 当前权威来源不支持此能力
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Business unavailable not system error

## EmptyState

- inputs: no verified saved context / no rows
- authority: S1 EMPTY or no selection
- missing: No fake run list
- interaction: open authorized context selector
- desktop: centered guided panel
- mobile: visible primary action
- copy: 请选择已保存预测
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No latest or old LIST shortcut

## LoadingSkeleton

- inputs: request generation, requested module
- authority: Presentation only
- missing: Never show 0 as pending
- interaction: aria-busy; cancel on switch
- desktop: fixed geometry cards/plot
- mobile: 2×2 skeleton
- copy: 正在读取已验证来源
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: No layout jump; reduced-motion static

## ScenarioResultFreshness

- inputs: input revision + completed request revision
- authority: S2 result identity comparison only
- missing: Edits mark stale immediately, hide active ranks
- interaction: manual re-submit, cancel old request
- desktop: notice above result
- mobile: notice before action/result
- copy: 输入已修改，结果已过期
- states: LOADING / READY / EMPTY / PARTIAL / NOT_AVAILABLE / ERROR / AUTHORITY_MISMATCH / NO_CURRENT_ACTUAL
- accessibility: Semantic labels; visible focus; 44px targets; color never sole status; text alternative; 200% text test
- acceptance: Late response cannot replace new identity or revision

## 共用图表规则

## ScenarioEditor 逐日输入细则

S5 以保存曲线 exact date set 建立15日以内行表，原始日期只读。桌面逐日行可编辑 mode、DIRECT或workforce字段与buffer；手机顶部日期选择，一次编辑一日，上一日/下一日保留草稿，日列表标记“已填写/待填写/非法”，不自行填补空日。切换mode清除互斥字段，人数严格整数、人效无默认。可显式“将本日产能输入复制到所选日期”，必须先列出目标日期并确认；只复制用户输入，不派生预测/能力结果，不作为隐藏forward-fill。未填写日期在提交前显示字段错误，额外/重复日期拒绝。

新情景从空草稿创建（无成本/人效默认），ID/version显式或由界面建议后用户确认；删除草稿需确认，最多20个。每个草稿独立验证。比较要求至少2个合法同源情景，非法情景不污染其他草稿，但不能静默忽略后声称比较全体。编辑任何参与比较的输入使原比较排名过期；单情景旧结果标记其自己的revision。提交按钮在缺少保存身份、成本ID/hash、capacity日期或字段非法时禁用，并显示具体原因。静态原型展示预声明A/B/C与代表输入布局，不实施逐日生产表单或计算。

所有输入有明确label、输入提示与inline错误，错误关联aria-describedby，提交失败将焦点移至错误摘要的首字段链接。切日不自动提交。用户误离开有脏草稿时给出保留/放弃选择；不在S4添加localStorage或生产缓存。

时间轴为服务端 target_date 升序、lead_day明确；纵轴kg，零基线明确。POINT实线；将来合法上界用不同虚线与文字图例，当前不绘制。缺失值断线，不跨缺日连接、不插值、不补零。坐标允许Number转换，仅用于像素映射，业务累计/峰值/损失/排名禁止。Tooltip/辅助表保留原Decimal字符串，可复制原值；视觉短格式不反写。窄屏减少刻度而非删除数据，所有日期仍可按钮/表格访问。

CapacityDemandChart使用同一S2日结果的demand/effective；BacklogChart独立使用closing_backlog，不把daily_overload误作queue。Quality coverage仅H7/H15，observed与nominal并排，分母与not-computable数必须可读。利用率展示derived值同时可展开exact numerator/denominator、precision50/HALF_EVEN与rounding flag，zero denominator显示不可计算，不显示0%。
