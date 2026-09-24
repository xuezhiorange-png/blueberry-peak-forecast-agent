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
import subprocess
import tempfile
import zipfile
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

TASK_ID = "V0_8_S3_AREA_SOURCE_INVENTORY_COMPLETENESS_CLOSURE_R2"
OLD_SOURCE_INVENTORY_SHA256 = "81341ce629a479db82ad4f02539afd9759c8eacfe29a311683dd38ef63c681cf"
OLD_SOURCE_MANIFEST_SHA256 = "c66dffe275741b7c985920fed4cf32c8af43420650873b59f6a2bdb2fbfea2f1"
LEGACY_BUILDER_SHA256 = "d9a4a1d214e68ffaa00e46f74842001480b0b2aee29d3f9e56ab2240a60376f9"
R1_DISCOVERY_MANIFEST_PATH = (
    "/Users/charles/Documents/blueberry-area-yield-artifacts/"
    "v0-8-s3-area-source-inventory-completeness-r1/area-source-discovery-manifest-r1.json"
)
R1_DISCOVERY_MANIFEST_SHA256 = "217743b3b146cbe6ad18a3abf82dd0b2b6d706c8aee1e51e42ba280148ed4285"

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
    "classification_rule_id",
    "classification_reason",
    "classification_evidence",
    "review_required",
)
DIFF_FIELDS = ("diff_status", "file_path", "file_sha256", "record_count", "detail")
OLD_PATH_FIELDS = (
    "old_source_path",
    "file_sha256",
    "frozen_source_sha256",
    "file_exists_now",
    "search_root_covered",
    "file_extension",
    "filename_keyword_hits",
    "content_keyword_hits",
    "scan_status",
    "legacy_parser_used",
    "prior_discovery_candidate",
    "rediscovered_path",
    "path_status",
    "why_not_discovered",
    "required_policy_change",
)
PRIOR_REVIEW_COHORT_FIELDS = (
    "r1_source_category",
    "r1_source_path",
    "r1_source_sha256",
    "current_source_path",
    "current_source_sha256",
    "current_source_category",
    "current_classification_rule_id",
    "current_classification_reason",
    "current_classification_evidence",
    "current_scan_status",
    "r1_historical_sha256_verified",
    "r1_historical_git_revision",
    "r1_historical_classification_rule_id",
    "r1_historical_classification_reason",
    "r1_historical_classification_evidence",
    "reconciliation_status",
    "reconciliation_reason",
)
DUPLICATE_PARITY_FIELDS = (
    "logical_record_key_sha256",
    "source_hash",
    "duplicate_row_count",
    "duplicate_rows_removed",
    "business_field_parity",
    "differing_business_fields",
)
BUSINESS_DUPLICATE_FIELDS = (
    "source_hash",
    "season",
    "farm_identity",
    "base_identity",
    "area_mu",
    "area_semantics",
    "area_basis",
    "decision",
    "authority_eligibility",
)
AREA_HEADER_TOKENS = (
    "亩",
    "亩数",
    "面积亩",
    "面积(亩)",
    "面积（亩）",
    "种植面积",
    "投产面积",
    "productive_area_mu",
    "historical_area_mu",
    "area_mu",
)
IDENTITY_HEADER_TOKENS = (
    "农场",
    "农场名称",
    "基地",
    "基地名称",
    "source_farm_label",
    "canonical_base_name",
    "base_id",
    "farm",
    "加工厂",
    "加工厂名称",
)
CLASSIFICATION_RULE_REGISTRY: tuple[dict[str, str], ...] = (
    {
        "rule_id": "R2-001",
        "category": "INCLUDED_AREA_SOURCE",
        "basis": "FROZEN_LEGACY_PARSER_INPUT",
    },
    {"rule_id": "R2-002", "category": "EXCLUDED_DUPLICATE", "basis": "BYTE_IDENTICAL_SHA256_COPY"},
    {
        "rule_id": "R2-003",
        "category": "EXCLUDED_TEST_FIXTURE",
        "basis": "TEST_FIXTURE_PATH_SEGMENT",
    },
    {
        "rule_id": "R2-004",
        "category": "EXCLUDED_GENERATED_DERIVATIVE",
        "basis": "GENERATED_INVENTORY_MODEL_OR_EVIDENCE_PATH",
    },
    {
        "rule_id": "R2-005",
        "category": "EXCLUDED_NON_AGRICULTURAL_AREA",
        "basis": "STRUCTURED_PROCESSING_FACTORY_GRAIN",
    },
    {
        "rule_id": "R2-006",
        "category": "EXCLUDED_ENGINEERING_AREA",
        "basis": "STRUCTURED_FACILITY_OR_BUILDING_AREA",
    },
    {
        "rule_id": "R2-007",
        "category": "EXCLUDED_REFERENCE_ONLY",
        "basis": "REFERENCE_REGISTRY_OR_AUTHORITY_CONTEXT",
    },
    {
        "rule_id": "R2-008",
        "category": "EXCLUDED_HARVEST_ONLY",
        "basis": "HARVEST_QUANTITY_SCHEMA_WITHOUT_AREA_FIELD",
    },
    {
        "rule_id": "R2-009",
        "category": "EXCLUDED_WEATHER_FILE",
        "basis": "WEATHER_SOURCE_OR_OBSERVATION_SCHEMA",
    },
    {
        "rule_id": "R2-010",
        "category": "EXCLUDED_REPORT_ONLY",
        "basis": "REPORT_DOCUMENT_WITHOUT_SOURCE_ROW_SCHEMA",
    },
    {
        "rule_id": "R2-011",
        "category": "EXCLUDED_NON_AREA_BUSINESS_FILE",
        "basis": "CODE_OR_NON_DATA_BUSINESS_DOCUMENT",
    },
    {
        "rule_id": "R2-012",
        "category": "REVIEW_REQUIRED",
        "basis": "INSUFFICIENT_DETERMINISTIC_EVIDENCE",
    },
    {
        "rule_id": "R2-013",
        "category": "EXCLUDED_BACKUP_COPY",
        "basis": "OFFICE_LOCK_OR_TEMPORARY_COPY",
    },
    {
        "rule_id": "R2-014",
        "category": "EXCLUDED_ENGINEERING_AREA",
        "basis": "CAD_CREATOR_METADATA_OR_EXPLICIT_ENGINEERING_CONTEXT",
    },
    {
        "rule_id": "R2-015",
        "category": "EXCLUDED_NO_AREA_FIELD",
        "basis": "PINNED_LEGACY_SCAN_FOUND_NO_AGRICULTURAL_AREA_FIELD",
    },
    {
        "rule_id": "R2-016",
        "category": "EXCLUDED_UNSUPPORTED_FORMAT",
        "basis": "PINNED_LEGACY_NON_SOURCE_CONTEXT_FOR_UNSUPPORTED_FORMAT",
    },
    {
        "rule_id": "R2-017",
        "category": "EXCLUDED_TEMPLATE",
        "basis": "GENERIC_OR_BLANK_DECISION_TEMPLATE_SCHEMA",
    },
)


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


def _pdf_metadata(path: Path) -> dict[str, str]:
    """Read deterministic literal metadata from a PDF header without rendering it."""
    try:
        payload = path.read_bytes()[: 1024 * 1024]
    except OSError:
        return {}
    metadata: dict[str, str] = {}
    for key in (b"Title", b"Creator", b"Producer", b"Subject"):
        match = re.search(rb"/" + key + rb"\s*\((?:\\.|[^)])*\)", payload)
        if match:
            value = match.group(0).split(b"(", 1)[1].rsplit(b")", 1)[0]
            metadata[key.decode("ascii").lower()] = _decode_search_bytes(value)
    return metadata


def _is_office_temporary(path: Path) -> bool:
    return path.name.startswith((".~", "~$"))


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


def _normalized_header(value: Any) -> str:
    return re.sub(r"[\s\u3000:：_\-（）()\[\]【】]", "", str(value or "")).casefold()


def _spreadsheet_rows(path: Path) -> tuple[list[tuple[str, int, list[str]]], str]:
    """Read bounded spreadsheet rows for structural source detection only."""
    suffix = path.suffix.lower()
    rows: list[tuple[str, int, list[str]]] = []
    try:
        if suffix in {".xlsx", ".xlsm"}:
            from openpyxl import load_workbook

            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                for sheet in workbook.worksheets:
                    for number, values in enumerate(
                        sheet.iter_rows(max_row=500, max_col=60, values_only=True), 1
                    ):
                        rows.append(
                            (sheet.title, number, [str(v) if v is not None else "" for v in values])
                        )
            finally:
                workbook.close()
            return rows, "STRUCTURE_SCANNED"
        if suffix == ".xls":
            import xlrd

            workbook = xlrd.open_workbook(str(path), on_demand=True)
            try:
                for sheet in workbook.sheets():
                    for number in range(min(sheet.nrows, 500)):
                        values = sheet.row_values(
                            number, start_colx=0, end_colx=min(sheet.ncols, 60)
                        )
                        rows.append((sheet.name, number + 1, [str(v) for v in values]))
            finally:
                workbook.release_resources()
            return rows, "STRUCTURE_SCANNED"
        if suffix == ".ods":
            with zipfile.ZipFile(path) as archive:
                payload = archive.read("content.xml")
            root = ElementTree.fromstring(payload)
            table_ns = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
            text_ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
            for sheet in root.iter(f"{table_ns}table"):
                sheet_name = sheet.attrib.get(f"{table_ns}name", "")
                for row_number, row in enumerate(sheet.iter(f"{table_ns}table-row"), 1):
                    if row_number > 500:
                        break
                    ods_values: list[str] = []
                    for cell in list(row)[:60]:
                        text = " ".join(node.text or "" for node in cell.iter(f"{text_ns}p"))
                        repeat = int(cell.attrib.get(f"{table_ns}number-columns-repeated", "1"))
                        ods_values.extend([text] * min(repeat, 60 - len(ods_values)))
                    rows.append((sheet_name, row_number, ods_values))
            return rows, "STRUCTURE_SCANNED"
    except Exception as exc:  # workbook decoders expose several library-specific exceptions
        return [], f"STRUCTURE_SCAN_UNAVAILABLE:{type(exc).__name__}"
    return [], "STRUCTURE_SCAN_UNSUPPORTED"


