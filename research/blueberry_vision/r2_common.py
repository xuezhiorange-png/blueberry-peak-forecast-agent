"""Canonical research artifacts; no database, network, or mutable run overwrites."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

JSONDict = dict[str, Any]
CLASS_LABEL = "SYNTHETIC_BLUEBERRY_VISIBLE"
TASK_ID = "BLUEBERRY_VISION_R2_OFFLINE_DETECTION_COUNTING_PIPELINE"


def canonical_hash(value: object) -> str:
    """Use R1's UTF-8/sorted-key/non-finite-rejecting canonical JSON convention."""
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unique_keys(pairs: list[tuple[str, Any]]) -> JSONDict:
    result: JSONDict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("NONFINITE_JSON_NUMBER")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("NONFINITE_JSON_NUMBER")
    return number


def read_json(path: Path, *, max_bytes: int = 8_000_000) -> JSONDict:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("JSON_SIZE_POLICY_INVALID")
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("JSON_SIZE_LIMIT")
    value = json.loads(
        data,
        object_pairs_hook=_unique_keys,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


def write_json_new(path: Path, value: object) -> str:
    """Never replace historical experiments, even when outputs look equivalent."""
    content = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content + "\n")
    return file_hash(path)


def seal(value: JSONDict, hash_key: str) -> JSONDict:
    payload = {key: item for key, item in value.items() if key != hash_key}
    return {**payload, hash_key: canonical_hash(payload)}


def verify_seal(value: JSONDict, hash_key: str) -> bool:
    return value.get(hash_key) == canonical_hash(
        {key: item for key, item in value.items() if key != hash_key}
    )


def dataset_split_hash(images: list[JSONDict]) -> str:
    """Bind declared independent image/group/seed identities, without ground-truth labels."""
    keys = (
        "image_id",
        "split",
        "capture_session_id",
        "sampling_unit_id",
        "template_group_id",
        "near_duplicate_group_id",
        "generation_seed",
    )
    rows = [{key: record[key] for key in keys} for record in images]
    return canonical_hash(sorted(rows, key=lambda row: row["image_id"]))
