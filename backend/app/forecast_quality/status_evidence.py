"""Pure construction helpers for frozen Quality status evidence.

This module deliberately contains no persistence, transport, actor, clock, or
metric-calculation concerns.  It records the S3 contract's inability to prove
or compute a result without deriving a replacement value.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Literal, cast

from .canonical import canonical_json_bytes
from .schemas import QualityStatusEvidenceCell, QualityStatusEvidenceScope, S3BindingRow

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HORIZONS = (7, 14, 21)
_QUANTILES = ("P50", "P80", "P90")


def _hash(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _require_sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


def _require_scope(scope: QualityStatusEvidenceScope) -> None:
    if not isinstance(scope, QualityStatusEvidenceScope):
        raise TypeError("status evidence scope must be typed")
    if scope.forecast_horizon_days not in _HORIZONS:
        raise ValueError("status evidence horizon is unsupported")
    for name in (
        "season_business_key",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "model_identity",
    ):
        value = getattr(scope, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"status evidence scope field is empty: {name}")


def _require_decimal_or_none(value: Decimal | None, field: str) -> None:
    if value is not None and (
        isinstance(value, float) or not isinstance(value, Decimal) or not value.is_finite()
    ):
        raise ValueError(f"{field} must be a finite Decimal or null")


def _scope_from_rows(rows: Sequence[S3BindingRow], horizon: int) -> QualityStatusEvidenceScope:
    if not rows:
        raise ValueError("status evidence requires persisted S2 rows")
    matching = [row for row in rows if row.forecast_horizon_days == horizon]
    source = matching[0] if matching else rows[0]
    scope = QualityStatusEvidenceScope(
        forecast_horizon_days=horizon,  # type: ignore[arg-type]
        season_business_key=source.season_business_key,
        farm_business_key=source.farm_business_key,
        subfarm_business_key=source.subfarm_business_key,
        variety_business_key=source.variety_business_key,
        model_identity=source.model_identity,
    )
    _require_scope(scope)
    for row in rows:
        if (
            row.season_business_key != scope.season_business_key
            or row.farm_business_key != scope.farm_business_key
            or row.subfarm_business_key != scope.subfarm_business_key
            or row.variety_business_key != scope.variety_business_key
            or row.model_identity != scope.model_identity
        ):
            raise ValueError("status evidence rows contain multiple business scopes")
    return scope


def _validate_rows(rows: Sequence[S3BindingRow]) -> None:
    for row in rows:
        for field in ("forecast_value_kg", "actual_value_kg"):
            value = getattr(row, field)
            if value is not None and (
                isinstance(value, float) or not isinstance(value, Decimal) or not value.is_finite()
            ):
                raise ValueError(f"{field} must be a finite Decimal or null")
        cutoff = row.forecast_cutoff_at
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("forecast_cutoff_at must be timezone-aware")


def _cell(
    *,
    metric_name: Literal[
        "p80_upper_coverage",
        "p90_upper_coverage",
        "single_day_peak",
        "sustained_seven_day_peak",
        "prediction_interval",
    ],
    metric_status: Literal["NOT_VERIFIED", "NOT_COMPUTABLE"],
    reason_code: str,
    scope: QualityStatusEvidenceScope,
    quantile: Literal["P50", "P80", "P90"],
    candidate_row_count: int | None,
    source_s2_run_identity: str,
    source_s2_manifest_identity: str,
    source_s2_binding_row_set_hash: str,
) -> QualityStatusEvidenceCell:
    _require_scope(scope)
    if quantile not in _QUANTILES:
        raise ValueError("status evidence quantile is unsupported")
    if candidate_row_count is not None and candidate_row_count < 0:
        raise ValueError("candidate row count cannot be negative")
    for field, value in (
        ("source_s2_run_identity", source_s2_run_identity),
        ("source_s2_manifest_identity", source_s2_manifest_identity),
        ("source_s2_binding_row_set_hash", source_s2_binding_row_set_hash),
    ):
        _require_sha256(value, field)
    breakdown_identity = {
        **scope.as_payload(),
        "forecast_quantile": quantile,
    }
    payload: dict[str, object] = {
        "schema_version": "v0.2-s3-quality-frozen-status-evidence-v1",
        "metric_name": metric_name,
        "metric_status": metric_status,
        "reason_code": reason_code,
        "forecast_horizon_days": scope.forecast_horizon_days,
        "forecast_quantile": quantile,
        "breakdown_identity": breakdown_identity,
        "metric_value": None,
        "numerator": None,
        "denominator": None,
        "covered_count_or_null": None,
        "candidate_row_count_or_null": candidate_row_count,
        "business_date_or_null": None,
        "window_start_date_or_null": None,
        "window_end_date_or_null": None,
        "lower_bound_available_or_null": (False if metric_name == "prediction_interval" else None),
        "lower_bound_value_or_null": None,
        "upper_bound_value_or_null": None,
        "source_s2_run_identity": source_s2_run_identity,
        "source_s2_manifest_identity": source_s2_manifest_identity,
        "source_s2_binding_row_set_hash": source_s2_binding_row_set_hash,
    }
    key_payload = {
        "schema_version": payload["schema_version"],
        "metric_name": metric_name,
        "forecast_horizon_days": scope.forecast_horizon_days,
        "forecast_quantile": quantile,
        "breakdown_identity": breakdown_identity,
        "source_s2_binding_row_set_hash": source_s2_binding_row_set_hash,
    }
    metric_result_key_hash = _hash(key_payload)
    canonical_hash = _hash(payload)
    return QualityStatusEvidenceCell(
        metric_name=metric_name,
        metric_status=metric_status,
        reason_code=reason_code,
        scope=scope,
        forecast_quantile=quantile,
        metric_value=None,
        numerator=None,
        denominator=None,
        covered_count_or_null=None,
        candidate_row_count_or_null=candidate_row_count,
        business_date_or_null=None,
        window_start_date_or_null=None,
        window_end_date_or_null=None,
        lower_bound_available_or_null=(False if metric_name == "prediction_interval" else None),
        lower_bound_value_or_null=None,
        upper_bound_value_or_null=None,
        source_s2_run_identity=source_s2_run_identity,
        source_s2_manifest_identity=source_s2_manifest_identity,
        source_s2_binding_row_set_hash=source_s2_binding_row_set_hash,
        metric_result_key_hash=metric_result_key_hash,
        canonical_payload=payload,
        canonical_hash=canonical_hash,
    )


def _validate_cell(cell: QualityStatusEvidenceCell) -> None:
    _require_scope(cell.scope)
    for field in (
        "source_s2_run_identity",
        "source_s2_manifest_identity",
        "source_s2_binding_row_set_hash",
    ):
        _require_sha256(getattr(cell, field), field)
    _require_decimal_or_none(cell.metric_value, "metric_value")
    _require_decimal_or_none(cell.numerator, "numerator")
    _require_decimal_or_none(cell.denominator, "denominator")
    if cell.metric_value is not None or cell.numerator is not None or cell.denominator is not None:
        raise ValueError("frozen status evidence numeric values must be null")
    if cell.metric_name in {"p80_upper_coverage", "p90_upper_coverage"}:
        if cell.metric_status != "NOT_VERIFIED":
            raise ValueError("coverage status evidence must be NOT_VERIFIED")
        if cell.reason_code != "QUANTILE_SEMANTICS_NOT_VERIFIED":
            raise ValueError("coverage status evidence reason drift")
        expected_quantile = cell.metric_name[:3].upper()
        if cell.forecast_quantile != expected_quantile:
            raise ValueError("coverage quantile projection drift")
        if cell.covered_count_or_null is not None:
            raise ValueError("unverified coverage cannot expose covered count")
    elif cell.metric_name in {"single_day_peak", "sustained_seven_day_peak"}:
        if cell.metric_status != "NOT_COMPUTABLE":
            raise ValueError("peak status evidence must be NOT_COMPUTABLE")
        if cell.reason_code != "COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING":
            raise ValueError("peak status evidence reason drift")
        if any(
            value is not None
            for value in (
                cell.business_date_or_null,
                cell.window_start_date_or_null,
                cell.window_end_date_or_null,
            )
        ):
            raise ValueError("not-computable peak dates must be null")
    elif cell.metric_name == "prediction_interval":
        if cell.metric_status != "NOT_COMPUTABLE":
            raise ValueError("interval status evidence must be NOT_COMPUTABLE")
        if cell.reason_code != "PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE":
            raise ValueError("interval status evidence reason drift")
        if cell.lower_bound_available_or_null is not False or any(
            value is not None
            for value in (
                cell.lower_bound_value_or_null,
                cell.upper_bound_value_or_null,
            )
        ):
            raise ValueError("unavailable interval bounds must be null")
    else:
        raise ValueError("unknown frozen status metric")
    if _hash(cell.canonical_payload) != cell.canonical_hash:
        raise ValueError("status evidence canonical hash drift")
    if cell.canonical_payload.get("breakdown_identity") != {
        **cell.scope.as_payload(),
        "forecast_quantile": cell.forecast_quantile,
    }:
        raise ValueError("status evidence breakdown identity drift")
    if (
        _hash(
            {
                "schema_version": cell.canonical_payload["schema_version"],
                "metric_name": cell.metric_name,
                "forecast_horizon_days": cell.scope.forecast_horizon_days,
                "forecast_quantile": cell.forecast_quantile,
                "breakdown_identity": cell.canonical_payload["breakdown_identity"],
                "source_s2_binding_row_set_hash": cell.source_s2_binding_row_set_hash,
            }
        )
        != cell.metric_result_key_hash
    ):
        raise ValueError("status evidence key hash drift")


def build_frozen_quality_status_evidence(
    *,
    requested_horizons_days: Sequence[int],
    rows: Sequence[S3BindingRow],
    source_s2_run_identity: str,
    source_s2_manifest_identity: str,
    source_s2_binding_row_set_hash: str,
) -> tuple[QualityStatusEvidenceCell, ...]:
    """Build the deterministic 30-cell frozen status evidence set."""

    if tuple(requested_horizons_days) != _HORIZONS:
        raise ValueError("status evidence horizons must be exactly (7, 14, 21)")
    if not rows:
        raise ValueError("status evidence requires persisted S2 rows")
    _validate_rows(rows)
    result: list[QualityStatusEvidenceCell] = []
    for horizon in _HORIZONS:
        scope = _scope_from_rows(rows, horizon)
        for quantile, metric_name in (("P80", "p80_upper_coverage"), ("P90", "p90_upper_coverage")):
            result.append(
                _cell(
                    metric_name=cast(
                        Literal["p80_upper_coverage", "p90_upper_coverage"], metric_name
                    ),
                    metric_status="NOT_VERIFIED",
                    reason_code="QUANTILE_SEMANTICS_NOT_VERIFIED",
                    scope=scope,
                    quantile=quantile,  # type: ignore[arg-type]
                    candidate_row_count=sum(
                        row.forecast_horizon_days == horizon and row.forecast_quantile == quantile
                        for row in rows
                    ),
                    source_s2_run_identity=source_s2_run_identity,
                    source_s2_manifest_identity=source_s2_manifest_identity,
                    source_s2_binding_row_set_hash=source_s2_binding_row_set_hash,
                )
            )
        for metric_name in ("single_day_peak", "sustained_seven_day_peak"):
            for quantile in _QUANTILES:
                result.append(
                    _cell(
                        metric_name=cast(
                            Literal[
                                "p80_upper_coverage",
                                "p90_upper_coverage",
                                "single_day_peak",
                                "sustained_seven_day_peak",
                                "prediction_interval",
                            ],
                            metric_name,
                        ),
                        metric_status="NOT_COMPUTABLE",
                        reason_code="COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING",
                        scope=scope,
                        quantile=quantile,  # type: ignore[arg-type]
                        candidate_row_count=None,
                        source_s2_run_identity=source_s2_run_identity,
                        source_s2_manifest_identity=source_s2_manifest_identity,
                        source_s2_binding_row_set_hash=source_s2_binding_row_set_hash,
                    )
                )
        for quantile in ("P80", "P90"):
            result.append(
                _cell(
                    metric_name="prediction_interval",
                    metric_status="NOT_COMPUTABLE",
                    reason_code="PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE",
                    scope=scope,
                    quantile=quantile,  # type: ignore[arg-type]
                    candidate_row_count=None,
                    source_s2_run_identity=source_s2_run_identity,
                    source_s2_manifest_identity=source_s2_manifest_identity,
                    source_s2_binding_row_set_hash=source_s2_binding_row_set_hash,
                )
            )
    if len(result) != 30:
        raise ValueError("frozen status evidence must contain exactly 30 records")
    for cell in result:
        _validate_cell(cell)
    return tuple(result)


__all__ = [
    "build_frozen_quality_status_evidence",
]
