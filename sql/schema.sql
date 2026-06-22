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
  CONSTRAINT fk_parameter_observation_library_version_id_parameter_library_version FOREIGN KEY (library_version_id) REFERENCES parameter_library_version(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_variety_id_dim_variety FOREIGN KEY (variety_id) REFERENCES dim_variety(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_farm_id_dim_farm FOREIGN KEY (farm_id) REFERENCES dim_farm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_subfarm_id_dim_subfarm FOREIGN KEY (subfarm_id) REFERENCES dim_subfarm(id) ON DELETE RESTRICT,
  CONSTRAINT fk_parameter_observation_location_reference_id_location_reference FOREIGN KEY (location_reference_id) REFERENCES location_reference(id) ON DELETE RESTRICT,
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
  CONSTRAINT fk_parameter_inference_run_library_version_id_parameter_library_version FOREIGN KEY (library_version_id) REFERENCES parameter_library_version(id) ON DELETE RESTRICT
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
