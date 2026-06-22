from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.master_data import Farm, Season
from backend.app.models.planning import ParameterLibraryVersion, ParameterObservation
from backend.app.planning.config import ParameterInferenceConfig
from backend.app.planning.hashing import input_hash as build_input_hash
from backend.app.planning.hashing import source_signature
from backend.app.planning.inference import (
    eligible_as_of_date,
    infer_parameter,
    merge_duplicate_varieties,
)
from backend.app.planning.location import resolve_location_input, resolved_location_payload
from backend.app.planning.repository import (
    create_running_run,
    create_task,
    find_existing_run,
    get_active_library_version,
    get_library_version_by_code,
    get_library_version_by_id,
    get_run_by_task,
    get_task,
    get_task_by_hash,
    get_variety_by_lookup,
    load_result_rows,
    mark_run_completed,
    mark_run_failed,
    mark_task_status,
    replace_results,
)
from backend.app.planning.schemas import (
    CandidateObservation,
    ParameterInferenceExecutionResult,
    ParameterInferenceValue,
)

PARAMETER_UNITS = {
    "yield_kg_per_mu": "kg_per_mu",
    "marketable_rate": "ratio",
    "first_harvest_offset_days": "days",
    "maturity_peak_offset_days": "days",
    "maturity_width_days": "days",
    "maturity_skewness": "scalar",
    "harvest_realization_rate": "ratio",
}


def _sanitize_error_message(message: str) -> str:
    return " ".join(str(message).replace("\n", " ").replace("\r", " ").split())[:500]


