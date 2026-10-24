"""Manual issuance, exact-scope discovery and explicit-window comparison."""

from datetime import date
from decimal import Decimal, localcontext
from typing import Any, get_args

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.local_auth.sessions import AuthError, Principal
from backend.app.rolling_forecast import engine, inbound, model_artifacts, observations, persistence
from backend.app.rolling_forecast.identity import implementation_hash
from backend.app.rolling_forecast.models import RollingRun
from backend.app.rolling_forecast.policy import Catalog, Context, InboundSnapshot
from backend.app.rolling_forecast.schemas import Issue, TargetQuantityBasis
from backend.research.v019_synthetic_validation import digest


def contexts(catalog: Catalog, principal: Principal, operation: str) -> list[Context]:
    allowed = catalog.allowed(principal, operation)
    if not allowed:
        raise AuthError("FORBIDDEN")
    return allowed


def scope_filter(allowed: list[Context], principal: Principal) -> Any:
    # Authorization predicates are applied in SQL BEFORE ordering/limit/offset.
    return (RollingRun.principal_id == principal.principal_id) & or_(
        *(
            and_(
                RollingRun.context_reference == c.reference,
                RollingRun.base_id == c.area.base_id,
                RollingRun.target_season == c.calendar.season,
                RollingRun.snapshot["input"]["organization_id"].as_string() == c.organization_id,
            )
            for c in allowed
        )
    )


async def get(
    db: AsyncSession, catalog: Catalog, principal: Principal, run_id: int, operation: str = "read"
) -> dict[str, Any]:
    allowed = contexts(catalog, principal, operation)
    run = await db.scalar(
        select(RollingRun).where(RollingRun.id == run_id, scope_filter(allowed, principal))
    )
    if run is None:
        raise AuthError("RUN_NOT_FOUND", 404)
    return await persistence.canonical(db, run)


async def issue(
    db: AsyncSession, catalog: Catalog, principal: Principal, request: Issue
) -> dict[str, Any]:
    candidates = [
        c
        for c in contexts(catalog, principal, "issue")
        if c.area.base_id == request.base_id
        and c.area.season == request.target_season
        and c.area.reference == request.area_authority_reference
        and request.execution_mode in c.modes
        and any(m.reference == request.frozen_model_artifact_reference for m in c.models)
        and any(s.reference == request.observation_snapshot_reference for s in c.snapshots)
    ]
    if len(candidates) != 1:
        raise AuthError("FORBIDDEN")
    context = candidates[0]
    if request.rerun_of_run_id is not None:
        # A parent reference is an authorized business read too. Check it before
        # model/observation reads, not after computing the proposed new forecast.
        parent = await get(db, catalog, principal, request.rerun_of_run_id, "issue")
        if parent["input"]["context_reference"] != context.reference or (
            parent["base_id"],
            parent["target_season"],
        ) != (request.base_id, request.target_season):
            raise AuthError("RUN_NOT_FOUND", 404)
    source = next(
        s for s in context.snapshots if s.reference == request.observation_snapshot_reference
    )
    model = next(
        m for m in context.models if m.reference == request.frozen_model_artifact_reference
    )
    # Non-sensitive authority and model checks precede observation quantities.
    engine.harvest_features(
        context.calendar,
        context.area,
        request.origin_date,
        request.origin_cutoff_at,
        [],
        request.execution_mode,
    )
    pair = model_artifacts.load(model)
    if isinstance(source, InboundSnapshot):
        inbound.require_target(source, pair)
    rows = await observations.load(
        db, context, source, request.origin_date, request.origin_cutoff_at
    )
    result = engine.forecast(
        context.calendar,
        context.area,
        request.origin_date,
        request.origin_cutoff_at,
        rows,
        pair,
        request.execution_mode,
    )
    input_snapshot = {
        "issue": request.model_dump(mode="json"),
        "context_reference": context.reference,
        "organization_id": context.organization_id,
        "catalog_revision": catalog.revision,
        "context_hash": digest(context.model_dump(mode="json")),
        "observation_snapshot": source.model_dump(mode="json", exclude={"manifest_path"}),
        "model_source": model.model_dump(mode="json", exclude={"path", "execution_manifest_path"}),
        "feature_hash": result["feature_snapshot"]["feature_hash"],
        "algorithm_version": "ROLLING_SHADOW_V1_S6_FROZEN_RIDGE",
        "implementation_hash": implementation_hash(),
    }
    return await persistence.save(
        db, principal.principal_id, context.reference, request, input_snapshot, result
    )


