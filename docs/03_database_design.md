# 数据库与主数据设计

本文档定义任务1范围内的主数据模型。任务1只建立主数据表、ORM、迁移和 CRUD API，不创建历史事实表、预测表、天气表、人员表或模型运行表。

## 设计原则

- PostgreSQL 是约束来源，所有主键、唯一约束、外键和检查约束必须由 Alembic 迁移真实创建。
- SQLAlchemy ORM、Alembic 迁移和 `sql/schema.sql` 必须保持同一字段语义、数据类型和约束名称。修改任一层时必须同步另外两层。
- API 只返回 Pydantic schema，不直接暴露 SQLAlchemy 对象内部状态。
- 删除策略保守：外键默认限制删除，不使用级联删除清除未来事实数据。
- `factory` 和 `holiday` 支持 `active` 软停用；其他主数据允许 DELETE，但只有未被其他记录引用时才能删除。

## 表结构

### dim_season

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 非空，唯一 |
| start_date | DATE | 非空 |
| end_date | DATE | 非空，`end_date >= start_date` |

### dim_factory

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 唯一，可空 |
| name | TEXT | 非空，唯一 |
| region_name | TEXT | 可空 |
| latitude | NUMERIC(9,6) | 可空，`-90 <= latitude <= 90` |
| longitude | NUMERIC(9,6) | 可空，`-180 <= longitude <= 180` |
| altitude_m | NUMERIC(8,2) | 可空 |
| active | BOOLEAN | 非空，默认 true |

### dim_farm

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| name | TEXT | 非空，唯一 |
| latitude | NUMERIC(9,6) | 可空，`-90 <= latitude <= 90` |
| longitude | NUMERIC(9,6) | 可空，`-180 <= longitude <= 180` |
| altitude_m | NUMERIC(8,2) | 可空 |

### dim_subfarm

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| farm_id | BIGINT | 非空，外键到 `dim_farm.id`，限制删除 |
| name | TEXT | 非空 |
| altitude_m | NUMERIC(8,2) | 可空 |

唯一约束：`UNIQUE(farm_id, name)`。删除仍被分场引用的农场必须返回 409。

### dim_variety

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 非空，唯一 |
| name | TEXT | 非空 |

任务1不插入正式品种清单。

### dim_grade

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| code | TEXT | 非空，唯一 |
| is_analysis_eligible_default | BOOLEAN | 非空，默认 true |

任务1不把“普鲜、普青、普冻、废果”等生产规则硬编码进迁移；后续导入规则通过配置和 curated 层处理。

### dim_holiday

| 字段 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | 主键 |
| season_id | BIGINT | 非空，外键到 `dim_season.id`，限制删除 |
| code | TEXT | 非空 |
| name | TEXT | 非空 |
| start_date | DATE | 非空 |
| end_date | DATE | 非空，`end_date >= start_date` |
| region_name | TEXT | 可空；空值表示全局节假日 |
| active | BOOLEAN | 非空，默认 true |
| created_at | TIMESTAMPTZ | 非空，默认 now() |
| updated_at | TIMESTAMPTZ | 非空，默认 now() |

唯一约束：`UNIQUE(season_id, code)`。

`dim_holiday` 只维护节假日时间窗口。春节采摘能力、积压释放和预测影响属于后续任务，不在任务1实现。

## API

统一前缀：`/api/v1/master-data`

| 资源 | 路径 |
|---|---|
| seasons | `/api/v1/master-data/seasons` |
| factories | `/api/v1/master-data/factories` |
| farms | `/api/v1/master-data/farms` |
| subfarms | `/api/v1/master-data/subfarms` |
| varieties | `/api/v1/master-data/varieties` |
| grades | `/api/v1/master-data/grades` |
| holidays | `/api/v1/master-data/holidays` |

每类资源支持：

- `POST /` 创建，成功返回 201；
- `GET /` 列表，成功返回 200；
- `GET /{id}` 按 ID 查询，成功返回 200；
- `PATCH /{id}` 部分更新，成功返回 200；
- `DELETE /{id}` 删除，成功返回 204。

列表参数：

- `limit` 默认 50，最大 100；
- `offset` 默认 0；
- 默认按 `id ASC` 稳定排序；
- `factories` 支持 `active`；
- `subfarms` 支持 `farm_id`；
- `holidays` 支持 `season_id`、`region_name`、`active`。

错误返回：

- 资源不存在：404；
- 唯一约束冲突：409；
- 外键冲突或删除被引用数据：409；
- 输入校验失败：422；
- 不返回 SQL、连接串、密码或数据库异常原文。

创建不存在的 `farm_id`、`season_id` 等外键引用统一返回 409。

## ORM、Alembic 与 schema.sql 一致性

- ORM 模型位于 `backend/app/models/`，使用 SQLAlchemy 2 typed declarative API。
- Alembic 迁移位于 `backend/alembic/versions/`，是数据库结构的发布记录。
- `sql/schema.sql` 是面向评审和后续任务的参考 SQL，必须与当前 ORM 和最新 migration 保持一致。
- 新字段或约束必须同时更新 ORM、migration 和 `sql/schema.sql`，并用 PostgreSQL 集成测试验证。