def inspect_structured_area_schema(path: Path) -> dict[str, Any]:
    """Detect identity/area column co-occurrence without inferring authority."""
    rows, status = _spreadsheet_rows(path)
    findings: list[dict[str, Any]] = []
    for index, (sheet, row_number, values) in enumerate(rows):
        normalized = [_normalized_header(value) for value in values]
        identity_columns = [
            values[column].strip()
            for column, value in enumerate(normalized)
            if value and any(_normalized_header(token) == value for token in IDENTITY_HEADER_TOKENS)
        ]
        area_columns = [
            values[column].strip()
            for column, value in enumerate(normalized)
            if value and any(_normalized_header(token) == value for token in AREA_HEADER_TOKENS)
        ]
        if not identity_columns or not area_columns:
            continue
        later_rows = rows[index + 1 : index + 21]
        has_data = any(
            any(value.strip() for value in later_values)
            for later_sheet, later_number, later_values in later_rows
            if later_sheet == sheet and later_number > row_number
        )
        identity_joined = "|".join(_normalized_header(value) for value in identity_columns)
        area_joined = "|".join(_normalized_header(value) for value in area_columns)
        if "加工厂" in identity_joined:
            grain = "PROCESSING_FACTORY"
        elif any(token in identity_joined for token in ("农场", "基地", "farm", "base")):
            grain = "FARM_OR_BASE_CANDIDATE"
        else:
            grain = "OTHER_IDENTITY_GRAIN"
        if any(token in area_joined for token in ("m2", "平方米", "建筑面积", "库房底面积")):
            area_unit_class = "FACILITY_AREA_OR_SQUARE_METRES"
        elif any(token in area_joined for token in ("亩", "area_mu", "productive_area_mu")):
            area_unit_class = "MU_OR_AREA_MU_FIELD"
        else:
            area_unit_class = "AREA_UNIT_NOT_ESTABLISHED"
        findings.append(
            {
                "sheet": sheet,
                "header_row": row_number,
                "identity_columns": identity_columns,
                "area_columns": area_columns,
                "grain": grain,
                "area_unit_class": area_unit_class,
                "has_data_rows": has_data,
            }
        )
    return {"scan_status": status, "findings": findings}


