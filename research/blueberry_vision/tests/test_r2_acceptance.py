"""Independent source-boundary acceptance; no production data is read or imported."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from research.blueberry_vision.r2_common import file_hash, read_json

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = Path(__file__).resolve().parents[1]

# Independently fixed M0/R1 source byte identities; neither fixture regeneration
# nor a change to the environment report can silently redefine these assertions.
SOURCE_SHA256 = {
    "research/blueberry_vision/contracts.py": (
        "f1c67186ce050c5d2368f34d38d946fbdb5b6096e9e076c450dd8cd0c7b8c8a2"
    ),
    "research/blueberry_vision/validate_manifest.py": (
        "9ff23c888e4a4bec816e8bf16a3e8b7823b617b9c4977c40697a3cba3db314d9"
    ),
    "research/blueberry_vision/tests/test_validator.py": (
        "327d461f6e83653ddda520161f426a76ac83114caf51791ec189df2687b3e453"
    ),
    "research/blueberry_vision/README.md": (
        "343049be4434583e08082ad651aa9224956b9fccf390babc48b5eaaf2ca60803"
    ),
    "research/blueberry_vision/experiment_protocol_r1.json": (
        "f64591d95400cc9735e99d6483df5b49fee48d40bea68c216137e6a2e18915ad"
    ),
    "docs/research/blueberry-vision-data-contract-r1.md": (
        "44d60dd2ff84accc5c18edf0f81b1c5bf70d5ac6c75e18489c2260faedf9ae84"
    ),
    "pyproject.toml": ("c9210aeadcf68e6ded852d778e380737bc644e3a3a5766c64e9d412654c384df"),
    "uv.lock": ("02f743c0d2ecc884f453c2b6bc4570faf1da6cbca9513dce01e4e5a9d375717e"),
}


@pytest.mark.parametrize(("relative", "expected"), SOURCE_SHA256.items())
def test_r1_contract_and_production_dependency_bytes_are_unchanged(
    relative: str, expected: str
) -> None:
    assert file_hash(REPOSITORY_ROOT / relative) == expected


def test_research_modules_do_not_import_production_or_network_services() -> None:
    forbidden = {"backend", "sqlalchemy", "httpx", "requests", "socket", "urllib", "boto3"}
    for source in sorted(RESEARCH_ROOT.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [(node.module or "").split(".")[0]]
            else:
                continue
            assert forbidden.isdisjoint(imports), source.name


def test_committed_training_evidence_contains_only_synthetic_train_identities() -> None:
    manifest = read_json(RESEARCH_ROOT / "evidence/r2/dataset_manifest.json")
    model = read_json(RESEARCH_ROOT / "evidence/r2/model_manifest.json")
    assert manifest["SYNTHETIC"] is True and model["SYNTHETIC"] is True
    assert all(record["SYNTHETIC"] is True for record in manifest["images"])
    train_ids = {record["image_id"] for record in manifest["images"] if record["split"] == "train"}
    held_out_ids = {
        record["image_id"] for record in manifest["images"] if record["split"] != "train"
    }
    assert set(model["train_image_ids"]) == train_ids
    assert set(model["train_image_ids"]).isdisjoint(held_out_ids)
    assert model["train_image_count"] == len(train_ids)
