# V0.3-S3-A2 Incumbent forecast V0.2/S3 SQL table-name authority contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-sql-table-authority-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=2cfc2c0d3d576f24f574a30cfb27cefc46274587
BASE_MAIN_TREE_SHA=8cd09910e90dc9a08a9cf63fb92ef30e3329ffdb
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-sql-table-authority-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-sql-table-authority-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **V0.2/S3 SQL table-name authority** contract freeze
after harvest source R1 (#350). Postgres obtain R1 is landed; default obtain remains
`()`. This contract freezes the read-only Alembic audit of existing table names. It
does **not** implement live postgres read, issue grants, execute R1, or flip
`NO_VERSIONED` / `NO_LIVE_S2` / `AVAILABLE` / `VERIFIED`.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
~~~

## 1. Why this contract (unique gap after #350)

1. Harvest source R1 landed; default harvest obtain still `()`.
2. Postgres obtain R1 landed; parent contract §3.1 requires frozen table names.
3. No prior contract audited Alembic `op.create_table` names against replay grain.
4. Without audit, future R1 could bind `core_forecast_daily_row` or invent SQL.
5. This contract freezes zero-MATCH audit only.

## 2. Upstream bindings (reference only)

~~~text
PARENT_POSTGRES_OBTAIN_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
HARVEST_SOURCE_R1_EVIDENCE_JSON_SHA256=bef3cedecf7498064f9929e7c40b863ed8ad028d0cf0e9f30e7b547bc7af408e
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
~~~

## 3. Alembic audit summary

~~~text
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
~~~

| table_name | alembic_revision_path | verdict | reason |
|---|---|---|---|
| `dim_season` | `backend/alembic/versions/0002_master_data.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `dim_factory` | `backend/alembic/versions/0002_master_data.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `dim_farm` | `backend/alembic/versions/0002_master_data.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `dim_variety` | `backend/alembic/versions/0002_master_data.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `dim_grade` | `backend/alembic/versions/0002_master_data.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `dim_subfarm` | `backend/alembic/versions/0002_master_data.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `dim_holiday` | `backend/alembic/versions/0002_master_data.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `ingest_file` | `backend/alembic/versions/0003_historical_ingest.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `fact_receipt_raw` | `backend/alembic/versions/0003_historical_ingest.py` | NOT_MATCH | carries_kg_or_weight_columns:weight_kg_raw,weight_kg,is_weight_valid; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `analytics_build_run` | `backend/alembic/versions/0004_daily_facts_peak_metrics.py` | NOT_MATCH | carries_kg_or_weight_columns:source_eligible_weight_kg; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `fact_receipt_daily` | `backend/alembic/versions/0004_daily_facts_peak_metrics.py` | NOT_MATCH | carries_kg_or_weight_columns:weight_kg; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `factory_season_peak_metric` | `backend/alembic/versions/0004_daily_facts_peak_metrics.py` | NOT_MATCH | carries_kg_or_weight_columns:total_weight_kg,single_day_peak_kg,stable_median_3d_peak_kg,mean_3d_peak_kg,unknown_farm_weight_share...; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `baseline_backtest_run` | `backend/alembic/versions/0005_baseline_backtest.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `baseline_backtest_result` | `backend/alembic/versions/0005_baseline_backtest.py` | NOT_MATCH | carries_kg_or_weight_columns:actual_stable_peak_kg,predicted_stable_peak_kg,absolute_error_kg,signed_error_kg; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `dim_agro_climate_zone` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `climate_zone_import_run` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `location_reference` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `parameter_library_version` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `parameter_observation` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | carries_kg_or_weight_columns:sample_weight; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `minimal_forecast_task` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `parameter_inference_run` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `parameter_inference_result` | `backend/alembic/versions/0006_minimal_input_parameters.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `farm_season_variety_plan` | `backend/alembic/versions/0007_prod_plan_phenology.py` | NOT_MATCH | carries_kg_or_weight_columns:planted_area_mu,expected_yield_kg_per_mu,expected_total_marketable_kg; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `production_plan_import_run` | `backend/alembic/versions/0007_prod_plan_phenology.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `weather_source_location` | `backend/alembic/versions/0008_weather_timeline.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `weather_daily_observation` | `backend/alembic/versions/0008_weather_timeline.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `weather_import_run` | `backend/alembic/versions/0008_weather_timeline.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `location_weather_mapping` | `backend/alembic/versions/0008_weather_timeline.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `base_temperature_search_run` | `backend/alembic/versions/0008_weather_timeline.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `weather_feature_run` | `backend/alembic/versions/0008_weather_timeline.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `maturity_model_run` | `backend/alembic/versions/0009_natural_maturity_curve.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `maturity_model_artifact` | `backend/alembic/versions/0009_natural_maturity_curve.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `maturity_forecast_run` | `backend/alembic/versions/0009_natural_maturity_curve.py` | NOT_MATCH | carries_kg_or_weight_columns:expected_marketable_total_kg; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `maturity_daily_prediction` | `backend/alembic/versions/0009_natural_maturity_curve.py` | NOT_MATCH | carries_kg_or_weight_columns:p50_kg,p80_kg,p90_kg,cumulative_p50_kg,cumulative_p80_kg...; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `harvest_state_run` | `backend/alembic/versions/0010_harvest_state_persistence.py` | NOT_MATCH | harvest_state_quantile_persistence_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `harvest_state_daily_pool_row` | `backend/alembic/versions/0010_harvest_state_persistence.py` | NOT_MATCH | carries_kg_or_weight_columns:opening_mature_inventory_kg,natural_maturity_supply_kg,available_mature_quantity_kg,mature_inventory_loss_quantity_kg,harvestable_mature_quantity_kg...; harvest_state_quantile_persistence_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id |
| `harvest_state_daily_member_row` | `backend/alembic/versions/0010_harvest_state_persistence.py` | NOT_MATCH | carries_kg_or_weight_columns:opening_mature_inventory_kg,natural_maturity_supply_kg,available_mature_quantity_kg,mature_inventory_loss_quantity_kg,harvestable_mature_quantity_kg...; harvest_state_quantile_persistence_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id |
| `harvest_state_cohort_transition_row` | `backend/alembic/versions/0010_harvest_state_persistence.py` | NOT_MATCH | carries_kg_or_weight_columns:opening_quantity_kg,new_supply_quantity_kg,quantity_before_loss_kg,mature_inventory_loss_quantity_kg,quantity_before_harvest_kg...; harvest_state_quantile_persistence_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id |
| `harvest_state_future_arrival_row` | `backend/alembic/versions/0010_harvest_state_persistence.py` | NOT_MATCH | carries_kg_or_weight_columns:quantity_kg; harvest_state_quantile_persistence_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id |
| `residual_model_training_run` | `backend/alembic/versions/0011_residual_model.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `residual_model_manifest_row` | `backend/alembic/versions/0011_residual_model.py` | NOT_MATCH | carries_kg_or_weight_columns:observed_effective_receipt_kg,structural_p50_kg,structural_p80_kg,structural_p90_kg,residual_label_kg...; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `residual_model_artifact` | `backend/alembic/versions/0011_residual_model.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `residual_model_prediction_run` | `backend/alembic/versions/0011_residual_model.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `residual_model_prediction_row` | `backend/alembic/versions/0011_residual_model.py` | NOT_MATCH | carries_kg_or_weight_columns:structural_p50_kg,structural_p80_kg,structural_p90_kg,raw_residual_p50_kg,raw_residual_p80_kg...; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `residual_model_execution_attempt` | `backend/alembic/versions/0011_residual_model.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_run` | `backend/alembic/versions/0012_rolling_backtest.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_node` | `backend/alembic/versions/0012_rolling_backtest.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_attempt` | `backend/alembic/versions/0012_rolling_backtest.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_resolved_input` | `backend/alembic/versions/0012_rolling_backtest.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_availability_audit` | `backend/alembic/versions/0012_rolling_backtest.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_dag_snapshot` | `backend/alembic/versions/0012_rolling_backtest.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_stage_event` | `backend/alembic/versions/0013_rolling_backtest_orchestration.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_orchestration_snapshot` | `backend/alembic/versions/0013_rolling_backtest_orchestration.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `harvest_state_replay_source_visibility_audit` | `backend/alembic/versions/0015_task11_phase3_schema_gap.py` | NOT_MATCH | harvest_state_quantile_persistence_not_incumbent_artifact; missing_model_id; missing_forecast_quantile |
| `core_forecast_run` | `backend/alembic/versions/0017_core_forecast_run_persistence.py` | NOT_MATCH | V0_1_core_forecast_persistence_docstring_not_replay_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `core_forecast_daily_row` | `backend/alembic/versions/0017_core_forecast_run_persistence.py` | NOT_MATCH | daily_curve_grain_date_plus_quantile_without_forecast_cutoff; V0_1_core_forecast_persistence_docstring_not_replay_grain; missing_forecast_cutoff_at; missing_model_id |
| `core_forecast_metric` | `backend/alembic/versions/0017_core_forecast_run_persistence.py` | NOT_MATCH | carries_kg_or_weight_columns:single_day_peak_quantity_kg,sustained_7day_cumulative_quantity_kg,sustained_7day_daily_average_kg_per_day,season_cumulative_effective_marketable_kg; V0_1_core_forecast_persistence_docstring_not_replay_grain; missing_forecast_cutoff_at; missing_model_id |
| `actual_harvest_import_batch` | `backend/alembic/versions/0018_actual_harvest_import_staging.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_import_record` | `backend/alembic/versions/0018_actual_harvest_import_staging.py` | NOT_MATCH | carries_kg_or_weight_columns:actual_harvest_quantity_kg; carries_harvest_business_date:harvest_business_date; actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_mapping_policy_registry` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_mapping_registry_entry` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_run` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_attempt` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_mapping_snapshot` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_result` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_record` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_mapping_evidence` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_error` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_lineage_node` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_lineage_edge` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_lineage_basis` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_validation_lineage_basis_member` | `backend/alembic/versions/0019_actual_harvest_validation_evidence.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_commit_manifest` | `backend/alembic/versions/0020_actual_harvest_commit_manifest.py` | NOT_MATCH | actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_label_snapshot` | `backend/alembic/versions/0021_actual_harvest_label_snapshot.py` | NOT_MATCH | carries_harvest_business_date:harvest_date_start,harvest_date_end; actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_label_snapshot_winner` | `backend/alembic/versions/0021_actual_harvest_label_snapshot.py` | NOT_MATCH | carries_kg_or_weight_columns:actual_harvest_quantity_kg; carries_harvest_business_date:harvest_business_date; actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_label_snapshot_label` | `backend/alembic/versions/0021_actual_harvest_label_snapshot.py` | NOT_MATCH | carries_kg_or_weight_columns:exact_decimal_quantity_sum_kg; carries_harvest_business_date:harvest_business_date; actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `actual_harvest_label_snapshot_exclusion` | `backend/alembic/versions/0021_actual_harvest_label_snapshot.py` | NOT_MATCH | carries_harvest_business_date:harvest_business_date_or_null; actual_harvest_lane_not_forecast_replay; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `core_forecast_code_authority` | `backend/alembic/versions/0023_historical_backtest_binding.py` | NOT_MATCH | V0_1_core_forecast_persistence_docstring_not_replay_grain; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_manifest` | `backend/alembic/versions/0023_historical_backtest_binding.py` | NOT_MATCH | rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `rolling_backtest_binding_row` | `backend/alembic/versions/0023_historical_backtest_binding.py` | NOT_MATCH | carries_kg_or_weight_columns:forecast_value_kg,actual_value_kg; carries_alignment_or_catalog_cell_fields:physical_alignment_status; rolling_backtest_orchestration_not_incumbent_artifact_grain; missing_model_id; missing_forecast_quantile |
| `quality_evaluation_run` | `backend/alembic/versions/0024_s3_forecast_quality_persistence.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `quality_metric_result` | `backend/alembic/versions/0024_s3_forecast_quality_persistence.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `quality_breakdown_result` | `backend/alembic/versions/0024_s3_forecast_quality_persistence.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `naive_baseline_run` | `backend/alembic/versions/0024_s3_forecast_quality_persistence.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `model_baseline_comparison` | `backend/alembic/versions/0024_s3_forecast_quality_persistence.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `quality_evaluation_manifest` | `backend/alembic/versions/0024_s3_forecast_quality_persistence.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `model_baseline_comparison` | `backend/alembic/versions/0025_s3_model_baseline_comparison.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `model_baseline_comparison` | `backend/alembic/versions/0025_s3_model_baseline_comparison.py` | NOT_MATCH | forecast_quality_or_baseline_metrics_not_incumbent_artifact; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `core_forecast_marketable_policy` | `backend/alembic/versions/0026_s5_round_a2_policy_and_trial_resource_binding.py` | NOT_MATCH | V0_1_core_forecast_persistence_docstring_not_replay_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `core_forecast_marketable_policy_entry` | `backend/alembic/versions/0026_s5_round_a2_policy_and_trial_resource_binding.py` | NOT_MATCH | V0_1_core_forecast_persistence_docstring_not_replay_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `trial_resource_binding` | `backend/alembic/versions/0026_s5_round_a2_policy_and_trial_resource_binding.py` | NOT_MATCH | missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `trial_forecast_evidence` | `backend/alembic/versions/0027_s5_a2_forecast_evidence_persistence.py` | NOT_MATCH | carries_kg_or_weight_columns:planting_area_mu; trial_forecast_evidence_not_distinct_replay_grain; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_raw_source_artifact` | `backend/alembic/versions/0029_s2_lane_a_raw_ingestion_lineage.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_raw_import_batch` | `backend/alembic/versions/0029_s2_lane_a_raw_ingestion_lineage.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_source_row_lineage` | `backend/alembic/versions/0029_s2_lane_a_raw_ingestion_lineage.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_cleaned_dataset_version` | `backend/alembic/versions/2af278a20e2a_s2_lane_b_cleaning_quality_correction.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_cleaned_row` | `backend/alembic/versions/2af278a20e2a_s2_lane_b_cleaning_quality_correction.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; carries_kg_or_weight_columns:source_actual_harvest_quantity_kg,effective_actual_harvest_quantity_kg; carries_harvest_business_date:harvest_business_date; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_quality_finding` | `backend/alembic/versions/2af278a20e2a_s2_lane_b_cleaning_quality_correction.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_correction_ledger_entry` | `backend/alembic/versions/2af278a20e2a_s2_lane_b_cleaning_quality_correction.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_exclusion_ledger_entry` | `backend/alembic/versions/2af278a20e2a_s2_lane_b_cleaning_quality_correction.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_pit_visibility_decision` | `backend/alembic/versions/8c6aead9f8e9_s2_lane_c_pit_visibility_revision_winner.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_model_id; missing_forecast_quantile |
| `s2_revision_winner_decision` | `backend/alembic/versions/8c6aead9f8e9_s2_lane_c_pit_visibility_revision_winner.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_model_id; missing_forecast_quantile |
| `s2_idfl_label_side_winner_decision` | `backend/alembic/versions/a7c3e9f1b2d4_s2_lane_c_idfl_label_side_winner.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_materialized_dataset` | `backend/alembic/versions/d4e8f1a2b3c5_s2_lane_d_materialized_dataset.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_materialized_materializable_row` | `backend/alembic/versions/d4e8f1a2b3c5_s2_lane_d_materialized_dataset.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; carries_kg_or_weight_columns:actual_harvest_quantity_kg; carries_harvest_business_date:harvest_business_date; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |
| `s2_materialized_partition` | `backend/alembic/versions/d4e8f1a2b3c5_s2_lane_d_materialized_dataset.py` | NOT_MATCH | S2_lane_table_not_incumbent_forecast_artifact_authority; missing_forecast_cutoff_at; missing_model_id; missing_forecast_quantile |

## 4. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED=false → true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false (companion; not flipped)
~~~

## 5. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
