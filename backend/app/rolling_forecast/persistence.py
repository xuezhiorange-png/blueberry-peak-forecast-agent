"""Canonical reload and idempotent immutable persistence, caller-owned transaction."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rolling_forecast.models import RollingDaily, RollingRun
from backend.app.rolling_forecast.schemas import Issue
from backend.research.v019_synthetic_validation import digest


def verify_persisted_metrics(
    rows: list[RollingDaily], result: dict[str, Any], origin: date
) -> None:
    """Recompute from persisted daily values, not JSON summaries or Ridge."""
    with localcontext() as ctx:
        ctx.prec = 50
        for name, model in result["models"].items():
            daily = sorted((r for r in rows if r.model == name), key=lambda r: r.target_date)
            if model["status"] == "NOT_COMPUTABLE":
                if daily or model["H7"] is not None or model["H15"] is not None:
                    raise ValueError("ROLLING_PERSISTED_METRIC_MISMATCH")
                continue
            dates = [origin + timedelta(days=i) for i in range(1, 16)]
            if (
                model["status"] != "COMPUTED"
                or [r.target_date for r in daily] != dates
                or [r["date"] for r in model["daily_forecast_kg"]] != list(map(str, dates))
            ):
                raise ValueError("ROLLING_DAILY_CALENDAR_MISMATCH")
            if any(not r.quantity_kg.is_finite() or r.quantity_kg < 0 for r in daily):
                raise ValueError("ROLLING_DAILY_ROW_MISMATCH")
            for window, count in (("H7", 7), ("H15", 15)):
                selected = daily[:count]
                peak = max(selected, key=lambda r: r.quantity_kg)
                sums = [
                    sum((r.quantity_kg for r in selected[i : i + 7]), Decimal(0))
                    for i in range(count - 6)
                ]
                start = max(range(len(sums)), key=lambda i: sums[i])
                # max returns the first equal maximum: chronological earliest tie.
                expected = {
                    "forecast_total_kg": format(
                        sum((r.quantity_kg for r in selected), Decimal(0)), ".6f"
                    ),
                    "single_day_peak_date": str(peak.target_date),
                    "single_day_peak_kg": format(peak.quantity_kg, ".6f"),
                    "rolling_7day_peak_start": str(selected[start].target_date),
                    "rolling_7day_peak_end": str(selected[start + 6].target_date),
                    "rolling_7day_peak_cumulative_kg": format(sums[start], ".6f"),
                    "scope": "THIS_FORECAST_WINDOW_ONLY",
                }
                if model[window] != expected:
                    raise ValueError("ROLLING_PERSISTED_METRIC_MISMATCH")


async def canonical(db: AsyncSession, run: RollingRun) -> dict[str, Any]:
    body = run.snapshot
    issue = body["input"]["issue"]
    if (
        run.base_id != issue["base_id"]
        or run.target_season != issue["target_season"]
        or str(run.origin_date) != issue["origin_date"]
        or run.origin_cutoff_at != datetime.fromisoformat(issue["origin_cutoff_at"])
        or run.context_reference != body["input"]["context_reference"]
    ):
        raise ValueError("ROLLING_IDENTITY_MISMATCH")
    if digest(body["input"]) != run.input_hash or digest(body["result"]) != run.result_hash:
        raise ValueError("ROLLING_RESULT_HASH_MISMATCH")
    rows = list((await db.scalars(select(RollingDaily).where(RollingDaily.run_id == run.id))).all())
    actual = sorted((r.model, str(r.target_date), format(r.quantity_kg, ".6f")) for r in rows)
    expected = sorted(
        (m, r["date"], r["kg"])
        for m, value in body["result"]["models"].items()
        for r in value["daily_forecast_kg"]
    )
    if actual != expected:
        raise ValueError("ROLLING_DAILY_ROW_MISMATCH")
    verify_persisted_metrics(rows, body["result"], run.origin_date)
    return {
        "run_id": run.id,
        "base_id": run.base_id,
        "target_season": run.target_season,
        "origin_date": str(run.origin_date),
        "origin_cutoff_at": run.origin_cutoff_at.isoformat(),
        "created_at": run.created_at.isoformat(),
        "issued_at": run.issued_at.isoformat() if run.issued_at else None,
        "rerun_of_run_id": run.rerun_of_run_id,
        "status": run.status,
        "input_hash": run.input_hash,
        "result_hash": run.result_hash,
        **body,
    }


async def save(
    db: AsyncSession,
    principal: str,
    context: str,
    issue: Issue,
    input_snapshot: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    key = digest(input_snapshot)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(key[:15], 16)})
    existing = await db.scalar(
        select(RollingRun).where(RollingRun.principal_id == principal, RollingRun.input_hash == key)
    )
    if existing is not None:
        return await canonical(db, existing)
    if issue.rerun_of_run_id is not None:
        parent = await db.scalar(
            select(RollingRun.id).where(
                RollingRun.id == issue.rerun_of_run_id,
                RollingRun.principal_id == principal,
                RollingRun.context_reference == context,
                RollingRun.base_id == issue.base_id,
                RollingRun.target_season == issue.target_season,
                RollingRun.snapshot["input"]["organization_id"].as_string()
                == input_snapshot["organization_id"],
            )
        )
        if parent is None:
            raise ValueError("RERUN_SCOPE_MISMATCH")
    states = [v["status"] for v in result["models"].values()]
    run = RollingRun(
        principal_id=principal,
        context_reference=context,
        base_id=issue.base_id,
        target_season=issue.target_season,
        origin_date=issue.origin_date,
        origin_cutoff_at=issue.origin_cutoff_at,
        input_hash=key,
        result_hash=digest(result),
        status="COMPUTED"
        if all(s == "COMPUTED" for s in states)
        else "PARTIAL"
        if "COMPUTED" in states
        else "BLOCKED",
        snapshot={"input": input_snapshot, "result": result},
        created_at=datetime.now(UTC),
        issued_at=None,
        rerun_of_run_id=issue.rerun_of_run_id,
    )
    db.add(run)
    await db.flush()
    for model, value in result["models"].items():
        db.add_all(
            [
                RollingDaily(
                    run_id=run.id,
                    model=model,
                    target_date=date.fromisoformat(r["date"]),
                    quantity_kg=Decimal(r["kg"]),
                )
                for r in value["daily_forecast_kg"]
            ]
        )
    await db.flush()
    return await canonical(db, run)
