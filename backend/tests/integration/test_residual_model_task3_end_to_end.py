"""Section 4: End-to-end integration test for residual model via real Task 3 builder.

Flow: raw receipt rows -> build_daily_facts_for_season(...) -> completed
AnalyticsBuildRun -> Task 10 manifest -> residual training -> save training
run -> save artifacts -> reload training run.

This test uses PostgreSQL only and does NOT use _seed_build_run() for the
formal Task 3 builder; all AnalyticsBuildRun records go through the real
build_daily_facts_for_season pipeline.

Key properties verified:
  - Train/validation are DISJOINT seasons (different season_id, different code)
  - All validation IDs are explicitly created and passed (no magic defaults)
  - Real build_daily_facts_for_season() for ALL builds
  - Correct field names: destination_factory_id, target_arrival_local_date
  - Config freezes: require_improvement_over_structural=False,
    max_validation_wmape=Decimal("100"), max_fallback_rate=Decimal("1")
  - Full pipeline: feature correctness, manifest construction, training,
    persistence, reload parity
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, date, datetime
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
    ResidualModelManifestRow,
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
from backend.tests.harvest_state.conftest import make_request
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
    """Relax eligibility rules so small test data always passes.

    ALSO freezes:
      - require_improvement_over_structural=False (no hard improve check)
      - max_validation_wmape=Decimal("100")   (effectively unlimited)
      - max_fallback_rate=Decimal("1")        (allow 100% fallback)
    """
    config = _config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
        require_improvement_over_structural=False,
        max_validation_wmape=Decimal("100"),
        max_fallback_rate=Decimal("1"),
    )
    rules = replace(config.rules, eligibility=eligibility)
    return replace(config, rules=rules)


async def _set_build_available_at(
    session: AsyncSessionMaker,
    *,
    build_run_id: int,
    available_at: datetime,
) -> None:
    build = await session.get(AnalyticsBuildRun, build_run_id)
    assert build is not None
    build.started_at = available_at
    build.finished_at = available_at
    await session.commit()


@pytest.mark.integration
async def test_real_task3_build_residual_model_end_to_end() -> None:
    """End-to-end: raw rows -> real Task 3 builds -> manifest -> training
    -> save -> reload with comprehensive verification.

    TRAIN season:   id=1, code="2025-2026"
    VALIDATION season: id=3, code="2025-2026-val"  (disjoint ID + code)
    All four Task 3 builds go through real build_daily_facts_for_season().
    Both train and validation Task 9 runs are created via _persist_task9_run
    with explicit payloads.
    """
    _require_postgres()

    async with AsyncSessionMaker() as session:
        feature_available_at = datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
        label_available_at = datetime(2026, 3, 20, 12, 0, tzinfo=UTC)

        # ------------------------------------------------------------------
        # 1. Seed master data — train season + validation season
        # ------------------------------------------------------------------
        season_id, factory_id, variety_id = await _seed_master_data(session)
        secondary_factory = Factory(
            id=702,
            code="factory-b",
            name="Factory B",
            region_name="south",
            active=True,
        )
        session.add(secondary_factory)
        await session.flush()
        # season_id = 1, code = "2025-2026"

        # Validation season: different season_id AND different code (disjoint)
        validation_season_id = await _seed_season(
            session,
            season_id=3,
            code="2025-2026-val",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        analytics_config = load_analytics_config(repo_root() / "configs" / "analytics_rules.yaml")

        # ------------------------------------------------------------------
        # 2. TRAIN SEASON — Limited feature build for a different factory.
        #    This creates a real frozen coverage snapshot that excludes the
        #    Task 9 destination factory, without relying on sparse-fact myths.
        # ------------------------------------------------------------------
        limited_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=1,
            season_id=season_id,
            file_sha256="limited-feature-build",
        )
        await _insert_raw_rows(
            session,
            ingest_file_id=limited_ingest_id,
            season_id=season_id,
            factory_id=secondary_factory.id,
            variety_id=variety_id,
            rows=[
                {
                    "receipt_date": date(2026, 1, 10),
                    "weight_kg": Decimal("5"),
                    "farm_raw": "farm-a",
                    "subfarm_raw": "subfarm-a",
                },
            ],
        )
        await session.commit()

        limited_feature_build = await build_daily_facts_for_season(
            session,
            "2025-2026",
            analytics_config,
        )
        assert limited_feature_build.status == "completed", (
            f"Limited feature build expected 'completed', got {limited_feature_build.status!r}"
        )
        limited_feature_build_run_id = limited_feature_build.build_run_id
        assert limited_feature_build_run_id is not None
        await _set_build_available_at(
            session,
            build_run_id=limited_feature_build_run_id,
            available_at=feature_available_at,
        )

        # ------------------------------------------------------------------
        # 3. TRAIN SEASON — Main feature build (covers Jan+Feb data)
        #    Insert additional Feb rows before building again;
        #    higher source_max_raw_id creates a new build run.
        # ------------------------------------------------------------------
        main_feature_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=2,
            season_id=season_id,
            file_sha256="main-feature-build",
        )
        await _insert_raw_rows(
            session,
            ingest_file_id=main_feature_ingest_id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            rows=[
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

        main_feature_build = await build_daily_facts_for_season(
            session,
            "2025-2026",
            analytics_config,
        )
        assert main_feature_build.status == "completed", (
            f"Main feature build expected 'completed', got {main_feature_build.status!r}"
        )
        main_feature_build_run_id = main_feature_build.build_run_id
        assert main_feature_build_run_id is not None
        await _set_build_available_at(
            session,
            build_run_id=main_feature_build_run_id,
            available_at=feature_available_at,
        )

        # ------------------------------------------------------------------
        # 4. TRAIN SEASON — Label build (covers Jan+Feb+Mar data)
        # ------------------------------------------------------------------
        label_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=3,
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
            session,
            "2025-2026",
            analytics_config,
        )
        assert label_build.status == "completed", (
            f"Label build expected 'completed', got {label_build.status!r}"
        )
        label_build_run_id = label_build.build_run_id
        assert label_build_run_id is not None
        await _set_build_available_at(
            session,
            build_run_id=label_build_run_id,
            available_at=label_available_at,
        )

        # ------------------------------------------------------------------
        # 5. TRAIN Task 9 — harvest-state run (standard make_request)
        # ------------------------------------------------------------------
        task9_run_id, output = await _persist_task9_run(session)
        as_of_date = _snapshot_as_of_date(output)  # 2026-02-28

        # ------------------------------------------------------------------
        # 6. VALIDATION SEASON — Feature build
        # ------------------------------------------------------------------
        val_feature_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=4,
            season_id=validation_season_id,
            file_sha256="val-feature-build",
        )
        await _insert_raw_rows(
            session,
            ingest_file_id=val_feature_ingest_id,
            season_id=validation_season_id,
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

        val_feature_build = await build_daily_facts_for_season(
            session,
            "2025-2026-val",
            analytics_config,
        )
        assert val_feature_build.status == "completed", (
            f"Validation feature build expected 'completed', got {val_feature_build.status!r}"
        )
        val_feature_build_run_id = val_feature_build.build_run_id
        assert val_feature_build_run_id is not None
        await _set_build_available_at(
            session,
            build_run_id=val_feature_build_run_id,
            available_at=feature_available_at,
        )

        # ------------------------------------------------------------------
        # 7. VALIDATION SEASON — Label build
        # ------------------------------------------------------------------
        val_label_ingest_id = await _create_ingest_file(
            session,
            ingest_file_id=5,
            season_id=validation_season_id,
            file_sha256="val-label-build",
        )
        await _insert_raw_rows(
            session,
            ingest_file_id=val_label_ingest_id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            rows=[
                {
                    "receipt_date": date(2026, 3, 1),
                    "weight_kg": Decimal("200"),
                    "farm_raw": "farm-a",
                    "subfarm_raw": "subfarm-a",
                },
                {
                    "receipt_date": date(2026, 3, 2),
                    "weight_kg": Decimal("201"),
                    "farm_raw": "farm-b",
                    "subfarm_raw": "subfarm-b",
                },
                {
                    "receipt_date": date(2026, 3, 3),
                    "weight_kg": Decimal("202"),
                    "farm_raw": "farm-c",
                    "subfarm_raw": "subfarm-c",
                },
            ],
        )
        await session.commit()

        val_label_build = await build_daily_facts_for_season(
            session,
            "2025-2026-val",
            analytics_config,
        )
        assert val_label_build.status == "completed", (
            f"Validation label build expected 'completed', got {val_label_build.status!r}"
        )
        val_label_build_run_id = val_label_build.build_run_id
        assert val_label_build_run_id is not None
        await _set_build_available_at(
            session,
            build_run_id=val_label_build_run_id,
            available_at=label_available_at,
        )

        # ------------------------------------------------------------------
        # 8. VALIDATION Task 9 — customized payload for disjoint season
        # ------------------------------------------------------------------
        validation_payload = make_request()
        # Tweak payload so that the two Task 9 runs produce different outputs
        validation_payload["initial_inventory_cohorts"][0] = {
            **validation_payload["initial_inventory_cohorts"][0],
            "remaining_quantity_kg": Decimal("6"),
        }
        validation_payload["initial_opening_mature_inventory_kg"] = Decimal("31")

        val_task9_run_id, val_output = await _persist_task9_run(
            session,
            payload=validation_payload,
        )
        assert val_output.status == "completed"

        # ================================================================
        # ----  SECTION A: Task 3 build characteristics  ----
        # ================================================================

        # A1. All builds are completed
        for label, build_result in [
            ("limited_feature", limited_feature_build),
            ("main_feature", main_feature_build),
            ("label", label_build),
            ("val_feature", val_feature_build),
            ("val_label", val_label_build),
        ]:
            assert build_result.status == "completed", (
                f"{label} build expected 'completed', got {build_result.status!r}"
            )

        # A2. All build_run_ids are set and different
        all_build_ids = [
            limited_feature_build_run_id,
            main_feature_build_run_id,
            label_build_run_id,
            val_feature_build_run_id,
            val_label_build_run_id,
        ]
        assert len(set(all_build_ids)) == 5, f"Expected 5 unique build_run_ids, got {all_build_ids}"

        # A3. Train builds belong to train season; validation builds to
        #     validation season (disjoint season verification)
        train_build_ids = [
            limited_feature_build_run_id,
            main_feature_build_run_id,
            label_build_run_id,
        ]
        for build_run_id in train_build_ids:
            row = await session.get(AnalyticsBuildRun, build_run_id)
            assert row is not None
            assert row.season_id == season_id, (
                f"Train build {build_run_id} has season_id {row.season_id}, expected {season_id}"
            )
        for build_run_id in [val_feature_build_run_id, val_label_build_run_id]:
            row = await session.get(AnalyticsBuildRun, build_run_id)
            assert row is not None
            assert row.season_id == validation_season_id, (
                f"Validation build {build_run_id} has season_id {row.season_id}, "
                f"expected {validation_season_id}"
            )

        # A4. source_max_raw_id > 0 for all builds
        for build_run_id in all_build_ids:
            row = await session.get(AnalyticsBuildRun, build_run_id)
            assert row is not None
            assert row.source_max_raw_id > 0, (
                f"Build {build_run_id} source_max_raw_id should be >0, got {row.source_max_raw_id}"
            )

        # A5. aggregation_version is 'task3-v1'
        for build_run_id in all_build_ids:
            row = await session.get(AnalyticsBuildRun, build_run_id)
            assert row is not None
            assert row.aggregation_version == "task3-v1", (
                f"Build {build_run_id} aggregation_version should be 'task3-v1', "
                f"got {row.aggregation_version!r}"
            )

        as_of_cutoff = datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC)
        for build_run_id in (
            limited_feature_build_run_id,
            main_feature_build_run_id,
            val_feature_build_run_id,
        ):
            build = await session.get(AnalyticsBuildRun, build_run_id)
            assert build is not None
            assert build.finished_at is not None
            assert build.finished_at <= as_of_cutoff, (
                f"Feature build {build_run_id} finished_at {build.finished_at} "
                f"must be <= {as_of_cutoff}"
            )

        # A6. Factory coverage sets
        limited_metrics = (
            await session.scalars(
                select(FactorySeasonPeakMetric).where(
                    FactorySeasonPeakMetric.build_run_id == limited_feature_build_run_id
                )
            )
        ).all()
        main_metrics = (
            await session.scalars(
                select(FactorySeasonPeakMetric).where(
                    FactorySeasonPeakMetric.build_run_id == main_feature_build_run_id
                )
            )
        ).all()
        limited_factory_ids = {row.factory_id for row in limited_metrics}
        main_factory_ids = {row.factory_id for row in main_metrics}
        assert limited_factory_ids == {secondary_factory.id}, (
            f"Expected limited build factories {{{secondary_factory.id}}}, "
            f"got {limited_factory_ids}"
        )
        assert main_factory_ids == {factory_id, secondary_factory.id}, (
            f"Expected main build factories {{{factory_id}, {secondary_factory.id}}}, "
            f"got {main_factory_ids}"
        )
        assert factory_id not in limited_factory_ids
        assert factory_id in main_factory_ids
        fpm = next(row for row in main_metrics if row.factory_id == factory_id)
        assert fpm.factory_id == factory_id
        assert fpm.analysis_start_date == date(2026, 1, 1), (
            f"Expected analysis_start_date 2026-01-01, got {fpm.analysis_start_date}"
        )
        assert fpm.analysis_end_date is not None
        assert fpm.calendar_day_count > 0

        # ================================================================
        # ----  SECTION B: Manifest row feature correctness  ----
        # ================================================================

        # Build covered manifest (main path)
        covered_manifest_rows = await build_residual_training_manifest(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=task9_run_id,
                    label_analytics_build_run_id=label_build_run_id,
                    feature_analytics_build_run_id=main_feature_build_run_id,
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

        # B1. Correct field names: destination_factory_id
        assert first_row.destination_factory_id == factory_id, (
            f"Expected destination_factory_id={factory_id}, got {first_row.destination_factory_id}"
        )
        # B1b. Correct field names: target_arrival_local_date
        assert first_row.target_arrival_local_date is not None

        feature_map = {item.feature_name: item.value for item in first_row.feature_values}

        # B2. Multi-farm/subfarm same-day data deterministic SUM
        #     Feb 25 has 10 kg (farm-b) + 13 kg (farm-c) = 23 kg
        assert feature_map["actual_receipt_lag_3d_kg"] == Decimal("23"), (
            f"Expected lag_3d=23, got {feature_map['actual_receipt_lag_3d_kg']}"
        )

        # B3. Covered missing date = real zero
        #     Feb 26 (as_of - 2) has no data but factory is covered → zero
        #     The rolling 3d includes Feb 26 as zero → (23+0+11)/3 = 34/3
        expected_roll_3d = Decimal("34") / Decimal("3")
        assert feature_map["actual_receipt_rolling_3d_mean_kg"] == expected_roll_3d, (
            f"Expected rolling_3d={expected_roll_3d}, "
            f"got {feature_map['actual_receipt_rolling_3d_mean_kg']}"
        )

        # B4. Frozen coverage exclusion = excluded (using limited feature build
        #     that does not cover the Task 9 destination factory).
        uncovered_manifest_rows = await build_residual_training_manifest(
            session,
            samples=[
                ResidualTrainingSampleSpec(
                    task9_run_id=task9_run_id,
                    label_analytics_build_run_id=label_build_run_id,
                    feature_analytics_build_run_id=limited_feature_build_run_id,
                    split="train",
                    supplemental_feature_values=_supplemental_features(
                        as_of_date=as_of_date,
                    ),
                )
            ],
        )
        assert uncovered_manifest_rows, "Uncovered manifest must not be empty"
        assert all(row.include is False for row in uncovered_manifest_rows), (
            "Every uncovered row must be excluded"
        )
        assert all(
            row.exclusion_reason == "factory_missing_from_build_run"
            for row in uncovered_manifest_rows
        ), (
            "Exclusion reason must be factory_missing_from_build_run, "
            f"got {set(r.exclusion_reason for r in uncovered_manifest_rows)}"
        )

        # B5. Lag 1/3/7
        #     as_of_date = Feb 28 → lag-1 = Feb 27 (11), lag-3 = Feb 25 (23),
        #     lag-7 = Feb 21 (17)
        assert feature_map["actual_receipt_lag_1d_kg"] == Decimal("11"), (
            f"Expected lag_1d=11, got {feature_map['actual_receipt_lag_1d_kg']}"
        )
        assert feature_map["actual_receipt_lag_3d_kg"] == Decimal("23"), (
            f"Expected lag_3d=23, got {feature_map['actual_receipt_lag_3d_kg']}"
        )
        assert feature_map["actual_receipt_lag_7d_kg"] == Decimal("17"), (
            f"Expected lag_7d=17, got {feature_map['actual_receipt_lag_7d_kg']}"
        )

        # B6. Rolling 3/7
        expected_roll_7d = Decimal("51") / Decimal("7")
        assert feature_map["actual_receipt_rolling_3d_mean_kg"] == expected_roll_3d, (
            f"Expected rolling_3d={expected_roll_3d}, "
            f"got {feature_map['actual_receipt_rolling_3d_mean_kg']}"
        )
        assert feature_map["actual_receipt_rolling_7d_mean_kg"] == expected_roll_7d, (
            f"Expected rolling_7d={expected_roll_7d}, "
            f"got {feature_map['actual_receipt_rolling_7d_mean_kg']}"
        )

        # B7. Cumulative through "as_of - 1"
        #     Primary destination factory data before Feb 28 = 17 + 10 + 13 + 11 = 51
        #     The secondary factory's 5 kg is excluded from this cumulative feature.
        assert feature_map["actual_receipt_cumulative_to_as_of_kg"] == Decimal("51"), (
            f"Expected cumulative=51, got {feature_map['actual_receipt_cumulative_to_as_of_kg']}"
        )

        # B8. Manifest ordering — rows ordered by
        #     (destination_factory_id, target_arrival_local_date,
        #      task9_run_id, split)
        row_keys = [
            (
                r.destination_factory_id,
                r.target_arrival_local_date,
                r.task9_run_id,
                r.split.value,
            )
            for r in covered_manifest_rows
        ]
        assert row_keys == sorted(row_keys), (
            f"Manifest rows must be ordered by "
            f"(destination_factory_id, target_arrival_local_date, "
            f"task9_run_id, split): {row_keys}"
        )

        # B9. Per-row feature_vector_hash is non-empty and unique
        for row in covered_manifest_rows:
            assert row.feature_vector_hash, (
                f"Row feature_vector_hash must not be empty for "
                f"destination_factory_id={row.destination_factory_id}, "
                f"date={row.target_arrival_local_date}"
            )
        row_hashes = {row.feature_vector_hash for row in covered_manifest_rows}
        assert len(row_hashes) == len(covered_manifest_rows), (
            "Each manifest row must have a unique feature_vector_hash"
        )

        # ================================================================
        # ----  SECTION C: Training execution and persistence  ----
        # ================================================================

        # C1. Build diverse training samples including validation split
        training_samples = _diverse_training_samples(
            task9_run_id=task9_run_id,
            label_build_run_id=label_build_run_id,
            feature_build_run_id=main_feature_build_run_id,
            validation_task9_run_id=val_task9_run_id,
            validation_label_build_run_id=val_label_build_run_id,
            validation_feature_build_run_id=val_feature_build_run_id,
            as_of_date=as_of_date,
        )

        # C1a. Rebuild manifest for disjoint season verification
        manifest_for_verification = await build_residual_training_manifest(
            session,
            samples=training_samples,
        )
        train_seasons = {
            row.season_id
            for row in manifest_for_verification
            if row.include and row.split == "train"
        }
        validation_seasons = {
            row.season_id
            for row in manifest_for_verification
            if row.include and row.split == "validation"
        }
        assert train_seasons, "Must have at least one train season"
        assert validation_seasons, "Must have at least one validation season"
        assert train_seasons.isdisjoint(validation_seasons), (
            f"Train seasons {train_seasons} and validation seasons "
            f"{validation_seasons} must be disjoint"
        )
        assert len(train_seasons) == 1, f"Expected exactly 1 train season, got {len(train_seasons)}"
        assert len(validation_seasons) == 1, (
            f"Expected exactly 1 validation season, got {len(validation_seasons)}"
        )
        included_rows = [row for row in manifest_for_verification if row.include]
        assert included_rows, "Expected at least one included manifest row"
        assert all(
            row.feature_visibility_audit is not None
            and row.feature_visibility_audit.status.value == "completed"
            for row in included_rows
        ), {
            row.feature_visibility_audit.audit_hash: [
                issue.code.value for issue in row.feature_visibility_audit.blockers
            ]
            for row in included_rows
            if row.feature_visibility_audit is not None
            and row.feature_visibility_audit.status.value != "completed"
        }

        training_result, training_run_id = await execute_residual_training(
            session,
            samples=training_samples,
            config=_relaxed_config(),
        )

        # C2. Training signature is set
        assert training_result.training_signature, "Training signature must not be empty"

        # C3. Execution completed
        assert training_result.execution_status == "completed", (
            f"Expected training completed, got {training_result.execution_status}"
        )

        # C4. Eligibility is eligible (relaxed config)
        assert training_result.eligibility_status == "eligible", (
            f"Expected eligibility 'eligible', "
            f"got {training_result.eligibility_status}, "
            f"reasons={training_result.eligibility_reasons}"
        )

        # C5. Manifest hash is set
        assert training_result.manifest_hash, "Manifest hash must not be empty"

        # C6. Distinct seasons = 1 (train rows only, validation is excluded
        #     from training distinct_season_count)
        assert training_result.distinct_season_count == 1, (
            f"Expected 1 distinct season (train only), got {training_result.distinct_season_count}"
        )

        # C7. Distinct factories >= 1
        assert training_result.distinct_factory_count >= 1, (
            f"Expected at least 1 factory, got {training_result.distinct_factory_count}"
        )

        # C8. Persistence / reload parity
        loaded = await load_residual_training_run_by_id(
            session,
            run_id=training_run_id,
        )
        assert loaded is not None, "Must be able to reload training run"
        assert training_result_json_payload(loaded) == (
            training_result_json_payload(training_result)
        ), "Reloaded payload must match original"
        assert loaded.training_signature == training_result.training_signature, (
            "Reloaded training signature must match"
        )
        assert loaded.manifest_hash == training_result.manifest_hash, (
            "Reloaded manifest hash must match"
        )

        # C9. Artifact count = 3 (P50, P80, P90)
        assert (
            await session.scalar(select(func.count()).select_from(ResidualModelTrainingRun)) == 1
        ), "Expected exactly 1 training run"
        assert await session.scalar(select(func.count()).select_from(ResidualModelArtifact)) == 3, (
            "Expected exactly 3 artifacts (P50, P80, P90)"
        )

        # C10. Manifest rows stored in DB
        manifest_db_count = await session.scalar(
            select(func.count()).select_from(ResidualModelManifestRow)
        )
        assert manifest_db_count is not None
        assert manifest_db_count > 0, "Expected at least 1 manifest row in the database"

        # C11. Explicit validation: training and validation use DIFFERENT
        #      task9_run_id and DIFFERENT build_run_ids
        train_sample = training_samples[0]
        val_samples = [s for s in training_samples if s.split.value == "validation"]
        assert val_samples, "Must have at least one validation sample"
        val_sample = val_samples[0]
        assert train_sample.task9_run_id != val_sample.task9_run_id, (
            "Train and validation must use different task9_run_id"
        )
        assert (
            train_sample.label_analytics_build_run_id != val_sample.label_analytics_build_run_id
        ), "Train and validation must use different label build_run_id"
        assert (
            train_sample.feature_analytics_build_run_id != val_sample.feature_analytics_build_run_id
        ), "Train and validation must use different feature build_run_id"

        # C12. No blockers
        assert training_result.blockers == (), (
            f"Expected no blockers, got {training_result.blockers}"
        )

        # C13. Sample count > 0
        assert training_result.sample_count > 0, (
            f"Expected sample_count > 0, got {training_result.sample_count}"
        )
