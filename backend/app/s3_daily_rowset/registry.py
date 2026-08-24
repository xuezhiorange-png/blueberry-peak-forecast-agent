"""S3-A2 evaluation instance registry service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from backend.app.s3_daily_rowset.actuals import window_contains_test_partition
from backend.app.s3_daily_rowset.exclusion import is_cell_level_excluded
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    HORIZON_DAYS,
    DatasetIdentity,
    DatasetIdentityMismatchError,
    EvaluationInstanceCell,
)
from backend.app.s3_daily_rowset.window import (
    complete_season_window_dates,
    horizon_window_dates,
    window_within_default_month_scope,
)

HORIZON_H7_SUCCESS_FIXTURE_HASH = "8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18"
V0_3_S3_ACTUALS_AUTHORITY = "V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION"
V0_3_S3_FORECASTS_AUTHORITY = "V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF"
REGISTRY_SOURCE_STATUS_UNBOUND = "NOT_MATERIALIZED_OR_NOT_BOUND"
EVALUATION_PARTITIONS = frozenset({"TRAIN", "VALIDATION"})


class CatalogSourceKind(StrEnum):
    UNBOUND = "NOT_MATERIALIZED_OR_NOT_BOUND"
    BOUND_FIXTURE = "BOUND_FIXTURE"
    SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT = (
        "SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT"
    )
    H7_FIXTURE_HASH = "H7_FIXTURE_HASH"
    S2_HARVEST_GRAIN = "S2_HARVEST_GRAIN"
    V0_2_S3_BINDING_ROWS = "V0_2_S3_BINDING_ROWS"
    HANDWRITTEN_FARM_LIST = "HANDWRITTEN_FARM_LIST"
    HANDWRITTEN_CUTOFF_LIST = "HANDWRITTEN_CUTOFF_LIST"
    FARM_PICK_DAY_ENUMERATION = "FARM_PICK_DAY_ENUMERATION"


FORBIDDEN_CATALOG_SOURCE_KINDS = frozenset(
    {
        CatalogSourceKind.H7_FIXTURE_HASH,
        CatalogSourceKind.S2_HARVEST_GRAIN,
        CatalogSourceKind.V0_2_S3_BINDING_ROWS,
        CatalogSourceKind.HANDWRITTEN_FARM_LIST,
        CatalogSourceKind.HANDWRITTEN_CUTOFF_LIST,
        CatalogSourceKind.FARM_PICK_DAY_ENUMERATION,
    }
)

ALLOWED_ALIGNMENT_SOURCE_KINDS = frozenset(
    {
        CatalogSourceKind.BOUND_FIXTURE,
        CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT,
    }
)


class ForbiddenCatalogSourceError(ValueError):
    """Raised when a forbidden catalog source is supplied."""


@dataclass(frozen=True, slots=True)
class RegistryCatalogEntry:
    cell: EvaluationInstanceCell
    partition: Literal["TRAIN", "VALIDATION", "TEST"]


@dataclass(frozen=True, slots=True)
class InScopeRegistryCell:
    cell: EvaluationInstanceCell
    partition: Literal["TRAIN", "VALIDATION"]


@dataclass(frozen=True, slots=True)
class VerificationUnit:
    cell: EvaluationInstanceCell
    partition: Literal["TRAIN", "VALIDATION"]
    evaluation_window_days: Literal[7, 14, 21]


@dataclass(frozen=True, slots=True)
class EvaluationRegistrySnapshot:
    registry_source_status: str
    registry_identity_sha256: str | None
    actuals_authority: str | None
    forecasts_authority: str | None
    in_scope_cells: tuple[InScopeRegistryCell, ...]
    verification_units: tuple[VerificationUnit, ...]
    evaluation_instance_registry_available: bool = False
    dataset_completeness_verified: bool = False
    current_s3_daily_rowset_completeness_verified: bool = False


class EvaluationInstanceCatalogPort:
    """Port for versioned evaluation instance master catalogs."""

    def source_kind(self) -> CatalogSourceKind:
        raise NotImplementedError

    def identity_sha256(self) -> str | None:
        raise NotImplementedError

    def entries(self) -> tuple[RegistryCatalogEntry, ...]:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class UnboundEvaluationInstanceCatalog(EvaluationInstanceCatalogPort):
    def source_kind(self) -> CatalogSourceKind:
        return CatalogSourceKind.UNBOUND

    def identity_sha256(self) -> str | None:
        return None

    def entries(self) -> tuple[RegistryCatalogEntry, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class InMemoryEvaluationInstanceCatalog(EvaluationInstanceCatalogPort):
    catalog_entries: tuple[RegistryCatalogEntry, ...]
    bound_registry_identity_sha256: str | None
    catalog_source_kind: CatalogSourceKind

    def __post_init__(self) -> None:
        if self.catalog_source_kind in FORBIDDEN_CATALOG_SOURCE_KINDS:
            raise ForbiddenCatalogSourceError(
                f"forbidden catalog source kind: {self.catalog_source_kind}"
            )
        if self.bound_registry_identity_sha256 == HORIZON_H7_SUCCESS_FIXTURE_HASH:
            raise ForbiddenCatalogSourceError(
                "H=7 fixture hash cannot be used as evaluation instance catalog identity"
            )
        if self.catalog_entries and self.bound_registry_identity_sha256 is None:
            raise ValueError("non-empty catalog requires explicit registry_identity_sha256")
        if not self.catalog_entries and self.bound_registry_identity_sha256 is not None:
            raise ValueError("empty catalog must not supply a bound registry identity hash")

    def source_kind(self) -> CatalogSourceKind:
        return self.catalog_source_kind

    def identity_sha256(self) -> str | None:
        return self.bound_registry_identity_sha256

    def entries(self) -> tuple[RegistryCatalogEntry, ...]:
        return self.catalog_entries


@dataclass
class EvaluationInstanceRegistryService:
    dataset_identity: DatasetIdentity
    catalog: EvaluationInstanceCatalogPort = field(default_factory=UnboundEvaluationInstanceCatalog)

    def __post_init__(self) -> None:
        self._validate_dataset_identity()
        self._validate_catalog_source()

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

    def _validate_catalog_source(self) -> None:
        if self.catalog.source_kind() in FORBIDDEN_CATALOG_SOURCE_KINDS:
            raise ForbiddenCatalogSourceError(
                f"forbidden catalog source kind: {self.catalog.source_kind()}"
            )
        identity = self.catalog.identity_sha256()
        if identity == HORIZON_H7_SUCCESS_FIXTURE_HASH:
            raise ForbiddenCatalogSourceError(
                "H=7 fixture hash cannot be used as evaluation instance catalog identity"
            )

    def snapshot(self) -> EvaluationRegistrySnapshot:
        in_scope_cells = self.list_in_scope_cells()
        verification_units = self.list_verification_units()
        is_bound = self.catalog.source_kind() != CatalogSourceKind.UNBOUND
        registry_identity = self.catalog.identity_sha256()
        if not in_scope_cells:
            registry_identity = None
        return EvaluationRegistrySnapshot(
            registry_source_status=self._registry_source_status(),
            registry_identity_sha256=registry_identity,
            actuals_authority=V0_3_S3_ACTUALS_AUTHORITY if is_bound and in_scope_cells else None,
            forecasts_authority=V0_3_S3_FORECASTS_AUTHORITY
            if is_bound and in_scope_cells
            else None,
            in_scope_cells=in_scope_cells,
            verification_units=verification_units,
        )

    def list_in_scope_cells(self) -> tuple[InScopeRegistryCell, ...]:
        in_scope: list[InScopeRegistryCell] = []
        for entry in self.catalog.entries():
            if entry.partition == "TEST":
                continue
            if entry.partition not in EVALUATION_PARTITIONS:
                continue
            partition: Literal["TRAIN", "VALIDATION"] = entry.partition
            if not self._cell_is_in_scope(entry.cell, partition):
                continue
            in_scope.append(
                InScopeRegistryCell(
                    cell=entry.cell,
                    partition=partition,
                )
            )
        return tuple(in_scope)

    def list_verification_units(self) -> tuple[VerificationUnit, ...]:
        units: list[VerificationUnit] = []
        for in_scope_cell in self.list_in_scope_cells():
            for horizon_days in sorted(HORIZON_DAYS):
                units.append(
                    VerificationUnit(
                        cell=in_scope_cell.cell,
                        partition=in_scope_cell.partition,
                        evaluation_window_days=horizon_days,  # type: ignore[arg-type]
                    )
                )
        return tuple(units)

    def complete_season_intersects_test_partition(self, season: str) -> bool:
        return window_contains_test_partition(complete_season_window_dates(season))

    def _registry_source_status(self) -> str:
        if self.catalog.source_kind() == CatalogSourceKind.UNBOUND:
            return REGISTRY_SOURCE_STATUS_UNBOUND
        if not self.catalog.entries():
            return REGISTRY_SOURCE_STATUS_UNBOUND
        return REGISTRY_SOURCE_STATUS_UNBOUND

    def _cell_is_in_scope(
        self,
        cell: EvaluationInstanceCell,
        partition: Literal["TRAIN", "VALIDATION"],
    ) -> bool:
        if partition not in EVALUATION_PARTITIONS:
            return False
        if is_cell_level_excluded(cell):
            return False
        for horizon_days in HORIZON_DAYS:
            window_dates = horizon_window_dates(cell.forecast_cutoff_at, horizon_days)
            if not window_within_default_month_scope(window_dates, cell.season):
                return False
            if window_contains_test_partition(window_dates):
                return False
        return True
