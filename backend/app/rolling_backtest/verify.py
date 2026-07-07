"""TASK-011 Phase 4c-3 — production-shaped E2E and reload integrity.

This module is the 4c-3 implementation slice of the Phase 4c design
contract (``docs/task-11-phase4c-3-production-e2e-reload-integrity-amendment.md``
on main, frozen at content SHA
``ef5732243db327ae41bd223d77ae7d820b344aca91c67592f82a686b1bd686f4``).
It implements the manifest-first reload path and the typed failure model
for verifying a previously-written 4c-2 artifact set.

Frozen design source
--------------------
``docs/task-11-phase4c-3-production-e2e-reload-integrity-amendment.md`` on
main (frozen at content SHA
``ef5732243db327ae41bd223d77ae7d820b344aca91c67592f82a686b1bd686f4``).

Binding sections
----------------
* §3 — Production-shaped E2E contract (this module provides the
  reload-side primitives only; the E2E test harness lives in
  ``backend/tests/rolling_backtest/test_verify.py`` and is permitted
  to invoke the CLI as a subprocess per §3.3).
* §4 — Reload integrity contract (manifest-first path, hash
  verification, CSV ↔ JSON consistency, path integrity).
* §5 — Provenance chain contract (no new hash; reuses 4b/4c-1/4c-2
  identities).
* §6 — Failure / blocker model (10 typed failure kinds).
* §7 — Test contract (test surface description; 16 test cases).

Forbidden scope (binding)
-------------------------
This module MUST NOT:

* recompute Phase 4b metrics;
* bypass the 4c-1 service-layer validation;
* read / write the database, network, or any other side channel;
* introduce a new audit format;
* modify Phase 4a materialization semantics or Phase 4b metric
  formula semantics;
* implement ``replay_trained_model``;
* introduce ``current`` / ``latest`` / ``most recent`` implicit
  fallback. Every reload MUST be invoked with an explicit
  ``root`` directory (the directory containing the ``{json, csv,
  manifest, audit}`` sub-directories) and an optional explicit
  ``expected_mask_hash``. The function refuses to enumerate or
  select an implicit artifact set.
"""

from __future__ import annotations

import csv as csv_module
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from backend.app.rolling_backtest.export import (
    CSV_HEADER,
    JSON_TOP_LEVEL_KEYS,
    MANIFEST_TOP_LEVEL_KEYS,
)
from backend.app.rolling_backtest.metrics import (
    METRIC_DEFINITION_VERSION,
    canonical_payload_hash,
)

# Frozen version of this module. Bumping requires a new design amendment.
RELOAD_CONTRACT_VERSION: Final[str] = "4c-3.0.0"

# Frozen sub-directory names from the 4c-2 export (binding for §4.5).
_JSON_SUBDIR: Final[str] = "json"
_CSV_SUBDIR: Final[str] = "csv"
_MANIFEST_SUBDIR: Final[str] = "manifest"
_AUDIT_SUBDIR: Final[str] = "audit"


# ---------------------------------------------------------------------------
# Failure / blocker model (design §6.1 – §6.10)
# ---------------------------------------------------------------------------


class ReloadContractError(ValueError):
    """Reload-integrity contract error (design §6 — base class).

    Subclasses ``ValueError`` for forward-compat with callers that
    expect ``ValueError`` on bad input. The ``kind`` field carries the
    machine-readable error code; the ``message`` field carries a
    human-readable description. The :func:`to_payload` method renders
    a structured payload with the documented carries from §6.1 – §6.10.
    """

    kind: str = "reload_contract_error"

    def __init__(self, message: str, **carries: object) -> None:
        super().__init__(message)
        self.message = message
        self._carries: dict[str, object] = dict(carries)

    def to_payload(self) -> dict[str, object]:
        """Render the structured error payload (§6)."""
        payload: dict[str, object] = {
            "kind": self.kind,
            "message": self.message,
            "metric_definition_version": METRIC_DEFINITION_VERSION,
            "reload_contract_version": RELOAD_CONTRACT_VERSION,
        }
        payload.update(self._carries)
        return payload


class MissingArtifactError(ReloadContractError):
    """A file referenced in the manifest is missing on disk (§6.1)."""

    kind = "missing_artifact"


class MalformedJsonError(ReloadContractError):
    """A JSON file failed to parse or is missing a frozen top-level key (§6.2)."""

    kind = "malformed_json"


