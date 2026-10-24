"""Read existing I7 winners with exact Base membership and explicit completeness.

No import, source discovery, revision rewriting, inferred zeros or label table.
SQL restricts dates BEFORE quantities are selected. Later revisions cannot alter
the immutable snapshot referenced by an already persisted rolling run.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.actual_harvest_import.commit_models import (
    ActualHarvestCommitManifestModel as Commit,
)
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel as Batch
from backend.app.actual_harvest_import.models import ActualHarvestImportRecordModel as Record
from backend.app.actual_harvest_labels.hashes import compute_winner_manifest_hash
from backend.app.actual_harvest_labels.models import ActualHarvestLabelSnapshotModel as Header
from backend.app.actual_harvest_labels.models import ActualHarvestLabelSnapshotWinnerModel as Winner
from backend.app.actual_harvest_labels.persistence import winner_row_hash_for
from backend.app.actual_harvest_labels.service import _compute_canonical_record_hash_for_record
from backend.app.rolling_forecast.policy import Context, InboundSnapshot, Snapshot
from backend.app.rolling_forecast.schemas import Observation
from backend.research.v019_synthetic_validation import digest


async def load(
    db: AsyncSession,
    context: Context,
    source: Snapshot | InboundSnapshot,
    origin: date,
    cutoff: datetime,
    start: date | None = None,
) -> list[Observation]:
    if isinstance(source, InboundSnapshot):
        from backend.app.rolling_forecast import inbound

        return inbound.load(context, source, origin, cutoff, start)
    first = context.calendar.start if start is None else start
    header = await db.get(Header, source.snapshot_id)
    if (
        header is None
        or header.label_snapshot_hash != source.snapshot_hash
        or header.source_system != source.source_system
    ):
        raise ValueError("OBSERVATION_SNAPSHOT_IDENTITY_MISMATCH")
    if (
        source.provenance == "SYNTHETIC_TEST_FIXTURE"
        and not header.source_system.upper().startswith("SYNTHETIC")
    ):
        raise ValueError("SOURCE_PROVENANCE_MISMATCH")
    if context.calendar.season == "2026-2027" and source.provenance != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("CURRENT_SEASON_REAL_READ_NOT_AUTHORIZED")
    if (
        header.visibility_mode != "AS_OF_EVALUATION"
        or header.label_observation_cutoff_at_or_null != cutoff
    ):
        raise ValueError("OBSERVATION_CUTOFF_MISMATCH")
    metadata = (
        (
            await db.execute(
                select(
                    Winner.source_system,
                    Winner.external_logical_record_id,
                    Winner.external_revision_id,
                    Winner.winner_row_hash,
                ).where(Winner.snapshot_id == source.snapshot_id)
            )
        )
        .mappings()
        .all()
    )
    if (
        len(metadata) != header.winner_count
        or compute_winner_manifest_hash([dict(m) for m in metadata]) != header.winner_manifest_hash
    ):
        raise ValueError("OBSERVATION_WINNER_SET_MISMATCH")
    members = [
        and_(
            Winner.season_business_key == m.season_business_key,
            Winner.farm_business_key == m.farm_business_key,
            Winner.subfarm_business_key == m.subfarm_business_key,
            Winner.variety_business_key == m.variety_business_key,
        )
        for m in source.members
    ]
    rows = (
        await db.execute(
            select(Winner, Record, Commit, Batch)
            .join(
                Record,
                and_(
                    Record.source_system == Winner.source_system,
                    Record.external_revision_id == Winner.external_revision_id,
                ),
            )
            .join(Commit, Commit.commit_manifest_hash == Winner.commit_manifest_hash)
            .join(Batch, Batch.id == Commit.batch_id)
            .where(
                Winner.snapshot_id == source.snapshot_id,
                Winner.harvest_business_date >= first,
                Winner.harvest_business_date < origin,
                or_(*members),
            )
            .order_by(Winner.harvest_business_date, Winner.external_logical_record_id)
        )
    ).all()
    by_day: dict[date, list[tuple[Decimal, datetime, datetime, str]]] = {}
    invalid: set[date] = set()
    for winner, record, commit, batch in rows:
        payload = {c.name: getattr(winner, c.name) for c in Winner.__table__.columns}
        if winner_row_hash_for(payload) != winner.winner_row_hash:
            raise ValueError("OBSERVATION_WINNER_HASH_MISMATCH")
        if winner.registry_content_hash != source.mapping_registry_hash:
            raise ValueError("BASE_MAPPING_AUTHORITY_MISMATCH")
        day = winner.harvest_business_date
        if (
            record.batch_id != batch.id
            or _compute_canonical_record_hash_for_record(record) != winner.canonical_record_hash
            or batch.source_system != source.source_system
            or commit.source_semantics_attestation_hash != batch.source_semantics_attestation_hash
            or batch.source_semantics_physical_event != "FARM_PICK"
            or batch.source_semantics_quantity_basis != "OBSERVED_WEIGHT"
            or batch.source_semantics_quantity_unit != "KG"
        ):
            raise ValueError("OBSERVATION_SOURCE_OR_PHYSICAL_BASIS_MISMATCH")
        timestamps = (winner.source_recorded_at_or_null, record.ingested_at, commit.committed_at)
        if (
            winner.source_recorded_at_authority_status != "TRUSTED_SOURCE_TIMESTAMP"
            or any(t is None or t > cutoff for t in timestamps)
            or winner.effective_status not in {"ACTIVE", "FINALIZED"}
        ):
            invalid.add(day)
            continue
        by_day.setdefault(day, []).append(
            (
                Decimal(winner.actual_harvest_quantity_kg),
                timestamps[0],
                max(record.ingested_at, commit.committed_at),
                winner.winner_row_hash,
            )
        )
    result = []
    for i in range((origin - first).days):
        day = first + timedelta(days=i)
        values = by_day.get(day, [])
        complete = (
            day in source.complete_dates
            and day not in invalid
            and source.completeness_known_at <= cutoff
        )
        zero = day in source.confirmed_zero_dates
        with localcontext() as ctx:
            ctx.prec = 50
            total = sum((v[0] for v in values), Decimal(0))
        if zero and total != 0:
            raise ValueError("ZERO_AUTHORITY_CONFLICT")
        # No rows can only mean zero with separate, explicit day+member authority.
        valid = complete and (bool(values) or zero)
        result.append(
            Observation(
                base_id=context.area.base_id,
                season=context.calendar.season,
                business_date=day,
                quantity_kg=total if valid else None,
                record_state=("CONFIRMED_ZERO" if total == 0 else "VALID_OBSERVED")
                if valid
                else "PARTIAL"
                if values
                else "MISSING",
                quantity_basis=source.quantity_basis,
                source_system=source.source_system,
                source_identity=f"{source.reference}:{day}",
                source_hash=digest(
                    [
                        source.snapshot_hash,
                        source.membership_authority_hash,
                        source.completeness_authority_hash,
                        sorted(v[3] for v in values),
                        str(day),
                    ]
                ),
                source_recorded_at=max((v[1] for v in values), default=header.snapshot_executed_at),
                server_ingested_at=max((v[2] for v in values), default=header.snapshot_executed_at),
                available_at_authority="TRUSTED_SOURCE_TIMESTAMP" if valid else "MISSING",
                observation_completeness="COMPLETE" if valid else "INCOMPLETE",
            )
        )
    return result
