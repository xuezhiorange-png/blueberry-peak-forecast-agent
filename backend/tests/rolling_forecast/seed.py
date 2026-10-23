"""SYNTHETIC I5 evidence/I7 snapshot plus frozen-model fixture; no private files."""

import asyncio
import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from backend.app.actual_harvest_import.api_auth import ActualHarvestActorContext
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiAppendRecordsRequest,
    ActualHarvestApiCreateImportRequest,
    ActualHarvestApiRecordInput,
)
from backend.app.actual_harvest_import.commit_service import commit_batch
from backend.app.actual_harvest_import.lifecycle import (
    append_import_records,
    create_import,
    seal_import,
    validate_import,
)
from backend.app.actual_harvest_labels.service import create_label_snapshot
from backend.app.rolling_forecast.policy import Catalog
from backend.app.rolling_forecast.schemas import Area, Calendar
from backend.research.v019_daily_curve import canonical_bytes
from backend.tests.actual_harvest_import import test_i7_label_snapshot as i7
from backend.tests.actual_harvest_import.test_lifecycle_postgres import (
    _create_payload,
    _record_payload,
    _seed_i5_registry_sync,
)
from backend.tests.rolling_forecast.training_fixture import frozen_document

ORIGIN = date(2026, 11, 5)
CUTOFF = datetime(2026, 11, 5, 9, tzinfo=UTC)


