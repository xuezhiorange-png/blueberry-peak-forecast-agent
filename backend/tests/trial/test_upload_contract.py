from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from starlette.requests import Request

import backend.app.api.trial as trial_api_module
import backend.app.trial as trial_module
from backend.app.actual_harvest_import.api_auth import (
    ActualHarvestActorContext,
    get_actual_harvest_actor,
)
from backend.app.actual_harvest_import.api_errors import ActualHarvestApiError
from backend.app.actual_harvest_import.api_schemas import (
    ActualHarvestApiCommitRequest,
    ActualHarvestApiCreateImportRequest,
)
from backend.app.actual_harvest_import.enums import (
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestRecordStatus,
    ActualHarvestValidationErrorCode,
    SourceRecordedAtAuthorityStatus,
)
from backend.app.actual_harvest_import.schemas import ActualHarvestImportRecordInput
from backend.app.trial import (
    DefaultTrialApplicationService,
    TrialActualHarvestUploadMetadata,
    TrialApiError,
    _public_import_status,
)


def _request(*, content_type: str, file_name: str, file_hash: str | None = None) -> Request:
    headers = [
        (b"content-type", content_type.encode()),
        (b"x-file-name", file_name.encode()),
    ]
    if file_hash is not None:
        headers.append((b"x-file-sha256", file_hash.encode()))
    return Request({"type": "http", "headers": headers})


def _actor(
    *,
    channel: ActualHarvestImportChannel = ActualHarvestImportChannel.CSV,
    channels: frozenset[ActualHarvestImportChannel] | None = None,
    identity: str = "trial-user",
) -> ActualHarvestActorContext:
    return ActualHarvestActorContext(
        identity=identity,
        allowed_source_systems=frozenset({"farm-system"}),
        allowed_channels=channels or frozenset({channel}),
        may_create=True,
        may_append=True,
        may_preview=True,
        may_seal=True,
        may_validate=True,
        may_commit=True,
    )


def _batch(
    *,
    source_system: str = "farm-system",
    channel: ActualHarvestImportChannel = ActualHarvestImportChannel.CSV,
    identity: str = "trial-user",
) -> SimpleNamespace:
    return SimpleNamespace(
        import_channel=channel.value,
        source_system=source_system,
        submitted_by_identity=identity,
    )


def _create_request(
    *,
    source_system: str = "farm-system",
    identity: str = "trial-user",
) -> ActualHarvestApiCreateImportRequest:
    return ActualHarvestApiCreateImportRequest(
        import_channel=ActualHarvestImportChannel.API,
        source_system=source_system,
        source_dataset="dataset-1",
        source_version="v1",
        external_batch_id="batch-1",
        idempotency_key="idempotency-1",
        submitted_at=datetime(2026, 1, 1, 8, tzinfo=UTC),
        submitted_by_identity=identity,
        raw_payload_hash="a" * 64,
        schema_version="schema-v1",
        mapping_policy_version="mapping-v1",
        validation_policy_version="validation-v1",
        source_semantics_attestation={
            "attestation_version": "attestation-v1",
            "physical_event": "FARM_PICK",
            "quantity_basis": "OBSERVED_WEIGHT",
            "quantity_unit": "KG",
            "missing_record_semantics": "UNKNOWN_NOT_ZERO",
        },
        source_semantics_attestation_hash="b" * 64,
    )


def _record() -> ActualHarvestImportRecordInput:
    return ActualHarvestImportRecordInput(
        external_logical_record_id="logical-1",
        external_revision_id="revision-1",
        source_system="farm-system",
        external_batch_id="batch-1",
        harvest_business_date=date(2026, 1, 1),
        farm_code="farm-1",
        subfarm_or_plot_code="subfarm-1",
        variety_code="variety-1",
        actual_harvest_quantity_kg="1.000000",
        source_recorded_at=datetime(2026, 1, 1, 8, tzinfo=UTC),
        source_recorded_at_authority_status=SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP,
        source_recorded_at_authority_reference_or_null="source-1",
        revision_number=1,
        record_status=ActualHarvestRecordStatus.ACTIVE,
        season_code="season-1",
        farm_timezone="UTC",
    )


