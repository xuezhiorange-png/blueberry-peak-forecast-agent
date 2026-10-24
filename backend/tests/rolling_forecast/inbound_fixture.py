"""Explicit SYNTHETIC inbound events; no warehouse, private inputs or training."""

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from backend.app.rolling_forecast.policy import Catalog
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_synthetic_validation import digest
from backend.tests.rolling_forecast.test_model_artifacts import reference


def write(path: Path, value):
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def fixture(directory: Path, principal_id="SYNTHETIC-user", mutate=None):
    from backend.app.rolling_forecast.inbound import Index
    from backend.app.rolling_forecast.policy import InboundSnapshot

    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    model, _ = reference(directory)
    model = model.model_copy(
        update={"model_training_target_quantity_basis": "RECORDED_INBOUND_WEIGHT"}
    )
    member = dict(
        season_business_key="SYNTHETIC-season",
        farm_business_key="SYNTHETIC-farm",
        subfarm_business_key="SYNTHETIC-subfarm",
        variety_business_key="SYNTHETIC-variety",
    )
    definition = dict(
        event="INBOUND_RECEIPT",
        measure="RECORDED_WEIGHT_AS_RECORDED",
        business_date_rule="INBOUND_EVENT_LOCAL_DATE",
        unit="kg",
        tare_or_field_conversion="NONE",
        proof_hash="a" * 64,
    )
    start = date(2026, 10, 1)
    days = []
    for i in range(52):
        day = start + timedelta(days=i)
        timestamp = datetime.combine(day, datetime.min.time(), UTC).isoformat()
        record = dict(
            logical_id=f"SYNTHETIC-{i}",
            revision_id=f"SYNTHETIC-{i}-r1",
            member=member,
            grade="SYNTHETIC-ACCEPTED",
            quantity_kg=f"{i + 1}.000000",
            source_recorded_at=timestamp,
            server_ingested_at=timestamp,
            available_at_authority="TRUSTED_SOURCE_TIMESTAMP",
        )
        payload = dict(
            base_id="SYNTHETIC_INBOUND_BASE",
            season="2026-2027",
            business_date=str(day),
            source_system="SYNTHETIC-INBOUND",
            records=[record],
        )
        if mutate:
            mutate(i, payload)
        path = directory / f"day-{day}.json"
        days.append(
            dict(
                business_date=str(day),
                file=path.name,
                sha256=write(path, payload),
                member_coverage=[member],
                completeness_status="COMPLETE",
                known_at=timestamp,
            )
        )
    manifest = dict(
        schema_version="CONTROLLED_RECORDED_INBOUND_V1",
        base_id="SYNTHETIC_INBOUND_BASE",
        season="2026-2027",
        source_system="SYNTHETIC-INBOUND",
        physical_definition=definition,
        accepted_grades=["SYNTHETIC-ACCEPTED"],
        excluded_grades=["SYNTHETIC-EXCLUDED"],
        revision_rule="EXPLICIT_IMMUTABLE_WINNERS",
        days=days,
    )
    manifest = Index.model_validate(manifest).model_dump(mode="json")
    path = directory / "manifest.json"
    sha = write(path, manifest)
    source = dict(
        reference="SYNTHETIC-INBOUND-SNAPSHOT",
        snapshot_id=1,
        source_kind="CONTROLLED_RECORDED_INBOUND_V1",
        manifest_path=str(path.resolve()),
        manifest_sha256=sha,
        snapshot_hash=digest(manifest),
        source_system="SYNTHETIC-INBOUND",
        provenance="SYNTHETIC_TEST_FIXTURE",
        members=[member],
        membership_authority_hash="b" * 64,
        mapping_registry_hash="c" * 64,
        completeness_authority_hash="d" * 64,
        completeness_known_at="2026-09-01T00:00:00Z",
        complete_dates=[d["business_date"] for d in days],
        quantity_basis="RECORDED_INBOUND_WEIGHT",
        physical_definition_hash=digest(definition),
        target_binding=dict(
            fit_sha256=model.fit_sha256, authority_hash="e" * 64, scope="SYNTHETIC_CONTRACT_ONLY"
        ),
    )
    InboundSnapshot.model_validate(source)
    calendar = dict(
        reference="SYNTHETIC-INBOUND-CALENDAR",
        season="2026-2027",
        start=str(start),
        end="2026-12-31",
        source_hash="f" * 64,
        known_at="2026-09-01T00:00:00Z",
    )
    area = dict(
        reference="SYNTHETIC-INBOUND-AREA",
        base_id="SYNTHETIC_INBOUND_BASE",
        season="2026-2027",
        area_mu="100",
        source_hash="1" * 64,
        known_at=calendar["known_at"],
        effective_from=calendar["start"],
        effective_until=calendar["end"],
    )
    context = dict(
        reference="SYNTHETIC-INBOUND-CONTEXT",
        organization_id="SYNTHETIC_ORG",
        area=area,
        calendar=calendar,
        models=[model],
        snapshots=[source],
        modes=["RESEARCH_SHADOW"],
        review_snapshots=[
            dict(
                source,
                reference="SYNTHETIC-INBOUND-LABELS",
                mature_through="2026-11-30",
                label_cutoff_at="2026-11-30T09:00:00Z",
                maturity_authority_hash="2" * 64,
            )
        ],
    )
    catalog = Catalog.model_validate(
        dict(
            schema_version="ROLLING_SHADOW_CATALOG_V1",
            revision="SYNTHETIC-S8-R1",
            contexts=[context],
            capabilities=[
                dict(
                    principal_id=principal_id,
                    auth_revision=1,
                    grant_revision=1,
                    contexts=[context["reference"]],
                    operations=["issue", "read", "compare", "evaluate"],
                    valid_from="2020-01-01T00:00:00Z",
                    valid_until="2035-01-01T00:00:00Z",
                )
            ],
        )
    )
    return catalog


def body(offset=0):
    return dict(
        base_id="SYNTHETIC_INBOUND_BASE",
        target_season="2026-2027",
        origin_date=str(date(2026, 11, 5) + timedelta(days=offset)),
        origin_cutoff_at=(
            datetime(2026, 11, 5, 9, tzinfo=UTC) + timedelta(days=offset)
        ).isoformat(),
        observation_snapshot_reference="SYNTHETIC-INBOUND-SNAPSHOT",
        area_authority_reference="SYNTHETIC-INBOUND-AREA",
        frozen_model_artifact_reference="SYNTHETIC",
        execution_mode="RESEARCH_SHADOW",
    )
