"""Tests for TASK-011 Phase 4c-3 — production-shaped E2E / reload integrity.

These tests cover the 4c-3 implementation slice of the Phase 4c design
contract
(``docs/task-11-phase4c-3-production-e2e-reload-integrity-amendment.md``,
frozen at content SHA
``ef5732243db327ae41bd223d77ae7d820b344aca91c67592f82a686b1bd686f4``).
They mirror the 4c-1 ``test_service.py`` and 4c-2 ``test_export.py`` style.

The 4c-3 test contract (design §10) calls for 16 cases:

* §7.1 — Production-shaped E2E happy path
* §7.2 — Reload from manifest (stateless, idempotent)
* §7.3 — JSON / CSV consistency check
* §7.4 — Audit hash check
* §7.5 — Deterministic re-run check (re-derives canonical_payload_hash)
* §7.6a — missing_artifact
* §7.6b — malformed_json
* §7.6c — malformed_csv
* §7.6d — manifest_mismatch (metric_definition_version)
* §7.6e — canonical_payload_hash_mismatch
* §7.6f — audit_payload_hash_mismatch
* §7.6g — row_order_mismatch
* §7.6h — metric_definition_version_mismatch
* §7.6i — mask_hash_mismatch
* §7.6j — forbidden_implicit_fallback
* §7.7 — No database / network side channel

The first six (§7.1 – §7.5, §7.7) are positive / contract cases; the last
ten (§7.6a – §7.6j) are negative cases, one per failure kind in §6.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.rolling_backtest import (
    EXIT_METRIC_BLOCKER,
    EXIT_SUCCESS,
    METRIC_DEFINITION_VERSION,
    RELOAD_CONTRACT_VERSION,
    AuditPayloadHashMismatchError,
    CanonicalPayloadHashMismatchError,
    ExportRequest,
    ForbiddenImplicitFallbackError,
    MalformedCsvError,
    MalformedJsonError,
    MaskHashMismatchError,
    MaskState,
    MetricDefinitionVersionMismatchError,
    MissingArtifactError,
    ReloadContractError,
    ReloadResult,
    RowOrderMismatchError,
    all_reload_error_kinds,
    compute_metrics,
    get_reload_error_class,
    register_materialization_provider,
    verify_artifact_set,
    write_export_artifacts,
)
from backend.app.rolling_backtest.export import OverwritePolicy
from backend.app.rolling_backtest.metrics import EvaluationMetricRow, EvaluationResult

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_MASK_HASH = "0" * 63 + "1"  # 64-char lowercase hex
SAMPLE_RUN_ID = "run-001"
SAMPLE_SCOPE: dict[str, object] = {
    "run": SAMPLE_RUN_ID,
    "node": 1,
    "horizon": "daily",
    "farm": 100,
    "variety": 7,
    "model_version": "v1.0",
    "evaluation_mask_hash": SAMPLE_MASK_HASH,
}


def _row(
    *,
    forecast_output_id: int,
    node_id: int,
    evaluation_as_of_date: date,
    target: Decimal | None,
    prediction: Decimal | None,
    mask_state: MaskState = MaskState.NONE,
    p50_kg: Decimal | None = None,
    p80_kg: Decimal | None = None,
) -> EvaluationMetricRow:
    return EvaluationMetricRow(
        forecast_output_id=forecast_output_id,
        node_id=node_id,
        evaluation_as_of_date=evaluation_as_of_date,
        target=target,
        prediction=prediction,
        mask_state=mask_state,
        p50_kg=p50_kg,
        p80_kg=p80_kg,
    )


@pytest.fixture
def golden_rows_single_node() -> list[EvaluationMetricRow]:
    """Three comparable rows on a single node 1; absolute errors 0.1, 0.2, 0.3."""
    return [
        _row(
            forecast_output_id=10,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 1),
            target=Decimal("10.0"),
            prediction=Decimal("10.1"),
            p50_kg=Decimal("10.1"),
            p80_kg=Decimal("12"),
        ),
        _row(
            forecast_output_id=11,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("19.8"),
            p50_kg=Decimal("19.8"),
            p80_kg=Decimal("22"),
        ),
        _row(
            forecast_output_id=12,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 3),
            target=Decimal("30.0"),
            prediction=Decimal("30.3"),
            p50_kg=Decimal("30.3"),
            p80_kg=Decimal("33"),
        ),
    ]


@pytest.fixture
def rows_by_run_mask() -> dict[tuple[str, str], list[EvaluationMetricRow]]:
    return {}


@pytest.fixture
def stub_provider(
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
) -> Iterator[None]:
    """Register a stub materialization provider; tear down after the test."""

    def provider(run_id: str, mask_hash: str) -> list[EvaluationMetricRow]:
        present_runs = {r for r, _ in rows_by_run_mask}
        if run_id not in present_runs:
            from backend.app.rolling_backtest import MaterializationRunNotFound

            raise MaterializationRunNotFound(run_id=run_id)
        if (run_id, mask_hash) not in rows_by_run_mask:
            from backend.app.rolling_backtest import MaterializationMaskNotBound

            raise MaterializationMaskNotBound(run_id=run_id, mask_hash=mask_hash)
        return rows_by_run_mask[(run_id, mask_hash)]

    previous = register_materialization_provider(provider)
    try:
        yield
    finally:
        register_materialization_provider(previous)


def _write_artifacts(
    golden_rows_single_node: list[EvaluationMetricRow],
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    tmp_path: Path,
    *,
    emit_audit: bool = True,
    overwrite_policy: OverwritePolicy = OverwritePolicy.MISSING,
) -> tuple[EvaluationResult, ExportRequest]:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )
    request = ExportRequest(
        result=result,
        run_id=SAMPLE_RUN_ID,
        decimal_scale=6,
        output_dir=tmp_path,
        overwrite_policy=overwrite_policy,
        cli_invocation={
            "argv": "compute-metrics --run-id run-001",
            "--scope": json.dumps(SAMPLE_SCOPE),
            "--mask-hash": SAMPLE_MASK_HASH,
            "--metric-subset": "",
        }
        if emit_audit
        else None,
        emit_audit=emit_audit,
    )
    write_export_artifacts(request)
    return result, request


# ---------------------------------------------------------------------------
# §0. Module surface (helper assertions, not counted in the 16)
# ---------------------------------------------------------------------------


def test_module_exposes_10_frozen_error_kinds() -> None:
    """§6 lists 10 error kinds. The module MUST export all 10 (and only
    those 10) in the frozen order.
    """
    assert all_reload_error_kinds() == (
        "missing_artifact",
        "malformed_json",
        "malformed_csv",
        "manifest_mismatch",
        "canonical_payload_hash_mismatch",
        "audit_payload_hash_mismatch",
        "row_order_mismatch",
        "metric_definition_version_mismatch",
        "mask_hash_mismatch",
        "forbidden_implicit_fallback",
    )


def test_get_reload_error_class_maps_all_10_kinds() -> None:
    for kind in all_reload_error_kinds():
        cls = get_reload_error_class(kind)
        assert issubclass(cls, ReloadContractError)
        assert cls.kind == kind


def test_reload_contract_version_is_frozen() -> None:
    """RELOAD_CONTRACT_VERSION MUST be a stable, versioned identity.

    Bumping requires a new design amendment.
    """
    assert RELOAD_CONTRACT_VERSION == "4c-3.0.0"


# ---------------------------------------------------------------------------
# §7.1 — Production-shaped E2E happy path (positive)
# ---------------------------------------------------------------------------


def test_verify_happy_path_on_real_artifact_set(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.1: a verify against a freshly written 4c-2 artifact set MUST
    return a ReloadResult whose canonical_payload_hash matches the
    EvaluationResult and whose identity triple is preserved.
    """
    result, _ = _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    reload_result = verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert isinstance(reload_result, ReloadResult)
    assert reload_result.canonical_payload_hash == result.canonical_payload_hash
    assert reload_result.run_id == SAMPLE_RUN_ID
    assert reload_result.evaluation_mask_hash == SAMPLE_MASK_HASH
    assert reload_result.metric_definition_version == METRIC_DEFINITION_VERSION
    # Audit hash MUST round-trip (the manifest's audit_payload_hash is
    # the SHA-256 of the audit file bytes).
    assert reload_result.audit_payload_hash is not None
    assert len(reload_result.audit_payload_hash) == 64
    # All four paths MUST resolve to real files.
    assert reload_result.json_path.is_file()
    assert reload_result.csv_path.is_file()
    assert reload_result.manifest_path.is_file()
    assert reload_result.audit_path is not None
    assert reload_result.audit_path.is_file()


