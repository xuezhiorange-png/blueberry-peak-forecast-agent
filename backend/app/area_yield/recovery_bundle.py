"""Directory custody with relative inventory, exclusive publication and E2 reuse.

Integrity hashes are not external signatures or protection against administrators.
No source discovery, training, actual import or permission promotion is reachable.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from backend.app.area_yield import artifact_registration as e2
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield.data import digest
from backend.app.area_yield.research_records import file_hash, read

Record = dict[str, Any]
SCHEMA = "V0_12_E3_DIRECTORY_CUSTODY_R1"
CANDIDATE = "artifacts/candidate-artifact.json"
BASELINE = "artifacts/baseline-artifact.json"
RECEIPT = "provenance/run-receipt.json"
SEAL = "provenance/prediction-seal.json"
CONTRACT = "provenance/execution-contract.json"
PUBLIC = "public/frozen-evidence.json"
ROLES = {
    CANDIDATE: "FROZEN_CANDIDATE",
    BASELINE: "FROZEN_COMPARATOR",
    RECEIPT: "HISTORICAL_RECEIPT",
    SEAL: "HISTORICAL_SEAL",
    CONTRACT: "FROZEN_EXECUTION_CONTRACT",
    PUBLIC: "PUBLIC_FROZEN_AUTHORITY",
    "README.txt": "CUSTODY_INSTRUCTIONS",
}
README = (
    "V0.12-E3 private local custody bundle. Keep access controlled.\n"
    "Use the compatible repository's v0-12-research verify-bundle/restore-bundle.\n"
    "Re-register restored artifacts; never copy a machine-specific runtime registry.\n"
    "TEST_ONLY engineering, not scientific validation or real issuance authority.\n"
    "No raw historical input or holdout rows are included.\n"
)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _relative(value: str) -> None:
    require(isinstance(value, str) and bool(value), "RELATIVE_PATH_REQUIRED")
    p = PurePosixPath(value)
    require(
        not p.is_absolute()
        and p.as_posix() == value
        and all(x not in {".", ".."} for x in p.parts)
        and "\\" not in value
        and ":" not in value,
        "UNSAFE_RELATIVE_PATH",
    )


def _portable(value: Any) -> None:
    if isinstance(value, dict):
        require(
            not any(
                str(k).lower()
                in {
                    "password",
                    "token",
                    "secret",
                    "ssh_private_key",
                    "credentials",
                    "rows",
                    "actual_rows",
                    "training_rows",
                }
                for k in value
            ),
            "FORBIDDEN_BUNDLE_PAYLOAD",
        )
        for k, v in value.items():
            _portable(k)
            _portable(v)
    elif isinstance(value, list):
        for v in value:
            _portable(v)
    elif isinstance(value, str):
        require(
            not value.startswith(("/", "~", "\\"))
            and not re.match(r"^[A-Za-z]:[\\/]", value)
            and "file://" not in value
            and "/Users/" not in value
            and "/private/tmp/" not in value,
            "NONPORTABLE_ABSOLUTE_REFERENCE",
        )


def _pairs(items: list[tuple[str, Any]]) -> Record:
    result: Record = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json(path: Path) -> Record:
    require(path.is_file() and not path.is_symlink(), "MISSING_OR_SYMLINK_FILE")
    require(path.stat().st_size <= 10_000_000, "BUNDLE_FILE_TOO_LARGE")
    result = json.loads(path.read_text(), object_pairs_hook=_pairs)
    if not isinstance(result, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    _portable(result)
    return result


def _write(path: Path, value: Record) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    path.chmod(0o600)


def _destination(path: Path) -> Path:
    if path.exists() or path.is_symlink():
        raise FileExistsError("RECOVERY_OUTPUT_ALREADY_EXISTS")
    require(path.parent.is_dir(), "EXISTING_OUTPUT_PARENT_REQUIRED")
    return path.parent.resolve() / path.name


def _publish(staged: Path, output: Path) -> None:
    """Exclusive atomic directory rename on macOS/Linux, never replace a target."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        call = library.renamex_np
        call.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = call(os.fsencode(staged), os.fsencode(output), 4)  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        call = library.renameat2
        call.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        result = call(-100, os.fsencode(staged), -100, os.fsencode(output), 1)  # RENAME_NOREPLACE
    else:
        raise OSError("EXCLUSIVE_DIRECTORY_RENAME_UNSUPPORTED")
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError("RECOVERY_OUTPUT_ALREADY_EXISTS")
        raise OSError(code, "ATOMIC_PUBLICATION_FAILED")


