"""TASK-011 Phase 4c-2 — deterministic JSON / CSV / manifest export.

Implements the writer half of the 4c-2 contract. The module is a
**pure serialization layer** over the Phase 4b / 4c-1
``EvaluationResult``: it does NOT recompute metrics, it does NOT
introduce a new audit format, and it does NOT bypass service-layer
validation.

Frozen design source
--------------------
``docs/task-11-phase4c-service-cli-export-amendment.md`` on main
(frozen at content SHA
``9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216``).

Binding sections
----------------
* §5.1 — JSON export (canonical JSON, frozen top-level key order,
  Decimal canonical string, no float, UTF-8 no BOM, no trailing newline)
* §5.2 — CSV export (UTF-8 LF, frozen header order, RFC 4180 escaping,
  null -> empty field, stable row order)
* §5.3 — Manifest export (the only file callers must read first)
* §5.4 — Output directory layout
* §6.1 — Path determinism (filename pattern
  ``<run-id>__<scope-id>__<canonical_payload_hash>.<ext>``)
* §6.2 — Overwrite / collision policy
* §6.3 — Crash-recovery (remove stale ``*.tmp.<random>`` files on
  startup)

Forbidden scope (binding)
-------------------------
This module MUST NOT:

* recompute Phase 4b metrics;
* bypass the 4c-1 service-layer validation;
* read / write the database, network, or any other side channel;
* introduce a new audit format (4c-2 reuses Phase 4b's
  ``canonical_payload_hash``);
* implement 4c-3 production-shaped E2E / reload integrity;
* modify Phase 4a materialization semantics or Phase 4b metric
  formula semantics;
* implement ``replay_trained_model``;
* introduce ``current`` / ``latest`` / ``most recent`` implicit fallback.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from backend.app.rolling_backtest.canonical import (
    canonical_json_dumps,
)
from backend.app.rolling_backtest.metrics import (
    METRIC_DEFINITION_VERSION,
    EvaluationResult,
)

# Module version recorded in audit payloads (binding for §4.4 + §7.1).
CLI_VERSION: str = "4c-2.0.0"

# Default crash-recovery threshold (seconds) per §6.3.
DEFAULT_CRASH_RECOVERY_THRESHOLD_SECONDS: int = 3600

# File-name pattern (frozen) per §5.1 / §5.2 / §5.3 / §5.4 / §6.1.
_FILE_NAME_PATTERN: re.Pattern[str] = re.compile(
    r"^[A-Za-z0-9_.-]+__[0-9a-f]+__[0-9a-f]{64}\.[a-z]+$"
)

# Run-id is referenced in the filename and audit file. We allow
# ``[A-Za-z0-9_.-]`` (matches the regex above) to be liberal in
# accepting the same characters 4c-1 accepts; no leading/trailing
# whitespace; non-empty.
_RUN_ID_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_.-]+$")

# ISO-8601 Z-suffix UTC timestamp formatter per §5.1.
_ISO_8601_Z_FORMAT: str = "%Y-%m-%dT%H:%M:%S"

# Frozen top-level key order for the JSON export (§5.1) and the
# manifest export (§5.3). Both contracts explicitly require
# lexicographic key order; ``canonical_json_dumps`` enforces this
# via ``sorted(value.keys())``. These tuples document the binding
# contract for the auditor.
JSON_TOP_LEVEL_KEYS: tuple[str, ...] = (
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

MANIFEST_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "audit_payload_hash",
    "canonical_payload_hash",
    "csv_path",
    "decimal_scale",
    "evaluation_mask_hash",
    "inputs",
    "json_path",
    "metric_definition_version",
    "scope_id",
    "written_at_utc",
)

# Frozen CSV header order (binding for §5.2).
CSV_HEADER: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "comparable_row_count",
    "decimal_scale",
    "evaluation_mask_hash",
    "metric_scope_identity",
    "metric_definition_version",
    "blocker_count",
    "blocker_kinds",
)

# RFC 4180 CSV escape character (binding for §5.2).
_CSV_QUOTECHAR: str = '"'


class OverwritePolicy(StrEnum):
    """Overwrite / collision policy (binding for §6.2)."""

    NEVER = "never"
    MISSING = "missing"
    ALWAYS = "always"


class ExportSubdir(StrEnum):
    """Frozen output sub-directory names (binding for §5.4)."""

    JSON = "json"
    CSV = "csv"
    MANIFEST = "manifest"
    AUDIT = "audit"


@dataclass(frozen=True, slots=True)
class ExportRequest:
    """Inputs to the deterministic export writer (binding for §5 + §6).

    The request carries the caller's CLI invocation context (optional)
    and the policy choices. The writer derives the four target file
    paths from the ``EvaluationResult`` — the caller does NOT choose
    paths. This is the binding rule for §6.1: ``scope_id`` comes from
    ``EvaluationResult.outputs[0].metric_scope_identity`` (Phase 4b's
    hex identity), not from the caller's ``scope`` object.
    """

    result: EvaluationResult
    run_id: str
    decimal_scale: int
    output_dir: Path
    overwrite_policy: OverwritePolicy = OverwritePolicy.MISSING
    cli_invocation: dict[str, str] | None = None
    emit_audit: bool = True
    crash_recovery_threshold_seconds: int = DEFAULT_CRASH_RECOVERY_THRESHOLD_SECONDS


@dataclass(frozen=True, slots=True)
class ExportArtifacts:
    """The four file paths written by :func:`write_export_artifacts`."""

    json_path: Path
    csv_path: Path
    manifest_path: Path
    audit_path: Path | None  # ``None`` when ``--no-audit`` was used


def _now_utc_iso_z() -> str:
    """Return current UTC time as ISO-8601 with ``Z`` suffix (§5.1)."""
    return datetime.now(tz=UTC).strftime(_ISO_8601_Z_FORMAT) + "Z"


def _validate_run_id(run_id: str) -> None:
    """Reject run-ids that would produce unsafe file names."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError(f"run_id must be a non-empty string (got {run_id!r})")
    if not _RUN_ID_PATTERN.match(run_id):
        raise ValueError(f"run_id must match {_RUN_ID_PATTERN.pattern} (got {run_id!r})")


