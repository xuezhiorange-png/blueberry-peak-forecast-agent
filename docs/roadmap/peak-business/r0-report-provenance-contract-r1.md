# Peak Business R0 — 业务报告与可追溯性合同候选 R1

状态：报告字段/数据来源设计；无报告 API、导出或生产文档生成实现。

## 1. 报告权威规则

业务报告是服务端权威 Forecast Intelligence 投影的只读呈现，不是第二计算器。每个报告结果必须取自一份完整、可验证的 saved response 与同一 forecast identity；多页、多个 metric 可以组合，但必须逐项留有来源/状态，不可拼出不存在的 READY 全景。

* 客户端不得计算峰值、rolling window、总量、浓度、工厂 allocation、capacity utilization、损失或排名。
* 原始 Decimal 字符串、日期、业务层级、source result hash、adapter/engine/projection hash 原值保留；不得将展示格式、图表坐标或下载软件的小数格式反写为权威数值。
* 报告生成时间 `report_generated_at` 只表示导出时间，不是预测签发时间或输入信息可用时间。
* `origin_date` 是预测业务起点；除非来源含经验证的 `as_issued_at`，不可称为预测发布时间。
* 如果报告引用的是模拟，必须保存用户所选 capacity rows、cost contract identity/hash、planning level、scenario identity/hash、S2 engine result/comparison hash，并明显注明它是条件情景，非实际业务动作。
* 未授权的 source、缺失字段、hash 漂移或不兼容 authority 不通过报告层“补齐”；对应 section 记 `NOT_AVAILABLE`、`PARTIAL` 或 `AUTHORITY_MISMATCH`。

## 2. 推荐报告 Manifest

```json
{
  "schema_version": "PEAK_BUSINESS_TRACEABLE_REPORT_R1",
  "report_id": "server-issued opaque identifier",
  "report_generated_at": "RFC3339 timestamp",
  "metric_contract_version": "owner-approved version or null",
  "forecast_identity": {
    "source_kind": "...",
    "forecast_family": "...",
    "run_id": "...",
    "hierarchy_level": "BASE|REGION|COMPANY",
    "entity_id": "...",
    "target_season": "...",
    "origin_date": "YYYY-MM-DD",
    "baseline_id": "...",
    "policy_version": "...",
    "source_result_hash": "sha256"
  },
  "target_date_range": {"start": "...", "end": "...", "available_days": 0},
  "business_date_basis": {"calendar": "...", "timezone_policy_version": "..."},
  "forecast_source": {"source_projection_hash": "sha256|null", "evidence_mode": "SAVED_FORECAST"},
  "metric_sections": [],
  "factory_assignment_authority": {"status": "NOT_AVAILABLE|READY|PARTIAL", "revision": null, "source_hash": null},
  "factory_capacity_authority": {"status": "NOT_AVAILABLE|READY|PARTIAL", "revision": null, "source_hash": null},
  "decision_scenario": null,
  "privacy_and_governance": {"actual_data_used": false, "synthetic_cost": false}
}
```

以上为字段示例，不是批准的 schema。具体 URL、存储方式、可见字段和保留期限待 Owner/安全/业务授权决定。外部业务报表不得泄漏未授权 run 是否存在；内部脱敏审计和对用户的固定 denial 文案分离。

## 3. Metric section 合同

每个 metric section 至少包含：

```text
metric_id
metric_definition_version
status + unavailable_reason
value_decimal_string / value_unit (not present when unavailable)
numerator / denominator (for ratio, when applicable)
date/window start + end + business date basis
scope identity + hierarchy authority snapshot
source_result_hash + source_projection_hash + metric_projection_hash
available/expected date count + child coverage/candidate window counts
interpretation and prohibited claims
```

建议报告章节：

1. **Forecast identity & coverage**：family, run, entity/hierarchy, season, origin date, requested/available period, completeness, baseline/policy, saved source result hash。
2. **Daily forecast**：仅打印已返回的合法日期行；缺日期断开，不补零或插值。
3. **Single-day peak**：R0-A 候选结果、日期和 tie rule。
4. **Rolling-7 peak**：R0-B1 候选结果、start/end、9/实际可用窗口数；明确与 H7 prefix 不同。
5. **High-harvest period**：阈值、方法未批准时显示 `NOT_AVAILABLE_THRESHOLD_UNAPPROVED`，不显示预警。
6. **Concentration**：仅显示经批准 metric/window/denominator；否则标记 pending/not available。
7. **Factory assignment/capacity**：assignment revision、allocation completeness、capacity basis、capacity source revision/period；当前均 NOT_AVAILABLE。
8. **Scenario**：显式 DIRECT/WORKFORCE 输入、planning level、selected synthetic cost id/hash、loss unit、date set、server result/ranking hashes；合成损失绝不显示为人民币。
9. **Quality research**：只有 source-authorized historical M1 summary 时作为 retrospective observation 单列；不称 Operational Peak run precision/current performance。

## 4. 时间与结果追溯

如果来源未来具备时间戳，分别记录 `forecast_origin_business_date`、`as_issued_at`、`source_available_at`、`ingested_at`、`actual_available_at`、`scoring_cutoff`。缺少的字段保持 null/status `NOT_PROVEN`；不能以日期、文件 mtime、DB created_at、S2 Shanghai midnight adapter anchor推断。当前没有 actual scoring 授权，报告不得访问/包含当季 actual。

报告 bytes 可做 canonical serialization，并以 manifest hash 绑定：报告 schema version、forecast source/result hash、metric policy/version、各 section projection hash、factory mapping/capacity source revision（如合法存在）、scenario request/result hash（如适用）。报告 hash 是导出物 hash，不冒充源预测 hash。PDF/CSV 另存导出格式、生成器版本和内容 hash，不能用显示文件覆盖机器 manifest。

## 5. 当前不可用项与边界

```text
ROLLING_7DAY_PEAK_AUTHORITY=NOT_AVAILABLE_IN_V0_17_READ_CONTRACT
HIGH_PERIOD_THRESHOLD=PENDING_OWNER_DECISION
CONCENTRATION_THRESHOLD=PENDING_OWNER_DECISION
FACTORY_ASSIGNMENT_AUTHORITY=NOT_AVAILABLE
FACTORY_PROCESSING_CAPACITY_AUTHORITY=NOT_AVAILABLE
HISTORICAL_OP_PEAK_ACCURACY=NOT_VALIDATED
STRICT_PIT=false
PROSPECTIVE_ACCURACY_VALIDATED=false
CURRENT_SEASON_ACTUAL_AVAILABLE=false
```

静态/合成原型中的数值必须标为 `SYNTHETIC DESIGN FIXTURE — NOT PRODUCTION DATA`。本轮测试也只验证字段/状态/完整性合同，不生成真实报告、不调用业务数据库、不读取真实预测曲线或 actual。
