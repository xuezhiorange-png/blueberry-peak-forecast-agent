"""Runtime calendar/observation bridge; frozen V1 features and Ridge arithmetic."""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.area_yield.formal_multi_season_validation import BusinessBoundary
from backend.app.area_yield.v015_harvest_state import FEATURES, valid_day
from backend.app.area_yield.weather_aware_backtest import (
    BASE_FEATURES,
    RollingTargetRow,
    _base_feature_values,
)
from backend.app.rolling_forecast.harvest_state import window_values
from backend.app.rolling_forecast.schemas import Area, Calendar, Mode, Observation
from backend.research.v019_origin_evaluation import curve, peaks
from backend.research.v019_origin_models import PreparedPair
from backend.research.v019_synthetic_validation import digest


def harvest_features(
    calendar: Calendar,
    area: Area,
    origin: date,
    cutoff: datetime,
    observations: list[Observation],
    mode: Mode,
) -> dict[str, Any]:
    if mode not in {"RESEARCH_SHADOW", "RETROSPECTIVE_DATE_BOUND"}:
        raise ValueError("UNSUPPORTED_EXECUTION_MODE")
    if cutoff.tzinfo is None or cutoff.astimezone(ZoneInfo(calendar.timezone)).date() != origin:
        raise ValueError("ORIGIN_CUTOFF_MISMATCH")
    if (
        area.season != calendar.season
        or not calendar.start <= origin
        or origin + timedelta(days=15) > calendar.end
        or area.effective_from > origin + timedelta(days=1)
        or area.effective_until < origin + timedelta(days=15)
    ):
        raise ValueError("AREA_OR_CALENDAR_MISMATCH")
    if mode == "RESEARCH_SHADOW" and any(
        t is None or t > cutoff for t in (area.known_at, calendar.known_at)
    ):
        raise ValueError("AREA_OR_CALENDAR_TIME_UNPROVEN")
    prior, lineage, reasons, bases = {}, [], set(), set()
    for row in observations:
        if row.base_id != area.base_id or row.season != calendar.season:
            raise ValueError("OBSERVATION_SCOPE_MISMATCH")
        if not calendar.start <= row.business_date < origin:
            continue
        if row.business_date in prior:
            raise ValueError("DUPLICATE_BUSINESS_DAY")
        bases.add(row.quantity_basis)
        trusted = (
            row.available_at_authority == "TRUSTED_SOURCE_TIMESTAMP"
            and row.source_recorded_at is not None
            and row.source_recorded_at <= cutoff
            and row.server_ingested_at is not None
            and row.server_ingested_at <= cutoff
        )
        late = any(
            t is not None and t > cutoff for t in (row.source_recorded_at, row.server_ingested_at)
        )
        value, reason = valid_day(
            {
                "record_state": "REAL_ZERO"
                if row.record_state == "CONFIRMED_ZERO"
                else row.record_state,
                "quantity_kg": row.quantity_kg,
                "logical_record_id": row.source_identity,
                "source_hashes": [row.source_hash],
                "conflict_status": ["CONFLICT"] if row.record_state == "CONFLICTING" else ["NONE"],
            }
        )
        if (
            late
            or (mode == "RESEARCH_SHADOW" and not trusted)
            or row.observation_completeness != "COMPLETE"
        ):
            value, reason = None, "OBSERVATION_TIME_OR_COMPLETENESS_UNPROVEN"
        prior[row.business_date] = value
        if reason:
            reasons.add(reason)
        lineage.append(row.model_dump(mode="json"))
    if len(bases) > 1:
        raise ValueError("QUANTITY_BASIS_CONFLICT")
    values, audit, missing = window_values(prior, calendar.start, origin)
    reasons.update(missing)
    if any(v for v in audit.values()):
        reasons.add("INCOMPLETE_PRIOR_OBSERVATIONS")
    body = {
        "values": values,
        "audit": audit,
        "reasons": sorted(reasons),
        "complete": not any(audit.values()),
        "quantity_basis": next(iter(bases), None),
        "consumed_prior_rows": sorted(lineage, key=lambda r: r["business_date"]),
        "origin_date": str(origin),
        "origin_cutoff_at": cutoff.isoformat(),
        "visibility": "TRUSTED_AS_OF_CUTOFF"
        if mode == "RESEARCH_SHADOW"
        else "RETROSPECTIVE_DATE_BOUND",
        "strict_pit": False,
        "unit": "kg",
    }
    return {**body, "feature_hash": digest(body)}


