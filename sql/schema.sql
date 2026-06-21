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