def test_all_server_import_statuses_are_preserved() -> None:
    for status in ActualHarvestImportBatchStatus:
        assert _public_import_status(status.value) == status.value
        assert _public_import_status(status.value) != "BLOCKED"


@pytest.mark.asyncio
async def test_upload_parses_before_any_lifecycle_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DefaultTrialApplicationService()
    calls: list[str] = []
    session = SimpleNamespace()
    batch = _batch()
    summary = SimpleNamespace(
        validation_status="VALIDATED",
        valid_count=1,
        invalid_count=0,
        validation_run_identity="a" * 64,
        validation_result_hash="b" * 64,
    )

    async def get_batch(session, import_id):
        del session, import_id
        return batch

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    monkeypatch.setattr(
        trial_module,
        "parse_csv",
        lambda content: SimpleNamespace(records=(_record(),)),
    )

    async def run_mutation(session, operation):
        del session
        calls.append("mutate")
        return await operation()

    async def run_sync(callback):
        return callback(None)

    session.run_sync = run_sync

    async def append(session, import_id, request):
        del session, import_id, request
        calls.append("append")
        return (None, (), False)

    async def seal(session, import_id, *, actor_identity):
        del session, import_id, actor_identity
        calls.append("seal")
        return None

    async def validate(session, import_id):
        del session, import_id
        calls.append("validate")
        return summary

    monkeypatch.setattr(trial_module, "_run_mutation", run_mutation)
    monkeypatch.setattr(trial_module, "_store_upload_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(trial_module, "append_import_records", append)
    monkeypatch.setattr(trial_module, "seal_import", seal)
    monkeypatch.setattr(trial_module, "validate_import", validate)

    response = await service.upload_import(
        session,
        "import-1",
        b"csv",
        TrialActualHarvestUploadMetadata(
            file_name="harvest.csv",
            mime_type="text/csv",
            channel=ActualHarvestImportChannel.CSV,
        ),
        _actor(),
    )

    assert response.uploaded_record_count == 1
    assert response.validation_status == "VALIDATED"
    assert calls == ["mutate", "append", "mutate", "seal", "validate"]


@pytest.mark.asyncio
async def test_upload_parser_failure_does_not_mutate_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DefaultTrialApplicationService()
    calls: list[str] = []

    async def get_batch(session, import_id):
        del session, import_id
        return _batch()

    monkeypatch.setattr(trial_module, "get_import", get_batch)

    def fail_parse(content):
        del content
        raise trial_module.SpreadsheetParserError(
            ActualHarvestValidationErrorCode.CSV_STRUCTURE_INVALID,
            "invalid CSV",
        )

    monkeypatch.setattr(trial_module, "parse_csv", fail_parse)
    monkeypatch.setattr(trial_module, "append_import_records", lambda *args: calls.append("append"))
    with pytest.raises(TrialApiError) as error:
        await service.upload_import(
            None,
            "import-1",
            b"bad",
            TrialActualHarvestUploadMetadata(
                file_name="harvest.csv",
                mime_type="text/csv",
                channel=ActualHarvestImportChannel.CSV,
            ),
            _actor(),
        )
    assert error.value.status_code == 422
    assert error.value.code.value == "TRIAL_CSV_PARSE_FAILED"
    assert calls == []


@pytest.mark.asyncio
async def test_xlsx_upload_reuses_parser_and_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DefaultTrialApplicationService()
    calls: list[str] = []
    session = SimpleNamespace()
    batch = _batch(channel=ActualHarvestImportChannel.XLSX)
    summary = SimpleNamespace(
        validation_status="VALIDATED",
        valid_count=1,
        invalid_count=0,
        validation_run_identity="a" * 64,
        validation_result_hash="b" * 64,
    )

    async def get_batch(session, import_id):
        del session, import_id
        return batch

    async def run_mutation(session, operation):
        del session
        return await operation()

    async def run_sync(callback):
        return callback(None)

    session.run_sync = run_sync

    async def append(session, import_id, request):
        del session, import_id, request
        calls.append("append")
        return (None, (), False)

    async def seal(session, import_id, *, actor_identity):
        del session, import_id, actor_identity
        calls.append("seal")

    async def validate(session, import_id):
        del session, import_id
        calls.append("validate")
        return summary

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    monkeypatch.setattr(
        trial_module,
        "parse_xlsx",
        lambda content: SimpleNamespace(records=(_record(),)),
    )
    monkeypatch.setattr(trial_module, "_run_mutation", run_mutation)
    monkeypatch.setattr(trial_module, "_store_upload_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(trial_module, "append_import_records", append)
    monkeypatch.setattr(trial_module, "seal_import", seal)
    monkeypatch.setattr(trial_module, "validate_import", validate)

    response = await service.upload_import(
        session,
        "import-1",
        b"xlsx",
        TrialActualHarvestUploadMetadata(
            file_name="harvest.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            channel=ActualHarvestImportChannel.XLSX,
        ),
        _actor(channel=ActualHarvestImportChannel.XLSX),
    )

    assert response.validation_status == "VALIDATED"
    assert calls == ["append", "seal", "validate"]


@pytest.mark.asyncio
async def test_empty_upload_is_rejected_before_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DefaultTrialApplicationService()

    async def get_batch(session, import_id):
        del session, import_id
        return _batch()

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    parser_called = False

    def parser(content):
        nonlocal parser_called
        parser_called = True
        return SimpleNamespace(records=())

    monkeypatch.setattr(trial_module, "parse_csv", parser)
    with pytest.raises(TrialApiError) as error:
        await service.upload_import(
            None,
            "import-1",
            b"",
            TrialActualHarvestUploadMetadata(
                file_name="harvest.csv",
                mime_type="text/csv",
                channel=ActualHarvestImportChannel.CSV,
            ),
            _actor(),
        )
    assert error.value.status_code == 422
    assert parser_called is False


def test_upload_metadata_rejects_invalid_mime_filename_and_hash() -> None:
    invalid = (
        ("application/octet-stream", "harvest.csv", None),
        ("text/csv", "harvest.xlsx", None),
        ("text/csv", "../harvest.csv", None),
        ("text/csv", "harvest.csv", "A" * 64),
    )
    for content_type, file_name, file_hash in invalid:
        with pytest.raises(TrialApiError):
            trial_api_module._upload_metadata(
                _request(
                    content_type=content_type,
                    file_name=file_name,
                    file_hash=file_hash,
                )
            )


@pytest.mark.asyncio
async def test_upload_hash_mismatch_is_rejected_before_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DefaultTrialApplicationService()

    async def get_batch(session, import_id):
        del session, import_id
        return _batch()

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    append_called = False

    async def append(*args):
        nonlocal append_called
        append_called = True

    monkeypatch.setattr(trial_module, "append_import_records", append)
    with pytest.raises(TrialApiError) as error:
        await service.upload_import(
            None,
            "import-1",
            b"csv",
            TrialActualHarvestUploadMetadata(
                file_name="harvest.csv",
                mime_type="text/csv",
                channel=ActualHarvestImportChannel.CSV,
                sha256="0" * 64,
            ),
            _actor(),
        )
    assert error.value.code.value == "TRIAL_FILE_HASH_MISMATCH"
    assert append_called is False


@pytest.mark.asyncio
async def test_oversized_upload_is_rejected_before_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DefaultTrialApplicationService()
    monkeypatch.setattr(
        trial_module,
        "DEFAULT_SPREADSHEET_POLICY",
        SimpleNamespace(max_file_size_bytes=3),
    )

    async def get_batch(session, import_id):
        del session, import_id
        return _batch()

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    with pytest.raises(TrialApiError) as error:
        await service.upload_import(
            None,
            "import-1",
            b"1234",
            TrialActualHarvestUploadMetadata(
                file_name="harvest.csv",
                mime_type="text/csv",
                channel=ActualHarvestImportChannel.CSV,
            ),
            _actor(),
        )
    assert error.value.code.value == "TRIAL_FILE_SIZE_EXCEEDED"


@pytest.mark.asyncio
async def test_invalid_row_pagination_is_returned_without_recomputation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DefaultTrialApplicationService()

    async def get_batch(session, import_id):
        del session, import_id
        return _batch()

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    summary = SimpleNamespace(
        validation_status="VALIDATION_FAILED",
        validation_run_identity="a" * 64,
    )
    row = {
        "severity": "ERROR",
        "error_code": "ROW_INVALID",
        "record_index": 1,
        "external_logical_record_id": "logical-1",
        "external_revision_id": "revision-1",
        "field_path": "quantity",
        "message_template_id": "ROW_INVALID",
        "details": {},
    }
    seen: list[str | None] = []

    async def errors(session, import_id, *, page_size, page_token):
        del session, import_id, page_size
        seen.append(page_token)
        return summary, (row,), "next-token" if page_token is None else None

    monkeypatch.setattr(trial_module, "validation_errors", errors)
    first = await service.get_import_errors(
        None, "import-1", page_size=1, page_token=None, actor=_actor()
    )
    second = await service.get_import_errors(
        None, "import-1", page_size=1, page_token=first.next_page_token, actor=_actor()
    )
    assert len(first.rows) == len(second.rows) == 1
    assert first.next_page_token == "next-token"
    assert second.next_page_token is None
    assert seen == [None, "next-token"]


@pytest.mark.asyncio
async def test_cross_scope_upload_is_concealed(monkeypatch: pytest.MonkeyPatch) -> None:
    service = DefaultTrialApplicationService()

    async def get_batch(session, import_id):
        del session, import_id
        return _batch(source_system="other-system", identity="other-user")

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    with pytest.raises(ActualHarvestApiError) as error:
        await service.upload_import(
            None,
            "import-1",
            b"csv",
            TrialActualHarvestUploadMetadata(
                file_name="harvest.csv",
                mime_type="text/csv",
                channel=ActualHarvestImportChannel.CSV,
            ),
            _actor(),
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_actor_configuration_fails_closed_and_validates_server_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TRIAL_ACTOR_IDENTITY",
        "TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS",
        "TRIAL_ACTOR_ALLOWED_CHANNELS",
        "TRIAL_ACTOR_PERMISSIONS",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ActualHarvestApiError) as missing:
        await get_actual_harvest_actor()
    assert missing.value.status_code == 503

    monkeypatch.setenv("TRIAL_ACTOR_IDENTITY", "configured-actor")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_SOURCE_SYSTEMS", "farm-system")
    monkeypatch.setenv("TRIAL_ACTOR_ALLOWED_CHANNELS", "csv")
    monkeypatch.setenv("TRIAL_ACTOR_PERMISSIONS", "may_append,may_validate")
    actor = await get_actual_harvest_actor()
    assert actor.identity == "configured-actor"
    assert actor.may_append is True
    assert actor.may_commit is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_kwargs", "actor"),
    [
        (
            {"source_system": "other-system"},
            _actor(channels=frozenset({ActualHarvestImportChannel.API})),
        ),
        ({}, _actor()),
        (
            {"identity": "other-user"},
            _actor(channels=frozenset({ActualHarvestImportChannel.API})),
        ),
    ],
    ids=("source", "channel", "owner"),
)
async def test_create_import_scope_failure_is_forbidden_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    request_kwargs: dict[str, str],
    actor: ActualHarvestActorContext,
) -> None:
    service = DefaultTrialApplicationService()
    mutation_called = False

    async def create_batch(*args, **kwargs):
        nonlocal mutation_called
        mutation_called = True
        del args, kwargs
        raise AssertionError("create lifecycle must not run")

    monkeypatch.setattr(trial_module, "create_import", create_batch)
    with pytest.raises(ActualHarvestApiError) as error:
        await service.create_import(None, _create_request(**request_kwargs), actor)
    assert error.value.status_code == 403
    assert mutation_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "batch",
    [
        _batch(source_system="other-system"),
        _batch(identity="other-user"),
        _batch(channel=ActualHarvestImportChannel.API),
    ],
    ids=("source", "owner", "channel"),
)
async def test_get_import_scope_failure_is_concealed_before_validation(
    monkeypatch: pytest.MonkeyPatch,
    batch: SimpleNamespace,
) -> None:
    service = DefaultTrialApplicationService()
    validation_called = False

    async def get_batch(session, import_id):
        del session, import_id
        return batch

    async def read_validation(session, import_id):
        nonlocal validation_called
        validation_called = True
        del session, import_id
        raise AssertionError("validation summary must not be read")

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    monkeypatch.setattr(trial_module, "validation_summary", read_validation)
    with pytest.raises(ActualHarvestApiError) as error:
        await service.get_import(None, "import-1", _actor())
    assert error.value.status_code == 404
    assert validation_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "batch",
    [
        _batch(source_system="other-system"),
        _batch(identity="other-user"),
        _batch(channel=ActualHarvestImportChannel.API),
    ],
    ids=("source", "owner", "channel"),
)
async def test_commit_import_scope_failure_is_concealed_before_commit(
    monkeypatch: pytest.MonkeyPatch,
    batch: SimpleNamespace,
) -> None:
    service = DefaultTrialApplicationService()
    commit_called = False

    async def get_batch(session, import_id):
        del session, import_id
        return batch

    async def commit(*args, **kwargs):
        nonlocal commit_called
        commit_called = True
        del args, kwargs
        raise AssertionError("commit lifecycle must not run")

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    monkeypatch.setattr(trial_module, "commit_batch", commit)
    with pytest.raises(ActualHarvestApiError) as error:
        await service.commit_import(
            None,
            "import-1",
            ActualHarvestApiCommitRequest(validation_run_instance_identity_hash="a" * 64),
            _actor(),
        )
    assert error.value.status_code == 404
    assert commit_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("batch", "actor", "channel"),
    [
        (_batch(source_system="other-system"), _actor(), ActualHarvestImportChannel.CSV),
        (_batch(identity="other-user"), _actor(), ActualHarvestImportChannel.CSV),
        (_batch(channel=ActualHarvestImportChannel.API), _actor(), ActualHarvestImportChannel.CSV),
        (_batch(), _actor(), ActualHarvestImportChannel.XLSX),
    ],
    ids=("source", "owner", "persisted-channel", "upload-channel"),
)
async def test_upload_scope_failure_is_concealed_before_parse_or_mutation(
    monkeypatch: pytest.MonkeyPatch,
    batch: SimpleNamespace,
    actor: ActualHarvestActorContext,
    channel: ActualHarvestImportChannel,
) -> None:
    service = DefaultTrialApplicationService()
    parser_called = False
    mutation_called = False

    async def get_batch(session, import_id):
        del session, import_id
        return batch

    def parser(content):
        nonlocal parser_called
        parser_called = True
        del content
        raise AssertionError("parser must not run")

    async def mutation(*args, **kwargs):
        nonlocal mutation_called
        mutation_called = True
        del args, kwargs
        raise AssertionError("upload mutation must not run")

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    monkeypatch.setattr(trial_module, "parse_csv", parser)
    monkeypatch.setattr(trial_module, "parse_xlsx", parser)
    monkeypatch.setattr(trial_module, "_run_mutation", mutation)
    with pytest.raises(ActualHarvestApiError) as error:
        await service.upload_import(
            None,
            "import-1",
            b"raw-content",
            TrialActualHarvestUploadMetadata(
                file_name=(
                    "harvest.xlsx" if channel is ActualHarvestImportChannel.XLSX else "harvest.csv"
                ),
                mime_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    if channel is ActualHarvestImportChannel.XLSX
                    else "text/csv"
                ),
                channel=channel,
            ),
            actor,
        )
    assert error.value.status_code == 404
    assert parser_called is False
    assert mutation_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "batch",
    [
        _batch(source_system="other-system"),
        _batch(identity="other-user"),
        _batch(channel=ActualHarvestImportChannel.API),
    ],
    ids=("source", "owner", "channel"),
)
async def test_import_errors_scope_failure_is_concealed_before_read(
    monkeypatch: pytest.MonkeyPatch,
    batch: SimpleNamespace,
) -> None:
    service = DefaultTrialApplicationService()
    errors_called = False

    async def get_batch(session, import_id):
        del session, import_id
        return batch

    async def read_errors(*args, **kwargs):
        nonlocal errors_called
        errors_called = True
        del args, kwargs
        raise AssertionError("validation errors must not be read")

    monkeypatch.setattr(trial_module, "get_import", get_batch)
    monkeypatch.setattr(trial_module, "validation_errors", read_errors)
    with pytest.raises(ActualHarvestApiError) as error:
        await service.get_import_errors(
            None,
            "import-1",
            page_size=1,
            page_token=None,
            actor=_actor(),
        )
    assert error.value.status_code == 404
    assert errors_called is False
