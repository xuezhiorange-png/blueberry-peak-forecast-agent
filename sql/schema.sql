CREATE TABLE IF NOT EXISTS dim_season (
  id BIGSERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_factory (
  id BIGSERIAL PRIMARY KEY,
  code TEXT UNIQUE,
  name TEXT UNIQUE NOT NULL,
  region_name TEXT,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  altitude_m NUMERIC(8,2),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_farm (
  id BIGSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  altitude_m NUMERIC(8,2)
);

CREATE TABLE IF NOT EXISTS dim_subfarm (
  id BIGSERIAL PRIMARY KEY,
  farm_id BIGINT NOT NULL REFERENCES dim_farm(id),
  name TEXT NOT NULL,
  altitude_m NUMERIC(8,2),
  UNIQUE(farm_id, name)
);

CREATE TABLE IF NOT EXISTS dim_variety (
  id BIGSERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_grade (
  id BIGSERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  is_analysis_eligible_default BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS ingest_file (
  id BIGSERIAL PRIMARY KEY,
  season_id BIGINT NOT NULL REFERENCES dim_season(id),
  original_name TEXT NOT NULL,
  object_key TEXT,
  sha256 CHAR(64) UNIQUE NOT NULL,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL,
  report JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS fact_receipt_raw (
  id BIGSERIAL PRIMARY KEY,
  ingest_file_id BIGINT NOT NULL REFERENCES ingest_file(id),
  sheet_name TEXT NOT NULL,
  source_row_no INTEGER NOT NULL,
  row_fingerprint CHAR(64) NOT NULL,
  receipt_date DATE,
  link_name_raw TEXT,
  farm_raw TEXT,
  subfarm_raw TEXT,
  variety_raw TEXT,
  grade_raw TEXT,
  weight_kg NUMERIC(18,6),
  factory_raw TEXT,
  raw_payload JSONB NOT NULL,
  UNIQUE(ingest_file_id, sheet_name, source_row_no)
);

CREATE TABLE IF NOT EXISTS fact_receipt_daily (
  id BIGSERIAL PRIMARY KEY,
  season_id BIGINT NOT NULL REFERENCES dim_season(id),
  receipt_date DATE NOT NULL,
  factory_id BIGINT NOT NULL REFERENCES dim_factory(id),
  farm_id BIGINT REFERENCES dim_farm(id),
  subfarm_id BIGINT REFERENCES dim_subfarm(id),
  variety_id BIGINT REFERENCES dim_variety(id),
  grade_id BIGINT REFERENCES dim_grade(id),
  weight_kg NUMERIC(18,6) NOT NULL,
  is_analysis_eligible BOOLEAN NOT NULL,
  exclusion_reason TEXT,
  is_holiday BOOLEAN NOT NULL DEFAULT FALSE,
  holiday_phase TEXT,
  data_version TEXT NOT NULL,
  UNIQUE(season_id, receipt_date, factory_id, farm_id, subfarm_id, variety_id, grade_id, data_version)
);

CREATE TABLE IF NOT EXISTS fact_yield_plan_version (
  id BIGSERIAL PRIMARY KEY,
  season_id BIGINT NOT NULL REFERENCES dim_season(id),
  farm_id BIGINT NOT NULL REFERENCES dim_farm(id),
  subfarm_id BIGINT REFERENCES dim_subfarm(id),
  variety_id BIGINT NOT NULL REFERENCES dim_variety(id),
  destination_factory_id BIGINT NOT NULL REFERENCES dim_factory(id),
  valid_from TIMESTAMPTZ NOT NULL,
  area_mu NUMERIC(12,3) NOT NULL,
  expected_yield_kg_per_mu NUMERIC(12,3),
  effective_commodity_rate NUMERIC(8,5),
  expected_effective_total_kg NUMERIC(18,3),
  tree_age_years NUMERIC(6,2),
  pruning_date DATE,
  flowering_date DATE,
  first_pick_date DATE,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_weather_daily (
  id BIGSERIAL PRIMARY KEY,
  location_key TEXT NOT NULL,
  observed_date DATE NOT NULL,
  source TEXT NOT NULL,
  t_mean_c NUMERIC(7,3),
  t_min_c NUMERIC(7,3),
  t_max_c NUMERIC(7,3),
  precipitation_mm NUMERIC(10,3),
  solar_radiation_mj NUMERIC(10,3),
  data_version TEXT NOT NULL,
  UNIQUE(location_key, observed_date, source, data_version)
);

CREATE TABLE IF NOT EXISTS fact_labor_daily (
  id BIGSERIAL PRIMARY KEY,
  subfarm_id BIGINT NOT NULL REFERENCES dim_subfarm(id),
  work_date DATE NOT NULL,
  available_pickers INTEGER,
  planned_hours NUMERIC(6,2),
  actual_pickers INTEGER,
  actual_hours NUMERIC(6,2),
  kg_per_person_hour NUMERIC(10,3),
  source TEXT NOT NULL,
  data_version TEXT NOT NULL,
  UNIQUE(subfarm_id, work_date, data_version)
);

CREATE TABLE IF NOT EXISTS model_run (
  id UUID PRIMARY KEY,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  run_type TEXT NOT NULL,
  as_of_time TIMESTAMPTZ NOT NULL,
  training_cutoff DATE,
  config JSONB NOT NULL,
  metrics JSONB,
  artifact_uri TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS forecast_daily (
  id BIGSERIAL PRIMARY KEY,
  model_run_id UUID NOT NULL REFERENCES model_run(id),
  factory_id BIGINT NOT NULL REFERENCES dim_factory(id),
  forecast_date DATE NOT NULL,
  p50_t NUMERIC(14,4) NOT NULL,
  p80_low_t NUMERIC(14,4),
  p80_high_t NUMERIC(14,4),
  p90_low_t NUMERIC(14,4),
  p90_high_t NUMERIC(14,4),
  natural_maturity_t NUMERIC(14,4),
  harvest_capacity_t NUMERIC(14,4),
  backlog_t NUMERIC(14,4),
  UNIQUE(model_run_id, factory_id, forecast_date)
);

CREATE TABLE IF NOT EXISTS forecast_peak (
  id BIGSERIAL PRIMARY KEY,
  model_run_id UUID NOT NULL REFERENCES model_run(id),
  factory_id BIGINT NOT NULL REFERENCES dim_factory(id),
  raw_peak_p50_t NUMERIC(14,4),
  raw_peak_date DATE,
  stable_peak_p50_t NUMERIC(14,4),
  stable_peak_date DATE,
  stable_peak_p80_t NUMERIC(14,4),
  stable_peak_p90_t NUMERIC(14,4),
  confidence_level TEXT NOT NULL,
  explanation JSONB NOT NULL,
  UNIQUE(model_run_id, factory_id)
);
