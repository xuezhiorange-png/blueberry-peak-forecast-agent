"""Live S3-A2 catalog origin execution from bound SOURCE_002 actuals.

Injects alignment and forecast ports in-process only. Does not wire a session
into the catalog default obtain path. Does not invent tonnes. Harvest dates are
not used as forecast cutoffs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls
from sqlalchemy.orm import Session

from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow
from backend.app.s3_daily_rowset.accepted_s2_identity_alignment_evidence import (
    AcceptedS2IdentityAlignmentEvidenceProducer,
)
from backend.app.s3_daily_rowset.actuals import InMemoryS2ActualsSource, S2ActualsSourcePort
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactProductionResult,
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.forecast_artifact import IncumbentForecastArtifactAdapter
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    ReplayIdentityOriginLandingResult,
    land_replay_identity_origin_into_sync_session,
    replay_identity_origin_entries,
)
from backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source import (
    LiveAcceptedS2TrainValActualsBindingEnvelope,
    LiveAcceptedS2TrainValActualsBindOutcome,
    LiveAcceptedS2TrainValActualsSourceReasonCode,
    _bind_from_sync_session,
)
from backend.app.s3_daily_rowset.registry import CatalogSourceKind
from backend.app.s3_daily_rowset.s2_identity_alignment import S2IdentityAlignmentAdapter
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
)

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True
LIVE_FORECAST_ENVELOPE_KIND = CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
DEFAULT_DATASET_IDENTITY = DatasetIdentity(
    dataset_id=EXPECTED_DATASET_ID,
    dataset_version=EXPECTED_DATASET_VERSION,
    materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)


class LiveCatalogOriginExecutionReasonCode(StrEnum):
    ARTIFACT_PRODUCED = "ARTIFACT_PRODUCED"
    FAIL_CLOSED_NO_ASYNC_SESSION_MAKER = "FAIL_CLOSED_NO_ASYNC_SESSION_MAKER"
    FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER = (
        "FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER"
    )
    FAIL_CLOSED_ASYNC_SESSION_UNREADABLE = "FAIL_CLOSED_ASYNC_SESSION_UNREADABLE"
    FAIL_CLOSED_ACTUALS_NOT_BOUND = "FAIL_CLOSED_ACTUALS_NOT_BOUND"
    FAIL_CLOSED_NO_ORIGIN_ENTRIES = "FAIL_CLOSED_NO_ORIGIN_ENTRIES"
    FAIL_CLOSED_NO_IN_MEMORY_ACTUALS = "FAIL_CLOSED_NO_IN_MEMORY_ACTUALS"
    FAIL_CLOSED_CATALOG_NOT_PRODUCED = "FAIL_CLOSED_CATALOG_NOT_PRODUCED"


class _AsyncSessionNotObtained(RuntimeError):
    pass


class LiveCatalogOriginExecutionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    live_execution_reason_code: LiveCatalogOriginExecutionReasonCode
    catalog_reason_code: str
    catalog_identity_sha256: str | None = None
    forecast_artifact_content_identity_sha256: str | None = None
    origin_entry_count: int = 0
    landing_reason_code: str | None = None
    landed_inserted: int = 0
    landed_skipped: int = 0
    table_row_count: int | None = None
    aligned_identity_count: int = 0
    catalog_entry_count: int = 0
    parsed_train_row_count: int | None = None
    parsed_validation_row_count: int | None = None
    parsed_total_row_count: int | None = None
    test_row_count: int | None = None
    test_remains_sealed: bool = True
    uses_harvest_date_as_forecast_cutoff: bool = False
    declared_catalog_source_kind: str = LIVE_FORECAST_ENVELOPE_KIND.value
    alignment_source_kind: str | None = None
    actuals_bound: bool = False
    actuals_reason_code: str | None = None
    dataset_id: str | None = None
    dataset_version: str | None = None
    materialized_dataset_identity_sha256: str | None = None
    current_s3_daily_rowset_completeness_verified: bool = False
    no_bindable_catalog_in_repository: bool = True
    evaluation_instance_registry_available: bool = False
    default_harvest_obtain_empty: bool = True
    default_catalog_first_blocker: str = (
        CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT.value
    )
    default_session_provider_left_unset: bool = True


@dataclass(frozen=True, slots=True)
class _BindAndLandOutcome:
    bind: LiveAcceptedS2TrainValActualsBindOutcome
    landing: ReplayIdentityOriginLandingResult | None
    origin_entries: tuple[IncumbentForecastArtifactEntry, ...]


def execute_live_catalog_origin() -> LiveCatalogOriginExecutionEnvelope:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        bind_and_land = asyncio.run(_bind_and_land_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(
            LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
        )
    except Exception:
        return _fail(LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE)
    return execute_catalog_origin_from_bind_and_land(bind_and_land)


def execute_catalog_origin_from_bound_actuals(
    *,
    actuals_source: S2ActualsSourcePort,
    sync_session: Session | None = None,
    actuals_envelope: LiveAcceptedS2TrainValActualsBindingEnvelope | None = None,
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY,
) -> LiveCatalogOriginExecutionEnvelope:
    origin_entries = replay_identity_origin_entries()
    landing: ReplayIdentityOriginLandingResult | None = None
    if sync_session is not None:
        landing = land_replay_identity_origin_into_sync_session(sync_session, origin_entries)
    bind = LiveAcceptedS2TrainValActualsBindOutcome(
        envelope=actuals_envelope
        or LiveAcceptedS2TrainValActualsBindingEnvelope(
            bound=True,
            live_accepted_s2_train_val_actuals_source_bound=True,
            reason_code=LiveAcceptedS2TrainValActualsSourceReasonCode.BOUND,
            dataset_id=dataset_identity.dataset_id,
            dataset_version=dataset_identity.dataset_version,
            materialized_dataset_identity_sha256=(
                dataset_identity.materialized_dataset_identity_sha256
            ),
            test_remains_sealed=True,
        ),
        actuals_source=actuals_source,
    )
    return execute_catalog_origin_from_bind_and_land(
        _BindAndLandOutcome(bind=bind, landing=landing, origin_entries=origin_entries),
        dataset_identity=dataset_identity,
    )


def execute_catalog_origin_from_bind_and_land(
    bind_and_land: _BindAndLandOutcome,
    *,
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY,
) -> LiveCatalogOriginExecutionEnvelope:
    bind = bind_and_land.bind
    origin_entries = bind_and_land.origin_entries or replay_identity_origin_entries()
    if not bind.envelope.bound or bind.actuals_source is None:
        return _fail(
            LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_ACTUALS_NOT_BOUND,
            actuals_envelope=bind.envelope,
            origin_entry_count=len(origin_entries),
            landing=bind_and_land.landing,
        )
    if not origin_entries:
        return _fail(
            LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_NO_ORIGIN_ENTRIES,
            actuals_envelope=bind.envelope,
            landing=bind_and_land.landing,
        )
    if not isinstance(bind.actuals_source, InMemoryS2ActualsSource):
        return _fail(
            LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_NO_IN_MEMORY_ACTUALS,
            actuals_envelope=bind.envelope,
            origin_entry_count=len(origin_entries),
            landing=bind_and_land.landing,
        )

    harvest_rows = bind.actuals_source.rows
    forecast_producer = IncumbentForecastArtifactContentProducer(
        replay_rows=origin_entries,
        declared_catalog_source_kind=LIVE_FORECAST_ENVELOPE_KIND,
        uses_harvest_date_as_forecast_cutoff=False,
    )
    artifact = forecast_producer.produce()
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=dataset_identity,
        harvest_rows=harvest_rows,
    ).produce()
    alignment = S2IdentityAlignmentAdapter(evidence=evidence)
    catalog_result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=dataset_identity,
        forecast_port=IncumbentForecastArtifactAdapter(artifact=artifact),
        alignment_port=alignment,
    ).produce()

    default_catalog = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=dataset_identity,
    ).produce()
    default_harvest_empty = S2IdentityAlignmentHarvestSource().obtain() == ()
    if catalog_result.reason_code != CatalogArtifactReasonCode.ARTIFACT_PRODUCED:
        return _envelope(
            live_reason=LiveCatalogOriginExecutionReasonCode.FAIL_CLOSED_CATALOG_NOT_PRODUCED,
            catalog_result=catalog_result,
            actuals_envelope=bind.envelope,
            origin_entry_count=len(origin_entries),
            landing=bind_and_land.landing,
            artifact_sha=artifact.content_identity_sha256 if artifact is not None else None,
            aligned_identity_count=len(alignment.aligned_identities()),
            alignment_source_kind=alignment.alignment_source_kind().value,
            default_harvest_obtain_empty=default_harvest_empty,
            default_catalog_first_blocker=default_catalog.reason_code.value,
        )

    return _envelope(
        live_reason=LiveCatalogOriginExecutionReasonCode.ARTIFACT_PRODUCED,
        catalog_result=catalog_result,
        actuals_envelope=bind.envelope,
        origin_entry_count=len(origin_entries),
        landing=bind_and_land.landing,
        artifact_sha=artifact.content_identity_sha256 if artifact is not None else None,
        aligned_identity_count=len(alignment.aligned_identities()),
        alignment_source_kind=alignment.alignment_source_kind().value,
        default_harvest_obtain_empty=default_harvest_empty,
        default_catalog_first_blocker=default_catalog.reason_code.value,
    )


def produce_injected_catalog_artifact(
    *,
    harvest_rows: tuple[MaterializableRow, ...],
    origin_entries: tuple[IncumbentForecastArtifactEntry, ...],
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY,
) -> CatalogArtifactProductionResult:
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=dataset_identity,
        harvest_rows=harvest_rows,
    ).produce()
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=origin_entries,
        declared_catalog_source_kind=LIVE_FORECAST_ENVELOPE_KIND,
        uses_harvest_date_as_forecast_cutoff=False,
    ).produce()
    return EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=dataset_identity,
        forecast_port=IncumbentForecastArtifactAdapter(artifact=artifact),
        alignment_port=S2IdentityAlignmentAdapter(evidence=evidence),
    ).produce()


def _bind_and_land_sync(session: Session) -> _BindAndLandOutcome:
    bind = _bind_from_sync_session(session)
    origin_entries = replay_identity_origin_entries()
    landing: ReplayIdentityOriginLandingResult | None = None
    if bind.envelope.bound:
        landing = land_replay_identity_origin_into_sync_session(session, origin_entries)
    return _BindAndLandOutcome(bind=bind, landing=landing, origin_entries=origin_entries)


async def _bind_and_land_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> _BindAndLandOutcome:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()
        return await session.run_sync(_bind_and_land_sync)
    finally:
        await session_cm.__aexit__(None, None, None)


def _fail(
    reason: LiveCatalogOriginExecutionReasonCode,
    *,
    actuals_envelope: LiveAcceptedS2TrainValActualsBindingEnvelope | None = None,
    origin_entry_count: int = 0,
    landing: ReplayIdentityOriginLandingResult | None = None,
) -> LiveCatalogOriginExecutionEnvelope:
    return _envelope(
        live_reason=reason,
        catalog_result=None,
        actuals_envelope=actuals_envelope,
        origin_entry_count=origin_entry_count,
        landing=landing,
        artifact_sha=None,
        aligned_identity_count=0,
        alignment_source_kind=None,
        default_harvest_obtain_empty=S2IdentityAlignmentHarvestSource().obtain() == (),
        default_catalog_first_blocker=EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DEFAULT_DATASET_IDENTITY,
        )
        .produce()
        .reason_code.value,
    )


def _envelope(
    *,
    live_reason: LiveCatalogOriginExecutionReasonCode,
    catalog_result: CatalogArtifactProductionResult | None,
    actuals_envelope: LiveAcceptedS2TrainValActualsBindingEnvelope | None,
    origin_entry_count: int,
    landing: ReplayIdentityOriginLandingResult | None,
    artifact_sha: str | None,
    aligned_identity_count: int,
    alignment_source_kind: str | None,
    default_harvest_obtain_empty: bool,
    default_catalog_first_blocker: str,
) -> LiveCatalogOriginExecutionEnvelope:
    catalog_reason = (
        catalog_result.reason_code.value
        if catalog_result is not None
        else CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT.value
    )
    catalog_entries = catalog_result.catalog.entries() if catalog_result is not None else ()
    return LiveCatalogOriginExecutionEnvelope(
        live_execution_reason_code=live_reason,
        catalog_reason_code=catalog_reason,
        catalog_identity_sha256=(
            catalog_result.catalog_identity_sha256 if catalog_result is not None else None
        ),
        forecast_artifact_content_identity_sha256=artifact_sha,
        origin_entry_count=origin_entry_count,
        landing_reason_code=landing.reason_code.value if landing is not None else None,
        landed_inserted=landing.inserted if landing is not None else 0,
        landed_skipped=landing.skipped if landing is not None else 0,
        table_row_count=landing.table_row_count if landing is not None else None,
        aligned_identity_count=aligned_identity_count,
        catalog_entry_count=len(catalog_entries),
        parsed_train_row_count=(
            actuals_envelope.parsed_train_row_count if actuals_envelope is not None else None
        ),
        parsed_validation_row_count=(
            actuals_envelope.parsed_validation_row_count if actuals_envelope is not None else None
        ),
        parsed_total_row_count=(
            actuals_envelope.parsed_total_row_count if actuals_envelope is not None else None
        ),
        test_row_count=actuals_envelope.test_row_count if actuals_envelope is not None else None,
        test_remains_sealed=(
            actuals_envelope.test_remains_sealed if actuals_envelope is not None else True
        ),
        uses_harvest_date_as_forecast_cutoff=False,
        declared_catalog_source_kind=LIVE_FORECAST_ENVELOPE_KIND.value,
        alignment_source_kind=alignment_source_kind,
        actuals_bound=actuals_envelope.bound if actuals_envelope is not None else False,
        actuals_reason_code=(
            actuals_envelope.reason_code.value if actuals_envelope is not None else None
        ),
        dataset_id=actuals_envelope.dataset_id if actuals_envelope is not None else None,
        dataset_version=actuals_envelope.dataset_version if actuals_envelope is not None else None,
        materialized_dataset_identity_sha256=(
            actuals_envelope.materialized_dataset_identity_sha256
            if actuals_envelope is not None
            else None
        ),
        current_s3_daily_rowset_completeness_verified=(
            catalog_result.current_s3_daily_rowset_completeness_verified
            if catalog_result is not None
            else False
        ),
        no_bindable_catalog_in_repository=(
            catalog_result.no_bindable_catalog_in_repository if catalog_result is not None else True
        ),
        evaluation_instance_registry_available=(
            catalog_result.evaluation_instance_registry_available
            if catalog_result is not None
            else False
        ),
        default_harvest_obtain_empty=default_harvest_obtain_empty,
        default_catalog_first_blocker=default_catalog_first_blocker,
        default_session_provider_left_unset=True,
    )


def main() -> None:
    envelope = execute_live_catalog_origin()
    print(envelope.model_dump_json())


if __name__ == "__main__":
    main()
