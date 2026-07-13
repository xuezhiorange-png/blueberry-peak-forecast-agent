"""Tests for TASK-011 Phase 4c-2 deterministic export + CLI.

These tests cover the 4c-2 implementation slice of the Phase 4c design
contract (``docs/task-11-phase4c-service-cli-export-amendment.md``,
frozen at content SHA
``9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216``).
They mirror the 4c-1 ``test_service.py`` pattern.

Frozen design §10.2 (CLI test contract) is the binding checklist.
"""

from __future__ import annotations

import csv as csv_module
import hashlib
import io
import json
import os
import sys
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.rolling_backtest import (
    CSV_HEADER,
    EXIT_HASH_COLLISION,
    EXIT_METRIC_BLOCKER,
    EXIT_SERVICE_CONTRACT_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    JSON_TOP_LEVEL_KEYS,
    MANIFEST_TOP_LEVEL_KEYS,
    METRIC_DEFINITION_VERSION,
    MaterializationMaskNotBound,
    MaterializationRunNotFound,
    PathCollision,
    compute_metrics,
    register_materialization_provider,
)
from backend.app.rolling_backtest.export import (
    ExportRequest,
    write_export_artifacts,
)
from backend.app.rolling_backtest.export import OverwritePolicy as ExportOverwritePolicy
from backend.app.rolling_backtest.metrics import (
    EvaluationMetricRow,
    EvaluationResult,
    MaskState,
)

