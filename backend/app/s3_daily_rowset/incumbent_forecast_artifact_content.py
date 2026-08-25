"""S3-A2 incumbent forecast artifact content producer."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.forecast_artifact import (
    VersionedIncumbentForecastArtifact,
    _entry_intersects_test_partition,
)
from backend.app.s3_daily_rowset.registry import (
    FORBIDDEN_CATALOG_SOURCE_KINDS,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.app.s3_daily_rowset.window import DEFAULT_IN_SEASON_MONTHS, cutoff_business_date

INCUMBENT_FORECAST_ARTIFACT_CONTENT_IDENTITY_VERSION = (
    "v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1"
)
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True

FORBIDDEN_EMPTY_CONTENT_IDENTITY_HASHES = frozenset(
    {
        "",
        "0" * 64,
    }
)


class ForbiddenIncumbentForecastArtifactContentError(ValueError):
    """Raised when incumbent forecast artifact content production is forbidden."""


def _validate_content_identity_sha256(content_identity_sha256: str) -> None:
    if content_identity_sha256 in FORBIDDEN_EMPTY_CONTENT_IDENTITY_HASHES:
        raise ForbiddenIncumbentForecastArtifactContentError(
            "empty incumbent forecast artifact content hash sentinel is forbidden"
        )
    if content_identity_sha256 == HORIZON_H7_SUCCESS_FIXTURE_HASH:
        raise ForbiddenIncumbentForecastArtifactContentError(
            "H=7 fixture hash cannot be used as incumbent forecast artifact content identity"
        )


def _canonical_field(value: str, *, field_name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ForbiddenIncumbentForecastArtifactContentError(
            f"blank incumbent forecast artifact field after trim is forbidden: {field_name}"
        )
    return trimmed


def _entry_payload(entry: IncumbentForecastArtifactEntry) -> dict[str, object]:
    return {
        "forecast_cutoff_at": entry.forecast_cutoff_at.isoformat(),
        "forecast_quantile": entry.forecast_quantile,
        "model_id": entry.model_id,
    }


def _entry_sort_key(entry: IncumbentForecastArtifactEntry) -> tuple[str, ...]:
    return (
        entry.model_id,
        entry.forecast_cutoff_at.isoformat(),
        entry.forecast_quantile,
    )


def _accepted_replay_entry(
    entry: IncumbentForecastArtifactEntry,
) -> IncumbentForecastArtifactEntry | None:
    model_id = _canonical_field(entry.model_id, field_name="model_id")
    forecast_quantile = _canonical_field(entry.forecast_quantile, field_name="forecast_quantile")
    if entry.forecast_cutoff_at.tzinfo is None or entry.forecast_cutoff_at.utcoffset() is None:
        raise ForbiddenIncumbentForecastArtifactContentError(
            "forecast_cutoff_at must be timezone-aware"
        )

    normalized = IncumbentForecastArtifactEntry(
        model_id=model_id,
        forecast_cutoff_at=entry.forecast_cutoff_at,
        forecast_quantile=forecast_quantile,
    )
    if cutoff_business_date(normalized.forecast_cutoff_at).month not in DEFAULT_IN_SEASON_MONTHS:
        return None
    if _entry_intersects_test_partition(normalized):
        return None
    return normalized


def project_incumbent_forecast_artifact_entries(
    replay_rows: tuple[IncumbentForecastArtifactEntry, ...],
) -> tuple[IncumbentForecastArtifactEntry, ...]:
    deduped: dict[tuple[str, str, str], IncumbentForecastArtifactEntry] = {}
    for replay_row in replay_rows:
        projected = _accepted_replay_entry(replay_row)
        if projected is None:
            continue
        dedup_key = (
            projected.model_id,
            projected.forecast_cutoff_at.isoformat(),
            projected.forecast_quantile,
        )
        deduped[dedup_key] = projected
    return tuple(sorted(deduped.values(), key=_entry_sort_key))


def compute_content_identity_sha256(
    *,
    rows: tuple[IncumbentForecastArtifactEntry, ...],
) -> str:
    if not rows:
        raise ValueError(
            "non-empty incumbent forecast artifact content rows required for identity hash"
        )
    sorted_rows = sorted(rows, key=_entry_sort_key)
    payload = {
        "content_identity_version": INCUMBENT_FORECAST_ARTIFACT_CONTENT_IDENTITY_VERSION,
        "entries": [_entry_payload(row) for row in sorted_rows],
    }
    digest = sha256_payload(payload)
    _validate_content_identity_sha256(digest)
    return digest


def envelope_catalog_source_kind_for_declaration(
    declared_catalog_source_kind: CatalogSourceKind,
) -> CatalogSourceKind:
    if declared_catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE:
        return CatalogSourceKind.BOUND_FIXTURE
    if (
        declared_catalog_source_kind
        == CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
    ):
        return CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
    if declared_catalog_source_kind == CatalogSourceKind.UNBOUND:
        raise ForbiddenIncumbentForecastArtifactContentError(
            "UNBOUND catalog source kind cannot be assigned to forecast envelope"
        )
    if declared_catalog_source_kind in FORBIDDEN_CATALOG_SOURCE_KINDS:
        raise ForbiddenIncumbentForecastArtifactContentError(
            "forbidden catalog source kind cannot be assigned to forecast envelope: "
            f"{declared_catalog_source_kind}"
        )
    if (
        declared_catalog_source_kind
        == CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
    ):
        raise ForbiddenIncumbentForecastArtifactContentError(
            "alignment catalog source kind cannot be assigned to forecast envelope"
        )
    raise ForbiddenIncumbentForecastArtifactContentError(
        "catalog source kind cannot be assigned to forecast envelope: "
        f"{declared_catalog_source_kind}"
    )


@dataclass
class IncumbentForecastArtifactContentProducer:
    replay_rows: tuple[IncumbentForecastArtifactEntry, ...] = ()
    uses_harvest_date_as_forecast_cutoff: bool = False
    declared_catalog_source_kind: CatalogSourceKind = CatalogSourceKind.BOUND_FIXTURE

    def produce(self) -> VersionedIncumbentForecastArtifact | None:
        if self.uses_harvest_date_as_forecast_cutoff:
            return None
        if not self.replay_rows:
            return None

        rows = project_incumbent_forecast_artifact_entries(self.replay_rows)
        if not rows:
            return None

        envelope_kind = envelope_catalog_source_kind_for_declaration(
            self.declared_catalog_source_kind
        )
        content_identity_sha256 = compute_content_identity_sha256(rows=rows)
        return VersionedIncumbentForecastArtifact(
            content_identity_sha256=content_identity_sha256,
            rows=rows,
            catalog_source_kind=envelope_kind,
            uses_harvest_date_as_forecast_cutoff=False,
        )