async def history(
    db: AsyncSession, catalog: Catalog, principal: Principal, filters: dict[str, Any]
) -> dict[str, Any]:
    allowed = contexts(catalog, principal, "read")
    query = select(RollingRun).where(scope_filter(allowed, principal))
    for key in ("base_id", "target_season", "origin_date"):
        if filters.get(key) is not None:
            query = query.where(getattr(RollingRun, key) == filters[key])
    rows = (
        await db.scalars(
            query.order_by(RollingRun.origin_date.desc(), RollingRun.id.desc())
            .offset(filters["offset"])
            .limit(filters["limit"])
        )
    ).all()
    items = []
    for row in rows:
        value = await persistence.canonical(db, row)
        items.append(
            {
                k: value[k]
                for k in (
                    "run_id",
                    "base_id",
                    "target_season",
                    "origin_date",
                    "status",
                    "result_hash",
                )
            }
        )
    # Only authorized resource references, never private paths or global entities.
    resources = [
        {
            "base_id": c.area.base_id,
            "target_season": c.area.season,
            "area_authority_reference": c.area.reference,
            "observation_snapshot_references": [s.reference for s in c.snapshots],
            "frozen_model_artifact_references": [m.reference for m in c.models],
            "execution_modes": list(c.modes),
        }
        for c in allowed
    ]
    return {
        "items": items,
        "resources": resources,
        "offset": filters["offset"],
        "limit": filters["limit"],
    }


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    lr, rr = left["result"], right["result"]
    bases = get_args(TargetQuantityBasis)
    common_reasons = []
    if left["base_id"] != right["base_id"]:
        common_reasons.append("BASE_MISMATCH")
    if left["target_season"] != right["target_season"]:
        common_reasons.append("SEASON_MISMATCH")
    left_basis, right_basis = (r["feature_snapshot"]["quantity_basis"] for r in (lr, rr))
    if left_basis not in bases or right_basis not in bases:
        common_reasons.append("FEATURE_OBSERVATION_BASIS_UNVERIFIED")
    elif left_basis != right_basis:
        common_reasons.append("FEATURE_OBSERVATION_BASIS_MISMATCH")
    result: dict[str, Any] = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for model in ("M0", "M1"):
            a, b = lr["models"][model], rr["models"][model]
            if a["status"] != "COMPUTED" or b["status"] != "COMPUTED":
                result[model] = {
                    "status": "NOT_COMPUTABLE",
                    "reasons": ["INCOMPLETE_MODEL_PREDICTIONS"],
                }
                continue
            reasons = list(common_reasons)
            if (a["model_artifact_hash"], a["model_id"]) != (
                b["model_artifact_hash"],
                b["model_id"],
            ):
                reasons.append("MODEL_IDENTITY_MISMATCH")
            if a.get("model_provenance") != b.get("model_provenance"):
                reasons.append("MODEL_PROVENANCE_MISMATCH")
            targets = [v.get("forecast_target_quantity_basis") for v in (a, b)]
            if any(t not in bases for t in targets) or any(
                v.get("model_training_target_quantity_basis") != t
                for v, t in zip((a, b), targets, strict=True)
            ):
                reasons.append("MODEL_TARGET_BASIS_UNVERIFIED")
            elif targets[0] != targets[1]:
                reasons.append("FORECAST_TARGET_BASIS_MISMATCH")
            if reasons:
                result[model] = {"status": "NOT_COMPARABLE", "reasons": reasons}
                continue
            aa = {r["date"]: Decimal(r["kg"]) for r in a["daily_forecast_kg"]}
            bb = {r["date"]: Decimal(r["kg"]) for r in b["daily_forecast_kg"]}
            common_dates = aa.keys() & bb.keys()
            if not common_dates:
                result[model] = {
                    "status": "NOT_COMPARABLE",
                    "reasons": ["NO_COMMON_TARGET_DATES"],
                }
                continue
            windows = {}
            for window in ("H7", "H15"):
                av, bv = a[window], b[window]
                windows[window] = {
                    "total_delta_kg": format(
                        Decimal(bv["forecast_total_kg"]) - Decimal(av["forecast_total_kg"]), ".6f"
                    ),
                    "single_peak_date_delta_days": (
                        date.fromisoformat(bv["single_day_peak_date"])
                        - date.fromisoformat(av["single_day_peak_date"])
                    ).days,
                    "single_peak_kg_delta": str(
                        Decimal(bv["single_day_peak_kg"]) - Decimal(av["single_day_peak_kg"])
                    ),
                    "rolling7_start_delta_days": (
                        date.fromisoformat(bv["rolling_7day_peak_start"])
                        - date.fromisoformat(av["rolling_7day_peak_start"])
                    ).days,
                    "rolling7_kg_delta": str(
                        Decimal(bv["rolling_7day_peak_cumulative_kg"])
                        - Decimal(av["rolling_7day_peak_cumulative_kg"])
                    ),
                    "meaning": "DIFFERENT_ORIGIN_WINDOW_TOTALS_NOT_SAME_DATE_REVISION",
                }
            result[model] = {
                "status": "COMPARABLE",
                "windows": windows,
                "common_target_daily_delta_kg": [
                    {"date": d, "kg": format(bb[d] - aa[d], ".6f")} for d in sorted(common_dates)
                ],
            }
    body = {
        "left_run": left["run_id"],
        "right_run": right["run_id"],
        "left_origin": left["origin_date"],
        "right_origin": right["origin_date"],
        "left_result_hash": left["result_hash"],
        "right_result_hash": right["result_hash"],
        "left_quantity_basis": lr["feature_snapshot"]["quantity_basis"],
        "right_quantity_basis": rr["feature_snapshot"]["quantity_basis"],
        "models": result,
        "production_model": False,
    }
    return {**body, "comparison_hash": digest(body)}
