"""ECMWF IFS Open Data adapter for prospective S2 weather capture.

The adapter is intentionally small and operator-configured.  It reads the
already-authorized Base location artifact, selects one provider run at or
before the forecast cutoff, preserves the exact index/GRIB byte ranges in an
operator-owned artifact directory, and exposes only the selected Base grid
points to the PIT layer.

This module never reads ERA5-Land and never converts realized weather into a
forecast.  The provider-native run timestamp is the IFS cycle timestamp; a
GRIB generation time is not used as ``issued_at``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from pathlib import Path
from tempfile import TemporaryFile
from typing import Any

from backend.app.pit.canonical import canonical_payload_text, hash_payload
from backend.app.pit.schemas import WeatherForecastSnapshotInput
from backend.app.pit.shadow_forecast import (
    WeatherForecastCaptureResult,
    WeatherForecastProviderError,
)

BASE_LOCATION_AUTHORITY_SHA256 = "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904"
BASE_LOCATION_AUTHORITY_PAYLOAD_HASH = (
    "d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293"
)
BASE_LOCATION_COUNT = 39
PROVIDER_NAME = "ECMWF_IFS_OPEN_DATA"
MODEL_ID = "IFS"
STREAM = "oper"
RESOLUTION = "0p25"
GRID_SELECTION_POLICY = "ECMWF_0P25_NEAREST_GRID_CELL_V1"
GRID_TIE_BREAK = "LOWER_GRID_COORDINATE"
REQUIRED_HORIZONS = (24, 72, 168)
OPTIONAL_HORIZONS = (360,)
PARAMETERS = ("2t", "tp", "ssrd", "10u", "10v")
OPTIONAL_PARAMETERS = ("mn2t3", "mx2t3")
_QUANTUM = Decimal("0.000001")
_GRID_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class BaseForecastLocation:
    base_id: str
    canonical_base_name: str
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True, slots=True)
class GridPoint:
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True, slots=True)
class _FieldIndex:
    step: int
    parameter: str
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class _DecodedField:
    values: Any
    latitudes: Any
    longitudes: Any
    ni: int
    nj: int


@dataclass(frozen=True, slots=True)
class _RunCache:
    run_id: str
    issued_at: datetime
    base_url: str
    index_hashes: Mapping[int, str]
    field_hashes: Mapping[tuple[int, str], str]
    field_values: Mapping[tuple[int, str], Mapping[str, Decimal]]
    grid_points: Mapping[str, GridPoint]
    fetched_at: datetime
    provider_identity: str
    artifact_manifest_hash: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise WeatherForecastProviderError("ECMWF_ARTIFACT_READ_FAILED") from exc


def _write_immutable(path: Path, value: bytes) -> str:
    digest = _sha256_bytes(value)
    try:
        if path.exists():
            existing = path.read_bytes()
            if existing != value:
                raise WeatherForecastProviderError("ECMWF_RAW_ARTIFACT_CONFLICT")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
    except OSError as exc:
        raise WeatherForecastProviderError("ECMWF_ARTIFACT_WRITE_FAILED") from exc
    return digest


def _decimal_grid_point(value: Decimal, resolution: Decimal = Decimal("0.25")) -> Decimal:
    scaled = value / resolution
    lower = scaled.to_integral_value(rounding=ROUND_FLOOR)
    fraction = scaled - lower
    if fraction > Decimal("0.5"):
        selected = lower + 1
    else:
        # An exact tie deliberately chooses the lower grid coordinate.
        selected = lower
    return (selected * resolution).quantize(resolution, rounding=ROUND_HALF_EVEN)


def select_nearest_grid_point(latitude: Decimal, longitude: Decimal) -> GridPoint:
    """Select the ECMWF 0.25-degree point with an explicit tie rule."""

    return GridPoint(
        latitude=_decimal_grid_point(latitude),
        longitude=_decimal_grid_point(longitude),
    )


def _normalize_longitude(value: Decimal) -> Decimal:
    normalized = value
    while normalized > Decimal("180"):
        normalized -= Decimal("360")
    while normalized < Decimal("-180"):
        normalized += Decimal("360")
    return normalized


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(_read_bytes(path))


def load_base_location_authority(
    path: Path,
    *,
    expected_sha256: str = BASE_LOCATION_AUTHORITY_SHA256,
) -> dict[str, BaseForecastLocation]:
    """Load and validate the private, operator-owned 39-Base location file."""

    raw = _read_bytes(path)
    actual_sha256 = _sha256_bytes(raw)
    if actual_sha256 != expected_sha256:
        raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_HASH_MISMATCH")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_INVALID") from exc
    if not isinstance(payload, dict):
        raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_INVALID")
    if payload.get("hash") != BASE_LOCATION_AUTHORITY_PAYLOAD_HASH:
        raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_PAYLOAD_HASH_MISMATCH")
    rows = payload.get("bases")
    if not isinstance(rows, list) or len(rows) != BASE_LOCATION_COUNT:
        raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_COUNT_MISMATCH")
    locations: dict[str, BaseForecastLocation] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_INVALID")
        try:
            base_id = str(row["base_id"])
            name = str(row["canonical_base_name"])
            latitude = Decimal(str(row["latitude"]))
            longitude = Decimal(str(row["longitude"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_INVALID") from exc
        if (
            not base_id
            or not name
            or not latitude.is_finite()
            or not longitude.is_finite()
            or not Decimal("-90") <= latitude <= Decimal("90")
            or not Decimal("-180") <= longitude <= Decimal("180")
            or row.get("coordinate_review_status") != "RANGE_VALID_CRS_UNCONFIRMED"
            or row.get("coordinate_reference_system") != "NOT_ESTABLISHED"
            or base_id in locations
        ):
            raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_INVALID")
        locations[base_id] = BaseForecastLocation(base_id, name, latitude, longitude)
    return locations


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise WeatherForecastProviderError("ECMWF_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _finite_decimal(value: float, *, field: str) -> Decimal:
    if not math.isfinite(value):
        raise WeatherForecastProviderError(f"ECMWF_NONFINITE_{field.upper()}")
    return _quantize(Decimal(str(value)))


def _temperature_celsius(value: float) -> Decimal:
    return _finite_decimal(value - 273.15, field="temperature")


def _precipitation_mm(value: float) -> Decimal:
    if not math.isfinite(value):
        raise WeatherForecastProviderError("ECMWF_NONFINITE_PRECIPITATION")
    if value < 0:
        raise WeatherForecastProviderError("ECMWF_NEGATIVE_PRECIPITATION")
    return _quantize(Decimal(str(value * 1000.0)))


def _solar_radiation(value: float) -> Decimal:
    if not math.isfinite(value):
        raise WeatherForecastProviderError("ECMWF_NONFINITE_SOLAR_RADIATION")
    if value < 0:
        raise WeatherForecastProviderError("ECMWF_NEGATIVE_SOLAR_RADIATION")
    return _finite_decimal(value, field="solar_radiation")


def _wind_speed(u10: float, v10: float) -> Decimal:
    if not math.isfinite(u10) or not math.isfinite(v10):
        raise WeatherForecastProviderError("ECMWF_NONFINITE_WIND")
    return _finite_decimal(math.hypot(u10, v10), field="wind_speed")


def _parameter_rows(index_bytes: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in index_bytes.splitlines():
            if line.strip():
                row = json.loads(line.decode("utf-8"))
                if isinstance(row, dict):
                    rows.append(row)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherForecastProviderError("ECMWF_INDEX_INVALID") from exc
    return rows


def _find_index(rows: Iterable[dict[str, Any]], step: int, parameter: str) -> _FieldIndex | None:
    for row in rows:
        if (
            row.get("step") == str(step)
            and row.get("param") == parameter
            and row.get("levtype") == "sfc"
        ):
            try:
                return _FieldIndex(
                    step=step,
                    parameter=parameter,
                    offset=int(row["_offset"]),
                    length=int(row["_length"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise WeatherForecastProviderError("ECMWF_INDEX_ENTRY_INVALID") from exc
    return None


class ECMWFOpenDataForecastProvider:
    """Read-only, raw-preserving adapter for ECMWF IFS Open Data."""

    provider_name = PROVIDER_NAME

    def __init__(
        self,
        *,
        location_authority_path: Path,
        location_authority_sha256: str = BASE_LOCATION_AUTHORITY_SHA256,
        artifact_root: Path,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self.locations = load_base_location_authority(
            location_authority_path,
            expected_sha256=location_authority_sha256,
        )
        self.artifact_root = artifact_root
        try:
            self.artifact_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WeatherForecastProviderError("ECMWF_ARTIFACT_ROOT_UNAVAILABLE") from exc
        self._urlopen = urlopen or urllib.request.urlopen
        self._run_cache: dict[str, _RunCache] = {}

    @property
    def max_forecast_horizon_hours(self) -> int:
        return 360

    def _request(self, url: str, *, byte_range: tuple[int, int] | None = None) -> bytes:
        headers = {"User-Agent": "blueberry-peak-forecast-agent/0.6"}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end}"
        request = urllib.request.Request(url, headers=headers)
        context = ssl.create_default_context()
        try:
            import certifi

            context.load_verify_locations(certifi.where())
        except ImportError:
            pass
        for attempt in range(3):
            try:
                with self._urlopen(request, context=context, timeout=60) as response:
                    status = int(getattr(response, "status", 200))
                    body = bytes(response.read())
                    if byte_range is not None:
                        expected_length = byte_range[1] - byte_range[0] + 1
                        if status != 206 or len(body) != expected_length:
                            raise WeatherForecastProviderError("ECMWF_RANGE_RESPONSE_INVALID")
                    elif status != 200:
                        raise WeatherForecastProviderError("ECMWF_INDEX_RESPONSE_INVALID")
                    return body
            except WeatherForecastProviderError:
                raise
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise WeatherForecastProviderError("ECMWF_NETWORK_OR_HTTP_FAILURE") from exc
                retry_after = exc.headers.get("Retry-After")
                delay = min(float(retry_after) if retry_after else 2.0**attempt, 8.0)
                time.sleep(max(delay, 0.25))
            except (OSError, urllib.error.URLError) as exc:
                raise WeatherForecastProviderError("ECMWF_NETWORK_OR_HTTP_FAILURE") from exc
        raise WeatherForecastProviderError("ECMWF_NETWORK_OR_HTTP_FAILURE")

    @staticmethod
    def _run_id(issued_at: datetime) -> str:
        return issued_at.strftime("%Y%m%d%H%M%S")

    @staticmethod
    def _run_url(issued_at: datetime) -> str:
        day = issued_at.strftime("%Y%m%d")
        cycle = issued_at.strftime("%H")
        return f"https://data.ecmwf.int/forecasts/{day}/{cycle}z/ifs/{RESOLUTION}/oper"

    def _candidate_runs(self, forecast_created_at: datetime) -> list[datetime]:
        cutoff = _as_utc(forecast_created_at)
        candidates: list[datetime] = []
        for day_offset in range(0, 3):
            day = cutoff.date() - timedelta(days=day_offset)
            for hour in (12, 0):
                candidate = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
                if candidate <= cutoff:
                    candidates.append(candidate)
        return sorted(candidates, reverse=True)

    def _artifact_path(self, run_id: str, name: str) -> Path:
        return self.artifact_root / f"{run_id}-{MODEL_ID}-{RESOLUTION}-{STREAM}" / name

    def _cached_or_request(
        self,
        path: Path,
        url: str,
        *,
        byte_range: tuple[int, int] | None = None,
    ) -> bytes:
        if path.exists():
            return _read_bytes(path)
        return self._request(url, byte_range=byte_range)

    def _decode_grib(self, payload: bytes) -> _DecodedField:
        try:
            import eccodes  # type: ignore[import-untyped]
        except ImportError as exc:
            raise WeatherForecastProviderError("ECMWF_GRIB_DECODER_NOT_AVAILABLE") from exc
        with TemporaryFile() as stream:
            stream.write(payload)
            stream.seek(0)
            handle = eccodes.codes_grib_new_from_file(stream)
            if handle is None:
                raise WeatherForecastProviderError("ECMWF_GRIB_PAYLOAD_INVALID")
            try:
                values = eccodes.codes_get_array(handle, "values")
                latitudes = eccodes.codes_get_array(handle, "latitudes")
                longitudes = eccodes.codes_get_array(handle, "longitudes")
                ni = int(eccodes.codes_get(handle, "Ni"))
                nj = int(eccodes.codes_get(handle, "Nj"))
            except Exception as exc:  # eccodes exposes runtime-specific exception types.
                raise WeatherForecastProviderError("ECMWF_GRIB_DECODE_FAILED") from exc
            finally:
                eccodes.codes_release(handle)
        if (
            len(values) != ni * nj
            or len(latitudes) != len(values)
            or len(longitudes) != len(values)
        ):
            raise WeatherForecastProviderError("ECMWF_GRIB_GRID_SIZE_INVALID")
        return _DecodedField(values, latitudes, longitudes, ni, nj)

    @staticmethod
    def _grid_indices(
        field: _DecodedField,
        locations: Mapping[str, BaseForecastLocation],
    ) -> dict[str, tuple[int, GridPoint]]:
        expected_by_point: dict[GridPoint, list[str]] = {}
        for base_id, location in locations.items():
            expected = select_nearest_grid_point(location.latitude, location.longitude)
            expected_by_point.setdefault(expected, []).append(base_id)
        found: dict[GridPoint, tuple[int, GridPoint]] = {}
        for index, (latitude, longitude) in enumerate(
            zip(field.latitudes, field.longitudes, strict=True)
        ):
            returned = GridPoint(
                latitude=Decimal(str(float(latitude))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_EVEN
                ),
                longitude=_normalize_longitude(
                    Decimal(str(float(longitude))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_EVEN
                    )
                ),
            )
            if returned in expected_by_point and returned not in found:
                found[returned] = (index, returned)
        if set(found) != set(expected_by_point):
            raise WeatherForecastProviderError("ECMWF_GRID_SELECTION_MISMATCH")
        indices = {
            base_id: found[point]
            for point, base_ids in expected_by_point.items()
            for base_id in base_ids
        }
        return indices

    def _load_run(self, issued_at: datetime) -> _RunCache:
        run_id = self._run_id(issued_at)
        cached = self._run_cache.get(run_id)
        if cached is not None:
            return cached
        base_url = self._run_url(issued_at)
        rows_by_step: dict[int, list[dict[str, Any]]] = {}
        index_hashes: dict[int, str] = {}
        field_indexes: dict[tuple[int, str], _FieldIndex] = {}
        horizons = REQUIRED_HORIZONS + OPTIONAL_HORIZONS
        for step in horizons:
            index_url = f"{base_url}/{run_id}-{step}h-oper-fc.index"
            index_path = self._artifact_path(run_id, f"{step:03d}h.index")
            try:
                index_bytes = self._cached_or_request(index_path, index_url)
            except WeatherForecastProviderError as exc:
                if step in OPTIONAL_HORIZONS:
                    continue
                raise exc
            index_hashes[step] = _write_immutable(index_path, index_bytes)
            rows_by_step[step] = _parameter_rows(index_bytes)
            for parameter in PARAMETERS + OPTIONAL_PARAMETERS:
                found = _find_index(rows_by_step[step], step, parameter)
                if found is not None:
                    field_indexes[(step, parameter)] = found
            if any((step, parameter) not in field_indexes for parameter in PARAMETERS):
                if step in REQUIRED_HORIZONS:
                    raise WeatherForecastProviderError("ECMWF_REQUIRED_PARAMETER_MISSING")
                del index_hashes[step]
                del rows_by_step[step]
        if any(step not in index_hashes for step in REQUIRED_HORIZONS):
            raise WeatherForecastProviderError("ECMWF_REQUIRED_HORIZON_MISSING")

        # The private registry is the complete location authority.  Decode the
        # first required field to prove every requested Base has the provider's
        # expected returned grid point before accepting any field values.
        first_key = (REQUIRED_HORIZONS[0], PARAMETERS[0])
        first_index = field_indexes[first_key]
        first_path = self._artifact_path(
            run_id,
            f"{first_index.step:03d}h-{first_index.parameter}.grib2",
        )
        first_bytes = self._cached_or_request(
            first_path,
            f"{base_url}/{run_id}-{first_index.step}h-oper-fc.grib2",
            byte_range=(first_index.offset, first_index.offset + first_index.length - 1),
        )
        first_hash = _write_immutable(first_path, first_bytes)
        field_hashes: dict[tuple[int, str], str] = {first_key: first_hash}
        first_field = self._decode_grib(first_bytes)
        grid_indices = self._grid_indices(first_field, self.locations)
        grid_points = {base_id: item[1] for base_id, item in grid_indices.items()}
        field_values: dict[tuple[int, str], dict[str, Decimal]] = {
            first_key: {
                base_id: _finite_decimal(
                    float(first_field.values[index]),
                    field="provider_value",
                )
                for base_id, (index, _) in grid_indices.items()
            }
        }
        for key, field_index in sorted(field_indexes.items()):
            if key == first_key:
                continue
            field_path = self._artifact_path(
                run_id,
                f"{field_index.step:03d}h-{field_index.parameter}.grib2",
            )
            field_bytes = self._cached_or_request(
                field_path,
                f"{base_url}/{run_id}-{field_index.step}h-oper-fc.grib2",
                byte_range=(field_index.offset, field_index.offset + field_index.length - 1),
            )
            field_hashes[key] = _write_immutable(field_path, field_bytes)
            field = self._decode_grib(field_bytes)
            if (field.ni, field.nj) != (first_field.ni, first_field.nj):
                raise WeatherForecastProviderError("ECMWF_GRID_SELECTION_MISMATCH")
            for _base_id, (index, expected) in grid_indices.items():
                returned = GridPoint(
                    latitude=Decimal(str(float(field.latitudes[index]))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_EVEN
                    ),
                    longitude=_normalize_longitude(
                        Decimal(str(float(field.longitudes[index]))).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_EVEN
                        )
                    ),
                )
                if returned != expected:
                    raise WeatherForecastProviderError("ECMWF_GRID_SELECTION_MISMATCH")
            field_values[key] = {
                base_id: _finite_decimal(float(field.values[index]), field="provider_value")
                for base_id, (index, _) in grid_indices.items()
            }
        fetched_at = datetime.now(UTC)
        provider_identity = (
            f"{PROVIDER_NAME}|model={MODEL_ID}|stream={STREAM}|resolution={RESOLUTION}|run={run_id}"
        )
        artifact_manifest = {
            "schema_version": "V0_6_ECMWF_RAW_ARTIFACT_MANIFEST_V1",
            "provider": PROVIDER_NAME,
            "model": MODEL_ID,
            "stream": STREAM,
            "resolution": RESOLUTION,
            "run_id": run_id,
            "issued_at": issued_at,
            "location_authority_sha256": BASE_LOCATION_AUTHORITY_SHA256,
            "base_count": len(self.locations),
            "grid_selection_policy": GRID_SELECTION_POLICY,
            "grid_tie_break": GRID_TIE_BREAK,
            "index_artifacts": [
                {"step": step, "sha256": index_hashes[step]} for step in sorted(index_hashes)
            ],
            "field_artifacts": [
                {
                    "step": step,
                    "parameter": parameter,
                    "sha256": field_hashes[(step, parameter)],
                }
                for step, parameter in sorted(field_hashes)
            ],
            "selected_grid_coordinates": {
                base_id: {
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                }
                for base_id, point in sorted(grid_points.items())
            },
        }
        manifest_path = self._artifact_path(run_id, "artifact-manifest.json")
        manifest_hash = _write_immutable(
            manifest_path,
            canonical_payload_text(artifact_manifest).encode("utf-8"),
        )
        cache = _RunCache(
            run_id=run_id,
            issued_at=issued_at,
            base_url=base_url,
            index_hashes=index_hashes,
            field_hashes=field_hashes,
            field_values=field_values,
            grid_points=grid_points,
            fetched_at=fetched_at,
            provider_identity=provider_identity,
            artifact_manifest_hash=manifest_hash,
        )
        self._run_cache[run_id] = cache
        return cache

    def _select_run(self, forecast_created_at: datetime) -> _RunCache:
        errors: list[Exception] = []
        for candidate in self._candidate_runs(forecast_created_at):
            try:
                return self._load_run(candidate)
            except WeatherForecastProviderError as exc:
                errors.append(exc)
                continue
        cause = errors[-1] if errors else None
        raise WeatherForecastProviderError("ECMWF_NO_QUALIFIED_RUN") from cause

    def _snapshot_for_base(
        self,
        *,
        cache: _RunCache,
        location: BaseForecastLocation,
        step: int,
    ) -> WeatherForecastSnapshotInput:
        base_id = location.base_id
        values = cache.field_values
        mean_k = values[(step, "2t")][base_id]
        precipitation_m = values[(step, "tp")][base_id]
        solar = values[(step, "ssrd")][base_id]
        wind = _wind_speed(
            float(values[(step, "10u")][base_id]),
            float(values[(step, "10v")][base_id]),
        )
        min_value = values.get((step, "mn2t3"), {}).get(base_id)
        max_value = values.get((step, "mx2t3"), {}).get(base_id)
        source_fields = [
            {
                "step": step,
                "parameter": parameter,
                "sha256": cache.field_hashes[(step, parameter)],
            }
            for parameter in PARAMETERS + OPTIONAL_PARAMETERS
            if (step, parameter) in cache.field_hashes
        ]
        raw_manifest = {
            "provider": PROVIDER_NAME,
            "model": MODEL_ID,
            "stream": STREAM,
            "resolution": RESOLUTION,
            "run_id": cache.run_id,
            "issued_at": cache.issued_at,
            "step": step,
            "index_sha256": cache.index_hashes[step],
            "fields": source_fields,
            "grid_selection_policy": GRID_SELECTION_POLICY,
            "artifact_manifest_sha256": cache.artifact_manifest_hash,
        }
        normalized = {
            "provider_identity": cache.provider_identity,
            "base_id": base_id,
            "requested_coordinates": {
                "latitude": location.latitude,
                "longitude": location.longitude,
            },
            "selected_grid_coordinates": {
                "latitude": cache.grid_points[base_id].latitude,
                "longitude": cache.grid_points[base_id].longitude,
            },
            "valid_at": cache.issued_at + timedelta(hours=step),
            "forecast_horizon_hours": step,
            "temperature_mean_c": _temperature_celsius(float(mean_k)),
            "temperature_min_c": (
                _temperature_celsius(float(min_value)) if min_value is not None else None
            ),
            "temperature_max_c": (
                _temperature_celsius(float(max_value)) if max_value is not None else None
            ),
            "precipitation_mm": _precipitation_mm(float(precipitation_m)),
            "solar_radiation": _solar_radiation(float(solar)),
            "wind_speed": wind,
        }
        raw_reference = canonical_payload_text(
            {
                "artifact_root_relative": f"{cache.run_id}-{MODEL_ID}-{RESOLUTION}-{STREAM}",
                "source_url": f"{cache.base_url}/{cache.run_id}-{step}h-oper-fc.grib2",
                "manifest": raw_manifest,
                "requested_coordinates": normalized["requested_coordinates"],
                "selected_grid_coordinates": normalized["selected_grid_coordinates"],
            }
        )
        raw_payload_hash = hash_payload(raw_manifest)
        normalized_payload_hash = hash_payload(normalized)
        weather_snapshot_id = f"ecmwf-ifs-{cache.run_id}-{base_id}-{step}h"
        return WeatherForecastSnapshotInput(
            weather_snapshot_id=weather_snapshot_id,
            provider=cache.provider_identity,
            base_id=base_id,
            location_id=(
                f"ecmwf-ifs-{cache.grid_points[base_id].latitude}"
                f"-{cache.grid_points[base_id].longitude}"
            ),
            issued_at=cache.issued_at,
            fetched_at=cache.fetched_at,
            known_at=cache.fetched_at,
            valid_at=cache.issued_at + timedelta(hours=step),
            forecast_horizon_hours=step,
            temperature_min=(
                _temperature_celsius(float(min_value)) if min_value is not None else None
            ),
            temperature_max=(
                _temperature_celsius(float(max_value)) if max_value is not None else None
            ),
            temperature_mean=_temperature_celsius(float(mean_k)),
            precipitation=_precipitation_mm(float(precipitation_m)),
            solar_radiation=_solar_radiation(float(solar)),
            wind_speed=wind,
            raw_payload_reference=raw_reference,
            raw_payload_hash=raw_payload_hash,
            normalized_payload_hash=normalized_payload_hash,
        )

    def capture(
        self,
        *,
        base: Mapping[str, object],
        forecast_created_at: datetime,
        target_season: str,
    ) -> WeatherForecastCaptureResult:
        del target_season
        base_id = str(base.get("base_id", ""))
        location = self.locations.get(base_id)
        if location is None:
            raise WeatherForecastProviderError("BASE_LOCATION_AUTHORITY_NOT_FOUND")
        if (
            str(base.get("canonical_base_name", location.canonical_base_name))
            != location.canonical_base_name
        ):
            raise WeatherForecastProviderError("BASE_LOCATION_IDENTITY_MISMATCH")
        cache = self._select_run(_as_utc(forecast_created_at))
        steps = [
            step
            for step in REQUIRED_HORIZONS + OPTIONAL_HORIZONS
            if (step, "2t") in cache.field_values
        ]
        snapshots = tuple(
            self._snapshot_for_base(cache=cache, location=location, step=step) for step in steps
        )
        return WeatherForecastCaptureResult(
            status="CAPTURED",
            provider=cache.provider_identity,
            snapshots=snapshots,
            capture_completed_at=cache.fetched_at,
        )


def configured_weather_forecast_provider() -> ECMWFOpenDataForecastProvider | None:
    """Build the operator-configured provider, or retain explicit unavailability."""

    if os.environ.get("V06_WEATHER_PROVIDER") != PROVIDER_NAME:
        return None
    location_path = os.environ.get("V06_BASE_LOCATION_AUTHORITY_PATH")
    artifact_root = os.environ.get("V06_WEATHER_ARTIFACT_ROOT")
    if not location_path or not artifact_root:
        raise WeatherForecastProviderError("ECMWF_PROVIDER_CONFIGURATION_INCOMPLETE")
    expected_sha = os.environ.get(
        "V06_BASE_LOCATION_AUTHORITY_SHA256", BASE_LOCATION_AUTHORITY_SHA256
    )
    return ECMWFOpenDataForecastProvider(
        location_authority_path=Path(location_path),
        location_authority_sha256=expected_sha,
        artifact_root=Path(artifact_root),
    )


__all__ = [
    "BASE_LOCATION_AUTHORITY_SHA256",
    "BASE_LOCATION_COUNT",
    "ECMWFOpenDataForecastProvider",
    "GRID_SELECTION_POLICY",
    "GridPoint",
    "configured_weather_forecast_provider",
    "load_base_location_authority",
    "select_nearest_grid_point",
]
