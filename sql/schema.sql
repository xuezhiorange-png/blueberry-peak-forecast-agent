CREATE TABLE IF NOT EXISTS dim_season (
  id BIGSERIAL CONSTRAINT pk_dim_season PRIMARY KEY,
  code TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  CONSTRAINT uq_dim_season_code UNIQUE (code),
  CONSTRAINT ck_dim_season_date_range CHECK (end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS dim_factory (
  id BIGSERIAL CONSTRAINT pk_dim_factory PRIMARY KEY,
  code TEXT,
  name TEXT NOT NULL,
  region_name TEXT,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  altitude_m NUMERIC(8,2),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_dim_factory_code UNIQUE (code),
  CONSTRAINT uq_dim_factory_name UNIQUE (name),
  CONSTRAINT ck_dim_factory_latitude_range CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
  CONSTRAINT ck_dim_factory_longitude_range CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180))
);

CREATE TABLE IF NOT EXISTS dim_farm (
  id BIGSERIAL CONSTRAINT pk_dim_farm PRIMARY KEY,
  name TEXT NOT NULL,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  altitude_m NUMERIC(8,2),
  CONSTRAINT uq_dim_farm_name UNIQUE (name),
  CONSTRAINT ck_dim_farm_latitude_range CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
  CONSTRAINT ck_dim_farm_longitude_range CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180))
);

