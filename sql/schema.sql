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
