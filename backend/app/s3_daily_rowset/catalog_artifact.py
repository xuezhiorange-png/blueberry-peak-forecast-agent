"""S3-A2 evaluation instance catalog artifact production service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.binding import (
    CatalogBindingCandidate,
    CatalogBindingResult,
    EvaluationInstanceCatalogBindingService,
    expected_catalog_binding_lineage,
)
from backend.app.s3_daily_rowset.registry import (
    ALLOWED_ALIGNMENT_SOURCE_KINDS,
    FORBIDDEN_CATALOG_SOURCE_KINDS,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    REGISTRY_SOURCE_STATUS_UNBOUND,
    CatalogSourceKind,
    EvaluationInstanceCatalogPort,
    InMemoryEvaluationInstanceCatalog,
    RegistryCatalogEntry,
    UnboundEvaluationInstanceCatalog,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
    DatasetIdentityMismatchError,
    EvaluationInstanceCell,
)

CATALOG_IDENTITY_VERSION = "v0-3-s3-a2-catalog-artifact-identity-v1"


class CatalogArtifactReasonCode(StrEnum):
    NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT = "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT"
    NO_S2_IDENTITY_ALIGNMENT = "NO_S2_IDENTITY_ALIGNMENT"
    DATASET_IDENTITY_MISMATCH = "DATASET_IDENTITY_MISMATCH"
    FORBIDDEN_CATALOG_SOURCE = "FORBIDDEN_CATALOG_SOURCE"
    HARVEST_DATE_AS_CUTOFF_FORBIDDEN = "HARVEST_DATE_AS_CUTOFF_FORBIDDEN"
    ARTIFACT_PRODUCED = "ARTIFACT_PRODUCED"


@dataclass(frozen=True, slots=True)
class IncumbentForecastArtifactEntry:
    model_id: str
    forecast_cutoff_at: datetime
    forecast_quantile: str


class IncumbentForecastArtifactPort:
    """Port for versioned incumbent forecast artifacts at historical cutoff."""

    def has_versioned_artifact(self) -> bool:
        raise NotImplementedError

    def catalog_source_kind(self) -> CatalogSourceKind:
        raise NotImplementedError

    def entries(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        raise NotImplementedError

    def uses_harvest_date_as_forecast_cutoff(self) -> bool:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class MissingIncumbentForecastArtifactPort(IncumbentForecastArtifactPort):
    def has_versioned_artifact(self) -> bool:
        return False

    def catalog_source_kind(self) -> CatalogSourceKind:
        return CatalogSourceKind.UNBOUND

    def entries(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        return ()

    def uses_harvest_date_as_forecast_cutoff(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class S2AlignedIdentity:
    season: str
    farm: str
    subfarm: str
    variety: str
    partition: Literal["TRAIN", "VALIDATION"]


class S2IdentityAlignmentPort:
    """Port for S2 TRAIN/VALIDATION identity alignment evidence."""

    def alignment_source_kind(self) -> CatalogSourceKind:
        raise NotImplementedError

    def aligned_identities(self) -> tuple[S2AlignedIdentity, ...]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class EmptyS2IdentityAlignmentPort(S2IdentityAlignmentPort):
    def alignment_source_kind(self) -> CatalogSourceKind:
        return CatalogSourceKind.UNBOUND

    def aligned_identities(self) -> tuple[S2AlignedIdentity, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class CatalogArtifactProductionResult:
    reason_code: CatalogArtifactReasonCode
    catalog: EvaluationInstanceCatalogPort
    catalog_identity_sha256: str | None
    binding_result: CatalogBindingResult | None
    evaluation_instance_registry_available: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False
    no_bindable_catalog_in_repository: bool = True
    registry_source_status: str = REGISTRY_SOURCE_STATUS_UNBOUND


def _cell_payload(cell: EvaluationInstanceCell) -> dict[str, object]:
    return {
        "farm": cell.farm,
        "forecast_cutoff_at": cell.forecast_cutoff_at,
        "forecast_quantile": cell.forecast_quantile,
        "model_id": cell.model_id,
        "season": cell.season,
        "subfarm": cell.subfarm,
        "variety": cell.variety,
    }


def _entry_sort_key(entry: RegistryCatalogEntry) -> tuple[str, ...]:
    cell = entry.cell
    return (
        entry.partition,
        cell.season,
        cell.farm,
        cell.subfarm,
        cell.variety,
        cell.model_id,
        cell.forecast_cutoff_at.isoformat(),
        cell.forecast_quantile,
    )


def compute_catalog_identity_sha256(
    *,
    dataset_identity: DatasetIdentity,
    entries: tuple[RegistryCatalogEntry, ...],
) -> str:
    if not entries:
        raise ValueError("non-empty catalog entries required for identity hash")
    sorted_entries = sorted(entries, key=_entry_sort_key)
    payload = {
        "catalog_identity_version": CATALOG_IDENTITY_VERSION,
        "dataset_id": dataset_identity.dataset_id,
        "dataset_version": dataset_identity.dataset_version,
        "materialized_dataset_identity_sha256": (
            dataset_identity.materialized_dataset_identity_sha256
        ),
        "entries": [
            {
                "cell": _cell_payload(entry.cell),
                "partition": entry.partition,
            }
            for entry in sorted_entries
        ],
    }
    digest = sha256_payload(payload)
    if digest == HORIZON_H7_SUCCESS_FIXTURE_HASH:
        raise ValueError("catalog identity must not equal H7 fixture hash")
    return digest


def _unbound_result(
    *,
    dataset_identity: DatasetIdentity,
    reason_code: CatalogArtifactReasonCode,
) -> CatalogArtifactProductionResult:
    binding_result = EvaluationInstanceCatalogBindingService(
        dataset_identity=dataset_identity,
        candidate=None,
    ).validate()
    return CatalogArtifactProductionResult(
        reason_code=reason_code,
        catalog=UnboundEvaluationInstanceCatalog(),
        catalog_identity_sha256=None,
        binding_result=binding_result,
    )


def _default_forecast_artifact_port() -> IncumbentForecastArtifactPort:
    from backend.app.s3_daily_rowset.forecast_artifact import IncumbentForecastArtifactAdapter

    return IncumbentForecastArtifactAdapter()


def _default_s2_identity_alignment_port() -> S2IdentityAlignmentPort:
    from backend.app.s3_daily_rowset.s2_identity_alignment import S2IdentityAlignmentAdapter

    return S2IdentityAlignmentAdapter()


@dataclass
class EvaluationInstanceCatalogArtifactProductionService:
    dataset_identity: DatasetIdentity
    forecast_port: IncumbentForecastArtifactPort = field(
        default_factory=_default_forecast_artifact_port
    )
    alignment_port: S2IdentityAlignmentPort = field(
        default_factory=_default_s2_identity_alignment_port
    )

    def _validate_dataset_identity(self) -> None:
        identity = self.dataset_identity
        if (
            identity.dataset_id != EXPECTED_DATASET_ID
            or identity.dataset_version != EXPECTED_DATASET_VERSION
            or identity.materialized_dataset_identity_sha256
            != EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256
        ):
            raise DatasetIdentityMismatchError(
                "S2 materialized dataset identity does not match bound authority"
            )

    def _build_catalog_entries(
        self,
        forecast_entries: tuple[IncumbentForecastArtifactEntry, ...],
        aligned_identities: tuple[S2AlignedIdentity, ...],
    ) -> tuple[RegistryCatalogEntry, ...]:
        catalog_entries: list[RegistryCatalogEntry] = []
        for aligned in aligned_identities:
            for forecast in forecast_entries:
                cell = EvaluationInstanceCell(
                    season=aligned.season,
                    farm=aligned.farm,
                    subfarm=aligned.subfarm,
                    variety=aligned.variety,
                    model_id=forecast.model_id,
                    forecast_cutoff_at=forecast.forecast_cutoff_at,
                    forecast_quantile=forecast.forecast_quantile,
                )
                catalog_entries.append(
                    RegistryCatalogEntry(
                        cell=cell,
                        partition=aligned.partition,
                    )
                )
        return tuple(catalog_entries)

    def produce(self) -> CatalogArtifactProductionResult:
        try:
            self._validate_dataset_identity()
        except DatasetIdentityMismatchError:
            return CatalogArtifactProductionResult(
                reason_code=CatalogArtifactReasonCode.DATASET_IDENTITY_MISMATCH,
                catalog=UnboundEvaluationInstanceCatalog(),
                catalog_identity_sha256=None,
                binding_result=EvaluationInstanceCatalogBindingService(
                    dataset_identity=self.dataset_identity,
                    candidate=None,
                ).validate(),
            )

        if not self.forecast_port.has_versioned_artifact():
            return CatalogArtifactProductionResult(
                reason_code=CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT,
                catalog=UnboundEvaluationInstanceCatalog(),
                catalog_identity_sha256=None,
                binding_result=EvaluationInstanceCatalogBindingService(
                    dataset_identity=self.dataset_identity,
                    candidate=None,
                ).validate(),
            )

        forecast_source_kind = self.forecast_port.catalog_source_kind()
        if forecast_source_kind in FORBIDDEN_CATALOG_SOURCE_KINDS:
            return _unbound_result(
                dataset_identity=self.dataset_identity,
                reason_code=CatalogArtifactReasonCode.FORBIDDEN_CATALOG_SOURCE,
            )

        if self.forecast_port.uses_harvest_date_as_forecast_cutoff():
            return _unbound_result(
                dataset_identity=self.dataset_identity,
                reason_code=CatalogArtifactReasonCode.HARVEST_DATE_AS_CUTOFF_FORBIDDEN,
            )

        forecast_entries = self.forecast_port.entries()
        if not forecast_entries:
            return CatalogArtifactProductionResult(
                reason_code=CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT,
                catalog=UnboundEvaluationInstanceCatalog(),
                catalog_identity_sha256=None,
                binding_result=EvaluationInstanceCatalogBindingService(
                    dataset_identity=self.dataset_identity,
                    candidate=None,
                ).validate(),
            )

        alignment_source_kind = self.alignment_port.alignment_source_kind()
        if alignment_source_kind in FORBIDDEN_CATALOG_SOURCE_KINDS:
            return _unbound_result(
                dataset_identity=self.dataset_identity,
                reason_code=CatalogArtifactReasonCode.FORBIDDEN_CATALOG_SOURCE,
            )

        aligned_identities = self.alignment_port.aligned_identities()
        if not aligned_identities:
            return CatalogArtifactProductionResult(
                reason_code=CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT,
                catalog=UnboundEvaluationInstanceCatalog(),
                catalog_identity_sha256=None,
                binding_result=EvaluationInstanceCatalogBindingService(
                    dataset_identity=self.dataset_identity,
                    candidate=None,
                ).validate(),
            )

        if alignment_source_kind == CatalogSourceKind.UNBOUND:
            return _unbound_result(
                dataset_identity=self.dataset_identity,
                reason_code=CatalogArtifactReasonCode.FORBIDDEN_CATALOG_SOURCE,
            )

        if alignment_source_kind not in ALLOWED_ALIGNMENT_SOURCE_KINDS:
            return _unbound_result(
                dataset_identity=self.dataset_identity,
                reason_code=CatalogArtifactReasonCode.FORBIDDEN_CATALOG_SOURCE,
            )

        catalog_entries = self._build_catalog_entries(forecast_entries, aligned_identities)
        catalog_identity = compute_catalog_identity_sha256(
            dataset_identity=self.dataset_identity,
            entries=catalog_entries,
        )
        catalog = InMemoryEvaluationInstanceCatalog(
            catalog_entries=catalog_entries,
            bound_registry_identity_sha256=catalog_identity,
            catalog_source_kind=forecast_source_kind,
        )
        binding_result = EvaluationInstanceCatalogBindingService(
            dataset_identity=self.dataset_identity,
            candidate=CatalogBindingCandidate(
                catalog=catalog,
                lineage=expected_catalog_binding_lineage(),
            ),
        ).validate()

        return CatalogArtifactProductionResult(
            reason_code=CatalogArtifactReasonCode.ARTIFACT_PRODUCED,
            catalog=catalog,
            catalog_identity_sha256=catalog_identity,
            binding_result=binding_result,
            evaluation_instance_registry_available=False,
            current_s3_daily_rowset_completeness_verified=False,
            no_bindable_catalog_in_repository=True,
            registry_source_status=REGISTRY_SOURCE_STATUS_UNBOUND,
        )
