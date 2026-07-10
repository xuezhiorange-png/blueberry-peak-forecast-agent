"""TASK-011 Phase 4c-2 — CLI entrypoint.

Thin wrapper over the 4c-1 service layer (``compute_metrics``) and the
4c-2 deterministic export writer (``write_export_artifacts``). The CLI
does NOT recompute metrics, does NOT bypass service-layer validation,
and does NOT introduce a new audit format.

Frozen design source
--------------------
``docs/task-11-phase4c-service-cli-export-amendment.md`` on main
(frozen at content SHA
``9f1f541367ee7c4ea3814f0068f682b29e590758690dcb2098cadd5de7796216``).

Binding sections
----------------
* §4.1 — Module / entry point
* §4.2 — Flag grammar
* §4.3 — Exit code model
* §4.4 — CLI audit contract (delegated to ``export.py``)
* §4.5 — CLI error / blocker model
* §9 — Consolidated error / blocker model

Entry point (frozen for §4.1)
-----------------------------
``python -m backend.app.rolling_backtest.cli compute-metrics …``

Forbidden scope (binding)
-------------------------
This module MUST NOT:

* recompute Phase 4b metrics;
* bypass the 4c-1 service-layer validation;
* read / write the database, network, or any other side channel;
* introduce a new audit format;
* implement 4c-3 production-shaped E2E / reload integrity;
* modify Phase 4a materialization semantics or Phase 4b metric
  formula semantics;
* implement ``replay_trained_model``;
* introduce ``current`` / ``latest`` / ``most recent`` implicit fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.rolling_backtest.export import (
    ExportRequest,
    OverwritePolicy,
    PathCollision,
    write_export_artifacts,
)
from backend.app.rolling_backtest.metrics import (
    METRIC_DEFINITION_VERSION,
    EvaluationResult,
)
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    ReplayTrainedServiceError,
    execute_replay_trained_prediction,
)
from backend.app.rolling_backtest.service import (
    ServiceContractError,
    compute_metrics,
)

# Exit codes (frozen, §4.3).
EXIT_SUCCESS: int = 0
EXIT_SERVICE_CONTRACT_ERROR: int = 2
EXIT_METRIC_BLOCKER: int = 3
EXIT_IO_ERROR: int = 4
EXIT_HASH_COLLISION: int = 5
EXIT_USAGE_ERROR: int = 64

# CLI module name (used in audit `cli_version`).
CLI_VERSION: str = "4c-2.0.0"


# ---------------------------------------------------------------------------
# Exit helpers
# ---------------------------------------------------------------------------


def _emit_error(
    *,
    kind: str,
    message: str,
    scope_id: str = "",
    evaluation_mask_hash: str = "",
    metric_definition_version: str = METRIC_DEFINITION_VERSION,
    run_id: str = "",
    extra: dict[str, object] | None = None,
) -> int:
    """Emit a single-line stderr message + JSON stdout payload (§4.5).

    Returns the desired process exit code (2) so the caller can
    propagate it without using ``sys.exit``.
    """
    payload: dict[str, object] = {
        "kind": kind,
        "message": message,
        "scope_id": scope_id,
        "metric_definition_version": metric_definition_version,
        "evaluation_mask_hash": evaluation_mask_hash,
    }
    if run_id:
        payload["run_id"] = run_id
    if extra:
        payload.update(extra)
    print(canonical_json_dumps(payload), file=sys.stdout)
    print(f"error: {kind}: {message}", file=sys.stderr)
    return EXIT_SERVICE_CONTRACT_ERROR


def _emit_blocker(
    *,
    blockers: list[dict[str, str]],
    canonical_payload_hash: str,
    scope_id: str,
    evaluation_mask_hash: str,
    run_id: str,
) -> int:
    """Emit blocker list on stdout (§4.5). Returns exit code 3."""
    payload: dict[str, object] = {
        "kind": "metric_blocker",
        "blockers": blockers,
        "canonical_payload_hash": canonical_payload_hash,
        "scope_id": scope_id,
        "evaluation_mask_hash": evaluation_mask_hash,
        "run_id": run_id,
        "metric_definition_version": METRIC_DEFINITION_VERSION,
    }
    print(canonical_json_dumps(payload), file=sys.stdout)
    return EXIT_METRIC_BLOCKER


def _emit_hash_collision(path: Path) -> int:
    """Emit conflicting path on stderr. Returns exit code 5."""
    print(f"error: hash_collision: {path}", file=sys.stderr)
    return EXIT_HASH_COLLISION


def _emit_io_error(message: str) -> int:
    """Emit IO error on stderr. Returns exit code 4."""
    print(f"error: io_error: {message}", file=sys.stderr)
    return EXIT_IO_ERROR


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with the frozen §4.2 flag grammar."""
    parser = argparse.ArgumentParser(
        prog="python -m backend.app.rolling_backtest.cli compute-metrics",
        description=(
            "TASK-011 Phase 4c-2 CLI: compute Phase 4b metrics over a "
            "Phase 4a materialization and write deterministic JSON / CSV "
            "/ manifest / audit files."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p = sub.add_parser("compute-metrics", help=argparse.SUPPRESS)

    p.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Phase 4a logical run id (binding for §4.2).",
    )
    p.add_argument(
        "--scope",
        type=str,
        required=True,
        help=(
            "JSON object; MUST include 'node' (binding for §4.2 / §3.4). "
            "Pass the JSON as a single CLI argument, e.g. "
            '--scope \'{"node":1,"horizon":"daily"}\'.'
        ),
    )
    p.add_argument(
        "--mask-hash",
        type=str,
        required=True,
        help="64-char lowercase hex Phase 4a evaluation mask hash (§4.2).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Absolute path; the writer creates json/ csv/ manifest/ audit/ sub-dirs.",
    )
    p.add_argument(
        "--metric-subset",
        type=str,
        default=None,
        help="Comma-separated allowlist of metric names (binding for §4.2).",
    )
    p.add_argument(
        "--decimal-scale",
        type=int,
        default=None,
        help="Decimal scale (≥ 0; default 6). Binding for §4.2.",
    )
    p.add_argument(
        "--overwrite",
        type=str,
        choices=("never", "missing", "always"),
        default="missing",
        help="Overwrite / collision policy (§6.2). Default: missing.",
    )
    p.add_argument(
        "--no-audit",
        action="store_true",
        help="Skip audit-record emission (§4.4).",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stderr progress logs (§4.2).",
    )

    replay = sub.add_parser(
        "replay-trained-predict",
        help="Execute one explicitly identified TASK-012 replay-trained prediction.",
    )
    replay.add_argument(
        "--request-json",
        type=str,
        required=True,
        help="Absolute UTF-8 JSON request path containing the complete replay identity.",
    )
    replay.add_argument(
        "--output-json",
        type=str,
        required=True,
        help="Absolute output path for the canonical UTF-8 JSON result.",
    )
    replay.add_argument(
        "--overwrite",
        type=str,
        choices=("never", "missing", "always"),
        default="missing",
        help="Existing output policy: never, missing, or always.",
    )
    replay.add_argument(
        "--quiet",
        action="store_true",
        help="Do not echo the successful canonical result to stdout.",
    )
    return parser


def _parse_metric_subset(raw: str | None) -> tuple[str, ...] | None:
    """Parse a comma-separated metric-subset string into a tuple."""
    if raw is None:
        return None
    items = tuple(s.strip() for s in raw.split(",") if s.strip())
    return items or None


class CLIUsageError(ValueError):
    """Raised by CLI argument-parsing helpers when input is malformed.

    The CLI ``main()`` translates this to ``EXIT_USAGE_ERROR`` (64).
    Distinct from ``ServiceContractError`` (4c-1) which exits 2.
    """


def _parse_scope_json(raw: str) -> dict[str, object]:
    """Parse ``--scope`` JSON. Raises :class:`CLIUsageError` on malformed JSON."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CLIUsageError(f"invalid_scope_json: {exc.msg} at pos {exc.pos}") from exc
    if not isinstance(parsed, dict):
        raise CLIUsageError(
            f"invalid_scope_json: scope must be a JSON object (got {type(parsed).__name__})"
        )
    return parsed


def _validate_output_dir_absolute(raw: str) -> Path:
    """Validate ``--output-dir`` BEFORE calling ``Path.resolve()``.

    ``Path.resolve()`` collapses relative paths to absolute paths on
    the host, which would silently transform a caller mistake
    (``./rel`` → ``/cwd/rel``) into a successful run writing to an
    unintended directory. Per §4.2 the contract is that
    ``--output-dir`` MUST be absolute; we therefore reject relative
    paths with a CLI usage error (exit 64) so the failure mode is
    loud and never silently coerces a relative input.
    """
    if not raw:
        raise CLIUsageError("invalid_output_dir: --output-dir is empty")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise CLIUsageError(f"invalid_output_dir: --output-dir must be absolute (got {raw!r})")
    return candidate


def _validate_absolute_file(raw: str, *, flag: str) -> Path:
    if not raw:
        raise CLIUsageError(f"invalid_{flag}: {flag} is empty")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise CLIUsageError(f"invalid_{flag}: {flag} must be absolute (got {raw!r})")
    return candidate


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CLIUsageError(f"duplicate_json_key: {key}")
        result[key] = value
    return result


def _load_replay_request(path: Path) -> ReplayTrainedExecutionRequest:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CLIUsageError(f"request_read_failed: {path}") from exc
    try:
        decoded = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, CLIUsageError) as exc:
        if isinstance(exc, CLIUsageError):
            raise
        raise CLIUsageError(f"request_json_invalid: {exc.msg} at pos {exc.pos}") from exc
    if not isinstance(decoded, dict):
        raise CLIUsageError("request_json_invalid: root must be an object")
    return ReplayTrainedExecutionRequest.from_payload(decoded)


def _write_replay_result(path: Path, payload: bytes, *, overwrite: str) -> bool:
    """Atomically write a result and return whether an identical file existed."""
    if path.exists():
        existing = path.read_bytes()
        if overwrite == "never":
            raise FileExistsError("output_exists")
        if overwrite == "missing":
            if existing == payload:
                return True
            raise FileExistsError("output_payload_conflict")
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise OSError("output_parent_missing")
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
    return False


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _handle_compute_metrics(
    args: argparse.Namespace,
    *,
    effective_argv: Sequence[str],
) -> int:
    """Handle the ``compute-metrics`` subcommand.

    Returns the desired process exit code; main() propagates it via
    ``sys.exit``.

    ``effective_argv`` is the post-subcommand argv slice that was
    actually parsed (i.e. ``argv[1:]`` when ``argv[0]`` is
    ``"compute-metrics"``). We pass it explicitly so the audit
    record captures the caller's effective invocation rather than
    ``sys.argv[1:]`` — using ``sys.argv`` would corrupt the audit
    whenever the CLI is invoked via ``main(argv=[...])`` from a
    test harness or library entry point where ``sys.argv`` is the
    pytest runner, not the CLI.
    """
    scope = _parse_scope_json(args.scope)
    metric_subset = _parse_metric_subset(args.metric_subset)
    output_dir: Path = _validate_output_dir_absolute(args.output_dir)
    overwrite_policy = OverwritePolicy(args.overwrite)
    emit_audit = not args.no_audit

    # 1) Call 4c-1 service layer.
    try:
        result: EvaluationResult = compute_metrics(
            run_id=args.run_id,
            scope=scope,
            mask_hash=args.mask_hash,
            metric_subset=metric_subset,
            decimal_scale=(
                args.decimal_scale
                if args.decimal_scale is not None
                else 6  # Phase 4b default (binding for §3.2)
            ),
        )
    except ServiceContractError as exc:
        payload = exc.to_payload()
        kind = str(payload.get("kind", "service_contract_error"))
        message = str(payload.get("message", ""))
        return _emit_error(
            kind=kind,
            message=message,
            run_id=str(payload.get("run_id") or args.run_id),
            scope_id=str(payload.get("scope_id") or ""),
            evaluation_mask_hash=str(payload.get("evaluation_mask_hash") or args.mask_hash),
            metric_definition_version=str(
                payload.get("metric_definition_version", METRIC_DEFINITION_VERSION)
            ),
        )

    # 2) Derive scope_id from result.outputs[0].metric_scope_identity (§6.1).
    scope_id = result.outputs[0].metric_scope_identity if result.outputs else ""
    evaluation_mask_hash = result.outputs[0].evaluation_mask_hash if result.outputs else ""

    # 3) Check MetricBlocker presence (§4.5 / §9).
    blockers: list[dict[str, str]] = []
    for out in result.outputs:
        for b in out.blocked_reasons:
            blockers.append(b.to_payload())

    # 4) Build ExportRequest and write the four target files.
    cli_invocation: dict[str, str] = {
        "argv": " ".join(effective_argv),
        "--scope": args.scope,
        "--mask-hash": args.mask_hash,
        "--metric-subset": args.metric_subset or "",
    }
    request = ExportRequest(
        result=result,
        run_id=args.run_id,
        decimal_scale=(args.decimal_scale if args.decimal_scale is not None else 6),
        output_dir=output_dir,
        overwrite_policy=overwrite_policy,
        cli_invocation=cli_invocation if emit_audit else None,
        emit_audit=emit_audit,
    )

    try:
        artifacts = write_export_artifacts(request)
    except PathCollision as exc:
        return _emit_hash_collision(exc.path)
    except OSError as exc:
        return _emit_io_error(str(exc))

    # 5) Emit success output. If MetricBlocker is present, exit 3
    #    (§4.5); otherwise exit 0 with the canonical payload hash on
    #    stdout (unless --quiet).
    if blockers:
        return _emit_blocker(
            blockers=blockers,
            canonical_payload_hash=result.canonical_payload_hash,
            scope_id=scope_id,
            evaluation_mask_hash=evaluation_mask_hash,
            run_id=args.run_id,
        )

    if not args.quiet:
        print(
            canonical_json_dumps(
                {
                    "canonical_payload_hash": result.canonical_payload_hash,
                    "json_path": str(artifacts.json_path),
                    "csv_path": str(artifacts.csv_path),
                    "manifest_path": str(artifacts.manifest_path),
                    "audit_path": (
                        str(artifacts.audit_path) if artifacts.audit_path is not None else None
                    ),
                    "run_id": args.run_id,
                    "scope_id": scope_id,
                    "evaluation_mask_hash": evaluation_mask_hash,
                    "metric_definition_version": METRIC_DEFINITION_VERSION,
                }
            ),
            file=sys.stdout,
        )
    return EXIT_SUCCESS


def _emit_replay_error(exc: ReplayTrainedServiceError) -> int:
    payload = {
        "error": {
            "code": exc.code,
            "message": str(exc),
            "blocker": exc.blocker_code,
            "identity": exc.to_payload(),
        }
    }
    print(canonical_json_dumps(payload), file=sys.stdout)
    print(f"error: {exc.code}", file=sys.stderr)
    if exc.blocker_code:
        return EXIT_METRIC_BLOCKER
    return EXIT_SERVICE_CONTRACT_ERROR


def _handle_replay_trained_predict(args: argparse.Namespace) -> int:
    request_path = _validate_absolute_file(args.request_json, flag="request_json")
    output_path = _validate_absolute_file(args.output_json, flag="output_json")
    try:
        request = _load_replay_request(request_path)
        result = asyncio.run(execute_replay_trained_prediction(session=None, request=request))
    except ReplayTrainedServiceError as exc:
        return _emit_replay_error(exc)
    payload = canonical_json_dumps(result.to_payload()).encode("utf-8")
    try:
        _write_replay_result(output_path, payload, overwrite=args.overwrite)
    except FileExistsError as exc:
        print(
            canonical_json_dumps(
                {
                    "error": {
                        "code": "TASK012_REPLAY_TRAINED_CONFLICT",
                        "message": str(exc),
                        "blocker": None,
                        "identity": {},
                    }
                }
            ),
            file=sys.stdout,
        )
        print("error: TASK012_REPLAY_TRAINED_CONFLICT", file=sys.stderr)
        return EXIT_HASH_COLLISION
    except OSError as exc:
        print(
            canonical_json_dumps(
                {
                    "error": {
                        "code": "TASK012_REPLAY_TRAINED_IO_ERROR",
                        "message": str(exc),
                        "blocker": None,
                        "identity": {},
                    }
                }
            ),
            file=sys.stdout,
        )
        print("error: TASK012_REPLAY_TRAINED_IO_ERROR", file=sys.stderr)
        return EXIT_IO_ERROR
    if not args.quiet:
        print(payload.decode("utf-8"), file=sys.stdout)
    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point (§4.1).

    ``argv`` is the effective caller-provided argv slice. When
    ``None`` we fall back to ``sys.argv[1:]`` (the standard
    module-as-script invocation). We deliberately do NOT use
    ``sys.argv[1:]`` as the audit's argv capture: when this function
    is invoked from a library / test harness with an explicit
    ``argv=``, the audit must reflect the caller, not the test
    runner.
    """
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # Argparse raises SystemExit(2) on usage errors. The frozen
        # §4.3 exit-code model mandates exit 64 for CLI usage
        # errors. Translate here.
        return EXIT_USAGE_ERROR if exc.code not in (None, 0) else 0
    if args.subcommand == "compute-metrics":
        try:
            return _handle_compute_metrics(args, effective_argv=argv)
        except CLIUsageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE_ERROR
    if args.subcommand == "replay-trained-predict":
        try:
            return _handle_replay_trained_predict(args)
        except CLIUsageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE_ERROR
    parser.print_help(sys.stderr)
    return EXIT_USAGE_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