def inspect_structured_sources(
    file_rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Scan every bounded spreadsheet candidate for identity/area header structure."""
    findings: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for file_row in file_rows:
        path = Path(file_row["file_path"])
        if path.suffix.lower() not in {".xlsx", ".xlsm", ".xls", ".ods"}:
            continue
        if _is_office_temporary(path):
            continue
        inspection = inspect_structured_area_schema(path)
        if inspection["findings"] or "UNAVAILABLE" in inspection["scan_status"]:
            findings[file_row["file_path"]] = inspection
        if "UNAVAILABLE" in inspection["scan_status"]:
            errors.append(
                f"STRUCTURED_SCAN_UNAVAILABLE:{file_row['file_path']}:{inspection['scan_status']}"
            )
    return findings, errors


def enumerate_files(
    roots: list[dict[str, Any]],
    ignored_directory_names: set[str],
    excluded_output: Path,
    ignored_directory_name_prefixes: tuple[str, ...] = (),
    ignored_file_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Recursively enumerate files in sorted order; symlinks are recorded as skips."""
    paths: dict[str, set[str]] = defaultdict(set)
    enumerated_paths: set[str] = set()
    scan_errors: list[str] = []
    output_root = excluded_output.resolve(strict=False)
    ignored_files = ignored_file_paths or set()
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
                if (
                    dirname in ignored_directory_names
                    or any(dirname.startswith(prefix) for prefix in ignored_directory_name_prefixes)
                    or directory.is_symlink()
                ):
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
                if normalized in ignored_files or _path_is_within(path, output_root):
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
    file_rows: list[dict[str, Any]],
    extensions: set[str],
    keywords: list[str],
    structural_findings: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    structural_findings = structural_findings or {}
    candidates: list[dict[str, Any]] = []
    for file_row in file_rows:
        path = Path(file_row["file_path"])
        suffix = path.suffix.lower()
        if suffix not in extensions:
            continue
        name_hits = _matches_keywords(path.name, keywords)
        content, scan_status = searchable_text(path)
        content_hits = _matches_keywords(content, keywords)
        structural = structural_findings.get(file_row["file_path"], {})
        structural_rows = structural.get("findings", [])
        pdf_metadata = _pdf_metadata(path) if suffix == ".pdf" else {}
        scan_failed = (
            scan_status == "READ_ERROR"
            or "UNAVAILABLE" in scan_status
            or "LIMIT_EXCEEDED" in scan_status
        )
        if not name_hits and not content_hits and not scan_failed and not structural_rows:
            continue
        hits = sorted(set(name_hits + content_hits), key=str.casefold)
        file_digest = sha256_file(path)
        structural_grains = sorted({item["grain"] for item in structural_rows})
        structural_area_units = sorted({item["area_unit_class"] for item in structural_rows})
        candidates.append(
            {
                **file_row,
                "file_sha256": file_digest,
                "source_category": "UNCLASSIFIED_CANDIDATE",
                "candidate_reason": (
                    "STRUCTURAL_AREA_SCHEMA"
                    if structural_rows and not name_hits and not content_hits and not scan_failed
                    else "CONTENT_SCAN_FAILED"
                    if scan_failed
                    else "KEYWORD_MATCH:" + ",".join(hits)
                ),
                "included_in_inventory": False,
                "exclusion_reason": "",
                "logical_source_identity": "CONTENT_SHA256:" + file_digest,
                "scan_status": scan_status,
                "structural_area_schema": structural_rows,
                "structural_grains": structural_grains,
                "structural_area_units": structural_area_units,
                "pdf_metadata": pdf_metadata,
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
        row["classification_rule_id"] = ""
        row["classification_reason"] = ""
        row["classification_evidence"] = ""
        row["review_required"] = False

        def classify(
            category: str,
            rule_id: str,
            reason: str,
            evidence: str,
            target: dict[str, Any] = row,
        ) -> None:
            target["source_category"] = category
            target["classification_rule_id"] = rule_id
            target["classification_reason"] = reason
            target["classification_evidence"] = evidence
            target["review_required"] = category == "REVIEW_REQUIRED"
            target["exclusion_reason"] = "" if category == "INCLUDED_AREA_SOURCE" else reason

        if (
            normalized in rebuilt_source_paths
            and canonical_path_by_hash[row["file_sha256"]] == normalized
        ):
            row["included_in_inventory"] = True
            row["exclusion_reason"] = ""
            classify(
                "INCLUDED_AREA_SOURCE",
                "R2-001",
                "FROZEN_LEGACY_PARSER_INPUT",
                "path emitted by SHA-pinned legacy parser; inventory semantics remain unchanged",
            )
        elif normalized in legacy_exclusions:
            category, reason = _category_for_known_exclusion(legacy_exclusions[normalized])
            rule_id = {
                "EXCLUDED_REFERENCE_ONLY": "R2-007",
                "EXCLUDED_NO_AREA_FIELD": "R2-015",
                "EXCLUDED_UNSUPPORTED_FORMAT": "R2-016",
                "EXCLUDED_REPORT_ONLY": "R2-010",
            }[category]
            classify(
                category,
                rule_id,
                reason,
                "pinned legacy exclusion manifest",
            )
        elif canonical_path_by_hash[row["file_sha256"]] != normalized:
            target = canonical_path_by_hash[row["file_sha256"]]
            classify(
                "EXCLUDED_DUPLICATE",
                "R2-002",
                "BYTE_IDENTICAL_TO:" + target,
                "same SHA256 as canonical discovered path " + target,
            )
        else:
            full_path = path.as_posix().casefold()
            name = path.name.casefold()
            suffix = path.suffix.lower()
            structural = row.get("structural_area_schema", [])
            structural_grains = set(row.get("structural_grains", []))
            structural_units = set(row.get("structural_area_units", []))
            pdf_metadata = row.get("pdf_metadata", {})
            pdf_creator = str(pdf_metadata.get("creator", "")).casefold()
            path_parts = {part.casefold() for part in path.parts}
            if _is_office_temporary(path):
                classify(
                    "EXCLUDED_BACKUP_COPY",
                    "R2-013",
                    "OFFICE_LOCK_OR_TEMPORARY_WORKBOOK_COPY",
                    "filename uses the Office temporary/lock prefix .~ or ~$",
                )
            elif path_parts & {"test", "tests", "fixture", "fixtures", "__tests__"}:
                classify(
                    "EXCLUDED_TEST_FIXTURE",
                    "R2-003",
                    "TEST_OR_FIXTURE_PATH",
                    "path segment identifies a test or fixture",
                )
            elif (
                "/templates/" in full_path
                or name == "season_variety_planting.csv"
                or "template" in name
                or "模板" in name
            ):
                classify(
                    "EXCLUDED_TEMPLATE",
                    "R2-017",
                    "GENERIC_TEMPLATE_NOT_SOURCE_ROWS",
                    "template directory or header-only template identity",
                )
            elif any(
                token in full_path
                for token in (
                    "/area-yield-model-",
                    "/replay-",
                    "/backtest",
                    "/predictions",
                    "/evidence/",
                    "/area-curve-",
                    "/phenology-anchored-temporal-model-r6/",
                )
            ) or any(
                token in name
                for token in (
                    "inventory",
                    "manifest",
                    "summary",
                    "candidate",
                    "ledger",
                    "evidence",
                    "prediction",
                    "backtest",
                    "training",
                    "model-artifact",
                    "metric-comparison",
                    "old-vs-new-area-authority-diff",
                    "identity-matrix",
                    "priority-matrix",
                    "per-base-timing",
                    "per_base_timing_r6",
                    "per-farm-comparison",
                    "forecast_example",
                    "final_targets",
                )
            ):
                classify(
                    "EXCLUDED_GENERATED_DERIVATIVE",
                    "R2-004",
                    "GENERATED_MODEL_OR_EVIDENCE_ARTIFACT",
                    "path/name identifies a derived model, replay, inventory, or evidence artifact",
                )
            elif structural and "PROCESSING_FACTORY" in structural_grains:
                classify(
                    "EXCLUDED_NON_AGRICULTURAL_AREA",
                    "R2-005",
                    "PROCESSING_FACTORY_STATISTICAL_GRAIN",
                    "structured identity header includes 加工厂; not farm/Base "
                    "productive-area grain",
                )
            elif (
                structural
                and "FACILITY_AREA_OR_SQUARE_METRES" in structural_units
                and "FARM_OR_BASE_CANDIDATE" not in structural_grains
            ):
                classify(
                    "EXCLUDED_ENGINEERING_AREA",
                    "R2-006",
                    "FACILITY_OR_BUILDING_AREA_SCHEMA",
                    "structured area field is facility/building m2 and lacks farm/Base identity",
                )
            elif "area_confirmation_" in name and suffix in {".csv", ".tsv"}:
                headers, data_rows = _read_tabular(path)
                confirmation_fields = (
                    "BUSINESS_CONFIRMED_AREA_MU",
                    "BUSINESS_CONFIRMATION_NOTE",
                    "CONFIRMED_BY",
                    "CONFIRMED_AT",
                )
                has_confirmation_fields = set(confirmation_fields).issubset(set(headers))
                has_confirmed_values = any(
                    any(str(data.get(field, "")).strip() for field in confirmation_fields)
                    for data in data_rows
                )
                if has_confirmation_fields and not has_confirmed_values:
                    classify(
                        "EXCLUDED_TEMPLATE",
                        "R2-017",
                        "BUSINESS_CONFIRMATION_FIELDS_BLANK",
                        "confirmation template has explicit decision columns and all are blank",
                    )
                else:
                    classify(
                        "REVIEW_REQUIRED",
                        "R2-012",
                        "BUSINESS_CONFIRMATION_CONTENT_REQUIRES_AUTHORITY_REVIEW",
                        "confirmation fields are populated or schema is incomplete; "
                        "no automatic acceptance",
                    )
            elif (
                any(
                    token in full_path
                    for token in (
                        "/base-registry",
                        "/registry",
                        "/authority",
                        "/identity",
                        "/area-confirmation",
                        "/cross-season-data-mapping",
                        "/historical-identity-reconstruction",
                        "/existing-area-source-semantics-reconstruction",
                    )
                )
                or "area_source_semantics_" in name
            ):
                classify(
                    "EXCLUDED_REFERENCE_ONLY",
                    "R2-007",
                    "REFERENCE_OR_AUTHORITY_CONTEXT",
                    "path identifies registry, authority, identity, or audit derivative",
                )
            elif any(
                token in full_path or token in name
                for token in ("era5", "weather", "meteorological", "气象", "天气")
            ):
                classify(
                    "EXCLUDED_WEATHER_FILE",
                    "R2-009",
                    "WEATHER_DATA_NOT_AREA_SOURCE",
                    "path/name identifies weather source or observation data",
                )
            elif (
                structural
                and "FARM_OR_BASE_CANDIDATE" in structural_grains
                and "MU_OR_AREA_MU_FIELD" in structural_units
            ):
                if any(
                    token in full_path
                    for token in (
                        "reference_area",
                        "reference-area",
                        "base-registry",
                        "registry",
                        "model",
                        "forecast",
                        "backtest",
                    )
                ):
                    classify(
                        "EXCLUDED_REFERENCE_ONLY",
                        "R2-007",
                        "REFERENCE_OR_MODEL_INPUT_AREA",
                        "farm/Base area schema is explicitly in registry/reference/model context",
                    )
                else:
                    classify(
                        "REVIEW_REQUIRED",
                        "R2-012",
                        "POTENTIAL_FARM_AREA_SOURCE_NEEDS_PROVENANCE_REVIEW",
                        "structured farm/Base identity and mu area columns with data rows; "
                        "season/authority must be reviewed",
                    )
            elif suffix == ".py":
                classify(
                    "EXCLUDED_NON_AREA_BUSINESS_FILE",
                    "R2-011",
                    "SOURCE_CODE_NOT_SOURCE_RECORDS",
                    "Python source file cannot itself establish business area rows",
                )
            elif suffix in {".csv", ".tsv"}:
                headers = _read_tabular_header(path)
                normalized_headers = {_normalized_header(value) for value in headers}
                if any(
                    token in full_path or token in name
                    for token in ("施工图设置", "配筋计算", "drawset")
                ):
                    classify(
                        "EXCLUDED_ENGINEERING_AREA",
                        "R2-006",
                        "CAD_ENGINEERING_QUANTITY_EXPORT",
                        "path/name identifies CAD reinforcement or engineering drawing export",
                    )
                elif normalized_headers & {
                    "actualkg",
                    "harvestkg",
                    "harvestquantitykg",
                    "quantitykg",
                    "采摘量",
                    "产量",
                } and not normalized_headers & {
                    _normalized_header(token) for token in AREA_HEADER_TOKENS
                }:
                    classify(
                        "EXCLUDED_HARVEST_ONLY",
                        "R2-008",
                        "HARVEST_QUANTITY_SCHEMA_WITHOUT_AREA_FIELD",
                        "tabular header has harvest quantity but no area field",
                    )
                elif (
                    any(
                        token in full_path
                        for token in (
                            "/model",
                            "/replay",
                            "/backtest",
                            "/training",
                            "/audit",
                            "/evidence",
                            "/cross-season",
                            "historical-season-area-authority-recovery",
                            "business-season-boundary-audit",
                            "existing-area-source-semantics",
                            "phenology-anchored-temporal-model-r6",
                        )
                    )
                    or any(
                        token in normalized_headers
                        for token in (
                            "predictedtotalkg",
                            "predictionkg",
                            "modelversion",
                            "dailywape",
                            "totalabserror",
                            "peakdateerrordays",
                        )
                    )
                    or any(
                        token in name
                        for token in (
                            "audit",
                            "reconstruction",
                            "comparison",
                            "metric",
                            "per_base_timing_r6",
                        )
                    )
                ):
                    classify(
                        "EXCLUDED_GENERATED_DERIVATIVE",
                        "R2-004",
                        "GENERATED_TABULAR_DERIVATIVE",
                        "tabular path is a model, replay, audit, or evidence output",
                    )
                elif "referenceareamu" in normalized_headers or "areabasis" in normalized_headers:
                    classify(
                        "EXCLUDED_REFERENCE_ONLY",
                        "R2-007",
                        "REFERENCE_AREA_OR_MODEL_SCHEMA",
                        "tabular header marks area as reference/model input",
                    )
                else:
                    classify(
                        "REVIEW_REQUIRED",
                        "R2-012",
                        "TABULAR_CANDIDATE_SCHEMA_NOT_RESOLVED",
                        "tabular area candidate lacks a deterministic source/non-source rule",
                    )
            elif suffix in {".xlsx", ".xlsm", ".xls", ".ods"} and structural:
                classify(
                    "REVIEW_REQUIRED",
                    "R2-012",
                    "SPREADSHEET_AREA_SCHEMA_NOT_RESOLVED",
                    "spreadsheet has area-like structure not covered by an exclusion authority",
                )
            elif (suffix == ".pdf" and pdf_creator in {"gcad", "zwcad", "autocad"}) or any(
                token in full_path or token in name
                for token in (
                    "施工图",
                    "建施",
                    "结施",
                    "水施",
                    "电施",
                    "冷库",
                    "加工厂",
                    "制冷",
                    "设备配置",
                    "冷库报价",
                    "平面图",
                    "总图",
                    "审图",
                    "建筑主体",
                    "规划设计图",
                    "速冻线",
                    "示意图",
                    "机组",
                    "电控箱",
                    "压缩机机组",
                    "配筋计算",
                    "施工图设置",
                )
            ):
                classify(
                    "EXCLUDED_ENGINEERING_AREA",
                    "R2-014"
                    if suffix == ".pdf" and pdf_creator in {"gcad", "zwcad", "autocad"}
                    else "R2-006",
                    "ENGINEERING_OR_FACILITY_DOCUMENT",
                    "PDF creator metadata=" + pdf_creator
                    if suffix == ".pdf" and pdf_creator in {"gcad", "zwcad", "autocad"}
                    else "path/name identifies a facility, CAD drawing, building, equipment, "
                    "or engineering source context",
                )
            elif suffix in {".pdf", ".xls", ".doc", ".docx"} and (
                "tpm" in name
                or "tpm" in full_path
                or any(
                    token in name
                    for token in (
                        "方案",
                        "介绍",
                        "教材",
                        "讲义",
                        "培养",
                        "培训",
                        "汇报",
                        "分析",
                        "点检",
                        "保养规范",
                    )
                )
            ):
                classify(
                    "EXCLUDED_REPORT_ONLY",
                    "R2-010",
                    "REPORT_OR_TRAINING_DOCUMENT_NOT_SOURCE_ROWS",
                    "filename identifies report, proposal, analysis, or training material; "
                    "no structured source row schema",
                )
            elif suffix in {".md", ".doc", ".docx", ".html", ".txt"}:
                classify(
                    "EXCLUDED_REPORT_ONLY",
                    "R2-010",
                    "DOCUMENT_WITHOUT_SOURCE_ROW_SCHEMA",
                    "document text is not a structured area source row set",
                )
            elif suffix in {".json", ".xml", ".yml", ".yaml", ".toml"}:
                classify(
                    "EXCLUDED_REFERENCE_ONLY",
                    "R2-007",
                    "MACHINE_READABLE_REFERENCE_OR_CONFIGURATION",
                    "machine-readable config/metadata is not a raw business area source",
                )
            elif (
                row.get("scan_status") in {"READ_ERROR"}
                or "UNAVAILABLE" in row.get("scan_status", "")
                or "LIMIT_EXCEEDED" in row.get("scan_status", "")
            ):
                classify(
                    "REVIEW_REQUIRED",
                    "R2-012",
                    "CONTENT_UNREADABLE_WITHOUT_PROVEN_NON_SOURCE_CONTEXT",
                    row.get("scan_status", "unknown scan status"),
                )
            else:
                classify(
                    "EXCLUDED_NON_AREA_BUSINESS_FILE",
                    "R2-011",
                    "NO_FARM_AREA_SOURCE_SCHEMA",
                    "content/structure contains area search term but no raw farm-area "
                    "source schema",
                )
        output.append(row)
    return sorted(output, key=lambda row: row["file_path"])


def _read_tabular_header(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return next(
                csv.reader(stream, delimiter="\t" if path.suffix.lower() == ".tsv" else ","), []
            )
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _read_tabular(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(
                stream, delimiter="\t" if path.suffix.lower() == ".tsv" else ","
            )
            return list(reader.fieldnames or []), list(reader)
    except (OSError, UnicodeDecodeError, csv.Error):
        return [], []


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


def review_required_count(category_counts: dict[str, int]) -> int:
    """Count both legacy review buckets plus explicit R2 unresolved rows."""
    return sum(
        category_counts.get(category, 0)
        for category in ("EXCLUDED_OTHER", "UNCLASSIFIED_CANDIDATE", "REVIEW_REQUIRED")
    )


def reconcile_prior_review_cohort(
    prior_discovery_manifest: dict[str, Any],
    current_classified_rows: list[dict[str, Any]],
    historical_prior_blobs: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Map each R1 review item to current bytes and a deterministic R2 disposition."""
    historical_prior_blobs = historical_prior_blobs or {}
    review_categories = {"EXCLUDED_OTHER", "UNCLASSIFIED_CANDIDATE"}
    prior_rows = [
        row
        for row in prior_discovery_manifest.get("files", [])
        if row.get("source_category") in review_categories
    ]
    current_by_path = {row["file_path"]: row for row in current_classified_rows}
    current_by_digest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in current_classified_rows:
        current_by_digest[row.get("file_sha256", "")].append(row)

    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for prior in sorted(
        prior_rows, key=lambda row: (row.get("file_path", ""), row.get("file_sha256", ""))
    ):
        prior_path = str(prior.get("file_path", ""))
        prior_hash = str(prior.get("file_sha256", ""))
        same_path = current_by_path.get(prior_path)
        exact = same_path if same_path and same_path.get("file_sha256") == prior_hash else None
        redirect_rows = current_by_digest.get(prior_hash, [])
        current = (
            exact
            or same_path
            or (
                sorted(redirect_rows, key=lambda row: row["file_path"])[0]
                if redirect_rows
                else None
            )
        )
        historical = historical_prior_blobs.get(prior_path, {})
        historical_verified = historical.get("sha256") == prior_hash
        historical_rule_matches_current = current is not None and historical.get(
            "classification_rule_id"
        ) == current.get("classification_rule_id")
        if exact:
            status = "EXACT_PATH_AND_HASH_RECLASSIFIED"
            reason = "R1 candidate path and bytes match; current R2 rule supplies the disposition"
        elif same_path:
            if historical_verified and historical_rule_matches_current:
                status = "SAME_PATH_BYTES_CHANGED_HISTORICAL_BLOB_VERIFIED"
                reason = (
                    "R1 bytes were verified from the pinned Git history and classified from "
                    "their historical JSON evidence structure; current bytes are independently "
                    "classified by the same deterministic R2 rule"
                )
            else:
                status = "PRIOR_REVIEW_ITEM_UNRESOLVED"
                reason = (
                    "same path has changed bytes but historical R1 bytes lack verified "
                    "classification"
                )
        elif current and redirect_rows:
            status = "BYTE_IDENTICAL_PATH_REDIRECT_RECLASSIFIED"
            reason = "R1 candidate bytes are present at a different current path and are classified"
        else:
            status = "PRIOR_REVIEW_ITEM_UNRESOLVED"
            reason = "no current candidate with the same path or source hash was found"

        excluded_review_categories = review_categories | {
            "REVIEW_REQUIRED",
            "UNCLASSIFIED_CANDIDATE",
            "EXCLUDED_OTHER",
        }
        resolved = current is not None and current.get("source_category", "") not in (
            excluded_review_categories
        )
        if not resolved:
            status = "PRIOR_REVIEW_ITEM_UNRESOLVED"
            reason = "no deterministic non-review R2 classification is available"
        counts[status] += 1
        output.append(
            {
                "r1_source_category": str(prior.get("source_category", "")),
                "r1_source_path": prior_path,
                "r1_source_sha256": prior_hash,
                "current_source_path": str(current.get("file_path", "")) if current else "",
                "current_source_sha256": str(current.get("file_sha256", "")) if current else "",
                "current_source_category": str(current.get("source_category", ""))
                if current
                else "",
                "current_classification_rule_id": str(current.get("classification_rule_id", ""))
                if current
                else "",
                "current_classification_reason": str(current.get("classification_reason", ""))
                if current
                else "",
                "current_classification_evidence": str(current.get("classification_evidence", ""))
                if current
                else "",
                "current_scan_status": str(current.get("scan_status", "")) if current else "",
                "r1_historical_sha256_verified": historical_verified,
                "r1_historical_git_revision": str(historical.get("git_revision", "")),
                "r1_historical_classification_rule_id": str(
                    historical.get("classification_rule_id", "")
                ),
                "r1_historical_classification_reason": str(
                    historical.get("classification_reason", "")
                ),
                "r1_historical_classification_evidence": str(
                    historical.get("classification_evidence", "")
                ),
                "reconciliation_status": status,
                "reconciliation_reason": reason,
            }
        )
    stats = {
        "prior_review_cohort_count": len(prior_rows),
        "exact_path_hash_reclassified_count": counts["EXACT_PATH_AND_HASH_RECLASSIFIED"],
        "same_path_bytes_changed_reclassified_count": counts[
            "SAME_PATH_BYTES_CHANGED_HISTORICAL_BLOB_VERIFIED"
        ],
        "historical_prior_git_blob_verified_count": sum(
            bool(row["r1_historical_sha256_verified"]) for row in output
        ),
        "byte_identical_path_redirect_reclassified_count": counts[
            "BYTE_IDENTICAL_PATH_REDIRECT_RECLASSIFIED"
        ],
        "unresolved_count": counts["PRIOR_REVIEW_ITEM_UNRESOLVED"],
    }
    return output, stats


def verify_historical_prior_review_blobs(
    *,
    repo_root: Path,
    prior_discovery_manifest: dict[str, Any],
    specifications: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Verify changed prior-candidate bytes against pinned Git objects and content."""
    review_rows = [
        row
        for row in prior_discovery_manifest.get("files", [])
        if row.get("source_category") in {"EXCLUDED_OTHER", "UNCLASSIFIED_CANDIDATE"}
    ]
    rows_by_identity = {
        (str(row.get("file_path", "")), str(row.get("file_sha256", ""))): row for row in review_rows
    }
    verified: dict[str, dict[str, Any]] = {}
    for specification in sorted(specifications, key=lambda row: row["repo_relative_path"]):
        relative_path = Path(specification["repo_relative_path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise InventoryError("PRIOR_REVIEW_GIT_PATH_NOT_REPOSITORY_RELATIVE")
        path = _normalized_path(repo_root / relative_path)
        expected_sha256 = specification["expected_sha256"]
        prior_row = rows_by_identity.get((path, expected_sha256))
        if prior_row is None:
            raise InventoryError(f"PRIOR_REVIEW_GIT_ROW_NOT_IN_PINNED_MANIFEST:{path}")
        revision = specification["git_revision"]
        git_path = f"{revision}:{relative_path.as_posix()}"
        try:
            blob_result = subprocess.run(
                ["git", "show", git_path],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise InventoryError(f"PRIOR_REVIEW_GIT_BLOB_UNAVAILABLE:{path}") from error
        actual_sha256 = sha256_bytes(blob_result.stdout)
        if actual_sha256 != expected_sha256:
            raise InventoryError(f"PRIOR_REVIEW_GIT_BLOB_HASH_MISMATCH:{path}:{actual_sha256}")
        try:
            payload = json.loads(blob_result.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InventoryError(f"PRIOR_REVIEW_GIT_BLOB_NOT_JSON_EVIDENCE:{path}") from error
        expected_task_id = specification["expected_task_id"]
        required_keys = set(specification.get("required_top_level_keys", []))
        if payload.get("task_id") != expected_task_id or not required_keys.issubset(payload):
            raise InventoryError(f"PRIOR_REVIEW_GIT_BLOB_EVIDENCE_SCHEMA_MISMATCH:{path}")
        rule_id = specification["classification_rule_id"]
        registry_rule = next(
            (rule for rule in CLASSIFICATION_RULE_REGISTRY if rule["rule_id"] == rule_id), None
        )
        if registry_rule is None or registry_rule["category"] != "EXCLUDED_GENERATED_DERIVATIVE":
            raise InventoryError(f"PRIOR_REVIEW_GIT_BLOB_RULE_INVALID:{rule_id}")
        verified[path] = {
            "sha256": actual_sha256,
            "git_revision": revision,
            "classification_rule_id": rule_id,
            "classification_reason": "HISTORICAL_GENERATED_EVIDENCE_JSON",
            "classification_evidence": (
                f"verified Git blob SHA256={actual_sha256}; JSON task_id={expected_task_id}; "
                f"required evidence keys={','.join(sorted(required_keys))}"
            ),
        }
    return verified


def resolve_structured_scan_errors(
    scan_errors: list[str], classified_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], list[str]]:
    """Close a decoder error only when independent path/schema evidence excludes the file."""
    by_path = {row["file_path"]: row for row in classified_rows}
    resolved: list[dict[str, str]] = []
    unresolved: list[str] = []
    prefix = "STRUCTURED_SCAN_UNAVAILABLE:"
    delimiter = ":STRUCTURE_SCAN_UNAVAILABLE:"
    for error in scan_errors:
        if not error.startswith(prefix):
            unresolved.append(error)
            continue
        payload = error.removeprefix(prefix)
        source_path, separator, status = payload.partition(delimiter)
        candidate = by_path.get(source_path) if separator else None
        if candidate and candidate["classification_rule_id"] in {"R2-006", "R2-010", "R2-014"}:
            resolved.append(
                {
                    "file_path": source_path,
                    "scan_status": status,
                    "classification_rule_id": candidate["classification_rule_id"],
                    "classification_reason": candidate["classification_reason"],
                    "resolution_basis": candidate["classification_evidence"],
                }
            )
        else:
            unresolved.append(error)
    return resolved, unresolved


def compare_canonical_records(
    old_raw_rows: list[dict[str, str]], new_raw_rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Apply the same canonical key/dedup/sort policy to both raw inventories."""
    old_rows = deduplicate_source_records(old_raw_rows)
    new_rows = deduplicate_source_records(new_raw_rows)
    differences = record_differences(old_rows, new_rows)
    return {
        "old_raw_record_count": len(old_raw_rows),
        "old_canonical_record_count": len(old_rows),
        "old_duplicate_rows_removed": len(old_raw_rows) - len(old_rows),
        "new_raw_record_count": len(new_raw_rows),
        "new_canonical_record_count": len(new_rows),
        "new_duplicate_rows_removed": len(new_raw_rows) - len(new_rows),
        "canonical_records_only_in_old": sum(
            row["diff_status"] == "OLD_RECORD_NOT_REPRODUCED" for row in differences
        ),
        "canonical_records_only_in_new": sum(
            row["diff_status"] == "NEW_RECORD_NOT_IN_OLD" for row in differences
        ),
        "canonical_record_parity": not differences,
        "old_canonical_rows": old_rows,
        "new_canonical_rows": new_rows,
        "canonical_record_diff": differences,
    }


def duplicate_business_fields_consistent(rows: list[dict[str, str]]) -> bool:
    """Prove duplicate removal never merges conflicting business values."""
    return all(row["business_field_parity"] for row in duplicate_business_field_parity(rows))


def duplicate_business_field_parity(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Return a row-level audit for every duplicate group removed by the canonical key."""
    grouped: dict[bytes, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_record_key(row)].append(row)
    result: list[dict[str, Any]] = []
    for duplicates in grouped.values():
        if len(duplicates) < 2:
            continue
        differing_fields = [
            field
            for field in BUSINESS_DUPLICATE_FIELDS
            if len({row.get(field, "") for row in duplicates}) > 1
        ]
        result.append(
            {
                "logical_record_key_sha256": sha256_bytes(_record_key(duplicates[0])),
                "source_hash": duplicates[0].get("source_hash", ""),
                "duplicate_row_count": len(duplicates),
                "duplicate_rows_removed": len(duplicates) - 1,
                "business_field_parity": not differing_fields,
                "differing_business_fields": "|".join(differing_fields),
            }
        )
    return sorted(result, key=lambda row: row["logical_record_key_sha256"])


def reconcile_old_source_paths(
    *,
    old_source_paths: set[str],
    old_path_to_digest: dict[str, str],
    discovered_rows: list[dict[str, Any]],
    legacy_parser_paths: set[str],
    search_roots: list[dict[str, Any]],
    prior_discovery_paths: set[str],
    prior_search_keywords: list[str],
) -> list[dict[str, Any]]:
    """Retain path-level history while detecting byte-identical relocation."""
    by_path = {row["file_path"]: row for row in discovered_rows}
    by_digest: dict[str, list[str]] = defaultdict(list)
    for row in discovered_rows:
        by_digest[row.get("file_sha256", "")].append(row["file_path"])
    normalized_roots = [Path(root["path"]) for root in search_roots]
    output: list[dict[str, Any]] = []
    for old_path in sorted(old_source_paths):
        path = Path(old_path)
        exists = path.is_file()
        normalized = _normalized_path(path)
        frozen_digest = old_path_to_digest.get(normalized, "")
        digest = sha256_file(path) if exists else frozen_digest
        candidate = by_path.get(normalized)
        content, scan_status = (
            searchable_text(path) if exists else ("", "OLD_PATH_NO_LONGER_EXISTS")
        )
        name_hits = _matches_keywords(path.name, prior_search_keywords)
        content_hits = _matches_keywords(content, prior_search_keywords)
        covered = any(_path_is_within(path, root) for root in normalized_roots)
        redirects = sorted(set(by_digest.get(digest, []))) if digest else []
        redirect = next((item for item in redirects if item != normalized), "")
        if exists and frozen_digest and digest != frozen_digest:
            path_status = "OLD_PATH_HASH_MISMATCH"
            why = (
                "current file bytes do not match the source SHA256 recorded "
                "in the frozen old inventory"
            )
            policy = "SOURCE_HASH_CONFLICT_REVIEW_REQUIRED"
        elif candidate:
            path_status = "OLD_PATH_REDISCOVERED"
            if normalized not in prior_discovery_paths and not name_hits and not content_hits:
                why = (
                    "R1 scan found neither filename nor content keyword; R2 workbook "
                    "structure scan discovered the header"
                )
            elif normalized not in prior_discovery_paths:
                why = (
                    "R1 configured extension/keyword scan missed the path; "
                    "R2 generalized discovery included it"
                )
            else:
                why = "path is present in both the pinned R1 scan and current discovery"
            policy = (
                "STRUCTURAL_AREA_SOURCE_DETECTION"
                if candidate.get("candidate_reason") == "STRUCTURAL_AREA_SCHEMA"
                or (normalized not in prior_discovery_paths and not name_hits and not content_hits)
                else "CURRENT_DISCOVERY_RULE"
            )
        elif redirect:
            path_status = "OLD_PATH_NOT_REDISCOVERED_BUT_CONTENT_PRESENT"
            why = (
                "old path absent from candidate paths but identical SHA256 exists "
                "at another discovered path"
            )
            policy = "RECORD_BYTE_IDENTICAL_PATH_REDIRECT"
        elif not exists:
            path_status = "OLD_PATH_NO_LONGER_EXISTS"
            why = "old source path no longer exists and no identical discovered SHA256 was found"
            policy = "SOURCE_RECOVERY_REQUIRED"
        elif not covered:
            path_status = "PATH_OUTSIDE_DECLARED_ROOT"
            why = "old path is not contained by any configured search root"
            policy = "ROOT_COVERAGE_REQUIRED"
        elif scan_status == "READ_ERROR" or "UNAVAILABLE" in scan_status:
            path_status = "OLD_PATH_CONTENT_SCAN_FAILED"
            why = scan_status
            policy = "CONTENT_EXTRACTION_REQUIRED"
        else:
            path_status = "OLD_PATH_LOGICAL_SOURCE_GAP"
            why = (
                "path exists under a searched root but neither keyword nor structural "
                "rules found it"
            )
            policy = "GENERALIZED_DISCOVERY_RULE_REQUIRED"
        output.append(
            {
                "old_source_path": normalized,
                "file_sha256": digest,
                "frozen_source_sha256": frozen_digest,
                "file_exists_now": exists,
                "search_root_covered": covered,
                "file_extension": path.suffix.lower(),
                "filename_keyword_hits": "|".join(name_hits),
                "content_keyword_hits": "|".join(content_hits),
                "prior_discovery_candidate": normalized in prior_discovery_paths,
                "scan_status": candidate.get("scan_status", scan_status)
                if candidate
                else scan_status,
                "legacy_parser_used": normalized in legacy_parser_paths,
                "rediscovered_path": normalized if candidate else redirect,
                "path_status": path_status,
                "why_not_discovered": (
                    ""
                    if path_status == "OLD_PATH_REDISCOVERED"
                    and normalized in prior_discovery_paths
                    else why
                ),
                "required_policy_change": policy,
            }
        )
    return output


def evaluate_completeness(
    *,
    old_source_paths: set[str],
    discovered_candidate_paths: set[str],
    rebuilt_source_paths: set[str],
    review_required_candidate_count: int,
    scan_errors: list[str],
    canonical_record_parity: bool = True,
    new_area_source_found: bool = False,
    prior_review_cohort_unreconciled_count: int = 0,
) -> dict[str, Any]:
    old_not_found = sorted(old_source_paths - discovered_candidate_paths)
    rebuilt_not_discovered = sorted(rebuilt_source_paths - discovered_candidate_paths)
    new_sources = sorted(rebuilt_source_paths - old_source_paths)
    complete = not (
        old_not_found
        or rebuilt_not_discovered
        or new_sources
        or review_required_candidate_count
        or scan_errors
        or not canonical_record_parity
        or new_area_source_found
        or prior_review_cohort_unreconciled_count
    )
    return {
        "completeness_proven": complete,
        "old_files_not_rediscovered": old_not_found,
        "rebuilt_files_not_discovered": rebuilt_not_discovered,
        "new_source_files_not_in_old": new_sources,
        "review_required_candidate_count": review_required_candidate_count,
        "canonical_record_parity": canonical_record_parity,
        "new_area_source_found": new_area_source_found,
        "prior_review_cohort_unreconciled_count": prior_review_cohort_unreconciled_count,
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
    """Close source-inventory provenance gaps without promoting area authority."""
    if output_dir.exists():
        raise InventoryError(f"OUTPUT_DIR_ALREADY_EXISTS:{output_dir}")
    old_inventory = old_inventory_path or Path(config["old_inventory_path"])
    old_manifest = old_manifest_path or Path(config["old_manifest_path"])
    builder = legacy_builder_path or Path(config["legacy_builder_path"])
    prior_discovery = Path(config.get("prior_discovery_manifest_path", R1_DISCOVERY_MANIFEST_PATH))
    for path, expected, label in (
        (old_inventory, OLD_SOURCE_INVENTORY_SHA256, "OLD_INVENTORY"),
        (old_manifest, OLD_SOURCE_MANIFEST_SHA256, "OLD_MANIFEST"),
        (builder, LEGACY_BUILDER_SHA256, "LEGACY_BUILDER"),
        (
            prior_discovery,
            config.get("expected_prior_discovery_manifest_sha256", R1_DISCOVERY_MANIFEST_SHA256),
            "R1_DISCOVERY_MANIFEST",
        ),
    ):
        if not path.is_file() or sha256_file(path) != expected:
            actual = sha256_file(path) if path.is_file() else "MISSING"
            raise InventoryError(f"PINNED_INPUT_MISMATCH:{label}:{actual}")
    with old_inventory.open(encoding="utf-8-sig", newline="") as stream:
        old_rows = list(csv.DictReader(stream))
    old_payload = json.loads(old_manifest.read_text(encoding="utf-8"))
    prior_discovery_payload = json.loads(prior_discovery.read_text(encoding="utf-8"))
    prior_counts = prior_discovery_payload.get("candidate_file_classification_counts", {})
    excluded_other_before = int(prior_counts.get("EXCLUDED_OTHER", 0))
    unclassified_before = int(prior_counts.get("UNCLASSIFIED_CANDIDATE", 0))
    review_required_before = review_required_count(
        {"EXCLUDED_OTHER": excluded_other_before, "UNCLASSIFIED_CANDIDATE": unclassified_before}
    )
    prior_review_rows = [
        row
        for row in prior_discovery_payload.get("files", [])
        if row.get("source_category") in {"EXCLUDED_OTHER", "UNCLASSIFIED_CANDIDATE"}
    ]
    if (excluded_other_before, unclassified_before, review_required_before) != (
        421,
        100,
        521,
    ) or len(prior_review_rows) != 521:
        raise InventoryError(
            "PINNED_R1_REVIEW_COHORT_MISMATCH:"
            f"{excluded_other_before}:{unclassified_before}:{review_required_before}:"
            f"rows={len(prior_review_rows)}"
        )
    historical_prior_blobs = verify_historical_prior_review_blobs(
        repo_root=repo_root,
        prior_discovery_manifest=prior_discovery_payload,
        specifications=config.get("prior_review_git_blob_provenance", []),
    )
    old_exclusions = {
        _normalized_path(Path(row["path"])): row["kind"]
        for row in old_payload.get("excluded_sources", [])
    }

    roots, declared_roots = resolve_search_roots(config, repo_root)
    ignored_repository_relative_paths = sorted(
        config.get("ignored_repository_relative_file_paths", [])
    )
    ignored_file_paths: set[str] = set()
    for relative_path_value in ignored_repository_relative_paths:
        relative_path = Path(relative_path_value)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise InventoryError("IGNORED_FILE_PATH_NOT_REPOSITORY_RELATIVE")
        ignored_file_paths.add(_normalized_path(repo_root / relative_path))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    file_rows, enumerated_file_count, enumeration_scan_errors = enumerate_files(
        roots,
        set(config["ignored_directory_names"]),
        output_dir,
        tuple(config.get("ignored_directory_name_prefixes", [])),
        ignored_file_paths,
    )
    root_type_by_id = {spec["root_id"]: spec["root_type"] for spec in config["search_roots"]}
    for row in file_rows:
        row["search_root_types"] = sorted(
            {
                root_type_by_id[root_id]
                for root_id in row["search_roots"]
                if root_id in root_type_by_id
            }
        )
    structural_findings, structural_scan_errors = inspect_structured_sources(file_rows)
    candidates = discover_area_candidates(
        file_rows,
        {extension.lower() for extension in config["file_extensions_scanned"]},
        list(config["search_keywords"]),
        structural_findings,
    )

    with tempfile.TemporaryDirectory(prefix="v08-area-inventory-legacy-replay-") as temporary:
        replay_dir = Path(temporary) / "legacy-output"
        replay_dir.mkdir(mode=0o700)
        parsed_rows = run_frozen_legacy_builder(builder, LEGACY_BUILDER_SHA256, replay_dir)
    # Normalize both raw inputs before applying the same key, ordering and dedup policy.
    for row in old_rows:
        row["source_file"] = _normalized_path(Path(row["source_file"]))
    for row in parsed_rows:
        row["source_file"] = _normalized_path(Path(row["source_file"]))
    old_paths = {row["source_file"] for row in old_rows}
    parser_paths = {row["source_file"] for row in parsed_rows}
    canonical = compare_canonical_records(old_rows, parsed_rows)
    if not duplicate_business_fields_consistent(
        old_rows
    ) or not duplicate_business_fields_consistent(parsed_rows):
        raise InventoryError("DUPLICATE_BUSINESS_FIELD_CONFLICT")
    old_canonical_rows = canonical["old_canonical_rows"]
    new_canonical_rows = canonical["new_canonical_rows"]
    old_logical_hashes = {row.get("source_hash", "") for row in old_rows}
    new_logical_hashes = {row.get("source_hash", "") for row in parsed_rows}
    old_hashes = {row for row in old_logical_hashes if row}
    parser_hashes = {row for row in new_logical_hashes if row}
    discovered_paths = {row["file_path"] for row in candidates}
    classified = classify_candidates(candidates, parser_paths, old_paths, old_exclusions)
    category_counts = dict(sorted(Counter(row["source_category"] for row in classified).items()))
    unsupported_candidate_count = category_counts.get("EXCLUDED_UNSUPPORTED_FORMAT", 0)
    review_after = review_required_count(category_counts)
    prior_review_reconciliation, prior_review_reconciliation_stats = reconcile_prior_review_cohort(
        prior_discovery_payload, classified, historical_prior_blobs
    )
    if len(prior_review_reconciliation) != review_required_before:
        raise InventoryError("PRIOR_REVIEW_COHORT_RECONCILIATION_ROW_COUNT_MISMATCH")
    prior_review_unreconciled_count = prior_review_reconciliation_stats["unresolved_count"]
    (
        resolved_structured_scan_exceptions,
        unresolved_structural_scan_errors,
    ) = resolve_structured_scan_errors(structural_scan_errors, classified)
    scan_errors = [*enumeration_scan_errors, *unresolved_structural_scan_errors]
    discovered_hashes = {row["file_sha256"] for row in classified if row.get("file_sha256")}
    logical_gap_after = len(old_hashes - discovered_hashes)
    new_logical_sources = sorted(parser_hashes - old_hashes)
    new_historical_area_candidates = [
        row
        for row in classified
        if row["classification_reason"] == "POTENTIAL_FARM_AREA_SOURCE_NEEDS_PROVENANCE_REVIEW"
    ]
    new_source_candidates = [
        row
        for row in classified
        if row["included_in_inventory"] and row["file_path"] not in old_paths
    ]
    legacy_paths = {_normalized_path(Path(row["source_file"])) for row in parsed_rows}
    old_path_reconciliation = reconcile_old_source_paths(
        old_source_paths=old_paths,
        old_path_to_digest={
            path: next(
                (row.get("source_hash", "") for row in old_rows if row["source_file"] == path),
                "",
            )
            for path in old_paths
        },
        discovered_rows=classified,
        legacy_parser_paths=legacy_paths,
        search_roots=roots,
        prior_discovery_paths={
            _normalized_path(Path(row["file_path"]))
            for row in prior_discovery_payload.get("files", [])
            if row.get("file_path")
        },
        prior_search_keywords=list(prior_discovery_payload.get("search_keywords", [])),
    )
    old_path_gaps_after = sum(
        row["path_status"]
        in {
            "OLD_PATH_LOGICAL_SOURCE_GAP",
            "OLD_PATH_NO_LONGER_EXISTS",
            "PATH_OUTSIDE_DECLARED_ROOT",
            "OLD_PATH_CONTENT_SCAN_FAILED",
            "OLD_PATH_HASH_MISMATCH",
        }
        for row in old_path_reconciliation
    )
    old_path_hash_mismatch_count = sum(
        row["path_status"] == "OLD_PATH_HASH_MISMATCH" for row in old_path_reconciliation
    )
    old_path_hash_match_count = sum(
        row["file_exists_now"]
        and row["frozen_source_sha256"]
        and row["file_sha256"] == row["frozen_source_sha256"]
        for row in old_path_reconciliation
    )
    old_paths_absent_from_prior_discovery_count = sum(
        not row["prior_discovery_candidate"] for row in old_path_reconciliation
    )
    record_diff = canonical["canonical_record_diff"]
    record_inventory_exact_parity = canonical["canonical_record_parity"]
    new_source_found = bool(
        new_source_candidates or new_historical_area_candidates or new_logical_sources
    )
    duplicates_consistent = duplicate_business_fields_consistent(
        old_rows
    ) and duplicate_business_fields_consistent(parsed_rows)
    old_duplicate_parity_rows = duplicate_business_field_parity(old_rows)
    new_duplicate_parity_rows = duplicate_business_field_parity(parsed_rows)
    completeness = evaluate_completeness(
        old_source_paths=old_paths,
        discovered_candidate_paths=discovered_paths,
        rebuilt_source_paths=parser_paths,
        review_required_candidate_count=review_after,
        scan_errors=scan_errors,
        canonical_record_parity=record_inventory_exact_parity and duplicates_consistent,
        new_area_source_found=new_source_found,
        prior_review_cohort_unreconciled_count=prior_review_unreconciled_count,
    )
    completeness_proven = (
        completeness["completeness_proven"]
        and old_path_gaps_after == 0
        and logical_gap_after == 0
        and not new_logical_sources
    )
    completeness["completeness_proven"] = completeness_proven
    recovery_unchanged = record_inventory_exact_parity and not new_source_found

    output_dir.mkdir(mode=0o700)
    output_dir.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    record_fields = tuple(parsed_rows[0].keys()) if parsed_rows else ()
    _write_csv(output_dir / "area-source-file-inventory-r2.csv", classified, FILE_FIELDS)
    _write_csv(output_dir / "new-raw-source-record-inventory-r2.csv", parsed_rows, record_fields)
    _write_csv(
        output_dir / "old-canonical-record-inventory-r2.csv", old_canonical_rows, record_fields
    )
    _write_csv(
        output_dir / "new-canonical-record-inventory-r2.csv", new_canonical_rows, record_fields
    )
    _write_csv(
        output_dir / "old-path-reconciliation-r2.csv", old_path_reconciliation, OLD_PATH_FIELDS
    )
    _write_csv(
        output_dir / "prior-candidate-review-ledger.csv",
        prior_review_reconciliation,
        PRIOR_REVIEW_COHORT_FIELDS,
    )
    _write_csv(
        output_dir / "duplicate-business-field-parity-r2.csv",
        old_duplicate_parity_rows + new_duplicate_parity_rows,
        DUPLICATE_PARITY_FIELDS,
    )
    _write_csv(output_dir / "canonical-record-diff-r2.csv", record_diff, DIFF_FIELDS)
    _write_csv(output_dir / "candidate-classification-r2.csv", classified, FILE_FIELDS)
    _write_json(
        output_dir / "classification-rule-registry-r2.json", list(CLASSIFICATION_RULE_REGISTRY)
    )

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
        "ignored_directory_name_prefixes": sorted(
            config.get("ignored_directory_name_prefixes", [])
        ),
        "ignored_repository_relative_file_paths": ignored_repository_relative_paths,
        "resolved_scan_config_sha256": sha256_bytes(canonical_json_bytes(config)),
        "scan_timestamp_policy": config["scan_timestamp_policy"],
        "deterministic_ordering": "NORMALIZED_ABSOLUTE_PATH_ASCENDING; ROOTS_AND_ENTRIES_SORTED",
        "deduplication_policy": config["deduplication_policy"],
        "scan_errors": scan_errors,
        "resolved_structured_scan_exceptions": resolved_structured_scan_exceptions,
        "structural_scan_errors_before_rule_resolution": structural_scan_errors,
        "files": classified,
        "legacy_source_path_reconciliation": {
            "old_physical_source_path_count": len(old_paths),
            "old_path_gap_before": 7,
            "old_path_gap_after": old_path_gaps_after,
            "old_path_hash_match_count": old_path_hash_match_count,
            "old_path_hash_mismatch_count": old_path_hash_mismatch_count,
            "old_paths_absent_from_prior_discovery_count": (
                old_paths_absent_from_prior_discovery_count
            ),
            "old_logical_source_gap_after": logical_gap_after,
            "old_path_content_redirect_count": sum(
                row["path_status"] == "OLD_PATH_NOT_REDISCOVERED_BUT_CONTENT_PRESENT"
                for row in old_path_reconciliation
            ),
            "records": old_path_reconciliation,
        },
        "canonical_dedup_summary": {
            key: value
            for key, value in canonical.items()
            if key not in {"old_canonical_rows", "new_canonical_rows", "canonical_record_diff"}
        }
        | {
            "duplicate_business_fields_consistent": duplicates_consistent,
            "duplicate_business_field_parity_row_count": len(old_duplicate_parity_rows)
            + len(new_duplicate_parity_rows),
            "old_duplicate_key_group_summary": _duplicate_record_group_summary(old_rows),
            "new_duplicate_key_group_summary": _duplicate_record_group_summary(parsed_rows),
            "records_only_in_old": canonical["canonical_records_only_in_old"],
            "records_only_in_new": canonical["canonical_records_only_in_new"],
        },
        "review_candidate_resolution_summary": {
            "review_required_before": review_required_before,
            "excluded_other_before": excluded_other_before,
            "unclassified_candidate_before": unclassified_before,
            "excluded_other_after": category_counts.get("EXCLUDED_OTHER", 0),
            "unclassified_candidate_after": category_counts.get("UNCLASSIFIED_CANDIDATE", 0),
            "review_required_after": review_after,
            "rule_classified_candidate_count": len(classified) - review_after,
        },
        "prior_review_cohort_reconciliation": {
            **prior_review_reconciliation_stats,
            "historical_prior_blob_sha256": {
                path: row["sha256"] for path, row in sorted(historical_prior_blobs.items())
            },
            "records": prior_review_reconciliation,
        },
        "classification_rule_registry": list(CLASSIFICATION_RULE_REGISTRY),
        "completeness_proven": completeness_proven,
    }
    _write_json(output_dir / "area-source-discovery-manifest-r2.json", discovery_manifest)

    summary = {
        "task_id": TASK_ID,
        "result": (
            "PASS_INVENTORY_COMPLETENESS_PROVEN"
            if completeness_proven and not new_source_found
            else "PASS_NEW_AREA_SOURCES_FOUND_REQUIRES_S3_REBUILD"
            if new_source_found
            else "BLOCKED_INVENTORY_COMPLETENESS_NOT_PROVEN"
        ),
        "review_required_before": review_required_before,
        "excluded_other_before": excluded_other_before,
        "unclassified_candidate_before": unclassified_before,
        "excluded_other_after": category_counts.get("EXCLUDED_OTHER", 0),
        "unclassified_candidate_after": category_counts.get("UNCLASSIFIED_CANDIDATE", 0),
        "review_required_after": review_after,
        "total_review_required_candidate_count": review_after,
        "prior_review_cohort_count": prior_review_reconciliation_stats["prior_review_cohort_count"],
        "prior_review_cohort_exact_path_hash_reclassified_count": (
            prior_review_reconciliation_stats["exact_path_hash_reclassified_count"]
        ),
        "prior_review_cohort_same_path_bytes_changed_reclassified_count": (
            prior_review_reconciliation_stats["same_path_bytes_changed_reclassified_count"]
        ),
        "prior_review_cohort_byte_identical_path_redirect_reclassified_count": (
            prior_review_reconciliation_stats["byte_identical_path_redirect_reclassified_count"]
        ),
        "prior_review_cohort_historical_prior_git_blob_verified_count": (
            prior_review_reconciliation_stats["historical_prior_git_blob_verified_count"]
        ),
        "prior_review_cohort_unreconciled_count": prior_review_unreconciled_count,
        "old_source_file_count": len(old_paths),
        "new_source_file_count": len(parser_paths),
        "old_raw_record_count": len(old_rows),
        "old_canonical_record_count": len(old_canonical_rows),
        "new_raw_replay_record_count": len(parsed_rows),
        "new_canonical_record_count": len(new_canonical_rows),
        "old_duplicate_rows_removed": canonical["old_duplicate_rows_removed"],
        "new_duplicate_rows_removed": canonical["new_duplicate_rows_removed"],
        "canonical_records_only_in_old": canonical["canonical_records_only_in_old"],
        "canonical_records_only_in_new": canonical["canonical_records_only_in_new"],
        "canonical_record_parity": record_inventory_exact_parity,
        "duplicate_business_fields_consistent": duplicates_consistent,
        "duplicate_business_field_parity_row_count": len(old_duplicate_parity_rows)
        + len(new_duplicate_parity_rows),
        "old_duplicate_key_group_summary": _duplicate_record_group_summary(old_rows),
        "new_duplicate_key_group_summary": _duplicate_record_group_summary(parsed_rows),
        "resolved_structured_scan_exception_count": len(resolved_structured_scan_exceptions),
        "resolved_structured_scan_exceptions": resolved_structured_scan_exceptions,
        "enumerated_file_count": enumerated_file_count,
        "area_candidate_file_count": len(classified),
        "source_category_counts": category_counts,
        "old_files_not_rediscovered": old_path_gaps_after,
        "old_path_gap_before": 7,
        "old_path_gap_after": old_path_gaps_after,
        "old_path_hash_match_count": old_path_hash_match_count,
        "old_path_hash_mismatch_count": old_path_hash_mismatch_count,
        "old_paths_absent_from_prior_discovery_count": old_paths_absent_from_prior_discovery_count,
        "old_logical_source_gap_after": logical_gap_after,
        "old_path_content_redirect_count": sum(
            row["path_status"] == "OLD_PATH_NOT_REDISCOVERED_BUT_CONTENT_PRESENT"
            for row in old_path_reconciliation
        ),
        "new_files_not_in_old": len(new_source_candidates),
        "new_logical_source_not_in_old": len(new_logical_sources),
        "new_historical_farm_area_source_count": len(new_historical_area_candidates),
        "old_source_paths_missing_from_discovery": [
            row["old_source_path"]
            for row in old_path_reconciliation
            if row["path_status"] != "OLD_PATH_REDISCOVERED"
        ],
        "completeness_gate": completeness,
        "scan_error_count": len(scan_errors),
        "unclassified_candidate_count": category_counts.get("UNCLASSIFIED_CANDIDATE", 0),
        "unsupported_candidate_count": unsupported_candidate_count,
        "area_source_inventory_rebuild_deterministic": True,
        "source_discovery_completeness_proven": completeness_proven,
        "source_file_set_exact_parity": old_path_gaps_after == 0
        and logical_gap_after == 0
        and not new_source_candidates,
        "record_inventory_exact_parity": record_inventory_exact_parity,
        "area_source_inventory_completeness_proven": completeness_proven,
        "previous_area_inventory_incomplete": bool(
            new_source_candidates or new_historical_area_candidates or new_logical_sources
        ),
        "inventory_rebuild_found_previously_missed_sources": bool(new_source_candidates),
        "area_recovery_results_unchanged": recovery_unchanged,
        "legacy_parsed_record_count_before_deduplication": len(parsed_rows),
        "exact_duplicate_record_count_removed": canonical["new_duplicate_rows_removed"],
        "duplicate_source_sha256_group_count": len(_duplicate_groups(classified)),
        "duplicate_source_file_copy_count": sum(
            group["duplicate_path_count"] for group in _duplicate_groups(classified)
        ),
        "resolved_scan_config_sha256": sha256_bytes(canonical_json_bytes(config)),
        "discovery_manifest_sha256": sha256_file(
            output_dir / "area-source-discovery-manifest-r2.json"
        ),
        "canonical_record_diff_sha256": sha256_file(output_dir / "canonical-record-diff-r2.csv"),
        "classification_registry_sha256": sha256_file(
            output_dir / "classification-rule-registry-r2.json"
        ),
        "s3_recovery_rerun_executed": False,
        "existing_area_authority_modified": False,
        "model_training_executed": False,
        "model_refit_executed": False,
        "backtest_executed": False,
        "forecast_replay_executed": False,
        "ready_authorized": False,
        "merge_authorized": False,
    }
    _write_json(output_dir / "inventory-completeness-summary-r2.json", summary)
    output_hashes = {
        path.name: sha256_file(path) for path in sorted(output_dir.iterdir()) if path.is_file()
    }
    artifact_manifest = {
        "task_id": TASK_ID,
        "resolved_scan_config_sha256": sha256_bytes(canonical_json_bytes(config)),
        "output_file_hashes": output_hashes,
        "summary_hash": sha256_file(output_dir / "inventory-completeness-summary-r2.json"),
        "source_inventory_builder_sha256": sha256_file(Path(__file__)),
        "legacy_parser_sha256": LEGACY_BUILDER_SHA256,
        "old_inventory_sha256": OLD_SOURCE_INVENTORY_SHA256,
        "old_manifest_sha256": OLD_SOURCE_MANIFEST_SHA256,
        "prior_discovery_manifest_sha256": R1_DISCOVERY_MANIFEST_SHA256,
    }
    _write_json(output_dir / "artifact-manifest.json", artifact_manifest)
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


def _duplicate_record_group_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Summarize deduped logical rows by source file hash, without source values."""
    grouped: dict[bytes, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_record_key(row)].append(row)
    duplicate_groups_by_source_hash: Counter[str] = Counter()
    removed_rows_by_source_hash: Counter[str] = Counter()
    for duplicates in grouped.values():
        if len(duplicates) < 2:
            continue
        source_hash = duplicates[0].get("source_hash", "")
        duplicate_groups_by_source_hash[source_hash] += 1
        removed_rows_by_source_hash[source_hash] += len(duplicates) - 1
    return {
        "duplicate_group_count": sum(duplicate_groups_by_source_hash.values()),
        "duplicate_rows_removed": sum(removed_rows_by_source_hash.values()),
        "duplicate_groups_by_source_hash": [
            {
                "source_hash": source_hash,
                "duplicate_group_count": duplicate_groups_by_source_hash[source_hash],
                "duplicate_rows_removed": removed_rows_by_source_hash[source_hash],
            }
            for source_hash in sorted(duplicate_groups_by_source_hash)
        ],
    }


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
    base_config_path = config.pop("base_config_path", None)
    if base_config_path:
        base_config = json.loads(Path(base_config_path).read_text(encoding="utf-8"))
        base_config.update(config)
        config = base_config
    output_dir = args.output_dir or Path(config["private_output_path"])
    summary = build_private_inventory(
        config=config,
        repo_root=args.repo_root.resolve(),
        output_dir=output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
