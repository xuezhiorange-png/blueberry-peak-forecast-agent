"""S3 private artifact custody and lazy label access, separate from model fitting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_base10_benchmark import (
    EXPECTED_COUNTS,
    SEASONS,
    access_allowed,
    flatten_features,
    verify_seal,
)
from backend.app.area_yield.v015_research_cohort import canonical, digest

DATASET_MANIFEST_HASH = "7f76d97c34679c31824271ca817835a9ed953504261abf2a249b896713e2e178"
FEATURE_HASHES = {
    "TRAIN": "37ecab5726a1846016c0e952750a3d3b926b8625dd414caf8343d86085cfea83",
    "VALIDATION": "547aa919a3d53217fb97efe03647b7918aace5e25cebc3f4bbcc15394d7ad477",
    "EXPOSED_OOT": "90fa6756bf27f57c7effdf47f0f51d474d6379ab1816c0f9f236bf93b6ad725e",
}
LABEL_HASHES = {
    "TRAIN": "6bee7e05f75f6031db94dca6ce85dd3d11bfddcaece56a98a2eb228e74c3fac5",
    "VALIDATION": "acfd434a5c21e323099ba51c1da91ad5cded17465746715f0c92cc67d3dc8e0e",
    "EXPOSED_OOT": "710ca7427d37f5a9f80b0b310d369a97990a8707d976cbb1744f5edcf7529262",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def save(path: Path, value: Any) -> None:
    """Create owner-only immutable derived output; never overwrite source data."""
    raw = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("IMMUTABLE_OUTPUT_CONFLICT")
        return
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o600)


def load(path: Path) -> Any:
    return json.loads(path.read_bytes())


def seal_files(
    root: Path, *, phase: str, names: list[str], rowset_hash: str, contract_hash: str
) -> dict[str, Any]:
    seal = {
        "phase": phase,
        "label_scope": "VALIDATION" if phase == "A" else "EXPOSED_OOT",
        "labels_read": False,
        "sealed_at": datetime.now().astimezone().isoformat(),
        "contract_hash": contract_hash,
        "rowset_hash": rowset_hash,
        "predictions": {name: sha((root / name).read_bytes()) for name in names},
        "external_trusted_timestamp": False,
    }
    seal["seal_hash"] = digest(seal)
    return seal


@dataclass(frozen=True)
class LabelPermit:
    split: str
    seal_hash: str


def check_files(
    root: Path, seal: dict[str, Any], *, expected_names: list[str], contract_hash: str, phase: str
) -> LabelPermit:
    verify_seal(seal)
    if seal["phase"] != phase or seal["contract_hash"] != contract_hash:
        raise ValueError("SEAL_CONTRACT_DRIFT")
    if set(seal["predictions"]) != set(expected_names):
        raise ValueError("SEAL_CANDIDATE_ROWSET_DRIFT")
    for name in expected_names:
        if sha((root / name).read_bytes()) != seal["predictions"][name]:
            raise ValueError("SEALED_PREDICTION_DRIFT")
    return LabelPermit("VALIDATION" if phase == "A" else "EXPOSED_OOT", seal["seal_hash"])


class FrozenDataset:
    """No label file hash/read/stat before its authorized stage and seal gate.

    Expected label hashes are verified in the frozen manifest up front, but the
    actual label bytes are opened/hash-checked only after the relevant seal.
    No directory scan, Weather8 input or raw database access is performed.
    """

    def __init__(self, root: Path, phase: str, *, label_gate: LabelPermit | None = None) -> None:
        self.root, self.phase, self.label_gate = root, phase, label_gate
        self.label_reads: list[str] = []
        manifest = load(root / "manifest.json")
        if (
            manifest.get("manifest_hash") != DATASET_MANIFEST_HASH
            or digest({k: v for k, v in manifest.items() if k != "manifest_hash"})
            != DATASET_MANIFEST_HASH
        ):
            raise ValueError("DATASET_DRIFT")
        for split in EXPECTED_COUNTS:
            if manifest["dataset_hashes"][split + "_FEATURESET_HASH"] != FEATURE_HASHES[split]:
                raise ValueError("DATASET_DRIFT")
            if manifest["dataset_hashes"][split + "_LABELSET_HASH"] != LABEL_HASHES[split]:
                raise ValueError("DATASET_DRIFT")

    def features(self, split: str) -> list[dict[str, Any]]:
        if not access_allowed(self.phase, split, labels=False):
            raise ValueError("FEATURE_PHASE_DENIED")
        path = self.root / "feature_zone" / f"{split.lower()}-base10.json"
        raw = path.read_bytes()
        if sha(raw) != FEATURE_HASHES[split]:
            raise ValueError("DATASET_DRIFT")
        rows: list[dict[str, Any]] = json.loads(raw)
        # Entire metadata envelope is checked before numeric/label use.
        if len(rows) != EXPECTED_COUNTS[split] or any(
            r["split"] != split or r["season"] != SEASONS[split] for r in rows
        ):
            raise ValueError("UNAUTHORIZED_SEASON_OR_ROW_COUNT")
        for r in rows:
            if "label_hash" in r or "labels" in r or "weather8" in r:
                raise ValueError("FEATURE_ZONE_CONTAMINATION")
            if digest({k: v for k, v in r.items() if k != "row_hash"}) != r["row_hash"]:
                raise ValueError("FEATURE_ROW_HASH_DRIFT")
            if digest(r["base10"]) != r["feature_hash"]:
                raise ValueError("FEATURE_VECTOR_HASH_DRIFT")
            origin = datetime.fromisoformat(r["forecast_origin"])
            if origin.tzinfo is None or r["target_dates"] != [
                (origin.date() + timedelta(days=i)).isoformat() for i in range(1, 16)
            ]:
                raise ValueError("TARGET_DATE_DRIFT")
        flatten_features(rows)
        return sorted(rows, key=lambda r: r["row_key"])

    def labels(self, split: str, features: list[dict[str, Any]]) -> list[list[str]]:
        if not access_allowed(self.phase, split, labels=True) or (
            split != "TRAIN"
            and (not isinstance(self.label_gate, LabelPermit) or self.label_gate.split != split)
        ):
            raise ValueError("LABEL_PHASE_OR_SEAL_DENIED")
        raw = (self.root / "label_zone" / f"{split.lower()}-labels.json").read_bytes()
        self.label_reads.append(split)
        if sha(raw) != LABEL_HASHES[split]:
            raise ValueError("DATASET_DRIFT")
        rows = json.loads(raw)
        if len(rows) != EXPECTED_COUNTS[split] or any(
            r["season"] != SEASONS[split] or r["split"] != split for r in rows
        ):
            raise ValueError("UNAUTHORIZED_SEASON_OR_ROW_COUNT")
        ordered = sorted(rows, key=lambda r: r["row_key"])
        if len(ordered) != len(features):
            raise ValueError("COMMON_ROWSET")
        result = []
        for r, f in zip(ordered, features, strict=True):
            if r["row_key"] != f["row_key"] or r["feature_hash"] != f["feature_hash"]:
                raise ValueError("COMMON_ROWSET")
            if r["target_dates"] != f["target_dates"] or r["base_id"] != f["base_id"]:
                raise ValueError("COMMON_ROWSET")
            if digest({k: v for k, v in r.items() if k != "row_hash"}) != r["row_hash"]:
                raise ValueError("LABEL_ROW_HASH_DRIFT")
            if digest(r["labels"]) != r["label_hash"]:
                raise ValueError("LABEL_VECTOR_HASH_DRIFT")
            values = r["labels"]["daily"]
            if len(values) != 15 or any(
                not Decimal(v).is_finite() or Decimal(v) < 0 for v in values
            ):
                raise ValueError("LABEL_INVALID")
            result.append(values)
        return result


def validate_public(value: Any) -> None:
    forbidden = {
        "base_id",
        "base_name",
        "daily",
        "labels",
        "prediction_values",
        "coefficients",
        "latitude",
        "longitude",
        "coordinates",
        "password",
        "token",
        "source_file",
    }
    if isinstance(value, dict):
        if forbidden & value.keys():
            raise ValueError("PUBLIC_PRIVACY")
        for item in value.values():
            validate_public(item)
    elif isinstance(value, list):
        for item in value:
            validate_public(item)
    elif isinstance(value, str) and any(
        part in value for part in ("/Users/", "/private/", "/tmp/", "postgresql://")
    ):
        raise ValueError("PUBLIC_PRIVATE_PATH")