async def seed(factory, principal_id: str, directory: Path):
    source = "synthetic-s7"
    start = date(2026, 10, 1)
    records = [
        ActualHarvestApiRecordInput.model_validate(
            {
                **_record_payload(),
                "source_system": source,
                "external_logical_record_id": f"SYNTHETIC-day-{i}",
                "external_revision_id": f"SYNTHETIC-rev-{i}",
                "actual_harvest_quantity_kg": str(i + 1),
                "harvest_business_date": start + timedelta(days=i),
                "source_recorded_at": datetime(2026, 10, 1, tzinfo=UTC),
                "revised_at": datetime(2026, 10, 1, tzinfo=UTC),
                "external_batch_id": "SYNTHETIC_S7",
            }
        )
        for i in range(52)
    ]
    async with factory() as db, db.begin():
        await db.run_sync(
            lambda session: _seed_i5_registry_sync(
                session, suffix="SYNTHETIC_S7", mapping_policy="SYNTHETIC_S7", source_system=source
            )
        )
        batch, _ = await create_import(
            db,
            ActualHarvestApiCreateImportRequest.model_validate(
                {
                    **_create_payload(),
                    "source_system": source,
                    "mapping_policy_version": "SYNTHETIC_S7",
                    "external_batch_id": "SYNTHETIC_S7",
                    "expected_record_count_or_null": len(records),
                }
            ),
        )
    async with factory() as db, db.begin():
        await append_import_records(
            db, batch.import_id, ActualHarvestApiAppendRecordsRequest(records=tuple(records))
        )
        await seal_import(db, batch.import_id, actor_identity="operator-1")
    async with factory() as db:
        validation = await validate_import(db, batch.import_id)
        assert validation.validation_status == "VALIDATED"
    async with factory() as db, db.begin():
        await commit_batch(
            db,
            import_id=batch.import_id,
            validation_run_instance_identity_hash=validation.validation_run_identity,
            actor=ActualHarvestActorContext(
                identity="operator-1",
                allowed_source_systems={source},
                allowed_channels={"api"},
                may_commit=True,
            ),
        )
    sources = []
    async with factory() as db, db.begin():
        for i in range(3):
            cutoff = CUTOFF + timedelta(days=i if i < 2 else 25)
            snapshot = await create_label_snapshot(
                db,
                request=i7._base_request(
                    source_system=source,
                    snapshot_idempotency_key=f"SYNTHETIC-S7-{i}",
                    label_observation_cutoff_at_or_null=cutoff,
                    harvest_date_start=start,
                    harvest_date_end=cutoff.date() - timedelta(days=1),
                    season_business_keys=("season-SYNTHETIC_S7",),
                ),
                created_by_identity="SYNTHETIC_S7_FIXTURE",
            )
            sources.append(
                {
                    "reference": f"SYNTHETIC-SNAPSHOT-{i}",
                    "snapshot_id": snapshot.header.snapshot_id,
                    "snapshot_hash": snapshot.header.label_snapshot_hash,
                    "source_system": source,
                    "provenance": "SYNTHETIC_TEST_FIXTURE",
                    "members": [
                        {
                            "season_business_key": "season-SYNTHETIC_S7",
                            "farm_business_key": "farm-master-SYNTHETIC_S7",
                            "subfarm_business_key": "subfarm-master-SYNTHETIC_S7",
                            "variety_business_key": "variety-master-SYNTHETIC_S7",
                        }
                    ],
                    "membership_authority_hash": "b" * 64,
                    "mapping_registry_hash": snapshot.winners[0]["registry_content_hash"],
                    "completeness_authority_hash": "c" * 64,
                    "completeness_known_at": "2026-10-01T00:00:00Z",
                    "complete_dates": [str(start + timedelta(days=j)) for j in range(52)],
                    "confirmed_zero_dates": [],
                    "quantity_basis": "FIELD_HARVEST_WEIGHT",
                }
            )
    directory = await asyncio.to_thread(directory.resolve)
    model_path = directory / "SYNTHETIC-frozen-model.json"
    data = frozen_document()
    raw = canonical_bytes(data)
    model_path.write_bytes(raw)
    model_path.chmod(0o600)
    calendar = Calendar(
        reference="SYNTHETIC-CALENDAR",
        season="2026-2027",
        start=start,
        end=date(2026, 12, 31),
        source_hash="a" * 64,
        known_at=datetime(2023, 1, 1, tzinfo=UTC),
    )
    area = Area(
        reference="SYNTHETIC-AREA",
        base_id="SYNTHETIC_BASE",
        season=calendar.season,
        area_mu="100",
        source_hash="b" * 64,
        known_at=calendar.known_at,
        effective_from=calendar.start,
        effective_until=calendar.end,
    )
    catalog = Catalog.model_validate(
        {
            "schema_version": "ROLLING_SHADOW_CATALOG_V1",
            "revision": "SYNTHETIC_R1",
            "contexts": [
                {
                    "reference": "SYNTHETIC-CONTEXT",
                    "organization_id": "SYNTHETIC_ORG",
                    "calendar": calendar,
                    "area": area,
                    "snapshots": sources[:2],
                    "review_snapshots": [
                        {
                            **sources[2],
                            "mature_through": "2026-11-30",
                            "label_cutoff_at": (CUTOFF + timedelta(days=25)).isoformat(),
                            "maturity_authority_hash": "d" * 64,
                        }
                    ],
                    "modes": ["RESEARCH_SHADOW"],
                    "models": [
                        {
                            "reference": "SYNTHETIC-MODEL",
                            "path": str(model_path),
                            "file_sha256": hashlib.sha256(raw).hexdigest(),
                            "fit_sha256": data["payload"]["experiments"]["B"]["sha256"],
                            "source_code_identity": "a" * 64,
                            "source_code_sha": "0" * 40,
                            "provenance": "SYNTHETIC_TEST_FIXTURE",
                            "model_training_target_quantity_basis": "FIELD_HARVEST_WEIGHT",
                        }
                    ],
                }
            ],
            "capabilities": [
                {
                    "principal_id": principal_id,
                    "auth_revision": 1,
                    "grant_revision": 1,
                    "contexts": ["SYNTHETIC-CONTEXT"],
                    "operations": ["issue", "read", "compare", "evaluate"],
                    "valid_from": "2020-01-01T00:00:00Z",
                    "valid_until": "2035-01-01T00:00:00Z",
                }
            ],
        }
    )
    policy_path = directory / "SYNTHETIC-catalog.json"
    policy_path.write_text(catalog.model_dump_json())
    policy_path.chmod(0o600)
    return catalog, policy_path


def issue_body(offset=0):
    return {
        "base_id": "SYNTHETIC_BASE",
        "target_season": "2026-2027",
        "origin_date": str(ORIGIN + timedelta(days=offset)),
        "origin_cutoff_at": (CUTOFF + timedelta(days=offset)).isoformat(),
        "observation_snapshot_reference": f"SYNTHETIC-SNAPSHOT-{offset}",
        "area_authority_reference": "SYNTHETIC-AREA",
        "frozen_model_artifact_reference": "SYNTHETIC-MODEL",
        "execution_mode": "RESEARCH_SHADOW",
    }
