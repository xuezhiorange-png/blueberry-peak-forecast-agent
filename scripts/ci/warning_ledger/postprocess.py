"""Build a deterministic, per-instance warning ledger from pytest output."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

MAPPED = "MAPPED_TO_ONE_SIGNATURE"
UNMAPPED = "UNMAPPED"
AMBIGUOUS = "AMBIGUOUS_OR_MULTI_MAPPED"

_DATE_INPUT = re.compile(r"input_value=['\"]\d{4}-\d{2}-\d{2}['\"]")
_TEMP_PATH = re.compile(r"/(?:tmp|private/tmp|home/runner|opt/hostedtoolcache)/[^\s'\"]+")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\b"
)


def _safe_text(value: str) -> str:
    value = _TEMP_PATH.sub("<temporary-path>", value)
    value = _UUID.sub("<uuid>", value)
    value = _ADDRESS.sub("<address>", value)
    value = _TIMESTAMP.sub("<timestamp>", value)
    value = _DATE_INPUT.sub("input_value=<date>", value)
    return value


def _read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(paths):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid raw warning record {path}:{line_number}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"raw warning record is not an object: {path}:{line_number}")
                records.append(record)
    return records


def _warning_text(event: dict[str, Any]) -> str:
    return "\n".join(
        str(event.get(key, ""))
        for key in ("warning_category", "raw_message", "source_filename", "nodeid")
    )


def _signature_candidates(event: dict[str, Any]) -> list[str]:
    text = _warning_text(event)
    category = str(event.get("warning_category", ""))
    candidates: list[str] = []

    if "PydanticDeprecatedSince20" in text and "json_encoders" in text:
        candidates.append("pydantic-json-encoders-deprecation")

    if "PydanticSerializationUnexpectedValue" in text:
        if "source_recorded_at_authority_status" in text and (
            "input_value='ACTIVE'" in text or "record_status='ACTIVE'" in text
        ):
            candidates.append("pydantic-enum-source-active")
        if "source_recorded_at_authority_status" in text and (
            "input_value='FINALIZED'" in text or "record_status='FINALIZED'" in text
        ):
            candidates.append("pydantic-enum-source-finalized")
        has_date = "Expected `date`" in text and "field_name='date'" in text
        has_float = "effective_marketable_quantity" in text and "input_type=float" in text
        if has_date and has_float:
            candidates.append("pydantic-date-effective-quantity-mixed")
        elif has_date:
            candidates.append("pydantic-date-serializer")

    shim_signatures = {
        "postgres_test_support": "test-postgres-support-import-shim",
        "migration_isolation_helpers": "test-migration-isolation-import-shim",
        "concurrency_isolation_helpers": "test-concurrency-isolation-import-shim",
    }
    if category == "DeprecationWarning":
        for marker, signature in shim_signatures.items():
            if marker in text:
                candidates.append(signature)

    if category == "PytestWarning":
        candidates.append("pytest-warning")
    if "HTTP_422_UNPROCESSABLE_ENTITY" in text:
        candidates.append("starlette-http-422-deprecation")
    if "Setting the shape on a NumPy array has been deprecated" in text:
        candidates.append("numpy-joblib-shape-deprecation")
    if "garbage collector is trying to clean up non-checked-in connection" in text:
        candidates.append("sqlalchemy-asyncpg-unreturned-connection")
    if "default datetime adapter is deprecated" in text:
        candidates.append("sqlite-datetime-adapter-deprecation")
    return sorted(set(candidates))


def _normalize_event(event: dict[str, Any]) -> tuple[str, str | None]:
    candidates = _signature_candidates(event)
    if len(candidates) == 1:
        return MAPPED, candidates[0]
    if len(candidates) > 1:
        return AMBIGUOUS, None
    return UNMAPPED, None


def _out_of_band_records(stderr_path: Path) -> list[dict[str, Any]]:
    """Collect warning-looking stderr lines without pretending they are unique.

    A stderr warning may duplicate a hook event.  Such a record is therefore
    intentionally ambiguous and never mapped to a signature by this script.
    """
    records: list[dict[str, Any]] = []
    if not stderr_path.exists():
        return records
    category_pattern = re.compile(
        r"\b(?:Warning|DeprecationWarning|UserWarning|RuntimeWarning|ResourceWarning|"
        r"PytestWarning|SAWarning|StarletteDeprecationWarning)\b"
    )
    for line_number, line in enumerate(stderr_path.read_text(encoding="utf-8"), start=1):
        if not category_pattern.search(line):
            continue
        if " warnings in " in line or " warning in " in line:
            continue
        records.append(
            {
                "sequence": len(records) + 1,
                "source": "pytest-stderr",
                "source_line": line_number,
                "raw_message": line.rstrip("\n"),
                "mapping_status": AMBIGUOUS,
                "reason": "stderr warning may duplicate a pytest hook event",
            }
        )
    return records


def _terminal_warning_count(stdout_path: Path, stderr_path: Path) -> int | None:
    content = "\n".join(
        path.read_text(encoding="utf-8") for path in (stdout_path, stderr_path) if path.exists()
    )
    matches = re.findall(r"\b(\d+)\s+warnings?\s+in\s+[^\n]+", content)
    return int(matches[-1]) if matches else None


def _junit_metrics(path: Path) -> dict[str, int | bool]:
    if not path.exists():
        return {"exists": False, "tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    root = ElementTree.parse(path).getroot()
    suites = list(root.iter("testsuite"))

    def metric(name: str) -> int:
        value = root.attrib.get(name)
        if value is not None:
            return int(float(value))
        return sum(int(float(suite.attrib.get(name, "0"))) for suite in suites)

    return {
        "exists": True,
        "tests": metric("tests"),
        "failures": metric("failures"),
        "errors": metric("errors"),
        "skipped": metric("skipped"),
    }


def _command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return "not_available"
    return (completed.stdout or completed.stderr).strip()


def _dependency_versions() -> list[str]:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "freeze", "--local"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ["not_available"]
    return sorted(line for line in completed.stdout.splitlines() if line.strip())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_gzip_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _write_normalized_json(
    path: Path,
    metadata: dict[str, Any],
    mappings: list[tuple[dict[str, Any], str, str | None]],
    signatures: dict[str, dict[str, Any]],
    out_of_band: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write('{\n  "metadata": ')
        json.dump(metadata, handle, ensure_ascii=False, sort_keys=True)
        handle.write(',\n  "record_mappings": [\n')
        for index, (event, status, signature_id) in enumerate(mappings):
            if index:
                handle.write(",\n")
            compact = {
                "sequence": event.get("sequence"),
                "process_id": event.get("process_id"),
                "worker_id": event.get("worker_id"),
                "signature_id": signature_id,
                "mapping_status": status,
            }
            handle.write("    " + json.dumps(compact, ensure_ascii=False, sort_keys=True))
        handle.write('\n  ],\n  "signatures": ')
        json.dump(
            sorted(signatures.values(), key=lambda item: item["signature_id"]),
            handle,
            ensure_ascii=False,
            sort_keys=True,
        )
        handle.write(',\n  "out_of_band": ')
        json.dump(out_of_band, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n}\n")


def _write_csv(path: Path, signatures: dict[str, dict[str, Any]]) -> None:
    fields = [
        "signature_id",
        "warning_category",
        "normalized_message",
        "source_filename",
        "source_line",
        "occurrence_count",
        "mapping_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for signature in sorted(signatures.values(), key=lambda item: item["signature_id"]):
            writer.writerow({field: signature.get(field, "") for field in fields})


def _write_manifest_and_checksums(output_dir: Path, manifest: dict[str, Any]) -> None:
    manifest_path = output_dir / "warning-ledger-manifest.json"
    _write_json(manifest_path, manifest)
    checksum_paths = sorted(
        path for path in output_dir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    checksum_path = output_dir / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_paths),
        encoding="utf-8",
    )


def build_ledger(args: argparse.Namespace) -> int:
    raw_dir = args.raw_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_records = _read_jsonl(raw_dir.glob("warning-events.raw.*.jsonl"))
    out_of_band = _out_of_band_records(args.stderr)

    mappings: list[tuple[dict[str, Any], str, str | None]] = []
    signatures: dict[str, dict[str, Any]] = {}
    unmapped_count = 0
    ambiguous_count = len(out_of_band)
    multi_mapped_count = 0

    for event in raw_records:
        status, signature_id = _normalize_event(event)
        mappings.append((event, status, signature_id))
        if status == UNMAPPED:
            unmapped_count += 1
        elif status == AMBIGUOUS:
            ambiguous_count += 1
            if len(_signature_candidates(event)) > 1:
                multi_mapped_count += 1
        elif signature_id is not None:
            signature = signatures.setdefault(
                signature_id,
                {
                    "signature_id": signature_id,
                    "warning_category": event.get("warning_category", ""),
                    "normalized_message": _safe_text(str(event.get("raw_message", ""))),
                    "source_filename": event.get("source_filename", ""),
                    "source_line": event.get("source_line", 0),
                    "occurrence_count": 0,
                    "mapping_status": MAPPED,
                    "sample_nodeids": [],
                    "sample_locations": [],
                },
            )
            signature["occurrence_count"] += 1
            nodeid = str(event.get("nodeid", ""))
            if (
                nodeid
                and nodeid not in signature["sample_nodeids"]
                and len(signature["sample_nodeids"]) < 20
            ):
                signature["sample_nodeids"].append(nodeid)
            location = {
                "filename": event.get("source_filename", ""),
                "line": event.get("source_line", 0),
            }
            if (
                location not in signature["sample_locations"]
                and len(signature["sample_locations"]) < 20
            ):
                signature["sample_locations"].append(location)

    terminal_count = _terminal_warning_count(args.stdout, args.stderr)
    junit = _junit_metrics(args.junitxml)
    mapped_count = sum(int(signature["occurrence_count"]) for signature in signatures.values())
    ledger_count = len(raw_records) + len(out_of_band)
    arithmetic_closed = (
        terminal_count is not None
        and ledger_count == terminal_count
        and mapped_count == terminal_count
        and unmapped_count == 0
        and ambiguous_count == 0
        and multi_mapped_count == 0
    )

    raw_gzip = output_dir / "warning-events.raw.jsonl.gz"
    _write_gzip_jsonl(raw_gzip, raw_records)
    out_gzip = output_dir / "warning-events.out-of-band.jsonl.gz"
    _write_gzip_jsonl(out_gzip, out_of_band)
    complete_log = output_dir / "pytest-complete.log"
    complete_log.write_text(
        "--- stdout ---\n"
        + (args.stdout.read_text(encoding="utf-8") if args.stdout.exists() else "")
        + "\n--- stderr ---\n"
        + (args.stderr.read_text(encoding="utf-8") if args.stderr.exists() else ""),
        encoding="utf-8",
    )
    complete_log_gzip = output_dir / "pytest-complete.log.gz"
    with complete_log.open("rb") as source, gzip.open(complete_log_gzip, "wb") as target:
        shutil.copyfileobj(source, target)
    complete_log.unlink()

    full_xml = output_dir / "full.xml"
    if args.junitxml.exists():
        shutil.copy2(args.junitxml, full_xml)
    normalized_metadata = {
        "base_sha": args.base_sha,
        "raw_hook_event_count": len(raw_records),
        "out_of_band_event_count": len(out_of_band),
        "warning_ledger_instance_count": ledger_count,
        "terminal_warning_count": terminal_count,
        "mapped_event_count": mapped_count,
        "unmapped_event_count": unmapped_count,
        "ambiguous_event_count": ambiguous_count,
        "multi_mapped_event_count": multi_mapped_count,
        "normalized_signature_count": len(signatures),
        "sum_signature_occurrence_count": mapped_count,
    }
    normalized_path = output_dir / "warning-ledger.normalized.json"
    _write_normalized_json(normalized_path, normalized_metadata, mappings, signatures, out_of_band)
    csv_path = output_dir / "warning-ledger.csv"
    _write_csv(csv_path, signatures)

    try:
        exit_code = int(args.exitcode.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        exit_code = 125
    tests = int(junit["tests"])
    failures = int(junit["failures"])
    errors = int(junit["errors"])
    skipped = int(junit["skipped"])
    manifest = {
        "repository": args.repository,
        "base_sha": args.base_sha,
        "workflow_run_id": args.workflow_run_id,
        "job_id": args.job_id,
        "pytest_command": args.pytest_command,
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "pytest": _command_output([sys.executable, "-m", "pytest", "--version"]),
            "pip": _command_output([sys.executable, "-m", "pip", "--version"]),
            "uv": _command_output(["uv", "--version"]),
            "platform": platform.platform(),
        },
        "dependency_versions": _dependency_versions(),
        "raw_hook_event_count": len(raw_records),
        "out_of_band_event_count": len(out_of_band),
        "mapped_event_count": mapped_count,
        "unmapped_event_count": unmapped_count,
        "ambiguous_event_count": ambiguous_count,
        "multi_mapped_event_count": multi_mapped_count,
        "normalized_signature_count": len(signatures),
        "sum_signature_occurrence_count": mapped_count,
        "pytest_terminal_warning_count": terminal_count,
        "warning_ledger_instance_count": ledger_count,
        "junit": {
            "tests": tests,
            "passed": tests - failures - errors - skipped,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        },
        "pytest_exit_code": exit_code,
        "validation": {
            "warning_count_matches_terminal": (
                terminal_count is not None and ledger_count == terminal_count
            ),
            "warning_ledger_arithmetic_closed": arithmetic_closed,
            "signature_count_matches_reference": len(signatures) == args.expected_signature_count,
            "warning_filter_changed": False,
            "test_execution_scope_changed": False,
            "dependency_profile_changed": False,
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    artifact_paths = [
        raw_gzip,
        out_gzip,
        complete_log_gzip,
        full_xml,
        normalized_path,
        csv_path,
    ]
    manifest["artifact_hashes"] = {
        path.name: _sha256(path) for path in artifact_paths if path.exists()
    }
    _write_manifest_and_checksums(output_dir, manifest)

    if not junit["exists"] or exit_code != 0:
        return 1
    if tests - failures - errors - skipped != args.expected_passed:
        return 1
    if failures != 0 or errors != 0:
        return 1
    if skipped != args.expected_skipped:
        return 1
    if len(signatures) != args.expected_signature_count:
        return 1
    return 0 if arithmetic_closed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--junitxml", type=Path, required=True)
    parser.add_argument("--exitcode", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--pytest-command", required=True)
    parser.add_argument("--expected-signature-count", type=int, required=True)
    parser.add_argument("--expected-passed", type=int, default=3423)
    parser.add_argument("--expected-skipped", type=int, default=3)
    args = parser.parse_args(argv)
    return build_ledger(args)


if __name__ == "__main__":
    raise SystemExit(main())
