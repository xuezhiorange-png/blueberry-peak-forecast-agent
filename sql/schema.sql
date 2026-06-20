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
