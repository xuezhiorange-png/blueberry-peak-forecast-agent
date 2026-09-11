"""Versioned empirical authority persistence and Task9 request binding."""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.canonical import sha256_hex
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.models.empirical_forecast import EmpiricalMaturityAuthority
from backend.app.planning.empirical_maturity import build_empirical_curve


def verify_authority(payload: dict[str, Any], authority_hash: str) -> None:
    if sha256_hex(payload) != authority_hash:
        raise ValueError("empirical authority hash mismatch")
    curve = payload["curve"]
    daily = {
        date.fromisoformat(r["historical_date"]): Decimal(r["historical_kg"])
        for r in curve["days"]
        if r["observed"]
    }
    replay = build_empirical_curve(
        daily,
        source_hash=curve["source_hash"],
        area_mu=Decimal(curve["calibration_area_mu"]),
        as_of=date.fromisoformat(curve["as_of"]),
    )
    if replay != curve:
        raise ValueError("empirical curve replay mismatch")


async def load_empirical_authority(session: AsyncSession, authority_hash: str) -> dict[str, Any]:
    row = await session.get(EmpiricalMaturityAuthority, authority_hash)
    if row is None:
        raise ValueError("empirical authority not found")
    verify_authority(row.payload, authority_hash)
    return row.payload


async def persist_empirical_authority(session: AsyncSession, payload: dict[str, Any]) -> str:
    authority_hash = sha256_hex(payload)
    verify_authority(payload, authority_hash)
    existing = await session.get(EmpiricalMaturityAuthority, authority_hash)
    if existing is None:
        session.add(EmpiricalMaturityAuthority(authority_hash=authority_hash, payload=payload))
        await session.flush()
    elif existing.payload != payload:
        raise ValueError("empirical authority conflict")
    return authority_hash


async def verify_empirical_task9_request(session: AsyncSession, request: Task9ARequest) -> None:
    if not request.empirical_daily_predictions:
        return
    hashes = {p.source_ref.authority_hash for p in request.empirical_daily_predictions}
    if len(hashes) != 1:
        raise ValueError("mixed empirical authorities")
    authority = await load_empirical_authority(session, next(iter(hashes)))
    from backend.app.planning.empirical_forecast import build_empirical_task9_request

    if request != build_empirical_task9_request(authority):
        raise ValueError("empirical operational policy binding mismatch")
    curve, scope = authority["curve"], authority["scope"]
    if (
        request.destination_factory_id != scope["factory_id"]
        or request.forecast_season_identity.model_dump(mode="json") != authority["season"]
        or request.as_of_date.isoformat() != curve["as_of"]
        or request.forecast_start_date.isoformat() != curve["forecast_start"]
        or request.forecast_end_date.isoformat() != curve["forecast_end"]
    ):
        raise ValueError("empirical request scope or window mismatch")
    supply = {r["date"]: Decimal(r["supply_kg"]) for r in curve["days"]}
    for p in request.empirical_daily_predictions:
        if (
            p.farm_id != scope["farm_id"]
            or p.variety_id != scope["variety_id"]
            or p.subfarm_id is not None
            or p.source_ref.curve_hash != curve["curve_hash"]
            or p.source_ref.available_at.isoformat() != curve["as_of"]
            or supply.get(p.prediction_date.isoformat()) != p.source_ref.source_quantity_kg
        ):
            raise ValueError("empirical persisted supply mismatch")