async def _normalize_payload(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    location = payload.get("location")
    if not isinstance(location, dict):
        raise ValueError("location must be an object")

    raw_varieties = payload.get("varieties")
    if not isinstance(raw_varieties, list) or not raw_varieties:
        raise ValueError("varieties must be a non-empty list")

    normalized_varieties: list[dict[str, Any]] = []
    for item in raw_varieties:
        if not isinstance(item, dict):
            raise ValueError("varieties entries must be objects")
        variety = await get_variety_by_lookup(
            session,
            variety_id=int(item["variety_id"]) if item.get("variety_id") is not None else None,
            variety_code=(
                str(item["variety_code"])
                if item.get("variety_code") is not None
                else None
            ),
            variety_name=(
                str(item["variety_name"])
                if item.get("variety_name") is not None
                else None
            ),
        )
        if variety is None:
            raise ValueError("unknown variety")
        normalized_varieties.append(
            {
                "variety_id": variety.id,
                "variety_code": variety.code,
                "variety_name": variety.name,
                "planted_area_mu": Decimal(str(item["planted_area_mu"])),
            }
        )

    deduped = merge_duplicate_varieties(
        [
            {
                "variety_id": item["variety_id"],
                "planted_area_mu": item["planted_area_mu"],
            }
            for item in normalized_varieties
        ]
    )
    area_by_variety_id = {
        int(item["variety_id"]): Decimal(str(item["planted_area_mu"]))
        for item in deduped
    }
    normalized_input = {
        "location": location,
        "varieties": [
            {
                "variety_id": item["variety_id"],
                "variety_code": item["variety_code"],
                "variety_name": item["variety_name"],
                "planted_area_mu": area_by_variety_id[int(item["variety_id"])],
            }
            for item in normalized_varieties
        ],
    }
    return normalized_input, cast(list[dict[str, Any]], normalized_input["varieties"])


async def _select_library_version(
    session: AsyncSession,
    *,
    version_code: str | None,
) -> ParameterLibraryVersion:
    version = (
        await get_library_version_by_code(session, version_code=version_code)
        if version_code is not None
        else await get_active_library_version(session)
    )
    if version is None:
        raise ValueError("parameter library version not found")
    return version


async def _load_candidates(
    session: AsyncSession,
    *,
    library_version_id: int,
    variety_id: int,
    as_of_date: date,
    resolved_location: dict[str, Any],
) -> list[CandidateObservation]:
    farm_lookup = {
        row.id: row.name
        for row in (await session.scalars(select(Farm).order_by(Farm.id.asc()))).all()
    }
    season_lookup = {
        row.id: row
        for row in (await session.scalars(select(Season).order_by(Season.id.asc()))).all()
    }
    rows = (
        await session.scalars(
            select(ParameterObservation).where(
                ParameterObservation.library_version_id == library_version_id,
                ParameterObservation.variety_id == variety_id,
                ParameterObservation.valid_from <= as_of_date,
                (
                    ParameterObservation.valid_to.is_(None)
                    | (ParameterObservation.valid_to >= as_of_date)
                ),
            )
        )
    ).all()

    resolved_farm_name = cast(str | None, resolved_location.get("farm_name"))
    resolved_township = cast(str | None, resolved_location.get("township"))
    resolved_county = cast(str | None, resolved_location.get("county"))
    resolved_zone_id = cast(int | None, resolved_location.get("climate_zone_id"))
    latitude_value = resolved_location.get("latitude")
    longitude_value = resolved_location.get("longitude")
    if latitude_value is None or longitude_value is None:
        return []
    latitude = Decimal(str(latitude_value))
    longitude = Decimal(str(longitude_value))

    candidates: list[CandidateObservation] = []
    for row in rows:
        farm_name = farm_lookup.get(row.farm_id) if row.farm_id is not None else None
        season = season_lookup.get(row.season_id) if row.season_id is not None else None
        source_level = "literature_variety_prior"
        if resolved_farm_name and farm_name and resolved_farm_name == farm_name:
            source_level = "same_farm_variety"
        elif (
            resolved_township is not None
            and row.township is not None
            and resolved_township == row.township
        ):
            source_level = "same_township_altitude_variety"
        elif (
            resolved_county is not None
            and row.county is not None
            and resolved_county == row.county
            and resolved_zone_id is not None
            and row.climate_zone_id == resolved_zone_id
        ):
            source_level = "same_county_climate_zone_variety"
        elif (
            resolved_location.get("province") is not None
            and row.province == resolved_location.get("province")
        ):
            source_level = "same_province_variety"

        candidate = CandidateObservation(
            observation_id=row.id,
            parameter_type=row.parameter_type,
            variety_id=row.variety_id,
            scalar_value=row.scalar_value,
            sample_weight=row.sample_weight,
            source_level=source_level,
            farm_id=row.farm_id,
            subfarm_id=row.subfarm_id,
            location_reference_id=row.location_reference_id,
            climate_zone_id=row.climate_zone_id,
            province=row.province,
            prefecture=row.prefecture,
            county=row.county,
            township=row.township,
            farm_name=farm_name,
            altitude_m=row.altitude_m,
            latitude=latitude,
            longitude=longitude,
            season_id=row.season_id,
            season_code=season.code if season is not None else None,
            season_end_date=season.end_date if season is not None else None,
            historical_mape=row.historical_mape,
            date_mae_days=row.date_mae_days,
            p90_coverage=row.p90_coverage,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            available_at=row.available_at,
            source_version=row.source_version,
        )
        if eligible_as_of_date(candidate, as_of_date=as_of_date):
            candidates.append(candidate)
    return candidates


def _parameter_row(
    *,
    variety_id: int,
    parameter_type: str,
    inferred: ParameterInferenceValue,
) -> dict[str, Any]:
    return {
        "variety_id": variety_id,
        "parameter_type": parameter_type,
        "status": inferred.status,
        "p50_value": inferred.p50_value,
        "p80_lower": inferred.p80_lower,
        "p80_upper": inferred.p80_upper,
        "unit": PARAMETER_UNITS[parameter_type],
        "source_level": inferred.source_level,
        "confidence_level": inferred.confidence_level,
        "confidence_score": inferred.confidence_score,
        "sample_count": inferred.sample_count,
        "season_count": inferred.season_count,
        "farm_count": inferred.farm_count,
        "source_observation_ids": list(inferred.source_observation_ids),
        "source_metadata": {
            "source_level": inferred.source_level,
            "missing_evidence": list(inferred.missing_evidence),
            "fallback_below_minimum": inferred.fallback_below_minimum,
        },
        "uncertainty_metadata": {
            "uncertainty_method": "deterministic_quantile_combination",
            "fallback_below_minimum": inferred.fallback_below_minimum,
        },
    }


def _effective_volume_summary(
    planted_area_mu: Decimal,
    yield_row: dict[str, Any],
    rate_row: dict[str, Any],
) -> dict[str, Any]:
    if yield_row["status"] != "available" or rate_row["status"] != "available":
        return {"status": "unavailable"}
    p50_value = cast(Decimal, yield_row["p50_value"]) * cast(
        Decimal, rate_row["p50_value"]
    )
    lower = cast(Decimal, yield_row["p80_lower"]) * cast(Decimal, rate_row["p80_lower"])
    upper = cast(Decimal, yield_row["p80_upper"]) * cast(Decimal, rate_row["p80_upper"])
    return {
        "status": "available",
        "uncertainty_method": "deterministic_quantile_combination",
        "p50_value": planted_area_mu * p50_value,
        "p80_lower": planted_area_mu * lower,
        "p80_upper": planted_area_mu * upper,
    }


def _variety_payload(
    *,
    variety: dict[str, Any],
    inferred_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    planted_area_mu = cast(Decimal, variety["planted_area_mu"])
    return {
        "variety_id": variety["variety_id"],
        "variety_code": variety["variety_code"],
        "variety_name": variety["variety_name"],
        "planted_area_mu": planted_area_mu,
        "yield_kg_per_mu": inferred_rows["yield_kg_per_mu"],
        "marketable_rate": inferred_rows["marketable_rate"],
        "estimated_effective_volume_kg": _effective_volume_summary(
            planted_area_mu,
            inferred_rows["yield_kg_per_mu"],
            inferred_rows["marketable_rate"],
        ),
        "first_harvest_offset_days": inferred_rows["first_harvest_offset_days"],
        "maturity_peak_offset_days": inferred_rows["maturity_peak_offset_days"],
        "maturity_width_days": inferred_rows["maturity_width_days"],
        "maturity_skewness": inferred_rows["maturity_skewness"],
        "harvest_realization_rate": inferred_rows["harvest_realization_rate"],
        "source": {
            "yield": inferred_rows["yield_kg_per_mu"].get("source_level"),
            "marketable_rate": inferred_rows["marketable_rate"].get("source_level"),
        },
        "confidence": {
            "yield": inferred_rows["yield_kg_per_mu"].get("confidence_level"),
            "marketable_rate": inferred_rows["marketable_rate"].get("confidence_level"),
        },
    }


def _result_payload(result: ParameterInferenceExecutionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "task_id": result.task_id,
        "run_id": result.run_id,
        "input_hash": result.input_hash,
        "as_of_date": result.as_of_date,
        "resolver_version": result.resolver_version,
        "library_version": result.library_version,
        "config_hash": result.config_hash,
        "source_signature": result.source_signature,
        "resolved_location": result.resolved_location,
        "similar_historical_samples": result.similar_historical_samples,
        "variety_parameters": result.variety_parameters,
        "warnings": list(result.warnings),
        "missing_data": list(result.missing_data),
        "reproducibility_snapshot": result.reproducibility_snapshot,
        "error_message": result.error_message,
    }


def _execution_result(
    *,
    status: str,
    task_id: int | None,
    run_id: int | None,
    input_hash: str,
    as_of_date: date,
    config: ParameterInferenceConfig,
    library_version: str | None,
    source_signature_value: str,
    resolved_location_value: dict[str, Any],
    similar_historical_samples: list[dict[str, Any]],
    variety_parameters: list[dict[str, Any]],
    warnings: tuple[str, ...],
    missing_data: tuple[str, ...],
    reproducibility_snapshot: dict[str, Any],
    error_message: str | None = None,
) -> ParameterInferenceExecutionResult:
    return ParameterInferenceExecutionResult(
        status=status,  # type: ignore[arg-type]
        task_id=task_id,
        run_id=run_id,
        input_hash=input_hash,
        as_of_date=as_of_date,
        resolver_version=config.rules.resolver_version,
        library_version=library_version,
        config_hash=config.config_hash,
        source_signature=source_signature_value,
        resolved_location=resolved_location_value,
        similar_historical_samples=similar_historical_samples,
        variety_parameters=variety_parameters,
        warnings=warnings,
        missing_data=missing_data,
        reproducibility_snapshot=reproducibility_snapshot,
        error_message=error_message,
    )


async def _rehydrate_existing(
    session: AsyncSession,
    *,
    task_id: int,
    run_id: int,
    config: ParameterInferenceConfig,
    normalized_input: dict[str, Any],
    library_version: str | None,
    source_signature_value: str,
    resolved_location_value: dict[str, Any],
) -> ParameterInferenceExecutionResult:
    rows = await load_result_rows(session, run_id=run_id)
    rows_by_variety: dict[int, dict[str, dict[str, Any]]] = {}
    similar_historical_samples: list[dict[str, Any]] = []
    for row in rows:
        row_payload = {
            "status": row.status,
            "p50_value": row.p50_value,
            "p80_lower": row.p80_lower,
            "p80_upper": row.p80_upper,
            "unit": row.unit,
            "source_level": row.source_level,
            "confidence_level": row.confidence_level,
            "confidence_score": row.confidence_score,
            "sample_count": row.sample_count,
            "season_count": row.season_count,
            "farm_count": row.farm_count,
            "source_observation_ids": list(row.source_observation_ids),
            "source_metadata": row.source_metadata,
            "uncertainty_metadata": row.uncertainty_metadata,
        }
        rows_by_variety.setdefault(row.variety_id, {})[row.parameter_type] = row_payload
        if row.source_observation_ids:
            similar_historical_samples.append(
                {
                    "variety_id": row.variety_id,
                    "parameter_type": row.parameter_type,
                    "observation_ids": list(row.source_observation_ids),
                }
            )
    variety_parameters = [
        _variety_payload(variety=item, inferred_rows=rows_by_variety[int(item["variety_id"])])
        for item in cast(list[dict[str, Any]], normalized_input["varieties"])
    ]
    return _execution_result(
        status="skipped",
        task_id=task_id,
        run_id=run_id,
        input_hash=str(normalized_input["input_hash"]),
        as_of_date=cast(date, normalized_input["as_of_date"]),
        config=config,
        library_version=library_version,
        source_signature_value=source_signature_value,
        resolved_location_value=resolved_location_value,
        similar_historical_samples=similar_historical_samples,
        variety_parameters=variety_parameters,
        warnings=(),
        missing_data=(),
        reproducibility_snapshot=cast(
            dict[str, Any],
            normalized_input.get("reproducibility_snapshot", {}),
        ),
    )


def _parameter_bounds(parameter_type: str) -> tuple[Decimal | None, Decimal | None]:
    if parameter_type in {"marketable_rate", "harvest_realization_rate"}:
        return Decimal("0"), Decimal("1")
    if parameter_type in {"yield_kg_per_mu", "maturity_width_days"}:
        return Decimal("0"), None
    return None, None


async def create_minimal_planning_task(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    config: ParameterInferenceConfig,
    dry_run: bool,
    library_version_code: str | None = None,
) -> ParameterInferenceExecutionResult:
    as_of_date = (
        date.fromisoformat(str(payload["as_of_date"]))
        if payload.get("as_of_date") is not None
        else date.today()
    )
    normalized_input, normalized_varieties = await _normalize_payload(session, payload=payload)
    input_hash_value = build_input_hash(normalized_input, as_of_date=as_of_date)
    library_version = await _select_library_version(session, version_code=library_version_code)
    resolved_location = await resolve_location_input(
        session,
        location=cast(dict[str, object], payload["location"]),
        as_of_date=as_of_date,
        rules=config.rules,
    )
    resolved_location_value = resolved_location_payload(resolved_location)
    reproducibility_snapshot = {
        "library_version": library_version.version_code,
        "location_reference_id": resolved_location_value.get("location_reference_id"),
    }
    normalized_input = {
        **normalized_input,
        "input_hash": input_hash_value,
        "as_of_date": as_of_date,
        "resolved_location": resolved_location_value,
        "reproducibility_snapshot": reproducibility_snapshot,
    }

    all_candidate_ids: list[int] = []
    result_rows: list[dict[str, Any]] = []
    variety_parameters: list[dict[str, Any]] = []
    similar_historical_samples: list[dict[str, Any]] = []
    missing_data: list[str] = []

    if resolved_location.status == "resolved":
        for variety in normalized_varieties:
            inferred_rows: dict[str, dict[str, Any]] = {}
            variety_id = int(variety["variety_id"])
            candidates = await _load_candidates(
                session,
                library_version_id=library_version.id,
                variety_id=variety_id,
                as_of_date=as_of_date,
                resolved_location=resolved_location_value,
            )
            for parameter_type in PARAMETER_UNITS:
                parameter_candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.parameter_type == parameter_type
                ]
                floor, ceiling = _parameter_bounds(parameter_type)
                inferred = infer_parameter(
                    parameter_type=parameter_type,
                    candidates=parameter_candidates,
                    rules=config.rules,
                    floor=floor,
                    ceiling=ceiling,
                    resolved_location=resolved_location,
                    as_of_date=as_of_date,
                )
                all_candidate_ids.extend(inferred.source_observation_ids)
                if inferred.status == "unavailable":
                    missing_data.append(f"{variety['variety_code']}:{parameter_type}")
                row = _parameter_row(
                    variety_id=variety_id,
                    parameter_type=parameter_type,
                    inferred=inferred,
                )
                inferred_rows[parameter_type] = row
                result_rows.append(row)
                if inferred.source_observation_ids:
                    similar_historical_samples.append(
                        {
                            "variety_id": variety_id,
                            "parameter_type": parameter_type,
                            "observation_ids": list(inferred.source_observation_ids),
                        }
                    )
            variety_parameters.append(
                _variety_payload(variety=variety, inferred_rows=inferred_rows)
            )

    source_signature_value = source_signature(
        input_hash_value=input_hash_value,
        resolver_version=config.rules.resolver_version,
        library_version=library_version.version_code,
        config_hash=config.config_hash,
        eligible_observation_ids=sorted(set(all_candidate_ids)),
        selected_location_version=str(
            resolved_location_value.get("location_reference_id") or "unresolved"
        ),
    )
    reproducibility_snapshot["eligible_observation_ids"] = sorted(set(all_candidate_ids))
    reproducibility_snapshot["source_signature"] = source_signature_value
    normalized_input["source_signature"] = source_signature_value
    warnings = tuple(resolved_location.warnings)
    missing = tuple(sorted(set(missing_data)))
    location_error_message = (
        warnings[0] if resolved_location.status != "resolved" and warnings else None
    )

    if dry_run:
        return _execution_result(
            status="failed" if resolved_location.status != "resolved" else "dry_run",
            task_id=None,
            run_id=None,
            input_hash=input_hash_value,
            as_of_date=as_of_date,
            config=config,
            library_version=library_version.version_code,
            source_signature_value=source_signature_value,
            resolved_location_value=resolved_location_value,
            similar_historical_samples=similar_historical_samples,
            variety_parameters=variety_parameters,
            warnings=warnings,
            missing_data=missing,
            reproducibility_snapshot=reproducibility_snapshot,
            error_message=location_error_message,
        )

    task = await get_task_by_hash(session, input_hash=input_hash_value, as_of_date=as_of_date)
    if task is None:
        task = await create_task(
            session,
            input_payload=payload,
            normalized_input=normalized_input,
            input_hash=input_hash_value,
            as_of_date=as_of_date,
            status="created",
        )

    task_id = task.id
    resolver_version = config.rules.resolver_version
    library_version_id = library_version.id
    library_version_code_value = library_version.version_code
    config_hash_value = config.config_hash

    existing = await find_existing_run(
        session,
        input_hash=input_hash_value,
        as_of_date=as_of_date,
        resolver_version=resolver_version,
        library_version_id=library_version_id,
        config_hash=config_hash_value,
    )
    if existing is not None:
        if existing.status == "running":
            return _execution_result(
                status="running",
                task_id=task_id,
                run_id=existing.id,
                input_hash=input_hash_value,
                as_of_date=as_of_date,
                config=config,
                library_version=library_version_code_value,
                source_signature_value=existing.source_signature,
                resolved_location_value=resolved_location_value,
                similar_historical_samples=[],
                variety_parameters=[],
                warnings=warnings,
                missing_data=missing,
                reproducibility_snapshot=reproducibility_snapshot,
            )
        return await _rehydrate_existing(
            session,
            task_id=task_id,
            run_id=existing.id,
            config=config,
            normalized_input=normalized_input,
            library_version=library_version_code_value,
            source_signature_value=existing.source_signature,
            resolved_location_value=resolved_location_value,
        )

    if resolved_location.status != "resolved":
        assert location_error_message is not None
        await mark_task_status(
            session,
            task_id=task_id,
            status="failed",
            error_message=location_error_message,
        )
        return _execution_result(
            status="failed",
            task_id=task_id,
            run_id=None,
            input_hash=input_hash_value,
            as_of_date=as_of_date,
            config=config,
            library_version=library_version_code_value,
            source_signature_value=source_signature_value,
            resolved_location_value=resolved_location_value,
            similar_historical_samples=[],
            variety_parameters=[],
            warnings=warnings,
            missing_data=missing,
            reproducibility_snapshot=reproducibility_snapshot,
            error_message=location_error_message,
        )

    run_id: int | None = None
    try:
        await mark_task_status(session, task_id=task_id, status="resolving_location")
        run = await create_running_run(
            session,
            task_id=task_id,
            input_hash=input_hash_value,
            as_of_date=as_of_date,
            resolver_version=resolver_version,
            library_version_id=library_version_id,
            config_hash=config_hash_value,
            source_signature=source_signature_value,
        )
        run_id = run.id
    except IntegrityError:
        await session.rollback()
        current = await find_existing_run(
            session,
            input_hash=input_hash_value,
            as_of_date=as_of_date,
            resolver_version=resolver_version,
            library_version_id=library_version_id,
            config_hash=config_hash_value,
        )
        if current is None:
            raise
        if current.status == "running":
            return _execution_result(
                status="running",
                task_id=task_id,
                run_id=current.id,
                input_hash=input_hash_value,
                as_of_date=as_of_date,
                config=config,
                library_version=library_version_code_value,
                source_signature_value=current.source_signature,
                resolved_location_value=resolved_location_value,
                similar_historical_samples=[],
                variety_parameters=[],
                warnings=warnings,
                missing_data=missing,
                reproducibility_snapshot=reproducibility_snapshot,
            )
        return await _rehydrate_existing(
            session,
            task_id=task_id,
            run_id=current.id,
            config=config,
            normalized_input=normalized_input,
            library_version=library_version_code_value,
            source_signature_value=current.source_signature,
            resolved_location_value=resolved_location_value,
        )

    try:
        await mark_task_status(session, task_id=task_id, status="inferring_parameters")
        assert run_id is not None
        await replace_results(session, run_id=run_id, rows=result_rows)
        await session.commit()
        await mark_run_completed(session, run_id=run_id)
        await mark_task_status(session, task_id=task_id, status="parameters_ready")
        return _execution_result(
            status="completed",
            task_id=task_id,
            run_id=run_id,
            input_hash=input_hash_value,
            as_of_date=as_of_date,
            config=config,
            library_version=library_version_code_value,
            source_signature_value=source_signature_value,
            resolved_location_value=resolved_location_value,
            similar_historical_samples=similar_historical_samples,
            variety_parameters=variety_parameters,
            warnings=warnings,
            missing_data=missing,
            reproducibility_snapshot=reproducibility_snapshot,
        )
    except Exception as exc:
        error_message = _sanitize_error_message(str(exc))
        await session.rollback()
        if run_id is not None:
            await mark_run_failed(session, run_id=run_id, error_message=error_message)
        await mark_task_status(
            session,
            task_id=task_id,
            status="failed",
            error_message=error_message,
        )
        return _execution_result(
            status="failed",
            task_id=task_id,
            run_id=run_id,
            input_hash=input_hash_value,
            as_of_date=as_of_date,
            config=config,
            library_version=library_version_code_value,
            source_signature_value=source_signature_value,
            resolved_location_value=resolved_location_value,
            similar_historical_samples=similar_historical_samples,
            variety_parameters=variety_parameters,
            warnings=warnings,
            missing_data=missing,
            reproducibility_snapshot=reproducibility_snapshot,
            error_message=error_message,
        )


async def load_minimal_planning_task_result(
    session: AsyncSession,
    *,
    task_id: int,
    config: ParameterInferenceConfig,
) -> ParameterInferenceExecutionResult:
    task = await get_task(session, task_id=task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")
    run = await get_run_by_task(session, task_id=task_id)
    normalized_input = task.normalized_input
    if run is None:
        if task.status != "failed":
            raise ValueError(f"run not found for task: {task_id}")
        resolved_location_value = cast(
            dict[str, Any],
            normalized_input.get("resolved_location", {}),
        )
        warnings = tuple(cast(tuple[str, ...], tuple(resolved_location_value.get("warnings", ()))))
        reproducibility_snapshot = cast(
            dict[str, Any],
            normalized_input.get("reproducibility_snapshot", {}),
        )
        return _execution_result(
            status="failed",
            task_id=task.id,
            run_id=None,
            input_hash=task.input_hash,
            as_of_date=task.as_of_date,
            config=config,
            library_version=cast(str | None, reproducibility_snapshot.get("library_version")),
            source_signature_value=str(normalized_input.get("source_signature", "")),
            resolved_location_value=resolved_location_value,
            similar_historical_samples=[],
            variety_parameters=[],
            warnings=warnings,
            missing_data=(),
            reproducibility_snapshot=reproducibility_snapshot,
            error_message=task.error_message,
        )
    library_version = await get_library_version_by_id(
        session,
        library_version_id=run.library_version_id,
    )
    return await _rehydrate_existing(
        session,
        task_id=task.id,
        run_id=run.id,
        config=config,
        normalized_input=normalized_input,
        library_version=(library_version.version_code if library_version is not None else None),
        source_signature_value=run.source_signature,
        resolved_location_value=cast(
            dict[str, Any],
            normalized_input.get("resolved_location", {}),
        ),
    )
