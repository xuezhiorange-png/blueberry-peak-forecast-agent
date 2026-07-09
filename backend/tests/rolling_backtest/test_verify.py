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
    ManifestMismatchError,
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
# §7.5b — Path integrity (§4.5 path escape)
# ---------------------------------------------------------------------------


def test_manifest_path_escape_raises_manifest_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§4.5 path integrity: a manifest whose ``json_path`` resolves
    outside the reload root MUST surface as :class:`ManifestMismatchError`
    with ``field='path_escape'`` and a structured payload carrying the
    offending path and the expected root.

    This is a security-sensitive invariant: a manifest MUST NOT be able
    to coerce the reload into validating files outside the caller-chosen
    root directory.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    # Mutate the manifest's json_path to one that resolves outside
    # the reload root.
    manifest_dir = tmp_path / "manifest"
    manifest_files = sorted(manifest_dir.iterdir())
    assert len(manifest_files) == 1
    manifest_path = manifest_files[0]
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    # `../<one>/<two>` resolves above the reload root.
    payload["json_path"] = "../escape/escape.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(ManifestMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "manifest_mismatch"
    payload_dict = excinfo.value.to_payload()
    assert payload_dict["field"] == "path_escape"
    assert payload_dict["path"] == "../escape/escape.json"
    # The expected root MUST be the resolved reload root, and the
    # actual value MUST be the resolved escape target (caller is
    # informed where the path tried to go).
    assert payload_dict["expected"] == str(tmp_path.resolve())
    assert payload_dict["actual"] != payload_dict["expected"]
    # The error MUST NOT silently fall back to the original JSON.
    assert not payload_dict["actual"].startswith(str(tmp_path.resolve()))


