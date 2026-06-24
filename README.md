# 蓝莓加工峰值预测 Agent

本项目是一套可直接交给 Codex 分阶段开发的峰值预测系统骨架。核心原则：

1. 预测对象是“每日有效商品果到厂曲线”，不是直接回归一个峰值数字。
2. 农场种植面积是产量规模变量；加工厂建筑面积不参与峰值预测。
3. 普鲜、普青、普冻、废果默认剔除；巴松加工厂默认剔除，规则配置化。
4. 春节、采摘人员、降雨等因素通过“采摘能力与积压释放”建模，不粗暴删除数据。
5. 输出单日操作峰值、连续3日持续峰值、峰值日期、P50/P80/P90区间和影响因素解释。


## 用户极简输入模式

生产版本的默认入口只要求用户提交：

- 农场位置（文字地址、地图点位或经纬度）；
- 各品种定植亩数。

系统从历史数据库和气象数据中自动推断预计亩产、有效商品果率、成熟曲线、春节采摘实现率和不确定性，并输出：

- 1—4月逐日产能预测 P50/P80/P90；
- 单日操作峰值和连续3日持续峰值；
- 产季总曲线与品种堆叠曲线；
- 详细计算说明、历史样本和回测准确性；
- 设备能力、人员、预冷、班次和分流建议。

详细规范见 `docs/10_minimal_input_agent_spec.md` 和 `docs/11_output_report_spec.md`。亩产、商品果率、树龄、修剪日期等作为高级可选校正项，不是普通用户必填项。

## 当前历史数据基础

- `24~25到加工厂.xls`
- `原果入库汇总表到加工厂_1.xls`
- 原始列：时间、链路、农场、分场、品种、果径、入库公斤数、加工厂
- 统一分析窗口：1月1日—4月30日
- 默认剔除果径：普鲜、普青、普冻、废果
- 默认剔除加工厂：巴松加工厂

历史回测基线：在当季最终有效商品果总量和最终品种/农场/分场结构已知时，“总量 × 集中度模型”跨产季峰值 MAPE 约 12.8%，中位误差约 8.6%。该结果是模型能力上限，不等于真实提前预测误差；真实系统必须接入产量计划、物候、天气、采摘人员和跨厂调运数据。

## 技术栈

- Python 3.12
- FastAPI + Pydantic v2
- PostgreSQL 16 + SQLAlchemy 2 + Alembic
- scikit-learn；二期可增加 LightGBM
- React/Next.js 前端（方案见 `docs/06_ui_spec.md`）
- Docker Compose
- pytest
- 可选 OpenAI Agent 层：仅负责任务编排、解释和情景问答，数值计算必须调用确定性工具。

## 快速启动

```bash
cp .env.example .env
docker compose up -d db
uv sync --dev
uv run alembic -c backend/alembic.ini upgrade head
uv run uvicorn backend.app.main:app --reload
pytest
```

任务0仅初始化工程底座和健康检查。历史数据导入、业务表、预测模型和前端业务页面在后续任务中实现。

## Task 4 静态历史回测

Task 4 基于 Task 3 已持久化的 `factory_season_peak_metric` 运行三类静态基线：

- `previous_season_peak`
- `volume_previous_concentration`
- `ridge_structure`

并额外输出 `ridge_structure_factory_holdout` 诊断结果。

```bash
uv run python scripts/run_baseline_backtest.py \
  --config configs/baseline_model.yaml \
  --output-dir reports/baseline
```

说明：

- `benchmark_mode = historical_oracle`
- `production_eligible = false`
- `rolling_time_backtest = deferred_to_task_11`

当前季最终总量和最终结构 HHI 仅用于历史静态能力上限评估，不代表真实提前预测可用输入。

## 项目目录

- `AGENTS.md`：Codex 在本仓库中的强制开发规则
- `CODEX_TASKS.md`：可逐项交给 Codex 的开发任务
- `docs/`：产品、模型、数据库、导入、API、界面、回测、输出报告、建议引擎与运维方案
- `sql/schema.sql`：参考数据库结构
- `configs/`：历史导入规则、工厂别名、节假日、源文件清单
- `data/templates/`：位置、分品种面积、物候、人员、天气和极简请求模板
- `CODEX_MASTER_PROMPT.md`：可直接复制给 Codex 的总控提示词
- `app/etl/`：旧版 XLS 导入器
- `app/domain/`：峰值定义和业务规则
- `app/services/`：预测、回测、解释服务
- `app/api/`：接口
- `tests/`：核心业务规则测试

## Task 5 极简输入与参数推断

Task 5 将“位置 + 品种亩数”解析为可追溯的参数推断结果，不直接输出最终峰值预测。

```bash
uv run python scripts/import_agro_climate_zones.py \
  --file data/templates/agro_climate_zones.csv \
  --zone-version template-v1 \
  --source-name template \
  --source-version template-v1 \
  --dry-run

uv run python scripts/import_location_references.py \
  --file data/templates/farm_location_master.csv \
  --version template-v1 \
  --dry-run

uv run python scripts/import_parameter_library.py \
  --file data/templates/parameter_observations.csv \
  --version synthetic-v1 \
  --dry-run

uv run python scripts/create_minimal_planning_task.py \
  --address "云南省 红河州 弥勒市 西三镇" \
  --variety-area DX=700 \
  --as-of-date 2026-01-01 \
  --dry-run
```

