"""Canonical reload and idempotent immutable persistence, caller-owned transaction."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rolling_forecast.models import RollingDaily, RollingRun
from backend.app.rolling_forecast.schemas import Issue
from backend.research.v019_synthetic_validation import digest


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
        parent = await db.get(RollingRun, issue.rerun_of_run_id)
        if parent is None or (parent.principal_id, parent.context_reference) != (
            principal,
            context,
        ):
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