class MalformedCsvError(ReloadContractError):
    """A CSV file failed to parse or has a missing/incorrect header row (§6.3)."""

    kind = "malformed_csv"


class ManifestMismatchError(ReloadContractError):
    """A manifest failed a structural or version check (§6.4)."""

    kind = "manifest_mismatch"


class CanonicalPayloadHashMismatchError(ReloadContractError):
    """Recomputed ``canonical_payload_hash`` does not equal the manifest value (§6.5)."""

    kind = "canonical_payload_hash_mismatch"


class AuditPayloadHashMismatchError(ReloadContractError):
    """Recomputed ``SHA-256(audit_bytes)`` does not equal the manifest value (§6.6)."""

    kind = "audit_payload_hash_mismatch"


class RowOrderMismatchError(ReloadContractError):
    """CSV ``metric_name`` column order differs from JSON ``outputs[*].metric_name`` (§6.7)."""

    kind = "row_order_mismatch"


class MetricDefinitionVersionMismatchError(ReloadContractError):
    """An artifact's ``metric_definition_version`` is not ``"4b-1.0.0"`` (§6.8)."""

    kind = "metric_definition_version_mismatch"


class MaskHashMismatchError(ReloadContractError):
    """The JSON's ``evaluation_mask_hash`` differs from the caller's expected value (§6.9)."""

    kind = "mask_hash_mismatch"


class ForbiddenImplicitFallbackError(ReloadContractError):
    """A reload attempted implicit ``current`` / ``latest`` / ``most recent`` selection (§6.10)."""

    kind = "forbidden_implicit_fallback"


# Frozen mapping from the 4c-3 error kind strings (per design §6) to the
# concrete exception classes above. The exporter of structured payloads
# (e.g. a future CLI surface) MUST use this registry to discriminate
# kinds — never ``isinstance`` on a class-name substring.
_RELOAD_ERROR_KIND_TO_CLASS: Final[Mapping[str, type[ReloadContractError]]] = {
    "missing_artifact": MissingArtifactError,
    "malformed_json": MalformedJsonError,
    "malformed_csv": MalformedCsvError,
    "manifest_mismatch": ManifestMismatchError,
    "canonical_payload_hash_mismatch": CanonicalPayloadHashMismatchError,
    "audit_payload_hash_mismatch": AuditPayloadHashMismatchError,
    "row_order_mismatch": RowOrderMismatchError,
    "metric_definition_version_mismatch": MetricDefinitionVersionMismatchError,
    "mask_hash_mismatch": MaskHashMismatchError,
    "forbidden_implicit_fallback": ForbiddenImplicitFallbackError,
}


def get_reload_error_class(kind: str) -> type[ReloadContractError]:
    """Return the exception class bound to ``kind`` (design §6).

    Raises :class:`KeyError` if ``kind`` is not a frozen 4c-3 kind.
    """
    return _RELOAD_ERROR_KIND_TO_CLASS[kind]


def all_reload_error_kinds() -> tuple[str, ...]:
    """Return the frozen tuple of 10 reload error kinds (design §6)."""
    return tuple(_RELOAD_ERROR_KIND_TO_CLASS.keys())


