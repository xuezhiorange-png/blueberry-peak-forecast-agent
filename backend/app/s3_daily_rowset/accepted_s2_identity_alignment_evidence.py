"""S3-A2 accepted S2 identity alignment evidence producer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.actuals import partition_for_harvest_date
from backend.app.s3_daily_rowset.exclusion import is_bason_factory, is_forbidden_variety
from backend.app.s3_daily_rowset.registry import HORIZON_H7_SUCCESS_FIXTURE_HASH
from backend.app.s3_daily_rowset.s2_identity_alignment import (
    AcceptedS2IdentityEvidenceRow,
    VersionedAcceptedS2IdentityAlignmentEvidence,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
)
from backend.app.s3_daily_rowset.window import DEFAULT_IN_SEASON_MONTHS

if TYPE_CHECKING:
    from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
        S2IdentityAlignmentHarvestSource,
    )


def _default_harvest_source() -> S2IdentityAlignmentHarvestSource:
    from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
        S2IdentityAlignmentHarvestSource,
    )

    return S2IdentityAlignmentHarvestSource()


def _try_live_origin_construction_harvest_rows() -> tuple[MaterializableRow, ...]:
    try:
        from backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_construction import (
            live_origin_harvest_rows_for_default_construction,
        )
    except ImportError:
        return ()
    return live_origin_harvest_rows_for_default_construction()


ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION = (
    "v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1"
)
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True

FORBIDDEN_EMPTY_CONTENT_IDENTITY_HASHES = frozenset(
    {
        "",
        "0" * 64,
    }
)


class ForbiddenAcceptedS2IdentityAlignmentEvidenceError(ValueError):
    """Raised when accepted S2 identity alignment evidence production is forbidden."""


def _validate_dataset_binding(dataset_identity: DatasetIdentity) -> None:
    if (
        dataset_identity.dataset_id != EXPECTED_DATASET_ID
        or dataset_identity.dataset_version != EXPECTED_DATASET_VERSION
        or dataset_identity.materialized_dataset_identity_sha256
        != EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
    ):
        raise ForbiddenAcceptedS2IdentityAlignmentEvidenceError(
            "S2 materialized dataset identity does not match bound authority"
        )


def _validate_content_identity_sha256(content_identity_sha256: str) -> None:
    if content_identity_sha256 in FORBIDDEN_EMPTY_CONTENT_IDENTITY_HASHES:
        raise ForbiddenAcceptedS2IdentityAlignmentEvidenceError(
            "empty accepted S2 identity alignment evidence hash sentinel is forbidden"
        )
    if content_identity_sha256 == HORIZON_H7_SUCCESS_FIXTURE_HASH:
        raise ForbiddenAcceptedS2IdentityAlignmentEvidenceError(
            "H=7 fixture hash cannot be used as accepted S2 identity alignment evidence identity"
        )


def _canonical_field(value: str, *, field_name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ForbiddenAcceptedS2IdentityAlignmentEvidenceError(
            f"blank accepted S2 identity alignment field after trim is forbidden: {field_name}"
        )
    return trimmed


def _row_payload(row: AcceptedS2IdentityEvidenceRow) -> dict[str, object]:
    return {
        "farm": row.farm,
        "harvest_business_date": row.harvest_business_date.isoformat(),
        "season": row.season,
        "subfarm": row.subfarm,
        "variety": row.variety,
    }


def _row_sort_key(row: AcceptedS2IdentityEvidenceRow) -> tuple[str, ...]:
    return (
        row.harvest_business_date.isoformat(),
        row.season,
        row.farm,
        row.subfarm,
        row.variety,
    )


def _accepted_evidence_row(row: MaterializableRow) -> AcceptedS2IdentityEvidenceRow | None:
    season = _canonical_field(row.season, field_name="season")
    farm = _canonical_field(row.farm, field_name="farm")
    subfarm = _canonical_field(row.subfarm, field_name="subfarm")
    variety = _canonical_field(row.variety, field_name="variety")

    partition = partition_for_harvest_date(row.harvest_business_date)
    if partition not in {"TRAIN", "VALIDATION"}:
        return None
    if row.harvest_business_date.month not in DEFAULT_IN_SEASON_MONTHS:
        return None
    if is_forbidden_variety(variety) or is_bason_factory(farm):
        return None

    return AcceptedS2IdentityEvidenceRow(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=row.harvest_business_date,
    )


def project_accepted_s2_identity_evidence_rows(
    harvest_rows: tuple[MaterializableRow, ...],
) -> tuple[AcceptedS2IdentityEvidenceRow, ...]:
    deduped: dict[tuple[str, str, str, str, date], AcceptedS2IdentityEvidenceRow] = {}
    for harvest_row in harvest_rows:
        projected = _accepted_evidence_row(harvest_row)
        if projected is None:
            continue
        dedup_key = (
            projected.season,
            projected.farm,
            projected.subfarm,
            projected.variety,
            projected.harvest_business_date,
        )
        deduped[dedup_key] = projected
    return tuple(sorted(deduped.values(), key=_row_sort_key))


def compute_content_identity_sha256(
    *,
    dataset_identity: DatasetIdentity,
    rows: tuple[AcceptedS2IdentityEvidenceRow, ...],
) -> str:
    if not rows:
        raise ValueError("non-empty accepted S2 identity evidence rows required for identity hash")
    sorted_rows = sorted(rows, key=_row_sort_key)
    payload = {
        "content_identity_version": ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION,
        "dataset_id": dataset_identity.dataset_id,
        "dataset_version": dataset_identity.dataset_version,
        "materialized_dataset_identity_sha256": (
            dataset_identity.materialized_dataset_identity_sha256
        ),
        "rows": [_row_payload(row) for row in sorted_rows],
    }
    digest = sha256_payload(payload)
    _validate_content_identity_sha256(digest)
    return digest


@dataclass
class AcceptedS2IdentityAlignmentEvidenceProducer:
    dataset_identity: DatasetIdentity
    harvest_rows: tuple[MaterializableRow, ...] = ()
    harvest_source: S2IdentityAlignmentHarvestSource = field(
        default_factory=_default_harvest_source
    )

    def produce(self) -> VersionedAcceptedS2IdentityAlignmentEvidence | None:
        source_rows = self.harvest_rows
        if not source_rows:
            source_rows = self.harvest_source.obtain()
        if not source_rows:
            source_rows = _try_live_origin_construction_harvest_rows()
        if not source_rows:
            return None

        _validate_dataset_binding(self.dataset_identity)
        rows = project_accepted_s2_identity_evidence_rows(source_rows)
        if not rows:
            return None

        content_identity_sha256 = compute_content_identity_sha256(
            dataset_identity=self.dataset_identity,
            rows=rows,
        )
        return VersionedAcceptedS2IdentityAlignmentEvidence(
            content_identity_sha256=content_identity_sha256,
            dataset_id=self.dataset_identity.dataset_id,
            dataset_version=self.dataset_identity.dataset_version,
            materialized_dataset_identity_sha256=(
                self.dataset_identity.materialized_dataset_identity_sha256
            ),
            rows=rows,
        )