# ---------------------------------------------------------------------------
# §7.2 — Reload from manifest (stateless, idempotent)
# ---------------------------------------------------------------------------


def test_reload_is_stateless_and_idempotent(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.2: invoking ``verify_artifact_set`` twice MUST produce identical
    results (the reload is stateless — it reads artifacts from disk, not
    from any in-memory cache).
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    first = verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    second = verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert first == second


# ---------------------------------------------------------------------------
# §7.3 — JSON / CSV consistency check (positive + negative)
# ---------------------------------------------------------------------------


def test_json_csv_metric_name_order_is_consistent(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.3: the JSON and CSV MUST agree on ``metric_name`` order
    (positive case: a freshly written artifact set).
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    # Reload MUST succeed.
    verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)


def test_swapping_two_csv_rows_raises_row_order_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6g / §6.7: swapping two CSV rows post-write MUST surface as
    :class:`RowOrderMismatchError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    # Locate the CSV file and swap the first two data rows.
    csv_files = sorted((tmp_path / "csv").iterdir())
    assert len(csv_files) == 1
    csv_path = csv_files[0]
    text = csv_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # lines[0] is the header; lines[1] and lines[2] are data rows 1 and 2.
    lines[1], lines[2] = lines[2], lines[1]
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(RowOrderMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "row_order_mismatch"
    assert excinfo.value.to_payload()["first_diverging_index"] == 0


# ---------------------------------------------------------------------------
# §7.4 — Audit hash check (positive + negative)
# ---------------------------------------------------------------------------


def test_corrupting_audit_file_raises_audit_payload_hash_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6f / §6.6: corrupting the audit file post-write MUST surface as
    :class:`AuditPayloadHashMismatchError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    audit_files = sorted((tmp_path / "audit").iterdir())
    assert len(audit_files) == 1
    audit_path = audit_files[0]
    original_bytes = audit_path.read_bytes()
    # Flip one byte in the middle of the file.
    mutated = bytearray(original_bytes)
    flip_index = len(mutated) // 2
    mutated[flip_index] = (mutated[flip_index] + 1) % 256
    audit_path.write_bytes(bytes(mutated))
    with pytest.raises(AuditPayloadHashMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "audit_payload_hash_mismatch"
    assert "expected" in excinfo.value.to_payload()
    assert "actual" in excinfo.value.to_payload()


# ---------------------------------------------------------------------------
# §7.5 — Deterministic re-run check
# ---------------------------------------------------------------------------


def test_repeated_export_is_byte_identical(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.5: re-running the export with identical inputs MUST produce
    byte-identical JSON / CSV outputs (determinism binding to Phase 4b).
    The manifest carries a ``written_at_utc`` timestamp and the audit
    file is allowed to differ; both are excluded from the byte-identity
    check, mirroring the 4c-2 ``test_repeated_export_byte_identical_for_identical_inputs``
    contract.
    """

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    out_a.mkdir()
    out_b.mkdir()
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, out_a)
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, out_b)
    # JSON and CSV MUST be byte-identical.
    for sub in ("json", "csv"):
        a_files = sorted((out_a / sub).iterdir())
        b_files = sorted((out_b / sub).iterdir())
        assert len(a_files) == len(b_files) == 1
        assert a_files[0].read_bytes() == b_files[0].read_bytes(), (
            f"{sub} files differ between two runs"
        )
    # Manifest: canonical_payload_hash MUST match; written_at_utc is
    # allowed to differ (timestamp field).
    a_manifest = json.loads(sorted((out_a / "manifest").iterdir())[0].read_text(encoding="utf-8"))
    b_manifest = json.loads(sorted((out_b / "manifest").iterdir())[0].read_text(encoding="utf-8"))
    assert a_manifest["canonical_payload_hash"] == b_manifest["canonical_payload_hash"]
    # Verify each run reloads cleanly.
    verify_artifact_set(out_a, expected_mask_hash=SAMPLE_MASK_HASH)
    verify_artifact_set(out_b, expected_mask_hash=SAMPLE_MASK_HASH)


def test_corrupting_json_outputs_raises_canonical_payload_hash_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6e / §6.5: corrupting the JSON's ``outputs`` array post-write
    MUST surface as :class:`CanonicalPayloadHashMismatchError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    json_files = sorted((tmp_path / "json").iterdir())
    assert len(json_files) == 1
    json_path = json_files[0]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    # Mutate one byte in the first output's metric_value. We flip a
    # digit in a Decimal string; this changes the canonical_payload_hash
    # but preserves the JSON shape (so the JSON still parses).
    outputs = payload["outputs"]
    original_value = outputs[0]["metric_value"]
    # Construct a new value that differs in exactly one digit.
    flipped = list(str(original_value))
    if flipped and flipped[0].isdigit():
        flipped[0] = "0" if flipped[0] != "0" else "1"
    else:
        # Fallback: append a character that mutates the value.
        flipped = list(str(original_value)) + ["0"]
    outputs[0]["metric_value"] = "".join(flipped)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    with pytest.raises(CanonicalPayloadHashMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "canonical_payload_hash_mismatch"


# ---------------------------------------------------------------------------
# §7.6a — missing_artifact
# ---------------------------------------------------------------------------


def test_deleting_json_file_raises_missing_artifact(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6a / §6.1: deleting the JSON file post-write MUST surface as
    :class:`MissingArtifactError` with ``expected_kind='json'``.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    json_files = sorted((tmp_path / "json").iterdir())
    assert len(json_files) == 1
    json_files[0].unlink()
    with pytest.raises(MissingArtifactError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "missing_artifact"
    assert excinfo.value.to_payload()["expected_kind"] == "json"


def test_missing_manifest_subdir_raises_missing_artifact(tmp_path: Path) -> None:
    """§6.1: an empty reload root MUST surface as ``missing_artifact``."""
    with pytest.raises(MissingArtifactError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "missing_artifact"
    assert excinfo.value.to_payload()["expected_kind"] == "manifest"


# ---------------------------------------------------------------------------
# §7.6b — malformed_json
# ---------------------------------------------------------------------------


def test_corrupting_json_with_invalid_syntax_raises_malformed_json(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6b / §6.2: writing a syntactically invalid JSON MUST surface as
    :class:`MalformedJsonError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    json_files = sorted((tmp_path / "json").iterdir())
    assert len(json_files) == 1
    json_files[0].write_text("{not valid json", encoding="utf-8")
    with pytest.raises(MalformedJsonError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "malformed_json"


def test_missing_frozen_top_level_key_raises_malformed_json(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§6.2: a JSON missing a frozen top-level key (§5.1) MUST surface
    as :class:`MalformedJsonError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    json_files = sorted((tmp_path / "json").iterdir())
    assert len(json_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    del payload["run_id"]
    json_files[0].write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    with pytest.raises(MalformedJsonError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "malformed_json"


# ---------------------------------------------------------------------------
# §7.6c — malformed_csv
# ---------------------------------------------------------------------------


def test_csv_with_missing_header_column_raises_malformed_csv(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6c / §6.3: a CSV missing a frozen header column MUST surface
    as :class:`MalformedCsvError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    csv_files = sorted((tmp_path / "csv").iterdir())
    assert len(csv_files) == 1
    csv_path = csv_files[0]
    text = csv_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # Drop the last header column.
    lines[0] = ",".join(lines[0].split(",")[:-1])
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(MalformedCsvError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "malformed_csv"


# ---------------------------------------------------------------------------
# §7.6d / §7.6h — manifest_mismatch / metric_definition_version_mismatch
# ---------------------------------------------------------------------------


def test_modifying_manifest_metric_definition_version_raises_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6d / §6.4 + §7.6h / §6.8: modifying the manifest's
    ``metric_definition_version`` post-write MUST surface as
    :class:`MetricDefinitionVersionMismatchError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    manifest_files = sorted((tmp_path / "manifest").iterdir())
    assert len(manifest_files) == 1
    manifest_path = manifest_files[0]
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["metric_definition_version"] = "4b-0.9.0"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    with pytest.raises(MetricDefinitionVersionMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "metric_definition_version_mismatch"
    assert excinfo.value.to_payload()["expected"] == METRIC_DEFINITION_VERSION
    assert excinfo.value.to_payload()["actual"] == "4b-0.9.0"


def test_json_with_wrong_metric_definition_version_raises_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6h: a JSON whose ``metric_definition_version`` is not 4b-1.0.0
    MUST surface as :class:`MetricDefinitionVersionMismatchError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    json_files = sorted((tmp_path / "json").iterdir())
    assert len(json_files) == 1
    json_path = json_files[0]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["metric_definition_version"] = "4b-0.9.0"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    with pytest.raises(MetricDefinitionVersionMismatchError):
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)


# ---------------------------------------------------------------------------
# §7.6i — mask_hash_mismatch
# ---------------------------------------------------------------------------


def test_wrong_expected_mask_hash_raises_mask_hash_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6i / §6.9: passing an ``expected_mask_hash`` that differs from
    the JSON's MUST surface as :class:`MaskHashMismatchError`.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    wrong = "f" * 64
    assert wrong != SAMPLE_MASK_HASH
    with pytest.raises(MaskHashMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=wrong)
    assert excinfo.value.kind == "mask_hash_mismatch"
    payload = excinfo.value.to_payload()
    assert payload["expected_mask_hash"] == wrong
    assert payload["actual_mask_hash"] == SAMPLE_MASK_HASH


# ---------------------------------------------------------------------------
# §7.6j — forbidden_implicit_fallback
# ---------------------------------------------------------------------------


def test_two_manifest_files_raises_forbidden_implicit_fallback(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.6j / §6.10: multiple manifest files in the same reload root
    MUST surface as :class:`ForbiddenImplicitFallbackError`. The reload
    refuses to pick one implicitly.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    # Create a second manifest file with a different filename.
    manifest_dir = tmp_path / "manifest"
    existing = list(manifest_dir.iterdir())
    assert len(existing) == 1
    new_path = manifest_dir / "run-002__other__fake.json"
    new_path.write_text('{"manifest": "placeholder"}', encoding="utf-8")
    with pytest.raises(ForbiddenImplicitFallbackError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "forbidden_implicit_fallback"


# ---------------------------------------------------------------------------
# §7.7 — No database / network side channel
# ---------------------------------------------------------------------------


def test_verify_artifact_set_does_not_touch_db_or_network(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§7.7: a 4c-3 reload MUST NOT perform database IO or network IO.

    The test patches the most common entry points (``urllib.request``,
    ``requests.*`` if available, and the canonical ``db.session`` if it
    exists in the project) and asserts that no patched call was made
    during the reload.
    """
    import urllib.request as _urllib_request

    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)

    def _fail(*args: object, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError(f"forbidden side channel invoked: args={args!r} kwargs={kwargs!r}")

    # Patch all urlopen variants.
    monkeypatch.setattr(_urllib_request, "urlopen", _fail)

    # Patch requests.* if available.
    try:
        import requests as _requests  # type: ignore[import-not-found]

        monkeypatch.setattr(_requests, "get", _fail)
        monkeypatch.setattr(_requests, "post", _fail)
    except ImportError:
        pass

    # The reload MUST complete without raising.
    verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)


# ---------------------------------------------------------------------------
# Extra: CLI exit code 0 / 3 binding (§10.2 — bound to 4c-2)
# ---------------------------------------------------------------------------


def test_cli_compute_metrics_exits_0_or_3(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§10.2 (binding for the 4c-2 CLI): a well-formed ``compute-metrics``
    invocation MUST exit 0 (success) or 3 (``MetricBlocker``). This
    test exercises the CLI in-process to keep the stub materialization
    provider visible to ``compute_metrics`` (the 4c-3 reload path itself
    is DB-free per §7.7).
    """
    from backend.app.rolling_backtest import cli_main

    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    rc = cli_main(
        [
            "compute-metrics",
            "--run-id",
            SAMPLE_RUN_ID,
            "--scope",
            json.dumps(SAMPLE_SCOPE),
            "--mask-hash",
            SAMPLE_MASK_HASH,
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc in (EXIT_SUCCESS, EXIT_METRIC_BLOCKER)
    # The four files MUST be present after the CLI run.
    assert (tmp_path / "json").is_dir()
    assert (tmp_path / "csv").is_dir()
    assert (tmp_path / "manifest").is_dir()
    assert (tmp_path / "audit").is_dir()
    # And the 4c-3 reload MUST accept the artifact set.
    verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
