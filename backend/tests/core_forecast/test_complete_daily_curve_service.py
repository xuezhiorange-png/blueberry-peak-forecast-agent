from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.repository import (
    SeasonSource,
    Task8AuthoritySource,
    Task8DailyPredictionSource,
    Task9AuthoritySource,
    Task9MemberSource,
)
from backend.app.core_forecast.schemas import (
    QUANTILES,
    CompleteDailyMarketableCurveRequest,
    MarketableRetentionPolicyEntry,
    MarketableRetentionPolicySnapshot,
)
from backend.app.core_forecast.service import compose_complete_daily_marketable_curve
from backend.app.rolling_backtest.canonical import canonical_json_dumps

FIXTURE_DIR = Path("backend/tests/fixtures/v0_1_complete_season_case_01")
INPUT = json.loads((FIXTURE_DIR / "input.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURE_DIR / "expected_daily.json").read_text(encoding="utf-8"))["rows"]


class FixtureRepository:
    def __init__(
        self,
        task8: Task8AuthoritySource,
        task9: Task9AuthoritySource,
        season: SeasonSource | None = None,
    ) -> None:
        self.task8 = task8
        self.task9 = task9
        self.season = season or SeasonSource(season_id=2026, code="2026-DEMO")

    async def load_task8_authority(self, run_id: int) -> Task8AuthoritySource | None:
        return self.task8 if run_id == self.task8.run_id else None

    async def load_task9_authority(self, run_id: int) -> Task9AuthoritySource | None:
        return self.task9 if run_id == self.task9.run_id else None

    async def load_season(self, season_id: int) -> SeasonSource | None:
        return self.season if season_id == self.season.season_id else None


def _request() -> CompleteDailyMarketableCurveRequest:
    scopes = sorted(
        {(row["farm_id"], row["subfarm_id"], row["variety_id"]) for row in INPUT["daily_inputs"]}
    )
    return CompleteDailyMarketableCurveRequest(
        forecast_season_id=2026,
        forecast_season_code=INPUT["season"]["season_code"],
        forecast_start_date=date.fromisoformat(INPUT["season"]["forecast_start_date"]),
        forecast_end_date=date.fromisoformat(INPUT["season"]["forecast_end_date"]),
        destination_factory_id=9101,
        task8_forecast_run_id=810001,
        task9_harvest_state_run_id=910001,
        scopes=tuple(
            {"farm_id": farm, "subfarm_id": subfarm, "variety_id": variety}
            for farm, subfarm, variety in scopes
        ),
    )


def _policy() -> MarketableRetentionPolicySnapshot:
    return MarketableRetentionPolicySnapshot(
        entries=tuple(
            MarketableRetentionPolicyEntry(
                forecast_season_id=2026,
                forecast_season_code=entry["season_code"],
                farm_id=entry["farm_id"],
                subfarm_id=entry["subfarm_id"],
                variety_id=entry["variety_id"],
                sorting_retention_rate=entry["sorting_retention_rate"],
                postharvest_retention_rate=entry["postharvest_retention_rate"],
                source=entry["source"],
                version=entry["version"],
                hash=entry["hash"],
            )
            for entry in INPUT["marketable_retention_policy"]
        )
    )


def _sources() -> tuple[Task8AuthoritySource, Task9AuthoritySource]:
    daily_inputs = INPUT["daily_inputs"]
    task8_rows: list[Task8DailyPredictionSource] = []
    for current_date in sorted({row["date"] for row in daily_inputs}):
        by_quantile = {
            quantile: sum(
                (
                    Decimal(row["natural_maturity_supply_kg"])
                    for row in daily_inputs
                    if row["date"] == current_date and row["forecast_quantile"] == quantile
                ),
                Decimal("0"),
            )
            for quantile in QUANTILES
        }
        task8_rows.append(
            Task8DailyPredictionSource(
                prediction_date=date.fromisoformat(current_date),
                p50_kg=by_quantile["P50"],
                p80_kg=by_quantile["P80"],
                p90_kg=by_quantile["P90"],
            )
        )

    members = tuple(
        Task9MemberSource(
            state_date=date.fromisoformat(row["date"]),
            forecast_quantile=row["forecast_quantile"],
            farm_id=row["farm_id"],
            subfarm_id=row["subfarm_id"],
            variety_id=row["variety_id"],
            destination_factory_id=row["destination_factory_id"],
            natural_maturity_supply_kg=Decimal(row["natural_maturity_supply_kg"]),
            opening_mature_inventory_kg=Decimal(row["opening_mature_inventory_kg"]),
            available_mature_quantity_kg=Decimal(row["available_mature_quantity_kg"]),
            mature_inventory_loss_quantity_kg=Decimal(row["mature_inventory_loss_quantity_kg"]),
            harvestable_mature_quantity_kg=Decimal(row["harvestable_mature_quantity_kg"]),
            allocated_harvest_capacity_kg=Decimal(row["effective_harvest_capacity_kg"]),
            harvested_quantity_kg=Decimal(row["model_harvested_marketable_quantity_kg"]),
            closing_mature_inventory_kg=Decimal(row["closing_mature_inventory_kg"]),
            unharvested_backlog_kg=Decimal(row["unharvested_backlog_kg"]),
        )
        for row in daily_inputs
    )
    task8 = Task8AuthoritySource(
        run_id=810001,
        model_run_id=810000,
        status="completed",
        prediction_start_date=date(2026, 3, 1),
        prediction_end_date=date(2026, 5, 29),
        artifact_id=810010,
        artifact_run_id=810000,
        artifact_hash=INPUT["task8_authority"]["artifact_hash"],
        daily_predictions=tuple(task8_rows),
    )
    task9 = Task9AuthoritySource(
        run_id=910001,
        status="completed",
        forecast_start_date=date(2026, 3, 1),
        forecast_end_date=date(2026, 5, 29),
        destination_factory_id=9101,
        forecast_season_id=2026,
        maturity_forecast_run_id=810001,
        maturity_model_artifact_hash=INPUT["task8_authority"]["artifact_hash"],
        result_hash=INPUT["task9_authority"]["result_hash"],
        member_rows=members,
    )
    return task8, task9


async def _run(
    repository: FixtureRepository | None = None,
    *,
    policy: MarketableRetentionPolicySnapshot | None = None,
):
    task8, task9 = _sources()
    repo = repository or FixtureRepository(task8, task9)
    return await compose_complete_daily_marketable_curve(
        cast(AsyncSession, object()),
        request=_request(),
        retention_policy=policy or _policy(),
        repository=repo,
    )


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.golden
async def test_complete_season_fixture_replay_matches_expected_daily_exactly() -> None:
    result = await _run()
    assert result.status == "COMPLETED"
    assert [row.model_dump(mode="json") for row in result.rows] == EXPECTED


@pytest.mark.unit
async def test_output_has_1080_rows_1080_unique_keys_and_12_complete_series() -> None:
    result = await _run()
    keys = [
        (row.date, row.farm_id, row.subfarm_id, row.variety_id, row.forecast_quantile)
        for row in result.rows
    ]
    series = {
        (row.farm_id, row.subfarm_id, row.variety_id, row.forecast_quantile) for row in result.rows
    }
    assert len(result.rows) == 1080
    assert len(set(keys)) == 1080
    assert len(series) == 12
    assert all(keys.count(key) == 1 for key in set(keys))


@pytest.mark.unit
async def test_task8_task9_daily_supply_reconciles_for_every_date_and_quantile() -> None:
    result = await _run()
    assert result.status == "COMPLETED"
    assert result.blockers == ()


@pytest.mark.unit
async def test_effective_marketable_quantity_uses_only_two_retention_rates() -> None:
    result = await _run()
    row = next(
        row
        for row in result.rows
        if row.variety_id == 2102 and row.effective_marketable_quantity_kg != "0.000000"
    )
    expected = (
        Decimal(row.model_harvested_marketable_quantity_kg)
        * Decimal(row.sorting_retention_rate)
        * Decimal(row.postharvest_retention_rate)
    ).quantize(Decimal("0.000001"))
    assert row.effective_marketable_quantity_kg == format(expected, "f")


@pytest.mark.unit
async def test_marketable_rate_is_never_reapplied() -> None:
    result = await _run()
    row = next(
        row
        for row in result.rows
        if row.variety_id == 2102 and row.effective_marketable_quantity_kg != "0.000000"
    )
    double_reduced = (
        Decimal(row.model_harvested_marketable_quantity_kg)
        * Decimal("0.800000")
        * Decimal(row.sorting_retention_rate)
        * Decimal(row.postharvest_retention_rate)
    ).quantize(Decimal("0.000001"))
    assert Decimal(row.effective_marketable_quantity_kg) != double_reduced


@pytest.mark.unit
async def test_member_allocated_capacity_maps_to_effective_harvest_capacity() -> None:
    result = await _run()
    source = {
        key: row
        for key, row in zip(
            [
                (r.date, r.forecast_quantile, r.farm_id, r.subfarm_id, r.variety_id)
                for r in result.rows
            ],
            result.rows,
            strict=True,
        )
    }
    _, task9 = _sources()
    for member in task9.member_rows:
        key = (
            member.state_date,
            member.forecast_quantile,
            member.farm_id,
            member.subfarm_id,
            member.variety_id,
        )
        assert (
            source[key].effective_harvest_capacity_kg
            == f"{member.allocated_harvest_capacity_kg:.6f}"
        )


@pytest.mark.unit
async def test_row_hash_matches_s1_canonical_payload() -> None:
    result = await _run()
    for row in result.rows:
        payload = row.model_dump(mode="json", exclude={"row_hash"})
        import hashlib

        expected = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
        assert row.row_hash == expected


@pytest.mark.unit
async def test_same_inputs_produce_identical_rows_and_curve_hash() -> None:
    first = await _run()
    second = await _run()
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


@pytest.mark.unit
async def test_rows_are_sorted_by_frozen_business_key() -> None:
    result = await _run()
    actual = [
        (row.date, row.farm_id, row.subfarm_id, row.variety_id, row.forecast_quantile)
        for row in result.rows
    ]
    assert actual == sorted(actual, key=lambda item: (*item[:4], QUANTILES.index(item[4])))


@pytest.mark.unit
async def test_missing_policy_fails_closed() -> None:
    result = await _run(policy=MarketableRetentionPolicySnapshot(entries=()))
    assert result.status == "BLOCKED"
    assert result.rows == ()
    assert result.blockers[0].code == "MARKETABLE_RETENTION_POLICY_MISSING"


@pytest.mark.unit
async def test_duplicate_policy_fails_closed() -> None:
    policy = _policy()
    result = await _run(
        policy=MarketableRetentionPolicySnapshot(entries=policy.entries + (policy.entries[0],))
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "MARKETABLE_RETENTION_POLICY_CONFLICT"


@pytest.mark.unit
def test_invalid_policy_rate_fails_closed() -> None:
    with pytest.raises(ValidationError):
        MarketableRetentionPolicyEntry(
            forecast_season_id=2026,
            forecast_season_code="2026-DEMO",
            farm_id=101,
            subfarm_id=1101,
            variety_id=2101,
            sorting_retention_rate=1.1,  # type: ignore[arg-type]
            postharvest_retention_rate="1.000000",
            source="fixture",
            version="v1",
            hash="a" * 64,
        )


@pytest.mark.unit
def test_malformed_policy_hash_fails_closed() -> None:
    with pytest.raises(ValidationError):
        MarketableRetentionPolicyEntry(
            forecast_season_id=2026,
            forecast_season_code="2026-DEMO",
            farm_id=101,
            subfarm_id=1101,
            variety_id=2101,
            sorting_retention_rate="1.000000",
            postharvest_retention_rate="1.000000",
            source="fixture",
            version="v1",
            hash="not-a-sha",
        )


@pytest.mark.unit
async def test_task8_task9_lineage_mismatch_fails_closed() -> None:
    task8, task9 = _sources()
    repository = FixtureRepository(task8, replace(task9, maturity_forecast_run_id=999999))
    result = await _run(repository)
    assert result.status == "BLOCKED"
    assert result.rows == ()
    assert result.blockers[0].code == "AUTHORITY_LINEAGE_MISMATCH"


@pytest.mark.unit
async def test_missing_task8_daily_prediction_fails_closed() -> None:
    task8, task9 = _sources()
    repository = FixtureRepository(task8=replace(task8, daily_predictions=()), task9=task9)
    result = await _run(repository)
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "TASK8_TASK9_SUPPLY_RECONCILIATION_FAILED"


@pytest.mark.unit
async def test_duplicate_member_key_fails_closed() -> None:
    task8, task9 = _sources()
    repository = FixtureRepository(
        task8, replace(task9, member_rows=task9.member_rows + (task9.member_rows[0],))
    )
    result = await _run(repository)
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "DAILY_CURVE_DUPLICATE_KEY"


@pytest.mark.unit
async def test_incomplete_calendar_series_fails_closed() -> None:
    task8, task9 = _sources()
    repository = FixtureRepository(task8, replace(task9, member_rows=task9.member_rows[1:]))
    result = await _run(repository)
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "DAILY_CURVE_INCOMPLETE_SERIES"


@pytest.mark.unit
async def test_cross_day_inventory_break_fails_closed() -> None:
    task8, task9 = _sources()
    members = list(task9.member_rows)
    target = next(index for index, row in enumerate(members) if row.state_date == date(2026, 3, 2))
    members[target] = replace(members[target], opening_mature_inventory_kg=Decimal("999.000"))
    result = await _run(FixtureRepository(task8, replace(task9, member_rows=tuple(members))))
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "DAILY_CURVE_STATE_INVARIANT_FAILED"


@pytest.mark.unit
async def test_state_equation_break_fails_closed() -> None:
    task8, task9 = _sources()
    members = list(task9.member_rows)
    target = next(index for index, row in enumerate(members) if row.harvested_quantity_kg > 0)
    members[target] = replace(members[target], closing_mature_inventory_kg=Decimal("999.000"))
    result = await _run(FixtureRepository(task8, replace(task9, member_rows=tuple(members))))
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "DAILY_CURVE_STATE_INVARIANT_FAILED"


@pytest.mark.unit
async def test_null_subfarm_id_fails_closed() -> None:
    task8, task9 = _sources()
    members = list(task9.member_rows)
    members[0] = replace(members[0], subfarm_id=None)
    result = await _run(FixtureRepository(task8, replace(task9, member_rows=tuple(members))))
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "AUTHORITY_SCOPE_MISMATCH"


@pytest.mark.unit
async def test_extra_scope_or_quantile_fails_closed() -> None:
    task8, task9 = _sources()
    extra = replace(task9.member_rows[0], farm_id=999)
    result = await _run(
        FixtureRepository(task8, replace(task9, member_rows=task9.member_rows + (extra,)))
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "AUTHORITY_SCOPE_MISMATCH"
