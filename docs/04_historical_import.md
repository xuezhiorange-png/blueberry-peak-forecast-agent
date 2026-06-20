# 历史数据导入参考

## 1. 原始文件结构

两个历史文件均为旧版 `.xls`，含多个 Sheet，每个 Sheet 表头相同：

| 原列 | 目标字段 | 类型 | 说明 |
|---|---|---|---|
| 时间 | receipt_date | date | 兼容字符串和Excel日期 |
| 链路 | link_name_raw | text | 原样保留 |
| 农场 | farm_raw | text | 后续映射主数据 |
| 分场 | subfarm_raw | text | 后续映射主数据 |
| 品种 | variety_raw | text | 去除“蓝莓原果”前缀 |
| 果径 | grade_raw | text | 普鲜等在curated层标记排除 |
| 入库公斤数 | weight_kg | numeric | raw层允许空值、零值和负值；通过质量字段标记 |
| 加工厂 | factory_raw | text | 使用别名表归一化 |

## 2. 导入流程

1. 计算文件 SHA256；
2. 创建或重用 `ingest_file`；
3. 遍历全部 Sheet；
4. 按严格表头校验读取，并支持 manifest 中显式声明的表头别名；
5. 生成行指纹；
6. 归一化品种和加工厂；
7. 评估质量阈值；
8. 仅当文件通过校验时，将 raw 行作为单文件原子事务写入；
9. 标记 `is_analysis_eligible`；
10. 输出质量报告。

如果导入失败，`ingest_file` 仍需保留，记录 `status=failed`、`error_message`、`finished_at` 和当时已形成的质量摘要；raw 行不得留下半文件状态。

任务2只建立 `ingest_file` 和 `fact_receipt_raw`。`fact_receipt_daily` 聚合、峰值计算和任何模型特征生成延期到任务3。

## 3. 行指纹

建议：

任务2区分两类指纹：

- `source_row_fingerprint`：`sha256(file_sha256|sheet_name|source_row_number)`，用于严格技术幂等并建立唯一约束；
- `business_fingerprint`：`sha256(season|date|normalized_factory|normalized_farm|normalized_subfarm|normalized_variety|normalized_grade|round(weight,6))`，用于疑似业务重复识别，只建普通索引。

没有业务流水号时，不能百分百区分“真实相同的两笔”与重复行，因此 raw 层仍应保留原文件、Sheet和行号。是否去重必须可配置并输出争议清单。

## 4. 有效分析条件

```text
month in [1,2,3,4]
and grade not in [普鲜, 普青, 普冻, 废果]
and normalized_factory != 巴松加工厂
and weight_kg > 0
and factory is known unless rules explicitly allow unknown factories
and variety is known unless rules explicitly allow unknown varieties
```

## 5. 数据质量报告

- 文件与Sheet行数；
- 空日期/非法日期；
- 空加工厂、农场、分场、品种；
- 未知加工厂别名；
- 未知品种；
- 负重量/零重量；
- 疑似重复；
- 原始重量、有效重量、各类剔除重量；
- 日期范围和异常5月数据。
- 文件内重复、跨 Sheet 重复、跨文件重复；
- 实际 Sheet、缺失 Sheet、额外 Sheet；
- 按排除原因统计的行数和重量。

`fatal_quality_thresholds` 至少支持非法日期和非法重量的最大数量或比例。超过阈值时，dry-run 返回非0，正式导入写入 `failed` 状态但不写 raw 行。

文本 NFKC、首尾空格清理、连续空格折叠和全角半角统一是内置规范化行为，不通过 `import_rules.yaml` 单独开关；别名文件只负责显式映射和品种前缀移除。

## 6. 导入命令

```bash
python scripts/import_history.py \
  --manifest configs/source_manifest.yaml \
  --rules configs/import_rules.yaml \
  --aliases configs/factory_aliases.yaml \
  --dry-run
```

确认报告后去掉 `--dry-run` 正式写库。
