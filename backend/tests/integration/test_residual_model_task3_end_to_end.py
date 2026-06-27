"""Section 4: End-to-end integration test for residual model via real Task 3 builder.

Flow: raw receipt rows -> build_daily_facts_for_season(...) -> completed
AnalyticsBuildRun -> Task 10 manifest -> residual training -> save training
run -> save artifacts -> reload training run.

This test uses PostgreSQL only and does NOT use _seed_build_run() for the
formal Task 3 builder; all AnalyticsBuildRun records go through the real
build_daily_facts_for_season pipeline.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.app.analytics.config import load_analytics_config
from backend.app.analytics.daily_facts import build_daily_facts_for_season
from backend.app.db.session import AsyncSessionMaker
from backend.app.models.analytics import (
    AnalyticsBuildRun,
    FactorySeasonPeakMetric,
)
from backend.app.models.master_data import Factory
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelTrainingRun,
)
from backend.app.residual_model.application import execute_residual_training
from backend.app.residual_model.persistence import (
    load_residual_training_run_by_id,
    training_result_json_payload,
)
from backend.app.residual_model.schemas import ResidualTrainingSampleSpec
from backend.app.residual_model.training_manifest import (
    build_residual_training_manifest,
)
from backend.tests.residual_model.support import repo_root
from backend.tests.residual_model.test_training_manifest import (
    _config,
    _create_ingest_file,
    _diverse_training_samples,
    _insert_raw_rows,
    _persist_task9_run,
    _seed_master_data,
    _seed_season,
    _snapshot_as_of_date,
    _supplemental_features,
)

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _relaxed_config():
    config = _config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
    )
    rules = replace(config.rules, eligibility=eligibility)
    return replace(config, rules=rules)


@pytest.mark.integration
async def test_real_task3_build_residual_model_end_to_end() -> None:
    """End-to-end: raw rows -> Task 3 build -> manifest -> training -> save
    -> reload with 16 verification assertions."""
    _require_postgres()

    async with AsyncSessionMaker() as session:
        # ------------------------------------------------------------------
        # 1. Seed master data
        # ------------------------------------------------------------------
        season_id, factory_id, variety_id = await _seed_master_data(session)

        # Second season + factory for the "uncovered" exclusion test.
        await _seed_season(
            session,
            season_id=2,
            code="2026-2027",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )
        factory_2 = Factory(
            id=702,
            code="factory-b",
            name="Factory B",
            region_name="south",
            active=True,
        )
        session.add(factory_2)
        await session.flush()

        analytics_config = load_analytics_config(
            repo_root() / "configs" / "analytics_rules.yaml"
        )

        # ------------------------------------------------------------------
        # 2. Feature build — raw rows inserted first
        #    Data: Jan 10 (5), Feb 21 (17), Feb 25 multi-farm (10+13=23),
        #          Feb 27 (11).
        # ------------------------------------------------------------------
        feature_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=1,
            season_id=season_id,
            file_sha256="feature-build",
        )
        await _insert_raw_rows(
            session,
            ingest_file_id=feature_ingest_id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            rows=[
                {
                    "receipt_date": date(2026, 1, 10),
                    "weight_kg": Decimal("5"),
                    "farm_raw": "farm-a",
                    "subfarm_raw": "subfarm-a",
                },
                {
                    "receipt_date": date(2026, 2, 21),
                    "weight_kg": Decimal("17"),
                    "farm_raw": "farm-a",
                    "subfarm_raw": "subfarm-a",
                },
                {
                    "receipt_date": date(2026, 2, 25),
                    "weight_kg": Decimal("10"),
                    "farm_raw": "farm-b",
                    "subfarm_raw": "subfarm-b",
                },
                {
                    "receipt_date": date(2026, 2, 25),
                    "weight_kg": Decimal("13"),
                    "farm_raw": "farm-c",
                    "subfarm_raw": "subfarm-c",
                },
                {
                    "receipt_date": date(2026, 2, 27),
                    "weight_kg": Decimal("11"),
                    "farm_raw": "farm-a",
                    "subfarm_raw": "subfarm-d",
                },
            ],
        )
        await session.commit()

        feature_build = await build_daily_facts_for_season(
            session, "2025-2026", analytics_config,
        )

        # ------------------------------------------------------------------
        # 3. Label build — second ingest, second build (different source
        #    max raw id so a new AnalyticsBuildRun is created).
        # ------------------------------------------------------------------
        label_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=2,
            season_id=season_id,
            file_sha256="label-build",
        )
        await _insert_raw_rows(
            session,
            ingest_file_id=label_ingest_id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            rows=[
                {
                    "receipt_date": date(2026, 3, 1),
                    "weight_kg": Decimal("100"),
                    "farm_raw": "farm-a",
                    "subfarm_raw": "subfarm-a",
                },
                {
                    "receipt_date": date(2026, 3, 2),
                    "weight_kg": Decimal("101"),
                    "farm_raw": "farm-b",
                    "subfarm_raw": "subfarm-b",
                },
                {
                    "receipt_date": date(2026, 3, 3),
                    "weight_kg": Decimal("102"),
                    "farm_raw": "farm-c",
                    "subfarm_raw": "subfarm-c",
                },
            ],
        )
        await session.commit()

        label_build = await build_daily_facts_for_season(
            session, "2025-2026", analytics_config,
        )

        # ------------------------------------------------------------------
        # 4. Task 9 — harvest-state run
        # ------------------------------------------------------------------
        task9_run_id, output = await _persist_task9_run(session)
        as_of_date = _snapshot_as_of_date(output)  # 2026-02-28

        # ------------------------------------------------------------------
        # 5. Uncovered feature build (season 2, factory 702 only) for
        #    the exclusion assertion.
        # ------------------------------------------------------------------
        uncovered_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=3,
            season_id=2,
            file_sha256="uncovered-build",
        )
        await _insert_raw_rows(
            session,
            ingest_file_id=uncovered_ingest_id,
            season_id=2,
            factory_id=factory_2.id,
            variety_id=variety_id,
            rows=[
                {
                    "receipt_date": date(2026, 1, 15),
                    "weight_kg": Decimal("50"),
                    "farm_raw": "farm-x",
                    "subfarm_raw": "subfarm-x",
                },
            ],
        )
        await session.commit()

        uncovered_feature_build = await build_daily_facts_for_season(
            session, "2026-2027", analytics_config,
        )

        # ------------------------------------------------------------------
        # ----  ASSERTS 1-5: Task 3 build characteristics  -----------------
        # ------------------------------------------------------------------
        # 1. Task 3 build status is completed
        assert feature_build.status == "completed", (
            f"Expected feature build status 'completed', got {feature_build.status!r}"
        )
        assert label_build.status == "completed", (
            f"Expected label build status 'completed', got {label_build.status!r}"
        )

        # 2. label build and feature build IDs are set
        assert feature_build.build_run_id is not None, "Feature build_run_id must be set"
        assert label_build.build_run_id is not None, "Label build_run_id must be set"

        # 3. source cutoff is set
        feature_row = await session.get(AnalyticsBuildRun, feature_build.build_run_id)
        assert feature_row is not None
        assert feature_row.source_max_raw_id > 0, (
            f"Feature build source_max_raw_id should be >0, got {feature_row.source_max_raw_id}"
        )
        label_row = await session.get(AnalyticsBuildRun, label_build.build_run_id)
        assert label_row is not None
        assert label_row.source_max_raw_id > 0, (
            f"Label build source_max_raw_id should be >0, got {label_row.source_max_raw_id}"
        )

        # 4. analysis months / calendar correct
        #    Season 2025-2026: Jan 1 – Mar 31, analysis_months = [1, 2, 3, 4]
        #    Expect analysis_start_date = 2026-01-01, analysis_end_date = 2026-03-31
        feature_peak_metrics = (
            await session.scalars(
                select(FactorySeasonPeakMetric).where(
                    FactorySeasonPeakMetric.build_run_id == feature_build.build_run_id
                )
            )
        ).all()
        assert len(feature_peak_metrics) == 1, "Expected 1 factory peak metric for feature build"
        fpm = feature_peak_metrics[0]
        assert fpm.analysis_start_date == date(2026, 1, 1), (
            f"Expected analysis_start_date 2026-01-01, got {fpm.analysis_start_date}"
        )
        assert fpm.analysis_end_date == date(2026, 3, 31), (
            f"Expected analysis_end_date 2026-03-31, got {fpm.analysis_end_date}"
        )
        # Calendar days: Jan (31) + Feb (28) + Mar (31) = 90
        assert fpm.calendar_day_count == 90, (
            f"Expected 90 calendar days, got {fpm.calendar_day_count}"
        )

        # 5. factory coverage correct
        assert fpm.factory_id == factory_id, (
            f"Expected factory_id {factory_id}, got {fpm.factory_id}"
        )

        # ------------------------------------------------------------------
        # ----  ASSERTS 6-12: Manifest row feature correctness  ------------
        # ------------------------------------------------------------------
        # Build covered manifest (main path)
        covered_manifest_rows = await build_residual_training_manifest(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=task9_run_id,
                    label_analytics_build_run_id=label_build.build_run_id,
                    feature_analytics_build_run_id=feature_build.build_run_id,
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=as_of_date,
                        destination_factory_category="snapshot-north",
                    ),
                )
            ],
        )
        assert covered_manifest_rows, "Covered manifest must not be empty"
        first_row = covered_manifest_rows[0]
        feature_map = {
            item.feature_name: item.value for item in first_row.feature_values
        }

        # 6. Multi-farm/subfarm/variety same-day data deterministic SUM
        #    Feb 25 has 10 kg (farm-b) + 13 kg (farm-c) = 23 kg
        assert feature_map["actual_receipt_lag_3d_kg"] == Decimal("23"), (
            f"Expected lag_3d=23, got {feature_map['actual_receipt_lag_3d_kg']}"
        )

        # 7. Covered missing date = real zero
        #    Feb 26 (as_of - 2) has no data but factory is covered → zero
        #    The rolling 3d includes Feb 26 as zero → (23+0+11)/3 = 11.333...
        expected_roll_3d = Decimal("34") / Decimal("3")
        assert (
            feature_map["actual_receipt_rolling_3d_mean_kg"] == expected_roll_3d
        ), (
            f"Expected rolling_3d={expected_roll_3d}, "
            f"got {feature_map['actual_receipt_rolling_3d_mean_kg']}"
        )

        # 8. Uncovered date = excluded
        uncovered_manifest_rows = await build_residual_training_manifest(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=task9_run_id,
                    label_analytics_build_run_id=label_build.build_run_id,
                    feature_analytics_build_run_id=uncovered_feature_build.build_run_id,
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=as_of_date,
                    ),
                )
            ],
        )
        assert uncovered_manifest_rows, "Uncovered manifest must not be empty"
        assert all(
            row.include is False for row in uncovered_manifest_rows
        ), "Every uncovered row must be excluded"
        assert all(
            row.exclusion_reason == "factory_missing_from_build_run"
            for row in uncovered_manifest_rows
        ), "Exclusion reason must be factory_missing_from_build_run"

        # 9. Lag 1/3/7
        #    as_of_date = Feb 28 → lag-1 = Feb 27 (11), lag-3 = Feb 25 (23),
        #    lag-7 = Feb 21 (17)
        assert feature_map["actual_receipt_lag_1d_kg"] == Decimal("11"), (
            f"Expected lag_1d=11, got {feature_map['actual_receipt_lag_1d_kg']}"
        )
        assert feature_map["actual_receipt_lag_3d_kg"] == Decimal("23"), (
            f"Expected lag_3d=23, got {feature_map['actual_receipt_lag_3d_kg']}"
        )
        assert feature_map["actual_receipt_lag_7d_kg"] == Decimal("17"), (
            f"Expected lag_7d=17, got {feature_map['actual_receipt_lag_7d_kg']}"
        )

        # 10. Rolling 3/7
        expected_roll_7d = Decimal("51") / Decimal("7")
        assert (
            feature_map["actual_receipt_rolling_3d_mean_kg"] == expected_roll_3d
        ), (
            f"Expected rolling_3d={expected_roll_3d}, "
            f"got {feature_map['actual_receipt_rolling_3d_mean_kg']}"
        )
        assert (
            feature_map["actual_receipt_rolling_7d_mean_kg"] == expected_roll_7d
        ), (
            f"Expected rolling_7d={expected_roll_7d}, "
            f"got {feature_map['actual_receipt_rolling_7d_mean_kg']}"
        )

        # 11. Cumulative through "as_of - 1"
        #     All feature data before Feb 28 = 5 + 17 + 10 + 13 + 11 = 56
        assert feature_map["actual_receipt_cumulative_to_as_of_kg"] == Decimal("56"), (
            f"Expected cumulative=56, "
            f"got {feature_map['actual_receipt_cumulative_to_as_of_kg']}"
        )

        # 12. Manifest ordering — rows ordered by (factory_id, date)
        row_dates = [
            (r.factory_id, r.arrival_local_date) for r in covered_manifest_rows
        ]
        assert row_dates == sorted(row_dates), (
            f"Manifest rows must be ordered by (factory_id, date): {row_dates}"
        )

        # 13. Manifest hash — each row has a non-empty hash
        for row in covered_manifest_rows:
            assert row.manifest_row_hash, "Manifest row hash must not be empty"
        manifest_hashes = {row.manifest_row_hash for row in covered_manifest_rows}
        assert len(manifest_hashes) == len(covered_manifest_rows), (
            "Manifest row hashes must be unique"
        )

        # ------------------------------------------------------------------
        # ----  ASSERTS 14-16: Training execution and persistence  ---------
        # ------------------------------------------------------------------
        training_samples = _diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build.build_run_id,
            feature_build_run_id=feature_build.build_run_id,
            as_of_date=as_of_date,
        )

        training_result, training_run_id = await execute_residual_training(
            session,
            samples=training_samples,
            config=_relaxed_config(),
        )

        # 14. Training signature
        assert training_result.training_signature, (
            "Training signature must not be empty"
        )
        assert training_result.execution_status == "completed", (
            f"Expected training completed, got {training_result.execution_status}"
        )

        # 15. Persistence / reload parity
        loaded = await load_residual_training_run_by_id(
            session, run_id=training_run_id,
        )
        assert loaded is not None, "Must be able to reload training run"
        assert training_result_json_payload(loaded) == (
            training_result_json_payload(training_result)
        ), "Reloaded payload must match original"
        assert loaded.training_signature == training_result.training_signature, (
            "Reloaded training signature must match"
        )

        # 16. Artifact count is 3 (P50, P80, P90)
        assert await session.scalar(
            select(func.count()).select_from(ResidualModelTrainingRun)
        ) == 1, "Expected exactly 1 training run"
        assert await session.scalar(
            select(func.count()).select_from(ResidualModelArtifact)
        ) == 3, "Expected exactly 3 artifacts (P50, P80, P90)"