Task 5 状态语义：

- `parameters_ready`：参数推断完成
- `forecast_completed`：不在本任务范围

当前仓库仅提供模板 CSV 结构，不包含真实 `dim_agro_climate_zone`、`location_reference` 与 `parameter_observation` 业务数据。

## Task 6 产量计划与物候数据

Task 6 增加 `farm × subfarm? × season × variety` 粒度的版本化计划录入，单独保存人工计划与物候字段，不覆盖 Task 5 自动参数推断结果。

```bash
uv run python scripts/import_production_plans.py \
  --file data/templates/production_plans.csv \
  --dry-run
```

Task 6 核心约定：

- 版本查询同时要求 `available_at <= as_of_date`
- 有效区间采用半开区间 `[effective_from, effective_to)`
- 同一业务键同一 `as_of_date` 只能解析出唯一有效版本
- 派生总商品果量使用 `面积 × 预计亩产 × 商品果率`
- 若显式总量与派生总量差异超过容差，按配置返回 warning 或拒绝

Task 6 只做到 `计划录入 → 版本化持久化 → 历史查询 → CSV 导入 → API`，不进入 Task 7 天气与物候时间轴。

## Task 7 天气数据与物候时间轴

Task 7 在 Task 6 的有效计划版本之上增加确定性的天气特征、物候时间轴和基温搜索，不训练自然成熟曲线，也不进入 Task 8。

```bash
uv run python scripts/import_weather_locations.py \
  --file data/templates/weather_source_locations.csv \
  --provider-code synthetic_station \
  --source-version template-v1 \
  --location-type station \
  --dry-run

uv run python scripts/import_weather_observations.py \
  --file data/templates/weather_daily_observations.csv \
  --provider-code synthetic_station \
  --source-version template-v1 \
  --location-type station \
  --dry-run

uv run python scripts/import_location_weather_mappings.py \
  --file data/templates/location_weather_mappings.csv \
  --config configs/weather_features.yaml \
  --dry-run

uv run python scripts/build_weather_features.py \
  --farm-id 1 \
  --season-id 1 \
  --variety-id 1 \
  --as-of-date 2026-03-01 \
  --feature-date 2026-03-15 \
  --dry-run

uv run python scripts/search_base_temperature.py \
  --file data/templates/base_temperature_training_manifest.csv \
  --training-cutoff 2026-04-30 \
  --scope-type variety \
  --dry-run
```

Task 7 核心约定：

- 历史天气读取必须同时满足 `available_at <= as_of_date` 与 `observation_date <= feature_date`
- 同一观测日多个修订版本只能选择预测当时可见的最新版本
- 窗口固定为 7/14/21 天，区间定义为 `[feature_date - window_days + 1, feature_date]`
- 缺失天气不得以 0 填充，覆盖率不足时返回 `unavailable`
- 基温必须从训练样本搜索，不允许硬编码固定业务值
- Task 7 只输出天气特征、物候时间轴与基温搜索结果，不输出每日成熟量和峰值预测

## Task 8 自然成熟曲线模型

Task 8 在 Task 6 计划版本和 Task 7 天气/物候/基温能力之上，训练 `season × farm/subfarm × variety` 粒度的自然成熟代理曲线，并输出逐日自然成熟量，不进入 Task 9 的采摘能力、积压或到厂状态方程。

```bash
env UV_CACHE_DIR=.uv-cache uv run python scripts/train_maturity_curve.py \
  --file data/templates/maturity_curve_training_manifest.csv \
  --training-cutoff 2026-04-30 \
  --config configs/maturity_curve.yaml \
  --dry-run

env UV_CACHE_DIR=.uv-cache uv run python scripts/forecast_natural_maturity.py \
  --model-run-id 1 \
  --farm-id 1 \
  --season-id 1 \
  --variety-id 1 \
  --as-of-date 2026-03-01 \
  --prediction-start-date 2026-03-01 \
  --prediction-end-date 2026-03-07 \
  --facility-type open_field \
  --expected-marketable-total-kg 96000 \
  --dry-run
```

Task 8 核心约定：

- 训练标签明确为 `smoothed_arrival_proxy_for_natural_maturity`
- 区域共享曲线按 `climate_zone × variety` 建模，并向 `province × variety` / `variety_global` 层级显式回退
- P50 每日量执行质量守恒，对账到 `expected_marketable_total_kg`
- JSONB artifact 和报告 payload 只写 canonical JSON 类型，Decimal 以稳定字符串持久化
- 训练和预测 source signature 必须包含 manifest、计划版本、天气映射、天气 observation fingerprint、基温 run、配置和随机种子
- 只输出自然成熟量曲线及其区间，不输出实际到厂量或最终加工厂峰值
- Task 8 明确不进入 Task 9