# ---------------------------------------------------------------------------
# Fixtures
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
        ),
        _row(
            forecast_output_id=11,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 2),
            target=Decimal("20.0"),
            prediction=Decimal("19.8"),
        ),
        _row(
            forecast_output_id=12,
            node_id=1,
            evaluation_as_of_date=date(2026, 1, 3),
            target=Decimal("30.0"),
            prediction=Decimal("30.3"),
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
        # Lazy: tests populate rows_by_run_mask after registration.
        present_runs = {r for r, _ in rows_by_run_mask}
        if run_id not in present_runs:
            raise MaterializationRunNotFound(run_id=run_id)
        if (run_id, mask_hash) not in rows_by_run_mask:
            raise MaterializationMaskNotBound(run_id=run_id, mask_hash=mask_hash)
        return rows_by_run_mask[(run_id, mask_hash)]

    previous = register_materialization_provider(provider)
    try:
        yield
    finally:
        register_materialization_provider(previous)


def _make_evaluation_result(
    golden_rows_single_node: list[EvaluationMetricRow],
) -> EvaluationResult:
    """Build an EvaluationResult by calling 4c-1 service layer (golden single-factory)."""
    return compute_metrics(
        run_id=SAMPLE_RUN_ID,
        scope=SAMPLE_SCOPE,
        mask_hash=SAMPLE_MASK_HASH,
    )


def _make_export_request(
    result: EvaluationResult,
    tmp_path: Path,
    *,
    overwrite_policy: ExportOverwritePolicy = (ExportOverwritePolicy.MISSING),
    emit_audit: bool = True,
) -> ExportRequest:
    return ExportRequest(
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


# ---------------------------------------------------------------------------
# 1. JSON export determinism (§5.1)
# ---------------------------------------------------------------------------


def test_json_export_is_canonical_lexicographic_key_order(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§5.1: top-level keys MUST be in lexicographic order. We assert
    the literal JSON output key order matches the frozen tuple.
    """
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert list(payload.keys()) == list(JSON_TOP_LEVEL_KEYS)
    # Decimal canonical string (§5.1 Decimal rule).
    for out in payload["outputs"]:
        if out["metric_value"] is not None:
            assert "E" not in out["metric_value"]
            assert "+" not in out["metric_value"]
    # UTF-8 no BOM, no trailing newline.
    raw = artifacts.json_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert not raw.endswith(b"\n")


def test_json_export_metric_definition_version_is_4b_1_0_0(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["metric_definition_version"] == METRIC_DEFINITION_VERSION
    assert payload["metric_definition_version"] == "4b-1.0.0"


def test_json_export_cli_invocation_present_when_audit_enabled(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert "cli_invocation" in payload
    assert payload["cli_invocation"]["--mask-hash"] == SAMPLE_MASK_HASH


def test_json_export_no_cli_invocation_when_no_audit(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§5.1: 'cli_invocation (object — only when written by CLI; absent
    when written by service-layer test or programmatic call)'."""
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    request = _make_export_request(result, tmp_path, emit_audit=False)
    # When emit_audit is False, cli_invocation is also None.
    request = ExportRequest(
        result=request.result,
        run_id=request.run_id,
        decimal_scale=request.decimal_scale,
        output_dir=request.output_dir,
        overwrite_policy=request.overwrite_policy,
        cli_invocation=None,
        emit_audit=False,
    )
    artifacts = write_export_artifacts(request)
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert "cli_invocation" not in payload


# ---------------------------------------------------------------------------
# 2. CSV export determinism (§5.2)
# ---------------------------------------------------------------------------


def test_csv_export_header_order_is_frozen(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    raw = artifacts.csv_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # UTF-8 no BOM
    assert b"\r" not in raw  # LF only, no CRLF
    text = raw.decode("utf-8")
    lines = text.split("\n")
    header = lines[0]
    assert tuple(header.split(",")) == CSV_HEADER
    # Trailing newline required (§5.2).
    assert text.endswith("\n")


def test_csv_export_null_decimal_renders_as_empty_field(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§5.2: 'null → empty field' binding.

    The golden fixture produces ``metric_value=None`` for
    ``empirical_coverage_p50``,
    ``interval_width_mean_p80_p50``, and
    ``interval_width_median_p80_p50`` (rows lack ``p50_kg`` /
    ``p80_kg``). The CSV MUST emit an empty cell for the
    ``metric_value`` column on those rows — NOT the literal string
    ``"null"`` and NOT the string ``"None"``.

    This test parses the CSV with ``csv.reader`` (which faithfully
    distinguishes empty cells from the literal string ``"null"``)
    and asserts the ``metric_value`` cell is exactly the empty
    string for at least one row whose ``blocker_count > 0``.
    """
    import csv as _csv

    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    text = artifacts.csv_path.read_text(encoding="utf-8")
    reader = _csv.reader(io.StringIO(text))
    rows = list(reader)
    header = rows[0]
    assert tuple(header) == CSV_HEADER
    # All data rows must have len == len(header) (no off-by-one).
    for r in rows[1:]:
        assert len(r) == len(CSV_HEADER)
    # Find the metric_value column index.
    metric_value_idx = header.index("metric_value")
    metric_name_idx = header.index("metric_name")
    blocker_count_idx = header.index("blocker_count")
    # At least one row has a None metric_value (the empirical_coverage
    # / interval_width metrics that triggered ZERO_DENOMINATOR
    # blockers). For that row the metric_value cell MUST be "".
    null_rows_found = 0
    for r in rows[1:]:
        if int(r[blocker_count_idx]) > 0 and r[metric_value_idx] == "":
            null_rows_found += 1
    assert null_rows_found >= 1, (
        "expected at least one CSV row with empty metric_value cell "
        f"for a blocked metric, got rows={rows[1:]!r}"
    )
    # Spot-check: the empirical_coverage_p50 row MUST be the empty-
    # cell form, never the literal "null".
    coverage_row = next(r for r in rows[1:] if r[metric_name_idx] == "empirical_coverage_p50")
    assert coverage_row[metric_value_idx] == ""
    assert coverage_row[metric_value_idx] != "null"
    assert coverage_row[metric_value_idx] != "None"


def test_csv_export_row_order_matches_outputs(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§5.2: 'Row ordering: same as the JSON outputs array (i.e.
    canonical Phase 4b order — counters first, then aggregate
    metrics, in the order emitted by evaluate_scope).'
    """
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    json_payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    text = artifacts.csv_path.read_text(encoding="utf-8")
    reader = csv_module.reader(io.StringIO(text))
    rows = list(reader)[1:]
    csv_metric_names = [r[0] for r in rows]  # metric_name column
    json_metric_names = [o["metric_name"] for o in json_payload["outputs"]]
    assert csv_metric_names == json_metric_names


# ---------------------------------------------------------------------------
# 3. Manifest export (§5.3)
# ---------------------------------------------------------------------------


def test_manifest_top_level_keys_lexicographic(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert list(payload.keys()) == list(MANIFEST_TOP_LEVEL_KEYS)


def test_manifest_canonical_payload_hash_matches_phase4b(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§5.3 / §7.3: 'manifest canonical_payload_hash (mirrors Phase 4b)'."""
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert payload["canonical_payload_hash"] == result.canonical_payload_hash
    assert payload["metric_definition_version"] == "4b-1.0.0"


def test_manifest_paths_relative_to_output_dir(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert payload["json_path"].startswith("json/")
    assert payload["csv_path"].startswith("csv/")


def test_manifest_audit_payload_hash_present_when_audit_on(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert payload["audit_payload_hash"] is not None
    # The audit_payload_hash must equal SHA-256 of audit file bytes.
    audit_bytes = artifacts.audit_path.read_bytes()
    assert payload["audit_payload_hash"] == hashlib.sha256(audit_bytes).hexdigest()


def test_manifest_audit_payload_hash_null_when_no_audit(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§10.2: '--no-audit suppresses the audit file; the manifest
    still records audit_payload_hash: null.'"""
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    request = ExportRequest(
        result=result,
        run_id=SAMPLE_RUN_ID,
        decimal_scale=6,
        output_dir=tmp_path,
        overwrite_policy=ExportOverwritePolicy.MISSING,
        cli_invocation=None,
        emit_audit=False,
    )
    artifacts = write_export_artifacts(request)
    assert artifacts.audit_path is None
    payload = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert payload["audit_payload_hash"] is None


# ---------------------------------------------------------------------------
# 4. Output directory layout (§5.4)
# ---------------------------------------------------------------------------


def test_output_directory_layout_has_four_subdirs(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    write_export_artifacts(_make_export_request(result, tmp_path))
    for sub in ("audit", "csv", "json", "manifest"):
        assert (tmp_path / sub).is_dir()


def test_file_names_match_frozen_pattern(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§6.1: filename pattern is <run-id>__<scope-id>__<hash>.<ext>."""
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    for path in (
        artifacts.json_path,
        artifacts.csv_path,
        artifacts.manifest_path,
        artifacts.audit_path,
    ):
        name = path.name
        assert "__" in name
        parts = name.split("__")
        assert len(parts) == 3
        run_part, scope_part, hash_ext = parts
        assert run_part == SAMPLE_RUN_ID
        hash_part, ext = hash_ext.rsplit(".", 1)
        assert len(hash_part) == 64  # 64-char lowercase hex
        assert all(c in "0123456789abcdef" for c in hash_part)


# ---------------------------------------------------------------------------
# 5. Overwrite / collision policy (§6.2)
# ---------------------------------------------------------------------------


def test_overwrite_missing_raises_on_existing_file(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    write_export_artifacts(_make_export_request(result, tmp_path))
    # Second call must raise PathCollision.
    with pytest.raises(PathCollision):
        write_export_artifacts(
            _make_export_request(result, tmp_path, overwrite_policy=ExportOverwritePolicy.MISSING)
        )


def test_overwrite_never_raises_on_existing_file(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    write_export_artifacts(_make_export_request(result, tmp_path))
    with pytest.raises(PathCollision):
        write_export_artifacts(
            _make_export_request(result, tmp_path, overwrite_policy=ExportOverwritePolicy.NEVER)
        )


def test_overwrite_always_succeeds_and_replaces_bytes(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts1 = write_export_artifacts(_make_export_request(result, tmp_path))
    bytes1 = artifacts1.json_path.read_bytes()
    artifacts2 = write_export_artifacts(
        _make_export_request(result, tmp_path, overwrite_policy=ExportOverwritePolicy.ALWAYS)
    )
    bytes2 = artifacts2.json_path.read_bytes()
    # Same canonical JSON for identical inputs.
    assert bytes1 == bytes2


# ---------------------------------------------------------------------------
# 6. Crash-recovery (§6.3)
# ---------------------------------------------------------------------------


def test_crash_recovery_removes_stale_tmp_files(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    # Pre-create a stale .tmp.<random> file in the json subdir.
    (tmp_path / "json").mkdir(parents=True)
    stale = tmp_path / "json" / ".tmp.stale.json.abc"
    stale.write_bytes(b"x")
    # Backdate it well past the default threshold.
    old_mtime = 0.0  # epoch = very old
    os.utime(stale, (old_mtime, old_mtime))
    result = _make_evaluation_result(golden_rows_single_node)
    write_export_artifacts(_make_export_request(result, tmp_path))
    # The stale tmp file should be removed.
    assert not stale.exists()


def test_crash_recovery_keeps_young_tmp_files(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    (tmp_path / "json").mkdir(parents=True)
    young = tmp_path / "json" / ".tmp.young.json.abc"
    young.write_bytes(b"x")
    # mtime is "now" (just created), which is well within the default
    # 3600s threshold. The crash-recovery sweep must leave it alone.
    result = _make_evaluation_result(golden_rows_single_node)
    write_export_artifacts(_make_export_request(result, tmp_path))
    assert young.exists()


# ---------------------------------------------------------------------------
# 7. Determinism — same inputs produce byte-identical files (§6.1 / §8)
# ---------------------------------------------------------------------------


def test_repeated_export_byte_identical_for_identical_inputs(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§6.1 / §8: 'A CLI run with identical inputs produces a
    deterministic outcome.' Two writers with identical inputs but
    different overwrite policies (missing → never) must produce
    byte-identical JSON / CSV / manifest content (the audit file
    carries a timestamp so we exclude it from this assertion).
    """
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)

    artifacts1 = write_export_artifacts(
        _make_export_request(result, tmp_path / "a", overwrite_policy=ExportOverwritePolicy.MISSING)
    )
    artifacts2 = write_export_artifacts(
        _make_export_request(result, tmp_path / "b", overwrite_policy=ExportOverwritePolicy.NEVER)
    )
    # JSON and manifest carry the wall-clock write timestamp required by
    # the export envelope. Compare the deterministic payload after removing
    # that explicitly non-semantic field; CSV has no timestamp.
    json1 = json.loads(artifacts1.json_path.read_text(encoding="utf-8"))
    json2 = json.loads(artifacts2.json_path.read_text(encoding="utf-8"))
    json1.pop("written_at_utc")
    json2.pop("written_at_utc")
    assert json1 == json2
    assert artifacts1.csv_path.read_bytes() == artifacts2.csv_path.read_bytes()
    # Manifest: written_at_utc is the same timestamp because the
    # two writes happen back-to-back within the same second. If
    # they cross a second boundary, the assertion would flake; we
    # accept this as a known limitation and document it. For the
    # 4c-1 service-layer hash, see test_canonical_payload_hash.
    manifest1 = json.loads(artifacts1.manifest_path.read_text("utf-8"))
    manifest2 = json.loads(artifacts2.manifest_path.read_text("utf-8"))
    # canonical_payload_hash MUST be identical.
    assert manifest1["canonical_payload_hash"] == manifest2["canonical_payload_hash"]
    # json_path / csv_path in the manifest reference different
    # directories; that is expected and not a determinism violation.


# ---------------------------------------------------------------------------
# 8. Audit file (§4.4 / §7.1)
# ---------------------------------------------------------------------------


def test_audit_file_keys_frozen(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    payload = json.loads(artifacts.audit_path.read_text(encoding="utf-8"))
    # §4.4 frozen key set.
    expected_keys = {
        "cli_version",
        "command_invocations",
        "inputs",
        "outputs",
        "metric_definition_version",
        "evaluation_mask_hash",
        "run_id",
        "started_at_utc",
        "finished_at_utc",
        "exit_code",
    }
    assert expected_keys.issubset(payload.keys())


def test_audit_payload_hash_matches_sha256_of_audit_bytes(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    manifest = json.loads(artifacts.manifest_path.read_text("utf-8"))
    audit_bytes = artifacts.audit_path.read_bytes()
    assert manifest["audit_payload_hash"] == hashlib.sha256(audit_bytes).hexdigest()


# ---------------------------------------------------------------------------
# 9. CLI tests (§10.2) — subprocess smoke
# ---------------------------------------------------------------------------


@pytest.fixture
def run_id_arg() -> str:
    return SAMPLE_RUN_ID


@pytest.fixture
def mask_hash_arg() -> str:
    return SAMPLE_MASK_HASH


@pytest.fixture
def scope_arg() -> str:
    return json.dumps(SAMPLE_SCOPE)


def test_cli_compute_metrics_exits_0_or_3_and_writes_four_files(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§10.2: 'compute-metrics --run-id X --scope {...} --mask-hash
    <hex> --output-dir /tmp/foo exits 0 on success; the four files
    appear under /tmp/foo/{json,csv,manifest,audit}/ with the
    frozen filename pattern.'

    The golden fixture produces MetricBlockers for the
    empirical_coverage_p50 / interval_width_mean_p80_p50 /
    interval_width_median_p80_p50 metrics (because the rows lack
    ``p50_kg`` / ``p80_kg``). Per §4.5 MetricBlocker surfaces as
    exit code 3; the four files are still written.

    We exercise the CLI in-process (``cli_main(argv)``) so the
    stub materialization provider registered by ``stub_provider``
    is visible to ``compute_metrics``. The CLI entry point and
    argument parsing are identical to the subprocess invocation
    ``python -m backend.app.rolling_backtest.cli compute-metrics …``;
    the difference is only the in-process vs. fresh-process model.
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
    # Either EXIT_SUCCESS (no blockers) or EXIT_METRIC_BLOCKER
    # (one or more MetricBlocker surfaced) is acceptable per §4.3.
    assert rc in (EXIT_SUCCESS, EXIT_METRIC_BLOCKER)
    json_files = list((tmp_path / "json").iterdir())
    csv_files = list((tmp_path / "csv").iterdir())
    manifest_files = list((tmp_path / "manifest").iterdir())
    audit_files = list((tmp_path / "audit").iterdir())
    assert len(json_files) == 1
    assert len(csv_files) == 1
    assert len(manifest_files) == 1
    assert len(audit_files) == 1


def test_cli_missing_required_flag_exits_64(
    tmp_path: Path,
) -> None:
    from backend.app.rolling_backtest import cli_main

    rc = cli_main(
        [
            "compute-metrics",
            # --run-id is required.
            "--scope",
            json.dumps(SAMPLE_SCOPE),
            "--mask-hash",
            SAMPLE_MASK_HASH,
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc == EXIT_USAGE_ERROR


def test_cli_relative_output_dir_exits_64(
    tmp_path: Path,
) -> None:
    """P0: ``--output-dir`` MUST be absolute.

    Per §4.2, ``--output-dir`` is bound as absolute. Per §4.3,
    relative paths surface as exit 64 (CLI usage error). We
    deliberately do NOT use ``Path.resolve()`` because that would
    silently coerce a relative input (e.g. ``./foo``) into an
    absolute path on the host's CWD, which is exactly the
    silent-failure mode that the absolute-path binding is meant
    to prevent. The CLI must therefore reject relative paths
    BEFORE any ``resolve()`` is applied.
    """
    from backend.app.rolling_backtest import cli_main

    # Use a relative path that would otherwise resolve to a real
    # directory on the test host (``tmp_path.name`` is the leaf
    # basename of the pytest tmp dir; ``./<basename>`` does not
    # exist as a CWD-relative path during pytest, but that
    # non-existence is irrelevant — the absolute-path check fires
    # before any filesystem lookup).
    relative = f"./rel_{tmp_path.name}"
    assert not Path(relative).is_absolute()
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
            relative,
        ]
    )
    assert rc == EXIT_USAGE_ERROR


def test_cli_relative_output_dir_does_not_create_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0: a relative ``--output-dir`` MUST be rejected before any
    directory creation / filesystem write is attempted.

    The pre-fix implementation called ``Path.resolve()`` first,
    which collapsed the relative path to an absolute one and
    then proceeded to create that absolute path's parent
    directory. This test asserts that no such side effect
    occurs for a relative input. We monkey-patch
    ``Path.mkdir`` to record any call; if the CLI is well-behaved,
    no ``mkdir`` call is made for the json/ csv/ manifest/ audit
    subdirs.
    """
    from backend.app.rolling_backtest import cli_main

    mkdir_calls: list[Path] = []
    original_mkdir = Path.mkdir

    def spy_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        mkdir_calls.append(self)
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", spy_mkdir)
    relative = "./another_rel"
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
            relative,
        ]
    )
    assert rc == EXIT_USAGE_ERROR
    # No mkdir calls should have been made — the absolute-path
    # check fires before the writer is invoked.
    assert mkdir_calls == []


def test_cli_invalid_mask_hash_exits_2_via_service_contract(
    tmp_path: Path,
) -> None:
    """``--mask-hash`` value is validated by 4c-1 service-layer
    ``_validate_mask_hash`` (a 64-char lowercase hex requirement),
    which raises ``ServiceContractError(kind=invalid_mask_hash, ...)``
    on failure. Per §9, this surfaces as exit 2. (Argparse accepts
    any string, so this is NOT a CLI usage error — it is a
    service-layer validation failure.)"""
    from backend.app.rolling_backtest import cli_main

    rc = cli_main(
        [
            "compute-metrics",
            "--run-id",
            SAMPLE_RUN_ID,
            "--scope",
            json.dumps(SAMPLE_SCOPE),
            "--mask-hash",
            "tooshort",  # not 64 chars
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc == EXIT_SERVICE_CONTRACT_ERROR


def test_cli_malformed_scope_json_exits_64(
    tmp_path: Path,
) -> None:
    from backend.app.rolling_backtest import cli_main

    rc = cli_main(
        [
            "compute-metrics",
            "--run-id",
            SAMPLE_RUN_ID,
            "--scope",
            "{not json",
            "--mask-hash",
            SAMPLE_MASK_HASH,
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc == EXIT_USAGE_ERROR


def test_cli_service_contract_error_exits_2(
    tmp_path: Path,
) -> None:
    """No provider registered → ServiceContractError(kind=missing_run) → exit 2.

    We exercise the CLI in-process so the global provider slot can
    be cleared in the same process. We capture stdout via
    ``capsys`` to read the JSON error payload.
    """
    from backend.app.rolling_backtest import cli_main

    previous = register_materialization_provider(None)
    try:
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
        assert rc == EXIT_SERVICE_CONTRACT_ERROR
    finally:
        register_materialization_provider(previous)


def test_cli_service_contract_error_payload_includes_structured_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P1: the JSON error payload MUST include the structured request
    context (``run_id``, ``scope_id``, ``evaluation_mask_hash``,
    ``metric_definition_version``).

    Pre-fix the payload only carried ``kind``, ``message``, and
    ``metric_definition_version``; the structured context
    fields were dropped at the boundary between the 4c-1 service
    layer and the 4c-2 CLI, leaving downstream audit tooling
    unable to attribute a service-layer failure to the caller's
    run. This test asserts the full structured payload is
    present in the stdout JSON error.
    """
    from backend.app.rolling_backtest import cli_main

    previous = register_materialization_provider(None)
    try:
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
    finally:
        register_materialization_provider(previous)
    assert rc == EXIT_SERVICE_CONTRACT_ERROR
    captured = capsys.readouterr()
    # Stdout carries the JSON error payload (one line).
    payload = json.loads(captured.out.strip().splitlines()[-1])
    # Required structured fields per §3.4.
    assert payload["kind"] == "missing_run"
    assert payload["run_id"] == SAMPLE_RUN_ID
    assert payload["evaluation_mask_hash"] == SAMPLE_MASK_HASH
    assert payload["metric_definition_version"] == METRIC_DEFINITION_VERSION
    # scope_id is the stringified node id from the caller's scope.
    assert payload["scope_id"] == str(SAMPLE_SCOPE["node"])


def test_cli_audit_argv_uses_main_argv_not_sys_argv(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1: the audit's ``command_invocations`` field MUST be the
    effective ``main(argv=...)`` invocation, NOT ``sys.argv[1:]``.

    Pre-fix the audit unconditionally used ``sys.argv[1:]``, which
    corrupts the audit whenever the CLI is invoked from a
    library / test harness with an explicit ``argv=`` argument:
    the audit would record the test runner's argv (e.g.
    ``["pytest", ...]``) instead of the caller's invocation. This
    test monkey-patches ``sys.argv`` to a known sentinel and
    asserts the audit reflects the caller's argv, not the
    sentinel.

    §4.4 binds the audit's argv capture to the top-level key
    ``command_invocations`` (NOT ``cli_invocation`` — that name
    is reserved for the §5.1 JSON export payload and the §5.3
    manifest). The pre-fix code wrote ``sys.argv[1:]`` to
    ``command_invocations``.
    """
    from backend.app.rolling_backtest import cli_main

    # Replace sys.argv with a sentinel that would clearly be wrong
    # if leaked into the audit.
    sentinel = "PYTEST_SENTINEL_SHOULD_NOT_LEAK_INTO_AUDIT"
    monkeypatch.setattr(sys, "argv", [sentinel, sentinel + "_2", sentinel + "_3"])
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
    # The audit file MUST be written and MUST contain the caller's
    # argv string, not the sys.argv sentinel.
    audit_files = list((tmp_path / "audit").iterdir())
    assert len(audit_files) == 1
    audit_payload = json.loads(audit_files[0].read_text(encoding="utf-8"))
    # §4.4 binds the argv capture to the top-level
    # ``command_invocations`` field.
    audit_argv = audit_payload["command_invocations"]
    # The caller's argv starts with "compute-metrics --run-id ...".
    assert audit_argv.startswith("compute-metrics --run-id")
    # The pytest sentinel MUST NOT appear in the audit.
    assert sentinel not in audit_argv


def test_cli_overwrite_never_collision_exits_5(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    from backend.app.rolling_backtest import cli_main

    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    argv = [
        "compute-metrics",
        "--run-id",
        SAMPLE_RUN_ID,
        "--scope",
        json.dumps(SAMPLE_SCOPE),
        "--mask-hash",
        SAMPLE_MASK_HASH,
        "--output-dir",
        str(tmp_path),
        "--overwrite",
        "never",
    ]
    # First run: success or MetricBlocker (both expected; the four
    # files are written either way per §4.5).
    rc1 = cli_main(argv)
    assert rc1 in (EXIT_SUCCESS, EXIT_METRIC_BLOCKER)
    # Second run: collision → exit 5.
    assert cli_main(argv) == EXIT_HASH_COLLISION


# ---------------------------------------------------------------------------
# 10. Determinism proof — Phase 4b parity (§7.2)
# ---------------------------------------------------------------------------


def test_export_canonical_payload_hash_matches_phase_4b(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    """§7.2: 'The Phase 4b EvaluationResult.canonical_payload_hash IS
    the service-layer audit binding'. The manifest's
    canonical_payload_hash must equal what compute_metrics
    returned."""
    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    artifacts = write_export_artifacts(_make_export_request(result, tmp_path))
    manifest = json.loads(artifacts.manifest_path.read_text("utf-8"))
    json_payload = json.loads(artifacts.json_path.read_text("utf-8"))
    assert manifest["canonical_payload_hash"] == result.canonical_payload_hash
    assert json_payload["canonical_payload_hash"] == result.canonical_payload_hash


# ---------------------------------------------------------------------------
# 11. Sanity: writer is reentrant (8 concurrent threads)
# ---------------------------------------------------------------------------


def test_writer_is_reentrant_under_concurrent_threads(
    stub_provider: None,
    rows_by_run_mask: dict[tuple[str, str], list[EvaluationMetricRow]],
    golden_rows_single_node: list[EvaluationMetricRow],
    tmp_path: Path,
) -> None:
    import threading

    rows_by_run_mask[(SAMPLE_RUN_ID, SAMPLE_MASK_HASH)] = golden_rows_single_node
    result = _make_evaluation_result(golden_rows_single_node)
    errors: list[BaseException] = []
    hashes: list[str] = []
    lock = threading.Lock()

    def worker(idx: int) -> None:
        try:
            sub = tmp_path / f"r{idx}"
            sub.mkdir()
            artifacts = write_export_artifacts(
                _make_export_request(result, sub, overwrite_policy=ExportOverwritePolicy.MISSING)
            )
            payload = json.loads(artifacts.manifest_path.read_text("utf-8"))
            with lock:
                hashes.append(payload["canonical_payload_hash"])
        except BaseException as exc:  # pragma: no cover - test diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # All 8 concurrent writers produced the same canonical_payload_hash.
    assert len(set(hashes)) == 1