def _scope_id_from_result(result: EvaluationResult) -> str:
    """Return the ``scope_id`` for the filename (§6.1).

    The scope-id is the Phase 4b ``metric_scope_identity`` hex string
    of the first output. All outputs in an ``EvaluationResult`` share
    the same ``metric_scope_identity`` (per Phase 4b contract).
    """
    if not result.outputs:
        # Should not happen: ``compute_metrics`` always returns at
        # least the four counters. Defensive fallback.
        return "0" * 64
    return result.outputs[0].metric_scope_identity


def _build_file_name(*, run_id: str, scope_id: str, canonical_payload_hash: str, ext: str) -> str:
    """Build a file name per §5.1 / §5.2 / §5.3 / §6.1."""
    if not re.match(r"^[0-9a-f]{64}$", canonical_payload_hash):
        raise ValueError("canonical_payload_hash must be a 64-char lowercase hex string")
    if not re.match(r"^[0-9a-f]+$", scope_id):
        raise ValueError("scope_id must be a lowercase hex string")
    return f"{run_id}__{scope_id}__{canonical_payload_hash}.{ext}"


def _build_path(
    *,
    output_dir: Path,
    subdir: ExportSubdir,
    file_name: str,
) -> Path:
    return output_dir / subdir.value / file_name


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` atomically (§6.2).

    Uses a unique ``*.tmp.<random>`` file then ``os.replace`` so a
    crash mid-write leaves the previous bytes intact. The temp file
    is cleaned up by :func:`_crash_recovery_sweep` on the next run.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".tmp.{target.name}.",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, target)
    except BaseException:
        # Best-effort cleanup if os.replace never happened.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _crash_recovery_sweep(output_dir: Path, threshold_seconds: int) -> None:
    """Remove stale ``*.tmp.<random>`` files older than threshold (§6.3)."""
    if not output_dir.exists():
        return
    cutoff = time.time() - threshold_seconds
    for subdir in ExportSubdir:
        sub_path = output_dir / subdir.value
        if not sub_path.exists():
            continue
        for entry in sub_path.iterdir():
            if not entry.is_file():
                continue
            name = entry.name
            if not name.startswith(".tmp."):
                continue
            try:
                mtime = entry.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime < cutoff:
                try:
                    entry.unlink()
                except FileNotFoundError:
                    pass


def _check_collision(target_paths: tuple[Path, ...], policy: OverwritePolicy) -> None:
    """Raise :class:`PathCollision` per §6.2 / §8.

    * ``never`` — refuse if ANY target path exists.
    * ``missing`` (default) — refuse if ANY target path exists.
    * ``always`` — never refuses.
    """
    if policy == OverwritePolicy.ALWAYS:
        return
    for path in target_paths:
        if path.exists():
            raise PathCollision(path)


def _canonical_decimal_for_csv(value: Decimal | None) -> str:
    """Render a Decimal as the canonical string (§5.2).

    Mirrors ``_canonical_decimal`` from ``metrics.py`` (kept private
    there). Uses the harvest_state canonical-decimal primitive.
    """
    if value is None:
        return ""  # CSV null -> empty field (§5.2)
    from backend.app.harvest_state.canonical import canonical_decimal_string

    if not value.is_finite():
        # Phase 4b never produces non-finite Decimals, but be defensive.
        return ""
    return canonical_decimal_string(value)


class PathCollision(RuntimeError):
    """Raised when the target file path already exists and policy forbids overwrite."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"path collision: {path}")
        self.path = path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_target_paths(
    request: ExportRequest, *, output_dir: Path | None = None
) -> tuple[Path, Path, Path, Path]:
    """Compute the four target file paths for an export (§5.4 + §6.1).

    Returns
    -------
    (json_path, csv_path, manifest_path, audit_path) : tuple[Path, Path, Path, Path]
        ``audit_path`` is always returned; whether the file is
        actually written depends on ``request.cli_invocation["--no-audit"]``
        in :func:`write_export_artifacts`.
    """
    _validate_run_id(request.run_id)
    out = output_dir if output_dir is not None else request.output_dir
    if not out.is_absolute():
        raise ValueError(f"output_dir must be absolute (got {out})")
    scope_id = _scope_id_from_result(request.result)
    file_name_json = _build_file_name(
        run_id=request.run_id,
        scope_id=scope_id,
        canonical_payload_hash=request.result.canonical_payload_hash,
        ext="json",
    )
    file_name_csv = _build_file_name(
        run_id=request.run_id,
        scope_id=scope_id,
        canonical_payload_hash=request.result.canonical_payload_hash,
        ext="csv",
    )
    file_name_manifest = _build_file_name(
        run_id=request.run_id,
        scope_id=scope_id,
        canonical_payload_hash=request.result.canonical_payload_hash,
        ext="json",
    )
    file_name_audit = _build_file_name(
        run_id=request.run_id,
        scope_id=scope_id,
        canonical_payload_hash=request.result.canonical_payload_hash,
        ext="json",
    )
    return (
        _build_path(output_dir=out, subdir=ExportSubdir.JSON, file_name=file_name_json),
        _build_path(output_dir=out, subdir=ExportSubdir.CSV, file_name=file_name_csv),
        _build_path(
            output_dir=out,
            subdir=ExportSubdir.MANIFEST,
            file_name=file_name_manifest,
        ),
        _build_path(
            output_dir=out,
            subdir=ExportSubdir.AUDIT,
            file_name=file_name_audit,
        ),
    )


def _build_json_payload(request: ExportRequest, *, written_at_utc: str) -> dict[str, object]:
    """Build the JSON-export top-level payload dict (§5.1)."""
    scope_id = _scope_id_from_result(request.result)
    outputs = [o.to_audit_payload() for o in request.result.outputs]
    payload: dict[str, object] = {
        "canonical_payload_hash": request.result.canonical_payload_hash,
        "decimal_scale": request.decimal_scale,
        "evaluation_mask_hash": _evaluation_mask_hash_from_outputs(request.result.outputs),
        "metric_definition_version": METRIC_DEFINITION_VERSION,
        "outputs": outputs,
        "run_id": request.run_id,
        "scope_id": scope_id,
        "written_at_utc": written_at_utc,
    }
    if request.cli_invocation is not None:
        payload["cli_invocation"] = dict(request.cli_invocation)
    return payload


def _build_manifest_payload(
    request: ExportRequest,
    *,
    written_at_utc: str,
    audit_payload_hash: str | None,
    json_relpath: str,
    csv_relpath: str,
) -> dict[str, object]:
    """Build the manifest top-level payload dict (§5.3)."""
    scope_id = _scope_id_from_result(request.result)
    cli = request.cli_invocation or {}
    inputs: dict[str, object] = {
        "metric_subset": cli.get("--metric-subset", ""),
        "overwrite_policy": request.overwrite_policy.value,
        "run_id": request.run_id,
        "scope": cli.get("--scope", ""),
    }
    payload: dict[str, object] = {
        "audit_payload_hash": audit_payload_hash,
        "canonical_payload_hash": request.result.canonical_payload_hash,
        "csv_path": csv_relpath,
        "decimal_scale": request.decimal_scale,
        "evaluation_mask_hash": _evaluation_mask_hash_from_outputs(request.result.outputs),
        "inputs": inputs,
        "json_path": json_relpath,
        "metric_definition_version": METRIC_DEFINITION_VERSION,
        "scope_id": scope_id,
        "written_at_utc": written_at_utc,
    }
    return payload


def _build_audit_payload(
    request: ExportRequest,
    *,
    started_at_utc: str,
    finished_at_utc: str,
    exit_code: int,
    json_path: Path,
    csv_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    """Build the CLI audit payload dict (§4.4 + §7.1)."""
    cli = request.cli_invocation or {}
    outputs: dict[str, str] = {}
    for label, path in (
        ("json", json_path),
        ("csv", csv_path),
        ("manifest", manifest_path),
    ):
        outputs[label] = str(path)
    payload: dict[str, object] = {
        "cli_version": CLI_VERSION,
        "command_invocations": cli.get("argv", ""),
        "inputs": {
            "run_id": request.run_id,
            "scope": cli.get("--scope", ""),
            "mask_hash": cli.get("--mask-hash", ""),
            "metric_subset": cli.get("--metric-subset", ""),
            "decimal_scale": request.decimal_scale,
            "overwrite_policy": request.overwrite_policy.value,
        },
        "outputs": outputs,
        "metric_definition_version": METRIC_DEFINITION_VERSION,
        "evaluation_mask_hash": _evaluation_mask_hash_from_outputs(request.result.outputs),
        "run_id": request.run_id,
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "exit_code": exit_code,
    }
    return payload


def _evaluation_mask_hash_from_outputs(
    outputs: Sequence[object],
) -> str:
    """Return the evaluation-mask hash shared by all outputs in the result."""
    if not outputs:
        return ""
    evaluation_mask_hash = getattr(outputs[0], "evaluation_mask_hash", None)
    if not isinstance(evaluation_mask_hash, str):
        return ""
    return evaluation_mask_hash


def write_export_artifacts(request: ExportRequest) -> ExportArtifacts:
    """Write the four target files for a 4c-2 export (§5.4).

    The function:

    1. Validates inputs.
    2. Computes the four target paths (deterministic).
    3. Runs crash-recovery sweep (§6.3).
    4. Checks collision per overwrite policy (§6.2).
    5. Atomically writes the JSON, CSV, manifest, and audit files.

    Returns an :class:`ExportArtifacts` describing the four paths.
    Raises :class:`PathCollision` on policy violation.
    """
    if not request.output_dir.is_absolute():
        raise ValueError(f"output_dir must be absolute (got {request.output_dir})")
    _validate_run_id(request.run_id)
    json_path, csv_path, manifest_path, audit_path = build_target_paths(request)
    _crash_recovery_sweep(request.output_dir, request.crash_recovery_threshold_seconds)
    target_paths: tuple[Path, ...] = (
        json_path,
        csv_path,
        manifest_path,
    ) + ((audit_path,) if request.emit_audit else ())
    _check_collision(target_paths, request.overwrite_policy)

    started_at_utc = _now_utc_iso_z()

    # 1) JSON export (§5.1)
    json_payload = _build_json_payload(request, written_at_utc=started_at_utc)
    json_bytes = canonical_json_dumps(json_payload).encode("utf-8")
    _atomic_write_bytes(json_path, json_bytes)

    # 2) CSV export (§5.2)
    csv_bytes = _serialize_csv(request).encode("utf-8")
    _atomic_write_bytes(csv_path, csv_bytes)

    # 3) Audit file (§4.4 + §7.1) — optional via --no-audit
    audit_bytes: bytes | None = None
    audit_payload_hash: str | None = None
    if request.emit_audit:
        audit_payload = _build_audit_payload(
            request,
            started_at_utc=started_at_utc,
            finished_at_utc=started_at_utc,
            exit_code=0,
            json_path=json_path,
            csv_path=csv_path,
            manifest_path=manifest_path,
        )
        audit_bytes = canonical_json_dumps(audit_payload).encode("utf-8")
        audit_payload_hash = hashlib.sha256(audit_bytes).hexdigest()
        _atomic_write_bytes(audit_path, audit_bytes)

    # 4) Manifest export (§5.3)
    json_relpath = str(json_path.relative_to(request.output_dir).as_posix())
    csv_relpath = str(csv_path.relative_to(request.output_dir).as_posix())
    manifest_payload = _build_manifest_payload(
        request,
        written_at_utc=started_at_utc,
        audit_payload_hash=audit_payload_hash,
        json_relpath=json_relpath,
        csv_relpath=csv_relpath,
    )
    manifest_bytes = canonical_json_dumps(manifest_payload).encode("utf-8")
    _atomic_write_bytes(manifest_path, manifest_bytes)

    return ExportArtifacts(
        json_path=json_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        audit_path=audit_path if request.emit_audit else None,
    )


def _serialize_csv(request: ExportRequest) -> str:
    """Serialize the deterministic CSV body (§5.2).

    Row order matches ``request.outputs_for_export`` (which the
    service-layer test contract pins to canonical Phase 4b order —
    counters first, then aggregate metrics).
    """
    buf = io.StringIO()
    # csv.writer with lineterminator='\n' (LF only, §5.2).
    writer = csv.writer(
        buf,
        lineterminator="\n",
        quotechar=_CSV_QUOTECHAR,
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerow(CSV_HEADER)
    for output in request.result.outputs:
        blocker_kinds = ",".join(sorted({b.kind.value for b in output.blocked_reasons}))
        writer.writerow(
            (
                output.metric_name,
                _canonical_decimal_for_csv(output.metric_value),
                output.comparable_row_count,
                output.decimal_scale,
                output.evaluation_mask_hash,
                output.metric_scope_identity,
                output.metric_definition_version,
                len(output.blocked_reasons),
                blocker_kinds,
            )
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# File-name pattern (frozen) — exposed for tests / callers that need
# to validate filenames. Not part of the public CLI contract.
# ---------------------------------------------------------------------------


def file_name_pattern() -> re.Pattern[str]:
    """Return the frozen file-name pattern (§5.1 / §5.2 / §5.3 / §6.1)."""
    return _FILE_NAME_PATTERN
