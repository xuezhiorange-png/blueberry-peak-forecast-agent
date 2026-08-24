"""S3-A2 S2 identity alignment live adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from backend.app.s3_daily_rowset.actuals import partition_for_harvest_date
from backend.app.s3_daily_rowset.catalog_artifact import (
    S2AlignedIdentity,
    S2IdentityAlignmentPort,
)
from backend.app.s3_daily_rowset.exclusion import is_cell_level_excluded
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    EvaluationInstanceCell,
)
from backend.app.s3_daily_rowset.window import DEFAULT_IN_SEASON_MONTHS

ALIGNMENT_PROJECTION_VERSION = "v0-3-s3-a2-s2-identity-alignment-projection-v1"

FORBIDDEN_EMPTY_ALIGNMENT_EVIDENCE_HASHES = frozenset(
    {
        "",
        "0" * 64,
    }
)

_ALIGNMENT_PROJECTION_CUTOFF = datetime(2026, 2, 15, 16, 0, tzinfo=UTC)


class ForbiddenS2IdentityAlignmentError(ValueError):
    """Raised when S2 identity alignment evidence is forbidden."""


def _validate_alignment_evidence_identity(content_identity_sha256: str) -> None:
    if content_identity_sha256 in FORBIDDEN_EMPTY_ALIGNMENT_EVIDENCE_HASHES:
        raise ForbiddenS2IdentityAlignmentError(
            "empty S2 alignment evidence hash sentinel is forbidden"
        )
    if content_identity_sha256 == HORIZON_H7_SUCCESS_FIXTURE_HASH:
        raise ForbiddenS2IdentityAlignmentError(
            "H=7 fixture hash cannot be used as S2 alignment evidence identity"
        )


def _validate_dataset_binding(
    *,
    dataset_id: str,
    dataset_version: str,
    materialized_dataset_identity_sha256: str,
) -> None:
    if (
        dataset_id != EXPECTED_DATASET_ID
        or dataset_version != EXPECTED_DATASET_VERSION
        or materialized_dataset_identity_sha256 != EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
    ):
        raise ForbiddenS2IdentityAlignmentError(
            "S2 materialized dataset identity does not match bound authority"
        )


def _canonical_field(value: str, *, field_name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ForbiddenS2IdentityAlignmentError(
            f"blank S2 alignment field after trim is forbidden: {field_name}"
        )
    return trimmed


def _row_is_excluded(
    *,
    season: str,
    farm: str,
    subfarm: str,
    variety: str,
) -> bool:
    cell = EvaluationInstanceCell(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        model_id="alignment-projection-only",
        forecast_cutoff_at=_ALIGNMENT_PROJECTION_CUTOFF,
        forecast_quantile="P50",
    )
    return is_cell_level_excluded(cell)


def _project_identity(row: AcceptedS2IdentityEvidenceRow) -> S2AlignedIdentity | None:
    season = _canonical_field(row.season, field_name="season")
    farm = _canonical_field(row.farm, field_name="farm")
    subfarm = _canonical_field(row.subfarm, field_name="subfarm")
    variety = _canonical_field(row.variety, field_name="variety")

    partition = partition_for_harvest_date(row.harvest_business_date)
    if partition == "TRAIN":
        aligned_partition: Literal["TRAIN", "VALIDATION"] = "TRAIN"
    elif partition == "VALIDATION":
        aligned_partition = "VALIDATION"
    else:
        return None
    if row.harvest_business_date.month not in DEFAULT_IN_SEASON_MONTHS:
        return None
    if _row_is_excluded(season=season, farm=farm, subfarm=subfarm, variety=variety):
        return None

    return S2AlignedIdentity(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        partition=aligned_partition,
    )


def _identity_sort_key(identity: S2AlignedIdentity) -> tuple[str, ...]:
    return (
        identity.partition,
        identity.season,
        identity.farm,
        identity.subfarm,
        identity.variety,
    )


def project_accepted_s2_identities(
    rows: tuple[AcceptedS2IdentityEvidenceRow, ...],
) -> tuple[S2AlignedIdentity, ...]:
    deduped: dict[tuple[str, str, str, str, str], S2AlignedIdentity] = {}
    for row in rows:
        projected = _project_identity(row)
        if projected is None:
            continue
        dedup_key = (
            projected.season,
            projected.farm,
            projected.subfarm,
            projected.variety,
            projected.partition,
        )
        deduped[dedup_key] = projected
    return tuple(sorted(deduped.values(), key=_identity_sort_key))


@dataclass(frozen=True, slots=True)
class AcceptedS2IdentityEvidenceRow:
    season: str
    farm: str
    subfarm: str
    variety: str
    harvest_business_date: date


@dataclass(frozen=True, slots=True)
class VersionedAcceptedS2IdentityAlignmentEvidence:
    content_identity_sha256: str
    dataset_id: str
    dataset_version: str
    materialized_dataset_identity_sha256: str
    rows: tuple[AcceptedS2IdentityEvidenceRow, ...]

    def __post_init__(self) -> None:
        _validate_alignment_evidence_identity(self.content_identity_sha256)
        _validate_dataset_binding(
            dataset_id=self.dataset_id,
            dataset_version=self.dataset_version,
            materialized_dataset_identity_sha256=self.materialized_dataset_identity_sha256,
        )


@dataclass
class S2IdentityAlignmentAdapter(S2IdentityAlignmentPort):
    evidence: VersionedAcceptedS2IdentityAlignmentEvidence | None = None

    def _projected_identities(self) -> tuple[S2AlignedIdentity, ...]:
        if self.evidence is None:
            return ()
        return project_accepted_s2_identities(self.evidence.rows)

    def alignment_source_kind(self) -> CatalogSourceKind:
        if not self._projected_identities():
            return CatalogSourceKind.UNBOUND
        return CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT

    def aligned_identities(self) -> tuple[S2AlignedIdentity, ...]:
        return self._projected_identities()
