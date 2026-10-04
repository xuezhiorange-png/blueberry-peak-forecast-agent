"""One run-relative proxy/forecast representation; no scoring or selection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from tempfile import TemporaryFile
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.pit.canonical import canonical_payload_text
from backend.app.pit.ecmwf_open_data_provider import (
    _GRID_QUANTUM,
    BASE_LOCATION_AUTHORITY_SHA256,
    ECMWFOpenDataForecastProvider,
    GridPoint,
    _as_utc,
    _find_index,
    _normalize_longitude,
    _parameter_rows,
    _read_bytes,
    _write_immutable,
)
from backend.app.pit.shadow_forecast import WeatherForecastProviderError

STEPS = tuple(range(3, 145, 3)) + tuple(range(150, 361, 6))
REQUIRED_FIELDS = tuple((s, p) for s in STEPS for p in ("2t", "10u", "10v")) + tuple(
    (s, p) for s in (168, 360) for p in ("tp", "ssrd")
)
FEATURE_NAMES = tuple(
    f"wx_run_{block}h_{name}"
    for block in ("0_168", "168_360")
    for name in (
        "t2m_step_weighted_mean_c",
        "tp_total_mm",
        "ssrd_total_j_m2",
        "wind_step_weighted_mean_m_s",
    )
)
S1_SHA = "f3a217090de596a6ee52af8b0d35783fe54193c8a23bf2f6de73220e04d9e601"
HOURLY_SHA = "37a63e783035127f3db524a2cc33aa79ccbcd0994d69be8bf3b3f4a9f42278cd"
HOURLY_DATASET_HASH = "69bf00d3ca72d662c3e4efdc09e022eef8f908a8aab3d6663a83058e80105819"
HOURLY_LAYER = "ERA5_LAND_HOURLY_NORMALIZED_V1"
HOURLY_COUNT = 4749696
SOURCE_MANIFEST_HASH = "2bd5f909945f0ba677d9818c9cb23a3eb80119cb9e03407707cbbe83880bddb1"
RAW_SET_HASH = "6df5a8e909447384a3b33414facf6e768d1fb31c52b89ebec59bec37e3f358d8"
POLICY: dict[str, Any] = {
    "feature_policy_id": "V0_14_RUNREL_168_360_WEATHER_R1",
    "feature_names": list(FEATURE_NAMES),
    "blocks": [[0, 168], [168, 360]],
    "native_steps": list(STEPS),
    "time_basis": "FORECAST_RUN_RELATIVE_UTC",
    "anchor": "PROVIDER_RUN_ISSUED_AT",
    "step_zero_included": False,
    "temperature_formula": "SUM(endpoint_C*step_duration_hours)/block_hours",
    "wind_formula": "SUM(sqrt(u*u+v*v)*step_duration_hours)/block_hours",
    "temperature_semantics": "NATIVE_STEP_DURATION_WEIGHTED_ENDPOINT_SAMPLE_MEAN",
    "wind_semantics": "NATIVE_STEP_DURATION_WEIGHTED_ENDPOINT_WIND_SPEED_MEAN",
    "tp_formula": ["tp168*1000", "(tp360-tp168)*1000"],
    "ssrd_formula": ["ssrd168", "ssrd360-ssrd168"],
    "units": ["degC", "mm", "J/m2", "m/s"] * 2,
    "historical_tp_ssrd_formula": "SUM_PROVIDER_DEACCUMULATED_HOURLY_INTERVALS_FULLY_INSIDE_BLOCK",
    "historical_layer": HOURLY_LAYER,
    "historical_artifact_sha256": HOURLY_SHA,
    "historical_dataset_hash": HOURLY_DATASET_HASH,
    "source_manifest_hash": SOURCE_MANIFEST_HASH,
    "raw_artifact_set_hash": RAW_SET_HASH,
    "s1_evidence_sha256": S1_SHA,
    "required_max_step": 360,
    "required_field_count": 256,
    "missing_policy": "FAIL_CLOSED",
    "decimal_precision": 50,
    "quantize": "0.000000000001",
    "rounding": "ROUND_HALF_EVEN",
    "round_once": True,
    "interpolation": False,
    "prorating": False,
    "carry_forward": False,
    "gdd": False,
    "tmin_tmax": False,
    "ssrd_mean_flux": False,
    "model_family": "RIDGE_LEAST_SQUARES",
    "alpha": "10.000000",
    "train_seasons": ["2023-2024", "2024-2025"],
    "historical_scoring": False,
    "target_2026_2027_actual_read": False,
}


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def validate_policy(policy: Mapping[str, Any]) -> None:
    require(dict(policy) == POLICY, "FROZEN_FEATURE_POLICY_MISMATCH")


def decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    require(result.is_finite(), "NONFINITE_WEATHER")
    return result


def text(value: Decimal) -> str:
    return format(value.quantize(Decimal(POLICY["quantize"]), rounding=ROUND_HALF_EVEN), "f")


def synthetic_anchor(origin: datetime) -> datetime:
    require(origin.tzinfo is not None, "ORIGIN_TIMEZONE_REQUIRED")
    utc = origin.astimezone(UTC)
    return utc.replace(hour=12 if utc.hour >= 12 else 0, minute=0, second=0, microsecond=0)


def aggregate_ifs(fields: Mapping[tuple[int, str], Mapping[str, Any]]) -> dict[str, str]:
    require(set(fields) == set(REQUIRED_FIELDS), "W1_FEATURE_SURFACE_INCOMPLETE_OR_MUTATED")
    with localcontext() as context:
        context.prec = 50
        values = {}
        for (step, parameter), row in fields.items():
            accum = parameter in {"tp", "ssrd"}
            require(
                row.get("units")
                == {"2t": "K", "tp": "m", "ssrd": "J m**-2"}.get(parameter, "m s**-1"),
                "WRONG_WEATHER_UNIT",
            )
            require(
                row.get("stepType") == ("accum" if accum else "instant")
                and row.get("startStep") == (0 if accum else step)
                and row.get("endStep") == step,
                "WRONG_WEATHER_TIME_SEMANTICS",
            )
            values[step, parameter] = decimal(row["value"])
        for parameter in ("tp", "ssrd"):
            require(
                values[360, parameter] >= values[168, parameter] >= 0,
                "CUMULATIVE_WEATHER_REGRESSION",
            )
        output = []
        for start, end in ((0, 168), (168, 360)):
            temp = wind = Decimal(0)
            previous = start
            for step in STEPS:
                if start < step <= end:
                    duration = Decimal(step - previous)
                    temp += (values[step, "2t"] - Decimal("273.15")) * duration
                    wind += (values[step, "10u"] ** 2 + values[step, "10v"] ** 2).sqrt() * duration
                    previous = step
            require(previous == end, "BLOCK_ENDPOINT_MISSING")
            output.extend(
                [
                    temp / Decimal(end - start),
                    (values[end, "tp"] - (values[start, "tp"] if start else 0)) * 1000,
                    values[end, "ssrd"] - (values[start, "ssrd"] if start else 0),
                    wind / Decimal(end - start),
                ]
            )
        return dict(zip(FEATURE_NAMES, map(text, output), strict=True))


def aggregate_proxy(hourly: Mapping[tuple[int, str], Decimal]) -> dict[str, str]:
    """Keys are relative valid/end hours. ERA5 Celsius and interval totals stay native."""
    needed = {(s, p) for s in STEPS for p in ("t2m", "u10", "v10")} | {
        (s, p) for s in range(1, 361) for p in ("tp", "ssrd")
    }
    require(set(hourly) == needed, "PROXY_SUPPORT_INCOMPLETE")
    with localcontext() as context:
        context.prec = 50
        values = {key: decimal(value) for key, value in hourly.items()}
        require(
            all(value >= 0 for (s, p), value in values.items() if p in {"tp", "ssrd"}),
            "NEGATIVE_INTERVAL_VALUE",
        )
        output = []
        for start, end in ((0, 168), (168, 360)):
            previous = start
            temp = wind = Decimal(0)
            for step in STEPS:
                if start < step <= end:
                    duration = Decimal(step - previous)
                    temp += values[step, "t2m"] * duration
                    wind += (values[step, "u10"] ** 2 + values[step, "v10"] ** 2).sqrt() * duration
                    previous = step
            output.extend(
                [
                    temp / Decimal(end - start),
                    sum((values[s, "tp"] for s in range(start + 1, end + 1)), Decimal(0)),
                    sum((values[s, "ssrd"] for s in range(start + 1, end + 1)), Decimal(0)),
                    wind / Decimal(end - start),
                ]
            )
        return dict(zip(FEATURE_NAMES, map(text, output), strict=True))


def verify_artifact(artifact: Mapping[str, Any]) -> None:
    require(
        digest({k: v for k, v in artifact.items() if k != "artifact_hash"})
        == artifact.get("artifact_hash"),
        "ARTIFACT_SELF_HASH_MISMATCH",
    )
    role = artifact.get("prospective_role")
    require(role in {"C0", "W1"}, "WRONG_ARTIFACT_ROLE")
    require(
        artifact.get("schema") == f"V0_14_{role}_RIDGE_ARTIFACT_V1"
        and artifact.get("model_id")
        == (
            "V0_14_C0_BASE_ONLY_PROSPECTIVE_COMPARATOR"
            if role == "C0"
            else "V0_14_W1_AS_ISSUED_WEATHER_PROSPECTIVE_CANDIDATE"
        )
        and artifact.get("alpha") == "10.000000"
        and artifact.get("solver") == "numpy.linalg.solve"
        and artifact.get("standardization") == "TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD"
        and artifact.get("zero_std_policy") == "SCALE_1"
        and artifact.get("intercept_unpenalized") is True
        and artifact.get("nonnegative_output_clip") is True
        and artifact.get("production_approved") is False
        and artifact.get("feature_policy_hash") == digest(POLICY),
        "ARTIFACT_CONTRACT_MISMATCH",
    )
    from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES

    expected = BASE_FEATURES + (FEATURE_NAMES if role == "W1" else ())
    require(artifact.get("feature_names") == list(expected), "ARTIFACT_FEATURE_SCHEMA_MISMATCH")
    for field in ("feature_means", "feature_scales", "coefficients"):
        require(len(artifact.get(field, [])) == len(expected), "ARTIFACT_DIMENSION_MISMATCH")
        for value in artifact[field]:
            decimal(value)
    require(all(decimal(v) > 0 for v in artifact["feature_scales"]), "INVALID_SCALER")
    decimal(artifact["intercept"])


def validate_public_evidence(value: Any) -> None:
    """Reject row-level/private payloads before public serialization."""
    forbidden = {
        "coordinates",
        "latitude",
        "longitude",
        "features",
        "fields_by_base",
        "training_row_keys",
        "training_labels",
        "coefficients",
        "feature_means",
        "feature_scales",
        "actual_daily_kg",
        "normalized_value",
    }
    if isinstance(value, Mapping):
        require(not forbidden.intersection(value), "PRIVATE_PUBLIC_DISCLOSURE")
        for item in value.values():
            validate_public_evidence(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_public_evidence(item)
    elif isinstance(value, str):
        require("/Users/" not in value and "/private/" not in value, "PRIVATE_PATH_DISCLOSURE")


def verify_pair(c0: Mapping[str, Any], w1: Mapping[str, Any]) -> None:
    for key in (
        "training_row_key_hash",
        "training_label_hash",
        "training_cohort_hash",
        "training_row_count",
        "alpha",
        "solver",
        "standardization",
        "zero_std_policy",
        "intercept_unpenalized",
        "nonnegative_output_clip",
    ):
        require(key in c0 and key in w1 and c0[key] == w1[key], "C0_W1_PARITY_MISMATCH")


def synthetic_request_check(artifact: Mapping[str, Any]) -> str:
    """Reload integrity check on a fixed non-label-bearing synthetic vector only."""
    verify_artifact(artifact)
    inputs = [float(i + 1) for i in range(len(artifact["feature_names"]))]
    result = float(artifact["intercept"]) + sum(
        float(coefficient) * ((value - float(mean)) / float(scale))
        for value, mean, scale, coefficient in zip(
            inputs,
            artifact["feature_means"],
            artifact["feature_scales"],
            artifact["coefficients"],
            strict=True,
        )
    )
    decimal(result)
    return format(max(0.0, result), ".12f")


class ECMWFDenseFeatureSurfaceProvider(ECMWFOpenDataForecastProvider):
    """Opt-in dense surface using the existing provider's raw/grid primitives."""

    def capture_feature_surface(self, *, issued_at: datetime) -> dict[str, Any]:
        """Explicit V0.14 dense path. The default snapshot capture is unchanged.

        Raw encoding and Base/grid identity are checked before any aggregation.
        No six-decimal snapshot conversion is applied to these native values.
        Acquisition provenance is persisted separately from scientific identity.
        """
        issued_at = _as_utc(issued_at)
        if (
            issued_at.hour not in {0, 12}
            or issued_at.minute
            or issued_at.second
            or issued_at.microsecond
            or issued_at > datetime.now(UTC)
        ):
            raise WeatherForecastProviderError("DENSE_RUN_IDENTITY_INVALID")
        run_id = self._run_id(issued_at)
        base_url = self._run_url(issued_at)
        root = self._artifact_path(run_id, "feature-surface")
        indexes = {}
        fields: dict[str, dict[tuple[int, str], dict[str, Any]]] = {
            base: {} for base in self.locations
        }
        raw_manifest: dict[str, Any] = {
            "schema": "V0_14_DENSE_RAW_V1",
            "run_id": run_id,
            "issued_at": issued_at.isoformat(),
            "location_authority_sha256": BASE_LOCATION_AUTHORITY_SHA256,
            "files": {},
        }
        grid_indices = None
        shape = None
        for step, parameter in REQUIRED_FIELDS:
            if step not in indexes:
                path = root / f"{step:03d}h.index"
                payload = self._cached_or_request(
                    path, f"{base_url}/{run_id}-{step}h-oper-fc.index"
                )
                raw_manifest["files"][path.name] = _write_immutable(path, payload)
                rows = _parameter_rows(payload)
                for row in rows:
                    if row.get("param") not in {"2t", "10u", "10v", "tp", "ssrd"}:
                        continue
                    expected = {
                        "class": "od",
                        "stream": "oper",
                        "type": "fc",
                        "date": run_id[:8],
                        "time": run_id[8:12],
                        "step": str(step),
                    }
                    if any(str(row.get(k)) != v for k, v in expected.items()):
                        raise WeatherForecastProviderError("DENSE_INDEX_IDENTITY_INVALID")
                indexes[step] = rows
            item = _find_index(indexes[step], step, parameter)
            if item is None:
                raise WeatherForecastProviderError("W1_FEATURE_SURFACE_INCOMPLETE")
            path = root / f"{step:03d}h-{parameter}.grib2"
            payload = self._cached_or_request(
                path,
                f"{base_url}/{run_id}-{step}h-oper-fc.grib2",
                byte_range=(item.offset, item.offset + item.length - 1),
            )
            raw_manifest["files"][path.name] = _write_immutable(path, payload)
            metadata = self._feature_surface_metadata(payload)
            accum = parameter in {"tp", "ssrd"}
            units = {"2t": "K", "tp": "m", "ssrd": "J m**-2"}.get(parameter, "m s**-1")
            validity = issued_at + timedelta(hours=step)
            expected_metadata = {
                "shortName": parameter,
                "units": units,
                "stepType": "accum" if accum else "instant",
                "startStep": 0 if accum else step,
                "endStep": step,
                "dataDate": int(issued_at.strftime("%Y%m%d")),
                "dataTime": issued_at.hour * 100,
                "validityDate": int(validity.strftime("%Y%m%d")),
                "validityTime": validity.hour * 100,
            }
            if any(metadata.get(k) != v for k, v in expected_metadata.items()):
                raise WeatherForecastProviderError("DENSE_GRIB_SEMANTICS_MISMATCH")
            decoded = self._decode_grib(payload)
            if grid_indices is None:
                grid_indices = self._grid_indices(decoded, self.locations)
                shape = decoded.ni, decoded.nj
            if shape != (decoded.ni, decoded.nj):
                raise WeatherForecastProviderError("DENSE_GRID_MISMATCH")
            for base, (index, point) in grid_indices.items():
                returned = GridPoint(
                    Decimal(str(float(decoded.latitudes[index]))).quantize(_GRID_QUANTUM),
                    _normalize_longitude(
                        Decimal(str(float(decoded.longitudes[index]))).quantize(_GRID_QUANTUM)
                    ),
                )
                if returned != point:
                    raise WeatherForecastProviderError("DENSE_GRID_MISMATCH")
                value = Decimal(str(float(decoded.values[index])))
                if not value.is_finite():
                    raise WeatherForecastProviderError("DENSE_NONFINITE_VALUE")
                fields[base][step, parameter] = {**metadata, "value": format(value, "f")}
        manifest_bytes = canonical_payload_text(raw_manifest).encode()
        manifest_hash = _write_immutable(root / "raw-manifest.json", manifest_bytes)
        receipt_path = root / "acquisition-receipt.json"
        if receipt_path.exists():
            receipt = json.loads(_read_bytes(receipt_path))
        else:
            fetched = datetime.now(UTC).isoformat()
            receipt = {
                "issued_at": issued_at.isoformat(),
                "fetched_at": fetched,
                "known_at": fetched,
                "manifest_sha256": manifest_hash,
            }
            _write_immutable(receipt_path, canonical_payload_text(receipt).encode())
        if receipt["manifest_sha256"] != manifest_hash or not issued_at <= datetime.fromisoformat(
            receipt["fetched_at"]
        ) <= datetime.fromisoformat(receipt["known_at"]) <= datetime.now(UTC):
            raise WeatherForecastProviderError("DENSE_ACQUISITION_PROVENANCE_INVALID")
        return {
            "run_id": run_id,
            "issued_at": issued_at.isoformat(),
            "fields_by_base": fields,
            "raw_manifest_sha256": manifest_hash,
            "raw_manifest": raw_manifest,
            "acquisition_receipt": receipt,
        }

    @staticmethod
    def _feature_surface_metadata(payload: bytes) -> dict[str, Any]:
        import eccodes  # type: ignore[import-untyped]

        with TemporaryFile() as stream:
            stream.write(payload)
            stream.seek(0)
            handle = eccodes.codes_grib_new_from_file(stream)
            if handle is None:
                raise WeatherForecastProviderError("DENSE_GRIB_INVALID")
            try:
                return {
                    key: eccodes.codes_get(handle, key)
                    for key in (
                        "shortName",
                        "paramId",
                        "units",
                        "stepType",
                        "startStep",
                        "endStep",
                        "dataDate",
                        "dataTime",
                        "validityDate",
                        "validityTime",
                    )
                }
            finally:
                eccodes.codes_release(handle)