def summary(daily: list[dict[str, str]]) -> dict[str, Any]:
    p = peaks(curve(daily))
    return {
        "forecast_total_kg": format(sum((Decimal(r["kg"]) for r in daily), Decimal(0)), ".6f"),
        "single_day_peak_date": p["single_day"]["date"],
        "single_day_peak_kg": p["single_day"]["kg"],
        "rolling_7day_peak_start": p["rolling7"]["start"],
        "rolling_7day_peak_end": p["rolling7"]["end"],
        "rolling_7day_peak_cumulative_kg": p["rolling7"]["kg"],
        "scope": "THIS_FORECAST_WINDOW_ONLY",
    }


def forecast(
    calendar: Calendar,
    area: Area,
    origin: date,
    cutoff: datetime,
    observations: list[Observation],
    pair: PreparedPair,
    mode: Mode,
) -> dict[str, Any]:
    feature = harvest_features(calendar, area, origin, cutoff, observations, mode)
    if pair.training_last_date >= str(origin + timedelta(days=1)):
        raise ValueError("MODEL_TRAINING_CUTOFF_MISMATCH")
    boundary = BusinessBoundary(
        calendar.season,
        calendar.start,
        calendar.end,
        calendar.reference,
        calendar.source_hash,
        "EXPLICIT_RUNTIME_AUTHORITY",
    )
    models = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for model, artifact in pair.artifacts:
            daily = []
            if model == "M0" or feature["complete"]:
                for i in range(1, 16):
                    day = origin + timedelta(days=i)
                    base = _base_feature_values(
                        reference_area_mu=area.area_mu, target_date=day, boundary=boundary
                    )
                    row = RollingTargetRow(
                        key=digest([area.base_id, calendar.season, str(origin), i]),
                        base_id=area.base_id,
                        base_name="",
                        season=calendar.season,
                        forecast_origin=cutoff.isoformat(),
                        target_date=day,
                        lead_day=i,
                        reference_area_mu=area.area_mu,
                        feature_values=tuple((k, base[k]) for k in BASE_FEATURES)
                        + (
                            tuple((k, feature["values"][k]) for k in FEATURES)
                            if model == "M1"
                            else ()
                        ),
                        weather_feature_hash="",
                        weather_source="NONE",
                        weather_lane="NONE",
                        feature_policy_version="HARVEST_STATE_V1_RUNTIME",
                    )
                    daily.append(
                        {
                            "date": str(day),
                            "kg": format(
                                artifact.predict(row).quantize(
                                    Decimal(".000001"), rounding=ROUND_HALF_EVEN
                                ),
                                "f",
                            ),
                        }
                    )
            models[model] = {
                "status": "COMPUTED" if daily else "NOT_COMPUTABLE",
                "model_id": artifact.model_id,
                "model_artifact_hash": artifact.artifact_hash,
                "model_training_target_quantity_basis": getattr(
                    pair, "model_training_target_quantity_basis", None
                ),
                "forecast_target_quantity_basis": getattr(
                    pair, "model_training_target_quantity_basis", None
                ),
                "model_provenance": getattr(pair, "model_provenance", None),
                "daily_forecast_kg": daily,
                "H7": summary(daily[:7]) if daily else None,
                "H15": summary(daily) if daily else None,
                "blocker_reason": None if daily else feature["reasons"],
            }
    body = {
        "models": models,
        "feature_snapshot": feature,
        "feature_observation_quantity_basis": feature["quantity_basis"],
        "evaluation_label_quantity_basis": None,
        "area_authority": area.model_dump(mode="json"),
        "calendar_authority": calendar.model_dump(mode="json"),
        "fit_hash": pair.fit_sha256,
        "execution_mode": mode,
        "strict_pit": False,
        "production_model": False,
        "point_is_p50": False,
        "uncertainty_status": "NOT_AVAILABLE",
    }
    return {**body, "result_hash": digest(body)}
