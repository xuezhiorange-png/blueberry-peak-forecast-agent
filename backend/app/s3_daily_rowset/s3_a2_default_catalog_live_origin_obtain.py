"""Default catalog live-origin obtain from already-landed replay identity.

Reads forecast grains with the existing postgres read inside one
``AsyncSession.run_sync`` that also reuses the #476 bind family. Injects
alignment and forecast ports without rewriting frozen catalog production
bytes. Does not land grains, invent tonnes, or wire a session into the
catalog default constructor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionMakerCls
from sqlalchemy.orm import Session

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
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
    set_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.live_accepted_s2_train_val_actuals_source import (
    LiveAcceptedS2TrainValActualsBindingEnvelope,
    LiveAcceptedS2TrainValActualsBindOutcome,
    LiveAcceptedS2TrainValActualsSourceReasonCode,
    _bind_from_sync_session,
)
from backend.app.s3_daily_rowset.s2_identity_alignment import S2IdentityAlignmentAdapter
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_live_catalog_execution import (
    LIVE_FORECAST_ENVELOPE_KIND,
    produce_injected_catalog_artifact,
)
from backend.app.s3_daily_rowset.schemas import (
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_VERSION,
    EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
    DatasetIdentity,
)

HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF = True
DEFAULT_DATASET_IDENTITY = DatasetIdentity(
    dataset_id=EXPECTED_DATASET_ID,
    dataset_version=EXPECTED_DATASET_VERSION,
    materialized_dataset_identity_sha256=EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256,
)


class DefaultCatalogLiveOriginObtainReasonCode(StrEnum):
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


class DefaultCatalogLiveOriginObtainEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    obtain_reason_code: DefaultCatalogLiveOriginObtainReasonCode
    catalog_reason_code: str
    catalog_identity_sha256: str | None = None
    forecast_artifact_content_identity_sha256: str | None = None
    origin_entry_count: int = 0
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
class _BindAndReadOutcome:
    bind: LiveAcceptedS2TrainValActualsBindOutcome
    origin_entries: tuple[IncumbentForecastArtifactEntry, ...]


def obtain_default_catalog_from_live_origin() -> DefaultCatalogLiveOriginObtainEnvelope:
    try:
        from backend.app.db.session import AsyncSessionMaker as live_async_session_maker
    except Exception:
        return _fail(DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    if live_async_session_maker is None or not isinstance(
        live_async_session_maker, _AsyncSessionMakerCls
    ):
        return _fail(DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_NO_ASYNC_SESSION_MAKER)
    try:
        bind_and_read = asyncio.run(_bind_and_read_with_session_maker(live_async_session_maker))
    except _AsyncSessionNotObtained:
        return _fail(
            DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_NOT_OBTAINED_FROM_SESSION_MAKER
        )
    except Exception:
        return _fail(DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_ASYNC_SESSION_UNREADABLE)
    return _produce_from_bind_and_origin(bind_and_read)


def obtain_default_catalog_from_landed_origin(
    *,
    actuals_source: S2ActualsSourcePort,
    sync_session: Session,
    actuals_envelope: LiveAcceptedS2TrainValActualsBindingEnvelope | None = None,
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY,
) -> DefaultCatalogLiveOriginObtainEnvelope:
    origin_entries = _read_origin_from_held_session(sync_session)
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
    return _produce_from_bind_and_origin(
        _BindAndReadOutcome(bind=bind, origin_entries=origin_entries),
        dataset_identity=dataset_identity,
    )


def _read_origin_from_held_session(
    session: Session,
) -> tuple[IncumbentForecastArtifactEntry, ...]:
    set_v0_2_live_postgres_session_provider(lambda: session)
    try:
        return read_bindable_replay_identity_rows()
    finally:
        clear_v0_2_live_postgres_session_provider()


def _bind_and_read_sync(session: Session) -> _BindAndReadOutcome:
    bind = _bind_from_sync_session(session)
    origin_entries = _read_origin_from_held_session(session)
    return _BindAndReadOutcome(bind=bind, origin_entries=origin_entries)


async def _bind_and_read_with_session_maker(
    live_async_session_maker: _AsyncSessionMakerCls[AsyncSession],
) -> _BindAndReadOutcome:
    session_cm = live_async_session_maker()
    try:
        session = await session_cm.__aenter__()
    except Exception as exc:
        raise _AsyncSessionNotObtained() from exc
    try:
        if session is None:
            raise _AsyncSessionNotObtained()
        return await session.run_sync(_bind_and_read_sync)
    finally:
        await session_cm.__aexit__(None, None, None)


def _produce_from_bind_and_origin(
    bind_and_read: _BindAndReadOutcome,
    *,
    dataset_identity: DatasetIdentity = DEFAULT_DATASET_IDENTITY,
) -> DefaultCatalogLiveOriginObtainEnvelope:
    bind = bind_and_read.bind
    origin_entries = bind_and_read.origin_entries
    if not bind.envelope.bound or bind.actuals_source is None:
        return _fail(
            DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_ACTUALS_NOT_BOUND,
            actuals_envelope=bind.envelope,
            origin_entries=origin_entries,
        )
    if not origin_entries:
        return _fail(
            DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_NO_ORIGIN_ENTRIES,
            actuals_envelope=bind.envelope,
            origin_entries=origin_entries,
        )
    if not isinstance(bind.actuals_source, InMemoryS2ActualsSource):
        return _fail(
            DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_NO_IN_MEMORY_ACTUALS,
            actuals_envelope=bind.envelope,
            origin_entries=origin_entries,
        )

    catalog_result = produce_injected_catalog_artifact(
        harvest_rows=bind.actuals_source.rows,
        origin_entries=origin_entries,
        dataset_identity=dataset_identity,
    )
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=origin_entries,
        declared_catalog_source_kind=LIVE_FORECAST_ENVELOPE_KIND,
        uses_harvest_date_as_forecast_cutoff=False,
    ).produce()
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=dataset_identity,
        harvest_rows=bind.actuals_source.rows,
    ).produce()
    alignment = S2IdentityAlignmentAdapter(evidence=evidence)
    if catalog_result.reason_code != CatalogArtifactReasonCode.ARTIFACT_PRODUCED:
        return _envelope(
            obtain_reason=DefaultCatalogLiveOriginObtainReasonCode.FAIL_CLOSED_CATALOG_NOT_PRODUCED,
            catalog_result=catalog_result,
            actuals_envelope=bind.envelope,
            origin_entries=origin_entries,
            artifact_sha=artifact.content_identity_sha256 if artifact is not None else None,
            aligned_identity_count=len(alignment.aligned_identities()),
            alignment_source_kind=alignment.alignment_source_kind().value,
        )
    return _envelope(
        obtain_reason=DefaultCatalogLiveOriginObtainReasonCode.ARTIFACT_PRODUCED,
        catalog_result=catalog_result,
        actuals_envelope=bind.envelope,
        origin_entries=origin_entries,
        artifact_sha=artifact.content_identity_sha256 if artifact is not None else None,
        aligned_identity_count=len(alignment.aligned_identities()),
        alignment_source_kind=alignment.alignment_source_kind().value,
    )


def _fail(
    reason: DefaultCatalogLiveOriginObtainReasonCode,
    *,
    actuals_envelope: LiveAcceptedS2TrainValActualsBindingEnvelope | None = None,
    origin_entries: tuple[IncumbentForecastArtifactEntry, ...] = (),
) -> DefaultCatalogLiveOriginObtainEnvelope:
    return _envelope(
        obtain_reason=reason,
        catalog_result=None,
        actuals_envelope=actuals_envelope,
        origin_entries=origin_entries,
        artifact_sha=None,
        aligned_identity_count=0,
        alignment_source_kind=None,
    )


def _envelope(
    *,
    obtain_reason: DefaultCatalogLiveOriginObtainReasonCode,
    catalog_result: CatalogArtifactProductionResult | None,
    actuals_envelope: LiveAcceptedS2TrainValActualsBindingEnvelope | None,
    origin_entries: tuple[IncumbentForecastArtifactEntry, ...],
    artifact_sha: str | None,
    aligned_identity_count: int,
    alignment_source_kind: str | None,
) -> DefaultCatalogLiveOriginObtainEnvelope:
    catalog_reason = (
        catalog_result.reason_code.value
        if catalog_result is not None
        else CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT.value
    )
    catalog_entries = catalog_result.catalog.entries() if catalog_result is not None else ()
    default_catalog = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DEFAULT_DATASET_IDENTITY,
    ).produce()
    return DefaultCatalogLiveOriginObtainEnvelope(
        obtain_reason_code=obtain_reason,
        catalog_reason_code=catalog_reason,
        catalog_identity_sha256=(
            catalog_result.catalog_identity_sha256 if catalog_result is not None else None
        ),
        forecast_artifact_content_identity_sha256=artifact_sha,
        origin_entry_count=len(origin_entries),
        table_row_count=len(origin_entries),
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
        default_harvest_obtain_empty=S2IdentityAlignmentHarvestSource().obtain() == (),
        default_catalog_first_blocker=default_catalog.reason_code.value,
        default_session_provider_left_unset=True,
    )


def main() -> None:
    envelope = obtain_default_catalog_from_live_origin()
    print(envelope.model_dump_json())


if __name__ == "__main__":
    main()
