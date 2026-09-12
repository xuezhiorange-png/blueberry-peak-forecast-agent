# R3A 账本资格：仅待一个业务事实确认

TASK_ID=NEXT_VERSION_MULTI_SEASON_LEDGER_QUALIFICATION_AND_SHAPE_TRAINING_R3A。
继续 Draft #612，base `74881e8611cfea0eff3d1b5631520825c52e7018`。

## 实际结论

RESULT=NEEDS_SINGLE_SOURCE_SEMANTIC_CONFIRMATION。
两季均 SOURCE_EXPORT_COMPLETENESS=NOT_ESTABLISHED；当前 strict 数量为0，不执行真实训练/评分。
35个同名配对中，**保山华兴农场、保山杨柳农场、建水南庄基地**通过除完整导出语义之外的资格检查。
其余32个配对仍有边界或active-span global unknown等原因；不会因确认一个事实就放行全部35个。
这不是缺面积，不要求第二批数据，也不是新的治理任务。

唯一需要用户确认：

> 这两个XLS是否为对应期间扫码称重系统的完整导出，某农场某日无记录时是否可解释为当天该农场入库/采摘量为0？

## 复用与新增判定

不重复附件身份/新旧重叠审计。使用R3 hash绑定的input_manifest、canonical_daily_shape及pair清单；
新24–25仍是唯一来源，不拼接仓库旧源。R3已读取全部sheet的同构七列及分页，
65535数据行分页与一致字段支持“同一导出分页”解释，但不能证明此前未筛选，也不能证明全系统交易完整性。
不能由连续业务记录、无负数/重复或文件名反推出该业务事实。没有额外导出完整性证明。

source-active使用**所有农场**的合法已观察日，不只35个配对。仅在各文件实际覆盖期计数：

| 产季 | file_start..file_end | 全源无记录日 |
|---|---|---:|
| 23–24 |2023-07-26..2024-06-30|44|
| 24–25 |2024-07-01..2025-05-27|8|

取消R3“必须覆盖July1..June30全历日”的资格前置条件，改为用户指定的file边界缓冲14天。
first/last positive只作**资格诊断**，不是未来预测输入或模型日期对齐锚点。
全源无记录日保持UNKNOWN_GLOBAL_NO_RECORD及数量空值，绝不自动写0。
source-active当天某农场缺行先计source_active_absence_days；完整性未建立时source_active_zero_days=0，
不是说没有这些缺行，而是没有授权将其落为0。确认后仅能标RECORDED_LEDGER_ZERO，不能称生物学零产量。

每范围检查正总量、exact配对、14天两端边界、冲突及active harvest span内global unknown。
总量字段明确为RECORDED_EXPORT_TOTAL_NOT_BIOLOGICAL_TOTAL，未将其冒充未来产量。
35配对均当前DIAGNOSTIC_ONLY；eligible_if_source_confirmed仅用于指出待确认项，不参与任何正式指标。
窗口外global unknown仍保留，不把它们当零；没有构造或评分任何真实shape。

## 产物和验证

私有目录 `/Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a`：

- farm_season_qualification_r3a.csv（全部144农场-季，明确配对状态）
- paired_farm_qualification_r3a.csv（35配对）
- source_active_calendar_23_24.csv
- source_active_calendar_24_25.csv
- qualification_summary_r3a.json / artifact_manifest.json

[公开汇总/hash](evidence/ledger-qualification-r3a.json)。不上传逐行业务数据。
R1/R2所有产物与R3快照逐文件hash核对PASS。

真实执行：

```bash
.venv/bin/python -m scripts.run_ledger_r3a --r3 /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3 --output /Users/charles/Documents/blueberry-area-yield-artifacts/shape-r3a
```

本地优先：新增6测试覆盖active缺行语义、global unknown、14日边界、exact身份和不可升级生物学零。
area_yield/planning/maturity/core_forecast非PG相关回归共404 passed；Ruff、format、Mypy PASS。
代码、实际矩阵、证据都在一次最终push前冻结，不用GitHub调试；新head CI作为最终验证。
旧run34677091130只对应旧head，不作为本轮通过证据。required CI/full-suite-canary不绕过。

本轮无真实fit/评分、无旧TEST/S4/预算操作、无天气、无总亩产模型、无替换旧基线。
保持Draft，不Ready/Merge/Release。FINAL_STOP_GATE=COORDINATOR_R3A_LEDGER_AND_SHAPE_REVIEW。