CREATE TABLE IF NOT EXISTS dim_variety (
  id BIGSERIAL CONSTRAINT pk_dim_variety PRIMARY KEY,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  CONSTRAINT uq_dim_variety_code UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS dim_grade (
  id BIGSERIAL CONSTRAINT pk_dim_grade PRIMARY KEY,
  code TEXT NOT NULL,
  is_analysis_eligible_default BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_dim_grade_code UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS dim_subfarm (
  id BIGSERIAL CONSTRAINT pk_dim_subfarm PRIMARY KEY,
  farm_id BIGINT NOT NULL,
  name TEXT NOT NULL,
  altitude_m NUMERIC(8,2),
  CONSTRAINT fk_dim_subfarm_farm_id_dim_farm FOREIGN KEY (farm_id) REFERENCES dim_farm(id) ON DELETE RESTRICT,
  CONSTRAINT uq_dim_subfarm_farm_id_name UNIQUE (farm_id, name)
);

CREATE TABLE IF NOT EXISTS dim_holiday (
  id BIGSERIAL CONSTRAINT pk_dim_holiday PRIMARY KEY,
  season_id BIGINT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  region_name TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fk_dim_holiday_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT uq_dim_holiday_season_id_code UNIQUE (season_id, code),
  CONSTRAINT ck_dim_holiday_date_range CHECK (end_date >= start_date)
);

CREATE INDEX IF NOT EXISTS ix_dim_factory_active ON dim_factory (active);
CREATE INDEX IF NOT EXISTS ix_dim_subfarm_farm_id ON dim_subfarm (farm_id);
CREATE INDEX IF NOT EXISTS ix_dim_holiday_season_id ON dim_holiday (season_id);
CREATE INDEX IF NOT EXISTS ix_dim_holiday_region_name ON dim_holiday (region_name);
CREATE INDEX IF NOT EXISTS ix_dim_holiday_active ON dim_holiday (active);

CREATE TABLE IF NOT EXISTS ingest_file (
  id BIGSERIAL CONSTRAINT pk_ingest_file PRIMARY KEY,
  file_name TEXT NOT NULL,
  source_path TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,
  season_id BIGINT,
  status TEXT NOT NULL,
  sheet_count INTEGER NOT NULL DEFAULT 0,
  row_count INTEGER NOT NULL DEFAULT 0,
  inserted_row_count INTEGER NOT NULL DEFAULT 0,
  suspected_duplicate_count INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  config_hash TEXT NOT NULL,
  config_snapshot JSONB NOT NULL,
  quality_report JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT,
  CONSTRAINT uq_ingest_file_file_sha256 UNIQUE (file_sha256),
  CONSTRAINT ck_ingest_file_status CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
  CONSTRAINT fk_ingest_file_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_ingest_file_season_id ON ingest_file (season_id);
CREATE INDEX IF NOT EXISTS ix_ingest_file_status ON ingest_file (status);

CREATE TABLE IF NOT EXISTS fact_receipt_raw (
  id BIGSERIAL CONSTRAINT pk_fact_receipt_raw PRIMARY KEY,
  ingest_file_id BIGINT NOT NULL,
  season_id BIGINT NOT NULL,
  source_sheet TEXT NOT NULL,
  source_row_number INTEGER NOT NULL,
  raw_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  receipt_date_raw TEXT,
  link_name_raw TEXT,
  farm_raw TEXT,
  subfarm_raw TEXT,
  variety_raw TEXT,
  grade_raw TEXT,
  weight_kg_raw TEXT,
  factory_raw TEXT,
  receipt_date DATE,
  weight_kg NUMERIC(18,6),
  factory_normalized TEXT,
  variety_normalized TEXT,
  factory_id BIGINT,
  variety_id BIGINT,
  grade_id BIGINT,
  is_date_valid BOOLEAN NOT NULL,
  is_weight_valid BOOLEAN NOT NULL,
  is_factory_known BOOLEAN NOT NULL,
  is_variety_known BOOLEAN NOT NULL,
  is_suspected_duplicate BOOLEAN NOT NULL,
  is_analysis_eligible BOOLEAN NOT NULL,
  exclusion_reasons JSONB NOT NULL,
  parse_errors JSONB NOT NULL,
  source_row_fingerprint TEXT NOT NULL,
  business_fingerprint TEXT NOT NULL,
  CONSTRAINT uq_fact_receipt_raw_source_row_fp UNIQUE (source_row_fingerprint),
  CONSTRAINT fk_fact_receipt_raw_ingest_file_id FOREIGN KEY (ingest_file_id) REFERENCES ingest_file(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fact_receipt_raw_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fact_receipt_raw_factory_id_dim_factory FOREIGN KEY (factory_id) REFERENCES dim_factory(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fact_receipt_raw_variety_id_dim_variety FOREIGN KEY (variety_id) REFERENCES dim_variety(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fact_receipt_raw_grade_id_dim_grade FOREIGN KEY (grade_id) REFERENCES dim_grade(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_fact_receipt_raw_ingest_file_id ON fact_receipt_raw (ingest_file_id);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_raw_season_id ON fact_receipt_raw (season_id);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_raw_business_fp ON fact_receipt_raw (business_fingerprint);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_raw_receipt_date ON fact_receipt_raw (receipt_date);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_raw_factory_id ON fact_receipt_raw (factory_id);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_raw_variety_id ON fact_receipt_raw (variety_id);

CREATE TABLE IF NOT EXISTS analytics_build_run (
  id BIGSERIAL CONSTRAINT pk_analytics_build_run PRIMARY KEY,
  season_id BIGINT NOT NULL,
  aggregation_version TEXT NOT NULL,
  source_max_raw_id BIGINT NOT NULL,
  config_hash TEXT NOT NULL,
  config_snapshot JSONB NOT NULL,
  status TEXT NOT NULL,
  source_eligible_row_count INTEGER NOT NULL DEFAULT 0,
  source_eligible_weight_kg NUMERIC(18,6) NOT NULL DEFAULT 0,
  daily_fact_row_count INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  CONSTRAINT ck_analytics_build_run_status CHECK (status IN ('running', 'completed', 'failed')),
  CONSTRAINT fk_analytics_build_run_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_analytics_build_run_season_id ON analytics_build_run (season_id);
CREATE INDEX IF NOT EXISTS ix_analytics_build_run_status ON analytics_build_run (status);
CREATE INDEX IF NOT EXISTS ix_analytics_build_run_source_max_raw_id ON analytics_build_run (source_max_raw_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_analytics_build_run_active_or_completed
ON analytics_build_run (season_id, aggregation_version, source_max_raw_id, config_hash)
WHERE status IN ('running', 'completed');

CREATE TABLE IF NOT EXISTS fact_receipt_daily (
  id BIGSERIAL CONSTRAINT pk_fact_receipt_daily PRIMARY KEY,
  build_run_id BIGINT NOT NULL,
  season_id BIGINT NOT NULL,
  receipt_date DATE NOT NULL,
  factory_id BIGINT NOT NULL,
  farm_key TEXT NOT NULL,
  subfarm_key TEXT NOT NULL,
  variety_id BIGINT NOT NULL,
  weight_kg NUMERIC(18,6) NOT NULL,
  source_row_count INTEGER NOT NULL,
  holiday_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
  is_spring_festival BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_fact_receipt_daily_weight_positive CHECK (weight_kg > 0),
  CONSTRAINT ck_fact_receipt_daily_source_row_count_positive CHECK (source_row_count > 0),
  CONSTRAINT fk_fact_receipt_daily_build_run_id_analytics_build_run FOREIGN KEY (build_run_id) REFERENCES analytics_build_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fact_receipt_daily_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fact_receipt_daily_factory_id_dim_factory FOREIGN KEY (factory_id) REFERENCES dim_factory(id) ON DELETE RESTRICT,
  CONSTRAINT fk_fact_receipt_daily_variety_id_dim_variety FOREIGN KEY (variety_id) REFERENCES dim_variety(id) ON DELETE RESTRICT,
  CONSTRAINT uq_fact_receipt_daily_build_grain UNIQUE (build_run_id, season_id, receipt_date, factory_id, farm_key, subfarm_key, variety_id)
);

CREATE INDEX IF NOT EXISTS ix_fact_receipt_daily_build_run_id ON fact_receipt_daily (build_run_id);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_daily_season_id ON fact_receipt_daily (season_id);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_daily_factory_id ON fact_receipt_daily (factory_id);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_daily_receipt_date ON fact_receipt_daily (receipt_date);
CREATE INDEX IF NOT EXISTS ix_fact_receipt_daily_season_factory_date ON fact_receipt_daily (season_id, factory_id, receipt_date);

CREATE TABLE IF NOT EXISTS factory_season_peak_metric (
  id BIGSERIAL CONSTRAINT pk_factory_season_peak_metric PRIMARY KEY,
  build_run_id BIGINT NOT NULL,
  season_id BIGINT NOT NULL,
  factory_id BIGINT NOT NULL,
  analysis_start_date DATE NOT NULL,
  analysis_end_date DATE NOT NULL,
  calendar_day_count INTEGER NOT NULL,
  observed_day_count INTEGER NOT NULL,
  total_weight_kg NUMERIC(18,6) NOT NULL,
  single_day_peak_kg NUMERIC(18,6) NOT NULL,
  single_day_peak_date DATE NOT NULL,
  stable_median_3d_peak_kg NUMERIC(18,6) NOT NULL,
  stable_median_3d_peak_date DATE,
  mean_3d_peak_kg NUMERIC(18,6) NOT NULL,
  mean_3d_peak_date DATE,
  peak_concentration NUMERIC(12,10) NOT NULL,
  variety_hhi NUMERIC(12,10) NOT NULL,
  farm_hhi NUMERIC(12,10) NOT NULL,
  subfarm_hhi NUMERIC(12,10) NOT NULL,
  unknown_farm_weight_share NUMERIC(12,10) NOT NULL,
  unknown_subfarm_weight_share NUMERIC(12,10) NOT NULL,
  spring_festival_day_count INTEGER NOT NULL DEFAULT 0,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_factory_peak_total_weight_positive CHECK (total_weight_kg > 0),
  CONSTRAINT ck_factory_peak_observed_day_count CHECK (calendar_day_count >= observed_day_count AND observed_day_count >= 0),
  CONSTRAINT ck_factory_peak_peak_concentration_range CHECK (peak_concentration >= 0 AND peak_concentration <= 1),
  CONSTRAINT ck_factory_peak_variety_hhi_range CHECK (variety_hhi >= 0 AND variety_hhi <= 1),
  CONSTRAINT ck_factory_peak_farm_hhi_range CHECK (farm_hhi >= 0 AND farm_hhi <= 1),
  CONSTRAINT ck_factory_peak_subfarm_hhi_range CHECK (subfarm_hhi >= 0 AND subfarm_hhi <= 1),
  CONSTRAINT ck_factory_peak_unknown_farm_share_range CHECK (unknown_farm_weight_share >= 0 AND unknown_farm_weight_share <= 1),
  CONSTRAINT ck_factory_peak_unknown_subfarm_share_range CHECK (unknown_subfarm_weight_share >= 0 AND unknown_subfarm_weight_share <= 1),
  CONSTRAINT fk_factory_season_peak_metric_build_run_id_analytics_build_run FOREIGN KEY (build_run_id) REFERENCES analytics_build_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_factory_season_peak_metric_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT fk_factory_season_peak_metric_factory_id_dim_factory FOREIGN KEY (factory_id) REFERENCES dim_factory(id) ON DELETE RESTRICT,
  CONSTRAINT uq_factory_season_peak_metric_build_run_id_factory_id UNIQUE (build_run_id, factory_id)
);

CREATE INDEX IF NOT EXISTS ix_factory_season_peak_metric_build_run_id ON factory_season_peak_metric (build_run_id);
CREATE INDEX IF NOT EXISTS ix_factory_season_peak_metric_season_id ON factory_season_peak_metric (season_id);
CREATE INDEX IF NOT EXISTS ix_factory_season_peak_metric_factory_id ON factory_season_peak_metric (factory_id);

CREATE TABLE IF NOT EXISTS baseline_backtest_run (
  id BIGSERIAL CONSTRAINT pk_baseline_backtest_run PRIMARY KEY,
  model_version TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  config_snapshot JSONB NOT NULL,
  source_signature TEXT NOT NULL,
  source_build_runs JSONB NOT NULL,
  evaluation_scheme TEXT NOT NULL,
  status TEXT NOT NULL,
  random_seed BIGINT NOT NULL,
  result_row_count BIGINT NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  CONSTRAINT ck_baseline_backtest_run_status CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_baseline_backtest_run_status ON baseline_backtest_run (status);
CREATE INDEX IF NOT EXISTS ix_baseline_backtest_run_evaluation_scheme ON baseline_backtest_run (evaluation_scheme);
CREATE UNIQUE INDEX IF NOT EXISTS ux_baseline_backtest_run_active_or_completed
ON baseline_backtest_run (model_version, config_hash, source_signature, evaluation_scheme)
WHERE status IN ('running', 'completed');

CREATE TABLE IF NOT EXISTS baseline_backtest_result (
  id BIGSERIAL CONSTRAINT pk_baseline_backtest_result PRIMARY KEY,
  run_id BIGINT NOT NULL,
  baseline_name TEXT NOT NULL,
  target_season_id BIGINT NOT NULL,
  factory_id BIGINT NOT NULL,
  previous_season_id BIGINT,
  fold_key TEXT NOT NULL,
  status TEXT NOT NULL,
  actual_stable_peak_kg NUMERIC(18,6),
  predicted_stable_peak_kg NUMERIC(18,6),
  absolute_error_kg NUMERIC(18,6),
  signed_error_kg NUMERIC(18,6),
  ape NUMERIC(12,10),
  input_features JSONB NOT NULL,
  training_season_codes JSONB NOT NULL,
  model_metadata JSONB NOT NULL,
  exclusion_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_baseline_backtest_result_baseline_name CHECK (
    baseline_name IN (
      'previous_season_peak',
      'volume_previous_concentration',
      'ridge_structure',
      'ridge_structure_factory_holdout'
    )
  ),
  CONSTRAINT ck_baseline_backtest_result_status CHECK (status IN ('evaluated', 'excluded')),
  CONSTRAINT fk_baseline_backtest_result_run_id_baseline_backtest_run
    FOREIGN KEY (run_id) REFERENCES baseline_backtest_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_baseline_backtest_result_target_season_id_dim_season
    FOREIGN KEY (target_season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT fk_baseline_backtest_result_factory_id_dim_factory
    FOREIGN KEY (factory_id) REFERENCES dim_factory(id) ON DELETE RESTRICT,
  CONSTRAINT fk_baseline_backtest_result_previous_season_id_dim_season
    FOREIGN KEY (previous_season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT uq_baseline_backtest_result_run_model_target_factory_fold
    UNIQUE (run_id, baseline_name, target_season_id, factory_id, fold_key)
);

CREATE INDEX IF NOT EXISTS ix_baseline_backtest_result_run_id ON baseline_backtest_result (run_id);
CREATE INDEX IF NOT EXISTS ix_baseline_backtest_result_baseline_name ON baseline_backtest_result (baseline_name);
CREATE INDEX IF NOT EXISTS ix_baseline_backtest_result_target_season_id ON baseline_backtest_result (target_season_id);
CREATE INDEX IF NOT EXISTS ix_baseline_backtest_result_factory_id ON baseline_backtest_result (factory_id);

CREATE TABLE IF NOT EXISTS dim_agro_climate_zone (
  id BIGSERIAL CONSTRAINT pk_dim_agro_climate_zone PRIMARY KEY,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  country TEXT NOT NULL,
  province TEXT NOT NULL,
  prefecture TEXT,
  county TEXT,
  centroid_latitude NUMERIC(9,6) NOT NULL,
  centroid_longitude NUMERIC(9,6) NOT NULL,
  min_altitude_m NUMERIC(8,2),
  max_altitude_m NUMERIC(8,2),
  zone_version TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_to DATE,
  source_name TEXT NOT NULL,
  source_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_dim_agro_climate_zone_code_version UNIQUE (code, zone_version),
  CONSTRAINT ck_dim_agro_climate_zone_latitude_range CHECK (centroid_latitude >= -90 AND centroid_latitude <= 90),
  CONSTRAINT ck_dim_agro_climate_zone_longitude_range CHECK (centroid_longitude >= -180 AND centroid_longitude <= 180),
  CONSTRAINT ck_dim_agro_climate_zone_altitude_range CHECK (min_altitude_m IS NULL OR max_altitude_m IS NULL OR min_altitude_m <= max_altitude_m),
  CONSTRAINT ck_dim_agro_climate_zone_valid_range CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS climate_zone_import_run (
  id BIGSERIAL CONSTRAINT pk_climate_zone_import_run PRIMARY KEY,
  file_name TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,
  zone_version TEXT,
  source_name TEXT,
  source_version TEXT,
  status TEXT NOT NULL,
  row_count BIGINT NOT NULL DEFAULT 0,
  valid_row_count BIGINT NOT NULL DEFAULT 0,
  invalid_row_count BIGINT NOT NULL DEFAULT 0,
  inserted_count BIGINT NOT NULL DEFAULT 0,
  skipped_count BIGINT NOT NULL DEFAULT 0,
  conflict_count BIGINT NOT NULL DEFAULT 0,
  report_json JSONB NOT NULL,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  CONSTRAINT ck_climate_zone_import_run_status CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE TABLE IF NOT EXISTS location_reference (
  id BIGSERIAL CONSTRAINT pk_location_reference PRIMARY KEY,
  farm_id BIGINT,
  subfarm_id BIGINT,
  farm_code TEXT,
  farm_name TEXT,
  subfarm_name TEXT,
  address_raw TEXT,
  address_normalized TEXT NOT NULL,
  province TEXT,
  prefecture TEXT,
  county TEXT,
  township TEXT,
  village TEXT,
  latitude NUMERIC(9,6) NOT NULL,
  longitude NUMERIC(9,6) NOT NULL,
  altitude_m NUMERIC(8,2),
  climate_zone_id BIGINT,
  location_source TEXT NOT NULL,
  source_version TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_to DATE,
  source_row_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_location_reference_source_version_row_hash UNIQUE (source_version, source_row_hash),
  CONSTRAINT ck_location_reference_latitude_range CHECK (latitude >= -90 AND latitude <= 90),
  CONSTRAINT ck_location_reference_longitude_range CHECK (longitude >= -180 AND longitude <= 180),
  CONSTRAINT ck_location_reference_valid_range CHECK (valid_to IS NULL OR valid_to >= valid_from),
  CONSTRAINT fk_location_reference_farm_id_dim_farm FOREIGN KEY (farm_id) REFERENCES dim_farm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_location_reference_subfarm_id_dim_subfarm FOREIGN KEY (subfarm_id) REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_location_reference_climate_zone_id_dim_agro_climate_zone FOREIGN KEY (climate_zone_id) REFERENCES dim_agro_climate_zone(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_location_reference_address_normalized ON location_reference (address_normalized);
CREATE INDEX IF NOT EXISTS ix_location_reference_climate_zone_id ON location_reference (climate_zone_id);

CREATE TABLE IF NOT EXISTS parameter_library_version (
  id BIGSERIAL CONSTRAINT pk_parameter_library_version PRIMARY KEY,
  version_code TEXT NOT NULL,
  status TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_file_sha256 TEXT,
  config_hash TEXT NOT NULL,
  record_count BIGINT NOT NULL DEFAULT 0,
  effective_from DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_parameter_library_version_version_code UNIQUE (version_code),
  CONSTRAINT ck_parameter_library_version_status CHECK (status IN ('draft', 'active', 'retired', 'failed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_parameter_library_version_active
ON parameter_library_version (status)
WHERE status = 'active';

CREATE TABLE IF NOT EXISTS parameter_observation (
  id BIGSERIAL CONSTRAINT pk_parameter_observation PRIMARY KEY,
  library_version_id BIGINT NOT NULL,
  parameter_type TEXT NOT NULL,
  variety_id BIGINT NOT NULL,
  farm_id BIGINT,
  subfarm_id BIGINT,
  location_reference_id BIGINT,
  climate_zone_id BIGINT,
  season_id BIGINT,
  province TEXT,
  prefecture TEXT,
  county TEXT,
  township TEXT,
  altitude_m NUMERIC(8,2),
  scalar_value NUMERIC(18,6) NOT NULL,
  unit TEXT NOT NULL,
  sample_weight NUMERIC(18,6) NOT NULL,
  source_level TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_version TEXT NOT NULL,
  historical_mape NUMERIC(12,10),
  date_mae_days NUMERIC(12,6),
  p90_coverage NUMERIC(12,10),
  available_at DATE,
  valid_from DATE NOT NULL,
  valid_to DATE,
  source_row_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_parameter_observation_library_row_hash UNIQUE (library_version_id, source_row_hash),
  CONSTRAINT ck_parameter_observation_parameter_type CHECK (
    parameter_type IN (
      'yield_kg_per_mu',
      'marketable_rate',
      'first_harvest_offset_days',
      'maturity_peak_offset_days',
      'maturity_width_days',
      'maturity_skewness',
      'harvest_realization_rate'
    )
  ),
  CONSTRAINT ck_parameter_observation_yield_positive CHECK (parameter_type != 'yield_kg_per_mu' OR scalar_value > 0),
  CONSTRAINT ck_parameter_observation_marketable_rate_range CHECK (parameter_type != 'marketable_rate' OR (scalar_value >= 0 AND scalar_value <= 1)),
  CONSTRAINT ck_parameter_observation_harvest_realization_rate_range CHECK (parameter_type != 'harvest_realization_rate' OR (scalar_value >= 0 AND scalar_value <= 1)),
  CONSTRAINT ck_parameter_observation_width_positive CHECK (parameter_type != 'maturity_width_days' OR scalar_value > 0),
  CONSTRAINT ck_parameter_observation_sample_weight_positive CHECK (sample_weight > 0),
  CONSTRAINT ck_parameter_observation_valid_range CHECK (valid_to IS NULL OR valid_to >= valid_from),
  CONSTRAINT fk_param_obs_lib_ver_id_param_lib_ver FOREIGN KEY (library_version_id) REFERENCES parameter_library_version(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_variety_id_dim_variety FOREIGN KEY (variety_id) REFERENCES dim_variety(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_farm_id_dim_farm FOREIGN KEY (farm_id) REFERENCES dim_farm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_subfarm_id_dim_subfarm FOREIGN KEY (subfarm_id) REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_param_obs_loc_ref_id_location_ref FOREIGN KEY (location_reference_id) REFERENCES location_reference(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_climate_zone_id_dim_agro_climate_zone FOREIGN KEY (climate_zone_id) REFERENCES dim_agro_climate_zone(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_parameter_observation_variety_id ON parameter_observation (variety_id);
CREATE INDEX IF NOT EXISTS ix_parameter_observation_parameter_type ON parameter_observation (parameter_type);
CREATE INDEX IF NOT EXISTS ix_parameter_observation_climate_zone_id ON parameter_observation (climate_zone_id);

CREATE TABLE IF NOT EXISTS minimal_forecast_task (
  id BIGSERIAL CONSTRAINT pk_minimal_forecast_task PRIMARY KEY,
  input_payload JSONB NOT NULL,
  normalized_input JSONB NOT NULL,
  input_hash TEXT NOT NULL,
  as_of_date DATE NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  error_message TEXT,
  CONSTRAINT uq_minimal_forecast_task_input_hash_as_of UNIQUE (input_hash, as_of_date),
  CONSTRAINT ck_minimal_forecast_task_status CHECK (status IN ('created', 'resolving_location', 'inferring_parameters', 'parameters_ready', 'failed'))
);

CREATE TABLE IF NOT EXISTS parameter_inference_run (
  id BIGSERIAL CONSTRAINT pk_parameter_inference_run PRIMARY KEY,
  task_id BIGINT NOT NULL,
  input_hash TEXT NOT NULL,
  as_of_date DATE NOT NULL,
  resolver_version TEXT NOT NULL,
  library_version_id BIGINT NOT NULL,
  config_hash TEXT NOT NULL,
  source_signature TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  CONSTRAINT ck_parameter_inference_run_status CHECK (status IN ('running', 'completed', 'failed')),
  CONSTRAINT fk_parameter_inference_run_task_id_minimal_forecast_task FOREIGN KEY (task_id) REFERENCES minimal_forecast_task(id) ON DELETE RESTRICT,
  CONSTRAINT fk_param_infer_run_lib_ver_id_param_lib_ver FOREIGN KEY (library_version_id) REFERENCES parameter_library_version(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_parameter_inference_run_active_or_completed
ON parameter_inference_run (input_hash, as_of_date, resolver_version, library_version_id, config_hash)
WHERE status IN ('running', 'completed');

CREATE TABLE IF NOT EXISTS parameter_inference_result (
  id BIGSERIAL CONSTRAINT pk_parameter_inference_result PRIMARY KEY,
  run_id BIGINT NOT NULL,
  variety_id BIGINT NOT NULL,
  parameter_type TEXT NOT NULL,
  status TEXT NOT NULL,
  p50_value NUMERIC(18,6),
  p80_lower NUMERIC(18,6),
  p80_upper NUMERIC(18,6),
  unit TEXT NOT NULL,
  source_level TEXT,
  confidence_level TEXT,
  confidence_score NUMERIC(12,10),
  sample_count BIGINT NOT NULL DEFAULT 0,
  season_count BIGINT NOT NULL DEFAULT 0,
  farm_count BIGINT NOT NULL DEFAULT 0,
  source_observation_ids JSONB NOT NULL,
  source_metadata JSONB NOT NULL,
  uncertainty_metadata JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_parameter_inference_result_run_variety_parameter UNIQUE (run_id, variety_id, parameter_type),
  CONSTRAINT ck_parameter_inference_result_status CHECK (status IN ('available', 'unavailable')),
  CONSTRAINT fk_parameter_inference_result_run_id_parameter_inference_run FOREIGN KEY (run_id) REFERENCES parameter_inference_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_inference_result_variety_id_dim_variety FOREIGN KEY (variety_id) REFERENCES dim_variety(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS farm_season_variety_plan (
  id BIGSERIAL CONSTRAINT pk_farm_season_variety_plan PRIMARY KEY,
  farm_id BIGINT NOT NULL,
  subfarm_id BIGINT,
  season_id BIGINT NOT NULL,
  variety_id BIGINT NOT NULL,
  planted_area_mu NUMERIC(18,6) NOT NULL,
  expected_yield_kg_per_mu NUMERIC(18,6) NOT NULL,
  marketable_rate NUMERIC(12,10) NOT NULL,
  tree_age_years NUMERIC(8,2),
  pruning_date DATE,
  flowering_start_date DATE,
  flowering_peak_date DATE,
  flowering_end_date DATE,
  first_pick_date DATE,
  expected_total_marketable_kg NUMERIC(18,6),
  version INTEGER NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE,
  available_at DATE NOT NULL,
  source_type TEXT NOT NULL,
  source_name TEXT,
  source_version TEXT,
  notes TEXT,
  row_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_farm_season_variety_plan_row_hash UNIQUE (row_hash),
  CONSTRAINT ck_farm_season_variety_plan_planted_area_non_negative CHECK (planted_area_mu >= 0),
  CONSTRAINT ck_farm_season_variety_plan_expected_yield_non_negative CHECK (expected_yield_kg_per_mu >= 0),
  CONSTRAINT ck_farm_season_variety_plan_marketable_rate_range CHECK (marketable_rate >= 0 AND marketable_rate <= 1),
  CONSTRAINT ck_farm_season_variety_plan_expected_total_non_negative CHECK (expected_total_marketable_kg IS NULL OR expected_total_marketable_kg >= 0),
  CONSTRAINT ck_farm_season_variety_plan_tree_age_non_negative CHECK (tree_age_years IS NULL OR tree_age_years >= 0),
  CONSTRAINT ck_farm_season_variety_plan_version_positive CHECK (version > 0),
  CONSTRAINT ck_farm_season_variety_plan_effective_range CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT ck_farm_season_variety_plan_flowering_start_peak CHECK (flowering_start_date IS NULL OR flowering_peak_date IS NULL OR flowering_start_date <= flowering_peak_date),
  CONSTRAINT ck_farm_season_variety_plan_flowering_peak_end CHECK (flowering_peak_date IS NULL OR flowering_end_date IS NULL OR flowering_peak_date <= flowering_end_date),
  CONSTRAINT fk_farm_plan_farm_id_dim_farm FOREIGN KEY (farm_id) REFERENCES dim_farm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_farm_plan_subfarm_id_dim_subfarm FOREIGN KEY (subfarm_id) REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_farm_plan_season_id_dim_season FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT fk_farm_plan_variety_id_dim_variety FOREIGN KEY (variety_id) REFERENCES dim_variety(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_farm_season_variety_plan_version_null_subfarm
ON farm_season_variety_plan (farm_id, season_id, variety_id, version)
WHERE subfarm_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_farm_season_variety_plan_version_with_subfarm
ON farm_season_variety_plan (farm_id, subfarm_id, season_id, variety_id, version)
WHERE subfarm_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_farm_season_variety_plan_business_key
ON farm_season_variety_plan (farm_id, season_id, variety_id);
CREATE INDEX IF NOT EXISTS ix_farm_season_variety_plan_subfarm_id
ON farm_season_variety_plan (subfarm_id);
CREATE INDEX IF NOT EXISTS ix_farm_season_variety_plan_effective_from
ON farm_season_variety_plan (effective_from);
CREATE INDEX IF NOT EXISTS ix_farm_season_variety_plan_effective_to
ON farm_season_variety_plan (effective_to);
CREATE INDEX IF NOT EXISTS ix_farm_season_variety_plan_available_at
ON farm_season_variety_plan (available_at);
CREATE INDEX IF NOT EXISTS ix_farm_season_variety_plan_row_hash
ON farm_season_variety_plan (row_hash);

CREATE TABLE IF NOT EXISTS production_plan_import_run (
  id BIGSERIAL CONSTRAINT pk_production_plan_import_run PRIMARY KEY,
  file_name TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,
  source_version TEXT,
  status TEXT NOT NULL,
  row_count BIGINT NOT NULL DEFAULT 0,
  inserted_count BIGINT NOT NULL DEFAULT 0,
  skipped_count BIGINT NOT NULL DEFAULT 0,
  rejected_count BIGINT NOT NULL DEFAULT 0,
  duplicate_count BIGINT NOT NULL DEFAULT 0,
  unknown_farm_count BIGINT NOT NULL DEFAULT 0,
  unknown_subfarm_count BIGINT NOT NULL DEFAULT 0,
  unknown_season_count BIGINT NOT NULL DEFAULT 0,
  unknown_variety_count BIGINT NOT NULL DEFAULT 0,
  invalid_date_count BIGINT NOT NULL DEFAULT 0,
  invalid_numeric_count BIGINT NOT NULL DEFAULT 0,
  overlap_conflict_count BIGINT NOT NULL DEFAULT 0,
  version_conflict_count BIGINT NOT NULL DEFAULT 0,
  report_json JSONB NOT NULL,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  CONSTRAINT ck_production_plan_import_run_status CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE TABLE IF NOT EXISTS weather_source_location (
  id BIGSERIAL PRIMARY KEY,
  provider_code TEXT NOT NULL,
  external_location_id TEXT NOT NULL,
  location_type TEXT NOT NULL,
  name TEXT,
  latitude NUMERIC(9,6) NOT NULL,
  longitude NUMERIC(9,6) NOT NULL,
  altitude_m NUMERIC(8,2),
  timezone_name TEXT NOT NULL,
  grid_resolution TEXT,
  source_version TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_to DATE,
  row_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_weather_src_loc_provider_ext_ver UNIQUE (provider_code, external_location_id, source_version),
  CONSTRAINT uq_weather_src_loc_row_hash UNIQUE (row_hash),
  CONSTRAINT ck_weather_src_loc_type CHECK (location_type IN ('station', 'grid')),
  CONSTRAINT ck_weather_src_loc_latitude CHECK (latitude >= -90 AND latitude <= 90),
  CONSTRAINT ck_weather_src_loc_longitude CHECK (longitude >= -180 AND longitude <= 180),
  CONSTRAINT ck_weather_src_loc_valid_range CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX IF NOT EXISTS ix_weather_src_loc_provider
ON weather_source_location (provider_code);
CREATE INDEX IF NOT EXISTS ix_weather_src_loc_type
ON weather_source_location (location_type);

CREATE TABLE IF NOT EXISTS weather_daily_observation (
  id BIGSERIAL PRIMARY KEY,
  weather_source_location_id BIGINT NOT NULL,
  observation_date DATE NOT NULL,
  temperature_min_c NUMERIC(12,6) NOT NULL,
  temperature_max_c NUMERIC(12,6) NOT NULL,
  temperature_mean_c NUMERIC(12,6),
  temperature_mean_source TEXT NOT NULL,
  precipitation_mm NUMERIC(12,6) NOT NULL,
  solar_radiation_mj_m2 NUMERIC(12,6),
  provider_code TEXT NOT NULL,
  source_version TEXT NOT NULL,
  available_at DATE NOT NULL,
  quality_code TEXT,
  quality_flags JSONB NOT NULL,
  source_file_sha256 TEXT,
  source_row_number BIGINT,
  row_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_weather_daily_obs_row_hash UNIQUE (row_hash),
  CONSTRAINT ck_weather_daily_obs_temp_range CHECK (temperature_max_c >= temperature_min_c),
  CONSTRAINT ck_weather_daily_obs_mean_range CHECK (
    temperature_mean_c IS NULL
    OR (temperature_mean_c >= temperature_min_c AND temperature_mean_c <= temperature_max_c)
  ),
  CONSTRAINT ck_weather_daily_obs_mean_source CHECK (temperature_mean_source IN ('provided', 'derived')),
  CONSTRAINT ck_weather_daily_obs_precip_non_negative CHECK (precipitation_mm >= 0),
  CONSTRAINT ck_weather_daily_obs_solar_non_negative CHECK (solar_radiation_mj_m2 IS NULL OR solar_radiation_mj_m2 >= 0),
  CONSTRAINT fk_weather_daily_obs_src_loc_id FOREIGN KEY (weather_source_location_id) REFERENCES weather_source_location(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_weather_daily_obs_source_loc_id
ON weather_daily_observation (weather_source_location_id);
CREATE INDEX IF NOT EXISTS ix_weather_daily_obs_obs_date
ON weather_daily_observation (observation_date);
CREATE INDEX IF NOT EXISTS ix_weather_daily_obs_available_at
ON weather_daily_observation (available_at);

CREATE TABLE IF NOT EXISTS weather_import_run (
  id BIGSERIAL PRIMARY KEY,
  import_type TEXT NOT NULL,
  provider_code TEXT,
  file_name TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,
  source_version TEXT,
  dry_run BOOLEAN NOT NULL,
  status TEXT NOT NULL,
  row_count BIGINT NOT NULL DEFAULT 0,
  inserted_count BIGINT NOT NULL DEFAULT 0,
  skipped_count BIGINT NOT NULL DEFAULT 0,
  duplicate_count BIGINT NOT NULL DEFAULT 0,
  rejected_count BIGINT NOT NULL DEFAULT 0,
  invalid_date_count BIGINT NOT NULL DEFAULT 0,
  invalid_numeric_count BIGINT NOT NULL DEFAULT 0,
  unknown_location_count BIGINT NOT NULL DEFAULT 0,
  conflict_count BIGINT NOT NULL DEFAULT 0,
  report_json JSONB NOT NULL,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  CONSTRAINT ck_weather_import_run_type CHECK (import_type IN ('location', 'observation', 'mapping')),
  CONSTRAINT ck_weather_import_run_status CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE TABLE IF NOT EXISTS location_weather_mapping (
  id BIGSERIAL PRIMARY KEY,
  location_reference_id BIGINT NOT NULL,
  weather_source_location_id BIGINT NOT NULL,
  mapping_method TEXT NOT NULL,
  distance_km NUMERIC(12,6) NOT NULL,
  altitude_difference_m NUMERIC(12,6),
  mapping_score NUMERIC(12,6) NOT NULL,
  confidence_level TEXT NOT NULL,
  mapping_version TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  available_at DATE NOT NULL,
  valid_from DATE NOT NULL,
  valid_to DATE,
  row_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_location_weather_mapping_row_hash UNIQUE (row_hash),
  CONSTRAINT ck_location_weather_mapping_method CHECK (mapping_method IN ('explicit', 'nearest_station', 'nearest_grid')),
  CONSTRAINT ck_location_weather_mapping_distance CHECK (distance_km >= 0),
  CONSTRAINT ck_location_weather_mapping_score CHECK (mapping_score >= 0),
  CONSTRAINT ck_location_weather_mapping_valid_range CHECK (valid_to IS NULL OR valid_to >= valid_from),
  CONSTRAINT fk_loc_weather_mapping_loc_ref_id FOREIGN KEY (location_reference_id) REFERENCES location_reference(id) ON DELETE RESTRICT,
  CONSTRAINT fk_loc_weather_mapping_src_loc_id FOREIGN KEY (weather_source_location_id) REFERENCES weather_source_location(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_loc_weather_mapping_loc_ref_id
ON location_weather_mapping (location_reference_id);
CREATE INDEX IF NOT EXISTS ix_loc_weather_mapping_src_loc_id
ON location_weather_mapping (weather_source_location_id);
CREATE INDEX IF NOT EXISTS ix_loc_weather_mapping_available_at
ON location_weather_mapping (available_at);

CREATE TABLE IF NOT EXISTS base_temperature_search_run (
  id BIGSERIAL PRIMARY KEY,
  scope_type TEXT NOT NULL,
  variety_id BIGINT,
  climate_zone_id BIGINT,
  training_cutoff DATE NOT NULL,
  anchor_event TEXT NOT NULL,
  target_event TEXT NOT NULL,
  candidate_temperatures JSONB NOT NULL,
  selected_base_temperature NUMERIC(12,6),
  scoring_method TEXT NOT NULL,
  selected_score NUMERIC(12,6),
  sample_count BIGINT NOT NULL DEFAULT 0,
  distinct_season_count BIGINT NOT NULL DEFAULT 0,
  training_sample_ids JSONB NOT NULL,
  candidate_scores JSONB NOT NULL,
  config_hash TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  source_signature TEXT NOT NULL,
  status TEXT NOT NULL,
  warnings JSONB NOT NULL,
  blockers JSONB NOT NULL,
  input_snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  CONSTRAINT ck_base_temp_search_run_status CHECK (status IN ('running', 'completed', 'failed', 'unavailable')),
  CONSTRAINT fk_base_temp_search_run_variety_id FOREIGN KEY (variety_id) REFERENCES dim_variety(id) ON DELETE RESTRICT,
  CONSTRAINT fk_base_temp_search_run_zone_id FOREIGN KEY (climate_zone_id) REFERENCES dim_agro_climate_zone(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_base_temp_search_run_active_or_done
ON base_temperature_search_run (source_signature)
WHERE status IN ('running', 'completed', 'unavailable');

CREATE INDEX IF NOT EXISTS ix_base_temp_search_run_variety_id
ON base_temperature_search_run (variety_id);
CREATE INDEX IF NOT EXISTS ix_base_temp_search_run_zone_id
ON base_temperature_search_run (climate_zone_id);

CREATE TABLE IF NOT EXISTS weather_feature_run (
  id BIGSERIAL PRIMARY KEY,
  feature_version TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  mapping_version TEXT NOT NULL,
  weather_source_version TEXT NOT NULL,
  base_temperature_search_run_id BIGINT,
  plan_id BIGINT NOT NULL,
  location_reference_id BIGINT NOT NULL,
  location_weather_mapping_id BIGINT NOT NULL,
  weather_source_location_id BIGINT NOT NULL,
  as_of_date DATE NOT NULL,
  feature_date DATE NOT NULL,
  source_signature TEXT NOT NULL,
  status TEXT NOT NULL,
  input_snapshot JSONB NOT NULL,
  window_features JSONB NOT NULL,
  timeline_payload JSONB NOT NULL,
  weather_observation_ids JSONB NOT NULL,
  warnings JSONB NOT NULL,
  blockers JSONB NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  CONSTRAINT ck_weather_feature_run_status CHECK (status IN ('running', 'completed', 'failed', 'unavailable')),
  CONSTRAINT fk_weather_feature_run_base_temp_run_id FOREIGN KEY (base_temperature_search_run_id) REFERENCES base_temperature_search_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_weather_feature_run_plan_id FOREIGN KEY (plan_id) REFERENCES farm_season_variety_plan(id) ON DELETE RESTRICT,
  CONSTRAINT fk_weather_feature_run_loc_ref_id FOREIGN KEY (location_reference_id) REFERENCES location_reference(id) ON DELETE RESTRICT,
  CONSTRAINT fk_weather_feature_run_mapping_id FOREIGN KEY (location_weather_mapping_id) REFERENCES location_weather_mapping(id) ON DELETE RESTRICT,
  CONSTRAINT fk_weather_feature_run_src_loc_id FOREIGN KEY (weather_source_location_id) REFERENCES weather_source_location(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_weather_feature_run_active_or_done
ON weather_feature_run (source_signature)
WHERE status IN ('running', 'completed', 'unavailable');

CREATE INDEX IF NOT EXISTS ix_weather_feature_run_plan_id
ON weather_feature_run (plan_id);
CREATE INDEX IF NOT EXISTS ix_weather_feature_run_feature_date
ON weather_feature_run (feature_date);

CREATE TABLE IF NOT EXISTS maturity_model_run (
  id BIGSERIAL PRIMARY KEY,
  model_version TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  config_snapshot JSONB NOT NULL,
  training_cutoff DATE NOT NULL,
  source_signature TEXT NOT NULL,
  status TEXT NOT NULL,
  random_seed BIGINT NOT NULL,
  model_family TEXT NOT NULL,
  scope TEXT NOT NULL,
  sample_count BIGINT NOT NULL,
  distinct_season_count BIGINT NOT NULL,
  distinct_farm_count BIGINT NOT NULL,
  distinct_subfarm_count BIGINT NOT NULL,
  training_metrics JSONB NOT NULL,
  calibration_metrics JSONB NOT NULL,
  warnings JSONB NOT NULL,
  blockers JSONB NOT NULL,
  input_snapshot JSONB NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  CONSTRAINT ck_maturity_model_run_status CHECK (status IN ('running', 'completed', 'failed', 'unavailable')),
  CONSTRAINT uq_maturity_model_run_sig_status UNIQUE (source_signature, status)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_maturity_model_run_active_or_done
ON maturity_model_run (source_signature)
WHERE status IN ('running', 'completed', 'unavailable');

CREATE TABLE IF NOT EXISTS maturity_model_artifact (
  id BIGSERIAL PRIMARY KEY,
  run_id BIGINT NOT NULL,
  artifact_hash TEXT NOT NULL,
  support_min_day BIGINT NOT NULL,
  support_max_day BIGINT NOT NULL,
  artifact_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fk_maturity_artifact_run_id FOREIGN KEY (run_id) REFERENCES maturity_model_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_maturity_model_artifact_run_id UNIQUE (run_id),
  CONSTRAINT uq_maturity_model_artifact_hash UNIQUE (artifact_hash)
);

CREATE TABLE IF NOT EXISTS maturity_forecast_run (
  id BIGSERIAL PRIMARY KEY,
  model_run_id BIGINT NOT NULL,
  artifact_id BIGINT NOT NULL,
  plan_id BIGINT NOT NULL,
  location_reference_id BIGINT NOT NULL,
  weather_mapping_id BIGINT,
  base_temperature_search_run_id BIGINT,
  as_of_date DATE NOT NULL,
  prediction_start_date DATE NOT NULL,
  prediction_end_date DATE NOT NULL,
  expected_marketable_total_kg NUMERIC(18,6) NOT NULL,
  expected_total_source TEXT NOT NULL,
  axis_mode TEXT NOT NULL,
  source_signature TEXT NOT NULL,
  status TEXT NOT NULL,
  warnings JSONB NOT NULL,
  blockers JSONB NOT NULL,
  input_snapshot JSONB NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  CONSTRAINT ck_maturity_forecast_run_status CHECK (status IN ('running', 'completed', 'failed', 'unavailable')),
  CONSTRAINT ck_maturity_forecast_run_axis_mode CHECK (axis_mode IN ('observed_phenology_axis', 'calendar_proxy_axis')),
  CONSTRAINT fk_maturity_forecast_run_model_id FOREIGN KEY (model_run_id) REFERENCES maturity_model_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_maturity_forecast_run_artifact_id FOREIGN KEY (artifact_id) REFERENCES maturity_model_artifact(id) ON DELETE RESTRICT,
  CONSTRAINT fk_maturity_forecast_run_plan_id FOREIGN KEY (plan_id) REFERENCES farm_season_variety_plan(id) ON DELETE RESTRICT,
  CONSTRAINT fk_maturity_forecast_run_loc_ref_id FOREIGN KEY (location_reference_id) REFERENCES location_reference(id) ON DELETE RESTRICT,
  CONSTRAINT fk_maturity_forecast_run_mapping_id FOREIGN KEY (weather_mapping_id) REFERENCES location_weather_mapping(id) ON DELETE RESTRICT,
  CONSTRAINT fk_maturity_forecast_run_base_temp_id FOREIGN KEY (base_temperature_search_run_id) REFERENCES base_temperature_search_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_maturity_forecast_run_sig_status UNIQUE (source_signature, status)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_maturity_forecast_run_active_or_done
ON maturity_forecast_run (source_signature)
WHERE status IN ('running', 'completed', 'unavailable');

CREATE TABLE IF NOT EXISTS maturity_daily_prediction (
  id BIGSERIAL PRIMARY KEY,
  forecast_run_id BIGINT NOT NULL,
  prediction_date DATE NOT NULL,
  phenology_coordinate_day NUMERIC(12,6) NOT NULL,
  p50_kg NUMERIC(18,6) NOT NULL,
  p80_kg NUMERIC(18,6) NOT NULL,
  p90_kg NUMERIC(18,6) NOT NULL,
  cumulative_p50_kg NUMERIC(18,6) NOT NULL,
  cumulative_p80_kg NUMERIC(18,6) NOT NULL,
  cumulative_p90_kg NUMERIC(18,6) NOT NULL,
  curve_share NUMERIC(12,10) NOT NULL,
  confidence_level TEXT NOT NULL,
  quality_flags JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fk_maturity_daily_prediction_run_id FOREIGN KEY (forecast_run_id) REFERENCES maturity_forecast_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_maturity_daily_run_date UNIQUE (forecast_run_id, prediction_date)
);

CREATE INDEX IF NOT EXISTS ix_maturity_daily_prediction_run_id
ON maturity_daily_prediction (forecast_run_id);
CREATE INDEX IF NOT EXISTS ix_maturity_daily_prediction_date
ON maturity_daily_prediction (prediction_date);

CREATE TABLE IF NOT EXISTS harvest_state_run (
  id BIGSERIAL PRIMARY KEY,
  status TEXT NOT NULL,
  output_schema_version TEXT NOT NULL,
  result_hash_schema_version TEXT NOT NULL,
  resolved_parameter_snapshot_schema_version TEXT NOT NULL,
  source_ref_schema_version TEXT NOT NULL,
  stable_cohort_key_schema_version TEXT NOT NULL,
  input_snapshot JSONB NOT NULL,
  resolved_parameter_snapshot JSONB,
  source_ref_catalog JSONB NOT NULL,
  warnings JSONB NOT NULL,
  blockers JSONB NOT NULL,
  mass_balance_result JSONB,
  continuity_result JSONB,
  canonical_output JSONB NOT NULL,
  config_hash TEXT NOT NULL,
  result_hash TEXT NOT NULL,
  canonical_payload_hash TEXT NOT NULL,
  forecast_start_date DATE NOT NULL,
  forecast_end_date DATE NOT NULL,
  as_of_date DATE NOT NULL,
  destination_factory_id BIGINT NOT NULL,
  pool_row_count BIGINT NOT NULL,
  member_row_count BIGINT NOT NULL,
  cohort_row_count BIGINT NOT NULL,
  future_arrival_row_count BIGINT NOT NULL,
  maturity_model_run_id BIGINT,
  maturity_model_version TEXT,
  maturity_model_config_hash TEXT,
  maturity_model_source_signature TEXT,
  maturity_model_artifact_id BIGINT,
  maturity_model_artifact_hash TEXT,
  maturity_forecast_run_id BIGINT,
  maturity_forecast_source_signature TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_harvest_state_run_status CHECK (status IN ('completed', 'blocked')),
  CONSTRAINT ck_harvest_state_run_config_hash CHECK (
    length(config_hash) = 64
    AND lower(config_hash) = config_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(config_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_harvest_state_run_result_hash CHECK (
    length(result_hash) = 64
    AND lower(result_hash) = result_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(result_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_harvest_state_run_canonical_payload_hash CHECK (
    length(canonical_payload_hash) = 64
    AND lower(canonical_payload_hash) = canonical_payload_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(canonical_payload_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_harvest_state_run_forecast_date_range CHECK (forecast_end_date >= forecast_start_date),
  CONSTRAINT ck_hsr_prc_nn CHECK (pool_row_count >= 0),
  CONSTRAINT ck_hsr_mrc_nn CHECK (member_row_count >= 0),
  CONSTRAINT ck_hsr_crc_nn CHECK (cohort_row_count >= 0),
  CONSTRAINT ck_hsr_farc_nn CHECK (future_arrival_row_count >= 0),
  CONSTRAINT uq_harvest_state_run_result_hash UNIQUE (result_hash)
);

CREATE INDEX IF NOT EXISTS ix_harvest_state_run_status
ON harvest_state_run (status);
CREATE INDEX IF NOT EXISTS ix_harvest_state_run_as_of_date
ON harvest_state_run (as_of_date);
CREATE INDEX IF NOT EXISTS ix_harvest_state_run_maturity_forecast_run_id
ON harvest_state_run (maturity_forecast_run_id);
CREATE INDEX IF NOT EXISTS ix_harvest_state_run_maturity_model_run_id
ON harvest_state_run (maturity_model_run_id);

CREATE TABLE IF NOT EXISTS harvest_state_daily_pool_row (
  id BIGSERIAL PRIMARY KEY,
  harvest_state_run_id BIGINT NOT NULL,
  state_date DATE NOT NULL,
  forecast_quantile TEXT NOT NULL,
  capacity_pool_id TEXT NOT NULL,
  capacity_pool_grain TEXT NOT NULL,
  capacity_pool_membership_hash TEXT NOT NULL,
  capacity_input_mode TEXT NOT NULL,
  opening_mature_inventory_kg NUMERIC(18,3) NOT NULL,
  natural_maturity_supply_kg NUMERIC(18,3) NOT NULL,
  available_mature_quantity_kg NUMERIC(18,3) NOT NULL,
  mature_inventory_loss_quantity_kg NUMERIC(18,3) NOT NULL,
  harvestable_mature_quantity_kg NUMERIC(18,3) NOT NULL,
  nominal_harvest_capacity_kg_per_day NUMERIC(18,3) NOT NULL,
  labor_availability_ratio NUMERIC(12,6) NOT NULL,
  weather_harvest_efficiency_ratio NUMERIC(12,6) NOT NULL,
  operational_efficiency_ratio NUMERIC(12,6) NOT NULL,
  effective_harvest_capacity_kg_per_day NUMERIC(18,3) NOT NULL,
  effective_capacity_for_day_kg NUMERIC(18,3) NOT NULL,
  harvested_quantity_kg NUMERIC(18,3) NOT NULL,
  closing_mature_inventory_kg NUMERIC(18,3) NOT NULL,
  unharvested_backlog_kg NUMERIC(18,3) NOT NULL,
  arrival_quantity_kg NUMERIC(18,3) NOT NULL,
  opening_cohort_count BIGINT NOT NULL,
  closing_cohort_count BIGINT NOT NULL,
  member_count BIGINT NOT NULL,
  mass_balance_passed BOOLEAN NOT NULL,
  capacity_constraint_passed BOOLEAN NOT NULL,
  continuity_passed BOOLEAN NOT NULL,
  parameter_source_ref_hashes JSONB NOT NULL,
  cohort_source_ref_hashes JSONB NOT NULL,
  CONSTRAINT ck_harvest_state_daily_pool_quantile CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
  CONSTRAINT ck_harvest_state_daily_pool_grain CHECK (capacity_pool_grain IN ('SUBFARM_VARIETY', 'SUBFARM', 'FARM')),
  CONSTRAINT ck_harvest_state_daily_pool_input_mode CHECK (capacity_input_mode IN ('LABOR_DERIVED', 'DIRECT_CAPACITY')),
  CONSTRAINT ck_harvest_state_daily_pool_membership_hash CHECK (
    length(capacity_pool_membership_hash) = 64
    AND lower(capacity_pool_membership_hash) = capacity_pool_membership_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(capacity_pool_membership_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_harvest_state_daily_pool_labor_ratio CHECK (labor_availability_ratio >= 0 AND labor_availability_ratio <= 1),
  CONSTRAINT ck_harvest_state_daily_pool_weather_ratio CHECK (weather_harvest_efficiency_ratio >= 0 AND weather_harvest_efficiency_ratio <= 1),
  CONSTRAINT ck_harvest_state_daily_pool_operational_ratio CHECK (operational_efficiency_ratio >= 0 AND operational_efficiency_ratio <= 1),
  CONSTRAINT ck_hsdp_open_inv_nn CHECK (opening_mature_inventory_kg >= 0),
  CONSTRAINT ck_hsdp_supply_nn CHECK (natural_maturity_supply_kg >= 0),
  CONSTRAINT ck_hsdp_avail_nn CHECK (available_mature_quantity_kg >= 0),
  CONSTRAINT ck_hsdp_loss_nn CHECK (mature_inventory_loss_quantity_kg >= 0),
  CONSTRAINT ck_hsdp_harvestable_nn CHECK (harvestable_mature_quantity_kg >= 0),
  CONSTRAINT ck_hsdp_nom_cap_nn CHECK (nominal_harvest_capacity_kg_per_day >= 0),
  CONSTRAINT ck_hsdp_eff_cap_nn CHECK (effective_harvest_capacity_kg_per_day >= 0),
  CONSTRAINT ck_hsdp_day_cap_nn CHECK (effective_capacity_for_day_kg >= 0),
  CONSTRAINT ck_hsdp_harvested_nn CHECK (harvested_quantity_kg >= 0),
  CONSTRAINT ck_hsdp_close_inv_nn CHECK (closing_mature_inventory_kg >= 0),
  CONSTRAINT ck_hsdp_backlog_nn CHECK (unharvested_backlog_kg >= 0),
  CONSTRAINT ck_hsdp_arrival_nn CHECK (arrival_quantity_kg >= 0),
  CONSTRAINT ck_hsdp_open_coh_nn CHECK (opening_cohort_count >= 0),
  CONSTRAINT ck_hsdp_close_coh_nn CHECK (closing_cohort_count >= 0),
  CONSTRAINT ck_hsdp_members_nn CHECK (member_count >= 0),
  CONSTRAINT fk_harvest_state_daily_pool_run_id FOREIGN KEY (harvest_state_run_id) REFERENCES harvest_state_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_harvest_state_daily_pool_business_key UNIQUE (harvest_state_run_id, state_date, capacity_pool_id, forecast_quantile)
);

CREATE INDEX IF NOT EXISTS ix_harvest_state_daily_pool_run_id
ON harvest_state_daily_pool_row (harvest_state_run_id);

CREATE TABLE IF NOT EXISTS harvest_state_daily_member_row (
  id BIGSERIAL PRIMARY KEY,
  harvest_state_run_id BIGINT NOT NULL,
  state_date DATE NOT NULL,
  forecast_quantile TEXT NOT NULL,
  capacity_pool_id TEXT NOT NULL,
  capacity_pool_grain TEXT NOT NULL,
  capacity_pool_membership_hash TEXT NOT NULL,
  farm_id BIGINT NOT NULL,
  subfarm_id BIGINT,
  subfarm_identity_key TEXT NOT NULL,
  variety_id BIGINT NOT NULL,
  destination_factory_id BIGINT NOT NULL,
  opening_mature_inventory_kg NUMERIC(18,3) NOT NULL,
  natural_maturity_supply_kg NUMERIC(18,3) NOT NULL,
  available_mature_quantity_kg NUMERIC(18,3) NOT NULL,
  mature_inventory_loss_quantity_kg NUMERIC(18,3) NOT NULL,
  harvestable_mature_quantity_kg NUMERIC(18,3) NOT NULL,
  allocated_harvest_capacity_kg NUMERIC(18,3) NOT NULL,
  harvested_quantity_kg NUMERIC(18,3) NOT NULL,
  closing_mature_inventory_kg NUMERIC(18,3) NOT NULL,
  unharvested_backlog_kg NUMERIC(18,3) NOT NULL,
  arrival_quantity_kg NUMERIC(18,3) NOT NULL,
  opening_cohort_count BIGINT NOT NULL,
  closing_cohort_count BIGINT NOT NULL,
  cohort_source_ref_hashes JSONB NOT NULL,
  CONSTRAINT ck_harvest_state_daily_member_quantile CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
  CONSTRAINT ck_harvest_state_daily_member_grain CHECK (capacity_pool_grain IN ('SUBFARM_VARIETY', 'SUBFARM', 'FARM')),
  CONSTRAINT ck_harvest_state_daily_member_membership_hash CHECK (
    length(capacity_pool_membership_hash) = 64
    AND lower(capacity_pool_membership_hash) = capacity_pool_membership_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(capacity_pool_membership_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_harvest_state_daily_member_subfarm_identity_key CHECK (subfarm_identity_key <> ''),
  CONSTRAINT ck_hsdm_open_inv_nn CHECK (opening_mature_inventory_kg >= 0),
  CONSTRAINT ck_hsdm_supply_nn CHECK (natural_maturity_supply_kg >= 0),
  CONSTRAINT ck_hsdm_avail_nn CHECK (available_mature_quantity_kg >= 0),
  CONSTRAINT ck_hsdm_loss_nn CHECK (mature_inventory_loss_quantity_kg >= 0),
  CONSTRAINT ck_hsdm_harvestable_nn CHECK (harvestable_mature_quantity_kg >= 0),
  CONSTRAINT ck_hsdm_alloc_cap_nn CHECK (allocated_harvest_capacity_kg >= 0),
  CONSTRAINT ck_hsdm_harvested_nn CHECK (harvested_quantity_kg >= 0),
  CONSTRAINT ck_hsdm_close_inv_nn CHECK (closing_mature_inventory_kg >= 0),
  CONSTRAINT ck_hsdm_backlog_nn CHECK (unharvested_backlog_kg >= 0),
  CONSTRAINT ck_hsdm_arrival_nn CHECK (arrival_quantity_kg >= 0),
  CONSTRAINT ck_hsdm_open_coh_nn CHECK (opening_cohort_count >= 0),
  CONSTRAINT ck_hsdm_close_coh_nn CHECK (closing_cohort_count >= 0),
  CONSTRAINT fk_harvest_state_daily_member_run_id FOREIGN KEY (harvest_state_run_id) REFERENCES harvest_state_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_harvest_state_daily_member_business_key UNIQUE (harvest_state_run_id, state_date, capacity_pool_id, farm_id, subfarm_identity_key, variety_id, forecast_quantile)
);

CREATE INDEX IF NOT EXISTS ix_harvest_state_daily_member_run_id
ON harvest_state_daily_member_row (harvest_state_run_id);

CREATE TABLE IF NOT EXISTS harvest_state_cohort_transition_row (
  id BIGSERIAL PRIMARY KEY,
  harvest_state_run_id BIGINT NOT NULL,
  state_date DATE NOT NULL,
  forecast_quantile TEXT NOT NULL,
  capacity_pool_id TEXT NOT NULL,
  farm_id BIGINT NOT NULL,
  subfarm_id BIGINT,
  variety_id BIGINT NOT NULL,
  destination_factory_id BIGINT NOT NULL,
  capacity_pool_membership_hash TEXT NOT NULL,
  stable_cohort_key TEXT NOT NULL,
  stable_cohort_key_schema_version TEXT NOT NULL,
  source_ref_hash TEXT NOT NULL,
  source_ref JSONB NOT NULL,
  cohort_date DATE NOT NULL,
  opening_quantity_kg NUMERIC(18,3) NOT NULL,
  new_supply_quantity_kg NUMERIC(18,3) NOT NULL,
  quantity_before_loss_kg NUMERIC(18,3) NOT NULL,
  mature_inventory_loss_quantity_kg NUMERIC(18,3) NOT NULL,
  quantity_before_harvest_kg NUMERIC(18,3) NOT NULL,
  harvested_quantity_kg NUMERIC(18,3) NOT NULL,
  closing_quantity_kg NUMERIC(18,3) NOT NULL,
  harvest_anchor_at TIMESTAMPTZ,
  arrival_at TIMESTAMPTZ,
  arrival_local_date DATE,
  arrival_quantity_kg NUMERIC(18,3) NOT NULL,
  CONSTRAINT ck_harvest_state_cohort_transition_quantile CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
  CONSTRAINT ck_harvest_state_cohort_transition_stable_key CHECK (
    length(stable_cohort_key) = 64
    AND lower(stable_cohort_key) = stable_cohort_key
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(stable_cohort_key, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_harvest_state_cohort_transition_source_ref_hash CHECK (
    length(source_ref_hash) = 64
    AND lower(source_ref_hash) = source_ref_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(source_ref_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_harvest_state_cohort_transition_membership_hash CHECK (
    length(capacity_pool_membership_hash) = 64
    AND lower(capacity_pool_membership_hash) = capacity_pool_membership_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(capacity_pool_membership_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_hsct_open_qty_nn CHECK (opening_quantity_kg >= 0),
  CONSTRAINT ck_hsct_new_supply_nn CHECK (new_supply_quantity_kg >= 0),
  CONSTRAINT ck_hsct_before_loss_nn CHECK (quantity_before_loss_kg >= 0),
  CONSTRAINT ck_hsct_loss_nn CHECK (mature_inventory_loss_quantity_kg >= 0),
  CONSTRAINT ck_hsct_before_harvest_nn CHECK (quantity_before_harvest_kg >= 0),
  CONSTRAINT ck_hsct_harvested_nn CHECK (harvested_quantity_kg >= 0),
  CONSTRAINT ck_hsct_close_qty_nn CHECK (closing_quantity_kg >= 0),
  CONSTRAINT ck_hsct_arrival_nn CHECK (arrival_quantity_kg >= 0),
  CONSTRAINT fk_harvest_state_cohort_transition_run_id FOREIGN KEY (harvest_state_run_id) REFERENCES harvest_state_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_harvest_state_cohort_transition_business_key UNIQUE (harvest_state_run_id, state_date, capacity_pool_id, forecast_quantile, stable_cohort_key)
);

CREATE INDEX IF NOT EXISTS ix_harvest_state_cohort_transition_run_id
ON harvest_state_cohort_transition_row (harvest_state_run_id);

CREATE TABLE IF NOT EXISTS harvest_state_future_arrival_row (
  id BIGSERIAL PRIMARY KEY,
  harvest_state_run_id BIGINT NOT NULL,
  capacity_pool_id TEXT NOT NULL,
  farm_id BIGINT NOT NULL,
  subfarm_id BIGINT,
  subfarm_identity_key TEXT NOT NULL,
  destination_factory_id BIGINT NOT NULL,
  arrival_local_date DATE NOT NULL,
  variety_id BIGINT NOT NULL,
  forecast_quantile TEXT NOT NULL,
  quantity_kg NUMERIC(18,3) NOT NULL,
  harvest_to_arrival_lag_days BIGINT NOT NULL,
  farm_timezone TEXT NOT NULL,
  destination_factory_timezone TEXT NOT NULL,
  CONSTRAINT ck_harvest_state_future_arrival_quantile CHECK (forecast_quantile IN ('P50', 'P80', 'P90')),
  CONSTRAINT ck_harvest_state_future_arrival_subfarm_identity_key CHECK (subfarm_identity_key <> ''),
  CONSTRAINT ck_harvest_state_future_arrival_lag_non_negative CHECK (harvest_to_arrival_lag_days >= 0),
  CONSTRAINT ck_harvest_state_future_arrival_quantity_non_negative CHECK (quantity_kg >= 0),
  CONSTRAINT fk_harvest_state_future_arrival_run_id FOREIGN KEY (harvest_state_run_id) REFERENCES harvest_state_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_harvest_state_future_arrival_business_key UNIQUE (harvest_state_run_id, arrival_local_date, capacity_pool_id, farm_id, subfarm_identity_key, variety_id, forecast_quantile)
);

CREATE INDEX IF NOT EXISTS ix_harvest_state_future_arrival_run_id
ON harvest_state_future_arrival_row (harvest_state_run_id);

CREATE TABLE IF NOT EXISTS residual_model_training_run (
  id BIGSERIAL CONSTRAINT pk_residual_model_training_run PRIMARY KEY,
  execution_status TEXT NOT NULL,
  eligibility_status TEXT NOT NULL,
  model_family TEXT NOT NULL,
  model_version TEXT NOT NULL,
  feature_schema_version TEXT NOT NULL,
  feature_schema_hash TEXT NOT NULL,
  artifact_schema_version TEXT NOT NULL,
  training_signature TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  config_snapshot JSONB NOT NULL,
  manifest_hash TEXT NOT NULL,
  manifest_snapshot JSONB NOT NULL,
  feature_audit_summary JSONB NOT NULL,
  category_encoding_snapshot JSONB NOT NULL,
  training_metrics JSONB NOT NULL,
  validation_metrics JSONB NOT NULL,
  eligibility_reasons JSONB NOT NULL,
  warnings JSONB NOT NULL,
  blockers JSONB NOT NULL,
  fallback_reason TEXT,
  input_snapshot JSONB NOT NULL,
  canonical_output JSONB NOT NULL,
  canonical_payload_hash TEXT NOT NULL,
  sample_count BIGINT NOT NULL DEFAULT 0,
  distinct_season_count BIGINT NOT NULL DEFAULT 0,
  distinct_factory_count BIGINT NOT NULL DEFAULT 0,
  manifest_row_count BIGINT NOT NULL DEFAULT 0,
  expected_artifact_count BIGINT NOT NULL DEFAULT 0,
  python_version TEXT NOT NULL,
  numpy_version TEXT NOT NULL,
  sklearn_version TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  error_message TEXT,
  typed_attempt JSONB,
  CONSTRAINT ck_residual_model_training_run_execution_status CHECK (execution_status IN ('running', 'completed', 'blocked', 'failed')),
  CONSTRAINT ck_residual_model_training_run_eligibility_status CHECK (eligibility_status IN ('not_evaluated', 'eligible', 'ineligible')),
  CONSTRAINT ck_residual_model_training_run_sample_count CHECK (sample_count >= 0),
  CONSTRAINT ck_residual_model_training_run_season_count CHECK (distinct_season_count >= 0),
  CONSTRAINT ck_residual_model_training_run_factory_count CHECK (distinct_factory_count >= 0),
  CONSTRAINT ck_residual_model_training_run_manifest_row_count CHECK (manifest_row_count >= 0),
  CONSTRAINT ck_residual_model_training_run_expected_artifact_count CHECK (expected_artifact_count >= 0),
  CONSTRAINT ck_residual_model_training_run_completed_eligible_artifacts CHECK ((execution_status != 'completed' OR eligibility_status != 'eligible' OR expected_artifact_count = 3)),
  CONSTRAINT ck_residual_model_training_run_completed_ineligible_artifacts CHECK ((execution_status != 'completed' OR eligibility_status != 'ineligible' OR expected_artifact_count = 0)),
  CONSTRAINT ck_residual_model_training_run_blocked_failed_artifacts CHECK ((execution_status NOT IN ('blocked', 'failed') OR expected_artifact_count = 0)),
  CONSTRAINT ck_residual_model_training_run_eligible_only_when_completed CHECK ((eligibility_status != 'eligible' OR execution_status = 'completed')),
  CONSTRAINT ck_residual_model_training_run_signature CHECK (
    length(training_signature) = 64
    AND lower(training_signature) = training_signature
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(training_signature, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_training_run_config_hash CHECK (
    length(config_hash) = 64
    AND lower(config_hash) = config_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(config_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_training_run_manifest_hash CHECK (
    length(manifest_hash) = 64
    AND lower(manifest_hash) = manifest_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(manifest_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_training_run_feature_schema_hash CHECK (
    length(feature_schema_hash) = 64
    AND lower(feature_schema_hash) = feature_schema_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_schema_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_training_run_payload_hash CHECK (
    length(canonical_payload_hash) = 64
    AND lower(canonical_payload_hash) = canonical_payload_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(canonical_payload_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT uq_residual_model_training_run_signature UNIQUE (training_signature)
);

CREATE INDEX IF NOT EXISTS ix_residual_model_training_run_execution_status
ON residual_model_training_run (execution_status);
CREATE INDEX IF NOT EXISTS ix_residual_model_training_run_eligibility_status
ON residual_model_training_run (eligibility_status);

CREATE TABLE IF NOT EXISTS residual_model_manifest_row (
  id BIGSERIAL CONSTRAINT pk_residual_model_manifest_row PRIMARY KEY,
  training_run_id BIGINT NOT NULL,
  row_index BIGINT NOT NULL,
  split TEXT NOT NULL,
  include BOOLEAN NOT NULL,
  season_id BIGINT NOT NULL,
  destination_factory_id BIGINT NOT NULL,
  task9_run_id BIGINT NOT NULL,
  task9_result_hash TEXT NOT NULL,
  as_of_date DATE NOT NULL,
  target_arrival_local_date DATE NOT NULL,
  forecast_horizon_days BIGINT NOT NULL,
  label_analytics_build_run_id BIGINT NOT NULL,
  label_actual_source_max_raw_id BIGINT NOT NULL,
  label_actual_aggregation_version TEXT NOT NULL,
  label_actual_config_hash TEXT NOT NULL,
  label_actual_source_cutoff TIMESTAMPTZ NOT NULL,
  feature_analytics_build_run_id BIGINT NOT NULL,
  feature_actual_source_max_raw_id BIGINT NOT NULL,
  feature_actual_aggregation_version TEXT NOT NULL,
  feature_actual_config_hash TEXT NOT NULL,
  feature_actual_source_cutoff TIMESTAMPTZ NOT NULL,
  observed_effective_receipt_kg NUMERIC(18,6) NOT NULL,
  structural_p50_kg NUMERIC(18,6) NOT NULL,
  structural_p80_kg NUMERIC(18,6) NOT NULL,
  structural_p90_kg NUMERIC(18,6) NOT NULL,
  residual_label_kg NUMERIC(18,6) NOT NULL,
  sample_weight NUMERIC(18,6) NOT NULL,
  feature_vector_hash TEXT NOT NULL,
  feature_visibility_audit_hash TEXT NOT NULL,
  exclusion_reason TEXT,
  source_refs JSONB NOT NULL,
  row_payload JSONB NOT NULL,
  CONSTRAINT ck_residual_model_manifest_row_split CHECK (split IN ('train', 'validation', 'test')),
  CONSTRAINT ck_residual_model_manifest_row_task9_hash CHECK (
    length(task9_result_hash) = 64
    AND lower(task9_result_hash) = task9_result_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(task9_result_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_manifest_row_vector_hash CHECK (
    length(feature_vector_hash) = 64
    AND lower(feature_vector_hash) = feature_vector_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_vector_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_manifest_row_audit_hash CHECK (
    length(feature_visibility_audit_hash) = 64
    AND lower(feature_visibility_audit_hash) = feature_visibility_audit_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_visibility_audit_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_manifest_row_label_config_hash CHECK (
    length(label_actual_config_hash) = 64
    AND lower(label_actual_config_hash) = label_actual_config_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(label_actual_config_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_manifest_row_feature_config_hash CHECK (
    length(feature_actual_config_hash) = 64
    AND lower(feature_actual_config_hash) = feature_actual_config_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_actual_config_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_manifest_row_row_index CHECK (row_index > 0),
  CONSTRAINT ck_residual_model_manifest_row_forecast_horizon CHECK (forecast_horizon_days >= 0),
  CONSTRAINT ck_residual_model_manifest_row_sample_weight CHECK (sample_weight >= 0),
  CONSTRAINT fk_residual_model_manifest_row_training_run_id FOREIGN KEY (training_run_id) REFERENCES residual_model_training_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_manifest_row_season_id FOREIGN KEY (season_id) REFERENCES dim_season(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_manifest_row_factory_id FOREIGN KEY (destination_factory_id) REFERENCES dim_factory(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_manifest_row_task9_run_id FOREIGN KEY (task9_run_id) REFERENCES harvest_state_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_manifest_row_label_analytics_build_run_id FOREIGN KEY (label_analytics_build_run_id) REFERENCES analytics_build_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_manifest_row_feature_analytics_build_run_id FOREIGN KEY (feature_analytics_build_run_id) REFERENCES analytics_build_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_residual_model_manifest_row_run_index UNIQUE (training_run_id, row_index)
);

CREATE INDEX IF NOT EXISTS ix_residual_model_manifest_row_run_id
ON residual_model_manifest_row (training_run_id);

CREATE TABLE IF NOT EXISTS residual_model_artifact (
  id BIGSERIAL CONSTRAINT pk_residual_model_artifact PRIMARY KEY,
  training_run_id BIGINT NOT NULL,
  quantile_label TEXT NOT NULL,
  artifact_format TEXT NOT NULL,
  artifact_schema_version TEXT NOT NULL,
  estimator_type TEXT NOT NULL,
  loss_name TEXT NOT NULL,
  quantile_value NUMERIC(6,4) NOT NULL,
  artifact_bytes BYTEA NOT NULL,
  artifact_sha256 TEXT NOT NULL,
  feature_schema_version TEXT NOT NULL,
  feature_schema_hash TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  trusted_internal_source BOOLEAN NOT NULL DEFAULT true,
  metadata JSONB NOT NULL,
  python_version TEXT NOT NULL,
  numpy_version TEXT NOT NULL,
  sklearn_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_residual_model_artifact_quantile_label CHECK (quantile_label IN ('P50', 'P80', 'P90')),
  CONSTRAINT ck_residual_model_artifact_format CHECK (artifact_format IN ('joblib_bundle')),
  CONSTRAINT ck_residual_model_artifact_estimator_type CHECK (estimator_type IN ('HistGradientBoostingRegressor')),
  CONSTRAINT ck_residual_model_artifact_loss_name CHECK (loss_name IN ('quantile')),
  CONSTRAINT ck_residual_model_artifact_trusted_source CHECK (trusted_internal_source = true),
  CONSTRAINT ck_residual_model_artifact_quantile_value CHECK (
    (quantile_label = 'P50' AND quantile_value = 0.5000) OR
    (quantile_label = 'P80' AND quantile_value = 0.8000) OR
    (quantile_label = 'P90' AND quantile_value = 0.9000)
  ),
  CONSTRAINT ck_residual_model_artifact_sha256 CHECK (
    length(artifact_sha256) = 64
    AND lower(artifact_sha256) = artifact_sha256
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(artifact_sha256, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_artifact_feature_schema_hash CHECK (
    length(feature_schema_hash) = 64
    AND lower(feature_schema_hash) = feature_schema_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_schema_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_artifact_config_hash CHECK (
    length(config_hash) = 64
    AND lower(config_hash) = config_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(config_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT fk_residual_model_artifact_training_run_id FOREIGN KEY (training_run_id) REFERENCES residual_model_training_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_residual_model_artifact_run_quantile UNIQUE (training_run_id, quantile_label),
  CONSTRAINT uq_residual_model_artifact_sha256 UNIQUE (artifact_sha256)
);

CREATE INDEX IF NOT EXISTS ix_residual_model_artifact_training_run_id
ON residual_model_artifact (training_run_id);

CREATE TABLE IF NOT EXISTS residual_model_prediction_run (
  id BIGSERIAL CONSTRAINT pk_residual_model_prediction_run PRIMARY KEY,
  training_run_id BIGINT,
  task9_run_id BIGINT NOT NULL,
  task9_result_hash TEXT NOT NULL,
  execution_status TEXT NOT NULL,
  mode TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  feature_schema_version TEXT NOT NULL,
  feature_schema_hash TEXT NOT NULL,
  artifact_hashes JSONB NOT NULL,
  prediction_input_signature TEXT NOT NULL,
  prediction_hash TEXT NOT NULL,
  feature_audit JSONB NOT NULL,
  warnings JSONB NOT NULL,
  blockers JSONB NOT NULL,
  fallback_reason TEXT,
  expected_prediction_row_count BIGINT NOT NULL DEFAULT 0,
  input_snapshot JSONB NOT NULL,
  canonical_output JSONB NOT NULL,
  canonical_payload_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  typed_attempt JSONB,
  CONSTRAINT ck_residual_model_prediction_run_execution_status CHECK (execution_status IN ('completed', 'blocked', 'failed')),
  CONSTRAINT ck_residual_model_prediction_run_mode CHECK (mode IN ('residual_corrected', 'structural_only', 'blocked')),
  CONSTRAINT ck_residual_model_prediction_run_row_count CHECK (expected_prediction_row_count >= 0),
  CONSTRAINT ck_residual_model_prediction_run_blocked_zero CHECK ((execution_status != 'blocked' OR expected_prediction_row_count = 0)),
  CONSTRAINT ck_residual_model_prediction_run_structural_fallback CHECK ((execution_status != 'completed' OR mode != 'structural_only' OR fallback_reason IS NOT NULL)),
  CONSTRAINT ck_residual_model_prediction_run_task9_hash CHECK (
    length(task9_result_hash) = 64
    AND lower(task9_result_hash) = task9_result_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(task9_result_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_run_config_hash CHECK (
    length(config_hash) = 64
    AND lower(config_hash) = config_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(config_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_run_feature_schema_hash CHECK (
    length(feature_schema_hash) = 64
    AND lower(feature_schema_hash) = feature_schema_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_schema_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_run_input_signature CHECK (
    length(prediction_input_signature) = 64
    AND lower(prediction_input_signature) = prediction_input_signature
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(prediction_input_signature, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_run_prediction_hash CHECK (
    length(prediction_hash) = 64
    AND lower(prediction_hash) = prediction_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(prediction_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_run_payload_hash CHECK (
    length(canonical_payload_hash) = 64
    AND lower(canonical_payload_hash) = canonical_payload_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(canonical_payload_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT fk_residual_model_prediction_run_training_run_id FOREIGN KEY (training_run_id) REFERENCES residual_model_training_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_prediction_run_task9_run_id FOREIGN KEY (task9_run_id) REFERENCES harvest_state_run(id) ON DELETE RESTRICT,
  CONSTRAINT uq_residual_model_prediction_run_input_signature UNIQUE (prediction_input_signature)
);

CREATE INDEX IF NOT EXISTS ix_residual_model_prediction_run_execution_status
ON residual_model_prediction_run (execution_status);
CREATE INDEX IF NOT EXISTS ix_residual_model_prediction_run_task9_run_id
ON residual_model_prediction_run (task9_run_id);

CREATE TABLE IF NOT EXISTS residual_model_prediction_row (
  id BIGSERIAL CONSTRAINT pk_residual_model_prediction_row PRIMARY KEY,
  prediction_run_id BIGINT NOT NULL,
  model_run_id BIGINT,
  task9_run_id BIGINT NOT NULL,
  task9_result_hash TEXT NOT NULL,
  destination_factory_id BIGINT NOT NULL,
  arrival_local_date DATE NOT NULL,
  forecast_horizon_days BIGINT NOT NULL,
  structural_p50_kg NUMERIC(18,6) NOT NULL,
  structural_p80_kg NUMERIC(18,6) NOT NULL,
  structural_p90_kg NUMERIC(18,6) NOT NULL,
  raw_residual_p50_kg NUMERIC(18,6) NOT NULL,
  raw_residual_p80_kg NUMERIC(18,6) NOT NULL,
  raw_residual_p90_kg NUMERIC(18,6) NOT NULL,
  corrected_raw_p50_kg NUMERIC(18,6) NOT NULL,
  corrected_raw_p80_kg NUMERIC(18,6) NOT NULL,
  corrected_raw_p90_kg NUMERIC(18,6) NOT NULL,
  corrected_p50_kg NUMERIC(18,6) NOT NULL,
  corrected_p80_kg NUMERIC(18,6) NOT NULL,
  corrected_p90_kg NUMERIC(18,6) NOT NULL,
  nonnegative_projection_applied BOOLEAN NOT NULL,
  quantile_projection_applied BOOLEAN NOT NULL,
  projection_reasons JSONB NOT NULL,
  feature_vector_hash TEXT NOT NULL,
  feature_audit_hash TEXT NOT NULL,
  prediction_row_hash TEXT NOT NULL,
  mode TEXT NOT NULL,
  fallback_reason TEXT,
  CONSTRAINT ck_residual_model_prediction_row_task9_hash CHECK (
    length(task9_result_hash) = 64
    AND lower(task9_result_hash) = task9_result_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(task9_result_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_row_vector_hash CHECK (
    length(feature_vector_hash) = 64
    AND lower(feature_vector_hash) = feature_vector_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_vector_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_row_audit_hash CHECK (
    length(feature_audit_hash) = 64
    AND lower(feature_audit_hash) = feature_audit_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(feature_audit_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_row_hash CHECK (
    length(prediction_row_hash) = 64
    AND lower(prediction_row_hash) = prediction_row_hash
    AND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(prediction_row_hash, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''
  ),
  CONSTRAINT ck_residual_model_prediction_row_mode CHECK (mode IN ('residual_corrected', 'structural_only', 'blocked')),
  CONSTRAINT ck_residual_model_prediction_row_structural_fallback CHECK ((mode != 'structural_only' OR fallback_reason IS NOT NULL)),
  CONSTRAINT ck_residual_model_prediction_row_corrected_no_fallback CHECK ((mode != 'residual_corrected' OR fallback_reason IS NULL)),
  CONSTRAINT ck_residual_model_prediction_row_nonnegative CHECK (corrected_p50_kg >= 0 AND corrected_p80_kg >= 0 AND corrected_p90_kg >= 0),
  CONSTRAINT ck_residual_model_prediction_row_monotonic CHECK (corrected_p50_kg <= corrected_p80_kg AND corrected_p80_kg <= corrected_p90_kg),
  CONSTRAINT ck_residual_model_prediction_row_forecast_horizon CHECK (forecast_horizon_days >= 0),
  CONSTRAINT ck_residual_model_prediction_row_structural_only CHECK (
    mode != 'structural_only' OR (raw_residual_p50_kg = 0 AND raw_residual_p80_kg = 0 AND raw_residual_p90_kg = 0)
  ),
  CONSTRAINT fk_residual_model_prediction_row_prediction_run_id FOREIGN KEY (prediction_run_id) REFERENCES residual_model_prediction_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_prediction_row_model_run_id FOREIGN KEY (model_run_id) REFERENCES residual_model_training_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_prediction_row_task9_run_id FOREIGN KEY (task9_run_id) REFERENCES harvest_state_run(id) ON DELETE RESTRICT,
  CONSTRAINT fk_residual_model_prediction_row_factory_id FOREIGN KEY (destination_factory_id) REFERENCES dim_factory(id) ON DELETE RESTRICT,
  CONSTRAINT uq_residual_model_prediction_row_run_factory_date UNIQUE (prediction_run_id, destination_factory_id, arrival_local_date)
);

CREATE INDEX IF NOT EXISTS ix_residual_model_prediction_row_prediction_run_id
ON residual_model_prediction_row (prediction_run_id);