def _durable(root: Path) -> None:
    for p in root.rglob("*"):
        if p.is_file():
            with p.open("rb") as stream:
                os.fsync(stream.fileno())
    for p in [*sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True), root]:
        descriptor = os.open(p, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _inventory(root: Path) -> list[Record]:
    return [
        {
            "relative_path": p,
            "sha256": file_hash(root / p),
            "size_bytes": (root / p).stat().st_size,
            "role": ROLES[p],
        }
        for p in sorted(ROLES)
    ]


def _metadata(entries: list[Record], evidence: Record) -> Record:
    return {
        "bundle_schema": SCHEMA,
        "source_execution_id": e2.EXECUTION,
        "candidate_relative_path": CANDIDATE,
        "candidate_file_sha256": evidence["candidate_file_hash"],
        "candidate_artifact_hash": evidence["candidate_content_hash"],
        "comparator_relative_path": BASELINE,
        "comparator_file_sha256": evidence["comparator_file_hash"],
        "comparator_artifact_hash": evidence["comparator_content_hash"],
        "training_seasons": evidence["training_seasons"],
        "training_sample_count": evidence["training_sample_count"],
        "training_area_range_mu": evidence["training_area_range_mu"],
        "historical_code_sha": entries[0]["code_sha"],
        "run_receipt_relative_path": RECEIPT,
        "prediction_seal_relative_path": SEAL,
        "execution_contract_relative_path": CONTRACT,
        "public_evidence_relative_path": PUBLIC,
        "public_evidence_sha256": e2.PUBLIC_FILE_HASH,
        "role_mapping": evidence["role_mapping_type"],
    }


def _provenance(root: Path) -> None:
    receipt, seal, contract = (_json(root / p) for p in (RECEIPT, SEAL, CONTRACT))
    public = _json(root / PUBLIC)
    config = (
        Path(__file__).resolve().parents[3] / "configs/next_area_size_experiment_20261002_r1.json"
    )
    require(
        file_hash(config) == e2.CONFIG_FILE_HASH and contract == read(config),
        "FROZEN_CONTRACT_CONTENT_MISMATCH",
    )
    for key in (
        "artifact_file_hashes",
        "train_seasons",
        "test_season",
        "train_sample_count",
        "test_sample_count",
        "created_at",
    ):
        require(
            receipt["fold"][key] == public["fold"][key] == seal[key], "BUNDLE_PROVENANCE_MISMATCH"
        )
    require(
        contract["execution_id"] == e2.EXECUTION
        and receipt["stable_gain"] is False
        and receipt["scientific_result"] == "RESEARCH_CANDIDATE_NO_STABLE_GAIN",
        "BUNDLE_RESEARCH_SCOPE_MISMATCH",
    )


def verify(root: Path) -> Record:
    require(root.is_dir() and not root.is_symlink(), "BUNDLE_ROOT_REQUIRED_NO_SYMLINK")
    expected_files = set(ROLES) | {"manifest.json"}
    allowed_dirs = {str(PurePosixPath(p).parent) for p in ROLES if "/" in p}
    found = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "BUNDLE_SYMLINK_REJECTED")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            require(relative in allowed_dirs, "UNEXPECTED_BUNDLE_DIRECTORY")
        else:
            require(path.is_file(), "NONREGULAR_BUNDLE_ENTRY")
            found.add(relative)
    require(found == expected_files, "BUNDLE_INVENTORY_FILE_SET_MISMATCH")
    m = _json(root / "manifest.json")
    canonical_manifest = (json.dumps(m, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    require(
        (root / "manifest.json").read_bytes() == canonical_manifest,
        "MANIFEST_BYTE_ENCODING_MISMATCH",
    )
    require(m.get("bundle_schema") == SCHEMA, "BUNDLE_SCHEMA_MISMATCH")
    require(
        m.get("manifest_hash") == digest({k: v for k, v in m.items() if k != "manifest_hash"}),
        "MANIFEST_SELF_HASH_MISMATCH",
    )
    inv = m["file_inventory"]
    require(isinstance(inv, list) and len(inv) == len(ROLES), "INVENTORY_SIZE_MISMATCH")
    names = []
    for item in inv:
        require(
            set(item) == {"relative_path", "sha256", "size_bytes", "role"},
            "INVENTORY_SCHEMA_MISMATCH",
        )
        _relative(item["relative_path"])
        names.append(item["relative_path"])
    require(
        len(names) == len(set(names)) and set(names) == set(ROLES), "INVENTORY_PATH_SET_MISMATCH"
    )
    require(inv == _inventory(root), "BUNDLE_FILE_HASH_SIZE_OR_ROLE_MISMATCH")
    require(
        m["bundle_content_hash"] == digest(inv) and m["bundle_id"] == "E3-" + digest(inv),
        "BUNDLE_CONTENT_HASH_MISMATCH",
    )
    stamp = datetime.fromisoformat(m["created_at"])
    require(stamp.tzinfo is not None, "AWARE_BUNDLE_CLOCK_REQUIRED")
    for p in ROLES:
        if p.endswith(".json"):
            _json(root / p)
    require((root / "README.txt").read_text() == README, "README_IDENTITY_MISMATCH")
    entries, evidence = e2.verify_pair(root / CANDIDATE, root / BASELINE, root / PUBLIC)
    metadata = _metadata(entries, evidence)
    require(
        set(m)
        == set(metadata)
        | {"bundle_id", "bundle_content_hash", "file_inventory", "created_at", "manifest_hash"},
        "MANIFEST_SCHEMA_FIELDS_MISMATCH",
    )
    require(all(m[k] == v for k, v in metadata.items()), "MANIFEST_ARTIFACT_METADATA_MISMATCH")
    _provenance(root)
    return {
        **metadata,
        "bundle_id": m["bundle_id"],
        "bundle_content_hash": m["bundle_content_hash"],
        "bundle_verify": "PASS",
        "scientific_score_role": "NONE",
    }


def pack(
    candidate: Path,
    baseline: Path,
    receipt: Path,
    seal: Path,
    contract: Path,
    public: Path,
    output: Path,
) -> Record:
    output = _destination(output)
    sources = {
        CANDIDATE: candidate,
        BASELINE: baseline,
        RECEIPT: receipt,
        SEAL: seal,
        CONTRACT: contract,
        PUBLIC: public,
    }
    before = {}
    for name, path in sources.items():
        _json(path)
        before[name] = (file_hash(path), path.stat().st_size, path.stat().st_mtime_ns)
    entries, evidence = e2.verify_pair(candidate, baseline, public)
    with tempfile.TemporaryDirectory(prefix=".e3-pack-", dir=output.parent) as staging:
        staged = Path(staging) / "payload"
        staged.mkdir(mode=0o700)
        for name, source in sources.items():
            target = staged / name
            target.parent.mkdir(mode=0o700, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o600)
        (staged / "README.txt").write_text(README)
        inv = _inventory(staged)
        identity = digest(inv)
        m = {
            **_metadata(entries, evidence),
            "bundle_id": "E3-" + identity,
            "bundle_content_hash": identity,
            "file_inventory": inv,
            "created_at": datetime.now(UTC).isoformat(),
        }
        m["manifest_hash"] = digest(m)
        _write(staged / "manifest.json", m)
        result = verify(staged)
        require(
            all(
                before[n] == (file_hash(p), p.stat().st_size, p.stat().st_mtime_ns)
                for n, p in sources.items()
            ),
            "SOURCE_CHANGED_DURING_PACK",
        )
        _durable(staged)
        _publish(staged, output)
    return {**result, "portable_bundle_created": True, "original_artifact_bytes_unchanged": True}


def restore(bundle: Path, output: Path) -> Record:
    result = verify(bundle)
    output = _destination(output)
    require(not output.is_relative_to(bundle.resolve()), "RESTORE_INSIDE_SOURCE_REJECTED")
    with tempfile.TemporaryDirectory(prefix=".e3-restore-", dir=output.parent) as staging:
        staged = Path(staging) / "payload"
        shutil.copytree(bundle, staged, symlinks=False)
        require(verify(staged) == result, "RESTORED_IDENTITY_MISMATCH")
        _durable(staged)
        _publish(staged, output)
    return {**result, "restore_verify": "PASS", "restored_artifact_hash_parity": "PASS"}


def verify_runtime(restored: Path, registry: Path) -> Record:
    result = verify(restored)
    expected, _ = e2.verify_pair(restored / CANDIDATE, restored / BASELINE, restored / PUBLIC)
    record = read(registry)
    require(
        record.get("record_hash")
        == digest({k: v for k, v in record.items() if k != "record_hash"}),
        "RUNTIME_REGISTRY_SELF_HASH_MISMATCH",
    )
    require(
        record["entries"] == expected and record["schema"] == e1.SCHEMA,
        "RESTORED_REGISTRY_PATH_OR_IDENTITY_MISMATCH",
    )
    return {**result, "runtime_registry_verify": "PASS"}


def drill_result(restored: Path, registry: Path, store: Path, forecast_id: str) -> Record:
    result = verify_runtime(restored, registry)
    forecast = e1.verify_research_forecast(store, forecast_id)
    require(
        forecast["test_only"] is True and forecast["registry_hash"] == file_hash(registry),
        "RESTORED_TEST_FORECAST_BINDING_MISMATCH",
    )
    require(
        list(forecast["artifact_entries"].values()) == read(registry)["entries"],
        "RESTORED_FORECAST_REGISTRY_MISMATCH",
    )
    r = {
        "schema": SCHEMA + "_DRILL",
        "bundle_id": result["bundle_id"],
        "bundle_content_hash": result["bundle_content_hash"],
        "registry_file_hash": file_hash(registry),
        "forecast_id": forecast_id,
        "forecast_seal_hash": forecast["record_hash"],
        "test_only_issuance_result": "PASS",
        "real_issuance_enabled": False,
        "scientific_score_role": "NONE",
    }
    r["result_hash"] = digest(r)
    return r


def audit_export(
    bundle: Path, restored: Path, registry: Path, result_path: Path, store: Path, output: Path
) -> Record:
    custody = verify(bundle)
    require(verify(restored) == custody, "AUDIT_RESTORE_IDENTITY_MISMATCH")
    result = _json(result_path)
    require(
        result == drill_result(restored, registry, store, result["forecast_id"]),
        "AUDIT_DRILL_RESULT_MISMATCH",
    )
    report = {
        **{key: value for key, value in custody.items() if not key.endswith("_relative_path")},
        "candidate_model_id": e2.EXECUTION + "_CANDIDATE",
        "comparator_model_id": e2.EXECUTION + "_BASELINE",
        "comparator_registry_id": "V0_12_COMPARATOR_BASELINE",
        "restore_verify": "PASS",
        "runtime_registry_verify": "PASS",
        "test_only_issuance_result": "PASS",
        "forecast_seal_hash": result["forecast_seal_hash"],
        "real_issuance_enabled": False,
        "stable_gain": False,
        "prospective_accuracy_validated": False,
        "production_approved": False,
        "scientific_score_role": "NONE",
        "audit_export_sanitized": True,
    }
    report["audit_hash"] = digest(report)
    _portable(report)
    # Audit is a small create-only file, published only after all bindings pass.
    output = _destination(output)
    with tempfile.TemporaryDirectory(prefix=".e3-audit-", dir=output.parent) as staging:
        path = Path(staging) / "report.json"
        _write(path, report)
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        os.link(path, output)
    return report
