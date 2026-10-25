# V0_20 S0 — 数据标准与已有合同复用

## 固定历史来源

前端 `v0_20_vocabulary.json` 是基线 Git 提交中 V0.9 注册表的只读投影。事件代码、适用制度、强度要求、物候状态均来自原合同，未新增预测效应、产量系数或峰日偏移。Python 一致性测试从固定历史 Git Blob 验证来源 SHA256，避免未来合法源码变化破坏历史审计。

| 对象 | 原有字段/定义 | 本版处理 |
| --- | --- | --- |
| Farm / Subfarm / Variety | `master_data.py` 的 ID/业务键/关系 | 保留来源键；没有显式权威连接就 UNMAPPED；不模糊匹配 |
| 地块 | 现有主数据不能证明任意 Excel 地块身份 | `source_plot_id` 保留，`plot_authority_id=null`；不建立新权威地块 |
| Production Plan | 面积、树龄、修剪日、三个普通开花日、版本和日期级 available_at | 普通开花不映射百分比；日期可用性不证明严格 PIT |
| V0.9 管理 | 已登记类型、三制度、强度表达合同 | 多次操作独立；数值强度需方法/单位/分母/范围/来源；缺失不补系数 |
| V0.9 物候 | 状态机中的明确阶段 | 仅明确观测才映射，保留方法/样本/质量；不运行生物学推导 |
| V0.6 PIT | observed_at / recorded_at / known_at 及因果可见性 | 分别保留，不互相代替，不用当前处理时间回填 |

三种制度 `DECIDUOUS_NATURAL`、`DECIDUOUS_FORCING`、`EVERGREEN` 单独分组。产季用连续双年字符串；不同产季不合并为同一冲突或统计事实。

## 统一记录

共有：来源基地/农场/分场/地块/品种键、产季、制度、`PLANNED/OBSERVED/UNKNOWN`、logical_id、revision_id、supersedes_revision、source_reference、source_version、observed_at、recorded_at、known_at。

面积：`PLANTED/PRODUCTIVE/EFFECTIVE/UNKNOWN`，非负十进制数值（最多六位），单位、生效起止、树龄/种植年。只将明确 `mu/亩` 规范化为 mu；其他单位保留并阻断单位证明，不擅自换算。

事件：原始类型与注册类型分别保存，日期/结束日、修剪类型、方法、声明次数、强度类型/值/单位/分母。次数不用于虚构事件。UNKNOWN 既不等于计划，也不等于实际。

物候：原始阶段、明确 canonical stage 或普通 Production Plan 字段、日期、方法、样本范围、质量。开始/盛花/结束绝不自动映射为 BLOOM_10/50/90，即使用户把普通日期列的声明类型选为百分比也保留普通语义。

日期保留 raw、precision、lower_date、upper_date、instant。日/月/年和无时区本地时间的 instant=null；明确带时区的原始时间才可规范化 instant。Excel 数字日期即使解析出时钟，也标记 `EXCEL_SERIAL_TIMEZONE_UNPROVEN`，不附加可信时区。全部来源仍为 `PIT_NOT_PROVEN`，不因字段齐全自动通过严格 PIT。

## 权威与隐私

应用本轮无真实农事权限，不查询主数据库或私有文件。合成样例的显式精确连接仅属于合成参考，不是全局实体授权。任意文件只在当前浏览器内存中处理。准备包下载是用户主动本地保存，不进入服务端登记。JSON 保留用户的原始内容，应按文件自身敏感性妥善保管；本次验收只使用合成内容。
