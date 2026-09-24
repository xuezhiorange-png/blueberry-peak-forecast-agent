"""Discover and deterministically rebuild the historical area source inventory.

This tool records source discovery separately from area semantics and authority.
Detailed paths and rows are written only to a controlled private output folder.
The frozen legacy parser is replayed in an isolated temporary directory; its
existing private outputs are never overwritten.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

TASK_ID = "V0_8_S3_AREA_SOURCE_INVENTORY_COMPLETENESS_PROVENANCE_R1"
OLD_SOURCE_INVENTORY_SHA256 = "81341ce629a479db82ad4f02539afd9759c8eacfe29a311683dd38ef63c681cf"
OLD_SOURCE_MANIFEST_SHA256 = "c66dffe275741b7c985920fed4cf32c8af43420650873b59f6a2bdb2fbfea2f1"
LEGACY_BUILDER_SHA256 = "d9a4a1d214e68ffaa00e46f74842001480b0b2aee29d3f9e56ab2240a60376f9"

FILE_FIELDS = (
    "search_root",
    "search_root_type",
    "file_path",
    "file_sha256",
    "file_size",
    "source_category",
    "candidate_reason",
    "included_in_inventory",
    "exclusion_reason",
    "logical_source_identity",
    "scan_status",
)
DIFF_FIELDS = ("diff_status", "file_path", "file_sha256", "record_count", "detail")


class InventoryError(ValueError):
    """Stable fail-closed inventory error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _normalized_path(path: Path) -> str:
    return path.expanduser().resolve(strict=False).as_posix()


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def resolve_search_roots(
    config: dict[str, Any], repo_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand explicit paths/globs and merge aliases of the same root path."""
    merged: dict[str, dict[str, Any]] = {}
    declared: list[dict[str, Any]] = []
    for spec in config["search_roots"]:
        if "repo_relative_path" in spec:
            candidates = [repo_root / spec["repo_relative_path"]]
        elif "glob" in spec:
            candidates = (
                [Path(value) for value in sorted(Path().glob(spec["glob"]))]
                if not Path(spec["glob"]).is_absolute()
                else [Path(value) for value in sorted(Path("/").glob(spec["glob"].lstrip("/")))]
            )
            subdirs = spec.get("subdirectories")
            if subdirs:
                candidates = [candidate / subdir for candidate in candidates for subdir in subdirs]
        else:
            candidates = [Path(spec["path"])]
        present = 0
        for candidate in candidates:
            normalized = _normalized_path(candidate)
            exists = candidate.is_dir()
            present += int(exists)
            if normalized not in merged:
                merged[normalized] = {
                    "path": normalized,
                    "root_type": spec["root_type"],
                    "root_ids": [],
                    "exists": exists,
                }
            merged[normalized]["root_ids"].append(spec["root_id"])
            merged[normalized]["exists"] = merged[normalized]["exists"] or exists
        declared.append(
            {
                "root_id": spec["root_id"],
                "root_type": spec["root_type"],
                "declared_match_count": len(candidates),
                "existing_match_count": present,
            }
        )
    roots = sorted(merged.values(), key=lambda item: item["path"])
    for root in roots:
        root["root_ids"] = sorted(set(root["root_ids"]))
    return roots, declared


def _decode_search_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _zip_text(path: Path) -> tuple[str, str]:
    chunks: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if (
                    name == "xl/sharedStrings.xml"
                    or re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
                    or name in {"word/document.xml", "content.xml"}
                    or re.fullmatch(r"word/(header|footer)\d+\.xml", name)
                    or name.endswith((".csv", ".txt"))
                ):
                    chunks.append(_decode_search_bytes(archive.read(name)))
        return "\n".join(chunks), "CONTENT_SCANNED"
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return "", "READ_ERROR"


def _xls_text(path: Path) -> tuple[str, str]:
    try:
        import xlrd

        workbook = xlrd.open_workbook(str(path), on_demand=True)
        values: list[str] = []
        for sheet in workbook.sheets():
            for row_index in range(sheet.nrows):
                values.extend(str(value) for value in sheet.row_values(row_index) if value != "")
        workbook.release_resources()
        return "\n".join(values), "CONTENT_SCANNED"
    except Exception as exc:
        return "", f"CONTENT_SCAN_UNAVAILABLE:{type(exc).__name__}"


def _pdf_text(path: Path) -> tuple[str, str]:
    """Extract PDF literal text and bounded non-image Flate streams."""
    try:
        payload = path.read_bytes()
    except OSError:
        return "", "READ_ERROR"
    chunks = [_decode_search_bytes(payload)]
    stream_pattern = rb"stream\r?\n(.*?)\r?\nendstream"
    output_limit_exceeded = False
    for match in re.finditer(stream_pattern, payload, re.DOTALL):
        stream = match.group(1)
        dictionary = payload[max(0, match.start() - 4096) : match.start()]
        object_header = dictionary.rfind(b"obj")
        if object_header >= 0:
            dictionary = dictionary[object_header:]
        if b"/Subtype /Image" in dictionary or b"/Subtype/Image" in dictionary:
            continue
        if b"/DCTDecode" in dictionary or b"/JPXDecode" in dictionary:
            continue
        try:
            inflater = zlib.decompressobj()
            decoded = inflater.decompress(stream, 2 * 1024 * 1024)
            chunks.append(_decode_search_bytes(decoded))
            output_limit_exceeded = output_limit_exceeded or bool(inflater.unconsumed_tail)
        except zlib.error:
            continue
    status = (
        "CONTENT_SCAN_LIMIT_EXCEEDED"
        if output_limit_exceeded
        else "CONTENT_SCANNED_FLATE_TEXT_BEST_EFFORT"
    )
    return "\n".join(chunks), status


def searchable_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".ods", ".docx"}:
        return _zip_text(path)
    if suffix == ".xls":
        return _xls_text(path)
    if suffix == ".pdf":
        return _pdf_text(path)
    if suffix in {".doc", ".parquet", ".joblib", ".pkl", ".npz", ".npy"}:
        try:
            return _decode_search_bytes(path.read_bytes()), "BINARY_STRINGS_BEST_EFFORT"
        except OSError:
            return "", "READ_ERROR"
    try:
        return _decode_search_bytes(path.read_bytes()), "CONTENT_SCANNED"
    except OSError:
        return "", "READ_ERROR"


def _matches_keywords(value: str, keywords: Iterable[str]) -> list[str]:
    folded = value.casefold()
    return [keyword for keyword in keywords if keyword.casefold() in folded]


def enumerate_files(
    roots: list[dict[str, Any]], ignored_directory_names: set[str], excluded_output: Path
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Recursively enumerate files in sorted order; symlinks are recorded as skips."""
    paths: dict[str, set[str]] = defaultdict(set)
    enumerated_paths: set[str] = set()
    scan_errors: list[str] = []
    output_root = excluded_output.resolve(strict=False)
    for root in roots:
        root_path = Path(root["path"])
        if not root_path.is_dir():
            if root["root_type"] in {"USER_SOURCE_ROOT", "CONTROLLED_PRIVATE_ARTIFACT_ROOT"}:
                scan_errors.append(f"SEARCH_ROOT_MISSING:{root['path']}")
            continue
        for current, dirnames, filenames in os.walk(root_path, topdown=True, followlinks=False):
            current_path = Path(current)
            kept_dirs = []
            for dirname in sorted(dirnames):
                directory = current_path / dirname
                if dirname in ignored_directory_names or directory.is_symlink():
                    continue
                if _path_is_within(directory, output_root):
                    continue
                kept_dirs.append(dirname)
            dirnames[:] = kept_dirs
            for filename in sorted(filenames):
                path = current_path / filename
                if path.is_symlink() or not path.is_file():
                    continue
                normalized = _normalized_path(path)
                if _path_is_within(path, output_root):
                    continue
                enumerated_paths.add(normalized)
                paths[normalized].update(root["root_ids"])
    rows = [
        {
            "file_path": path,
            "search_roots": sorted(root_ids),
            "file_size": Path(path).stat().st_size,
        }
        for path, root_ids in sorted(paths.items())
    ]
    return rows, len(enumerated_paths), scan_errors


def discover_area_candidates(
    file_rows: list[dict[str, Any]], extensions: set[str], keywords: list[str]
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for file_row in file_rows:
        path = Path(file_row["file_path"])
        suffix = path.suffix.lower()
        if suffix not in extensions:
            continue
        name_hits = _matches_keywords(path.name, keywords)
        content, scan_status = searchable_text(path)
        content_hits = _matches_keywords(content, keywords)
        scan_failed = (
            scan_status == "READ_ERROR"
            or "UNAVAILABLE" in scan_status
            or "LIMIT_EXCEEDED" in scan_status
        )
        if not name_hits and not content_hits and not scan_failed:
            continue
        hits = sorted(set(name_hits + content_hits), key=str.casefold)
        file_digest = sha256_file(path)
        candidates.append(
            {
                **file_row,
                "file_sha256": file_digest,
                "source_category": "UNCLASSIFIED_CANDIDATE",
                "candidate_reason": (
                    "CONTENT_SCAN_FAILED" if scan_failed else "KEYWORD_MATCH:" + ",".join(hits)
                ),
                "included_in_inventory": False,
                "exclusion_reason": "",
                "logical_source_identity": "CONTENT_SHA256:" + file_digest,
                "scan_status": scan_status,
            }
        )
    return candidates


def _category_for_known_exclusion(kind: str) -> tuple[str, str]:
    if kind in {"HARVEST_ONLY_NO_AREA_COLUMNS", "SCANNED_NO_NUMERIC_AGRICULTURAL_AREA"}:
        return "EXCLUDED_NO_AREA_FIELD", "LEGACY_MANIFEST:" + kind
    if kind == "NON_TEXT_PLANNING_PDF":
        return "EXCLUDED_UNSUPPORTED_FORMAT", "LEGACY_MANIFEST:" + kind
    if kind in {"ENGINEERING_AREA_M2", "ENGINEERING_MAINTENANCE_SCOPE_TEXT"}:
        return "EXCLUDED_REFERENCE_ONLY", "LEGACY_MANIFEST:" + kind
    return "EXCLUDED_REPORT_ONLY", "LEGACY_MANIFEST:" + kind


def classify_candidates(
    candidates: list[dict[str, Any]],
    rebuilt_source_paths: set[str],
    old_source_paths: set[str],
    legacy_exclusions: dict[str, str],
) -> list[dict[str, Any]]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_hash[row["file_sha256"]].append(row)
    canonical_path_by_hash: dict[str, str] = {}
    for digest, rows in by_hash.items():
        preferred = sorted(
            rows,
            key=lambda row: (
                row["file_path"] not in rebuilt_source_paths,
                row["file_path"] not in old_source_paths,
                row["file_path"].casefold(),
            ),
        )[0]
        canonical_path_by_hash[digest] = preferred["file_path"]

    output: list[dict[str, Any]] = []
    for row in candidates:
        path = Path(row["file_path"])
        normalized = row["file_path"]
        if (
            row["scan_status"] == "READ_ERROR"
            or "UNAVAILABLE" in row["scan_status"]
            or "LIMIT_EXCEEDED" in row["scan_status"]
        ):
            row["source_category"] = "UNCLASSIFIED_CANDIDATE"
            row["exclusion_reason"] = "CONTENT_SCAN_FAILED_REQUIRES_REVIEW"
            output.append(row)
            continue
        if (
            normalized in rebuilt_source_paths
            and canonical_path_by_hash[row["file_sha256"]] == normalized
        ):
            row["source_category"] = "INCLUDED_AREA_SOURCE"
            row["included_in_inventory"] = True
            row["exclusion_reason"] = ""
        elif normalized in legacy_exclusions:
            category, reason = _category_for_known_exclusion(legacy_exclusions[normalized])
            row["source_category"] = category
            row["exclusion_reason"] = reason
        elif canonical_path_by_hash[row["file_sha256"]] != normalized:
            row["source_category"] = "EXCLUDED_DUPLICATE"
            row["exclusion_reason"] = (
                "BYTE_IDENTICAL_TO:" + canonical_path_by_hash[row["file_sha256"]]
            )
        else:
            parts = {part.casefold() for part in path.parts}
            if parts & {"test", "tests", "fixture", "fixtures", "__tests__"}:
                row["source_category"] = "EXCLUDED_TEST_FIXTURE"
                row["exclusion_reason"] = "TEST_OR_FIXTURE_PATH"
            elif (
                "/templates/" in path.as_posix().casefold()
                or path.name == "season_variety_planting.csv"
            ):
                row["source_category"] = "EXCLUDED_TEST_FIXTURE"
                row["exclusion_reason"] = "HEADER_ONLY_OR_GENERIC_TEMPLATE_NOT_SOURCE_RECORDS"
            elif (
                any(
                    token in path.name.casefold()
                    for token in (
                        "inventory",
                        "manifest",
                        "summary",
                        "candidate",
                        "ledger",
                        "evidence",
                    )
                )
                or "artifact" in path.name.casefold()
            ):
                row["source_category"] = "EXCLUDED_GENERATED_DERIVATIVE"
                row["exclusion_reason"] = "GENERATED_INVENTORY_OR_EVIDENCE_ARTIFACT"
            elif path.suffix.lower() in {".md", ".pdf", ".doc", ".docx"}:
                row["source_category"] = "EXCLUDED_REPORT_ONLY"
                row["exclusion_reason"] = "DOCUMENT_OR_REPORT_REQUIRES_STRUCTURED_SOURCE_ROW_SET"
            elif any(
                token in path.as_posix().casefold() for token in ("registry", "config", "authority")
            ):
                row["source_category"] = "EXCLUDED_REFERENCE_ONLY"
                row["exclusion_reason"] = "REFERENCE_OR_AUTHORITY_CONTEXT_NOT_RAW_AREA_SOURCE"
            else:
                row["source_category"] = "EXCLUDED_OTHER"
                row["exclusion_reason"] = "UNCLASSIFIED_AREA_CANDIDATE_REQUIRES_REVIEW"
        output.append(row)
    return sorted(output, key=lambda row: row["file_path"])


def _record_key(row: dict[str, str]) -> bytes:
    fields = (
        "source_hash",
        "sheet",
        "source_row",
        "source_original_name",
        "farm_identity",
        "base_identity",
        "season",
        "grain",
        "area_mu",
        "original_column_name",
        "original_wording",
        "area_semantics",
        "area_basis",
        "identity_mapping_status",
        "mapped_farm",
        "mapped_base_id",
        "mapped_base",
        "authority_eligibility",
        "decision",
        "notes",
    )
    return canonical_json_bytes({field: row.get(field, "") for field in fields})


def deduplicate_source_records(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse repeated rows emitted from byte-identical workbook copies."""
    sorted_rows = sorted(
        rows,
        key=lambda row: (row.get("source_file", "").casefold(), row.get("source_row", "")),
    )
    seen: set[bytes] = set()
    output = []
    for row in sorted_rows:
        key = _record_key(row)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def record_differences(
    old_rows: list[dict[str, str]], new_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    old_counts = Counter(_record_key(row) for row in old_rows)
    new_counts = Counter(_record_key(row) for row in new_rows)
    samples: dict[bytes, dict[str, str]] = {}
    for row in old_rows + new_rows:
        samples.setdefault(_record_key(row), row)
    result: list[dict[str, Any]] = []
    for key in sorted(set(old_counts) | set(new_counts)):
        delta = old_counts[key] - new_counts[key]
        if not delta:
            continue
        row = samples[key]
        for _ in range(abs(delta)):
            result.append(
                {
                    "diff_status": "OLD_RECORD_NOT_REPRODUCED"
                    if delta > 0
                    else "NEW_RECORD_NOT_IN_OLD",
                    "file_path": row.get("source_file", ""),
                    "file_sha256": row.get("source_hash", ""),
                    "record_count": 1,
                    "detail": "logical_record_key_sha256=" + sha256_bytes(key),
                }
            )
    return sorted(result, key=lambda row: (row["diff_status"], row["file_path"], row["detail"]))


def file_differences(
    old_source_paths: set[str],
    discovered_candidate_paths: set[str],
    new_source_paths: set[str],
    source_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(old_source_paths | new_source_paths):
        if path in old_source_paths and path not in discovered_candidate_paths:
            status = "OLD_FILE_NOT_REDISCOVERED"
        elif path not in old_source_paths and path in new_source_paths:
            status = "NEW_FILE_NOT_IN_OLD"
        elif path in old_source_paths and path in new_source_paths:
            status = "OLD_FILE_REDISCOVERED"
        elif path in old_source_paths and path in discovered_candidate_paths:
            status = "OLD_FILE_REDISCOVERED_DUPLICATE_COPY"
        else:
            continue
        rows.append(
            {
                "diff_status": status,
                "file_path": path,
                "file_sha256": source_hashes.get(path, ""),
                "record_count": 0,
                "detail": "source_file_path_membership",
            }
        )
    return rows


def evaluate_completeness(
    *,
    old_source_paths: set[str],
    discovered_candidate_paths: set[str],
    rebuilt_source_paths: set[str],
    unclassified_candidate_count: int,
    scan_errors: list[str],
) -> dict[str, Any]:
    old_not_found = sorted(old_source_paths - discovered_candidate_paths)
    rebuilt_not_discovered = sorted(rebuilt_source_paths - discovered_candidate_paths)
    new_sources = sorted(rebuilt_source_paths - old_source_paths)
    complete = not (
        old_not_found
        or rebuilt_not_discovered
        or new_sources
        or unclassified_candidate_count
        or scan_errors
    )
    return {
        "completeness_proven": complete,
        "old_files_not_rediscovered": old_not_found,
        "rebuilt_files_not_discovered": rebuilt_not_discovered,
        "new_source_files_not_in_old": new_sources,
        "unclassified_candidate_count": unclassified_candidate_count,
        "scan_errors": list(scan_errors),
    }


def run_frozen_legacy_builder(
    builder_path: Path, expected_sha256: str, output_dir: Path
) -> list[dict[str, str]]:
    actual_hash = sha256_file(builder_path)
    if actual_hash != expected_sha256:
        raise InventoryError(f"LEGACY_BUILDER_HASH_MISMATCH:{actual_hash}")
    source = builder_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(builder_path))
    replaced = False
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "OUT" for target in node.targets
        ):
            tree.body[index] = ast.Assign(
                targets=[ast.Name(id="OUT", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id="Path", ctx=ast.Load()),
                    args=[ast.Constant(str(output_dir))],
                    keywords=[],
                ),
            )
            replaced = True
            break
    if not replaced:
        raise InventoryError("LEGACY_BUILDER_OUTPUT_PATH_NOT_PATCHABLE")
    namespace: dict[str, Any] = {
        "__name__": "_frozen_private_area_inventory_builder",
        "__file__": str(builder_path),
    }
    exec(compile(ast.fix_missing_locations(tree), str(builder_path), "exec"), namespace)
    namespace["main"]()
    output_path = output_dir / "area_source_records.csv"
    if not output_path.is_file():
        raise InventoryError("LEGACY_BUILDER_DID_NOT_EMIT_SOURCE_RECORDS")
    with output_path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json_bytes(value))
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def build_private_inventory(
    *,
    config: dict[str, Any],
    repo_root: Path,
    output_dir: Path,
    old_inventory_path: Path | None = None,
    old_manifest_path: Path | None = None,
    legacy_builder_path: Path | None = None,
) -> dict[str, Any]:
    """Discover source candidates, replay rows, deduplicate and write private artifacts."""
    if output_dir.exists():
        raise InventoryError(f"OUTPUT_DIR_ALREADY_EXISTS:{output_dir}")
    old_inventory = old_inventory_path or Path(config["old_inventory_path"])
    old_manifest = old_manifest_path or Path(config["old_manifest_path"])
    builder = legacy_builder_path or Path(config["legacy_builder_path"])
    for path, expected, label in (
        (old_inventory, OLD_SOURCE_INVENTORY_SHA256, "OLD_INVENTORY"),
        (old_manifest, OLD_SOURCE_MANIFEST_SHA256, "OLD_MANIFEST"),
        (builder, LEGACY_BUILDER_SHA256, "LEGACY_BUILDER"),
    ):
        if not path.is_file() or sha256_file(path) != expected:
            actual = sha256_file(path) if path.is_file() else "MISSING"
            raise InventoryError(f"PINNED_INPUT_MISMATCH:{label}:{actual}")
    with old_inventory.open(encoding="utf-8-sig", newline="") as stream:
        old_rows = list(csv.DictReader(stream))
    old_payload = json.loads(old_manifest.read_text(encoding="utf-8"))
    old_source_paths = {row["source_file"] for row in old_rows}
    old_exclusions = {
        _normalized_path(Path(row["path"])): row["kind"]
        for row in old_payload.get("excluded_sources", [])
    }

    roots, declared_roots = resolve_search_roots(config, repo_root)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    file_rows, enumerated_file_count, scan_errors = enumerate_files(
        roots,
        set(config["ignored_directory_names"]),
        output_dir,
    )
    candidates = discover_area_candidates(
        file_rows,
        {extension.lower() for extension in config["file_extensions_scanned"]},
        list(config["search_keywords"]),
    )

    with tempfile.TemporaryDirectory(prefix="v08-area-inventory-legacy-replay-") as temporary:
        replay_dir = Path(temporary) / "legacy-output"
        replay_dir.mkdir(mode=0o700)
        parsed_rows = run_frozen_legacy_builder(builder, LEGACY_BUILDER_SHA256, replay_dir)
    rebuilt_rows = deduplicate_source_records(parsed_rows)
    new_source_paths = {row["source_file"] for row in rebuilt_rows}
    old_paths = {_normalized_path(Path(path)) for path in old_source_paths}
    new_paths = {_normalized_path(Path(path)) for path in new_source_paths}
    # Legacy records use normalized absolute paths; normalize for platform stability.
    for row in rebuilt_rows:
        row["source_file"] = _normalized_path(Path(row["source_file"]))
    for row in old_rows:
        row["source_file"] = _normalized_path(Path(row["source_file"]))
    old_paths = {row["source_file"] for row in old_rows}
    new_paths = {row["source_file"] for row in rebuilt_rows}
    discovered_paths = {row["file_path"] for row in candidates}
    path_to_digest = {row["file_path"]: row["file_sha256"] for row in candidates}
    classified = classify_candidates(candidates, new_paths, old_paths, old_exclusions)

    # Ensure any parser input omitted by keyword scanning is visible as a hard provenance error.
    missing_discovery_paths = sorted(new_paths - discovered_paths)
    old_missing = sorted(old_paths - discovered_paths)
    file_diff = file_differences(old_paths, discovered_paths, new_paths, path_to_digest)
    record_diff = record_differences(old_rows, rebuilt_rows)
    category_counts = dict(sorted(Counter(row["source_category"] for row in classified).items()))
    unclassified_count = category_counts.get("EXCLUDED_OTHER", 0)
    unsupported_candidate_count = sum(
        row["source_category"] == "EXCLUDED_UNSUPPORTED_FORMAT" for row in classified
    )
    new_source_candidates = [
        row
        for row in classified
        if row["included_in_inventory"] and row["file_path"] not in old_paths
    ]
    # An old inventory record count change is intentionally not accepted in this pass.
    record_inventory_exact_parity = len(old_rows) == len(rebuilt_rows) and not record_diff
    recovery_unchanged = record_inventory_exact_parity and not new_source_candidates
    completeness = evaluate_completeness(
        old_source_paths=old_paths,
        discovered_candidate_paths=discovered_paths,
        rebuilt_source_paths=new_paths,
        unclassified_candidate_count=unclassified_count,
        scan_errors=scan_errors,
    )
    completeness_proven = completeness["completeness_proven"]

    output_dir.mkdir(mode=0o700)
    output_dir.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    _write_csv(output_dir / "area-source-file-inventory-r1.csv", classified, FILE_FIELDS)
    record_fields = tuple(parsed_rows[0].keys()) if parsed_rows else ()
    _write_csv(output_dir / "area-source-record-inventory-r1.csv", rebuilt_rows, record_fields)
    _write_csv(output_dir / "old-vs-rebuilt-inventory-file-diff-r1.csv", file_diff, DIFF_FIELDS)
    _write_csv(output_dir / "old-vs-rebuilt-inventory-record-diff-r1.csv", record_diff, DIFF_FIELDS)

    discovery_manifest = {
        "task_id": TASK_ID,
        "search_root_count": len(roots),
        "declared_search_roots": declared_roots,
        "search_roots": roots,
        "enumerated_file_count": enumerated_file_count,
        "candidate_file_count": len(classified),
        "candidate_file_classification_counts": category_counts,
        "search_keywords": config["search_keywords"],
        "file_extensions_scanned": config["file_extensions_scanned"],
        "ignored_directory_names": sorted(config["ignored_directory_names"]),
        "scan_timestamp_policy": config["scan_timestamp_policy"],
        "deterministic_ordering": "NORMALIZED_ABSOLUTE_PATH_ASCENDING; ROOTS_AND_ENTRIES_SORTED",
        "deduplication_policy": config["deduplication_policy"],
        "scan_errors": scan_errors,
        "files": classified,
        "completeness_proven": completeness_proven,
    }
    _write_json(output_dir / "area-source-discovery-manifest-r1.json", discovery_manifest)

    summary = {
        "task_id": TASK_ID,
        "old_source_file_count": len(old_paths),
        "new_source_file_count": len(new_paths),
        "old_source_record_count": len(old_rows),
        "new_source_record_count": len(rebuilt_rows),
        "enumerated_file_count": enumerated_file_count,
        "area_candidate_file_count": len(classified),
        "source_category_counts": category_counts,
        "old_files_not_rediscovered": len(old_missing),
        "new_files_not_in_old": len(new_source_candidates),
        "new_records_not_in_old": sum(
            row["diff_status"] == "NEW_RECORD_NOT_IN_OLD" for row in record_diff
        ),
        "old_records_not_reproduced": sum(
            row["diff_status"] == "OLD_RECORD_NOT_REPRODUCED" for row in record_diff
        ),
        "old_source_paths_missing_from_discovery": old_missing,
        "rebuilt_source_paths_missing_from_discovery": missing_discovery_paths,
        "completeness_gate": completeness,
        "scan_error_count": len(scan_errors),
        "unclassified_candidate_count": unclassified_count,
        "unsupported_candidate_count": unsupported_candidate_count,
        "area_source_inventory_rebuild_deterministic": True,
        "source_discovery_completeness_proven": completeness_proven,
        "source_file_set_exact_parity": not (
            old_missing or missing_discovery_paths or new_source_candidates
        ),
        "record_inventory_exact_parity": record_inventory_exact_parity,
        "area_source_inventory_completeness_proven": completeness_proven
        and record_inventory_exact_parity,
        "previous_area_inventory_incomplete": bool(
            old_missing or missing_discovery_paths or new_source_candidates
        ),
        "inventory_rebuild_found_previously_missed_sources": bool(new_source_candidates),
        "area_recovery_results_unchanged": recovery_unchanged,
        "legacy_parsed_record_count_before_deduplication": len(parsed_rows),
        "exact_duplicate_record_count_removed": len(parsed_rows) - len(rebuilt_rows),
        "duplicate_source_sha256_groups": _duplicate_groups(classified),
        "s3_recovery_rerun_executed": False,
        "existing_area_authority_modified": False,
        "model_training_executed": False,
    }
    _write_json(output_dir / "inventory-rebuild-summary-r1.json", summary)
    output_hashes = {
        path.name: sha256_file(path) for path in sorted(output_dir.iterdir()) if path.is_file()
    }
    artifact_manifest = {
        "task_id": TASK_ID,
        "output_file_hashes": output_hashes,
        "summary_hash": sha256_file(output_dir / "inventory-rebuild-summary-r1.json"),
        "source_inventory_builder_sha256": sha256_file(Path(__file__)),
        "legacy_parser_sha256": LEGACY_BUILDER_SHA256,
        "old_inventory_sha256": OLD_SOURCE_INVENTORY_SHA256,
        "old_manifest_sha256": OLD_SOURCE_MANIFEST_SHA256,
    }
    _write_json(output_dir / "artifact-manifest.json", artifact_manifest)
    summary["discovery_manifest_sha256"] = sha256_file(
        output_dir / "area-source-discovery-manifest-r1.json"
    )
    summary["rebuilt_area_source_inventory_sha256"] = sha256_file(
        output_dir / "area-source-record-inventory-r1.csv"
    )
    summary["inventory_diff_sha256"] = sha256_file(
        output_dir / "old-vs-rebuilt-inventory-record-diff-r1.csv"
    )
    summary["private_artifact_manifest_sha256"] = sha256_file(output_dir / "artifact-manifest.json")
    return summary


def _duplicate_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row["file_sha256"]].append(row["file_path"])
    return [
        {"file_sha256": digest, "paths": sorted(paths), "duplicate_path_count": len(paths) - 1}
        for digest, paths in sorted(grouped.items())
        if len(paths) > 1
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/v0_8_s3_area_source_inventory_completeness_r1.json"),
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    output_dir = args.output_dir or Path(config["private_output_path"])
    summary = build_private_inventory(
        config=config,
        repo_root=args.repo_root.resolve(),
        output_dir=output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