# ---------------------------------------------------------------------------
# Reload result (the typed return value of ``verify_artifact_set``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReloadResult:
    """Typed reload verification result (design §4 / §5).

    Carries the reloaded identity triple and the verified file paths.
    A successful return value is the proof that the artifact set is
    byte-consistent with the frozen 4c-1 / 4c-2 / 4b identities.

    The ``metric_scope_identity`` is the Phase 4b scope identity of
    the first output row (all outputs in a 4c-2 export share the
    same identity per the 4b-1.0.0 contract).
    """

    run_id: str
    evaluation_mask_hash: str
    scope_id: str
    canonical_payload_hash: str
    audit_payload_hash: str | None
    metric_definition_version: str
    json_path: Path
    csv_path: Path
    manifest_path: Path
    audit_path: Path | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, object]:
    """Read a UTF-8 JSON file. Raises :class:`MalformedJsonError` on failure."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MalformedJsonError(
            f"json file not found: {path}",
            path=str(path),
            reason="file_not_found",
        ) from exc
    except OSError as exc:
        raise MalformedJsonError(
            f"json read error: {path}: {exc}",
            path=str(path),
            reason="os_error",
        ) from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MalformedJsonError(
            f"json parse error in {path}: {exc.msg} (line {exc.lineno}, col {exc.colno})",
            path=str(path),
            reason=f"json_decode_error:{exc.msg}",
        ) from exc
    if not isinstance(parsed, dict):
        raise MalformedJsonError(
            f"json top-level is not an object: {path} (got {type(parsed).__name__})",
            path=str(path),
            reason="not_an_object",
        )
    return parsed


def _validate_top_level_keys(
    payload: dict[str, object],
    *,
    expected: tuple[str, ...],
    path: str,
) -> None:
    """Assert that ``payload`` has exactly the frozen top-level key set."""
    actual_keys = tuple(payload.keys())
    if actual_keys != expected:
        missing = [k for k in expected if k not in payload]
        extra = [k for k in actual_keys if k not in expected]
        raise MalformedJsonError(
            f"json top-level keys mismatch: {path} (missing={missing}, extra={extra})",
            path=path,
            reason="key_mismatch",
            expected=list(expected),
            actual=list(actual_keys),
        )


def _read_manifest(root: Path) -> tuple[dict[str, object], Path]:
    """Read the (single) manifest file from ``root``.

    The 4c-2 contract writes a single manifest per artifact set under
    ``<root>/manifest/`` with a deterministic filename pattern
    ``<run-id>__<scope-id>__<hash>.json`` (see
    ``backend.app.rolling_backtest.export._build_file_name``). The
    reload refuses implicit selection (§6.10): if multiple manifest
    files exist, the reload raises :class:`ForbiddenImplicitFallbackError`.
    """
    manifest_dir = root / _MANIFEST_SUBDIR
    if not manifest_dir.is_dir():
        raise MissingArtifactError(
            f"manifest sub-directory missing: {manifest_dir}",
            path=str(manifest_dir),
            expected_kind="manifest",
        )
    manifest_files = sorted(p for p in manifest_dir.iterdir() if p.is_file())
    if not manifest_files:
        raise MissingArtifactError(
            f"no manifest file found under {manifest_dir}",
            path=str(manifest_dir),
            expected_kind="manifest",
        )
    if len(manifest_files) > 1:
        raise ForbiddenImplicitFallbackError(
            f"multiple manifest files found under {manifest_dir}; "
            "explicit manifest path required (§6.10)",
            attempted_selection="current",
        )
    manifest_path = manifest_files[0]
    payload = _read_json(manifest_path)
    return payload, manifest_path


def _resolve_under_root(root: Path, relpath: str) -> Path:
    """Resolve ``relpath`` under ``root`` and assert it does not escape
    ``root`` (§4.5 path integrity: every manifest path MUST resolve
    under the reload's root directory).
    """
    candidate = (root / relpath).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ManifestMismatchError(
            f"manifest path escapes reload root: {relpath} -> {candidate}",
            path=relpath,
            field="path_escape",
            expected=str(root_resolved),
            actual=str(candidate),
        ) from exc
    return candidate


def _validate_metric_definition_version(payload: dict[str, object], *, path: str) -> None:
    actual = payload.get("metric_definition_version")
    if actual != METRIC_DEFINITION_VERSION:
        raise MetricDefinitionVersionMismatchError(
            f"metric_definition_version mismatch in {path}: "
            f"expected {METRIC_DEFINITION_VERSION!r}, got {actual!r}",
            path=path,
            expected=METRIC_DEFINITION_VERSION,
            actual=actual,
        )


def _parse_decimal_safe(value: object) -> Decimal:
    """Parse a decimal value for CSV comparison (allow str / Decimal / None).

    Returns ``Decimal("NaN")`` for ``None`` so the comparison logic
    can distinguish "metric value present" from "metric value missing"
    in a way that does not raise.
    """
    if value is None:
        return Decimal("NaN")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        return Decimal(value)
    raise MalformedJsonError(
        f"metric value is not a Decimal / str / None: {value!r}",
        path="<outputs[*].metric_value>",
        reason="not_a_decimal",
    )


# ---------------------------------------------------------------------------
# Public API: verify_artifact_set
# ---------------------------------------------------------------------------


def verify_artifact_set(
    root: Path,
    *,
    expected_mask_hash: str | None = None,
) -> ReloadResult:
    """Verify a 4c-2 artifact set on disk (design §4 reload path).

    The reload is **stateless** (§4.1): the function reads the manifest
    first, resolves the JSON / CSV / audit paths from it, and verifies
    their byte-level integrity against the manifest's
    ``canonical_payload_hash`` and ``audit_payload_hash``.

    Parameters
    ----------
    root : Path
        The directory containing the ``{json, csv, manifest, audit}``
        sub-directories. MUST be a directory.
    expected_mask_hash : str | None
        If provided, the function asserts that the JSON's
        ``evaluation_mask_hash`` equals this value (§6.9).
        ``None`` disables the check (still records the actual value
        in the result).

    Returns
    -------
    ReloadResult

    Raises
    ------
    ReloadContractError (subclass per design §6)
        A typed error carrying the structured payload for the failure
        kind detected.

    Forbidden
    ---------
    * This function does NOT perform implicit selection (§6.10). If
      multiple manifest files exist, the function raises
      :class:`ForbiddenImplicitFallbackError`.
    * This function does NOT perform database or network IO (§7.7).
    * This function does NOT recompute Phase 4b metrics.
    """
    if not isinstance(root, Path):
        root = Path(root)
    if not root.is_dir():
        raise MissingArtifactError(
            f"reload root is not a directory: {root}",
            path=str(root),
            expected_kind="root",
        )

    # 1. Read manifest (§4.1).
    manifest_payload, manifest_path = _read_manifest(root)

    # 2. Manifest top-level keys MUST match the frozen tuple (§5.3).
    _validate_top_level_keys(
        manifest_payload,
        expected=MANIFEST_TOP_LEVEL_KEYS,
        path=str(manifest_path),
    )

    # 3. metric_definition_version MUST be 4b-1.0.0 (§6.4 / §6.8).
    _validate_metric_definition_version(manifest_payload, path=str(manifest_path))

    # 4. Extract manifest values.
    canonical_payload_hash_expected = manifest_payload.get("canonical_payload_hash")
    if not isinstance(canonical_payload_hash_expected, str) or not _is_64hex(
        canonical_payload_hash_expected
    ):
        raise ManifestMismatchError(
            f"manifest.canonical_payload_hash is not a 64-char lowercase hex string: "
            f"{canonical_payload_hash_expected!r}",
            path=str(manifest_path),
            field="canonical_payload_hash",
            expected="64-char lowercase hex",
            actual=canonical_payload_hash_expected,
        )
    audit_payload_hash_expected = manifest_payload.get("audit_payload_hash")
    if audit_payload_hash_expected is not None and not _is_64hex(audit_payload_hash_expected):
        raise ManifestMismatchError(
            f"manifest.audit_payload_hash is not a 64-char lowercase hex string or null: "
            f"{audit_payload_hash_expected!r}",
            path=str(manifest_path),
            field="audit_payload_hash",
            expected="64-char lowercase hex or null",
            actual=audit_payload_hash_expected,
        )
    json_relpath = manifest_payload.get("json_path")
    csv_relpath = manifest_payload.get("csv_path")
    if not isinstance(json_relpath, str) or not isinstance(csv_relpath, str):
        raise ManifestMismatchError(
            f"manifest.json_path / manifest.csv_path must be strings: "
            f"json={json_relpath!r} csv={csv_relpath!r}",
            path=str(manifest_path),
            field="json_path|csv_path",
            expected="str",
            actual={"json_path": json_relpath, "csv_path": csv_relpath},
        )

    # 5. Resolve and verify JSON / CSV / audit paths under the reload
    #    root (§4.5 path integrity).
    json_path = _resolve_under_root(root, json_relpath)
    csv_path = _resolve_under_root(root, csv_relpath)
    if not json_path.is_file():
        raise MissingArtifactError(
            f"json file missing on disk: {json_path}",
            path=str(json_path),
            expected_kind="json",
        )
    if not csv_path.is_file():
        raise MissingArtifactError(
            f"csv file missing on disk: {csv_path}",
            path=str(csv_path),
            expected_kind="csv",
        )

    audit_path: Path | None = None
    audit_bytes: bytes | None = None
    if audit_payload_hash_expected is not None:
        # Audit is expected. The 4c-2 contract writes the audit under
        # <root>/audit/ with the same filename pattern; the manifest
        # does NOT carry an explicit audit_path, so we compute it
        # from the JSON path (the audit uses the same filename stem).
        audit_relpath = str(json_path.relative_to(root.resolve())).replace(
            _JSON_SUBDIR + "/", _AUDIT_SUBDIR + "/", 1
        )
        audit_path = _resolve_under_root(root, audit_relpath)
        if not audit_path.is_file():
            raise MissingArtifactError(
                f"audit file missing on disk: {audit_path}",
                path=str(audit_path),
                expected_kind="audit",
            )
        audit_bytes = audit_path.read_bytes()

    # 6. JSON parse + top-level keys + version (§5.1 / §6.2 / §6.8).
    json_payload = _read_json(json_path)
    _validate_top_level_keys(json_payload, expected=JSON_TOP_LEVEL_KEYS, path=str(json_path))
    _validate_metric_definition_version(json_payload, path=str(json_path))

    # 7. evaluation_mask_hash consistency: JSON MUST equal manifest.
    json_mask_hash = json_payload.get("evaluation_mask_hash")
    manifest_mask_hash = manifest_payload.get("evaluation_mask_hash")
    if json_mask_hash != manifest_mask_hash:
        raise ManifestMismatchError(
            f"evaluation_mask_hash differs between json ({json_mask_hash!r}) and "
            f"manifest ({manifest_mask_hash!r})",
            path=str(manifest_path),
            field="evaluation_mask_hash",
            expected=json_mask_hash,
            actual=manifest_mask_hash,
        )

    # 8. evaluation_mask_hash vs caller's expected_mask_hash (§6.9).
    if expected_mask_hash is not None and json_mask_hash != expected_mask_hash:
        raise MaskHashMismatchError(
            f"evaluation_mask_hash mismatch: expected {expected_mask_hash!r}, "
            f"got {json_mask_hash!r}",
            expected_mask_hash=expected_mask_hash,
            actual_mask_hash=json_mask_hash,
        )

    # 9. Recompute canonical_payload_hash from JSON outputs (§4.2 / §6.5).
    json_outputs = json_payload.get("outputs")
    if not isinstance(json_outputs, list):
        raise MalformedJsonError(
            f"json.outputs is not a list: {json_path}",
            path=str(json_path),
            reason="outputs_not_list",
        )
    # Per the Phase 4b contract the digest is computed over
    # {"outputs": [...], "metric_definition_version": "4b-1.0.0"}
    # (see backend.app.rolling_backtest.metrics.evaluate_scope).
    canonical_payload_hash_actual = canonical_payload_hash(
        {
            "outputs": json_outputs,
            "metric_definition_version": METRIC_DEFINITION_VERSION,
        }
    )
    if canonical_payload_hash_actual != canonical_payload_hash_expected:
        raise CanonicalPayloadHashMismatchError(
            f"canonical_payload_hash mismatch in {json_path}: "
            f"expected {canonical_payload_hash_expected!r}, "
            f"recomputed {canonical_payload_hash_actual!r}",
            path=str(json_path),
            expected=canonical_payload_hash_expected,
            actual=canonical_payload_hash_actual,
        )

    # 10. Audit hash (§4.3 / §6.6).
    if audit_bytes is not None and audit_payload_hash_expected is not None:
        audit_payload_hash_actual = hashlib.sha256(audit_bytes).hexdigest()
        if audit_payload_hash_actual != audit_payload_hash_expected:
            raise AuditPayloadHashMismatchError(
                f"audit_payload_hash mismatch in {audit_path}: "
                f"expected {audit_payload_hash_expected!r}, "
                f"recomputed {audit_payload_hash_actual!r}",
                path=str(audit_path) if audit_path is not None else "<audit>",
                expected=audit_payload_hash_expected,
                actual=audit_payload_hash_actual,
            )

    # 11. CSV parse + header + row order (§4.4 / §6.3 / §6.7).
    csv_text = csv_path.read_text(encoding="utf-8")
    csv_reader = csv_module.reader(io_stringio(csv_text))
    csv_rows = list(csv_reader)
    if not csv_rows:
        raise MalformedCsvError(
            f"csv has no rows: {csv_path}",
            path=str(csv_path),
            reason="no_rows",
        )
    actual_header = tuple(csv_rows[0])
    if actual_header != CSV_HEADER:
        raise MalformedCsvError(
            f"csv header mismatch in {csv_path}: "
            f"expected {list(CSV_HEADER)}, got {list(actual_header)}",
            path=str(csv_path),
            reason="header_mismatch",
            expected=list(CSV_HEADER),
            actual=list(actual_header),
        )
    csv_data_rows = csv_rows[1:]
    if len(csv_data_rows) != len(json_outputs):
        raise MalformedCsvError(
            f"csv row count mismatch in {csv_path}: "
            f"expected {len(json_outputs)} data rows, got {len(csv_data_rows)}",
            path=str(csv_path),
            reason="row_count_mismatch",
            expected=len(json_outputs),
            actual=len(csv_data_rows),
        )
    csv_metric_name_column_index = CSV_HEADER.index("metric_name")
    csv_metric_names = [row[csv_metric_name_column_index] for row in csv_data_rows]
    json_metric_names = [str(o.get("metric_name")) for o in json_outputs]
    if csv_metric_names != json_metric_names:
        # Compute first diverging index.
        first_diverging_index = 0
        for i, (c, j) in enumerate(zip(csv_metric_names, json_metric_names, strict=False)):
            if c != j:
                first_diverging_index = i
                break
        raise RowOrderMismatchError(
            f"csv metric_name order differs from json outputs order in {csv_path}: "
            f"first diverging index = {first_diverging_index}",
            path=str(csv_path),
            csv_order=csv_metric_names,
            json_order=json_metric_names,
            first_diverging_index=first_diverging_index,
        )

    # 12. Build the reload result.
    run_id_value = json_payload.get("run_id")
    scope_id_value = json_payload.get("scope_id")
    if not isinstance(run_id_value, str) or not isinstance(scope_id_value, str):
        raise MalformedJsonError(
            f"json.run_id / json.scope_id must be strings: "
            f"run_id={run_id_value!r} scope_id={scope_id_value!r}",
            path=str(json_path),
            reason="run_id_or_scope_id_not_string",
        )

    return ReloadResult(
        run_id=run_id_value,
        evaluation_mask_hash=json_mask_hash if isinstance(json_mask_hash, str) else "",
        scope_id=scope_id_value,
        canonical_payload_hash=canonical_payload_hash_actual,
        audit_payload_hash=(
            audit_payload_hash_expected if isinstance(audit_payload_hash_expected, str) else None
        ),
        metric_definition_version=METRIC_DEFINITION_VERSION,
        json_path=json_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        audit_path=audit_path,
    )


# ---------------------------------------------------------------------------
# Small io helper: a thin ``io.StringIO`` wrapper that we use above for
# csv parsing. We isolate it here so future porting to async IO is one
# place.
# ---------------------------------------------------------------------------


def io_stringio(text: str) -> Any:
    """Return a ``io.StringIO`` for ``text`` (helper for csv parsing)."""
    import io as _io

    return _io.StringIO(text)


def _is_64hex(value: object) -> bool:
    """Return True iff ``value`` is a 64-character lowercase hex string."""
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(c in "0123456789abcdef" for c in value)


# ---------------------------------------------------------------------------
# ``canonical_payload_hash_of_outputs`` — convenience wrapper that
# mirrors the public primitive in ``metrics.py`` but is exposed here for
# use by callers that do not want to import the 4b module directly. It
# is a thin alias and is NOT a new hash; the re-binding of the 4c-3
# contract to the 4b-1.0.0 ``canonical_payload_hash`` primitive is the
# design's binding rule (§4.2).
# ---------------------------------------------------------------------------


def canonical_payload_hash_of_outputs(outputs: list[Mapping[str, object]]) -> str:
    """Re-derive ``canonical_payload_hash`` from a JSON ``outputs`` list.

    Thin alias for :func:`backend.app.rolling_backtest.metrics.canonical_payload_hash`
    bound to the Phase 4b-1.0.0 contract. Provided here so that 4c-3
    callers do not need to import the 4b module directly.

    The Phase 4b-1.0.0 contract computes the digest over
    ``{"outputs": [...], "metric_definition_version": "4b-1.0.0"}``
    (see :func:`backend.app.rolling_backtest.metrics.evaluate_scope`).
    """
    return canonical_payload_hash(
        {
            "outputs": list(outputs),
            "metric_definition_version": METRIC_DEFINITION_VERSION,
        }
    )


__all__ = [
    "RELOAD_CONTRACT_VERSION",
    "ReloadContractError",
    "MissingArtifactError",
    "MalformedJsonError",
    "MalformedCsvError",
    "ManifestMismatchError",
    "CanonicalPayloadHashMismatchError",
    "AuditPayloadHashMismatchError",
    "RowOrderMismatchError",
    "MetricDefinitionVersionMismatchError",
    "MaskHashMismatchError",
    "ForbiddenImplicitFallbackError",
    "ReloadResult",
    "all_reload_error_kinds",
    "get_reload_error_class",
    "verify_artifact_set",
    "canonical_payload_hash_of_outputs",
]