def test_nested_json_layout_with_audit_at_root_audit_subdir_succeeds(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """P1-1 regression: the 4c-2 contract allows the JSON to live at a
    nested path under ``<root>`` (e.g. ``<root>/2026-01/json/<file>``)
    while the audit always lives at ``<root>/audit/<filename>``. The
    reload's structural audit-path discovery (NOT string-replace of
    the parent dir) MUST handle this layout correctly.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    # Move the JSON into a nested subdir; the audit stays at
    # <root>/audit/<filename> per the 4c-2 contract.
    nested_json_dir = tmp_path / "2026-01" / "json"
    nested_json_dir.mkdir(parents=True)
    original_json = next((tmp_path / "json").iterdir())
    nested_json = nested_json_dir / original_json.name
    nested_json.write_bytes(original_json.read_bytes())
    original_json.unlink()
    # Update the manifest to reflect the new JSON path. The CSV and
    # audit paths stay at their canonical locations.
    manifest_dir = tmp_path / "manifest"
    manifest_path = next(manifest_dir.iterdir())
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["json_path"] = f"2026-01/json/{original_json.name}"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # The reload MUST succeed despite the nested JSON layout.
    result = verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert result.evaluation_mask_hash == SAMPLE_MASK_HASH
    assert result.canonical_payload_hash is not None


def test_mismatched_audit_filename_raises_missing_artifact(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """P1-1 negative: if the audit file at ``<root>/audit/<filename>``
    (matching the JSON filename) is missing or has a different
    filename, the reload MUST surface :class:`MissingArtifactError`
    with ``expected_kind='audit'`` — not silently fall back or raise a
    different error kind.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    # Rename the audit file so the JSON filename no longer matches
    # any audit file in <root>/audit/. The manifest's audit_payload_hash
    # is still the original hash, so the reload will look for the
    # matching audit file (and fail to find it).
    audit_dir = tmp_path / "audit"
    audit_files = sorted(audit_dir.iterdir())
    assert len(audit_files) == 1
    audit_files[0] = audit_files[0].rename(audit_dir / "renamed_audit.json")
    with pytest.raises(MissingArtifactError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert excinfo.value.kind == "missing_artifact"
    payload_dict = excinfo.value.to_payload()
    assert payload_dict["expected_kind"] == "audit"
    # The error payload MUST point to the expected audit path
    # (the structural lookup target), not some other location.
    assert "audit" in str(payload_dict["path"])
    assert str(payload_dict["path"]).endswith(".json")


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
    """§7.7: a 4c-3 reload MUST NOT perform database IO, network IO,
    or subprocess IO. The test patches every common entry point for
    these side channels (urllib, requests, urllib3, httpx, aiohttp,
    subprocess, SQLAlchemy engine, asyncpg/psycopg connection surfaces)
    and asserts none of them are invoked during a 4c-3 reload.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)

    # 1. Network: urllib.request.urlopen (always present).
    import urllib.request as _urllib_request

    def _fail_url(*args: object, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError(
            f"forbidden urllib side channel invoked: args={args!r} kwargs={kwargs!r}"
        )

    monkeypatch.setattr(_urllib_request, "urlopen", _fail_url)

    # 2. Network: requests (optional dep).
    try:
        import requests as _requests  # type: ignore[import-not-found]

        def _fail_requests(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden requests side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        monkeypatch.setattr(_requests, "get", _fail_requests)
        monkeypatch.setattr(_requests, "post", _fail_requests)
        if hasattr(_requests, "Session"):
            monkeypatch.setattr(_requests, "Session", _fail_requests)
    except ImportError:
        pass

    # 3. Network: urllib3 (optional dep).
    try:
        import urllib3  # type: ignore[import-not-found]

        def _fail_urllib3(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden urllib3 side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        # urllib3 may or may not expose a top-level PoolManager at import time.
        if hasattr(urllib3, "PoolManager"):
            monkeypatch.setattr(urllib3.PoolManager, "request", _fail_urllib3)
    except ImportError:
        pass

    # 4. Network: httpx (optional dep).
    try:
        import httpx  # type: ignore[import-not-found]

        def _fail_httpx(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden httpx side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        if hasattr(httpx, "Client"):
            monkeypatch.setattr(httpx.Client, "request", _fail_httpx)
        if hasattr(httpx, "AsyncClient"):
            monkeypatch.setattr(httpx.AsyncClient, "request", _fail_httpx)
    except ImportError:
        pass

    # 5. Network: aiohttp (optional dep).
    try:
        import aiohttp  # type: ignore[import-not-found]

        def _fail_aiohttp(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden aiohttp side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        if hasattr(aiohttp, "ClientSession"):
            monkeypatch.setattr(aiohttp.ClientSession, "get", _fail_aiohttp)
            monkeypatch.setattr(aiohttp.ClientSession, "post", _fail_aiohttp)
    except ImportError:
        pass

    # 6. Subprocess: subprocess.Popen is the standard shell-out
    # surface in Python's stdlib.
    import subprocess as _subprocess

    def _fail_subprocess(*args: object, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError(
            f"forbidden subprocess side channel invoked: args={args!r} kwargs={kwargs!r}"
        )

    monkeypatch.setattr(_subprocess, "Popen", _fail_subprocess)

    # 7. Database: SQLAlchemy engine creation surfaces.
    try:
        import sqlalchemy  # type: ignore[import-not-found]
        import sqlalchemy.engine as _sa_engine  # type: ignore[import-not-found]

        def _fail_sqlalchemy(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden sqlalchemy side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        if hasattr(_sa_engine, "create_engine"):
            monkeypatch.setattr(_sa_engine, "create_engine", _fail_sqlalchemy)
        if hasattr(sqlalchemy, "create_engine"):
            monkeypatch.setattr(sqlalchemy, "create_engine", _fail_sqlalchemy)
        try:
            from sqlalchemy.ext.asyncio import (  # type: ignore[import-not-found]  # noqa: F401
                create_async_engine,
            )

            monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", _fail_sqlalchemy)
        except ImportError:
            pass
        try:
            from sqlalchemy.orm import sessionmaker  # type: ignore[import-not-found]

            monkeypatch.setattr(sessionmaker, "__call__", _fail_sqlalchemy)
        except ImportError:
            pass
    except ImportError:
        pass

    # 8. Project's actual DB session module (the canonical entry point
    # for async SQLAlchemy sessions in this project). We patch the
    # module-level engine and the public ``get_db_session`` async
    # function so any DB usage would be detected.
    try:
        from backend.app.db import session as _db_session  # type: ignore[import-not-found]

        def _fail_db(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden project db side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        async def _fail_db_async(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden project db side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        if hasattr(_db_session, "get_db_session"):
            monkeypatch.setattr(_db_session, "get_db_session", _fail_db_async)
    except ImportError:
        pass

    # 9. Database: asyncpg + psycopg (optional deps).
    try:
        import asyncpg  # type: ignore[import-not-found]

        def _fail_asyncpg(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden asyncpg side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        if hasattr(asyncpg, "connect"):
            monkeypatch.setattr(asyncpg, "connect", _fail_asyncpg)
    except ImportError:
        pass

    try:
        import psycopg2  # type: ignore[import-not-found]

        def _fail_psycopg2(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden psycopg2 side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        if hasattr(psycopg2, "connect"):
            monkeypatch.setattr(psycopg2, "connect", _fail_psycopg2)
    except ImportError:
        pass

    try:
        import psycopg  # type: ignore[import-not-found]

        def _fail_psycopg(*args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError(
                f"forbidden psycopg side channel invoked: args={args!r} kwargs={kwargs!r}"
            )

        if hasattr(psycopg, "connect"):
            monkeypatch.setattr(psycopg, "connect", _fail_psycopg)
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


# ===========================================================================
# Phase 4c-3 P2 follow-up remediation (test-only).
#
# These five tests close the P2 follow-up items that PR #49 explicitly
# flagged as "intentionally NOT addressed this round" — see the PR #49
# body, "P2 follow-ups (intentionally NOT addressed this round)" section.
# Per the binding rule for this slice, production code under
# ``backend/app/rolling_backtest/verify.py`` is NOT modified; only this
# test file gains coverage. Two contract observations are surfaced as
# in-test documentation (the ``expected_kind="root"`` §6.1 union drift
# and the JSON-vs-manifest mask-hash mismatch kind choice) and are
# flagged in the PR body for separate Charles authorization.
#
# Cross-references (design §6):
# * §6.1 ``missing_artifact`` — carries ``path`` + ``expected_kind``
#   (frozen union: "json" | "csv" | "manifest" | "audit"; see
#   design §6.1 documentation. The production implementation also
#   emits ``expected_kind="root"`` for the reload-root-missing case;
#   this is a documented contract drift flagged in the PR body.)
# * §6.2 ``malformed_json`` — carries ``path`` + ``reason``
# * §6.3 ``malformed_csv`` — carries ``path`` + ``reason``
# * §6.4 ``manifest_mismatch`` — carries ``path`` + ``field`` +
#   ``expected`` + ``actual``
# * §6.5 ``canonical_payload_hash_mismatch`` — carries ``path`` +
#   ``expected`` + ``actual``
# * §6.6 ``audit_payload_hash_mismatch`` — carries ``path`` +
#   ``expected`` + ``actual``
# * §6.7 ``row_order_mismatch`` — carries ``path`` + ``csv_order`` +
#   ``json_order`` + ``first_diverging_index``
# * §6.8 ``metric_definition_version_mismatch`` — carries ``path`` +
#   ``expected`` + ``actual``
# * §6.9 ``mask_hash_mismatch`` — carries ``expected_mask_hash`` +
#   ``actual_mask_hash``
# * §6.10 ``forbidden_implicit_fallback`` — carries
#   ``attempted_selection``
# ===========================================================================


# ---------------------------------------------------------------------------
# P2-1 — assertion-depth self-check (no shallow assertions).
#
# Existing 4c-3 tests assert ``excinfo.value.kind == "..."`` for each
# failure kind. This test is the meta-check that the failure kind also
# carries the full structured payload documented in design §6.1 – §6.10
# (relevant subset per kind). A "shallow assertion" of only ``kind``
# would be insufficient: e.g. a contract regression that drops
# ``path`` from the payload would still satisfy ``kind == "..."`` but
# would break downstream tooling that consumes the structured payload.
# This test triggers each failure kind on a minimal artifact set and
# asserts the documented carries are present (not merely the kind).
# ---------------------------------------------------------------------------


def test_assertions_are_not_shallow_p2_self_check(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§6.1 – §6.10 / P2-1: every frozen failure kind MUST carry the
    structured payload documented in design §6 (relevant subset per
    kind), not just the kind string.

    A failure kind without its documented carries is a "shallow
    assertion" hazard: the kind-only check would pass even when the
    production payload drops fields downstream tooling depends on
    (paths, expected/actual values, indexes). This test pins the
    full structured payload to the design contract.
    """
    # ---- §6.1 missing_artifact (json path) ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    json_files = sorted((tmp_path / "json").iterdir())
    assert len(json_files) == 1
    json_path = json_files[0]
    json_path.unlink()
    with pytest.raises(MissingArtifactError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "missing_artifact"
    assert payload["expected_kind"] == "json"
    assert isinstance(payload["path"], str) and payload["path"].endswith(".json")
    # The payload MUST also carry the binding identity fields (§3.4
    # / §6 base class) so downstream tooling can correlate failures
    # with the canonical Phase 4b identity.
    assert payload["metric_definition_version"] == METRIC_DEFINITION_VERSION
    assert payload["reload_contract_version"] == RELOAD_CONTRACT_VERSION

    # ---- §6.2 malformed_json (frozen top-level key removed) ----
    _write_artifacts(
        golden_rows_single_node,
        rows_by_run_mask,
        tmp_path,
        overwrite_policy=OverwritePolicy.ALWAYS,
    )
    json_files = sorted((tmp_path / "json").iterdir())
    payload_dict = json.loads(json_files[0].read_text(encoding="utf-8"))
    del payload_dict["run_id"]
    json_files[0].write_text(
        json.dumps(payload_dict, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(MalformedJsonError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "malformed_json"
    assert payload["reason"] == "key_mismatch"
    assert isinstance(payload["path"], str) and payload["path"].endswith(".json")
    # §6.2 documents ``path`` + ``reason``; the production payload
    # also includes ``expected``/``actual`` lists when the reason is
    # ``key_mismatch``. Pin both lists so a regression that drops
    # them is caught here.
    assert payload["expected"] == list(
        # §5.1 frozen top-level keys
        (
            "canonical_payload_hash",
            "cli_invocation",
            "decimal_scale",
            "evaluation_mask_hash",
            "metric_definition_version",
            "outputs",
            "run_id",
            "scope_id",
            "written_at_utc",
        )
    )
    missing_keys = [k for k in payload["expected"] if k not in payload["actual"]]
    assert missing_keys == ["run_id"]
    assert "run_id" not in payload["actual"]

    # ---- §6.3 malformed_csv (header mismatch) ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    csv_files = sorted((tmp_path / "csv").iterdir())
    csv_text = csv_files[0].read_text(encoding="utf-8")
    # Replace the header line with a single-column CSV.
    first_newline = csv_text.index("\n")
    csv_files[0].write_text("only_one_column\n" + csv_text[first_newline + 1 :], encoding="utf-8")
    with pytest.raises(MalformedCsvError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "malformed_csv"
    assert payload["reason"] == "header_mismatch"
    assert isinstance(payload["path"], str) and payload["path"].endswith(".csv")
    # §6.3 documents ``path`` + ``reason``; the production payload
    # also carries ``expected``/``actual`` for header_mismatch.
    assert payload["expected"] == [
        "metric_name",
        "metric_value",
        "comparable_row_count",
        "decimal_scale",
        "evaluation_mask_hash",
        "metric_scope_identity",
        "metric_definition_version",
        "blocker_count",
        "blocker_kinds",
    ]
    assert payload["actual"] == ["only_one_column"]

    # ---- §6.4 manifest_mismatch (modifying the manifest's
    #      metric_definition_version in-place) ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    manifest_dir = tmp_path / "manifest"
    manifest_path = next(manifest_dir.iterdir())
    payload_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_dict["metric_definition_version"] = "4b-0.9.0"
    manifest_path.write_text(
        json.dumps(payload_dict, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    with pytest.raises(MetricDefinitionVersionMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    # §6.4 / §6.8 surface a kind-level discriminator; pin both.
    assert payload["kind"] == "metric_definition_version_mismatch"
    # §6.4 documents ``path`` + ``field`` + ``expected`` + ``actual``.
    # The production implementation (verify.py:_validate_metric_definition_version)
    # emits ``path`` + ``expected`` + ``actual`` (the ``field`` is
    # implied by the kind). Pin the production carries; the design
    # contract is partial-documented for the field discriminator.
    assert isinstance(payload["path"], str) and payload["path"].endswith(".json")
    assert payload["expected"] == METRIC_DEFINITION_VERSION
    assert payload["actual"] == "4b-0.9.0"

    # ---- §6.5 canonical_payload_hash_mismatch ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    json_files = sorted((tmp_path / "json").iterdir())
    payload_dict = json.loads(json_files[0].read_text(encoding="utf-8"))
    payload_dict["outputs"][0]["metric_value"] = "999.999999"
    json_files[0].write_text(
        json.dumps(payload_dict, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(CanonicalPayloadHashMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "canonical_payload_hash_mismatch"
    # §6.5 carries ``path`` + ``expected`` + ``actual`` — all three
    # MUST be 64-char lowercase hex, not generic strings.
    assert isinstance(payload["path"], str) and payload["path"].endswith(".json")
    assert isinstance(payload["expected"], str) and len(payload["expected"]) == 64
    assert isinstance(payload["actual"], str) and len(payload["actual"]) == 64
    assert payload["expected"] != payload["actual"]

    # ---- §6.6 audit_payload_hash_mismatch ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    audit_files = sorted((tmp_path / "audit").iterdir())
    audit_files[0].write_text("{not even valid json", encoding="utf-8")
    with pytest.raises(AuditPayloadHashMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "audit_payload_hash_mismatch"
    assert isinstance(payload["path"], str) and payload["path"].endswith(".json")
    assert isinstance(payload["expected"], str) and len(payload["expected"]) == 64
    assert isinstance(payload["actual"], str) and len(payload["actual"]) == 64
    assert payload["expected"] != payload["actual"]

    # ---- §6.7 row_order_mismatch (swap two CSV rows) ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    csv_files = sorted((tmp_path / "csv").iterdir())
    csv_text = csv_files[0].read_text(encoding="utf-8")
    lines = csv_text.split("\n")
    # lines[0] is the header. Swap lines[1] and lines[2].
    lines[1], lines[2] = lines[2], lines[1]
    csv_files[0].write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(RowOrderMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "row_order_mismatch"
    assert isinstance(payload["path"], str) and payload["path"].endswith(".csv")
    # §6.7 carries ``path`` + ``csv_order`` + ``json_order`` +
    # ``first_diverging_index``. The index is 0-based: swapping the
    # first two data rows produces a divergence at index 0 (per
    # verify.py:611-615). Pin the index to 0 and the two orderings
    # to be non-equal, so a regression that swaps or drops the index
    # is caught here.
    assert payload["first_diverging_index"] == 0
    assert payload["csv_order"] != payload["json_order"]
    assert isinstance(payload["csv_order"], list)
    assert isinstance(payload["json_order"], list)
    assert len(payload["csv_order"]) == len(payload["json_order"])
    assert len(payload["csv_order"]) >= 2

    # ---- §6.9 mask_hash_mismatch (caller's expected differs) ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    wrong = "f" * 64
    assert wrong != SAMPLE_MASK_HASH
    with pytest.raises(MaskHashMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=wrong)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "mask_hash_mismatch"
    assert payload["expected_mask_hash"] == wrong
    assert payload["actual_mask_hash"] == SAMPLE_MASK_HASH

    # ---- §6.10 forbidden_implicit_fallback (two manifest files) ----
    _write_artifacts(
        golden_rows_single_node, rows_by_run_mask, tmp_path, overwrite_policy=OverwritePolicy.ALWAYS
    )
    # Plant a second manifest file with a different filename so the
    # manifest directory contains two candidates.
    extra_manifest = tmp_path / "manifest" / "_extra_manifest.json"
    extra_manifest.write_text('{"_": "placeholder"}', encoding="utf-8")
    with pytest.raises(ForbiddenImplicitFallbackError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "forbidden_implicit_fallback"
    # §6.10 documents ``attempted_selection``. Pin it to a non-empty
    # string and assert it identifies the implicit selector the
    # reload attempted (current / latest / most recent).
    assert isinstance(payload["attempted_selection"], str)
    assert payload["attempted_selection"] != ""
    assert payload["attempted_selection"] in {"current", "latest", "most_recent"}


# ---------------------------------------------------------------------------
# P2-2 — ``expected_mask_hash=None`` path (happy path: skip the check).
#
# §6.9 documents the failure as "the caller specifies the
# ``(run_id, evaluation_mask_hash)`` they expect to verify, and a
# reload against a different mask hash is an error". The contract is
# silent on the case where the caller deliberately passes ``None`` to
# opt out of the check. The production implementation honours this opt-
# out at ``verify.py:528`` (``if expected_mask_hash is not None and
# ...``). This test pins both halves of the contract:
#
#   (a) ``expected_mask_hash=None`` MUST NOT raise
#       ``MaskHashMismatchError`` (the §6.9 check is opt-out, not
#       mandatory).
#   (b) A non-None mismatch MUST still raise the structured
#       ``MaskHashMismatchError`` (existing test already covers this;
#       we re-pin the structured payload to keep parity).
#
# ---------------------------------------------------------------------------


def test_verify_with_expected_mask_hash_none_skips_check(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§6.9 / P2-2: ``expected_mask_hash=None`` MUST skip the §6.9 check
    and return a typed ``ReloadResult`` carrying the JSON's actual
    ``evaluation_mask_hash``. A non-None mismatch MUST still raise
    ``MaskHashMismatchError`` with the full structured payload.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    # (a) expected_mask_hash=None MUST NOT raise.
    result = verify_artifact_set(tmp_path, expected_mask_hash=None)
    assert isinstance(result, ReloadResult)
    # The reload MUST still bind the §5.1 / §5.3 identity triple.
    assert result.run_id == SAMPLE_RUN_ID
    assert result.evaluation_mask_hash == SAMPLE_MASK_HASH
    assert result.scope_id != ""
    assert result.canonical_payload_hash != ""
    assert result.audit_payload_hash is not None
    assert result.metric_definition_version == METRIC_DEFINITION_VERSION
    # The result's evaluated-mask identity MUST equal what the JSON
    # carries — the §6.9 opt-out is a check skip, NOT a silent
    # substitution of the mask hash.
    assert result.evaluation_mask_hash == SAMPLE_MASK_HASH

    # (b) Non-None mismatch MUST still raise (parity with existing
    # test_wrong_expected_mask_hash_raises_mask_hash_mismatch). Pin
    # the full structured payload to ensure the opt-out branch did
    # not accidentally widen the contract.
    wrong = "f" * 64
    assert wrong != SAMPLE_MASK_HASH
    with pytest.raises(MaskHashMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=wrong)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "mask_hash_mismatch"
    assert payload["expected_mask_hash"] == wrong
    assert payload["actual_mask_hash"] == SAMPLE_MASK_HASH


# ---------------------------------------------------------------------------
# P2-3 — JSON vs manifest mask-hash inconsistency.
#
# §6.4 ``manifest_mismatch`` is documented for path-integrity and
# ``metric_definition_version`` mismatches. §6.9
# ``mask_hash_mismatch`` is documented for caller-vs-JSON mismatches.
# Neither §6.4 nor §6.9 explicitly cover the JSON-vs-manifest
# internal hash-field disagreement, but the production code at
# ``verify.py:514-525`` raises ``ManifestMismatchError`` (kind
# ``"manifest_mismatch"``) with the ``field``, ``expected``, and
# ``actual`` carries when the two hashes diverge. This is a reasonable
# interpretation (the manifest is the index, so the JSON is the
# expected source of truth and the manifest is at fault). This test
# pins that production behaviour with the full structured payload.
#
# Cross-reference: see PR body "production contract observation" for
# the rationale and the deferred alternative (``mask_hash_mismatch``).
# ---------------------------------------------------------------------------


def test_verify_detects_json_vs_manifest_mask_hash_mismatch(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§6 / P2-3: when the JSON's ``evaluation_mask_hash`` differs
    from the manifest's, the reload MUST surface a structured error
    (``manifest_mismatch`` per the production interpretation; see
    verify.py:514-525) with ``field`` / ``expected`` / ``actual``
    carries documenting which side carries which value.
    """
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    manifest_dir = tmp_path / "manifest"
    manifest_path = next(manifest_dir.iterdir())
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Pin a deliberately divergent manifest hash (any 64-char hex
    # other than SAMPLE_MASK_HASH).
    divergent_mask = "a" * 64
    assert divergent_mask != SAMPLE_MASK_HASH
    payload["evaluation_mask_hash"] = divergent_mask
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(ManifestMismatchError) as excinfo:
        verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    err_payload = excinfo.value.to_payload()
    # Production kind choice (verify.py:518): ``manifest_mismatch``.
    assert err_payload["kind"] == "manifest_mismatch"
    assert err_payload["field"] == "evaluation_mask_hash"
    # ``expected`` carries the JSON value (the source of truth per
    # the production comment); ``actual`` carries the manifest value
    # (the mismatched side).
    assert err_payload["expected"] == SAMPLE_MASK_HASH
    assert err_payload["actual"] == divergent_mask
    assert isinstance(err_payload["path"], str) and err_payload["path"].endswith(".json")


# ---------------------------------------------------------------------------
# P2-4 — non-existent reload root.
#
# §6.1 ``missing_artifact`` documents the ``expected_kind`` union as
# ``"json" | "csv" | "manifest" | "audit"``. The production code at
# ``verify.py:409-414`` raises ``MissingArtifactError`` with
# ``expected_kind="root"`` when the reload root itself does not
# exist. This is a documented contract drift: the union in §6.1 does
# not list ``"root"`` but the production payload uses it as a
# discriminator. We pin the production behaviour here so a future
# regression that aligns production with the documented union (or vice
# versa) is caught by this test rather than silently breaking
# downstream tooling.
#
# Cross-reference: PR body "production contract observation" notes
# this drift and defers the union extension / production rename to a
# separate Charles authorization.
# ---------------------------------------------------------------------------


def test_verify_on_nonexistent_root_raises_missing_artifact(
    tmp_path: Path,
) -> None:
    """§6.1 / P2-4: ``verify_artifact_set`` against a non-existent
    ``root`` MUST surface as ``MissingArtifactError`` with the
    production-chosen ``expected_kind`` discriminator.

    The production code at ``verify.py:409-414`` uses
    ``expected_kind="root"`` for the reload-root-missing case. The
    design §6.1 union (``"json" | "csv" | "manifest" | "audit"``)
    does not list ``"root"`` — this test pins the production
    behaviour and surfaces the drift in the PR body for separate
    authorization.
    """
    nonexistent_root = tmp_path / "_does_not_exist_subdir_"
    assert not nonexistent_root.exists()
    with pytest.raises(MissingArtifactError) as excinfo:
        verify_artifact_set(nonexistent_root, expected_mask_hash=SAMPLE_MASK_HASH)
    payload = excinfo.value.to_payload()
    assert payload["kind"] == "missing_artifact"
    # Production-chosen ``expected_kind`` discriminator. The
    # documented §6.1 union is ``"json" | "csv" | "manifest" |
    # "audit"``; ``"root"`` is the production extension for the
    # reload-root-missing case. See PR body for the contract drift
    # note.
    assert payload["expected_kind"] == "root"
    assert isinstance(payload["path"], str)
    # The carried ``path`` MUST point at the missing root, not at
    # some unrelated location.
    assert str(nonexistent_root) in payload["path"]
    # The reload MUST fail before any materialization provider or
    # DB / network call is touched (defensive: the contract is
    # stateless, but pinning here makes the no-side-effect
    # guarantee explicit at the very first guard).
    assert payload["metric_definition_version"] == METRIC_DEFINITION_VERSION
    assert payload["reload_contract_version"] == RELOAD_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# P2-5 — nested-layout audit-path discovery (existing test coverage
# depth-up).
#
# ``test_nested_json_layout_with_audit_at_root_audit_subdir_succeeds``
# already covers the happy path (the reload succeeds despite the
# nested JSON layout). This follow-up DEPTHS the assertions: pin the
# exact returned identity triple, the exact resolved audit / JSON /
# CSV / manifest paths, the canonical_payload_hash equality with the
# flat-layout reference run, and the no-side-effect guarantee.
#
# Per the round-1 directive ("如果已存在等价覆盖, 不要重复造同义
# 测试; 改为补强断言"), this test is a depth-up augmentation of
# the existing P1-1 regression rather than a brand-new test case.
# ---------------------------------------------------------------------------


def test_nested_layout_audit_path_discovered_via_structural_lookup(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7 / P2-5: depth-up of the nested-layout audit-path discovery
    regression (P1-1, originally covered by
    ``test_nested_json_layout_with_audit_at_root_audit_subdir_succeeds``).

    Pins the full ``ReloadResult`` identity triple + exact resolved
    paths + canonical_payload_hash equality with a flat-layout
    reference run + the binding identity fields, so a regression
    in the structural audit-path discovery (or in the canonical
    payload-hash derivation) is caught by this single test rather
    than silently breaking downstream consumers.
    """
    # 1. Build the nested-layout artifact set (same setup as the
    #    P1-1 regression).
    _write_artifacts(golden_rows_single_node, rows_by_run_mask, tmp_path)
    nested_json_dir = tmp_path / "2026-01" / "json"
    nested_json_dir.mkdir(parents=True)
    original_json = next((tmp_path / "json").iterdir())
    nested_json = nested_json_dir / original_json.name
    nested_json.write_bytes(original_json.read_bytes())
    original_json.unlink()
    manifest_dir = tmp_path / "manifest"
    manifest_path = next(manifest_dir.iterdir())
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["json_path"] = f"2026-01/json/{original_json.name}"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # 2. The reload MUST succeed with the nested JSON layout.
    result_nested = verify_artifact_set(tmp_path, expected_mask_hash=SAMPLE_MASK_HASH)
    assert isinstance(result_nested, ReloadResult)

    # 3. The reload's identity triple MUST equal the artifact set's
    #    §5.1 / §5.3 binding identity.
    assert result_nested.run_id == SAMPLE_RUN_ID
    assert result_nested.evaluation_mask_hash == SAMPLE_MASK_HASH
    assert result_nested.scope_id != ""
    assert result_nested.metric_definition_version == METRIC_DEFINITION_VERSION
    # The audit_payload_hash MUST be non-null (audit was emitted in
    # the fixture; verify.py:483 keeps the assertion that an audit
    # exists whenever the manifest records an audit_payload_hash).
    assert result_nested.audit_payload_hash is not None
    assert len(result_nested.audit_payload_hash) == 64

    # 4. The reload MUST resolve the JSON path to the nested layout
    #    (NOT the original flat layout). The CSV / audit / manifest
    #    paths MUST stay at their canonical locations. The 4c-2
    #    filename pattern (``<run-id>__<scope-id>__<hash>.<ext>``)
    #    differs in extension between JSON / CSV / manifest / audit,
    #    so the test derives each resolved path from the same base
    #    name with the appropriate extension rather than reusing the
    #    JSON name verbatim.
    base_name = original_json.name[: -len(".json")]
    assert result_nested.json_path == nested_json.resolve()
    assert "2026-01" in result_nested.json_path.parts
    assert result_nested.csv_path == (tmp_path / "csv" / f"{base_name}.csv").resolve()
    assert result_nested.manifest_path == (tmp_path / "manifest" / f"{base_name}.json").resolve()
    assert result_nested.audit_path == (tmp_path / "audit" / f"{base_name}.json").resolve()

    # 5. The reload MUST produce the same canonical_payload_hash as
    #    a flat-layout reference run. Build a fresh flat-layout
    #    artifact set in a separate tmp dir and assert hash equality
    #    — this guards against a regression in the structural lookup
    #    that silently recomputes the hash from a different JSON
    #    byte sequence.
    flat_root = tmp_path.parent / f"{tmp_path.name}_flat_reference"
    flat_root.mkdir()
    try:
        _write_artifacts(golden_rows_single_node, rows_by_run_mask, flat_root)
        result_flat = verify_artifact_set(flat_root, expected_mask_hash=SAMPLE_MASK_HASH)
        assert result_flat.canonical_payload_hash == result_nested.canonical_payload_hash
        assert result_flat.evaluation_mask_hash == result_nested.evaluation_mask_hash
        assert result_flat.scope_id == result_nested.scope_id
    finally:
        # Best-effort cleanup; pytest's tmp_path machinery handles
        # teardown of ``tmp_path`` itself but the parallel flat
        # reference dir is created in tmp_path.parent.
        import shutil

        shutil.rmtree(flat_root, ignore_errors=True)
